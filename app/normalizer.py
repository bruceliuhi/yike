from datetime import UTC, datetime
import hashlib
import json
import re
from typing import Any, Mapping


class PlatformResponseChanged(ValueError):
    pass


_CANONICAL_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def require_text(record: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is None or value == "":
            continue
        if not isinstance(value, str):
            raise PlatformResponseChanged(
                f"PLATFORM_RESPONSE_CHANGED: invalid {key}"
            )
        if value.strip():
            return value.strip()
    raise PlatformResponseChanged(f"PLATFORM_RESPONSE_CHANGED: missing {keys[0]}")


def optional_text(record: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if value is None or value == "":
            continue
        if not isinstance(value, str):
            raise PlatformResponseChanged(
                f"PLATFORM_RESPONSE_CHANGED: invalid {key}"
            )
        if value.strip():
            return value.strip()
    return None


def first_present(record: Mapping[str, Any], *keys: str) -> object | None:
    for key in keys:
        if key in record and record[key] is not None and record[key] != "":
            return record[key]
    return None


def normalize_time(value: object | None) -> str | None:
    if value is None or value == "":
        return None
    if type(value) is int:
        try:
            return datetime.fromtimestamp(value, UTC).isoformat(
                timespec="seconds"
            ).replace("+00:00", "Z")
        except (OverflowError, OSError, ValueError) as error:
            raise PlatformResponseChanged(
                "PLATFORM_RESPONSE_CHANGED: invalid timestamp"
            ) from error
    if isinstance(value, str) and _CANONICAL_UTC.fullmatch(value):
        try:
            datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as error:
            raise PlatformResponseChanged(
                "PLATFORM_RESPONSE_CHANGED: invalid timestamp"
            ) from error
        return value
    raise PlatformResponseChanged("PLATFORM_RESPONSE_CHANGED: invalid timestamp")


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
