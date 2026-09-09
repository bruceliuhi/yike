"""Strict, persistence-agnostic contract for human-approved outreach.

This module deliberately does not send messages or persist secrets.  It models
the immutable facts that a later store/adapter may persist and gives callers an
idempotent request-id registry for the short hand-off between confirmation and
channel execution.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_VERSION = 2_147_483_647
Platform = Literal["BILIBILI", "DOUYIN", "XIAOHONGSHU", "ZHIHU", "PUBLIC_WEB"]
Channel = Literal["comment", "dm"]
CapabilityStatus = Literal["AVAILABLE", "UNAVAILABLE", "UNVERIFIED", "PENDING"]
SendStatus = Literal["UNKNOWN", "PENDING", "FAILED", "SENT"]


class OutreachContractError(ValueError):
    """Stable, non-sensitive contract error."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class _Frozen(BaseModel):
    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
        hide_input_in_errors=True,
    )


_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def canonical_uuid(value: str) -> str:
    if type(value) is not str or not _UUID_RE.fullmatch(value) or str(UUID(value)) != value:
        raise ValueError("canonical UUID required")
    return value


def _text(value: str, *, minimum: int = 1, maximum: int = 4096) -> str:
    if type(value) is not str or not minimum <= len(value) <= maximum or not value.strip():
        raise ValueError("invalid text")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("invalid text") from None
    if any((ord(ch) < 32 and ch not in "\t\n\r") or 127 <= ord(ch) <= 159 for ch in value):
        raise ValueError("invalid text")
    return value


def _aware(value: datetime) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware datetime required")
    return value.astimezone(timezone.utc)


