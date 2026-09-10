"""Strict user intent contract for durable monitor plans."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_STATUSES = {
    "invalid_request": 422, "invalid_session": 401, "plan_not_found": 404,
    "request_not_found": 404, "request_conflict": 409, "plan_conflict": 409,
    "strategy_conflict": 409, "unsupported_schedule": 409, "plan_limit": 409,
    "monitor_store_unavailable": 503,
}


class MonitorPlanError(Exception):
    def __init__(self, code: str, status: int | None = None):
        self.code = code if code in _STATUSES else "monitor_store_unavailable"
        self.status = _STATUSES[self.code]
        super().__init__(self.code)


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid",
                              hide_input_in_errors=True, revalidate_instances="always")

    @model_validator(mode="before")
    @classmethod
    def raw_model(cls, value):
        if isinstance(value, BaseModel):
            # Include injected model_copy keys so extra=forbid still sees them.
            return dict(value.__dict__)
        return value

    @staticmethod
    def canonical_uuid(value):
        if type(value) is not str:
            raise ValueError("UUID string required")
        try:
            if str(UUID(value)) != value:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise ValueError("canonical UUID required") from None
        return value


class CreateMonitorPlanRequest(_Strict):
    schema_version: Literal["monitor-plans-v1"]
    request_id: str
    profile_version_id: str
    strategy_version_id: str
    human_confirmed: Literal[True]

    _uuid_fields = field_validator("request_id", "profile_version_id", "strategy_version_id")(_Strict.canonical_uuid)

    @field_validator("human_confirmed", mode="before")
    @classmethod
    def exact_confirmation(cls, value):
        if value is not True:
            raise ValueError("explicit confirmation required")
        return value


class SetMonitorPlanStateRequest(_Strict):
    schema_version: Literal["monitor-plans-v1"]
    request_id: str
    plan_id: str
    expected_revision: int = Field(gt=0, le=2_147_483_647)
    state: Literal["ACTIVE", "PAUSED"]
    human_confirmed: Literal[True]

    _uuid_fields = field_validator("request_id", "plan_id")(_Strict.canonical_uuid)

    @field_validator("expected_revision", mode="before")
    @classmethod
    def exact_revision(cls, value):
        if type(value) is not int:
            raise ValueError("strict revision required")
        return value

    @field_validator("human_confirmed", mode="before")
    @classmethod
    def exact_confirmation(cls, value):
        if value is not True:
            raise ValueError("explicit confirmation required")
        return value


__all__ = ["CreateMonitorPlanRequest", "SetMonitorPlanStateRequest", "MonitorPlanError"]
