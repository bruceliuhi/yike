"""Recoverable, owner-scoped device registration receipts."""
from __future__ import annotations

from functools import wraps
import hashlib
import re
from uuid import uuid4

from pilot.auth import InvalidPilotToken, TokenClaims
from pilot.device_keys import DeviceKeyError, uuid_string
from pilot.sessions import PilotSessionRegistry


_REVOCATION_KEY = re.compile(r"[0-9a-f]{64}\Z")
_RECEIPT_FIELDS = ("request_id", "device_id", "device_label", "registered_at")


def _row(cursor):
    row = cursor.fetchone()
    return dict(zip((column.name for column in cursor.description), row)) if row else None


def _receipt(row):
    return {
        "request_id": row["request_id"],
        "device_id": row["device_id"],
        "device_label": row["device_label"],
        "registered_at": row["registered_at"].isoformat(),
        "state": "SUCCEEDED",
    }


def _fixed_storage_error(code):
    def decorate(method):
        @wraps(method)
        def wrapped(*args, **kwargs):
            try:
                return method(*args, **kwargs)
            except DeviceKeyError:
                raise
            except (InvalidPilotToken, PermissionError):
                raise DeviceKeyError("invalid_session", 401) from None
            except Exception:
                # Commit acknowledgement can fail after PostgreSQL committed.
                # Never expose SQL, connection details, or caller content.
                raise DeviceKeyError(code, 503) from None

        return wrapped

    return decorate


class DeviceRegistrationStore:
    def __init__(self, database):
        self.database = database
        self.sessions = PilotSessionRegistry(database)

    @staticmethod
    def _validate_claims(claims):
        if (
            not isinstance(claims, TokenClaims)
            or type(claims.user_id) is not str
            or not 1 <= len(claims.user_id) <= 256
            or claims.user_id != claims.user_id.strip()
            or any(ord(character) < 32 for character in claims.user_id)
            or type(claims.expires_at) is not int
            or not 0 < claims.expires_at <= 253_402_300_799
            or type(claims.revocation_key) is not str
            or not _REVOCATION_KEY.fullmatch(claims.revocation_key)
        ):
            raise InvalidPilotToken("invalid pilot token")

    def _active(self, cursor, claims):
        self._validate_claims(claims)
        return self.sessions.require_active(cursor, claims)

    @staticmethod
    def _payload(payload):
        if type(payload) is not dict or set(payload) != {"request_id", "device_label"}:
            raise DeviceKeyError("invalid_request", 422)
        request_id = uuid_string(payload["request_id"])
        label = payload["device_label"]
        if type(label) is not str or "\x00" in label:
            raise DeviceKeyError("invalid_request", 422)
        try:
            label.encode("utf-8", errors="strict")
        except UnicodeError:
            raise DeviceKeyError("invalid_request", 422) from None
        label = label.strip()
        if not 1 <= len(label) <= 128:
            raise DeviceKeyError("invalid_request", 422)
        return request_id, label

    @staticmethod
    def _request_lock_key(tenant_id, owner_user_id, request_id):
        value = (tenant_id + "\0" + owner_user_id + "\0" + request_id).encode("utf-8")
        return int.from_bytes(hashlib.sha256(value).digest()[:4], "big", signed=True)

    @_fixed_storage_error("registration_outcome_unknown")
    def register(self, claims: TokenClaims, payload: dict) -> dict:
        request_id, device_label = self._payload(payload)
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                tenant_id = self._active(cursor, claims)
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(11601,%s)",
                    (self._request_lock_key(tenant_id, claims.user_id, request_id),),
                )
                tenant_id = self._active(cursor, claims)
                cursor.execute(
                    "SELECT request_id,device_id,device_label,registered_at "
                    "FROM pilot_device_registrations "
                    "WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s",
                    (tenant_id, claims.user_id, request_id),
                )
                existing = _row(cursor)
                self._active(cursor, claims)
                if existing is not None:
                    if existing["device_label"] != device_label:
                        raise DeviceKeyError("request_conflict", 409)
                    return _receipt(existing)

                device_id = str(uuid4())
                cursor.execute(
                    "INSERT INTO pilot_devices(device_id,tenant_id,device_label,owner_user_id) "
                    "VALUES (%s,%s,%s,%s)",
                    (device_id, tenant_id, device_label, claims.user_id),
                )
                cursor.execute(
                    "INSERT INTO pilot_device_registrations("
                    "tenant_id,owner_user_id,request_id,device_id,device_label) "
                    "VALUES (%s,%s,%s,%s,%s) "
                    "RETURNING request_id,device_id,device_label,registered_at",
                    (tenant_id, claims.user_id, request_id, device_id, device_label),
                )
                registered = _row(cursor)
                self._active(cursor, claims)
                return _receipt(registered)

    @_fixed_storage_error("device_registration_unavailable")
    def get_receipt(self, claims: TokenClaims, request_id: str) -> dict:
        request_id = uuid_string(request_id)
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                tenant_id = self._active(cursor, claims)
                cursor.execute(
                    "SELECT request_id,device_id,device_label,registered_at "
                    "FROM pilot_device_registrations "
                    "WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s",
                    (tenant_id, claims.user_id, request_id),
                )
                row = _row(cursor)
                self._active(cursor, claims)
                if row is None:
                    raise DeviceKeyError("request_not_found", 404)
                return _receipt(row)

    @_fixed_storage_error("device_registration_unavailable")
    def get_identity(self, claims: TokenClaims, device_id: str) -> dict:
        device_id = uuid_string(device_id)
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                tenant_id = self._active(cursor, claims)
                cursor.execute(
                    "SELECT d.device_id,d.status AS device_status,"
                    "c.credential_version,c.public_key "
                    "FROM pilot_devices d LEFT JOIN pilot_device_credentials c "
                    "ON c.tenant_id=d.tenant_id AND c.owner_user_id=d.owner_user_id "
                    "AND c.device_id=d.device_id "
                    "WHERE d.tenant_id=%s AND d.owner_user_id=%s AND d.device_id=%s",
                    (tenant_id, claims.user_id, device_id),
                )
                row = _row(cursor)
                self._active(cursor, claims)
                if row is None:
                    raise DeviceKeyError("device_unavailable", 404)
                return {
                    "device_id": row["device_id"],
                    "device_status": row["device_status"],
                    "credential_version": row["credential_version"] or 0,
                    "public_key": row["public_key"],
                }
