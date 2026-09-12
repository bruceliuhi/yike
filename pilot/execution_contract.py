"""Strict public execution requests. Signatures and server authority are separate."""
from __future__ import annotations

import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator, model_serializer

MAX_VERSION = 2147483647
Platform = Literal['XIAOHONGSHU', 'DOUYIN', 'BILIBILI', 'ZHIHU', 'PUBLIC_WEB']


class ExecutionRuntimeError(Exception):
    def __init__(self, code: str, status: int = 409):
        super().__init__(code)
        self.code, self.status = code, status


def canonical_uuid(value: str) -> str:
    try:
        if type(value) is not str or len(value) != 36 or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ExecutionRuntimeError('invalid_request', 422) from None
    return value


class _Frozen(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra='forbid',
        hide_input_in_errors=True, revalidate_instances='always')


class ExecutionTarget(_Frozen):
    platform: Platform
    access_mode: Literal['PLATFORM_ACCOUNT', 'PUBLIC_ANONYMOUS']
    connection_id: str | None
    connection_version: int | None = Field(default=None, ge=1, le=MAX_VERSION)

    @field_validator('connection_id')
    @classmethod
    def uuid(cls, value):
        return canonical_uuid(value) if value is not None else None

    @model_validator(mode='after')
    def mode(self):
        if self.access_mode == 'PLATFORM_ACCOUNT':
            valid = self.connection_id is not None and self.connection_version is not None
        else:
            valid = self.platform == 'PUBLIC_WEB' and self.connection_id is None and self.connection_version is None
        if not valid:
            raise ExecutionRuntimeError('invalid_request', 422)
        return self


class ExecutionOperation(_Frozen):
    schema_version: Literal['execution-runtime-v1']
    request_id: str
    operation: Literal['START', 'CLAIM', 'RENEW', 'CANCEL', 'FINISH']
    device_id: str
    credential_version: int = Field(ge=1, le=MAX_VERSION)
    profile_version_id: str | None = None
    strategy_version_id: str | None = None
    configuration_sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    targets: tuple[ExecutionTarget, ...] | None = Field(default=None, min_length=1, max_length=5)
    task_id: str | None = None
    platform_run_id: str | None = None
    lease_id: str | None = None
    execution_generation: int | None = Field(default=None, ge=1, le=MAX_VERSION)
    upload_request_id: str | None = None
    public_sampling_version: int | None = None
    native_progress_version: int | None = None

    @model_serializer(mode='wrap')
    def compatible_serialization(self, handler):
        value = handler(self)
        if self.operation != 'FINISH':
            value.pop('upload_request_id', None)
        if self.public_sampling_version is None:
            value.pop('public_sampling_version', None)
        if self.native_progress_version is None:
            value.pop('native_progress_version', None)
        return value

    @field_validator('public_sampling_version', 'native_progress_version', mode='before')
    @classmethod
    def sampling_version(cls, value):
        if value is not None and (type(value) is not int or value != 1):
            raise ExecutionRuntimeError('invalid_request', 422)
        return value

    @field_validator('targets', mode='before')
    @classmethod
    def freeze_targets(cls, value):
        return tuple(value) if type(value) is list else value

    @field_validator('request_id', 'device_id')
    @classmethod
    def uuid(cls, value):
        return canonical_uuid(value)

    @field_validator('profile_version_id', 'strategy_version_id', 'task_id', 'platform_run_id', 'lease_id', 'upload_request_id')
    @classmethod
    def opaque(cls, value):
        if value is not None and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value):
            raise ExecutionRuntimeError('invalid_request', 422)
        return value

    @model_validator(mode='after')
    def shape(self):
        applicable = {
            'START': {'profile_version_id', 'strategy_version_id', 'configuration_sha256', 'targets'},
            'CLAIM': {'task_id', 'platform_run_id'},
            'RENEW': {'task_id', 'platform_run_id', 'lease_id', 'execution_generation'},
            'FINISH': {'task_id', 'platform_run_id', 'lease_id', 'execution_generation', 'upload_request_id'},
            'CANCEL': {'task_id'},
        }[self.operation]
        conditional = {'profile_version_id', 'strategy_version_id', 'configuration_sha256', 'targets',
                       'task_id', 'platform_run_id', 'lease_id', 'execution_generation', 'upload_request_id'}
        if any((getattr(self, key) is not None) != (key in applicable) for key in conditional):
            raise ExecutionRuntimeError('invalid_request', 422)
        if ('public_sampling_version' in self.__pydantic_fields_set__
                and self.public_sampling_version is None):
            raise ExecutionRuntimeError('invalid_request', 422)
        if ('native_progress_version' in self.__pydantic_fields_set__
                and self.native_progress_version is None):
            raise ExecutionRuntimeError('invalid_request', 422)
        if self.public_sampling_version is not None and self.operation != 'CLAIM':
            raise ExecutionRuntimeError('invalid_request', 422)
        if self.native_progress_version is not None and self.operation != 'CLAIM':
            raise ExecutionRuntimeError('invalid_request', 422)
        if self.public_sampling_version is not None and self.native_progress_version is not None:
            raise ExecutionRuntimeError('invalid_request', 422)
        if self.targets and len({target.platform for target in self.targets}) != len(self.targets):
            raise ExecutionRuntimeError('invalid_request', 422)
        return self
