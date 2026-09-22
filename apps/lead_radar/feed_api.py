"""Safe Feed/Monitor projections over evidence-backed Lead Radar events."""
from __future__ import annotations

from typing import Any

try:
    from .business_api import API_VERSION, BusinessApiError, _required_text
    from .storage import FEED_EVENT_STATUSES, FEED_EVENT_TYPES, Store
except ImportError:  # running the module directly
    from business_api import API_VERSION, BusinessApiError, _required_text
    from storage import FEED_EVENT_STATUSES, FEED_EVENT_TYPES, Store


def _page_value(value: Any, field: str, default: int, maximum: int) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise BusinessApiError(f"{field}_invalid", f"{field} 必须是整数。") from exc
    if parsed < 0 or parsed > maximum or (field == "limit" and parsed == 0):
        raise BusinessApiError(f"{field}_out_of_range", f"{field} 超出允许范围。")
    return parsed


def list_feed(
    store: Store,
    workspace_id: str,
    *,
    event_type: Any = None,
    status: Any = None,
    since: Any = None,
    limit: Any = 50,
    offset: Any = 0,
) -> dict[str, Any]:
    normalized_type = None if event_type in (None, "") else _required_text(event_type, "event_type", 40).upper()
    if normalized_type and normalized_type not in FEED_EVENT_TYPES:
        raise BusinessApiError("feed_event_type_invalid", "event_type 不是受支持的 Feed 类型。")
    normalized_status = None if status in (None, "") else _required_text(status, "status", 20).upper()
    if normalized_status and normalized_status not in FEED_EVENT_STATUSES:
        raise BusinessApiError("feed_event_status_invalid", "status 不是受支持的 Feed 状态。")
    normalized_since = None if since in (None, "") else _required_text(since, "since", 80)
    try:
        page = store.list_feed_events(
            workspace_id,
            event_type=normalized_type,
            status=normalized_status,
            since=normalized_since,
            limit=_page_value(limit, "limit", 50, 100),
            offset=_page_value(offset, "offset", 0, 1_000_000),
        )
    except ValueError as exc:
        raise BusinessApiError("feed_query_invalid", str(exc)) from exc
    return {
        "api_version": API_VERSION,
        "items": page["items"],
        "pagination": page["pagination"],
        "contract": {
            "evidence_bound": True,
            "source_reopen_required": True,
            "contact_permission": "manual_confirmation_required",
            "messages_sent": False,
        },
    }


def get_feed_event(store: Store, workspace_id: str, event_id: Any) -> dict[str, Any]:
    event_id = _required_text(event_id, "event_id", 120)
    event = store.get_feed_event(event_id, workspace_id)
    if not event:
        raise BusinessApiError("feed_event_not_found", "Feed 事件不存在。", 404)
    return {"api_version": API_VERSION, "event": event}


def review_feed_event(
    store: Store,
    workspace_id: str,
    event_id: Any,
    payload: dict[str, Any],
) -> dict[str, Any]:
    event_id = _required_text(event_id, "event_id", 120)
    if not isinstance(payload, dict):
        raise BusinessApiError("body_must_be_object", "请求体必须是对象。")
    status = _required_text(payload.get("status"), "status", 20).upper()
    if status not in FEED_EVENT_STATUSES - {"NEW"}:
        raise BusinessApiError("feed_review_status_invalid", "Feed 复核状态只支持 REVIEWED 或 DISMISSED。")
    actor = _required_text(payload.get("actor", "operator"), "actor", 120)
    note = str(payload.get("note", "") or "").strip()
    if len(note) > 1000:
        raise BusinessApiError("note_too_long", "note 超出长度限制。")
    try:
        event = store.review_feed_event(event_id, workspace_id, status, actor, note)
    except ValueError as exc:
        raise BusinessApiError("feed_review_invalid", str(exc)) from exc
    if not event:
        raise BusinessApiError("feed_event_not_found", "Feed 事件不存在。", 404)
    return {"api_version": API_VERSION, "event": event}
