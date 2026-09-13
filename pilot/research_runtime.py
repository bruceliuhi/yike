"""Persisted, lease-fenced coordinator for bounded research advancement."""
from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from pilot.candidate_ingestion import CandidateIngestionError
from pilot.execution_contract import ExecutionRuntimeError, canonical_uuid
from pilot.research_source_catalog import SOURCE_IDS, source_from_snapshot


SOURCE_SCOPE = "V2EX_LATEST_INDEX"
SOURCE_LABEL = "V2EX最新主题 · 公开单源研究"


class ResearchRuntimeService:
    def __init__(self, orchestrator, *, lease_seconds=120, dynamic=None):
        self.orchestrator = orchestrator
        self.database = orchestrator.sources.resources.runtime.database
        self.execution = orchestrator.sources.resources.runtime
        self.owner = str(uuid4())
        self.lease_seconds = lease_seconds
        self.dynamic = dynamic

    def capability(self, claims, *, source_catalog_version=None, source_plan_version=None,
                   dynamic_research_version=None):
        with self.database.connect() as connection, connection.cursor() as cursor:
            self.execution._active(cursor, claims)
        selected = sum(value is not None for value in (
            source_catalog_version, source_plan_version, dynamic_research_version))
        if selected > 1:
            raise ExecutionRuntimeError('invalid_request', 422)
        if dynamic_research_version is not None:
            if (type(dynamic_research_version) is not int
                    or dynamic_research_version != 1 or self.dynamic is None):
                raise ExecutionRuntimeError('invalid_request', 422)
            return self.dynamic.capability()
        if source_plan_version is not None:
            if type(source_plan_version) is not int or source_plan_version != 1:
                raise ExecutionRuntimeError('invalid_request', 422)
            return {'contractVersion': 3, 'sourceScope': 'V2EX_INDEX_PLAN',
                'sourceLabel': 'V2EX多板块 · 有界来源计划', 'sourceIds': list(SOURCE_IDS),
                'maxPlannedSources': 3, 'maxFreshEffectsPerAdvance': 1, 'settlementState': 'PENDING'}
        if source_catalog_version is not None:
            if type(source_catalog_version) is not int or source_catalog_version != 1:
                raise ExecutionRuntimeError('invalid_request', 422)
            return {'contractVersion': 2, 'sourceScope': 'V2EX_SELECTED_INDEX',
                'sourceLabel': 'V2EX定向板块 · 单源索引研究', 'sourceIds': list(SOURCE_IDS),
                'maxFreshEffectsPerAdvance': 1, 'settlementState': 'PENDING'}
        return {"contractVersion": 1, "sourceScope": SOURCE_SCOPE,
            "sourceLabel": SOURCE_LABEL, "maxFreshEffectsPerAdvance": 1,
            "settlementState": "PENDING"}

    def _identity(self, cursor, claims, task_id, run_id=None, *, lock=False):
        tenant = self.execution._active(cursor, claims)
        cursor.execute("SELECT t.status,r.run_id,r.status FROM pilot_collection_tasks t "
            "JOIN pilot_collection_runs r ON r.tenant_id=t.tenant_id AND r.owner_user_id=t.owner_user_id "
            "AND r.task_id=t.task_id JOIN pilot_research_reservations q ON q.tenant_id=t.tenant_id "
            "AND q.owner_user_id=t.owner_user_id AND q.task_id=t.task_id AND q.run_id=r.run_id "
            "WHERE t.tenant_id=%s AND t.owner_user_id=%s AND t.task_id=%s" +
            (" FOR UPDATE OF t,r" if lock else ""), (tenant, claims.user_id, task_id))
        row = cursor.fetchone()
        if row is None:
            raise ExecutionRuntimeError("task_not_found", 404)
        if run_id is not None and row[1] != run_id:
            raise ExecutionRuntimeError("request_conflict", 409)
        self.execution._active(cursor, claims)
        return tenant, row

    def _coordinator(self, cursor, tenant, user, task_id, *, lock=False):
        cursor.execute("SELECT run_id,generation,current_owner,lease_expires_at,phase,stop_code "
            "FROM pilot_research_runtime WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s"+
            (" FOR UPDATE" if lock else ""), (tenant, user, task_id))
        return cursor.fetchone()

    def _usage(self, cursor, tenant, user, task_id, run_id, as_of):
        cursor.execute("SELECT resource,status,count(*),count(*) FILTER (WHERE status='ISSUED' AND deadline_at<=%s) "
            "FROM pilot_research_resource_events "
            "WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s AND run_id=%s "
            "GROUP BY resource,status", (as_of, tenant, user, task_id, run_id))
        counters = {resource: {key: 0 for key in ("issued","pending","succeeded","failed","unknown")}
            for resource in ("SOURCE_READ", "MODEL_CALL")}
        names = {"ISSUED": "pending", "SUCCEEDED": "succeeded", "FAILED": "failed", "UNKNOWN": "unknown"}
        overdue = 0
        for resource, status, count, expired in cursor.fetchall():
            counters[resource][names[status]] = count
            counters[resource]["issued"] += count
            overdue += expired
        return {"sourceReads": counters["SOURCE_READ"], "modelCalls": counters["MODEL_CALL"],
            "actualSoubei": None, "settlementState": "PENDING"}, overdue

    def _dto(self, claims, task_id, *, state=None, ignore_active_lease=False):
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                cursor.execute("SELECT clock_timestamp()")
                now = cursor.fetchone()[0]
                tenant, task = self._identity(cursor, claims, task_id)
                run_id = task[1]
                coordinator = self._coordinator(cursor, tenant, claims.user_id, task_id)
                usage, overdue = self._usage(cursor, tenant, claims.user_id, task_id, run_id, now)
        if state is None:
            state = self.orchestrator.inspect(claims, task_id=task_id, run_id=run_id)
        event, receipt = state["source_event"], state["receipt"]
        accepted = receipt.get("accepted_count") if type(receipt) is dict else None
        progress = state.get('source_progress')
        if progress is not None:
            accepted = sum(p['acceptedOriginals'] for p in progress) if all(p['phase'] == 'SUCCEEDED' for p in progress) else None
        analyzed = sum(item.get("kind") == "assessment" for item in state["reviews"])
        candidate_ids = list(dict.fromkeys(item["candidate_id"] for item in state["items"]))[:100]
        task_status, run_status = task[0], task[2]
        canceled = task_status in ("CANCELLING", "CANCELED") or run_status in ("CANCELLING", "CANCELED")
        pending = usage["sourceReads"]["pending"] + usage["modelCalls"]["pending"] > 0
        unknown = usage["sourceReads"]["unknown"] + usage["modelCalls"]["unknown"] > 0
        failed = usage["sourceReads"]["failed"] + usage["modelCalls"]["failed"] > 0
        review_unknown = any(item.get("kind") == "pending" for item in state["reviews"])
        review_failed = any(item.get("kind") == "failure" for item in state["reviews"])
        complete = task_status == "SUCCEEDED" and run_status == "SUCCEEDED"
        leased = bool(coordinator and coordinator[2] is not None
            and coordinator[3] is not None and coordinator[3] > now)
        durable_stopped = bool(coordinator and coordinator[4] == "STOPPED")
        broker_unknown = durable_stopped and coordinator[5] in (
            "broker_stop_unknown", "broker_stream_unknown"
        )
        phase = "STOPPED" if broker_unknown else "CANCELED" if canceled else "COMPLETED" if complete else \
            "STOPPED" if unknown or failed or review_unknown or review_failed or durable_stopped else \
            "RUNNING" if event is not None or leased or (progress and any(p['phase'] != 'NOT_STARTED' for p in progress)) else "QUEUED"
        stop = coordinator[5] if broker_unknown else "effect_unknown" if unknown else "effect_failed" if failed else \
            "assessment_unknown" if review_unknown else "assessment_failed" if review_failed else \
            coordinator[5] if durable_stopped else None
        blocked = (canceled or complete or unknown or failed or pending or review_unknown or review_failed or durable_stopped
            or (leased and not ignore_active_lease))
        terminal = task_status in ("SUCCEEDED", "CANCELED") and run_status in ("SUCCEEDED", "CANCELED")
        closeout = "UNCERTAIN" if broker_unknown or unknown or overdue or review_unknown else \
            "DRAINING" if pending or leased else "RECORDED" if terminal else "OPEN"
        usage["resourceCloseout"] = {"state": closeout, "overduePermits": overdue,
            "asOf": now.isoformat()}
        source = source_from_snapshot(state['strategy_snapshot'])
        result = {"contractVersion": source.version, "taskId": task_id, "runId": run_id,
            "phase": phase, "sourceScope": source.scope, "sourceLabel": source.label,
            "acceptedOriginals": accepted, "analyzedOriginals": analyzed,
            "skippedOriginals": state["skipped"], "candidateIds": candidate_ids,
            "canAdvance": not blocked, "stopCode": stop, "newActionsBlocked": blocked,
            "effectsPending": pending, "usage": usage}
        if progress is not None:
            result.update(contractVersion=3, sourceScope='V2EX_INDEX_PLAN',
                sourceLabel='V2EX多板块 · 有界来源计划', sourceProgress=progress)
        return result

    def status(self, claims, task_id):
        task_id = canonical_uuid(task_id)
        if self._dynamic_task(claims, task_id):
            if self.dynamic is None:
                raise ExecutionRuntimeError("capability_unavailable", 501)
            return self.dynamic.status(claims, task_id)
        return self._dto(claims, task_id)

    def reads(self, claims, task_id, *, run_id, after=0, limit=5):
        if self.dynamic is None:
            raise ExecutionRuntimeError("capability_unavailable", 501)
        return self.dynamic.reads(claims, canonical_uuid(task_id), run_id=canonical_uuid(run_id),
                                  after=after, limit=limit)

    def advance(self, claims, task_id, run_id):
        task_id, run_id = canonical_uuid(task_id), canonical_uuid(run_id)
        if self._dynamic_task(claims, task_id):
            if self.dynamic is None:
                raise ExecutionRuntimeError("capability_unavailable", 501)
            return self.dynamic.advance(claims, task_id, run_id)
        already_running = False
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant, task = self._identity(cursor, claims, task_id, run_id, lock=True)
            now = self.execution._now(cursor)
            row = self._coordinator(cursor, tenant, claims.user_id, task_id, lock=True)
            if row is None:
                cursor.execute("INSERT INTO pilot_research_runtime(tenant_id,owner_user_id,task_id,run_id) "
                    "VALUES (%s,%s,%s,%s)", (tenant, claims.user_id, task_id, run_id))
                row = self._coordinator(cursor, tenant, claims.user_id, task_id, lock=True)
            if row[0] != run_id:
                raise ExecutionRuntimeError("request_conflict", 409)
            if row[2] is not None and row[3] > now:
                already_running = True
            elif row[4] == "STOPPED" or row[4] == "COMPLETED" and task[0] == "SUCCEEDED":
                already_running = True
            elif task[0] in ("CANCELLING", "CANCELED") or task[2] in ("CANCELLING", "CANCELED"):
                already_running = True
            else:
                generation = row[1] + 1
                cursor.execute("UPDATE pilot_research_runtime SET generation=%s,current_owner=%s,"
                    "lease_expires_at=%s,phase='RUNNING',stop_code=NULL,updated_at=clock_timestamp() "
                    "WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s",
                    (generation, self.owner, now + timedelta(seconds=self.lease_seconds),
                     tenant, claims.user_id, task_id))
        if already_running:
            return self._dto(claims, task_id)
        try:
            before = self._dto(claims, task_id, ignore_active_lease=True)
            if before["newActionsBlocked"]:
                state = None
            else:
                state = self.orchestrator.advance_one(claims, task_id=task_id, run_id=run_id,
                    _admission=self._admission(claims, task_id, run_id, generation))
            result = self._dto(claims, task_id, state=state)
        except Exception as error:
            stop_code = error.code if isinstance(error, (ExecutionRuntimeError,
                CandidateIngestionError)) else "advance_failed"
            self._release(claims, task_id, generation, "STOPPED", stop_code)
            if isinstance(error, CandidateIngestionError):
                raise ExecutionRuntimeError(error.code, error.status) from None
            raise
        sequence_complete = (result["acceptedOriginals"] is not None
            and result["analyzedOriginals"] + result["skippedOriginals"] == result["acceptedOriginals"]
            and not result["effectsPending"] and result["phase"] not in ("STOPPED", "CANCELED"))
        if sequence_complete:
            self._complete(claims, task_id, run_id, generation)
        else:
            self._release(claims, task_id, generation, result["phase"], result["stopCode"])
        return self._dto(claims, task_id)

    def _dynamic_task(self, claims, task_id):
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self.execution._active(cursor, claims)
            cursor.execute("SELECT configuration_snapshot FROM pilot_collection_tasks "
                "WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s",
                (tenant, claims.user_id, task_id))
            row = cursor.fetchone()
            if row is None:
                raise ExecutionRuntimeError("task_not_found", 404)
            configuration = row[0].get("configuration", {})
            result = (type(configuration) is dict
                and configuration.get("publicSource") == "public-web-agent-v1")
            self.execution._active(cursor, claims)
            return result

    def _admission(self, claims, task_id, run_id, generation):
        def admit(cursor, tenant, event):
            # Runs while the resource admission already holds task authority locks.
            row = self._coordinator(cursor, tenant, claims.user_id, task_id, lock=True)
            cursor.execute("SELECT clock_timestamp()")
            now = cursor.fetchone()[0]
            if (event["task_id"] != task_id or event["run_id"] != run_id or row is None
                    or row[0] != run_id or row[1] != generation or row[2] != self.owner
                    or row[3] is None or row[3] <= now or row[4] != "RUNNING"):
                raise ExecutionRuntimeError("lease_conflict", 409)
            return True
        return admit

    def _release(self, claims, task_id, generation, phase, stop_code):
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self.execution._active(cursor, claims)
            cursor.execute("UPDATE pilot_research_runtime SET current_owner=NULL,lease_expires_at=NULL,"
                "phase=%s,stop_code=%s,updated_at=clock_timestamp() WHERE tenant_id=%s AND owner_user_id=%s "
                "AND task_id=%s AND generation=%s AND current_owner=%s",
                (phase, stop_code, tenant, claims.user_id, task_id, generation, self.owner))
            if cursor.rowcount != 1:
                raise ExecutionRuntimeError("lease_conflict", 409)

    def _complete(self, claims, task_id, run_id, generation, *, _admission=None):
        if _admission is not None and not callable(_admission):
            raise ExecutionRuntimeError("invalid_request", 422)
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant, task = self._identity(cursor, claims, task_id, run_id, lock=True)
            row = self._coordinator(cursor, tenant, claims.user_id, task_id, lock=True)
            if (row is None or row[0] != run_id or row[1] != generation
                    or row[2] != self.owner or row[4] != "RUNNING"
                    or row[3] is None or row[3] <= self.execution._now(cursor)):
                raise ExecutionRuntimeError("lease_conflict", 409)
            if task[0] in ("CANCELLING", "CANCELED") or task[2] in ("CANCELLING", "CANCELED"):
                raise ExecutionRuntimeError("task_cancelled", 409)
            if _admission is not None and _admission(cursor, tenant) is not True:
                raise ExecutionRuntimeError("request_conflict", 409)
            for table in ("pilot_collection_platform_runs", "pilot_collection_runs", "pilot_collection_tasks"):
                cursor.execute(f"UPDATE {table} SET status='SUCCEEDED' WHERE tenant_id=%s "
                    "AND owner_user_id=%s AND task_id=%s AND status IN ('PENDING','RUNNING')",
                    (tenant, claims.user_id, task_id))
            # One terminal transaction: a failed commit cannot strand a COMPLETED
            # coordinator with PENDING tasks. A new owner can finalize stored effects.
            cursor.execute("UPDATE pilot_research_runtime SET current_owner=NULL,lease_expires_at=NULL,"
                "phase='COMPLETED',stop_code=NULL,updated_at=clock_timestamp() "
                "WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s AND generation=%s",
                (tenant, claims.user_id, task_id, generation))
