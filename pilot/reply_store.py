"""PostgreSQL persistence for owner-scoped reply and follow-up facts."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from pilot.auth import InvalidPilotToken, TokenClaims
from pilot.reply_contract import ManualFollowupEvent, PlatformReplyEvent, parse_reply_event
from pilot.sessions import PilotSessionRegistry


class ReplyStoreError(ValueError):
    def __init__(self, code: str, status: int = 400):
        self.code, self.status = code, status
        super().__init__(code)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def event_digest(event) -> str:
    return hashlib.sha256(_json(event.model_dump(mode="json")).encode("utf-8")).hexdigest()


def _ts(value: str | None):
    return None if value is None else datetime.fromisoformat(value.replace("Z", "+00:00"))


def event_record(event, revision: int = 1) -> dict:
    value = event.model_dump(mode="json")
    common = {
        "event_id": event.event_id, "revision": revision, "kind": event.kind,
        "opportunity_id": event.opportunity_id, "source_id": event.source_id,
        "profile_version_id": event.profile_version_id, "outreach_request_id": event.outreach_request_id,
        "state": event.state, "corrects_event_id": event.corrects_event_id,
        "reason": event.reason, "observed_at": _ts(event.observed_at),
        "payload": value, "payload_sha256": event_digest(event),
    }
    if isinstance(event, PlatformReplyEvent):
        common.update(platform=event.platform, channel=event.channel, external_reply_id=event.external_reply_id,
                      sender_public_id=event.sender_public_id, body=event.body, received_at=_ts(event.received_at),
                      read_state=event.read_state, read_at=_ts(event.read_at), action=None, note=None, occurred_at=None)
    else:
        common.update(platform=None, channel=None, external_reply_id=None, sender_public_id=None, body=None,
                      received_at=None, read_state=None, read_at=None, action=event.action, note=event.note,
                      occurred_at=_ts(event.occurred_at))
    return common


def decode_event(value: object, digest: str | None = None):
    try:
        event = parse_reply_event(value)
    except Exception:
        raise ReplyStoreError("stored_event_invalid", 503) from None
    if digest is not None and (type(digest) is not str or event_digest(event) != digest):
        raise ReplyStoreError("stored_event_invalid", 503)
    return event


class ReplyEventStore:
    def __init__(self, database):
        self.database = database
        self.sessions = PilotSessionRegistry(database)

    def _active(self, cursor, claims: TokenClaims) -> str:
        if not isinstance(claims, TokenClaims):
            raise ReplyStoreError("invalid_session", 401)
        try:
            return self.sessions.require_active(cursor, claims)
        except (InvalidPilotToken, PermissionError):
            raise ReplyStoreError("invalid_session", 401) from None

    @staticmethod
    def _lock_key(value: str) -> int:
        return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest()[:4], "big", signed=True)

    @staticmethod
    def _row(cursor):
        row = cursor.fetchone()
        return None if row is None else dict(zip((column.name for column in cursor.description), row))

    def record(self, claims: TokenClaims, event):
        if not isinstance(event, (PlatformReplyEvent, ManualFollowupEvent)):
            raise ReplyStoreError("invalid_event", 422)
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant_id = self._active(cursor, claims)
            if event.tenant_id != tenant_id or event.user_id != claims.user_id:
                raise ReplyStoreError("event_scope_mismatch", 409)
            identity = (f"{tenant_id}\0{event.source_id}\0{event.outreach_request_id}\0"
                        f"{getattr(event, 'platform', 'MANUAL')}\0{getattr(event, 'external_reply_id', event.event_id)}")
            cursor.execute("SELECT pg_advisory_xact_lock(11801,%s)", (self._lock_key(identity),))
            self._active(cursor, claims)
            if event.state != "ACTIVE":
                # Corrections/voids are history entries.  They must point at
                # an existing event in the same owner scope and are keyed by
                # their own event id, not by the platform identity.
                cursor.execute("""SELECT 1 FROM pilot_reply_events
                    WHERE tenant_id=%s AND owner_user_id=%s AND event_id=%s
                    ORDER BY revision DESC LIMIT 1""",
                               (tenant_id, claims.user_id, event.corrects_event_id))
                if cursor.fetchone() is None:
                    raise ReplyStoreError("event_target_unavailable", 409)
                cursor.execute("""SELECT event_id,revision,payload,payload_sha256 FROM pilot_reply_events
                    WHERE tenant_id=%s AND owner_user_id=%s AND event_id=%s ORDER BY revision DESC LIMIT 1 FOR UPDATE""",
                               (tenant_id, claims.user_id, event.event_id))
            elif isinstance(event, PlatformReplyEvent):
                # A platform reply is accepted only when the same owner has a
                # durable, human-confirmed origin request for this source and
                # opportunity.  A client cannot fabricate a reply association.
                cursor.execute(
                    "SELECT opportunity_id,source_id FROM pilot_outreach_confirmations "
                    "WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s",
                    (tenant_id, claims.user_id, event.outreach_request_id),
                )
                origin = cursor.fetchone()
                if origin is None or origin[0] != event.opportunity_id or origin[1] != event.source_id:
                    raise ReplyStoreError("reply_origin_unavailable", 409)
                cursor.execute("""SELECT event_id,revision,payload,payload_sha256 FROM pilot_reply_events
                    WHERE tenant_id=%s AND owner_user_id=%s AND source_id=%s AND outreach_request_id=%s
                      AND platform=%s AND external_reply_id=%s ORDER BY revision DESC LIMIT 1 FOR UPDATE""",
                               (tenant_id, claims.user_id, event.source_id, event.outreach_request_id, event.platform, event.external_reply_id))
            elif isinstance(event, ManualFollowupEvent):
                cursor.execute("""SELECT event_id,revision,payload,payload_sha256 FROM pilot_reply_events
                    WHERE tenant_id=%s AND owner_user_id=%s AND event_id=%s ORDER BY revision DESC LIMIT 1 FOR UPDATE""",
                               (tenant_id, claims.user_id, event.event_id))
            existing = self._row(cursor)
            revision = 1
            if existing is not None:
                stored = decode_event(existing["payload"], existing["payload_sha256"])
                if isinstance(event, PlatformReplyEvent) and event.event_id != stored.event_id:
                    old = stored.model_dump(mode="json"); new = event.model_dump(mode="json")
                    old.pop("event_id", None); new.pop("event_id", None)
                    if old != new:
                        raise ReplyStoreError("duplicate_reply_conflict", 409)
                    return stored
                if event_digest(stored) == event_digest(event):
                    return stored
                if isinstance(event, ManualFollowupEvent) or event.event_id != stored.event_id:
                    raise ReplyStoreError("event_conflict", 409)
                revision = existing["revision"] + 1
            record = event_record(event, revision)
            sql_record = record | {"tenant_id": tenant_id, "owner_user_id": claims.user_id,
                                   "payload": _json(record["payload"])}
            cursor.execute("""INSERT INTO pilot_reply_events
                (tenant_id,owner_user_id,event_id,revision,kind,opportunity_id,source_id,profile_version_id,outreach_request_id,
                 platform,channel,external_reply_id,sender_public_id,body,received_at,read_state,read_at,action,note,occurred_at,
                 state,corrects_event_id,reason,observed_at,payload,payload_sha256)
                VALUES (%(tenant_id)s,%(owner_user_id)s,%(event_id)s,%(revision)s,%(kind)s,%(opportunity_id)s,%(source_id)s,
                 %(profile_version_id)s,%(outreach_request_id)s,%(platform)s,%(channel)s,%(external_reply_id)s,%(sender_public_id)s,
                 %(body)s,%(received_at)s,%(read_state)s,%(read_at)s,%(action)s,%(note)s,%(occurred_at)s,%(state)s,
                 %(corrects_event_id)s,%(reason)s,%(observed_at)s,%(payload)s::jsonb,%(payload_sha256)s)""",
                         sql_record)
            self._active(cursor, claims)
            return event

    def list_for_opportunity(self, claims: TokenClaims, opportunity_id: str):
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant_id = self._active(cursor, claims)
            cursor.execute("""SELECT payload,payload_sha256 FROM pilot_reply_events
                WHERE tenant_id=%s AND owner_user_id=%s AND opportunity_id=%s ORDER BY observed_at,revision""",
                           (tenant_id, claims.user_id, opportunity_id))
            rows = cursor.fetchall()
            self._active(cursor, claims)
            return [decode_event(row[0], row[1]) for row in rows]


__all__ = ["ReplyEventStore", "ReplyStoreError", "decode_event", "event_digest", "event_record"]