def _timestamp(value: str) -> str:
    if type(value) is not str:
        raise ValueError("RFC3339 timestamp required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        parsed = _aware(parsed)
    except (TypeError, ValueError):
        raise ValueError("RFC3339 timestamp required") from None
    return parsed.isoformat().replace("+00:00", "Z")


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_digest(content: str) -> str:
    """Digest content only; callers never need to persist the plaintext here."""
    return hashlib.sha256(_text(content, maximum=120_000).encode("utf-8")).hexdigest()


class SourceObject(_Frozen):
    schema_version: Literal["outreach-source-v1"]
    source_id: str
    opportunity_id: str
    platform: Platform
    public_url: str
    author_public_id: str
    source_version: int = Field(ge=1, le=MAX_VERSION)

    @field_validator("source_id", "opportunity_id")
    @classmethod
    def ids(cls, value: str) -> str:
        return canonical_uuid(value)

    @field_validator("author_public_id")
    @classmethod
    def author(cls, value: str) -> str:
        return _text(value, maximum=512)

    @field_validator("public_url")
    @classmethod
    def url(cls, value: str) -> str:
        if type(value) is not str or not (value.startswith("https://") or value.startswith("http://")):
            raise ValueError("public URL required")
        lowered = value.lower()
        if any(marker in lowered for marker in ("token=", "cookie=", "session=", "password=", "secret=")):
            raise ValueError("private URL material is not allowed")
        return _text(value, maximum=2048)


class ChannelCapability(_Frozen):
    schema_version: Literal["outreach-capability-v1"]
    channel: Channel
    status: CapabilityStatus
    connection_id: str | None
    connection_version: int | None = Field(default=None, ge=1, le=MAX_VERSION)
    checked_at: str
    reason: str

    @field_validator("connection_id")
    @classmethod
    def connection(cls, value: str | None) -> str | None:
        return None if value is None else canonical_uuid(value)

    @field_validator("checked_at")
    @classmethod
    def timestamp(cls, value: str) -> str:
        return _timestamp(value)

    @field_validator("reason")
    @classmethod
    def explanation(cls, value: str) -> str:
        return _text(value, maximum=1024)

    @model_validator(mode="after")
    def connection_shape(self):
        if self.status == "AVAILABLE" and (self.connection_id is None or self.connection_version is None):
            raise ValueError("available capability requires connection")
        if self.connection_id is None and self.connection_version is not None:
            raise ValueError("connection version requires connection")
        return self


class RecipientMapping(_Frozen):
    schema_version: Literal["outreach-recipient-v1"]
    source_id: str
    opportunity_id: str
    channel: Channel
    recipient_id: str
    recipient_label: str
    connection_id: str
    connection_version: int = Field(ge=1, le=MAX_VERSION)
    status: Literal["MAPPED"]

    @field_validator("source_id", "opportunity_id", "connection_id")
    @classmethod
    def mapping_ids(cls, value: str) -> str:
        return canonical_uuid(value)

    @field_validator("recipient_id")
    @classmethod
    def recipient(cls, value: str) -> str:
        return _text(value, maximum=512)

    @field_validator("recipient_label")
    @classmethod
    def label(cls, value: str) -> str:
        return _text(value, maximum=512)


class DraftBinding(_Frozen):
    schema_version: Literal["outreach-draft-v1"]
    draft_id: str
    opportunity_id: str
    source_id: str
    source_version: int = Field(ge=1, le=MAX_VERSION)
    channel: Channel
    content: str
    version: int = Field(ge=1, le=MAX_VERSION)
    account_id: str
    connection_version: int = Field(ge=1, le=MAX_VERSION)
    recipient_id: str

    @field_validator("draft_id", "opportunity_id", "source_id", "account_id")
    @classmethod
    def draft_ids(cls, value: str) -> str:
        return canonical_uuid(value)

    @field_validator("recipient_id")
    @classmethod
    def draft_recipient(cls, value: str) -> str:
        return _text(value, maximum=512)

    @field_validator("content")
    @classmethod
    def body(cls, value: str) -> str:
        return _text(value, maximum=120_000)


class ConfirmationSnapshot(_Frozen):
    schema_version: Literal["outreach-confirmation-v1"]
    request_id: str
    opportunity_id: str
    source_id: str
    source_version: int = Field(ge=1, le=MAX_VERSION)
    channel: Channel
    version: int = Field(ge=1, le=MAX_VERSION)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    account_id: str
    connection_version: int = Field(ge=1, le=MAX_VERSION)
    recipient_id: str
    expires_at: str
    confirmed_at: str

    @field_validator("request_id", "opportunity_id", "source_id", "account_id")
    @classmethod
    def confirmation_ids(cls, value: str) -> str:
        return canonical_uuid(value)

    @field_validator("recipient_id")
    @classmethod
    def confirmation_recipient(cls, value: str) -> str:
        return _text(value, maximum=512)

    @field_validator("expires_at", "confirmed_at")
    @classmethod
    def confirmation_times(cls, value: str) -> str:
        return _timestamp(value)

    @model_validator(mode="after")
    def expiry_order(self):
        if datetime.fromisoformat(self.expires_at.replace("Z", "+00:00")) <= datetime.fromisoformat(self.confirmed_at.replace("Z", "+00:00")):
            raise ValueError("confirmation expiry must be after confirmation")
        return self

    def is_valid_for(self, draft: DraftBinding, mapping: RecipientMapping, now: datetime) -> bool:
        try:
            current = _aware(now)
        except ValueError:
            return False
        return (
            datetime.fromisoformat(self.confirmed_at.replace("Z", "+00:00")) <= current < datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            and draft.opportunity_id == self.opportunity_id
            and draft.source_id == self.source_id
            and draft.source_version == self.source_version
            and draft.channel == self.channel
            and draft.version == self.version
            and content_digest(draft.content) == self.content_sha256
            and draft.account_id == self.account_id
            and draft.connection_version == self.connection_version
            and draft.recipient_id == self.recipient_id
            and mapping.opportunity_id == self.opportunity_id
            and mapping.source_id == self.source_id
            and mapping.channel == self.channel
            and mapping.recipient_id == self.recipient_id
            and mapping.connection_id == self.account_id
            and mapping.connection_version == self.connection_version
            and mapping.status == "MAPPED"
        )


class SendReceipt(_Frozen):
    schema_version: Literal["outreach-send-v1"]
    request_id: str
    opportunity_id: str
    channel: Channel
    version: int = Field(ge=1, le=MAX_VERSION)
    status: SendStatus
    confirmed: bool | None = None
    confirmed_not_delivered: bool | None = None
    message: str | None = None

    @field_validator("request_id", "opportunity_id")
    @classmethod
    def receipt_ids(cls, value: str) -> str:
        return canonical_uuid(value)

    @field_validator("message")
    @classmethod
    def receipt_message(cls, value: str | None) -> str | None:
        return None if value is None else _text(value, maximum=1024)

    @model_validator(mode="after")
    def outcome(self):
        if self.status == "SENT" and self.confirmed is not True:
            raise ValueError("SENT requires confirmed=true")
        if self.status == "FAILED" and (self.confirmed is not True or self.confirmed_not_delivered is not True):
            raise ValueError("FAILED requires confirmed non-delivery")
        if self.status in {"UNKNOWN", "PENDING"} and (self.confirmed is not None or self.confirmed_not_delivered is not None):
            raise ValueError("pending outcomes cannot claim confirmation")
        if self.status == "SENT" and self.confirmed_not_delivered is not None:
            raise ValueError("SENT cannot claim non-delivery")
        return self


def map_recipient(source: SourceObject, capability: ChannelCapability, raw: object) -> RecipientMapping:
    """Validate a server-resolved recipient; never infer one from a label."""
    if capability.status != "AVAILABLE":
        raise ValueError("capability unavailable")
    mapping = RecipientMapping.model_validate(raw)
    if mapping.source_id != source.source_id or mapping.opportunity_id != source.opportunity_id:
        raise ValueError("recipient mapping does not match source")
    if mapping.recipient_id != source.author_public_id:
        raise ValueError("recipient mapping does not match source author")
    if mapping.channel != capability.channel or mapping.connection_id != capability.connection_id:
        raise ValueError("recipient mapping does not match capability")
    if mapping.connection_version != capability.connection_version:
        raise ValueError("recipient mapping connection changed")
    return mapping


def bind_confirmation(source: SourceObject, draft: DraftBinding, mapping: RecipientMapping, *, request_id: str,
                      expires_at: datetime, confirmed_at: datetime) -> ConfirmationSnapshot:
    if draft.opportunity_id != source.opportunity_id or draft.source_id != source.source_id:
        raise ValueError("draft does not match source")
    if mapping.opportunity_id != source.opportunity_id or mapping.source_id != source.source_id:
        raise ValueError("recipient mapping does not match source")
    if mapping.recipient_id != source.author_public_id:
        raise ValueError("recipient mapping does not match source author")
    if draft.source_version != source.source_version:
        raise ValueError("draft does not match source version")
    if draft.channel != mapping.channel or draft.recipient_id != mapping.recipient_id:
        raise ValueError("draft does not match recipient")
    if draft.account_id != mapping.connection_id or draft.connection_version != mapping.connection_version:
        raise ValueError("draft does not match connection")
    return ConfirmationSnapshot(
        schema_version="outreach-confirmation-v1", request_id=canonical_uuid(request_id),
        opportunity_id=source.opportunity_id, source_id=source.source_id,
        source_version=source.source_version,
        channel=draft.channel, version=draft.version, content_sha256=content_digest(draft.content),
        account_id=draft.account_id, connection_version=draft.connection_version,
        recipient_id=draft.recipient_id,
        expires_at=_timestamp(_aware(expires_at).isoformat().replace("+00:00", "Z")),
        confirmed_at=_timestamp(_aware(confirmed_at).isoformat().replace("+00:00", "Z")),
    )


class IdempotencyRegistry:
    """Small in-memory model of a durable request-id uniqueness constraint."""

    def __init__(self):
        self._items: dict[str, ConfirmationSnapshot] = {}

    def bind(self, snapshot: ConfirmationSnapshot) -> ConfirmationSnapshot:
        snapshot = ConfirmationSnapshot.model_validate(snapshot)
        existing = self._items.get(snapshot.request_id)
        if existing is not None:
            if existing.model_dump(mode="json") != snapshot.model_dump(mode="json"):
                raise ValueError("request_id binding conflict")
            return existing
        self._items[snapshot.request_id] = snapshot
        return snapshot

    def get(self, request_id: str) -> ConfirmationSnapshot | None:
        return self._items.get(canonical_uuid(request_id))


__all__ = [
    "ChannelCapability", "ConfirmationSnapshot", "DraftBinding", "IdempotencyRegistry",
    "OutreachContractError", "RecipientMapping", "SendReceipt", "SourceObject",
    "bind_confirmation", "canonical_uuid", "content_digest", "map_recipient",
]
