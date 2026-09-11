"""Bounded user intent for research strategies; no execution or source authority."""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from pilot.candidate_contract import _validate_url
from pilot.execution_contract import Platform


_ERROR_STATUSES = {
    "invalid_request": 422,
    "invalid_session": 401,
    "request_not_found": 404,
    "strategy_not_found": 404,
    "request_conflict": 409,
    "draft_conflict": 409,
    "strategy_conflict": 409,
    "profile_unavailable": 409,
    "strategy_store_unavailable": 503,
}
_HHMM = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_MAX_CONFIGURATION_BYTES = 65536
_PositiveLimit = Annotated[int, Field(ge=1, le=1000000)]


class StrategyStoreError(Exception):
    """Only a fixed public error code/status can cross the service boundary."""

    def __init__(self, code: str, status: int | None = None):
        if status is None and type(code) is str:
            status = _ERROR_STATUSES.get(code)
        if type(code) is not str or type(status) is not int or _ERROR_STATUSES.get(code) != status:
            code, status = "strategy_store_unavailable", 503
        self.code, self.status = code, status
        super().__init__(code)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _check_string(value: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("invalid unicode") from None
    if any(unicodedata.category(char) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for char in value):
        raise ValueError("invalid control character")


def _raw_fields(value: object, depth: int = 0) -> object:
    """Inspect raw instance fields before any serializer can coerce forged values."""
    if depth > 20:
        raise ValueError("invalid configuration depth")
    if isinstance(value, BaseModel):
        # __dict__ also retains forbidden keys inserted by model_copy(update=...).
        fields = dict(vars(value))
        fields.update(value.__pydantic_extra__ or {})
        return _raw_fields(fields, depth + 1)
    if type(value) is dict:
        for key in value:
            if type(key) is not str:
                raise ValueError("invalid field name")
            _check_string(key)
        return {key: _raw_fields(item, depth + 1) for key, item in value.items()}
    if type(value) in (list, tuple):
        return type(value)(_raw_fields(item, depth + 1) for item in value)
    if isinstance(value, str):
        _check_string(value)
    if type(value) is float and not math.isfinite(value):
        raise ValueError("invalid number")
    return value


def _uuid(value: str) -> str:
    try:
        if type(value) is not str or len(value) != 36 or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError("invalid identifier") from None
    return value


def _visible_text(value: str, maximum: int) -> str:
    if type(value) is not str or not 1 <= len(value) <= maximum or not value.strip():
        raise ValueError("invalid text")
    _check_string(value)
    return value


def _term_key(value: str) -> str:
    return " ".join(value.split()).lower()


def _distinct(values: tuple) -> tuple:
    if len(set(values)) != len(values):
        raise ValueError("duplicate values")
    return values


class _Frozen(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid",
                              hide_input_in_errors=True, revalidate_instances="always")

    @model_validator(mode="before")
    @classmethod
    def raw_fields(cls, value):
        return _raw_fields(value)


class _Schedule(_Frozen):
    kind: Literal["daily", "interval"]
    times: tuple[str, ...] = Field(max_length=24)
    interval: int | float = Field(ge=1, le=168)
    start: str
    end: str
    timezone: str

    @field_validator("times", mode="before")
    @classmethod
    def freeze_times(cls, value):
        return tuple(value) if type(value) is list else value

    @field_validator("times")
    @classmethod
    def check_times(cls, value):
        if any(not _HHMM.fullmatch(item) for item in value):
            raise ValueError("invalid schedule time")
        return _distinct(value)

    @field_validator("start", "end")
    @classmethod
    def check_time(cls, value):
        if not _HHMM.fullmatch(value):
            raise ValueError("invalid schedule time")
        return value

    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            # Missing tzdata is unavailable too: never substitute a local zone.
            raise ValueError("unavailable timezone") from None
        return value

    @model_validator(mode="after")
    def daily_times(self):
        if self.kind == "daily" and not self.times:
            raise ValueError("daily schedule requires times")
        return self


class _VersionedSchedule(_Schedule):
    # A required field on a separate shape preserves legacy JSON and its digest.
    # This records user intent; it does not declare scheduler capabilities.
    policyVersion: Literal[1]

    @field_validator("policyVersion", mode="before")
    @classmethod
    def exact_policy(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("invalid schedule policy version")
        return value

    @model_validator(mode="after")
    def interval_window(self):
        if self.kind == "interval" and self.start == self.end:
            raise ValueError("interval schedule requires distinct bounds")
        return self


class _ResearchLimits(_Frozen):
    sources: _PositiveLimit
    minutes: _PositiveLimit
    modelCalls: _PositiveLimit


class _Research(_Frozen):
    version: Literal[1]
    demandTypes: tuple[Literal["INQUIRY", "COMPARISON", "REPLACEMENT", "CHANGE"], ...] = Field(
        min_length=1, max_length=4)
    maxSoubei: _PositiveLimit
    limits: _ResearchLimits
    stopAtAnyLimit: Literal[True]
    evidenceOrder: Literal["SOURCE_MATCH_CONTEXT"]

    @field_validator("version", mode="before")
    @classmethod
    def exact_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("invalid research version")
        return value

    @field_validator("stopAtAnyLimit", mode="before")
    @classmethod
    def exact_stop(cls, value):
        if value is not True:
            raise ValueError("all research limits must apply")
        return value

    @field_validator("demandTypes", mode="before")
    @classmethod
    def freeze_demands(cls, value):
        return tuple(value) if type(value) is list else value

    @field_validator("demandTypes")
    @classmethod
    def distinct_demands(cls, value):
        return _distinct(value)


class ResearchStrategyConfiguration(_Frozen):
    schema_version: Literal["research-strategy-v1"]
    name: str
    source: Literal["search", "links"]
    keywords: tuple[str, ...] = Field(max_length=20)
    exclusions: tuple[str, ...] = Field(max_length=20)
    links: tuple[str, ...] = Field(max_length=100)
    mode: Literal["once", "monitor"]
    schedule: _VersionedSchedule | _Schedule | None
    research: _Research | None

    @field_validator("name")
    @classmethod
    def check_name(cls, value):
        return _visible_text(value, 60)

    @field_validator("keywords", "exclusions", "links", mode="before")
    @classmethod
    def freeze_arrays(cls, value):
        return tuple(value) if type(value) is list else value

    @field_validator("keywords", "exclusions")
    @classmethod
    def check_terms(cls, value):
        for item in value:
            _visible_text(item, 80)
        _distinct(tuple(_term_key(item) for item in value))
        return value

    @field_validator("links")
    @classmethod
    def check_links(cls, value):
        for item in value:
            _validate_url(item, "PUBLIC_WEB")
        return _distinct(value)

    @model_validator(mode="after")
    def relations_and_size(self):
        if self.source == "search" and not self.keywords:
            raise ValueError("search requires keywords")
        if self.source == "links" and not self.links:
            raise ValueError("links source requires links")
        if any(_term_key(exclusion) in _term_key(keyword)
               for keyword in self.keywords for exclusion in self.exclusions):
            raise ValueError("keyword conflicts with exclusion")
        if self.mode == "monitor" and self.schedule is None:
            raise ValueError("monitor requires schedule")
        if len(_json(self.model_dump(mode="json")).encode("utf-8")) > _MAX_CONFIGURATION_BYTES:
            raise ValueError("configuration is too large")
        return self


class _IndustryTaskStrategy(_Frozen):
    version: Literal["industry-task-strategy-v1"]
    sourceTypes: tuple[Literal[
        "SOCIAL_POST", "COMMENT", "PROCUREMENT", "COMPANY_UPDATE", "INDUSTRY_SITE",
    ], ...] = Field(min_length=1, max_length=5)
    intentSignals: tuple[str, ...] = Field(min_length=1, max_length=5)
    counterSignals: tuple[str, ...] = Field(max_length=5)

    @field_validator("sourceTypes", "intentSignals", "counterSignals", mode="before")
    @classmethod
    def freeze_arrays(cls, value):
        return tuple(value) if type(value) is list else value

    @field_validator("sourceTypes", "intentSignals", "counterSignals")
    @classmethod
    def valid_distinct_values(cls, values):
        for value in values:
            _visible_text(value, 160)
        _distinct(tuple(_term_key(value) for value in values))
        return values


class _IndustryResearchStrategyConfiguration(ResearchStrategyConfiguration):
    # Required only on this shape so legacy bytes and digests remain unchanged.
    industryStrategy: _IndustryTaskStrategy


class _StrategyScope(_Frozen):
    profile_version_id: str
    configuration: _IndustryResearchStrategyConfiguration | ResearchStrategyConfiguration
    platforms: tuple[Platform, ...] = Field(min_length=1, max_length=5)
    max_records: int = Field(ge=1, le=10000)
    max_runtime_seconds: int = Field(ge=1, le=86400)

    @field_validator("profile_version_id")
    @classmethod
    def profile_uuid(cls, value):
        return _uuid(value)

    @field_validator("platforms", mode="before")
    @classmethod
    def freeze_platforms(cls, value):
        return tuple(value) if type(value) is list else value

    @field_validator("platforms")
    @classmethod
    def distinct_platforms(cls, value):
        return _distinct(value)


class _Operation(_Frozen):
    schema_version: Literal["strategy-confirmation-v1"]
    request_id: str

    @field_validator("request_id")
    @classmethod
    def request_uuid(cls, value):
        return _uuid(value)


class PrepareStrategyRequest(_Operation, _StrategyScope):
    draft_id: str
    draft_revision: int = Field(ge=1, le=2147483647)

    @field_validator("draft_id")
    @classmethod
    def draft_uuid(cls, value):
        return _uuid(value)


class _VersionOperation(_Operation):
    strategy_version_id: str

    @field_validator("strategy_version_id")
    @classmethod
    def strategy_uuid(cls, value):
        return _uuid(value)


class ConfirmStrategyRequest(_VersionOperation):
    configuration_sha256: str
    human_confirmed: Literal[True]

    @field_validator("configuration_sha256")
    @classmethod
    def check_digest(cls, value):
        if not _SHA256.fullmatch(value):
            raise ValueError("invalid configuration digest")
        return value

    @field_validator("human_confirmed", mode="before")
    @classmethod
    def exact_confirmation(cls, value):
        if value is not True:
            raise ValueError("explicit confirmation required")
        return value


class RevokeStrategyRequest(_VersionOperation):
    pass


class _StrategySnapshot(_StrategyScope):
    strategy_version_id: str

    @field_validator("strategy_version_id")
    @classmethod
    def strategy_uuid(cls, value):
        return _uuid(value)


def strategy_snapshot(profile_version_id, strategy_version_id, configuration, platforms,
                      max_records, max_runtime_seconds) -> dict:
    """Revalidate intent and return the exact six-field execution runtime snapshot."""
    try:
        parsed = _StrategySnapshot.model_validate(dict(
            profile_version_id=profile_version_id, strategy_version_id=strategy_version_id,
            configuration=configuration, platforms=platforms,
            max_records=max_records, max_runtime_seconds=max_runtime_seconds))
        return parsed.model_dump(mode="json")
    except (ValidationError, ValueError, TypeError, UnicodeError, RecursionError):
        raise StrategyStoreError("invalid_request", 422) from None


def _require_json(value: object, depth: int = 0) -> None:
    if depth > 20:
        raise ValueError("invalid json depth")
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("invalid json key")
            _check_string(key)
            _require_json(item, depth + 1)
    elif type(value) is list:
        for item in value:
            _require_json(item, depth + 1)
    elif type(value) is str:
        _check_string(value)
    elif type(value) is float:
        if not math.isfinite(value):
            raise ValueError("invalid json number")
    elif value is not None and type(value) not in (int, bool):
        raise ValueError("invalid json value")


def configuration_digest(snapshot: object) -> str:
    """Hash validated plain JSON only, with the execution runtime's canonical form."""
    try:
        if type(snapshot) is not dict:
            raise ValueError("invalid snapshot")
        _require_json(snapshot)
        _StrategySnapshot.model_validate(snapshot)
        return hashlib.sha256(_json(snapshot).encode("utf-8")).hexdigest()
    except (ValidationError, ValueError, TypeError, UnicodeError, RecursionError):
        raise StrategyStoreError("invalid_request", 422) from None
