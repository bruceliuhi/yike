"""PostgreSQL persistence for human-approved outreach confirmations.

This store freezes the confirmation binding before a future channel adapter is
called.  It intentionally has no send/reply methods and never persists draft
plaintext, cookies, tokens, or browser profile material.
"""
from __future__ import annotations

import hashlib
import json

from pilot.auth import InvalidPilotToken, TokenClaims
from pilot.outreach_contract import (
    ConfirmationSnapshot,
    DraftBinding,
    RecipientMapping,
    SourceObject,
    bind_confirmation as build_confirmation,
    canonical_uuid,
)
from pilot.sessions import PilotSessionRegistry


class OutreachStoreError(ValueError):
    """Stable, non-sensitive persistence error."""

    def __init__(self, code: str, status: int = 400):
        self.code, self.status = code, status
        super().__init__(code)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def snapshot_sha256(snapshot: ConfirmationSnapshot) -> str:
    """Hash the canonical snapshot, not the unpersisted draft body."""
    body = snapshot.model_dump(mode="json")
    return hashlib.sha256(_json(body).encode("utf-8")).hexdigest()


def snapshot_record(snapshot: ConfirmationSnapshot) -> dict:
    """Return the SQL record fields; plaintext draft content is absent by design."""
    body = snapshot.model_dump(mode="json")
    return {
        "request_id": snapshot.request_id,
        "opportunity_id": snapshot.opportunity_id,
        "source_id": snapshot.source_id,
        "channel": snapshot.channel,
        "draft_version": snapshot.version,
        "account_id": snapshot.account_id,
        "connection_version": snapshot.connection_version,
        "recipient_id": snapshot.recipient_id,
        "content_sha256": snapshot.content_sha256,
        "snapshot": body,
        "snapshot_sha256": snapshot_sha256(snapshot),
    }


def decode_snapshot(value: object, digest: str | None = None) -> ConfirmationSnapshot:
    """Validate a stored JSON snapshot and optionally its canonical digest."""
    try:
        snapshot = ConfirmationSnapshot.model_validate(value)
    except Exception:
        raise OutreachStoreError("stored_snapshot_invalid", 503) from None
    if digest is not None and (type(digest) is not str or snapshot_sha256(snapshot) != digest):
        raise OutreachStoreError("stored_snapshot_invalid", 503)
    return snapshot


