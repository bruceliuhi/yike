"""Bounded background supervisor for confirmed dynamic public-web research."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
from datetime import timedelta
import json
import threading

from pilot.candidate_ingestion import CandidateIngestionError
from pilot.codex_research_worker import run_public_research_mission
from pilot.customer_research_context import CustomerResearchContextStore
from pilot.durable_research_dispatch import DurableResearchDispatcher
from pilot.execution_contract import ExecutionRuntimeError, canonical_uuid
from pilot.research_runtime_config import dynamic_research_snapshot
from pilot.research_page_selection import parse_page_selection


_COUNTER = ("issued", "pending", "succeeded", "failed", "unknown")


def _discovery_limits(sources):
    # Per-kind ceilings reserve one attempt of the other kind, not fixed pots.
    # Their sum is NOT a grant: the durable SOURCE_READ ledger owns the total.
    return min(10, sources - 1), sources - 1


def _assessment_reserve(model_calls, max_records, max_reads):
    return min(max_records, max_reads, max(1, model_calls // 2))


def _stop_code(value, fallback):
    return value if type(value) is str and 1 <= len(value) <= 128 else fallback


class DynamicResearchRuntimeService:
    """Own at most two in-process workers; PostgreSQL remains authoritative."""

    def __init__(self, fixed, *, journal, candidates, agent,
                 mission=run_public_research_mission, max_workers=2):
        if (type(max_workers) is not int or not 1 <= max_workers <= 2
                or not callable(mission)):
            raise ValueError("invalid dynamic runtime configuration")
        self.fixed = fixed
        self.journal = journal
        self.candidates = candidates
        self.agent = agent
        self.mission = mission
        self.database = fixed.database
        self.execution = fixed.execution
        # The existing assessment admission fence is owned by the facade.
        # Share that persisted owner identity instead of inventing a second
        # coordinator principal for the same task.
        self.owner = fixed.owner
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="yike-dynamic-research"
        )
        self._capacity = threading.BoundedSemaphore(max_workers)
        self._shutdown = threading.Event()
        self._guard = threading.Lock()
        self._futures = set()

    @staticmethod
    def capability():
        return {
            "contractVersion": 4,
            "sourceScope": "PUBLIC_WEB_AGENT",
            "sourceLabel": "公开网页自主研究",
            "sourceIds": [
                "v2ex-latest-v1", "v2ex-qna-v1",
                "v2ex-outsourcing-authors-v1", "public-web-agent-v1",
            ],
            "maxPlannedSources": 3,
            "executionMode": "SERVER_BACKGROUND",
            "limits": {
                "maxSearches": 10, "maxSources": 100,
                "maxModelCalls": 20, "maxMinutes": 30,
                "maxRuntimeSeconds": 1800,
            },
            "settlementState": "PENDING",
        }

    def advance(self, claims, task_id, run_id):
        task_id, run_id = map(canonical_uuid, (task_id, run_id))
        if self._shutdown.is_set():
            raise ExecutionRuntimeError("runtime_shutdown", 503)
        if not self._capacity.acquire(blocking=False):
            raise ExecutionRuntimeError("worker_capacity_exceeded", 409)
        retained = False
        try:
            election = self._elect(claims, task_id, run_id)
            if election is None:
                return self.status(claims, task_id)
            generation, limits = election
            try:
                future = self._executor.submit(
                    self._run, claims, task_id, run_id, generation, limits
                )
            except RuntimeError:
                self._restore_queued(claims, task_id, generation)
                raise ExecutionRuntimeError("runtime_shutdown", 503) from None
            retained = True
            with self._guard:
                self._futures.add(future)
            future.add_done_callback(self._finished)
            return self.status(claims, task_id)
        finally:
            if not retained:
                self._capacity.release()

    def _finished(self, future):
        with self._guard:
            self._futures.discard(future)
        self._capacity.release()

    def _elect(self, claims, task_id, run_id):
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self.execution._active(cursor, claims)
            task, run, platforms = self.execution._locks(cursor, claims, tenant, task_id)
            if (run is None or run["run_id"] != run_id or len(platforms) != 1
                    or platforms[0]["platform"] != "PUBLIC_WEB"
                    or platforms[0]["access_mode"] != "PUBLIC_ANONYMOUS"
                    or platforms[0]["connection_id"] is not None
                    or platforms[0]["connection_version"] is not None
                    or not dynamic_research_snapshot(task["configuration_snapshot"])):
                raise ExecutionRuntimeError("request_conflict", 409)
            cursor.execute(
                "SELECT source_limit,minute_limit,model_call_limit FROM "
                "pilot_research_reservations WHERE tenant_id=%s AND owner_user_id=%s "
                "AND task_id=%s AND run_id=%s FOR UPDATE",
                (tenant, claims.user_id, task_id, run_id),
            )
            limits = cursor.fetchone()
            if limits is None:
                raise ExecutionRuntimeError("resource_unavailable", 503)
            now = self.execution._now(cursor)
            if (task["status"] in ("CANCELLING", "CANCELED")
                    or run["status"] in ("CANCELLING", "CANCELED")
                    or task["status"] == "SUCCEEDED" or run["status"] == "SUCCEEDED"):
                return None
            if now >= min(task["deadline_at"],
                          task["created_at"] + timedelta(minutes=limits[1])):
                raise ExecutionRuntimeError("task_unavailable", 409)
            row = self.fixed._coordinator(
                cursor, tenant, claims.user_id, task_id, lock=True
            )
            if row is None:
                cursor.execute(
                    "INSERT INTO pilot_research_runtime"
                    "(tenant_id,owner_user_id,task_id,run_id) VALUES (%s,%s,%s,%s)",
                    (tenant, claims.user_id, task_id, run_id),
                )
                row = self.fixed._coordinator(
                    cursor, tenant, claims.user_id, task_id, lock=True
                )
            if row[0] != run_id:
                raise ExecutionRuntimeError("request_conflict", 409)
            if row[4] == "RUNNING" and row[3] is not None and row[3] <= now:
                cursor.execute(
                    "UPDATE pilot_research_runtime SET current_owner=NULL,"
                    "lease_expires_at=NULL,phase='STOPPED',stop_code='worker_lost',"
                    "updated_at=clock_timestamp() WHERE tenant_id=%s AND owner_user_id=%s "
                    "AND task_id=%s", (tenant, claims.user_id, task_id),
                )
                return None
            if (row[4] in ("STOPPED", "COMPLETED", "CANCELED")
                    or row[2] is not None and row[3] is not None and row[3] > now):
                return None
            generation = row[1] + 1
            lease = min(
                now + timedelta(seconds=1800), task["deadline_at"],
                task["created_at"] + timedelta(minutes=limits[1]),
            )
            cursor.execute(
                "UPDATE pilot_research_runtime SET generation=%s,current_owner=%s,"
                "lease_expires_at=%s,phase='RUNNING',stop_code=NULL,"
                "updated_at=clock_timestamp() WHERE tenant_id=%s AND owner_user_id=%s "
                "AND task_id=%s",
                (generation, self.owner, lease, tenant, claims.user_id, task_id),
            )
            self.execution._active(cursor, claims)
            return generation, {
                "sources": limits[0], "minutes": limits[1],
                "modelCalls": limits[2], "maxRecords": task["max_records"],
                "seconds": max(1, min(1800, int((lease - now).total_seconds()))),
            }

    def _run(self, claims, task_id, run_id, generation, limits):
        try:
            context = CustomerResearchContextStore(self.execution).load(
                claims, task_id=task_id, run_id=run_id
            )
            dispatcher = DurableResearchDispatcher(
                self.journal, claims, task_id=task_id, run_id=run_id,
                generation=generation, coordinator_owner=self.owner,
                context_binding=context["binding"],
            )
            max_searches, max_reads = _discovery_limits(limits["sources"])
            reserve = _assessment_reserve(
                limits["modelCalls"], limits["maxRecords"], max_reads
            )
            result = self.mission(
                json.loads(context["context_json"])["seller_description"],
                codex_binary=self.agent.codex_binary,
                python_binary=self.agent.python_binary,
                api_key=self.agent.api_key,
                model=self.agent.model,
                search_api_key=self.agent.search_api_key,
                max_searches=max_searches,
                max_reads=max_reads,
                max_requests=limits["modelCalls"] - reserve,
                max_seconds=limits["seconds"],
                cancelled=lambda: self._cancelled(
                    claims, task_id, run_id, generation
                ),
                research_context=json.loads(context["context_json"]),
                effect_dispatcher=dispatcher,
            )
            if self._cancelled(claims, task_id, run_id, generation):
                self._settle_cancellation(claims, task_id, generation)
                return
            if (type(result) is not dict or result.get("status") != "COMPLETED"):
                code = result.get("code") if type(result) is dict else None
                self._release_if_owned(
                    claims, task_id, generation, "STOPPED",
                    _stop_code(code, "mission_failed"),
                )
                return
            entries = self._successful_reads(claims, task_id, run_id, generation)
            stop = self._durable_stop(claims, task_id, run_id, generation)
            if stop is not None:
                self._release_if_owned(claims, task_id, generation, "STOPPED", stop)
                return
            if result.get("research_binding") != context["binding"]:
                raise ExecutionRuntimeError("research_selection_invalid", 409)
            decisions = parse_page_selection(
                result.get("summary"), [entry["evidence"] for entry in entries]
            )
            by_page = {(item["url"], item["content_sha256"]): item for item in decisions}
            receipts = []
            for entry in entries:
                if self._cancelled(claims, task_id, run_id, generation):
                    self._settle_cancellation(claims, task_id, generation)
                    return
                receipts.append(self.candidates.publish(
                    claims, task_id=task_id, run_id=run_id,
                    sequence=entry["sequence"], generation=generation,
                    coordinator_owner=self.owner, context_binding=context["binding"],
                    selection=by_page[(entry["evidence"]["url"],
                                       entry["evidence"]["content_sha256"])],
                ))
            stop = self._durable_stop(claims, task_id, run_id, generation)
            if stop is not None:
                self._release_if_owned(claims, task_id, generation, "STOPPED", stop)
                return
            task = self.execution.get_task(claims, task_id)
            for receipt in receipts:
                for item in receipt["items"]:
                    if self._cancelled(claims, task_id, run_id, generation):
                        self._settle_cancellation(claims, task_id, generation)
                        return
                    stop = self._durable_stop(claims, task_id, run_id, generation)
                    if stop is not None:
                        self._release_if_owned(
                            claims, task_id, generation, "STOPPED", stop
                        )
                        return
                    if not self._model_slot_available(claims, task_id, run_id, limits):
                        self._release_if_owned(
                            claims, task_id, generation, "STOPPED",
                            "resource_limit_exceeded",
                        )
                        return
                    request_id = self.fixed.orchestrator._review_action(
                        task_id, run_id, item
                    )
                    try:
                        review = self.fixed.orchestrator.reviews.get_request(
                            claims, request_id
                        )
                    except CandidateIngestionError as error:
                        if (error.code, error.status) != ("request_not_found", 404):
                            raise
                        payload = self.fixed.orchestrator._current_payload(
                            claims, task, receipt, item, request_id
                        )
                        if payload is None:
                            continue
                        review = self.fixed.orchestrator.reviews.assess_research(
                            claims, payload, task_id=task_id, run_id=run_id,
                            observation_id=item["observation_id"],
                            _admission=self._assessment_admission(
                                claims, task_id, run_id, generation
                            ),
                        )
                    if review.get("kind") != "assessment":
                        if self._cancelled(claims, task_id, run_id, generation):
                            self._settle_cancellation(claims, task_id, generation)
                            return
                        durable = self._durable_stop(
                            claims, task_id, run_id, generation
                        )
                        self._release_if_owned(
                            claims, task_id, generation, "STOPPED",
                            durable or ("assessment_unknown"
                                if review.get("kind") == "pending"
                                else "assessment_failed"),
                        )
                        return
            if self._cancelled(claims, task_id, run_id, generation):
                self._settle_cancellation(claims, task_id, generation)
                return
            self.fixed._complete(
                claims, task_id, run_id, generation,
                _admission=self._completion_admission(
                    claims, task_id, run_id, generation
                ),
            )
        except BaseException as error:
            code = _stop_code(error.code, "advance_failed") if isinstance(
                error, (ExecutionRuntimeError, CandidateIngestionError)
            ) else "advance_failed"
            try:
                self._release_if_owned(
                    claims, task_id, generation,
                    "CANCELED" if code == "task_cancelled" else "STOPPED", code,
                )
            except BaseException:
                pass

    def _successful_reads(self, claims, task_id, run_id, generation):
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self.execution._active(cursor, claims)
            self.journal._coordinator(
                cursor, tenant, claims.user_id, task_id, run_id,
                generation, self.owner,
            )
            cursor.execute(
                "SELECT sequence,result FROM pilot_research_effect_journal WHERE tenant_id=%s "
                "AND owner_user_id=%s AND task_id=%s AND run_id=%s AND kind='READ' "
                "AND status='SUCCEEDED' ORDER BY sequence",
                (tenant, claims.user_id, task_id, run_id),
            )
            return [{"sequence": row[0], "evidence": row[1]["evidence"]}
                    for row in cursor.fetchall()]

    def _model_slot_available(self, claims, task_id, run_id, limits):
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self.execution._active(cursor, claims)
            cursor.execute(
                "SELECT count(*) FROM pilot_research_resource_events WHERE tenant_id=%s "
                "AND owner_user_id=%s AND task_id=%s AND run_id=%s "
                "AND resource='MODEL_CALL'", (tenant, claims.user_id, task_id, run_id),
            )
            return cursor.fetchone()[0] < limits["modelCalls"]

    def _effect_stop(self, cursor, tenant, user, task_id, run_id, *,
                     allowed_pending_action=None, lock=False):
        from pilot.research_effect_journal import _FIELDS as journal_fields, _entry
        from pilot.research_resources import _FIELDS as resource_fields, _event
        suffix = " ORDER BY action_id FOR UPDATE" if lock else ""
        cursor.execute(
            "SELECT "+','.join(resource_fields)+" FROM pilot_research_resource_events "
            "WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s AND run_id=%s" + suffix,
            (tenant, user, task_id, run_id),
        )
        events = {event['action_id']: event for event in map(_event, cursor.fetchall())}
        cursor.execute(
            "SELECT "+','.join(journal_fields)+" FROM pilot_research_effect_journal WHERE tenant_id=%s "
            "AND owner_user_id=%s AND task_id=%s AND run_id=%s" + suffix,
            (tenant, user, task_id, run_id),
        )
        entries = [_entry(row) for row in cursor.fetchall()]
        statuses = []
        for entry in entries:
            event = events.pop(entry['action_id'],None)
            if event is not None and self.journal.prior_effect_valid(entry,event):
                continue
            statuses.append(entry['status'])
            if event is not None:
                statuses.append(event['status'])
            # A corrupt/unpaired successful receipt is not positive completion evidence.
            if entry['status']=='SUCCEEDED':
                statuses.append('FAILED')
        for event in events.values():
            if (event['action_id']==allowed_pending_action and event['resource']=='MODEL_CALL'
                    and event['status']=='ISSUED'):
                continue
            statuses.append(event['status'])
        if "UNKNOWN" in statuses:
            return "effect_unknown"
        if "FAILED" in statuses:
            return "effect_failed"
        if "ISSUED" in statuses:
            return "effect_pending"
        return None

    def _durable_stop(self, claims, task_id, run_id, generation):
        if self._shutdown.is_set():
            return "runtime_shutdown"
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self.execution._active(cursor, claims)
            self.journal._coordinator(
                cursor, tenant, claims.user_id, task_id, run_id,
                generation, self.owner,
            )
            stop = self._effect_stop(
                cursor, tenant, claims.user_id, task_id, run_id, lock=True
            )
            self.execution._active(cursor, claims)
            return stop

    def _assessment_admission(self, claims, task_id, run_id, generation):
        coordinator = self.fixed._admission(claims, task_id, run_id, generation)

        def admit(cursor, tenant, event):
            coordinator(cursor, tenant, event)
            if self._shutdown.is_set():
                raise ExecutionRuntimeError("runtime_shutdown", 503)
            stop = self._effect_stop(
                cursor, tenant, claims.user_id, task_id, run_id,
                allowed_pending_action=event["action_id"], lock=True,
            )
            if stop is not None:
                raise ExecutionRuntimeError(stop, 409)
            return True
        return admit

    def _completion_admission(self, claims, task_id, run_id, generation):
        def admit(cursor, tenant):
            if self._shutdown.is_set():
                raise ExecutionRuntimeError("runtime_shutdown", 503)
            row = self.fixed._coordinator(
                cursor, tenant, claims.user_id, task_id, lock=True
            )
            if (row is None or row[0] != run_id or row[1] != generation
                    or row[2] != self.owner or row[4] != "RUNNING"):
                raise ExecutionRuntimeError("lease_conflict", 409)
            stop = self._effect_stop(
                cursor, tenant, claims.user_id, task_id, run_id, lock=True
            )
            if stop is not None:
                raise ExecutionRuntimeError(stop, 409)
            return True
        return admit

    def _cancelled(self, claims, task_id, run_id, generation):
        if self._shutdown.is_set():
            return True
        try:
            with self.database.connect() as connection, connection.cursor() as cursor:
                tenant = self.execution._active(cursor, claims)
                cursor.execute(
                    "SELECT t.status,r.status,c.run_id,c.generation,c.current_owner,"
                    "c.lease_expires_at,c.phase,clock_timestamp() FROM pilot_collection_tasks t "
                    "JOIN pilot_collection_runs r USING(tenant_id,owner_user_id,task_id) "
                    "JOIN pilot_research_runtime c USING(tenant_id,owner_user_id,task_id,run_id) "
                    "WHERE t.tenant_id=%s AND t.owner_user_id=%s AND t.task_id=%s",
                    (tenant, claims.user_id, task_id),
                )
                row = cursor.fetchone()
                return (row is None or row[0] not in ("PENDING", "RUNNING")
                    or row[1] not in ("PENDING", "RUNNING") or row[2] != run_id
                    or row[3] != generation or row[4] != self.owner
                    or row[5] is None or row[5] <= row[7] or row[6] != "RUNNING")
        except BaseException:
            return True

    def _release_if_owned(self, claims, task_id, generation, phase, code):
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self.execution._active(cursor, claims)
            cursor.execute(
                "UPDATE pilot_research_runtime SET current_owner=NULL,lease_expires_at=NULL,"
                "phase=%s,stop_code=%s,updated_at=clock_timestamp() WHERE tenant_id=%s "
                "AND owner_user_id=%s AND task_id=%s AND generation=%s AND current_owner=%s "
                "AND phase='RUNNING' AND lease_expires_at>clock_timestamp()",
                (phase, code, tenant, claims.user_id, task_id, generation, self.owner),
            )

    def _settle_cancellation(self, claims, task_id, generation):
        if self._shutdown.is_set():
            self._release_if_owned(
                claims, task_id, generation, "STOPPED", "runtime_shutdown"
            )
            return
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self.execution._active(cursor, claims)
            cursor.execute(
                "SELECT t.status,r.status FROM pilot_collection_tasks t "
                "JOIN pilot_collection_runs r USING(tenant_id,owner_user_id,task_id) "
                "WHERE t.tenant_id=%s AND t.owner_user_id=%s AND t.task_id=%s",
                (tenant, claims.user_id, task_id),
            )
            row = cursor.fetchone()
        if row is not None and (row[0] in ("CANCELLING", "CANCELED")
                                or row[1] in ("CANCELLING", "CANCELED")):
            self._release_if_owned(claims, task_id, generation, "CANCELED", None)

    def _restore_queued(self, claims, task_id, generation):
        # No future owns this election. Unlike a late worker release, this may
        # safely clear an exact just-elected row even if its short lease crossed
        # the wall-clock deadline while executor.submit rejected it.
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self.execution._active(cursor, claims)
            cursor.execute(
                "UPDATE pilot_research_runtime SET current_owner=NULL,lease_expires_at=NULL,"
                "phase='QUEUED',stop_code=NULL,updated_at=clock_timestamp() WHERE tenant_id=%s "
                "AND owner_user_id=%s AND task_id=%s AND generation=%s AND current_owner=%s "
                "AND phase='RUNNING'", (tenant, claims.user_id, task_id, generation, self.owner),
            )

    def _expire_lease(self, claims, task_id):
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self.execution._active(cursor, claims)
            cursor.execute(
                "UPDATE pilot_research_runtime SET current_owner=NULL,lease_expires_at=NULL,"
                "phase='STOPPED',stop_code='worker_lost',updated_at=clock_timestamp() "
                "WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s AND phase='RUNNING' "
                "AND lease_expires_at<=clock_timestamp()",
                (tenant, claims.user_id, task_id),
            )

    def status(self, claims, task_id):
        task_id = canonical_uuid(task_id)
        self._expire_lease(claims, task_id)
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                cursor.execute("SELECT clock_timestamp()")
                now = cursor.fetchone()[0]
                tenant, identity = self.fixed._identity(cursor, claims, task_id)
                run_id = identity[1]
                cursor.execute(
                    "SELECT t.configuration_snapshot,p.platform,p.access_mode,"
                    "p.connection_id,p.connection_version FROM pilot_collection_tasks t "
                    "JOIN pilot_collection_platform_runs p USING(tenant_id,owner_user_id,task_id) "
                    "WHERE t.tenant_id=%s AND t.owner_user_id=%s AND t.task_id=%s",
                    (tenant, claims.user_id, task_id),
                )
                scope = cursor.fetchall()
                if (len(scope) != 1 or not dynamic_research_snapshot(scope[0][0])
                        or scope[0][1:] != ("PUBLIC_WEB", "PUBLIC_ANONYMOUS", None, None)):
                    raise ExecutionRuntimeError("request_conflict", 409)
                coordinator = self.fixed._coordinator(
                    cursor, tenant, claims.user_id, task_id
                )
                usage, overdue = self.fixed._usage(
                    cursor, tenant, claims.user_id, task_id, run_id, now
                )
                effect_stop = self._effect_stop(cursor,tenant,claims.user_id,task_id,run_id)
                cursor.execute(
                    "SELECT kind,status,count(*) FROM pilot_research_effect_journal "
                    "WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s AND run_id=%s "
                    "AND kind IN ('SEARCH','READ') GROUP BY kind,status",
                    (tenant, claims.user_id, task_id, run_id),
                )
                discovery = {kind: {key: 0 for key in _COUNTER}
                             for kind in ("SEARCH", "READ")}
                names = {"ISSUED": "pending", "SUCCEEDED": "succeeded",
                         "FAILED": "failed", "UNKNOWN": "unknown"}
                for kind, status, count in cursor.fetchall():
                    discovery[kind]["issued"] += count
                    discovery[kind][names[status]] += count
                cursor.execute(
                    "SELECT j.sequence,b.accepted_count,b.receipt,b.execution_context FROM "
                    "pilot_research_effect_journal j LEFT JOIN pilot_candidate_batches b "
                    "ON b.tenant_id=j.tenant_id AND b.owner_user_id=j.owner_user_id "
                    "AND b.task_id=j.task_id AND b.run_id=j.run_id AND b.request_id=j.action_id "
                    "WHERE j.tenant_id=%s AND j.owner_user_id=%s AND j.task_id=%s "
                    "AND j.run_id=%s AND j.kind='READ' AND j.status='SUCCEEDED' "
                    "ORDER BY j.sequence", (tenant, claims.user_id, task_id, run_id),
                )
                batches = cursor.fetchall()
        accepted = sum(row[1] or 0 for row in batches)
        unpublished = 0
        for _, accepted_count, _, execution_context in batches:
            background = (type(execution_context) is dict
                          and execution_context.get("observed_count") == 1
                          and execution_context.get("accepted_count") == 0
                          and execution_context.get("skipped_background_count") == 1
                          and execution_context.get("skipped_invalid_count") == 0
                          and execution_context.get("skipped_budget_count") == 0
                          and type(execution_context.get("page_selection")) is dict
                          and execution_context["page_selection"].get("decision") == "BACKGROUND")
            unpublished += accepted_count is None or accepted_count == 0 and not background
        candidate_ids, analyzed, skipped = [], 0, 0
        task = self.execution.get_task(claims, task_id)
        for _, _, receipt, _ in batches:
            for item in receipt.get("items", []) if type(receipt) is dict else []:
                candidate_ids.append(item["candidate_id"])
                request_id = self.fixed.orchestrator._review_action(task_id, run_id, item)
                try:
                    review = self.fixed.orchestrator.reviews.get_request(claims, request_id)
                except CandidateIngestionError as error:
                    if (error.code, error.status) != ("request_not_found", 404):
                        raise
                    if self.fixed.orchestrator._current_payload(
                            claims, task, receipt, item, request_id) is None:
                        skipped += 1
                    continue
                analyzed += review.get("kind") == "assessment"
        task_status, run_status = identity[0], identity[2]
        canceled = (task_status in ("CANCELLING", "CANCELED")
                    or run_status in ("CANCELLING", "CANCELED")
                    or coordinator is not None and coordinator[4] == "CANCELED")
        complete = task_status == "SUCCEEDED" and run_status == "SUCCEEDED"
        pending = (effect_stop == "effect_pending"
                   or usage["sourceReads"]["pending"] + usage["modelCalls"]["pending"] > 0)
        failed = effect_stop == "effect_failed"
        unknown = (effect_stop == "effect_unknown"
                   or usage["sourceReads"]["unknown"] + usage["modelCalls"]["unknown"] > 0)
        active = bool(coordinator and coordinator[4] == "RUNNING"
                      and coordinator[2] is not None and coordinator[3] > now)
        durable_stop = bool(coordinator and coordinator[4] == "STOPPED")
        phase = ("CANCELED" if canceled else
                 "RUNNING" if active else
                 "STOPPED" if durable_stop or failed or unknown or complete and pending else
                 "COMPLETED" if complete else
                 "RUNNING" if pending else "QUEUED")
        stop = ("effect_unknown" if unknown else "effect_failed" if failed else
                "effect_pending" if complete and pending else
                _stop_code(coordinator[5], "advance_failed") if durable_stop else None)
        closeout = ("UNCERTAIN" if unknown or overdue else "DRAINING"
                    if pending or active else "RECORDED" if complete or canceled
                    else "OPEN")
        usage["resourceCloseout"] = {
            "state": closeout, "overduePermits": overdue, "asOf": now.isoformat()
        }
        queued = phase == "QUEUED"
        return {
            "contractVersion": 4, "taskId": task_id, "runId": run_id,
            "phase": phase, "sourceScope": "PUBLIC_WEB_AGENT",
            "sourceLabel": "公开网页自主研究",
            "executionMode": "SERVER_BACKGROUND",
            "acceptedOriginals": accepted, "analyzedOriginals": analyzed,
            "skippedOriginals": skipped,
            "candidateIds": list(dict.fromkeys(candidate_ids))[:100],
            "canAdvance": queued, "stopCode": stop,
            "newActionsBlocked": not queued, "effectsPending": pending,
            "usage": usage,
            "discovery": {
                "searches": discovery["SEARCH"], "reads": discovery["READ"],
                "unpublishedOriginals": unpublished,
            },
        }

    def shutdown(self, timeout_seconds=5):
        if type(timeout_seconds) not in (int, float) or timeout_seconds < 0:
            raise ValueError("invalid shutdown timeout")
        self._shutdown.set()
        with self._guard:
            futures = tuple(self._futures)
        for future in futures:
            future.cancel()
        _, pending = wait(futures, timeout=timeout_seconds)
        self._executor.shutdown(wait=False, cancel_futures=True)
        return not pending
