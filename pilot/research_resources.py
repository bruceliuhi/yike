"""Durable internal research resource permits; no HTTP, pricing, or callbacks."""
from __future__ import annotations

import hashlib
import json
import re
from uuid import uuid4

import psycopg

from pilot.execution_contract import ExecutionRuntimeError, canonical_uuid
from pilot.research_quote import ResearchQuoteRule


_SHA256 = re.compile(r"[0-9a-f]{64}")
_RESOURCES = {"SOURCE_READ": "source_limit", "MODEL_CALL": "model_call_limit"}
_FINAL = {"SUCCEEDED", "FAILED", "UNKNOWN"}
_FIELDS = ("reservation_id", "task_id", "run_id", "action_id", "permit_id",
    "research_generation", "resource", "input_sha256", "status", "output_sha256",
    "issued_at", "deadline_at", "finished_at")


def _sha256(value):
    if type(value) is not str or not _SHA256.fullmatch(value):
        raise ExecutionRuntimeError("invalid_request", 422)
    return value


def _event(row):
    value = dict(zip(_FIELDS, row))
    for key in ("issued_at", "deadline_at", "finished_at"):
        if value[key] is not None:
            value[key] = value[key].isoformat()
    return {"schema_version": "research-resource-v1", **value}


class ResearchResourceStore:
    def __init__(self, runtime, *, rule, research_capability):
        self.runtime = runtime
        self.rule = rule
        self.research_capability = research_capability

    @staticmethod
    def _select(cursor, tenant, user, task_id, run_id, action_id, *, lock=False):
        cursor.execute("SELECT "+",".join(_FIELDS)+" FROM pilot_research_resource_events "
            "WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s AND run_id=%s AND action_id=%s"+
            (" FOR UPDATE" if lock else ""), (tenant, user, task_id, run_id, action_id))
        return cursor.fetchone()

    @staticmethod
    def _targets(runtime, cursor, tenant, user, task_id, run_id):
        cursor.execute("SELECT platform,access_mode,connection_id,connection_version,credential_version "
            "FROM pilot_collection_platform_runs WHERE tenant_id=%s AND owner_user_id=%s "
            "AND task_id=%s AND run_id=%s ORDER BY platform,platform_run_id",
            (tenant, user, task_id, run_id))
        rows = cursor.fetchall()
        return rows, tuple(runtime._target(dict(platform=row[0], access_mode=row[1],
            connection_id=row[2], connection_version=row[3])) for row in rows)

    def begin(self, claims, *, task_id, run_id, action_id, resource, input_sha256,
              _admission=None):
        task_id, run_id, action_id = map(canonical_uuid, (task_id, run_id, action_id))
        if type(resource) is not str or resource not in _RESOURCES:
            raise ExecutionRuntimeError("invalid_request", 422)
        input_sha256 = _sha256(input_sha256)
        try:
            with self.runtime.database.connect() as connection, connection.cursor() as cursor:
                tenant = self.runtime._active(cursor, claims)
                lock = int.from_bytes(hashlib.sha256((tenant+'\0'+claims.user_id+'\0'+task_id+'\0'+
                    run_id+'\0'+action_id).encode()).digest()[:4], 'big', signed=True)
                cursor.execute("SELECT pg_advisory_xact_lock(13401,%s)", (lock,))
                self.runtime._active(cursor, claims)
                previous = self._select(cursor, tenant, claims.user_id, task_id, run_id, action_id)
                if previous is not None:
                    event = _event(previous)
                    if event["resource"] != resource or event["input_sha256"] != input_sha256:
                        raise ExecutionRuntimeError("request_conflict", 409)
                    self.runtime._active(cursor, claims)
                    return {"created": False, "event": event}

                cursor.execute("SELECT device_id,profile_version_id,strategy_version_id,configuration_sha256,"
                    "configuration_snapshot FROM pilot_collection_tasks WHERE tenant_id=%s AND owner_user_id=%s "
                    "AND task_id=%s", (tenant, claims.user_id, task_id))
                identity = cursor.fetchone()
                rows, targets = self._targets(self.runtime, cursor, tenant, claims.user_id, task_id, run_id)
                if identity is None or not rows:
                    raise ExecutionRuntimeError("task_unavailable", 409)
                self.runtime._key(cursor, claims, tenant, identity[0], rows[0][4])
                for target in targets:
                    self.runtime._connection(cursor, claims, identity[0], target)
                snapshot = self.runtime._strategy(cursor, claims, tenant, identity[1], identity[2], identity[3], targets)
                if json.dumps(snapshot, sort_keys=True, separators=(",", ":")) != json.dumps(
                        identity[4], sort_keys=True, separators=(",", ":")):
                    raise ExecutionRuntimeError("request_conflict", 409)
                try:
                    capable = self.research_capability(json.loads(json.dumps(snapshot)))
                except Exception:
                    capable = False
                if capable is not True:
                    raise ExecutionRuntimeError("capability_unavailable", 501)

                task, run, _ = self.runtime._locks(cursor, claims, tenant, task_id)
                if run is None or run["run_id"] != run_id or task["status"] not in ("PENDING", "RUNNING") \
                        or run["status"] not in ("PENDING", "RUNNING"):
                    raise ExecutionRuntimeError("task_unavailable", 409)
                cursor.execute("SELECT reservation_id,rule_version,rule_sha256,source_limit,minute_limit,"
                    "model_call_limit FROM pilot_research_reservations WHERE tenant_id=%s AND owner_user_id=%s "
                    "AND task_id=%s AND run_id=%s FOR UPDATE", (tenant, claims.user_id, task_id, run_id))
                reservation = cursor.fetchone()
                if reservation is None or not isinstance(self.rule, ResearchQuoteRule) \
                        or reservation[1] != self.rule.ruleVersion or reservation[2] != self.rule.digest():
                    raise ExecutionRuntimeError("resource_unavailable", 503)
                cursor.execute("SELECT clock_timestamp(),LEAST(%s,%s + %s * interval '1 minute')",
                    (task["deadline_at"], task["created_at"], reservation[4]))
                now, deadline = cursor.fetchone()
                if now >= deadline:
                    raise ExecutionRuntimeError("task_unavailable", 409)
                if _admission is not None:
                    if not callable(_admission):
                        raise ExecutionRuntimeError("invalid_request", 422)
                    try:
                        admitted = _admission(cursor, tenant, dict(task_id=task_id, run_id=run_id,
                            action_id=action_id, resource=resource, input_sha256=input_sha256,
                            reservation_id=str(reservation[0]), deadline=deadline,
                            strategy_snapshot=json.loads(json.dumps(snapshot))))
                    except ExecutionRuntimeError:
                        raise
                    except Exception:
                        raise ExecutionRuntimeError("resource_unavailable", 503) from None
                    if admitted is not True:
                        raise ExecutionRuntimeError("request_conflict", 409)
                cursor.execute("SELECT count(*) FROM pilot_research_resource_events WHERE tenant_id=%s "
                    "AND owner_user_id=%s AND reservation_id=%s AND resource=%s",
                    (tenant, claims.user_id, reservation[0], resource))
                limit = reservation[3] if resource == "SOURCE_READ" else reservation[5]
                if cursor.fetchone()[0] >= limit:
                    raise ExecutionRuntimeError("resource_limit_exceeded", 409)
                permit_id = str(uuid4())
                cursor.execute("INSERT INTO pilot_research_resource_events(tenant_id,owner_user_id,reservation_id,"
                    "task_id,run_id,action_id,permit_id,resource,input_sha256,issued_at,deadline_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING "+",".join(_FIELDS),
                    (tenant, claims.user_id, reservation[0], task_id, run_id, action_id, permit_id,
                     resource, input_sha256, now, deadline))
                event = _event(cursor.fetchone())
                self.runtime._active(cursor, claims)
                return {"created": True, "event": event}
        except ExecutionRuntimeError:
            raise
        except psycopg.Error:
            raise ExecutionRuntimeError("resource_unavailable", 503) from None

    def finish(self, claims, *, task_id, run_id, action_id, permit_id, status, output_sha256=None):
        task_id, run_id, action_id, permit_id = map(canonical_uuid,
            (task_id, run_id, action_id, permit_id))
        if type(status) is not str or status not in _FINAL:
            raise ExecutionRuntimeError("invalid_request", 422)
        if status == "SUCCEEDED":
            output_sha256 = _sha256(output_sha256)
        elif output_sha256 is not None:
            raise ExecutionRuntimeError("invalid_request", 422)
        try:
            with self.runtime.database.connect() as connection, connection.cursor() as cursor:
                tenant = self.runtime._active(cursor, claims)
                row = self._select(cursor, tenant, claims.user_id, task_id, run_id, action_id, lock=True)
                if row is None or row[4] != permit_id:
                    raise ExecutionRuntimeError("request_not_found", 404)
                event = _event(row)
                if event["status"] != "ISSUED":
                    if event["status"] != status or event["output_sha256"] != output_sha256:
                        raise ExecutionRuntimeError("request_conflict", 409)
                    return event
                cursor.execute("UPDATE pilot_research_resource_events SET status=%s,output_sha256=%s,"
                    "finished_at=clock_timestamp() WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s "
                    "AND run_id=%s AND action_id=%s RETURNING "+",".join(_FIELDS),
                    (status, output_sha256, tenant, claims.user_id, task_id, run_id, action_id))
                event = _event(cursor.fetchone())
                self.runtime._active(cursor, claims)
                return event
        except ExecutionRuntimeError:
            raise
        except psycopg.Error:
            raise ExecutionRuntimeError("resource_unavailable", 503) from None

    def get(self, claims, *, task_id, run_id, action_id):
        task_id, run_id, action_id = map(canonical_uuid, (task_id, run_id, action_id))
        try:
            with self.runtime.database.connect() as connection, connection.cursor() as cursor:
                tenant = self.runtime._active(cursor, claims)
                row = self._select(cursor, tenant, claims.user_id, task_id, run_id, action_id)
                self.runtime._active(cursor, claims)
                if row is None:
                    raise ExecutionRuntimeError("request_not_found", 404)
                return _event(row)
        except ExecutionRuntimeError:
            raise
        except psycopg.Error:
            raise ExecutionRuntimeError("resource_unavailable", 503) from None
