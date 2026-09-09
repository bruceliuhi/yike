"""Strict, append-only contract for platform replies and manual follow-ups.

This module records facts only.  It does not poll a platform, mark a remote
message read, or infer a reply from a UI state.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_MAX_VERSION = 2_147_483_647
_Platform = Literal["BILIBILI", "DOUYIN", "XIAOHONGSHU", "ZHIHU", "PUBLIC_WEB"]
_Channel = Literal["comment", "dm"]
_State = Literal["ACTIVE", "CORRECTED", "VOID"]


def _uuid(value: str) -> str:
    if type(value) is not str:
        raise ValueError("canonical UUID required")
    try:
        parsed = UUID(value)
    except ValueError:
        raise ValueError("canonical UUID required") from None
    if str(parsed) != value or parsed.version not in (1, 2, 3, 4, 5):
        raise ValueError("canonical UUID required")
    return value


def _text(value: str, maximum: int = 4096) -> str:
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError("invalid text")
    if any((ord(ch) < 32 and ch not in "\t\n\r") or 127 <= ord(ch) <= 159 for ch in value):
        raise ValueError("invalid text")
    return value


def _timestamp(value: str) -> str:
    if type(value) is not str:
        raise ValueError("timezone-aware timestamp required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("timezone-aware timestamp required") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class _Event(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", revalidate_instances="always", hide_input_in_errors=True)

    schema_version: Literal["reply-event-v1"]
    event_id: str
    tenant_id: str
    user_id: str
    opportunity_id: str
    source_id: str
    outreach_request_id: str
    profile_version_id: str
    state: _State = "ACTIVE"
    observed_at: str
    corrects_event_id: str | None = None
    reason: str | None = None

    @field_validator("event_id", "tenant_id", "user_id", "opportunity_id", "source_id", "outreach_request_id", "profile_version_id")
    @classmethod
    def ids(cls, value: str) -> str:
        return _uuid(value)

    @field_validator("observed_at")
    @classmethod
    def observed(cls, value: str) -> str:
        return _timestamp(value)

    @field_validator("corrects_event_id")
    @classmethod
    def correction_id(cls, value: str | None) -> str | None:
        return None if value is None else _uuid(value)

    @field_validator("reason")
    @classmethod
    def correction_reason(cls, value: str | None) -> str | None:
        return None if value is None else _text(value, 1024)

    @model_validator(mode="after")
    def correction_shape(self):
        if self.state == "ACTIVE" and (self.corrects_event_id is not None or self.reason is not None):
            raise ValueError("active event cannot correct another event")
        if self.state != "ACTIVE" and (self.corrects_event_id is None or self.reason is None):
            raise ValueError("correction requires target and reason")
        return self


class PlatformReplyEvent(_Event):
    kind: Literal["PLATFORM_REPLY"]
    platform: _Platform
    channel: _Channel
    external_reply_id: str
    sender_public_id: str
    body: str
    received_at: str
    read_state: Literal["UNREAD", "READ", "UNKNOWN"]
    read_at: str | None = None

    @field_validator("external_reply_id", "sender_public_id")
    @classmethod
    def public_ids(cls, value: str) -> str:
        return _text(value, 512)

    @field_validator("body")
    @classmethod
    def reply_body(cls, value: str) -> str:
        return _text(value, 120_000)

    @field_validator("received_at", "read_at")
    @classmethod
    def times(cls, value: str | None) -> str | None:
        return None if value is None else _timestamp(value)

    @model_validator(mode="after")
    def read_shape(self):
        if self.read_state == "READ" and self.read_at is None:
            raise ValueError("read event requires read_at")
        if self.read_state != "READ" and self.read_at is not None:
            raise ValueError("unread or unknown event cannot carry read_at")
        received = datetime.fromisoformat(self.received_at.replace("Z", "+00:00"))
        observed = datetime.fromisoformat(self.observed_at.replace("Z", "+00:00"))
        if received > observed:
            raise ValueError("reply observed before received")
        if self.read_at is not None:
            read_at = datetime.fromisoformat(self.read_at.replace("Z", "+00:00"))
            if read_at < received or read_at > observed:
                raise ValueError("read_at outside observation window")
        return self


class ManualFollowupEvent(_Event):
    kind: Literal["MANUAL_FOLLOWUP"]
    action: Literal["CONTACTED", "MEETING", "QUOTED", "LOST", "WON", "NOTE"]
    note: str
    occurred_at: str

    @field_validator("note")
    @classmethod
    def followup_note(cls, value: str) -> str:
        return _text(value, 120_000)

    @field_validator("occurred_at")
    @classmethod
    def occurrence(cls, value: str) -> str:
        return _timestamp(value)

    @model_validator(mode="after")
    def occurrence_not_future_of_observation(self):
        occurred = datetime.fromisoformat(self.occurred_at.replace("Z", "+00:00"))
        observed = datetime.fromisoformat(self.observed_at.replace("Z", "+00:00"))
        if occurred > observed:
            raise ValueError("future occurrence")
        if occurred.year > datetime.now(timezone.utc).year + 1:
            raise ValueError("future occurrence")
        return self


def parse_reply_event(value: object) -> PlatformReplyEvent | ManualFollowupEvent:
    if type(value) is not dict:
        raise ValueError("reply event object required")
    kind = value.get("kind")
    if kind == "PLATFORM_REPLY":
        return PlatformReplyEvent.model_validate(value)
    if kind == "MANUAL_FOLLOWUP":
        return ManualFollowupEvent.model_validate(value)
    raise ValueError("unknown reply event kind")


def mark_read(event: PlatformReplyEvent | ManualFollowupEvent, *, read_at: datetime,
              observed_at: datetime | None = None) -> PlatformReplyEvent:
    if not isinstance(event, PlatformReplyEvent):
        raise ValueError("mark-read requires platform reply")
    if event.read_state == "UNKNOWN":
        raise ValueError("unknown read state")
    if event.read_state != "UNREAD":
        raise ValueError("event is not UNREAD")
    read = _timestamp(_aware(read_at).isoformat().replace("+00:00", "Z"))
    observed = observed_at or read_at
    value = event.model_dump()
    value.update(read_state="READ", read_at=read, observed_at=_timestamp(_aware(observed).isoformat().replace("+00:00", "Z")))
    return PlatformReplyEvent.model_validate(value)


def _aware(value: datetime) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware datetime required")
    return value.astimezone(timezone.utc)


def transition_state(previous: _Event, successor: _Event) -> _Event:
    if not isinstance(previous, _Event) or not isinstance(successor, _Event):
        raise ValueError("reply event required")
    scope = ("tenant_id", "user_id", "opportunity_id", "source_id", "profile_version_id", "outreach_request_id", "kind")
    if any(getattr(previous, name) != getattr(successor, name) for name in scope):
        raise ValueError("scope mismatch")
    if previous.state != "ACTIVE" or successor.state == "ACTIVE":
        raise ValueError("state transition must be forward")
    if successor.corrects_event_id != previous.event_id:
        raise ValueError("state transition target mismatch")
    return successor


class ReplyEventRegistry:
    """In-memory deduplication model; production requires a durable unique key."""

    def __init__(self):
        self._items: dict[tuple[str, str, str, str, str], PlatformReplyEvent | ManualFollowupEvent] = {}

    def record(self, event: PlatformReplyEvent | ManualFollowupEvent):
        if not isinstance(event, _Event):
            raise ValueError("reply event required")
        if event.state != "ACTIVE":
            # Corrections and voids are append-only history, not a second
            # observation competing with the active platform identity.
            key = (event.tenant_id, event.source_id, event.outreach_request_id, "HISTORY", event.event_id)
            existing = self._items.get(key)
            if existing is not None:
                if existing.model_dump(mode="json") != event.model_dump(mode="json"):
                    raise ValueError("event history duplicate conflict")
                return existing
            self._items[key] = event
            return event
        if isinstance(event, PlatformReplyEvent):
            key = (event.tenant_id, event.source_id, event.outreach_request_id, event.platform, event.external_reply_id)
            existing = self._items.get(key)
            if existing is not None:
                old = existing.model_dump(mode="json")
                new = event.model_dump(mode="json")
                old.pop("event_id", None)
                new.pop("event_id", None)
                if old != new:
                    raise ValueError("duplicate platform reply conflict")
                return existing
            self._items[key] = event
        else:
            key = (event.tenant_id, event.source_id, event.outreach_request_id, "MANUAL", event.event_id)
            existing = self._items.get(key)
            if existing is not None:
                if existing.model_dump(mode="json") != event.model_dump(mode="json"):
                    raise ValueError("duplicate manual event conflict")
                return existing
            self._items[key] = event
        return event


__all__ = [
    "ManualFollowupEvent", "PlatformReplyEvent", "ReplyEventRegistry",
    "mark_read", "parse_reply_event", "transition_state",
]
