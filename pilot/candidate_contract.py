"""Strict, offline DTO validation for untrusted candidate claims."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import parse_qsl, unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, field_validator, model_validator

_OPAQUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_FRAGMENT = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SENSITIVE = ("token", "cookie", "session", "authorization", "signature", "password", "secret")
_NUMERIC_HOST = re.compile(r"^(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+))*$", re.IGNORECASE)
_DOMAINS = {
    "XIAOHONGSHU": ("xiaohongshu.com", "xhslink.com"),
    "DOUYIN": ("douyin.com", "iesdouyin.com"),
    "BILIBILI": ("bilibili.com", "b23.tv"),
    "ZHIHU": ("zhihu.com",),
}

class CandidateContractError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)

class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

def _opaque(value: str) -> str:
    if not isinstance(value, str) or not _OPAQUE.fullmatch(value):
        raise ValueError("invalid opaque identifier")
    return value

def _text(value: str, minimum: int, maximum: int, *, blank: bool = True) -> str:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise ValueError("invalid text")
    try: value.encode("utf-8")
    except UnicodeEncodeError: raise ValueError("invalid unicode") from None
    if not blank and not value.strip(): raise ValueError("blank text")
    if any((ord(ch) < 32 and ch not in "\t\n\r") or 127 <= ord(ch) <= 159 for ch in value):
        raise ValueError("control character")
    return value

def _parse_time(value: str) -> datetime:
    if not isinstance(value, str) or not _TIME.fullmatch(value): raise ValueError("invalid source time")
    try: return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError: raise ValueError("invalid source time") from None

def _normalize_host(hostname: str) -> str:
    host = hostname[:-1] if hostname.endswith(".") else hostname
    return host.encode("idna").decode("ascii").lower()

def _origin(url: str) -> str:
    parts = urlsplit(url)
    host = _normalize_host(parts.hostname or "")
    if ":" in host:
        host = f"[{host}]"
    return f"{parts.scheme.lower()}://{host}"

def _validate_url(value: str, platform: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 2048: raise ValueError("invalid source url")
    try: value.encode("utf-8")
    except UnicodeEncodeError: raise ValueError("invalid source url") from None
    decoded = unquote(value)
    if "\\" in value or any(ord(ch) < 33 or ord(ch) == 127 for ch in decoded): raise ValueError("invalid source url")
    try:
        parts = urlsplit(value)
        port = parts.port
        host = _normalize_host(parts.hostname or "")
    except (ValueError, UnicodeError): raise ValueError("invalid source url") from None
    if parts.scheme not in ("http", "https") or not host or parts.username is not None or parts.password is not None:
        raise ValueError("invalid source url")
    if port not in (None, 80 if parts.scheme == "http" else 443): raise ValueError("invalid source url")
    if host == "localhost" or host.endswith((".localhost", ".local")): raise ValueError("invalid source url")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global: raise ValueError("invalid source url")
    if address is None and _NUMERIC_HOST.fullmatch(host): raise ValueError("invalid source url")
    if platform != "PUBLIC_WEB" and not any(host == domain or host.endswith("." + domain) for domain in _DOMAINS[platform]):
        raise ValueError("invalid source url")
    for key, _ in parse_qsl(parts.query, keep_blank_values=True):
        if any(marker in unquote(key).lower() for marker in _SENSITIVE): raise ValueError("invalid source url")
    if parts.fragment and not _FRAGMENT.fullmatch(unquote(parts.fragment)): raise ValueError("invalid source url")
    return value

class ExecutionContextClaim(_Frozen):
    device_id: str; task_id: str; run_id: str; platform_run_id: str; lease_id: str
    credential_version: StrictInt = Field(ge=1, le=2147483647)
    execution_generation: StrictInt = Field(ge=1, le=2147483647)
    access_mode: Literal["PLATFORM_ACCOUNT", "PUBLIC_ANONYMOUS"]
    connection_id: str | None
    connection_version: StrictInt | None = Field(default=None, ge=1, le=2147483647)

    @field_validator("device_id", "task_id", "run_id", "platform_run_id", "lease_id", "connection_id")
    @classmethod
    def ids(cls, value): return None if value is None else _opaque(value)

class ParentContext(_Frozen):
    external_comment_id: str
    body: str | None = None
    author_public_id: str | None = None
    published_at: str | None = None
    public_url: str | None = None

    @field_validator("external_comment_id")
    @classmethod
    def comment_id(cls, value): return _text(value, 1, 256, blank=False)
    @field_validator("body")
    @classmethod
    def body_text(cls, value): return None if value is None else _text(value, 1, 20000, blank=False)
    @field_validator("author_public_id")
    @classmethod
    def author(cls, value): return None if value is None else _text(value, 1, 256, blank=False)
    @field_validator("published_at")
    @classmethod
    def time_shape(cls, value):
        if value is not None: _parse_time(value)
        return value

class CandidateRecord(_Frozen):
    kind: Literal["POST", "COMMENT", "PAGE"]
    external_source_id: str | None
    external_comment_id: str | None
    public_url: str
    title: str | None
    author_public_id: str | None
    body: str
    published_at: str | None
    observed_at: str
    parent: ParentContext | None
    collector_version: str
    normalizer_version: str
    query: str | None

    @field_validator("external_source_id", "external_comment_id")
    @classmethod
    def external_ids(cls, value): return None if value is None else _text(value, 1, 256, blank=False)
    @field_validator("title")
    @classmethod
    def title_text(cls, value): return None if value is None else _text(value, 1, 512, blank=False)
    @field_validator("author_public_id")
    @classmethod
    def author(cls, value): return None if value is None else _text(value, 1, 256, blank=False)
    @field_validator("body")
    @classmethod
    def body_text(cls, value): return _text(value, 1, 20000, blank=False)
    @field_validator("published_at", "observed_at")
    @classmethod
    def time_shape(cls, value):
        if value is not None: _parse_time(value)
        return value
    @field_validator("collector_version", "normalizer_version")
    @classmethod
    def versions(cls, value): return _opaque(value)
    @field_validator("query")
    @classmethod
    def query_text(cls, value): return None if value is None else _text(value, 1, 500, blank=False)

    @model_validator(mode="after")
    def relations(self):
        if (self.kind == "COMMENT") != (self.external_comment_id is not None): raise ValueError("invalid record relation")
        if self.parent is not None and self.kind != "COMMENT": raise ValueError("invalid record relation")
        if self.parent is not None and self.parent.external_comment_id == self.external_comment_id: raise ValueError("invalid record relation")
        return self

class CandidateBatch(_Frozen):
    schema_version: Literal["candidate-upload-v1"]
    request_id: str
    platform: Literal["XIAOHONGSHU", "DOUYIN", "BILIBILI", "ZHIHU", "PUBLIC_WEB"]
    profile_version_id: str
    strategy_version_id: str
    execution: ExecutionContextClaim
    records: tuple[CandidateRecord, ...] = Field(max_length=100)
    @field_validator("request_id", "profile_version_id", "strategy_version_id")
    @classmethod
    def ids(cls, value): return _opaque(value)

def _digest(value: object) -> str:
    encoded=json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    try: return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    except UnicodeEncodeError: raise CandidateContractError("INVALID_RECORD") from None

def source_identity(record: CandidateRecord, platform: str) -> str:
    source = record.external_source_id or record.public_url
    value = {"platform":platform, "kind":record.kind, "source":source, "comment":record.external_comment_id}
    if platform == "PUBLIC_WEB": value["origin"] = _origin(record.public_url)
    return _digest(value)

def content_version(record: CandidateRecord) -> str:
    return _digest({"public_url":record.public_url, "title":record.title, "author_public_id":record.author_public_id,
        "body":record.body, "published_at":record.published_at,
        "parent":None if record.parent is None else record.parent.model_dump(mode="json")})

def batch_fingerprint(batch: CandidateBatch) -> str:
    value=batch.model_dump(mode="json"); value.pop("request_id")
    return _digest(value)

def replay_decision(stored_fingerprint: str | None, incoming_fingerprint: str) -> str:
    if stored_fingerprint is None: return "NEW"
    return "REPLAY" if stored_fingerprint == incoming_fingerprint else "CONFLICT"

def validate_candidate_batch(payload: object, *, now: datetime) -> CandidateBatch:
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    trusted_now=now.astimezone(timezone.utc)
    if not isinstance(payload, dict): raise CandidateContractError("INVALID_BATCH") from None
    top_keys=set(CandidateBatch.model_fields)
    if set(payload) - top_keys: raise CandidateContractError("INVALID_BATCH") from None
    execution_data=payload.get("execution")
    try: execution=ExecutionContextClaim.model_validate(execution_data)
    except ValidationError: raise CandidateContractError("INVALID_EXECUTION_CLAIM") from None
    platform=payload.get("platform")
    if not isinstance(platform, str) or platform not in {"XIAOHONGSHU", "DOUYIN", "BILIBILI", "ZHIHU", "PUBLIC_WEB"}:
        raise CandidateContractError("INVALID_BATCH") from None
    if execution.access_mode == "PLATFORM_ACCOUNT":
        if execution.connection_id is None or execution.connection_version is None:
            raise CandidateContractError("INVALID_EXECUTION_CLAIM") from None
    elif platform != "PUBLIC_WEB" or execution.connection_id is not None or execution.connection_version is not None:
        raise CandidateContractError("INVALID_EXECUTION_CLAIM") from None
    raw_records=payload.get("records")
    if not isinstance(raw_records, list) or len(raw_records)>100: raise CandidateContractError("INVALID_BATCH") from None
    records=[]
    for raw in raw_records:
        if isinstance(raw, dict):
            try:
                for candidate_time in (raw.get("published_at"), raw.get("observed_at")):
                    if candidate_time is not None: _parse_time(candidate_time)
                parent_data = raw.get("parent")
                if isinstance(parent_data, dict) and parent_data.get("published_at") is not None:
                    _parse_time(parent_data["published_at"])
            except ValueError:
                raise CandidateContractError("INVALID_SOURCE_TIME") from None
        try: item=CandidateRecord.model_validate(raw)
        except ValidationError: raise CandidateContractError("INVALID_RECORD") from None
        if item.kind == "PAGE" and platform != "PUBLIC_WEB": raise CandidateContractError("INVALID_RECORD") from None
        if item.external_source_id is None and platform != "PUBLIC_WEB": raise CandidateContractError("INVALID_RECORD") from None
        try:
            _validate_url(item.public_url, platform)
            if item.parent and item.parent.public_url is not None: _validate_url(item.parent.public_url, platform)
        except (ValueError, KeyError): raise CandidateContractError("INVALID_SOURCE_URL") from None
        observed=_parse_time(item.observed_at); published=_parse_time(item.published_at) if item.published_at else None
        parent_time=_parse_time(item.parent.published_at) if item.parent and item.parent.published_at else None
        if observed>trusted_now or (published and published>observed) or (parent_time and parent_time>(published or observed)):
            raise CandidateContractError("INVALID_SOURCE_TIME") from None
        records.append(item)
    data=dict(payload); data["execution"]=execution; data["records"]=tuple(records)
    try: parsed=CandidateBatch.model_validate(data)
    except ValidationError: raise CandidateContractError("INVALID_BATCH") from None
    seen={}
    for item in parsed.records:
        identity=source_identity(item, parsed.platform); version=content_version(item)
        if identity in seen:
            code="DUPLICATE_RECORD" if seen[identity]==version else "SOURCE_VERSION_CONFLICT"
            raise CandidateContractError(code) from None
        seen[identity]=version
    return parsed