class OutreachConfirmationStore:
    """Owner/tenant-scoped durable request-id registry.

    ``bind`` is the only mutating operation.  PostgreSQL advisory locking plus
    the composite primary key makes same-request concurrent calls replay the
    exact snapshot or fail closed on a changed binding.
    """

    def __init__(self, database):
        self.database = database
        self.sessions = PilotSessionRegistry(database)

    @staticmethod
    def _validate_claims(claims: TokenClaims) -> None:
        if not isinstance(claims, TokenClaims):
            raise InvalidPilotToken("invalid pilot token")

    @staticmethod
    def _lock_key(tenant_id: str, owner_user_id: str, request_id: str) -> int:
        raw = (tenant_id + "\0" + owner_user_id + "\0" + request_id).encode("utf-8")
        return int.from_bytes(hashlib.sha256(raw).digest()[:4], "big", signed=True)

    @staticmethod
    def _row(cursor):
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(zip((column.name for column in cursor.description), row))

    def _active(self, cursor, claims: TokenClaims) -> str:
        self._validate_claims(claims)
        try:
            return self.sessions.require_active(cursor, claims)
        except (InvalidPilotToken, PermissionError):
            raise OutreachStoreError("invalid_session", 401) from None

    @staticmethod
    def _assert_authoritative_facts(cursor, tenant_id: str, source: SourceObject,
                                    draft: DraftBinding, mapping: RecipientMapping) -> None:
        """Re-read current tenant facts before accepting a confirmation.

        The DTOs arriving from a client are not authorization.  This check is
        intentionally conservative: a missing, closed, blocked, or stale
        source/opportunity/connection cannot produce a durable confirmation.
        """
        cursor.execute(
            "SELECT platform,public_url,health FROM pilot_sources "
            "WHERE tenant_id=%s AND source_id=%s FOR SHARE",
            (tenant_id, source.source_id),
        )
        source_row = cursor.fetchone()
        if source_row is None or source_row[0] != source.platform or source_row[1] != source.public_url or source_row[2] == "BLOCKED":
            raise OutreachStoreError("source_facts_unavailable", 409)
        cursor.execute(
            "SELECT source_id,source_status FROM pilot_opportunities "
            "WHERE tenant_id=%s AND opportunity_id=%s FOR SHARE",
            (tenant_id, source.opportunity_id),
        )
        opportunity_row = cursor.fetchone()
        if opportunity_row is None or opportunity_row[0] != source.source_id or opportunity_row[1] != "OPEN":
            raise OutreachStoreError("opportunity_facts_unavailable", 409)
        cursor.execute(
            "SELECT platform,status,connection_version FROM pilot_platform_connections "
            "WHERE tenant_id=%s AND connection_id=%s FOR SHARE",
            (tenant_id, draft.account_id),
        )
        connection_row = cursor.fetchone()
        if (
            connection_row is None
            or connection_row[0] != source.platform
            or connection_row[1] != "CONNECTED"
            or connection_row[2] != draft.connection_version
            or mapping.connection_id != draft.account_id
        ):
            raise OutreachStoreError("connection_facts_unavailable", 409)

    def bind(
        self,
        claims: TokenClaims,
        source: SourceObject,
        draft: DraftBinding,
        mapping: RecipientMapping,
        *,
        request_id: str,
        expires_at,
        confirmed_at,
    ) -> ConfirmationSnapshot:
        """Persist or replay one immutable confirmation snapshot.

        The caller must have resolved the recipient and obtained a valid
        human confirmation; this method does not contact a platform.
        """
        try:
            snapshot = build_confirmation(
                source,
                draft,
                mapping,
                request_id=request_id,
                expires_at=expires_at,
                confirmed_at=confirmed_at,
            )
        except (TypeError, ValueError):
            raise OutreachStoreError("invalid_confirmation", 422) from None
        record = snapshot_record(snapshot)
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant_id = self._active(cursor, claims)
            cursor.execute(
                "SELECT pg_advisory_xact_lock(11701,%s)",
                (self._lock_key(tenant_id, claims.user_id, snapshot.request_id),),
            )
            self._active(cursor, claims)
            self._assert_authoritative_facts(cursor, tenant_id, source, draft, mapping)
            cursor.execute(
                "SELECT snapshot,snapshot_sha256 FROM pilot_outreach_confirmations "
                "WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s",
                (tenant_id, claims.user_id, snapshot.request_id),
            )
            existing = self._row(cursor)
            if existing is not None:
                stored = decode_snapshot(existing["snapshot"], existing["snapshot_sha256"])
                if snapshot_sha256(stored) != record["snapshot_sha256"]:
                    raise OutreachStoreError("request_conflict", 409)
                self._active(cursor, claims)
                return stored
            cursor.execute(
                "INSERT INTO pilot_outreach_confirmations "
                "(tenant_id,owner_user_id,request_id,opportunity_id,source_id,channel,draft_version,"
                "account_id,connection_version,recipient_id,content_sha256,snapshot,snapshot_sha256) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)",
                (
                    tenant_id,
                    claims.user_id,
                    record["request_id"],
                    record["opportunity_id"],
                    record["source_id"],
                    record["channel"],
                    record["draft_version"],
                    record["account_id"],
                    record["connection_version"],
                    record["recipient_id"],
                    record["content_sha256"],
                    _json(record["snapshot"]),
                    record["snapshot_sha256"],
                ),
            )
            self._active(cursor, claims)
            return snapshot

    def get(self, claims: TokenClaims, request_id: str) -> ConfirmationSnapshot:
        """Read one owner-private snapshot; no cross-tenant lookup is exposed."""
        try:
            request_id = canonical_uuid(request_id)
        except ValueError:
            raise OutreachStoreError("invalid_request", 422) from None
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant_id = self._active(cursor, claims)
            cursor.execute(
                "SELECT snapshot,snapshot_sha256 FROM pilot_outreach_confirmations "
                "WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s",
                (tenant_id, claims.user_id, request_id),
            )
            row = self._row(cursor)
            self._active(cursor, claims)
            if row is None:
                raise OutreachStoreError("request_not_found", 404)
            return decode_snapshot(row["snapshot"], row["snapshot_sha256"])


__all__ = [
    "OutreachConfirmationStore",
    "OutreachStoreError",
    "decode_snapshot",
    "snapshot_record",
    "snapshot_sha256",
]
