"""Stable business operations for the Lead Radar HTTP and MCP surfaces.

The web UI and the developer surfaces share these operations so that they do not
quietly grow different validation, workspace boundaries, or result semantics.
These functions are local ledger operations. They do not search platforms,
perform external enrichment, or send messages.
"""
from __future__ import annotations

from typing import Any

try:
    from .domain import compile_intent
    from .planner import build_search_plan
    from .storage import Store
    from .templates import get_task_template
except ImportError:  # running the module directly during local inspection
    from domain import compile_intent
    from planner import build_search_plan
    from storage import Store
    from templates import get_task_template


API_VERSION = "2026-09-23"
MAX_OBJECTIVE_LENGTH = 2_000
MAX_IDEMPOTENCY_KEY_LENGTH = 200
MAX_PAGE_SIZE = 100
VALID_RESULT_STATUSES = {
    "REVIEW",
    "OBSERVE",
    "SEND_READY",
    "EXCLUDE",
    "CONTACTED",
    "DEFERRED",
    "HANDOFF",
    "DUPLICATE",
    "DO_NOT_CONTACT",
}
FORBIDDEN_CREDENTIAL_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "cookie",
    "cookies",
    "password",
    "passwd",
    "refresh_token",
    "session",
    "token",
}


class BusinessApiError(ValueError):
    """A safe, user-facing error that does not echo credential-bearing input."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _required_text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BusinessApiError(f"{field}_required", f"{field} 必填。")
    value = value.strip()
    if len(value) > maximum:
        raise BusinessApiError(f"{field}_too_long", f"{field} 超出长度限制。")
    return value


def _reject_credential_fields(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).strip().lower() in FORBIDDEN_CREDENTIAL_KEYS:
                raise BusinessApiError(
                    "credential_fields_not_allowed",
                    "业务 API 不接受 Cookie、密码或第三方 Token；请使用服务端已登记的来源证明。",
                )
            _reject_credential_fields(child)
    elif isinstance(value, list):
        for child in value:
            _reject_credential_fields(child)


def _workspace_task(store: Store, workspace_id: str, task_id: Any) -> dict[str, Any]:
    task_id = _required_text(task_id, "task_id", 120)
    task = store.get_task(task_id)
    if not task or task.get("workspace_id") != workspace_id:
        raise BusinessApiError("task_not_found", "任务不存在。", 404)
    return task


def create_search_task(
    store: Store,
    workspace_id: str,
    payload: dict[str, Any],
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Create an inspectable task and deterministic search plan."""

    if not isinstance(payload, dict):
        raise BusinessApiError("body_must_be_object", "请求体必须是对象。")
    _reject_credential_fields(payload)
    template_id = payload.get("template_id")
    if template_id is not None:
        template_id = _required_text(template_id, "template_id", 120)
        template = get_task_template(template_id, "zh-CN")
        if not template:
            raise BusinessApiError("task_template_not_found", "任务模板不存在。")
    else:
        template = None
    objective = _required_text(payload.get("objective") or (template or {}).get("objective"), "objective", MAX_OBJECTIVE_LENGTH)
    requested_limit = payload.get("requested_limit", 10)
    if isinstance(requested_limit, bool) or not isinstance(requested_limit, int) or not 1 <= requested_limit <= 500:
        raise BusinessApiError("requested_limit_out_of_range", "requested_limit 必须是 1 到 500 的整数。")
    criteria = payload.get("criteria") or (template or {}).get("criteria")
    if criteria is not None and not isinstance(criteria, dict):
        raise BusinessApiError("criteria_must_be_object", "criteria 必须是对象。")
    profile_id = payload.get("profile_id")
    if profile_id is not None:
        profile_id = _required_text(profile_id, "profile_id", 120)
    key = idempotency_key or payload.get("idempotency_key")
    if key is not None:
        key = _required_text(key, "idempotency_key", MAX_IDEMPOTENCY_KEY_LENGTH)

    compiled = compile_intent(objective, criteria)
    if template_id:
        compiled["template_id"] = template_id
    plan = build_search_plan(compiled, requested_limit)
    quoted_max = plan["cost_estimate"].get("max_credits")
    estimated_credits = 0 if quoted_max is None else int(quoted_max)
    task = store.create_task(
        workspace_id,
        profile_id,
        objective,
        compiled,
        requested_limit,
        estimated_credits,
        key,
        plan,
    )
    return {
        "api_version": API_VERSION,
        "task": task,
        "execution": {
            "status": plan["execution"]["status"],
            "can_start": plan["execution"]["can_start"],
            "runnable_sources": plan["execution"]["runnable_sources"],
            "blocked_sources": plan["execution"]["blocked_sources"],
        },
        "external_actions": {
            "search_performed": False,
            "messages_sent": False,
        },
    }


def get_search_status(store: Store, workspace_id: str, task_id: Any) -> dict[str, Any]:
    task = _workspace_task(store, workspace_id, task_id)
    return {
        "api_version": API_VERSION,
        "task_id": task["id"],
        "status": task["status"],
        "task": task,
        "latest_run": (task.get("runs") or [None])[0],
        "external_actions": {
            "search_performed": any(run.get("status") == "COMPLETED" for run in task.get("runs", [])),
            "messages_sent": False,
        },
    }


def _bounded_int(value: Any, field: str, default: int, minimum: int, maximum: int) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise BusinessApiError(f"{field}_invalid", f"{field} 必须是整数。") from exc
    if parsed < minimum or parsed > maximum:
        raise BusinessApiError(f"{field}_out_of_range", f"{field} 超出允许范围。")
    return parsed


def fetch_search_results(
    store: Store,
    workspace_id: str,
    task_id: Any,
    *,
    limit: Any = 20,
    offset: Any = 0,
    status: Any = None,
) -> dict[str, Any]:
    task = _workspace_task(store, workspace_id, task_id)
    page_size = _bounded_int(limit, "limit", 20, 1, MAX_PAGE_SIZE)
    page_offset = _bounded_int(offset, "offset", 0, 0, 1_000_000)
    result_status = None if status in (None, "") else _required_text(status, "status", 40).upper()
    if result_status and result_status not in VALID_RESULT_STATUSES:
        raise BusinessApiError("status_invalid", "status 不是受支持的机会状态。")
    all_items = [
        item
        for item in store.list_opportunities(workspace_id, result_status)
        if item.get("task_id") == task["id"]
    ]
    page = all_items[page_offset : page_offset + page_size]
    next_offset = page_offset + page_size if page_offset + page_size < len(all_items) else None
    return {
        "api_version": API_VERSION,
        "task_id": task["id"],
        "items": page,
        "pagination": {
            "limit": page_size,
            "offset": page_offset,
            "total": len(all_items),
            "has_more": next_offset is not None,
            "next_offset": next_offset,
        },
        "result_contract": {
            "evidence_reopen_required": True,
            "contact_permission": "manual_confirmation_required",
            "messages_sent": False,
        },
    }


def enrich_entity(store: Store, workspace_id: str, entity_id: Any) -> dict[str, Any]:
    entity_id = _required_text(entity_id, "entity_id", 120)
    entity = store.get_entity(entity_id)
    if not entity or entity.get("workspace_id") != workspace_id:
        raise BusinessApiError("entity_not_found", "实体不存在。", 404)
    return {
        "api_version": API_VERSION,
        "entity": entity,
        "enrichment": {
            "status": "LOCAL_ONLY",
            "source": "lead_radar_evidence_ledger",
            "external_lookup_performed": False,
            "contact_data_returned": False,
            "next_action": "通过已登记且通过生产门禁的来源补充企业背景，再由人工复核。",
        },
    }
