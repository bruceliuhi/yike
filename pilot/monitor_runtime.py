"""Durable online monitor pulses and at-most-once execution reservations."""
from __future__ import annotations

from datetime import timedelta
from functools import wraps
import hashlib
import json
from uuid import uuid4

import psycopg
from pydantic import ValidationError

from pilot.execution_contract import ExecutionOperation, ExecutionRuntimeError
from pilot.monitor_calendar import next_occurrence
from pilot.monitor_runtime_contract import MonitorPulseRequest


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _safe(method):
    @wraps(method)
    def wrapped(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except psycopg.Error:
            raise ExecutionRuntimeError("monitor_runtime_unavailable", 503) from None
    return wrapped


class MonitorRuntime:
    def __init__(self, database, execution_runtime):
        self.database = database
        self.execution_runtime = execution_runtime

    @_safe
    def support(self, claims):
        from pilot.foreground_collection import (three_platform_monitor_policy, four_platform_monitor_policy,
                                                four_platform_public_monitor_policy, four_platform_public_sampling_monitor_policy)
        runtime = self.execution_runtime
        with self.database.connect() as connection, connection.cursor() as cursor:
            runtime._active(cursor, claims)
            result = dict(
                schema_version='monitor-runtime-support-v1',
                mode={three_platform_monitor_policy:'three-platform-monitor-v1',
                      four_platform_monitor_policy:'four-platform-monitor-v1',
                      four_platform_public_monitor_policy:'four-platform-monitor-v1',
                      four_platform_public_sampling_monitor_policy:'four-platform-monitor-v1'}.get(runtime.capability_check))
            if runtime.capability_check is four_platform_public_sampling_monitor_policy:
                result['public_source'] = 'v2ex-latest-v1'
            return self._authorized(cursor, claims, result)

    def _authorized(self, cursor, claims, response):
        self.execution_runtime._active(cursor, claims)
        return response

    @staticmethod
    def _request(body):
        try:
            return MonitorPulseRequest.model_validate(body)
        except (ValidationError, ValueError, TypeError, UnicodeError, RecursionError):
            raise ExecutionRuntimeError("invalid_request", 422) from None

    @staticmethod
    def _owner_lock(cursor, tenant, user):
        key = (tenant + "\0" + user).encode()
        cursor.execute("SELECT pg_advisory_xact_lock(12601,%s)",
                       (int.from_bytes(hashlib.sha256(key).digest()[:4], "big", signed=True),))

    @staticmethod
    def _targets(request):
        return [target.model_dump(mode="json") for target in request.targets]

    @staticmethod
    def _occurrence(row):
        if row is None:
            return None
        keys = ("occurrence_id", "scheduled_at", "expires_at", "start_request", "task_id")
        value = dict(zip(keys, row))
        return dict(id=value["occurrence_id"], scheduled_at=value["scheduled_at"].isoformat(),
                    expires_at=value["expires_at"].isoformat(), start_request=value["start_request"],
                    task_id=value["task_id"])

    @staticmethod
    def _response(request, revision, state, now, due, occurrence=None):
        return dict(schema_version="monitor-runtime-v1", plan_id=request.plan_id,
                    plan_revision=revision, state=state, server_time=now.isoformat(),
                    next_due_at=due.isoformat() if due else None,
                    occurrence=MonitorRuntime._occurrence(occurrence))

    def _pending(self, cursor, tenant, user, plan_id):
        cursor.execute("SELECT o.occurrence_id,o.scheduled_at,o.expires_at,o.start_request,o.task_id,o.status,b.monitor_session_id,o.plan_revision "
                       "FROM pilot_monitor_occurrences o JOIN pilot_monitor_bindings b USING(tenant_id,owner_user_id,plan_id,plan_revision) "
                       "WHERE o.tenant_id=%s AND o.owner_user_id=%s AND o.plan_id=%s AND o.status IN ('RESERVED','STARTED') "
                       "FOR UPDATE OF o", (tenant, user, plan_id))
        return cursor.fetchone()

    def _settle_pending(self, cursor, request, tenant, user, now, revision, due):
        row = self._pending(cursor, tenant, user, request.plan_id)
        if row is None:
            return None, False
        occurrence, scheduled, expires, start, task_id, status, session_id, occurrence_revision = row
        public = (occurrence, scheduled, expires, start, task_id)
        if status == "RESERVED":
            if now >= expires:
                cursor.execute("UPDATE pilot_monitor_occurrences SET status='EXPIRED' "
                               "WHERE tenant_id=%s AND owner_user_id=%s AND occurrence_id=%s",
                               (tenant, user, occurrence))
                return None, True
            current_process = occurrence_revision == revision and session_id == request.monitor_session_id
            state = "READY" if current_process else "RECOVERY_REQUIRED"
            return self._response(request, revision, state, now, due, public), True
        cursor.execute("SELECT status,deadline_at FROM pilot_collection_tasks "
                       "WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s", (tenant, user, task_id))
        task = cursor.fetchone()
        if task and task[0] not in ("SUCCEEDED", "CANCELED") and now < task[1]:
            current_process = occurrence_revision == revision and session_id == request.monitor_session_id
            state = "RUNNING" if current_process else "RECOVERY_REQUIRED"
            return self._response(request, revision, state, now, due, public), True
        cursor.execute("UPDATE pilot_monitor_occurrences SET status='CLOSED' "
                       "WHERE tenant_id=%s AND owner_user_id=%s AND occurrence_id=%s",
                       (tenant, user, occurrence))
        return None, True

    @_safe
    def pulse(self, claims, body):
        request = self._request(body)
        runtime = self.execution_runtime
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = runtime._active(cursor, claims)
            self._owner_lock(cursor, tenant, claims.user_id)
            runtime._active(cursor, claims)
            cursor.execute("SELECT profile_version_id,strategy_version_id,configuration_sha256,schedule,state,revision,next_due_at "
                           "FROM pilot_monitor_plans WHERE tenant_id=%s AND owner_user_id=%s AND plan_id=%s",
                           (tenant, claims.user_id, request.plan_id))
            provisional = cursor.fetchone()
            if provisional is None:
                raise ExecutionRuntimeError("plan_not_found", 404)
            profile, strategy_id, digest, schedule, state, revision, due = provisional
            targets = self._targets(request)
            cursor.execute("SELECT device_id,credential_version,targets FROM pilot_monitor_bindings "
                           "WHERE tenant_id=%s AND owner_user_id=%s AND plan_id=%s AND plan_revision=%s",
                           (tenant, claims.user_id, request.plan_id, revision))
            existing_binding = cursor.fetchone()
            if existing_binding and existing_binding != (request.device_id, request.credential_version, targets):
                raise ExecutionRuntimeError("monitor_binding_conflict")
            runtime._key(cursor, claims, tenant, request.device_id, request.credential_version)
            for target in sorted(request.targets, key=lambda item: (item.platform, item.connection_id or "")):
                runtime._connection(cursor, claims, request.device_id, target)
            snapshot = runtime._strategy(cursor, claims, tenant, profile, strategy_id, digest, request.targets)
            from pilot.foreground_collection import (four_platform_monitor_policy,
                                                    four_platform_public_monitor_policy,
                                                    four_platform_public_sampling_monitor_policy)
            platforms = ("XIAOHONGSHU", "DOUYIN", "BILIBILI")
            if runtime.capability_check in (four_platform_monitor_policy, four_platform_public_monitor_policy,
                                            four_platform_public_sampling_monitor_policy):
                platforms += ("ZHIHU",)
            if runtime.capability_check is four_platform_public_sampling_monitor_policy:
                platforms += ("PUBLIC_WEB",)
            if (snapshot["configuration"].get("mode") != "monitor"
                    or snapshot["configuration"].get("schedule", {}).get("policyVersion") != 1
                    or any(target.platform not in platforms for target in request.targets)):
                raise ExecutionRuntimeError("capability_unavailable", 501)
            cursor.execute("SELECT profile_version_id,strategy_version_id,configuration_sha256,schedule,state,revision,next_due_at "
                           "FROM pilot_monitor_plans WHERE tenant_id=%s AND owner_user_id=%s AND plan_id=%s FOR UPDATE",
                           (tenant, claims.user_id, request.plan_id))
            current = cursor.fetchone()
            if current != provisional:
                raise ExecutionRuntimeError("monitor_binding_conflict")
            if state != "ACTIVE":
                raise ExecutionRuntimeError("monitor_plan_inactive")
            now = runtime._now(cursor)
            cursor.execute("SELECT device_id,credential_version,targets,monitor_session_id,last_seen_at "
                           "FROM pilot_monitor_bindings WHERE tenant_id=%s AND owner_user_id=%s AND plan_id=%s AND plan_revision=%s FOR UPDATE",
                           (tenant, claims.user_id, request.plan_id, revision))
            binding = cursor.fetchone()
            if binding and (binding[0], binding[1], binding[2]) != (request.device_id, request.credential_version, targets):
                raise ExecutionRuntimeError("monitor_binding_conflict")
            pending, had_pending = self._settle_pending(
                cursor, request, tenant, claims.user_id, now, revision, due)
            if had_pending and binding and binding[3] == request.monitor_session_id:
                cursor.execute("UPDATE pilot_monitor_bindings SET last_seen_at=%s "
                               "WHERE tenant_id=%s AND owner_user_id=%s AND plan_id=%s AND plan_revision=%s",
                               (now, tenant, claims.user_id, request.plan_id, revision))
                binding = (*binding[:4], now)
            if had_pending and due is not None and due <= now:
                due = next_occurrence(schedule, after=now)
                cursor.execute("UPDATE pilot_monitor_plans SET next_due_at=%s,updated_at=%s "
                               "WHERE tenant_id=%s AND owner_user_id=%s AND plan_id=%s",
                               (due, now, tenant, claims.user_id, request.plan_id))
                if pending is not None:
                    pending["next_due_at"] = due.isoformat()
            if pending is not None:
                return self._authorized(cursor, claims, pending)
            offline = binding is None or binding[3] != request.monitor_session_id or now - binding[4] > timedelta(seconds=90)
            if binding is None:
                cursor.execute("INSERT INTO pilot_monitor_bindings(tenant_id,owner_user_id,plan_id,plan_revision,device_id,credential_version,targets,monitor_session_id,last_seen_at) "
                               "VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)",
                               (tenant, claims.user_id, request.plan_id, revision, request.device_id,
                                request.credential_version, _json(targets), request.monitor_session_id, now))
            else:
                cursor.execute("UPDATE pilot_monitor_bindings SET monitor_session_id=%s,last_seen_at=%s "
                               "WHERE tenant_id=%s AND owner_user_id=%s AND plan_id=%s AND plan_revision=%s",
                               (request.monitor_session_id, now, tenant, claims.user_id, request.plan_id, revision))
            if due is None:
                raise ExecutionRuntimeError("monitor_plan_inactive")
            if offline:
                if due <= now:
                    due = next_occurrence(schedule, after=now)
                    cursor.execute("UPDATE pilot_monitor_plans SET next_due_at=%s,updated_at=%s "
                                   "WHERE tenant_id=%s AND owner_user_id=%s AND plan_id=%s",
                                   (due, now, tenant, claims.user_id, request.plan_id))
                    return self._authorized(cursor, claims, self._response(request, revision, "SKIPPED_OFFLINE", now, due))
                return self._authorized(cursor, claims, self._response(request, revision, "WAITING", now, due))
            last_seen = binding[4]
            if due > now:
                return self._authorized(cursor, claims, self._response(request, revision, "WAITING", now, due))
            if not request.can_start:
                due = next_occurrence(schedule, after=now)
                cursor.execute("UPDATE pilot_monitor_plans SET next_due_at=%s,updated_at=%s WHERE tenant_id=%s AND owner_user_id=%s AND plan_id=%s",
                               (due, now, tenant, claims.user_id, request.plan_id))
                return self._authorized(cursor, claims, self._response(request, revision, "SKIPPED_BUSY", now, due))
            if due <= last_seen:
                due = next_occurrence(schedule, after=now)
                cursor.execute("UPDATE pilot_monitor_plans SET next_due_at=%s,updated_at=%s WHERE tenant_id=%s AND owner_user_id=%s AND plan_id=%s",
                               (due, now, tenant, claims.user_id, request.plan_id))
                return self._authorized(cursor, claims, self._response(request, revision, "SKIPPED_MISSED", now, due))
            occurrence_id, request_id = str(uuid4()), str(uuid4())
            start = dict(schema_version="execution-runtime-v1", request_id=request_id, operation="START",
                         device_id=request.device_id, credential_version=request.credential_version,
                         profile_version_id=profile, strategy_version_id=strategy_id,
                         configuration_sha256=digest, targets=targets)
            start = ExecutionOperation.model_validate(start).model_dump(mode="json")
            expires = now + timedelta(seconds=90)
            scheduled = due
            due = next_occurrence(schedule, after=now)
            cursor.execute("INSERT INTO pilot_monitor_occurrences(tenant_id,owner_user_id,occurrence_id,plan_id,plan_revision,scheduled_at,expires_at,device_id,request_id,start_request,status) "
                           "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'RESERVED')",
                           (tenant, claims.user_id, occurrence_id, request.plan_id, revision, scheduled, expires,
                            request.device_id, request_id, _json(start)))
            cursor.execute("UPDATE pilot_monitor_plans SET next_due_at=%s,updated_at=%s WHERE tenant_id=%s AND owner_user_id=%s AND plan_id=%s",
                           (due, now, tenant, claims.user_id, request.plan_id))
            return self._authorized(cursor, claims, self._response(request, revision, "READY", now, due,
                                  (occurrence_id, scheduled, expires, start, None)))

    def guard_start(self, cursor, claims, tenant, request, snapshot):
        cursor.execute("SELECT occurrence_id,plan_id,plan_revision,expires_at,device_id,start_request,status "
                       "FROM pilot_monitor_occurrences WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s FOR UPDATE",
                       (tenant, claims.user_id, request.request_id))
        occurrence = cursor.fetchone()
        if occurrence is None:
            raise ExecutionRuntimeError("monitor_occurrence_required")
        occurrence_id, plan_id, revision, expires, device_id, original, status = occurrence
        if status != "RESERVED" or self.execution_runtime._now(cursor) >= expires:
            raise ExecutionRuntimeError("monitor_occurrence_expired")
        if device_id != request.device_id or _json(original) != _json(request.model_dump(mode="json")):
            raise ExecutionRuntimeError("monitor_binding_conflict")
        try:
            cursor.execute("SELECT state,revision,profile_version_id,strategy_version_id,configuration_sha256 "
                           "FROM pilot_monitor_plans WHERE tenant_id=%s AND owner_user_id=%s AND plan_id=%s FOR SHARE NOWAIT",
                           (tenant, claims.user_id, plan_id))
        except psycopg.errors.LockNotAvailable:
            raise ExecutionRuntimeError("monitor_plan_busy") from None
        plan = cursor.fetchone()
        if not plan or plan[0] != "ACTIVE" or plan[1] != revision:
            raise ExecutionRuntimeError("monitor_plan_inactive")
        if (plan[2], plan[3], plan[4]) != (snapshot["profile_version_id"], snapshot["strategy_version_id"], request.configuration_sha256):
            raise ExecutionRuntimeError("strategy_conflict")
        cursor.execute("SELECT device_id,credential_version,targets FROM pilot_monitor_bindings "
                       "WHERE tenant_id=%s AND owner_user_id=%s AND plan_id=%s AND plan_revision=%s",
                       (tenant, claims.user_id, plan_id, revision))
        binding = cursor.fetchone()
        if not binding or (binding[0], binding[1], binding[2]) != (
                request.device_id, request.credential_version,
                [target.model_dump(mode="json") for target in request.targets]):
            raise ExecutionRuntimeError("monitor_binding_conflict")
        return occurrence_id

    @staticmethod
    def link_start(cursor, claims, tenant, occurrence_id, task_id, run_id):
        cursor.execute("UPDATE pilot_monitor_occurrences SET status='STARTED',task_id=%s,run_id=%s "
                       "WHERE tenant_id=%s AND owner_user_id=%s AND occurrence_id=%s AND status='RESERVED'",
                       (task_id, run_id, tenant, claims.user_id, occurrence_id))
        if cursor.rowcount != 1:
            raise ExecutionRuntimeError("monitor_occurrence_expired")

    @staticmethod
    def guard_task(cursor, claims, tenant, task):
        try:
            cursor.execute("SELECT o.plan_id,o.plan_revision,p.state,p.revision,b.device_id,b.credential_version,b.targets,o.start_request "
                           "FROM pilot_monitor_occurrences o JOIN pilot_monitor_plans p USING(tenant_id,owner_user_id,plan_id) "
                           "JOIN pilot_monitor_bindings b USING(tenant_id,owner_user_id,plan_id,plan_revision) "
                           "WHERE o.tenant_id=%s AND o.owner_user_id=%s AND o.task_id=%s AND o.status='STARTED' "
                           "FOR SHARE OF p NOWAIT", (tenant, claims.user_id, task["task_id"]))
        except psycopg.errors.LockNotAvailable:
            raise ExecutionRuntimeError("monitor_plan_busy") from None
        row = cursor.fetchone()
        if row is None:
            raise ExecutionRuntimeError("monitor_occurrence_required")
        if row[2] != "ACTIVE" or row[1] != row[3]:
            raise ExecutionRuntimeError("monitor_plan_inactive")
        original = row[7]
        if (row[4] != task["device_id"] or row[5] != original["credential_version"]
                or row[6] != original["targets"] or original["profile_version_id"] != task["profile_version_id"]
                or original["strategy_version_id"] != task["strategy_version_id"]
                or original["configuration_sha256"] != task["configuration_sha256"]):
            raise ExecutionRuntimeError("monitor_binding_conflict")


__all__ = ["MonitorRuntime"]
