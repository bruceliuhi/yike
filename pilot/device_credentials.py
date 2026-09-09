"""Persisted Ed25519 possession receipts, not execution authorization."""
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import secrets
from uuid import uuid4

from pilot.auth import TokenClaims
from pilot.db import PilotDatabase
from pilot.device_keys import ChallengeRequest, CompletionProof, DeviceKeyError, uuid_string, verify_signature
from pilot.sessions import PilotSessionRegistry


def _row(cursor):
    row = cursor.fetchone()
    return dict(zip((column.name for column in cursor.description), row)) if row else None


def _receipt(row):
    return {"request_id": row["request_id"], "device_id": row["device_id"],
            "operation": row["operation"], "state": row["state"],
            "credential_version": row["result_version"]}


def _challenge(row):
    return {"request_id": row["request_id"], "challenge_id": row["challenge_id"],
            "signing_payload": row["signing_payload"],
            "expires_at": int(row["expires_at"].timestamp())}


class DeviceCredentialStore:
    def __init__(self, database: PilotDatabase):
        self.database = database
        self.sessions = PilotSessionRegistry(database)

    def _active(self, cursor, claims):
        try:
            return self.sessions.require_active(cursor, claims)
        except PermissionError:
            raise DeviceKeyError("invalid_session", 401) from None

    @staticmethod
    def _device(cursor, tenant, user, device_id):
        cursor.execute("SELECT status FROM pilot_devices WHERE tenant_id=%s AND owner_user_id=%s "
                       "AND device_id=%s FOR UPDATE", (tenant, user, device_id))
        row = cursor.fetchone()
        if row is None:
            raise DeviceKeyError("device_unavailable", 404)
        return row[0]

    @staticmethod
    def _credential(cursor, tenant, device_id):
        cursor.execute("SELECT public_key,credential_version FROM pilot_device_credentials "
                       "WHERE tenant_id=%s AND device_id=%s FOR UPDATE", (tenant, device_id))
        return _row(cursor)

    @staticmethod
    def _validate_version(operation, version, target, credential):
        current = credential["credential_version"] if credential else 0
        if version != current or (operation == "BIND") != (credential is None):
            raise DeviceKeyError("credential_conflict", 409)
        if operation == "ROTATE" and target == credential["public_key"]:
            raise DeviceKeyError("credential_conflict", 409)

    def create_challenge(self, claims: TokenClaims, device_id: str, request: ChallengeRequest) -> dict:
        uuid_string(device_id)
        fingerprint = hashlib.sha256(json.dumps(
            request.model_dump() | {"device_id": device_id}, sort_keys=True, separators=(",", ":")
        ).encode()).hexdigest()
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                tenant = self._active(cursor, claims)
                status = self._device(cursor, tenant, claims.user_id, device_id)
                self._active(cursor, claims)  # Database time after any device wait.
                cursor.execute("SELECT * FROM pilot_device_key_requests WHERE tenant_id=%s AND owner_user_id=%s "
                               "AND request_id=%s FOR UPDATE", (tenant, claims.user_id, request.request_id))
                existing = _row(cursor)
                self._active(cursor, claims)
                if existing:
                    if existing["request_sha256"] != fingerprint:
                        raise DeviceKeyError("request_conflict", 409)
                    return _challenge(existing)
                if status != "ACTIVE":
                    raise DeviceKeyError("device_unavailable", 404)
                credential = self._credential(cursor, tenant, device_id)
                self._active(cursor, claims)
                self._validate_version(request.operation, request.expected_credential_version,
                                       request.public_key, credential)
                cursor.execute("SELECT count(*) FROM pilot_device_key_requests WHERE tenant_id=%s AND device_id=%s "
                               "AND state='PENDING' AND expires_at>clock_timestamp()", (tenant, device_id))
                if cursor.fetchone()[0] >= 5:
                    raise DeviceKeyError("challenge_limit", 429)
                cursor.execute("SELECT floor(extract(epoch FROM clock_timestamp()))::bigint + 120")
                expires = cursor.fetchone()[0]
                challenge_id = str(uuid4())
                target = request.public_key if request.public_key else credential["public_key"]
                payload = json.dumps(dict(
                    protocol="yike-device-proof-v1", tenant_id=tenant, user_id=claims.user_id,
                    device_id=device_id, request_id=request.request_id, challenge_id=challenge_id,
                    session_digest=claims.revocation_key, operation=request.operation,
                    expected_credential_version=request.expected_credential_version,
                    target_public_key=target, nonce=secrets.token_urlsafe(32), expires_at=expires,
                ), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
                self._active(cursor, claims)
                cursor.execute(
                    "INSERT INTO pilot_device_key_requests(tenant_id,owner_user_id,request_id,challenge_id,device_id,"
                    "session_digest,request_sha256,operation,expected_credential_version,target_public_key,"
                    "signing_payload,expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (tenant_id,owner_user_id,request_id) DO NOTHING RETURNING *",
                    (tenant, claims.user_id, request.request_id, challenge_id, device_id, claims.revocation_key,
                     fingerprint, request.operation, request.expected_credential_version, target, payload,
                     datetime.fromtimestamp(expires, UTC)))
                row = _row(cursor)
                if row is None:
                    # A different session/device may race on this user's request ID.
                    cursor.execute("SELECT * FROM pilot_device_key_requests WHERE tenant_id=%s AND owner_user_id=%s "
                                   "AND request_id=%s", (tenant, claims.user_id, request.request_id))
                    row = _row(cursor)
                    if row["request_sha256"] != fingerprint:
                        raise DeviceKeyError("request_conflict", 409)
                self._active(cursor, claims)
                return _challenge(row)

    def complete_challenge(self, claims: TokenClaims, device_id: str, challenge_id: str,
                           proof: CompletionProof) -> dict:
        uuid_string(device_id)
        uuid_string(challenge_id)
        failure = None
        result = None
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                tenant = self._active(cursor, claims)
                status = self._device(cursor, tenant, claims.user_id, device_id)
                self._active(cursor, claims)
                cursor.execute("SELECT * FROM pilot_device_key_requests WHERE tenant_id=%s AND owner_user_id=%s "
                               "AND challenge_id=%s AND device_id=%s FOR UPDATE",
                               (tenant, claims.user_id, challenge_id, device_id))
                row = _row(cursor)
                if row is None:
                    raise DeviceKeyError("request_not_found", 404)
                self._active(cursor, claims)
                if row["state"] == "SUCCEEDED":
                    return _receipt(row)  # Historical evidence survives device revoke/rotation.
                if status != "ACTIVE":
                    raise DeviceKeyError("device_unavailable", 404)
                if row["state"] != "PENDING":
                    raise DeviceKeyError("challenge_expired", 409) if row["state"] == "EXPIRED" else DeviceKeyError("invalid_proof", 400)
                credential = self._credential(cursor, tenant, device_id)
                self._active(cursor, claims)
                try:
                    self._check_expiry(cursor, row)
                    if row["session_digest"] != claims.revocation_key:
                        raise DeviceKeyError("invalid_proof", 400)
                    self._validate_version(row["operation"], row["expected_credential_version"],
                                           row["target_public_key"], credential)
                    if row["operation"] == "ROTATE":
                        if proof.previous_signature is None:
                            raise DeviceKeyError("invalid_proof", 400)
                        verify_signature(credential["public_key"], proof.previous_signature, row["signing_payload"])
                    elif proof.previous_signature is not None:
                        raise DeviceKeyError("invalid_proof", 400)
                    verify_signature(row["target_public_key"], proof.signature, row["signing_payload"])
                    self._active(cursor, claims)
                    self._check_expiry(cursor, row)
                except DeviceKeyError as error:
                    if error.code == "invalid_session":
                        raise
                    failure = error
                    state = "EXPIRED" if error.code == "challenge_expired" else "REJECTED"
                    cursor.execute("UPDATE pilot_device_key_requests SET state=%s,completed_at=clock_timestamp() "
                                   "WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s",
                                   (state, tenant, claims.user_id, row["request_id"]))
                else:
                    version = row["expected_credential_version"] + (row["operation"] != "PROVE")
                    if row["operation"] == "BIND":
                        cursor.execute("INSERT INTO pilot_device_credentials(tenant_id,owner_user_id,device_id,public_key,credential_version) "
                                       "VALUES (%s,%s,%s,%s,%s)",
                                       (tenant, claims.user_id, device_id, row["target_public_key"], version))
                    elif row["operation"] == "ROTATE":
                        cursor.execute("UPDATE pilot_device_credentials SET public_key=%s,credential_version=%s,updated_at=clock_timestamp() "
                                       "WHERE tenant_id=%s AND device_id=%s", (row["target_public_key"], version, tenant, device_id))
                    cursor.execute("UPDATE pilot_device_key_requests SET state='SUCCEEDED',result_version=%s,completed_at=clock_timestamp() "
                                   "WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s RETURNING *",
                                   (version, tenant, claims.user_id, row["request_id"]))
                    result = _receipt(_row(cursor))
        # Consume failed challenges durably; never raise inside their transaction.
        if failure is not None:
            raise failure
        return result

    @staticmethod
    def _check_expiry(cursor, row):
        cursor.execute("SELECT clock_timestamp() >= %s", (row["expires_at"],))
        if cursor.fetchone()[0]:
            raise DeviceKeyError("challenge_expired", 409)

    def get_receipt(self, claims: TokenClaims, request_id: str) -> dict:
        uuid_string(request_id)
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                tenant = self._active(cursor, claims)
                cursor.execute("SELECT * FROM pilot_device_key_requests WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s",
                               (tenant, claims.user_id, request_id))
                row = _row(cursor)
                if row is None:
                    raise DeviceKeyError("request_not_found", 404)
                return _receipt(row)
