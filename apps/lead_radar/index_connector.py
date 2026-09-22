from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

try:
    from .source_policy import classify_public_url
except ImportError:  # running server.py directly
    from source_policy import classify_public_url


MAX_ITEMS = 100
MAX_PROVIDER_LENGTH = 120
MAX_QUERY_LENGTH = 500


class IndexResultError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _required_text(value: Any, code: str, message: str, limit: int) -> str:
    result = str(value or "").strip()
    if not result:
        raise IndexResultError(code, message)
    if len(result) > limit:
        raise IndexResultError(f"{code}_too_long", message)
    return result


def _parse_retrieved_at(value: Any) -> str:
    raw = _required_text(value, "retrieved_at_required", "索引结果必须提供 retrieved_at。", 80)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IndexResultError("retrieved_at_invalid", "retrieved_at 必须是 ISO-8601 时间。") from exc
    if parsed.tzinfo is None:
        raise IndexResultError("retrieved_at_timezone_required", "retrieved_at 必须包含时区。")
    parsed = parsed.astimezone(timezone.utc)
    if parsed > datetime.now(timezone.utc):
        raise IndexResultError("retrieved_at_in_future", "retrieved_at 不能晚于当前时间。")
    return parsed.isoformat(timespec="seconds")


def _https_url(value: Any) -> str:
    url = _required_text(value, "source_url_required", "索引结果必须提供 source_url。", 2048)
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise IndexResultError("source_url_invalid", "索引结果 source_url 必须是无凭据的 HTTPS URL。")
    return url


def _position(value: Any, fallback: int) -> int:
    if value is None or value == "":
        return fallback
    try:
        position = int(value)
    except (TypeError, ValueError) as exc:
        raise IndexResultError("position_invalid", "索引 item 的 position 必须是正整数。") from exc
    if position < 1:
        raise IndexResultError("position_invalid", "索引 item 的 position 必须是正整数。")
    return position


def normalize_index_results(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Validate server-side search-index output and downgrade it to review evidence.

    The contract intentionally accepts only proof metadata and public snippets.  It
    never accepts a caller-supplied SEND_READY status, permission, or raw cookies.
    """

    if not isinstance(payload, dict):
        raise IndexResultError("payload_must_be_object", "索引结果必须是对象。")
    provider = _required_text(payload.get("provider"), "provider_required", "索引结果必须提供 provider。", MAX_PROVIDER_LENGTH)
    query = _required_text(payload.get("query"), "query_required", "索引结果必须提供 query。", MAX_QUERY_LENGTH)
    proof_ref = _required_text(payload.get("proof_ref"), "proof_ref_required", "索引结果必须绑定 proof_ref。", 240)
    retrieved_at = _parse_retrieved_at(payload.get("retrieved_at"))
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise IndexResultError("items_required", "索引结果必须提供 items 数组。")
    result_status = str(payload.get("result_status") or ("MATCHES" if raw_items else "")).strip().upper()
    if result_status not in {"MATCHES", "NO_MATCHES"}:
        raise IndexResultError("result_status_invalid", "result_status 只能是 MATCHES 或 NO_MATCHES。")
    if not raw_items and result_status != "NO_MATCHES":
        raise IndexResultError("items_required", "items 为空时必须明确声明 result_status=NO_MATCHES。")
    if raw_items and result_status == "NO_MATCHES":
        raise IndexResultError("result_status_conflict", "result_status=NO_MATCHES 时 items 必须为空。")
    if len(raw_items) > MAX_ITEMS:
        raise IndexResultError("items_limit_exceeded", f"单次索引导入最多 {MAX_ITEMS} 条。")

    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for position, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            raise IndexResultError("item_must_be_object", "索引 item 必须是对象。")
        title = _required_text(raw.get("title"), "title_required", "索引 item 必须提供 title。", 240)
        snippet = _required_text(raw.get("snippet"), "snippet_required", "索引 item 必须提供 snippet。", 1200)
        source_url = _https_url(raw.get("source_url"))
        dedup_key = (source_url.lower(), title.lower())
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        provenance = classify_public_url(source_url)
        normalized.append(
            {
                "title": title,
                "author": str(raw.get("author") or "").strip() or None,
                "published_at": str(raw.get("published_at") or "").strip() or None,
                "intent_type": str(raw.get("intent_type") or "").strip() or None,
                "industry_location": str(raw.get("industry_location") or "").strip() or None,
                "entity_name": str(raw.get("entity_name") or raw.get("company_name") or "").strip() or None,
                "entity_type": str(raw.get("entity_type") or "organization").strip() or "organization",
                "source_kind": "search_index_snippet",
                "source_url": source_url,
                "snippet": snippet,
                "evidence_level": "INDEXED_SNIPPET",
                "source_permission": "search_index_proof",
                "evidence_type": "search_index_result",
                "evidence_metadata": {
                    "provider": provider,
                    "query": query,
                    "proof_ref": proof_ref,
                    "retrieved_at": retrieved_at,
                    "result_position": _position(raw.get("position"), position),
                    "reopen_required": True,
                    "capture_method": "licensed_search_index_import",
                    "source_provenance": provenance,
                },
            }
        )
    return {
        "provider": provider,
        "query": query,
        "proof_ref": proof_ref,
        "retrieved_at": retrieved_at,
        "result_status": result_status,
    }, normalized
