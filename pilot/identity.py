from __future__ import annotations

import json
import re


class IdentityValidationError(ValueError):
    """Raised when a device, connection or execution event is unsafe."""


SUPPORTED_PLATFORMS = frozenset({"XIAOHONGSHU", "DOUYIN", "BILIBILI", "ZHIHU", "PUBLIC_WEB"})
SUPPORTED_EVENT_TYPES = frozenset({
    "COLLECTION_STARTED",
    "COLLECTION_PROGRESS",
    "COLLECTION_SUCCEEDED",
    "COLLECTION_FAILED",
    "COLLECTION_CANCELLED",
    "CONNECTION_EXPIRED",
    "CONNECTION_REVOKED",
})
_OPAQUE_REF = re.compile(r"^vault://[A-Za-z0-9._~:/-]{1,512}$")
_SECRET_MARKERS = ("cookie=", "token=", "password=", "secret=", "authorization:")
_SECRET_KEYS = {"cookie", "token", "password", "secret", "authorization", "profile", "qr"}


def _text(value: str, field: str, limit: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise IdentityValidationError(f"{field} is invalid")
    return value.strip()


def validate_connection_input(platform: str, device_id: str, account_public_id: str, session_ref: str) -> dict[str, str]:
    platform = _text(platform, "platform", 32).upper()
    if platform not in SUPPORTED_PLATFORMS:
        raise IdentityValidationError("unsupported platform")
    device_id = _text(device_id, "device_id")
    account_public_id = _text(account_public_id, "account_public_id")
    session_ref = _text(session_ref, "session_ref", 512)
    if not _OPAQUE_REF.fullmatch(session_ref) or any(marker in session_ref.lower() for marker in _SECRET_MARKERS):
        raise IdentityValidationError("session_ref must be an opaque vault reference")
    return {
        "platform": platform,
        "device_id": device_id,
        "account_public_id": account_public_id,
        "session_ref": session_ref,
    }


def validate_execution_event(event_type: str, execution_generation: int, payload: dict) -> dict:
    event_type = _text(event_type, "event_type", 64).upper()
    if event_type not in SUPPORTED_EVENT_TYPES:
        raise IdentityValidationError("unsupported event_type")
    if isinstance(execution_generation, bool) or not isinstance(execution_generation, int) or execution_generation < 1:
        raise IdentityValidationError("execution_generation must be positive")
    if not isinstance(payload, dict):
        raise IdentityValidationError("payload must be an object")
    def has_secret_key(value: object) -> bool:
        if isinstance(value, dict):
            if any(str(key).lower() in _SECRET_KEYS for key in value):
                return True
            return any(has_secret_key(item) for item in value.values())
        if isinstance(value, list):
            return any(has_secret_key(item) for item in value)
        return False
    if has_secret_key(payload):
        raise IdentityValidationError("payload contains a protected field")
    try:
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise IdentityValidationError("payload must be JSON serializable") from error
    return {"event_type": event_type, "execution_generation": execution_generation, "payload": payload}
