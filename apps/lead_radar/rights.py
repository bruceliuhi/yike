"""Validation contract for source data rights and retention boundaries."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


ACCESS_METHODS = {"OFFICIAL_API", "CUSTOMER_AUTH", "LICENSED_INDEX", "PUBLIC_URL_USER_SUBMITTED", "MANUAL"}
RIGHT_STATUSES = {"DRAFT", "PENDING"}
OPERATIONS = {"SEARCH", "REOPEN", "STORE_EXCERPT", "STORE_ORIGINAL", "WRITE_BACK", "EXPORT"}


class SourceRightError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _text(value: Any, field: str, limit: int, required: bool = True) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise SourceRightError(f"{field}_required", f"{field} 必填。")
    if len(text) > limit:
        raise SourceRightError(f"{field}_too_long", f"{field} 超出长度限制。")
    return text


def _https_url(value: Any, field: str, required: bool = False) -> str | None:
    text = _text(value, field, 2048, required)
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SourceRightError(f"{field}_invalid", f"{field} 必须是无凭据、无查询参数的 HTTPS URL。")
    return text


def _string_list(value: Any, field: str, allowed: set[str] | None = None) -> list[str]:
    if not isinstance(value, list) or not value:
        raise SourceRightError(f"{field}_required", f"{field} 必须是非空数组。")
    result: list[str] = []
    for item in value:
        text = _text(item, field, 120)
        if allowed is not None and text not in allowed:
            raise SourceRightError(f"{field}_invalid", f"{field} 包含不受支持的值。")
        if text not in result:
            result.append(text)
    return result


def normalize_source_right(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SourceRightError("payload_must_be_object", "数据权利记录必须是对象。")
    source_id = _text(payload.get("source_id"), "source_id", 120)
    provider = _text(payload.get("provider"), "provider", 160)
    source_family = _text(payload.get("source_family"), "source_family", 120)
    access_method = _text(payload.get("access_method"), "access_method", 40).upper()
    if access_method not in ACCESS_METHODS:
        raise SourceRightError("access_method_invalid", "access_method 不受支持。")
    status = str(payload.get("status", "PENDING")).strip().upper()
    if status not in RIGHT_STATUSES:
        raise SourceRightError("status_invalid", "新建数据权利记录只能是 DRAFT 或 PENDING。")
    operations = _string_list(payload.get("allowed_operations"), "allowed_operations", OPERATIONS)
    fields = _string_list(payload.get("allowed_fields"), "allowed_fields")
    terms_url = _https_url(payload.get("terms_url"), "terms_url", required=False)
    privacy_url = _https_url(payload.get("privacy_url"), "privacy_url", required=False)
    proof_ref = _text(payload.get("proof_ref"), "proof_ref", 240, required=False)
    retention = payload.get("retention_days", 30)
    rate_limit = payload.get("rate_limit_per_minute", 60)
    if isinstance(retention, bool) or not isinstance(retention, int) or not 1 <= retention <= 3650:
        raise SourceRightError("retention_days_invalid", "retention_days 必须是 1 到 3650 的整数。")
    if isinstance(rate_limit, bool) or not isinstance(rate_limit, int) or not 1 <= rate_limit <= 1_000_000:
        raise SourceRightError("rate_limit_invalid", "rate_limit_per_minute 必须是正整数。")
    store_original = payload.get("store_original", False)
    can_search = payload.get("can_search", "SEARCH" in operations)
    can_write_back = payload.get("can_write_back", "WRITE_BACK" in operations)
    if not isinstance(store_original, bool) or not isinstance(can_search, bool) or not isinstance(can_write_back, bool):
        raise SourceRightError("permission_flags_invalid", "store_original、can_search、can_write_back 必须是布尔值。")
    if store_original and "STORE_ORIGINAL" not in operations:
        raise SourceRightError("store_original_operation_required", "允许保存原文时必须声明 STORE_ORIGINAL。")
    if can_search and "SEARCH" not in operations:
        raise SourceRightError("search_operation_required", "can_search=true 时必须声明 SEARCH。")
    if can_write_back and "WRITE_BACK" not in operations:
        raise SourceRightError("write_back_operation_required", "can_write_back=true 时必须声明 WRITE_BACK。")
    return {
        "source_id": source_id,
        "provider": provider,
        "source_family": source_family,
        "access_method": access_method,
        "status": status,
        "proof_ref": proof_ref or None,
        "terms_url": terms_url,
        "privacy_url": privacy_url,
        "allowed_operations": operations,
        "allowed_fields": fields,
        "store_original": store_original,
        "retention_days": retention,
        "rate_limit_per_minute": rate_limit,
        "can_search": can_search,
        "can_write_back": can_write_back,
        "notes": _text(payload.get("notes"), "notes", 4000, required=False) or None,
    }
