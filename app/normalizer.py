from datetime import UTC, datetime
import hashlib
import json
from typing import Any, Mapping


class PlatformResponseChanged(ValueError):
    pass


def require_text(record: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    raise PlatformResponseChanged(f"PLATFORM_RESPONSE_CHANGED: missing {keys[0]}")


def optional_text(record: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def normalize_time(value: object | None) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
    text = str(value).strip()
    if text.isdigit():
        return normalize_time(int(text))
    return text


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def raw_sha256(record: Mapping[str, Any]) -> str:
    provided = optional_text(record, "_raw_sha256")
    if provided:
        return provided
    encoded = json.dumps(
        record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return sha256_text(encoded)
