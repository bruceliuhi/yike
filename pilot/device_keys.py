"""Strict public device-proof protocol. No private keys or bearer grants."""
from __future__ import annotations

import base64
from typing import Literal
from uuid import UUID

from nacl.bindings import crypto_core_ed25519_is_valid_point
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DeviceKeyError(Exception):
    def __init__(self, code: str, status: int):
        super().__init__(code)
        self.code = code
        self.status = status


def uuid_string(value: str) -> str:
    try:
        if type(value) is not str or len(value) != 36 or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise DeviceKeyError("invalid_request", 422) from None
    return value


def decode_canonical(value: str, size: int) -> bytes:
    try:
        if type(value) is not str or len(value) != (size * 8 + 5) // 6:
            raise ValueError
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        if len(decoded) != size or base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != value:
            raise ValueError
        return decoded
    except (ValueError, TypeError, UnicodeError):
        raise DeviceKeyError("invalid_request", 422) from None


class ChallengeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(min_length=36, max_length=36)
    operation: Literal["BIND", "PROVE", "ROTATE"]
    expected_credential_version: int = Field(ge=0, le=2147483646)
    public_key: str | None = Field(max_length=43)

    @field_validator("request_id")
    @classmethod
    def valid_id(cls, value):
        return uuid_string(value)

    @field_validator("public_key")
    @classmethod
    def valid_key(cls, value):
        if value is not None:
            if not crypto_core_ed25519_is_valid_point(decode_canonical(value, 32)):
                raise DeviceKeyError("invalid_request", 422)
        return value

    @model_validator(mode="after")
    def valid_operation(self):
        if (self.operation == "PROVE") != (self.public_key is None):
            raise DeviceKeyError("invalid_request", 422)
        if (self.operation == "BIND") != (self.expected_credential_version == 0):
            raise DeviceKeyError("invalid_request", 422)
        return self


class CompletionProof(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    signature: str = Field(min_length=86, max_length=86, repr=False)
    previous_signature: str | None = Field(default=None, min_length=86, max_length=86, repr=False)

    @field_validator("signature", "previous_signature")
    @classmethod
    def valid_signature(cls, value):
        if value is not None:
            decode_canonical(value, 64)
        return value


def verify_signature(public_key: str, signature: str, payload: str) -> None:
    try:
        public = decode_canonical(public_key, 32)
        if not crypto_core_ed25519_is_valid_point(public):
            raise DeviceKeyError("invalid_proof", 400)
        VerifyKey(public).verify(payload.encode("utf-8"), decode_canonical(signature, 64))
    except (BadSignatureError, ValueError, DeviceKeyError):
        raise DeviceKeyError("invalid_proof", 400) from None
