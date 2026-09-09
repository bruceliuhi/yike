"""Versioned connection receipts and a caller-owned transaction fence.

Neither registration nor a historical receipt proves platform readiness.
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pilot.auth import InvalidPilotToken, TokenClaims
from pilot.db import PilotDatabase
from pilot.identity import SUPPORTED_PLATFORMS, IdentityValidationError, validate_connection_input
from pilot.sessions import PilotSessionRegistry

MAX_VERSION = 2147483647


class ConnectionOperationError(Exception):
    def __init__(self, code: str, status: int = 409):
        super().__init__(code)
        self.code, self.status = code, status


def canonical_uuid(value: str) -> str:
    if type(value) is not str or len(value) != 36:
        raise ConnectionOperationError("invalid_request", 422)
    try:
        valid = str(UUID(value)) == value
    except ValueError:
        valid = False
    if not valid:
        raise ConnectionOperationError("invalid_request", 422)
    return value


class ConnectionOperation(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True,
                              frozen=True, revalidate_instances="always")
    request_id: str
    action: Literal["REGISTER", "DISCONNECT"]
    device_id: str
    connection_id: str | None
    expected_connection_version: int = Field(ge=0, le=MAX_VERSION)
    platform: str | None
    account_public_id: str | None
    session_ref: str | None = Field(repr=False)

    @field_validator("request_id", "device_id", "connection_id")
    @classmethod
    def valid_uuid(cls, value):
        return canonical_uuid(value) if value is not None else value

    @model_validator(mode="after")
    def valid_action(self):
        if self.action == "DISCONNECT":
            if self.connection_id is None or self.expected_connection_version == 0 or any(
                value is not None for value in (self.platform, self.account_public_id, self.session_ref)
            ):
                raise ConnectionOperationError("invalid_request", 422)
        else:
            if self.connection_id is not None or self.platform not in SUPPORTED_PLATFORMS:
                raise ConnectionOperationError("invalid_request", 422)
            try:
                values = validate_connection_input(self.platform, self.device_id,
                                                   self.account_public_id, self.session_ref)
            except IdentityValidationError:
                raise ConnectionOperationError("invalid_request", 422) from None
            # Reject normalization, control characters and secret-like public IDs.
            for name in ("platform", "account_public_id", "session_ref"):
                raw = getattr(self, name)
                if raw != values[name] or any(unicodedata.category(c).startswith("C") for c in raw):
                    raise ConnectionOperationError("invalid_request", 422)
            if any(marker in self.account_public_id.lower() for marker in
                   ("cookie=", "token=", "password=", "secret=", "authorization:")):
                raise ConnectionOperationError("invalid_request", 422)
        return self


class ConnectionOperationStore:
    def __init__(self, database: PilotDatabase):
        self.database = database
        self.sessions = PilotSessionRegistry(database)

    def _active(self, cursor, claims):
        try:
            return self.sessions.require_active(cursor, claims)
        except (InvalidPilotToken, PermissionError):
            raise ConnectionOperationError("invalid_session", 401) from None

    @staticmethod
    def _receipt(cursor, tenant, user, request_id):
        cursor.execute(
            "SELECT request_id,requested_device_id AS device_id,action,state,connection_id,connection_version,"
            "connection_status,error_code,request_sha256 FROM pilot_connection_operations "
            "WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s",
            (tenant, user, request_id))
        row = cursor.fetchone()
        return dict(zip((col.name for col in cursor.description), row)) if row else None

    @staticmethod
    def _safe(receipt):
        return {key: value for key, value in receipt.items() if key != "request_sha256"}

    def get_receipt(self, claims: TokenClaims, request_id: str) -> dict:
        canonical_uuid(request_id)
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self._active(cursor, claims)
            receipt = self._receipt(cursor, tenant, claims.user_id, request_id)
            self._active(cursor, claims)
            if receipt is None:
                raise ConnectionOperationError("request_not_found", 404)
            return self._safe(receipt)

    def apply(self, claims: TokenClaims, request: ConnectionOperation) -> dict:
        request = ConnectionOperation.model_validate(request)
        fingerprint = hashlib.sha256(json.dumps(request.model_dump(exclude={"request_id"}),
            ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self._active(cursor, claims)
            raw = ("yike-connection-operation-v1\0" + tenant + "\0" + claims.user_id + "\0" + request.request_id).encode()
            lock_id = int.from_bytes(hashlib.sha256(raw).digest()[:4], "big", signed=True)
            # The two-int PostgreSQL namespace is disjoint from session bigint locks.
            cursor.execute("SELECT pg_advisory_xact_lock(10701,%s)", (lock_id,))
            self._active(cursor, claims)
            previous = self._receipt(cursor, tenant, claims.user_id, request.request_id)
            if previous:
                self._active(cursor, claims)
                if previous["request_sha256"] != fingerprint:
                    raise ConnectionOperationError("request_conflict")
                return self._safe(previous)
            cursor.execute("SELECT status FROM pilot_devices WHERE tenant_id=%s AND owner_user_id=%s "
                           "AND device_id=%s FOR UPDATE", (tenant, claims.user_id, request.device_id))
            device = cursor.fetchone()
            self._active(cursor, claims)
            result = dict(request_id=request.request_id, device_id=request.device_id,
                          action=request.action, state="REJECTED", connection_id=None,
                          connection_version=None, connection_status=None, error_code=None)
            if device is None or device[0] != "ACTIVE":
                result["error_code"] = "device_unavailable"
            else:
                self._mutate(cursor, tenant, claims, request, result)
            self._active(cursor, claims)
            cursor.execute(
                "INSERT INTO pilot_connection_operations(tenant_id,owner_user_id,request_id,requested_device_id,"
                "action,state,connection_id,connection_version,connection_status,error_code,request_sha256,authorized_device_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (tenant, claims.user_id, result["request_id"], result["device_id"], result["action"],
                 result["state"], result["connection_id"], result["connection_version"],
                 result["connection_status"], result["error_code"], fingerprint,
                 request.device_id if device else None))
            self._active(cursor, claims)
            return result

    def _mutate(self, cursor, tenant, claims, request, result):
        if request.action == "REGISTER":
            cursor.execute("SELECT connection_id,connection_version,status FROM pilot_platform_connections "
                "WHERE tenant_id=%s AND device_id=%s AND platform=%s AND account_public_id=%s FOR UPDATE",
                (tenant, request.device_id, request.platform, request.account_public_id))
        else:
            cursor.execute("SELECT connection_id,connection_version,status FROM pilot_platform_connections "
                "WHERE tenant_id=%s AND device_id=%s AND connection_id=%s FOR UPDATE",
                (tenant, request.device_id, request.connection_id))
        row = cursor.fetchone()
        self._active(cursor, claims)
        if row:
            result.update(connection_id=row[0], connection_version=row[1], connection_status=row[2])
        if request.action == "DISCONNECT" and row is None:
            result["error_code"] = "connection_unavailable"
        elif request.expected_connection_version != (row[1] if row else 0):
            result["error_code"] = "connection_version_conflict"
        elif row and row[1] == MAX_VERSION and (request.action == "REGISTER" or row[2] != "DISCONNECTED"):
            result["error_code"] = "connection_version_exhausted"
        else:
            if request.action == "REGISTER":
                if row:
                    cursor.execute("UPDATE pilot_platform_connections SET session_ref=%s,status='UNVERIFIED',"
                        "disconnected_at=NULL,connection_version=connection_version+1 "
                        "WHERE tenant_id=%s AND connection_id=%s RETURNING connection_id,connection_version,status",
                        (request.session_ref, tenant, row[0]))
                else:
                    cursor.execute("INSERT INTO pilot_platform_connections(connection_id,tenant_id,device_id,"
                        "platform,account_public_id,session_ref) VALUES (%s,%s,%s,%s,%s,%s) "
                        "RETURNING connection_id,connection_version,status",
                        (str(uuid4()), tenant, request.device_id, request.platform, request.account_public_id, request.session_ref))
            else:
                cursor.execute("UPDATE pilot_platform_connections SET status='DISCONNECTED',"
                    "disconnected_at=COALESCE(disconnected_at,CURRENT_TIMESTAMP) "
                    "WHERE tenant_id=%s AND connection_id=%s RETURNING connection_id,connection_version,status",
                    (tenant, row[0]))
            updated = cursor.fetchone()
            result.update(state="SUCCEEDED", connection_id=updated[0], connection_version=updated[1], connection_status=updated[2])

    def lock_current(self, cursor, claims: TokenClaims, *, device_id: str,
                     connection_id: str, connection_version: int, platform: str) -> dict:
        canonical_uuid(device_id)
        canonical_uuid(connection_id)
        if (type(connection_version) is not int or not 1 <= connection_version <= MAX_VERSION
                or type(platform) is not str or platform not in SUPPORTED_PLATFORMS):
            raise ConnectionOperationError("invalid_request", 422)
        tenant = self._active(cursor, claims)
        cursor.execute("SELECT status FROM pilot_devices WHERE tenant_id=%s AND owner_user_id=%s AND device_id=%s FOR UPDATE",
                       (tenant, claims.user_id, device_id))
        device = cursor.fetchone()
        self._active(cursor, claims)
        if not device or device[0] != "ACTIVE":
            raise ConnectionOperationError("device_unavailable")
        cursor.execute("SELECT connection_id,connection_version,platform,account_public_id,status "
                       "FROM pilot_platform_connections WHERE tenant_id=%s AND device_id=%s AND connection_id=%s AND platform=%s FOR UPDATE",
                       (tenant, device_id, connection_id, platform))
        row = cursor.fetchone()
        self._active(cursor, claims)
        if not row:
            raise ConnectionOperationError("connection_unavailable")
        if row[1] != connection_version:
            raise ConnectionOperationError("connection_version_conflict")
        if row[4] != "CONNECTED":
            raise ConnectionOperationError("connection_unavailable")
        return dict(zip(("connection_id", "connection_version", "platform", "account_public_id"), row[:4]))
