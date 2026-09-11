"""Persisted, lease-fenced coordinator for bounded research advancement."""
from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from pilot.candidate_ingestion import CandidateIngestionError
from pilot.execution_contract import ExecutionRuntimeError, canonical_uuid


SOURCE_SCOPE = "V2EX_LATEST_INDEX"
SOURCE_LABEL = "V2EX最新主题 · 公开单源研究"


class ResearchRuntimeService:
    def __init__(self, orchestrator, *, lease_seconds=120):
        self.orchestrator = orchestrator
        self.database = orchestrator.sources.resources.runtime.database
        self.execution = orchestrator.sources.resources.runtime
        self.owner = str(uuid4())
        self.lease_seconds = lease_seconds

    def capability(self, claims):
        with self.database.connect() as connection, connection.cursor() as cursor:
            self.execution._active(cursor, claims)
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

    def _usage(self, cursor, tenant, user, task_id, run_id):
        cursor.execute("SELECT resource,status,count(*) FROM pilot_research_resource_events "
            "WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s AND run_id=%s "
            "GROUP BY resource,status", (tenant, user, task_id, run_id))
        counters = {resource: {key: 0 for key in ("issued","pending","succeeded","failed","unknown")}
            for resource in ("SOURCE_READ", "MODEL_CALL")}
        names = {"ISSUED": "pending", "SUCCEEDED": "succeeded", "FAILED": "failed", "UNKNOWN": "unknown"}
        for resource, status, count in cursor.fetchall():
            counters[resource][names[status]] = count
            counters[resource]["issued"] += count
        return {"sourceReads": counters["SOURCE_READ"], "modelCalls": counters["MODEL_CALL"],
            "actualSoubei": None, "settlementState": "PENDING"}

    def _dto(self, claims, task_id, *, state=None, ignore_active_lease=False):
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant, task = self._identity(cursor, claims, task_id)
            run_id = task[1]
            coordinator = self._coordinator(cursor, tenant, claims.user_id, task_id)
            usage = self._usage(cursor, tenant, claims.user_id, task_id, run_id)
            cursor.execute("SELECT clock_timestamp()")
            now = cursor.fetchone()[0]
        if state is None:
            state = self.orchestrator.inspect(claims, task_id=task_id, run_id=run_id)
        event, receipt = state["source_event"], state["receipt"]
        accepted = receipt.get("accepted_count") if type(receipt) is dict else None
        analyzed = sum(item.get("kind") == "assessment" for item in state["reviews"])
        candidate_ids = list(dict.fromkeys(item["candidate_id"] for item in state["items"]))[:100]
        task_status, run_status = task[0], task[2]
        canceled = task_status in ("CANCELLING", "CANCELED") or run_status in ("CANCELLING", "CANCELED")
        pending = usage["sourceReads"]["pending"] + usage["modelCalls"]["pending"] > 0
        unknown = usage["sourceReads"]["unknown"] + usage["modelCalls"]["unknown"] > 0
        failed = usage["sourceReads"]["failed"] + usage["modelCalls"]["failed"] > 0
        complete = accepted is not None and analyzed + state["skipped"] == accepted and not pending
        leased = bool(coordinator and coordinator[2] is not None
            and coordinator[3] is not None and coordinator[3] > now)
        durable_stopped = bool(coordinator and coordinator[4] == "STOPPED")
        phase = "CANCELED" if canceled else "COMPLETED" if complete else \
            "STOPPED" if unknown or failed or durable_stopped else \
            "RUNNING" if event is not None or leased else "QUEUED"
        stop = "effect_unknown" if unknown else "effect_failed" if failed else \
            coordinator[5] if durable_stopped else None
        blocked = (canceled or complete or unknown or failed or pending or durable_stopped
            or (leased and not ignore_active_lease))
        return {"contractVersion": 1, "taskId": task_id, "runId": run_id,
            "phase": phase, "sourceScope": SOURCE_SCOPE, "sourceLabel": SOURCE_LABEL,
            "acceptedOriginals": accepted, "analyzedOriginals": analyzed,
            "skippedOriginals": state["skipped"], "candidateIds": candidate_ids,
            "canAdvance": not blocked, "stopCode": stop, "newActionsBlocked": blocked,
            "effectsPending": pending, "usage": usage}

    def status(self, claims, task_id):
        return self._dto(claims, canonical_uuid(task_id))

    def advance(self, claims, task_id, run_id):
        task_id, run_id = canonical_uuid(task_id), canonical_uuid(run_id)
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
            elif row[4] in ("STOPPED", "COMPLETED"):
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
                state = self.orchestrator.advance_one(claims, task_id=task_id, run_id=run_id)
            result = self._dto(claims, task_id, state=state)
        except Exception as error:
            stop_code = error.code if isinstance(error, (ExecutionRuntimeError,
                CandidateIngestionError)) else "advance_failed"
            self._release(claims, task_id, generation, "STOPPED", stop_code)
            if isinstance(error, CandidateIngestionError):
                raise ExecutionRuntimeError(error.code, error.status) from None
            raise
        self._release(claims, task_id, generation, result["phase"], result["stopCode"])
        if result["phase"] == "COMPLETED":
            self._complete(claims, task_id, run_id, generation)
        return self._dto(claims, task_id)

    def _release(self, claims, task_id, generation, phase, stop_code):
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self.execution._active(cursor, claims)
            cursor.execute("UPDATE pilot_research_runtime SET current_owner=NULL,lease_expires_at=NULL,"
                "phase=%s,stop_code=%s,updated_at=clock_timestamp() WHERE tenant_id=%s AND owner_user_id=%s "
                "AND task_id=%s AND generation=%s AND current_owner=%s",
                (phase, stop_code, tenant, claims.user_id, task_id, generation, self.owner))
            if cursor.rowcount != 1:
                raise ExecutionRuntimeError("lease_conflict", 409)

    def _complete(self, claims, task_id, run_id, generation):
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant, task = self._identity(cursor, claims, task_id, run_id, lock=True)
            row = self._coordinator(cursor, tenant, claims.user_id, task_id, lock=True)
            if row is None or row[1] != generation or row[4] != "COMPLETED":
                raise ExecutionRuntimeError("lease_conflict", 409)
            if task[0] in ("CANCELLING", "CANCELED") or task[2] in ("CANCELLING", "CANCELED"):
                raise ExecutionRuntimeError("task_cancelled", 409)
            for table in ("pilot_collection_platform_runs", "pilot_collection_runs", "pilot_collection_tasks"):
                cursor.execute(f"UPDATE {table} SET status='SUCCEEDED' WHERE tenant_id=%s "
                    "AND owner_user_id=%s AND task_id=%s AND status IN ('PENDING','RUNNING')",
                    (tenant, claims.user_id, task_id))
