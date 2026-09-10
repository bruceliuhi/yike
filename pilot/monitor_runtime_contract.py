"""Strict device heartbeat contract for durable monitor occurrences."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pilot.execution_contract import ExecutionRuntimeError, ExecutionTarget, MAX_VERSION, canonical_uuid


class MonitorPulseRequest(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid",
                              hide_input_in_errors=True, revalidate_instances="always")
    schema_version: Literal["monitor-runtime-v1"]
    plan_id: str
    device_id: str
    monitor_session_id: str
    credential_version: int = Field(ge=1, le=MAX_VERSION)
    can_start: bool = True
    targets: tuple[ExecutionTarget, ...] = Field(min_length=1, max_length=5)

    @field_validator("targets", mode="before")
    @classmethod
    def freeze_targets(cls, value):
        return tuple(value) if type(value) is list else value

    @field_validator("plan_id", "device_id", "monitor_session_id")
    @classmethod
    def uuids(cls, value):
        return canonical_uuid(value)

    @model_validator(mode="after")
    def unique_platforms(self):
        if len({target.platform for target in self.targets}) != len(self.targets):
            raise ExecutionRuntimeError("invalid_request", 422)
        return self


__all__ = ["MonitorPulseRequest"]
