from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


REQUIRED_PROOF_CHECKS = (
    "terms_and_robots",
    "rate_limit",
    "published_at",
    "url_reopen",
    "save_boundary",
    "retry_idempotency",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SourceProofError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _text(value: Any, code: str, message: str, limit: int) -> str:
    result = str(value or "").strip()
    if not result:
        raise SourceProofError(code, message)
    if len(result) > limit:
        raise SourceProofError(f"{code}_too_long", message)
    return result


def _checked_at(value: Any) -> str:
    raw = _text(value, "checked_at_required", "来源证明必须提供 checked_at。", 80)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SourceProofError("checked_at_invalid", "checked_at 必须是 ISO-8601 时间。") from exc
    if parsed.tzinfo is None:
        raise SourceProofError("checked_at_timezone_required", "checked_at 必须包含时区。")
    parsed = parsed.astimezone(timezone.utc)
    if parsed > datetime.now(timezone.utc):
        raise SourceProofError("checked_at_in_future", "checked_at 不能晚于当前时间。")
    return parsed.isoformat(timespec="seconds")


def _endpoint(value: Any) -> str:
    endpoint = _text(value, "endpoint_required", "来源证明必须提供 HTTPS endpoint。", 2048)
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise SourceProofError("endpoint_invalid", "来源证明 endpoint 必须是无凭据的 HTTPS URL。")
    return endpoint


def normalize_source_proof(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a proof binding without storing the raw external artifact."""

    if not isinstance(payload, dict):
        raise SourceProofError("payload_must_be_object", "来源证明必须是对象。")
    proof_ref = _text(payload.get("proof_ref"), "proof_ref_required", "来源证明必须提供 proof_ref。", 240)
    provider = _text(payload.get("provider"), "provider_required", "来源证明必须提供 provider。", 120)
    source_family = _text(payload.get("source_family"), "source_family_required", "来源证明必须提供 source_family。", 80)
    endpoint = _endpoint(payload.get("endpoint"))
    artifact_sha256 = str(payload.get("artifact_sha256") or "").strip().lower()
    if not SHA256_RE.fullmatch(artifact_sha256):
        raise SourceProofError("artifact_sha256_invalid", "来源证明 artifact_sha256 必须是 64 位小写 SHA-256。")
    checked_at = _checked_at(payload.get("checked_at"))
    raw_checks = payload.get("checks")
    if not isinstance(raw_checks, dict):
        raise SourceProofError("checks_required", "来源证明必须提供 checks 对象。")
    checks = {name: raw_checks.get(name) is True for name in REQUIRED_PROOF_CHECKS}
    missing = [name for name, passed in checks.items() if not passed]
    if missing:
        raise SourceProofError("proof_gates_incomplete", f"来源证明未通过全部 proof gates：{', '.join(missing)}。")
    return {
        "proof_ref": proof_ref,
        "provider": provider,
        "source_family": source_family,
        "endpoint": endpoint,
        "artifact_sha256": artifact_sha256,
        "checked_at": checked_at,
        "checks": checks,
    }
