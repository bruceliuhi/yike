"""PostgreSQL persistence for owner-scoped reply and follow-up facts."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from pilot.auth import InvalidPilotToken, TokenClaims
from pilot.reply_contract import ManualFollowupEvent, PlatformReplyEvent, mark_read, parse_reply_event, transition_state
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
        self.signed = None

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

    def _lock_events(self, cursor, tenant, owner, event):
        # Both uniqueness domains must serialize, even if a conflicting caller
        # changes the source/platform attached to an existing event UUID.
        identities = [('event', tenant, owner, event.event_id)]
        if event.corrects_event_id:
            identities.append(('event', tenant, owner, event.corrects_event_id))
        if isinstance(event, PlatformReplyEvent):
            identities.append(('platform', tenant, owner, event.source_id,
                event.outreach_request_id, event.platform, event.external_reply_id))
        for key in sorted({self._lock_key(_json(identity)) for identity in identities}):
            cursor.execute('SELECT pg_advisory_xact_lock(11801,%s)', (key,))

    @staticmethod
    def _read_transition(previous, event):
        try:
            if not isinstance(previous, PlatformReplyEvent) or event.state != 'ACTIVE': raise ValueError
            expected = mark_read(previous, read_at=_ts(event.read_at), observed_at=_ts(event.observed_at))
            if expected != event or _ts(event.observed_at) < _ts(previous.observed_at): raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise ReplyStoreError('event_conflict', 409) from None

    @staticmethod
    def _transition(previous, event):
        try:
            transition_state(previous, event)
            if previous.event_id == event.event_id: raise ValueError
            if isinstance(previous, PlatformReplyEvent) and any(getattr(previous, key) != getattr(event, key)
                    for key in ('platform', 'channel', 'external_reply_id', 'sender_public_id')):
                raise ValueError
        except ValueError:
            raise ReplyStoreError('event_transition_invalid', 409) from None

    def record(self, claims: TokenClaims, event):
        with self.database.connect() as connection, connection.cursor() as cursor:
            return self.record_in_transaction(cursor, claims, event)

    def record_in_transaction(self, cursor, claims, event, *, device_attestation=None):
        if not isinstance(event, (PlatformReplyEvent, ManualFollowupEvent)):
            raise ReplyStoreError('invalid_event',422)
        tenant_id = self._active(cursor, claims)
        if event.tenant_id != tenant_id or event.user_id != claims.user_id:
            raise ReplyStoreError("event_scope_mismatch", 409)
        if isinstance(event, PlatformReplyEvent) and device_attestation is None:
            # Also fence unsigned replay, read-state and correction requests.
            cursor.execute('SELECT opportunity_id,source_id FROM pilot_outreach_confirmations '
                'WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s',
                (tenant_id,claims.user_id,event.outreach_request_id))
            origin=cursor.fetchone()
            if origin is None or origin!=(event.opportunity_id,event.source_id):
                raise ReplyStoreError('reply_origin_unavailable',409)
        self._lock_events(cursor, tenant_id, claims.user_id, event)
        self._active(cursor, claims)
        # Append-only rows need SELECT, not FOR UPDATE. The transaction's
        # advisory locks protect inserts, including the absent-first-row case.
        cursor.execute('SELECT revision,payload,payload_sha256 FROM pilot_reply_events '
            'WHERE tenant_id=%s AND owner_user_id=%s AND event_id=%s ORDER BY revision DESC',
            (tenant_id, claims.user_id, event.event_id))
        prior = cursor.fetchall()
        stored = None
        for _, payload, digest in prior:
            candidate = decode_event(payload, digest)
            if event_digest(candidate) == event_digest(event):
                self._active(cursor, claims)
                return candidate  # An exact old revision is historical, not a rollback.
            if stored is None: stored = candidate
        if stored is not None:
            if not isinstance(event, PlatformReplyEvent) or event.state != 'ACTIVE':
                raise ReplyStoreError('event_conflict', 409)
            self._read_transition(stored, event)
        revision = 1
        if event.state != "ACTIVE":
            # Corrections/voids are history entries.  They must point at
            # an existing event in the same owner scope and are keyed by
            # their own event id, not by the platform identity.
            cursor.execute("""SELECT payload,payload_sha256 FROM pilot_reply_events
                WHERE tenant_id=%s AND owner_user_id=%s AND event_id=%s
                ORDER BY revision DESC LIMIT 1""",
                           (tenant_id, claims.user_id, event.corrects_event_id))
            target = cursor.fetchone()
            if target is None:
                raise ReplyStoreError("event_target_unavailable", 409)
            previous = decode_event(target[0], target[1])
            self._transition(previous, event)
        elif isinstance(event, PlatformReplyEvent):
            cursor.execute("""SELECT event_id,revision,payload,payload_sha256 FROM pilot_reply_events
                WHERE tenant_id=%s AND owner_user_id=%s AND source_id=%s AND outreach_request_id=%s
                  AND platform=%s AND external_reply_id=%s AND state='ACTIVE' ORDER BY revision DESC LIMIT 1""",
                           (tenant_id, claims.user_id, event.source_id, event.outreach_request_id, event.platform, event.external_reply_id))
            existing = self._row(cursor)
            if existing is not None and stored is None:
                same_reply = decode_event(existing['payload'], existing['payload_sha256'])
                old = same_reply.model_dump(mode="json"); new = event.model_dump(mode="json")
                old.pop("event_id", None); new.pop("event_id", None)
                if old != new:
                    raise ReplyStoreError("duplicate_reply_conflict", 409)
                self._active(cursor, claims)
                return same_reply
        if isinstance(event, PlatformReplyEvent):
            cursor.execute('SELECT COALESCE(max(revision),0)+1 FROM pilot_reply_events '
                'WHERE tenant_id=%s AND owner_user_id=%s AND source_id=%s AND outreach_request_id=%s '
                'AND platform=%s AND external_reply_id=%s',
                (tenant_id, claims.user_id, event.source_id, event.outreach_request_id, event.platform, event.external_reply_id))
            revision = cursor.fetchone()[0]
        record = event_record(event, revision)
        sql_record = record | {"tenant_id": tenant_id, "owner_user_id": claims.user_id,
                               "payload": _json(record["payload"]),
                               "device_attestation":None if device_attestation is None else _json(device_attestation)}
        cursor.execute("""INSERT INTO pilot_reply_events
            (tenant_id,owner_user_id,event_id,revision,kind,opportunity_id,source_id,profile_version_id,outreach_request_id,
             platform,channel,external_reply_id,sender_public_id,body,received_at,read_state,read_at,action,note,occurred_at,
             state,corrects_event_id,reason,observed_at,payload,payload_sha256,device_attestation)
            VALUES (%(tenant_id)s,%(owner_user_id)s,%(event_id)s,%(revision)s,%(kind)s,%(opportunity_id)s,%(source_id)s,
             %(profile_version_id)s,%(outreach_request_id)s,%(platform)s,%(channel)s,%(external_reply_id)s,%(sender_public_id)s,
             %(body)s,%(received_at)s,%(read_state)s,%(read_at)s,%(action)s,%(note)s,%(occurred_at)s,%(state)s,
             %(corrects_event_id)s,%(reason)s,%(observed_at)s,%(payload)s::jsonb,%(payload_sha256)s,%(device_attestation)s::jsonb)""",
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
