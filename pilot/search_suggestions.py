"""Authenticated PostgreSQL receipts; no model calls or disclosure authorization.

Only a first successful reserve returns description to the trusted caller. That
is not permission to disclose the description to any external model. Original
session completion, user-isolated receipts, and tenant-wide quota are durable.
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
import hashlib
import json
import re
import unicodedata
from uuid import UUID, uuid4

import psycopg
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from pilot.auth import InvalidPilotToken, TokenClaims
from pilot.db import PilotDatabase
from pilot.search_suggestion_model import (RULE_VERSION, SearchSuggestionError,
                                           serialize_suggestion, validate_suggestion)
from pilot.sessions import PilotSessionRegistry


_ERRORS = {
    "invalid_request": 422, "invalid_session": 401, "request_not_found": 404,
    "request_conflict": 409, "request_session_mismatch": 409, "profile_unavailable": 409,
    "disclosure_mismatch": 409,
    "suggestion_rate_limited": 429, "suggestion_quota_exceeded": 429,
    "invalid_suggestion_configuration": 500, "suggestion_store_unavailable": 503,
}
_TERMINAL_ERRORS = {"invalid_suggestion_result": "FAILED", "suggestion_provider_rejected": "FAILED",
                    "suggestion_result_unknown": "UNKNOWN", "dispatch_failed": "FAILED"}
_PUBLIC_FIELDS = ("request_id", "draft_id", "draft_revision", "profile_version_id", "profile_sha256",
                  "rule_version", "model_provider", "model_name", "disclosure_policy_version", "state", "result", "usage", "error_code",
                  "created_at", "updated_at")
_INTERNAL_FIELDS = _PUBLIC_FIELDS + ("request_sha256", "origin_session_key", "origin_session_expires_at")
_REJECTION_REASONS = {"capability_unavailable", "disclosure_mismatch", "profile_unavailable",
                      "suggestion_busy", "suggestion_rate_limited", "suggestion_quota_exceeded"}
_REJECTION_FIELDS = ("request_id", "draft_id", "draft_revision", "profile_version_id", "profile_sha256",
    "rule_version", "model_provider", "model_name", "disclosure_policy_version", "reason", "created_at",
    "request_sha256", "origin_session_key", "origin_session_expires_at")


class SearchSuggestionStoreError(Exception):
    def __init__(self, code: str, status: int | None = None):
        if type(code) is not str or code not in _ERRORS or (status is not None and status != _ERRORS[code]):
            code = "suggestion_store_unavailable"
        self.code, self.status = code, _ERRORS[code]
        super().__init__(code)


def _safe_database_errors(operation):
    @wraps(operation)
    def wrapped(*args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except psycopg.Error:
            pass
        # Outside both the transaction context manager and the except block:
        # generator.throw otherwise attaches the database error as __context__.
        raise SearchSuggestionStoreError("suggestion_store_unavailable")
    return wrapped


def _canonical_uuid(value: str) -> str:
    if type(value) is not str or len(value) != 36:
        raise ValueError("canonical UUID required")
    if str(UUID(value)) != value:
        raise ValueError("canonical UUID required")
    return value


class SearchSuggestionRequest(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", revalidate_instances="always",
                              hide_input_in_errors=True)
    request_id: str
    draft_id: str
    profile_version_id: str
    draft_revision: int = Field(ge=0, le=2147483647)

    @field_validator("request_id", "draft_id", "profile_version_id")
    @classmethod
    def valid_uuid(cls, value: str) -> str:
        return _canonical_uuid(value)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _usage(value: object) -> dict | None:
    names = ("prompt_tokens", "completion_tokens", "total_tokens")
    if type(value) is not dict:
        return None
    value = value.copy()
    if any(type(value.get(name)) is not int or not 0 <= value[name] <= 2147483647 for name in names):
        return None
    if value["total_tokens"] != value["prompt_tokens"] + value["completion_tokens"]:
        return None
    return {name: value[name] for name in names}


def _profile_content(payload: object) -> str | None:
    try:
        if type(payload) is not dict:
            return None
        description = payload.get("description")
        if type(description) is not str or not 1 <= len(description) <= 8000:
            return None
        description.encode("utf-8")
        if not any(not ch.isspace() and unicodedata.category(ch)[0] not in "CMZ" for ch in description):
            return None
        if any(unicodedata.category(ch) == "Cc" and ch not in "\t\n\r" for ch in description):
            return None
        return description
    except (ValueError, TypeError, UnicodeError):
        return None


class SearchSuggestionStore:
    def __init__(self, database: PilotDatabase):
        self.database = database
        self.sessions = PilotSessionRegistry(database)

    @contextmanager
    def _transaction(self):
        with self.database.connect() as connection, connection.cursor() as cursor:
            yield cursor

    def _active(self, cursor, claims: TokenClaims) -> str:
        if (not isinstance(claims, TokenClaims) or type(claims.user_id) is not str
                or not 1 <= len(claims.user_id) <= 256 or claims.user_id.strip() != claims.user_id
                or any(unicodedata.category(ch)[0] == "C" for ch in claims.user_id)
                or type(claims.revocation_key) is not str
                or not re.fullmatch(r"[a-f0-9]{64}", claims.revocation_key)
                or type(claims.expires_at) is not int or not 0 < claims.expires_at <= 253402300799):
            raise SearchSuggestionStoreError("invalid_session")
        try:
            return self.sessions.require_active(cursor, claims)
        except (InvalidPilotToken, PermissionError):
            pass
        raise SearchSuggestionStoreError("invalid_session")

    @staticmethod
    def _request_id(request_id: str) -> None:
        try:
            _canonical_uuid(request_id)
            return
        except (ValueError, TypeError):
            pass
        raise SearchSuggestionStoreError("invalid_request")

    @staticmethod
    def _row(cursor, tenant: str, user: str, request_id: str, *, lock: bool = False) -> dict | None:
        cursor.execute("SELECT " + ",".join(_INTERNAL_FIELDS) + " FROM pilot_search_suggestion_requests "
            "WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s" + (" FOR UPDATE" if lock else ""),
            (tenant, user, request_id))
        row = cursor.fetchone()
        return dict(zip(_INTERNAL_FIELDS, row)) if row else None

    @staticmethod
    def _rejection(cursor, tenant: str, user: str, request_id: str, *, lock: bool = False) -> dict | None:
        cursor.execute("SELECT " + ",".join(_REJECTION_FIELDS) + " FROM pilot_search_suggestion_rejections "
            "WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s",
            (tenant, user, request_id))
        row = cursor.fetchone()
        return dict(zip(_REJECTION_FIELDS, row)) if row else None

    @staticmethod
    def _rejection_receipt(row: dict) -> dict:
        receipt = {key: row[key] for key in _PUBLIC_FIELDS if key not in {"state", "result", "usage", "error_code", "updated_at"}}
        receipt.update(state="NOT_SUBMITTED", result=None, usage=None, error_code=row["reason"],
                       created_at=row["created_at"].isoformat(), updated_at=row["created_at"].isoformat(),
                       profile_current=False)
        return receipt

    @staticmethod
    def _lock(cursor, tenant: str) -> None:
        cursor.execute("SELECT pg_advisory_xact_lock(11001,hashtext(%s))", (tenant,))

    @staticmethod
    def _profile(cursor, tenant: str, version_id: str, *, lock: bool) -> dict | None:
        cursor.execute("SELECT profile_id FROM business_profile_versions WHERE tenant_id=%s AND profile_version_id=%s",
                       (tenant, version_id))
        row = cursor.fetchone()
        if row is None:
            return None
        profile_id = row[0]
        if lock:
            cursor.execute("SELECT profile_id FROM business_profiles WHERE tenant_id=%s AND profile_id=%s FOR UPDATE",
                           (tenant, profile_id))
            if cursor.fetchone() is None:
                return None
        cursor.execute("SELECT payload,content_sha256,status FROM business_profile_versions "
            "WHERE tenant_id=%s AND profile_version_id=%s AND profile_id=%s", (tenant, version_id, profile_id))
        row = cursor.fetchone()
        if row is None:
            return None
        from pilot.material_references import profile_content_digest
        cursor.execute("SELECT field_name,source_owner_user_id,source_profile_version_id,material_id,material_version,"
                       "extraction_id,adopted_value_sha256,valid FROM pilot_material_profile_references "
                       "WHERE tenant_id=%s AND target_profile_version_id=%s ORDER BY field_name", (tenant, version_id))
        reference_rows = cursor.fetchall()
        refs = [{"field_name": a, "source_owner_user_id": b, "source_profile_version_id": c,
                 "material_id": d, "material_version": e, "extraction_id": f,
                 "adopted_value_sha256": g} for a, b, c, d, e, f, g, _valid in reference_rows]
        valid = all(item[-1] for item in reference_rows)
        description = _profile_content(row[0])
        managed = bool(refs) or profile_content_digest(row[0], [], managed=False) != row[1]
        if description is None or profile_content_digest(row[0], refs, managed=managed) != row[1]:
            description = None
        return {"sha256": row[1], "description": description, "status": row[2], "references_valid": valid}

    def _safe(self, cursor, tenant: str, row: dict) -> dict:
        profile = self._profile(cursor, tenant, row["profile_version_id"], lock=False)
        receipt = {key: row[key] for key in _PUBLIC_FIELDS}
        for key in ("created_at", "updated_at"):
            receipt[key] = receipt[key].isoformat()
        receipt["profile_current"] = bool(profile and profile["status"] == "CONFIRMED"
            and profile["description"] is not None and profile["references_valid"]
            and profile["sha256"] == row["profile_sha256"])
        return receipt

    @_safe_database_errors
    def get_receipt(self, claims: TokenClaims, request_id: str) -> dict:
        self._request_id(request_id)
        with self._transaction() as cursor:
            tenant = self._active(cursor, claims)
            row = self._row(cursor, tenant, claims.user_id, request_id)
            if row is None:
                rejection = self._rejection(cursor, tenant, claims.user_id, request_id)
                if rejection is None:
                    raise SearchSuggestionStoreError("request_not_found")
                receipt = self._rejection_receipt(rejection)
            else:
                receipt = self._safe(cursor, tenant, row)
            self._active(cursor, claims)
            return receipt

    @_safe_database_errors
    def replay_receipt(self, claims: TokenClaims, request: SearchSuggestionRequest, disclosure: dict) -> dict | None:
        try:
            request = SearchSuggestionRequest.model_validate(request)
        except ValidationError:
            raise SearchSuggestionStoreError("invalid_request") from None
        fingerprint = _digest({"request": request.model_dump(), "disclosure": disclosure})
        with self._transaction() as cursor:
            tenant = self._active(cursor, claims)
            row = self._row(cursor, tenant, claims.user_id, request.request_id)
            if row is None:
                rejection = self._rejection(cursor, tenant, claims.user_id, request.request_id)
                if rejection is None:
                    return None
                if rejection["request_sha256"] != fingerprint:
                    raise SearchSuggestionStoreError("request_conflict")
                receipt = self._rejection_receipt(rejection)
                self._active(cursor, claims)
                return receipt
            if row["request_sha256"] != fingerprint:
                raise SearchSuggestionStoreError("request_conflict")
            receipt = self._safe(cursor, tenant, row)
            self._active(cursor, claims)
            return receipt

    @_safe_database_errors
    def reject(self, claims: TokenClaims, request: SearchSuggestionRequest, disclosure: dict, reason: str) -> dict:
        try:
            request = SearchSuggestionRequest.model_validate(request)
        except ValidationError:
            raise SearchSuggestionStoreError("invalid_request") from None
        if (type(disclosure) is not dict or set(disclosure) != {"accepted", "profile_sha256", "model_provider",
                "model_name", "policy_version"} or disclosure.get("accepted") is not True
                or not re.fullmatch(r"[a-f0-9]{64}", disclosure.get("profile_sha256", ""))
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", disclosure.get("model_provider", ""))
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}", disclosure.get("model_name", ""))
                or disclosure.get("policy_version") != "profile-description-v1" or reason not in _REJECTION_REASONS):
            raise SearchSuggestionStoreError("invalid_request")
        fingerprint = _digest({"request": request.model_dump(), "disclosure": disclosure})
        with self._transaction() as cursor:
            tenant = self._active(cursor, claims)
            self._lock(cursor, tenant)
            self._active(cursor, claims)
            actual = self._row(cursor, tenant, claims.user_id, request.request_id, lock=True)
            if actual is not None:
                if actual["request_sha256"] != fingerprint:
                    raise SearchSuggestionStoreError("request_conflict")
                receipt = self._safe(cursor, tenant, actual)
                self._active(cursor, claims)
                return receipt
            rejection = self._rejection(cursor, tenant, claims.user_id, request.request_id, lock=True)
            if rejection is not None:
                if rejection["request_sha256"] != fingerprint:
                    raise SearchSuggestionStoreError("request_conflict")
                receipt = self._rejection_receipt(rejection)
                self._active(cursor, claims)
                return receipt
            self._active(cursor, claims)
            cursor.execute("INSERT INTO pilot_search_suggestion_rejections(tenant_id,owner_user_id,request_id,draft_id,"
                "draft_revision,profile_version_id,request_sha256,profile_sha256,origin_session_key,"
                "origin_session_expires_at,rule_version,model_provider,model_name,disclosure_policy_version,reason) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (tenant, claims.user_id, request.request_id, request.draft_id, request.draft_revision,
                 request.profile_version_id, fingerprint, disclosure["profile_sha256"], claims.revocation_key,
                 claims.expires_at, RULE_VERSION, disclosure["model_provider"], disclosure["model_name"],
                 disclosure["policy_version"], reason))
            rejection = self._rejection(cursor, tenant, claims.user_id, request.request_id)
            self._active(cursor, claims)
            return self._rejection_receipt(rejection)

    @_safe_database_errors
    def preview(self, claims: TokenClaims, profile_version_id: str, *, provider: str, model: str) -> dict:
        self._request_id(profile_version_id)
        if (type(provider) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", provider)
                or type(model) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}", model)):
            raise SearchSuggestionStoreError("invalid_suggestion_configuration")
        with self._transaction() as cursor:
            tenant = self._active(cursor, claims)
            profile = self._profile(cursor, tenant, profile_version_id, lock=False)
            self._active(cursor, claims)
            if not profile or profile["status"] != "CONFIRMED" or profile["description"] is None or not profile["references_valid"]:
                raise SearchSuggestionStoreError("profile_unavailable")
            return {"profile_version_id": profile_version_id, "profile_sha256": profile["sha256"],
                    "description": profile["description"], "model_provider": provider, "model_name": model,
                    "disclosure_policy_version": "profile-description-v1"}

    @_safe_database_errors
    def reserve(self, claims: TokenClaims, request: SearchSuggestionRequest, *, provider: str, model: str,
                disclosure: dict | None = None) -> tuple[dict, str | None]:
        try:
            request = SearchSuggestionRequest.model_validate(request)
        except ValidationError:
            request = None
        if request is None:
            raise SearchSuggestionStoreError("invalid_request")
        if disclosure is not None and (type(disclosure) is not dict or set(disclosure) != {
                "accepted", "profile_sha256", "model_provider", "model_name", "policy_version"}):
            raise SearchSuggestionStoreError("invalid_request")
        fingerprint = _digest(request.model_dump() if disclosure is None else
                              {"request": request.model_dump(), "disclosure": disclosure})
        with self._transaction() as cursor:
            tenant = self._active(cursor, claims)
            self._lock(cursor, tenant)
            self._active(cursor, claims)
            previous = self._row(cursor, tenant, claims.user_id, request.request_id, lock=True)
            self._active(cursor, claims)
            if previous:
                if previous["request_sha256"] != fingerprint:
                    raise SearchSuggestionStoreError("request_conflict")
                receipt = self._safe(cursor, tenant, previous)
                self._active(cursor, claims)
                return receipt, None
            rejection = self._rejection(cursor, tenant, claims.user_id, request.request_id, lock=True)
            if rejection:
                if rejection["request_sha256"] != fingerprint:
                    raise SearchSuggestionStoreError("request_conflict")
                return self._rejection_receipt(rejection), None
            if (type(provider) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", provider)
                    or type(model) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}", model)):
                raise SearchSuggestionStoreError("invalid_suggestion_configuration")
            profile = self._profile(cursor, tenant, request.profile_version_id, lock=True)
            self._active(cursor, claims)
            if not profile or profile["status"] != "CONFIRMED" or profile["description"] is None or not profile["references_valid"]:
                raise SearchSuggestionStoreError("profile_unavailable")
            if disclosure is not None and disclosure != {"accepted": True, "profile_sha256": profile["sha256"],
                    "model_provider": provider, "model_name": model, "policy_version": "profile-description-v1"}:
                raise SearchSuggestionStoreError("disclosure_mismatch")
            cursor.execute("WITH wall AS MATERIALIZED (SELECT clock_timestamp() AS now) "
                "SELECT count(*),COALESCE(bool_or(created_at > wall.now-interval '2 seconds'),false) "
                "FROM pilot_search_suggestion_quota_events,wall WHERE tenant_id=%s AND created_at > wall.now-interval '1 hour'",
                (tenant,))
            count, too_recent = cursor.fetchone()
            if count >= 10:
                raise SearchSuggestionStoreError("suggestion_quota_exceeded")
            if too_recent:
                raise SearchSuggestionStoreError("suggestion_rate_limited")
            self._active(cursor, claims)
            cursor.execute("INSERT INTO pilot_search_suggestion_requests(tenant_id,owner_user_id,request_id,draft_id,draft_revision,"
                "profile_version_id,request_sha256,profile_sha256,origin_session_key,origin_session_expires_at,rule_version,model_provider,model_name,disclosure_policy_version) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (tenant, claims.user_id, request.request_id, request.draft_id, request.draft_revision,
                 request.profile_version_id, fingerprint, profile["sha256"], claims.revocation_key,
                 claims.expires_at, RULE_VERSION, provider, model,
                 disclosure["policy_version"] if disclosure is not None else None))
            cursor.execute("INSERT INTO pilot_search_suggestion_quota_events(tenant_id,quota_event_id) VALUES (%s,%s)",
                           (tenant, str(uuid4())))
            row = self._row(cursor, tenant, claims.user_id, request.request_id)
            receipt = self._safe(cursor, tenant, row)
            self._active(cursor, claims)
            return receipt, profile["description"]

    @_safe_database_errors
    def prepare_dispatch(self, claims: TokenClaims, request_id: str) -> str:
        """Recheck the originating session and immutable profile immediately before disclosure."""
        self._request_id(request_id)
        with self._transaction() as cursor:
            tenant = self._active(cursor, claims)
            row = self._row(cursor, tenant, claims.user_id, request_id, lock=True)
            self._active(cursor, claims)
            if row is None:
                raise SearchSuggestionStoreError("request_not_found")
            if claims.revocation_key != row["origin_session_key"] or claims.expires_at != row["origin_session_expires_at"]:
                raise SearchSuggestionStoreError("request_session_mismatch")
            if row["state"] != "PENDING" or row["disclosure_policy_version"] != "profile-description-v1":
                raise SearchSuggestionStoreError("request_conflict")
            profile = self._profile(cursor, tenant, row["profile_version_id"], lock=True)
            self._active(cursor, claims)
            if (not profile or profile["status"] != "CONFIRMED" or profile["description"] is None or not profile["references_valid"]
                    or profile["sha256"] != row["profile_sha256"]):
                raise SearchSuggestionStoreError("profile_unavailable")
            return profile["description"]

    @_safe_database_errors
    def finish(self, claims: TokenClaims, request_id: str, *, content=None, usage=None, error=None) -> dict:
        self._request_id(request_id)
        with self._transaction() as cursor:
            tenant = self._active(cursor, claims)
            row = self._row(cursor, tenant, claims.user_id, request_id, lock=True)
            self._active(cursor, claims)
            if row is None:
                raise SearchSuggestionStoreError("request_not_found")
            if (claims.revocation_key != row["origin_session_key"] or claims.expires_at != row["origin_session_expires_at"]):
                raise SearchSuggestionStoreError("request_session_mismatch")
            if row["state"] != "PENDING":
                receipt = self._safe(cursor, tenant, row)
                self._active(cursor, claims)
                return receipt
            profile = self._profile(cursor, tenant, row["profile_version_id"], lock=True)
            self._active(cursor, claims)
            state, error_code, validated, measured = "FAILED", "profile_changed", None, None
            if (profile and profile["status"] == "CONFIRMED" and profile["description"] is not None and profile["references_valid"]
                    and profile["sha256"] == row["profile_sha256"]):
                if error is not None:
                    error_code = error.code if isinstance(error, SearchSuggestionError) else error
                    if type(error_code) is not str or error_code not in _TERMINAL_ERRORS or content is not None:
                        raise SearchSuggestionStoreError("invalid_request")
                    state = _TERMINAL_ERRORS[error_code]
                elif content is None:
                    raise SearchSuggestionStoreError("invalid_request")
                else:
                    error_code = "invalid_suggestion_result"
                    try:
                        validated = serialize_suggestion(validate_suggestion(content, description=profile["description"]))
                    except SearchSuggestionError:
                        pass
                    if validated is not None:
                        state, error_code, measured = "SUCCEEDED", None, _usage(usage)
            self._active(cursor, claims)
            cursor.execute("UPDATE pilot_search_suggestion_requests SET state=%s,result=%s::jsonb,usage=%s::jsonb,error_code=%s "
                "WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s AND state='PENDING'",
                (state, _json(validated) if validated is not None else None, _json(measured) if measured is not None else None,
                 error_code, tenant, claims.user_id, request_id))
            updated = self._row(cursor, tenant, claims.user_id, request_id)
            receipt = self._safe(cursor, tenant, updated)
            self._active(cursor, claims)
            return receipt
