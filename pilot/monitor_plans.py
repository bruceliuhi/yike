"""Durable bounded monitor plan intent; deliberately no execution polling."""
from __future__ import annotations

from functools import wraps
import hashlib
import json
import re
import unicodedata
from uuid import UUID

import psycopg
from pydantic import BaseModel, ValidationError

from pilot.auth import InvalidPilotToken, TokenClaims
from pilot.execution_contract import ExecutionRuntimeError
from pilot.execution_runtime import ConfirmedExecutionStrategy
from pilot.monitor_contract import CreateMonitorPlanRequest, MonitorPlanError, SetMonitorPlanStateRequest
from pilot.sessions import PilotSessionRegistry


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _request(model, value):
    try:
        return model.model_validate(value)
    except (ValidationError, ValueError, TypeError, UnicodeError, RecursionError):
        raise MonitorPlanError("invalid_request") from None


def _safe(method):
    @wraps(method)
    def wrapped(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except psycopg.Error:
            pass
        raise MonitorPlanError("monitor_store_unavailable") from None
    return wrapped


class MonitorPlanStore:
    def __init__(self, database, strategy_resolver=None):
        self.database = database
        self.strategy_resolver = strategy_resolver
        self.sessions = PilotSessionRegistry(database)

    @staticmethod
    def _claims(claims):
        if (not isinstance(claims, TokenClaims) or type(claims.user_id) is not str
                or not 1 <= len(claims.user_id) <= 256 or claims.user_id.strip() != claims.user_id
                or any(unicodedata.category(ch)[0] == "C" for ch in claims.user_id)
                or type(claims.revocation_key) is not str or not re.fullmatch("[0-9a-f]{64}", claims.revocation_key)
                or type(claims.expires_at) is not int or not 0 < claims.expires_at <= 253402300799):
            raise MonitorPlanError("invalid_session")

    def _active(self, cursor, claims):
        self._claims(claims)
        try:
            return self.sessions.require_active(cursor, claims)
        except (InvalidPilotToken, PermissionError):
            raise MonitorPlanError("invalid_session") from None

    def _operation(self, cursor, claims, request, operation):
        tenant = self._active(cursor, claims)
        key = (tenant + "\0" + claims.user_id).encode()
        cursor.execute("SELECT pg_advisory_xact_lock(12601,%s)",
                       (int.from_bytes(hashlib.sha256(key).digest()[:4], "big", signed=True),))
        self._active(cursor, claims)
        fingerprint = _digest(request.model_dump(mode="json"))
        cursor.execute("SELECT operation,request_sha256,receipt FROM pilot_monitor_plan_operations "
                       "WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s",
                       (tenant, claims.user_id, request.request_id))
        row = cursor.fetchone()
        self._active(cursor, claims)
        if row and (row[0] != operation or row[1] != fingerprint):
            raise MonitorPlanError("request_conflict")
        return tenant, fingerprint, row[2] if row else None

    def _resolve(self, cursor, claims, request):
        if self.strategy_resolver is None:
            raise MonitorPlanError("strategy_conflict")
        try:
            strategy = self.strategy_resolver(cursor, claims, request.profile_version_id,
                                              request.strategy_version_id)
        except ExecutionRuntimeError as error:
            if error.code == "invalid_session":
                raise MonitorPlanError("invalid_session") from None
            if error.status == 503:
                raise MonitorPlanError("monitor_store_unavailable") from None
            raise MonitorPlanError("strategy_conflict") from None
        if not isinstance(strategy, ConfirmedExecutionStrategy):
            raise MonitorPlanError("strategy_conflict")
        configuration = strategy.configuration
        try:
            schedule = configuration["schedule"]
            if (configuration.get("mode") != "monitor" or type(schedule) is not dict
                    or schedule.get("policyVersion") != 1 or type(schedule.get("policyVersion")) is not int
                    or strategy.profile_version_id != request.profile_version_id
                    or strategy.strategy_version_id != request.strategy_version_id):
                raise ValueError
            # Ensure the saved digest actually binds the supplied snapshot.
            if not re.fullmatch("[0-9a-f]{64}", strategy.configuration_sha256):
                raise ValueError
            return strategy, json.loads(_json(schedule))
        except (KeyError, ValueError, TypeError, UnicodeError, RecursionError):
            raise MonitorPlanError("unsupported_schedule") from None

    @staticmethod
    def _view(row):
        keys = ("plan_id", "profile_version_id", "strategy_version_id", "configuration_sha256",
                "schedule", "state", "revision", "next_due_at")
        value = dict(zip(keys, row))
        value["next_due_at"] = value["next_due_at"].isoformat() if value["next_due_at"] else None
        value["execution_status"] = "NOT_CONNECTED"
        return value

    def _read_plan(self, cursor, tenant, user, plan_id, lock=False):
        cursor.execute("SELECT plan_id,profile_version_id,strategy_version_id,configuration_sha256,schedule,state,revision,next_due_at "
                       "FROM pilot_monitor_plans WHERE tenant_id=%s AND owner_user_id=%s AND plan_id=%s" +
                       (" FOR UPDATE" if lock else ""), (tenant, user, plan_id))
        return cursor.fetchone()

    def _record(self, cursor, claims, tenant, request, operation, fingerprint, plan, recorded):
        receipt = {"schema_version": "monitor-plans-v1", "request_id": request.request_id,
                   "operation": operation, "plan": self._view(plan), "recorded_at": recorded.isoformat()}
        self._active(cursor, claims)
        cursor.execute("INSERT INTO pilot_monitor_plan_operations(tenant_id,owner_user_id,request_id,operation,request_sha256,plan_id,receipt,created_at) "
                       "VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s)",
                       (tenant, claims.user_id, request.request_id, operation, fingerprint,
                        plan[0], _json(receipt), recorded))
        self._active(cursor, claims)
        return receipt

    @_safe
    def create(self, claims, body):
        request = _request(CreateMonitorPlanRequest, body)
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant, fingerprint, previous = self._operation(cursor, claims, request, "CREATE")
            if previous is not None:
                return previous
            strategy, schedule = self._resolve(cursor, claims, request)
            cursor.execute("SELECT count(*) FROM pilot_monitor_plans WHERE tenant_id=%s AND owner_user_id=%s",
                           (tenant, claims.user_id))
            if cursor.fetchone()[0] >= 20:
                raise MonitorPlanError("plan_limit")
            cursor.execute("SELECT 1 FROM pilot_monitor_plans WHERE tenant_id=%s AND owner_user_id=%s AND strategy_version_id=%s",
                           (tenant, claims.user_id, request.strategy_version_id))
            if cursor.fetchone():
                raise MonitorPlanError("plan_conflict")
            cursor.execute("SELECT clock_timestamp()")
            now = cursor.fetchone()[0]
            try:
                from pilot.monitor_calendar import next_occurrence
                due = next_occurrence(schedule, after=now)
            except (ValueError, TypeError, KeyError, OverflowError):
                raise MonitorPlanError("unsupported_schedule") from None
            cursor.execute("INSERT INTO pilot_monitor_plans(tenant_id,owner_user_id,plan_id,profile_version_id,strategy_version_id,configuration_sha256,schedule,state,revision,next_due_at,created_at,updated_at) "
                           "VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,'ACTIVE',1,%s,%s,%s)",
                           (tenant, claims.user_id, request.request_id, request.profile_version_id,
                            request.strategy_version_id, strategy.configuration_sha256, _json(schedule), due, now, now))
            plan = self._read_plan(cursor, tenant, claims.user_id, request.request_id)
            return self._record(cursor, claims, tenant, request, "CREATE", fingerprint, plan, now)

    @_safe
    def set_state(self, claims, body):
        request = _request(SetMonitorPlanStateRequest, body)
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant, fingerprint, previous = self._operation(cursor, claims, request, "SET_STATE")
            if previous is not None:
                return previous
            plan = self._read_plan(cursor, tenant, claims.user_id, request.plan_id, lock=True)
            self._active(cursor, claims)
            if plan is None:
                raise MonitorPlanError("plan_not_found")
            if plan[6] != request.expected_revision:
                raise MonitorPlanError("plan_conflict")
            due = None
            if request.state == "ACTIVE":
                proxy = CreateMonitorPlanRequest(schema_version="monitor-plans-v1", request_id=request.request_id,
                    profile_version_id=plan[1], strategy_version_id=plan[2], human_confirmed=True)
                _, schedule = self._resolve(cursor, claims, proxy)
                cursor.execute("SELECT clock_timestamp()")
                now = cursor.fetchone()[0]
                try:
                    from pilot.monitor_calendar import next_occurrence
                    due = next_occurrence(schedule, after=now)
                except (ValueError, TypeError, KeyError, OverflowError):
                    raise MonitorPlanError("unsupported_schedule") from None
            else:
                cursor.execute("SELECT clock_timestamp()")
                now = cursor.fetchone()[0]
            cursor.execute("UPDATE pilot_monitor_plans SET state=%s,revision=revision+1,next_due_at=%s,updated_at=%s "
                           "WHERE tenant_id=%s AND owner_user_id=%s AND plan_id=%s AND revision=%s",
                           (request.state, due, now, tenant, claims.user_id, request.plan_id, request.expected_revision))
            if cursor.rowcount != 1:
                raise MonitorPlanError("plan_conflict")
            plan = self._read_plan(cursor, tenant, claims.user_id, request.plan_id)
            return self._record(cursor, claims, tenant, request, "SET_STATE", fingerprint, plan, now)

    @_safe
    def list(self, claims):
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self._active(cursor, claims)
            cursor.execute("SELECT plan_id,profile_version_id,strategy_version_id,configuration_sha256,schedule,state,revision,next_due_at "
                           "FROM pilot_monitor_plans WHERE tenant_id=%s AND owner_user_id=%s ORDER BY created_at,plan_id LIMIT 20",
                           (tenant, claims.user_id))
            plans = [self._view(row) for row in cursor.fetchall()]
            self._active(cursor, claims)
            return {"schema_version": "monitor-plans-v1", "plans": plans, "execution_status": "NOT_CONNECTED"}

    @_safe
    def get_receipt(self, claims, request_id):
        try:
            if type(request_id) is not str or str(UUID(request_id)) != request_id:
                raise ValueError
        except (ValueError, TypeError):
            raise MonitorPlanError("invalid_request") from None
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self._active(cursor, claims)
            cursor.execute("SELECT receipt FROM pilot_monitor_plan_operations WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s",
                           (tenant, claims.user_id, request_id))
            row = cursor.fetchone()
            self._active(cursor, claims)
            if row is None:
                raise MonitorPlanError("request_not_found")
            return row[0]


__all__ = ["MonitorPlanStore"]
