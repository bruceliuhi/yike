"""Validation and orchestration for durable Lead Radar schedules."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

try:
    from .business_api import (
        API_VERSION,
        BusinessApiError,
        MAX_OBJECTIVE_LENGTH,
        _reject_credential_fields,
        _required_text,
    )
    from .domain import compile_intent, now_iso
    from .planner import build_search_plan
    from .storage import Store
except ImportError:  # running the module directly
    from business_api import API_VERSION, BusinessApiError, MAX_OBJECTIVE_LENGTH, _reject_credential_fields, _required_text
    from domain import compile_intent, now_iso
    from planner import build_search_plan
    from storage import Store


MIN_INTERVAL_MINUTES = 5
MAX_INTERVAL_MINUTES = 43_200
MAX_SCHEDULE_LIMIT = 500
MAX_BUDGET = 1_000_000
FAILURE_POLICIES = {"PAUSE", "CONTINUE"}
APPROVAL_POLICIES = {"MANUAL_REVIEW", "DRAFT_ONLY"}


def _integer(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise BusinessApiError(f"{field}_out_of_range", f"{field} 必须是 {minimum} 到 {maximum} 的整数。")
    return value


def _optional_integer(value: Any, field: str, minimum: int, maximum: int) -> int | None:
    if value is None:
        return None
    return _integer(value, field, minimum, maximum)


def _normalise_start_at(value: Any) -> str:
    if value in (None, ""):
        return now_iso()
    if not isinstance(value, str):
        raise BusinessApiError("start_at_invalid", "start_at 必须是带时区的 ISO-8601 时间。")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise BusinessApiError("start_at_invalid", "start_at 必须是带时区的 ISO-8601 时间。") from exc
    if parsed.tzinfo is None:
        raise BusinessApiError("start_at_timezone_required", "start_at 必须包含时区。")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def _common_schedule_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise BusinessApiError("body_must_be_object", "请求体必须是对象。")
    _reject_credential_fields(payload)
    objective = _required_text(payload.get("objective"), "objective", MAX_OBJECTIVE_LENGTH)
    criteria = payload.get("criteria")
    if criteria is not None and not isinstance(criteria, dict):
        raise BusinessApiError("criteria_must_be_object", "criteria 必须是对象。")
    requested_limit = _integer(payload.get("requested_limit", 10), "requested_limit", 1, MAX_SCHEDULE_LIMIT)
    interval_minutes = _integer(payload.get("interval_minutes", 60), "interval_minutes", MIN_INTERVAL_MINUTES, MAX_INTERVAL_MINUTES)
    budget_per_run = _integer(payload.get("max_credits_per_run", 100), "max_credits_per_run", 1, MAX_BUDGET)
    max_total = _optional_integer(payload.get("max_total_credits"), "max_total_credits", budget_per_run, MAX_BUDGET)
    min_new_results = _integer(payload.get("min_new_results", 0), "min_new_results", 0, requested_limit)
    failure_policy = str(payload.get("failure_policy", "PAUSE")).strip().upper()
    if failure_policy not in FAILURE_POLICIES:
        raise BusinessApiError("failure_policy_invalid", "failure_policy 只支持 PAUSE 或 CONTINUE。")
    approval_policy = str(payload.get("approval_policy", "MANUAL_REVIEW")).strip().upper()
    if approval_policy not in APPROVAL_POLICIES:
        raise BusinessApiError("approval_policy_invalid", "approval_policy 只支持 MANUAL_REVIEW 或 DRAFT_ONLY。")
    created_by = _required_text(payload.get("created_by", "operator"), "created_by", 120)
    return {
        "objective": objective,
        "criteria": compile_intent(objective, criteria),
        "requested_limit": requested_limit,
        "interval_minutes": interval_minutes,
        "max_credits_per_run": budget_per_run,
        "max_total_credits": max_total,
        "min_new_results": min_new_results,
        "failure_policy": failure_policy,
        "approval_policy": approval_policy,
        "next_run_at": _normalise_start_at(payload.get("start_at")),
        "created_by": created_by,
    }


def create_schedule(store: Store, workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    values = _common_schedule_payload(payload)
    schedule = store.create_scheduled_task(workspace_id, **values)
    if not schedule:
        raise BusinessApiError("workspace_not_found", "工作区不存在。", 404)
    plan = build_search_plan(values["criteria"], values["requested_limit"])
    return {
        "api_version": API_VERSION,
        "schedule": schedule,
        "plan": plan,
        "execution": {
            "background_worker": False,
            "next_step": "到期后调用 trigger；来源 worker 仍需通过生产门禁。",
            "external_search_performed": False,
            "messages_sent": False,
        },
    }


def list_schedules(store: Store, workspace_id: str) -> dict[str, Any]:
    return {"api_version": API_VERSION, "items": store.list_scheduled_tasks(workspace_id)}


def get_schedule(store: Store, workspace_id: str, schedule_id: Any) -> dict[str, Any]:
    schedule_id = _required_text(schedule_id, "schedule_id", 120)
    schedule = store.get_scheduled_task(schedule_id, workspace_id)
    if not schedule:
        raise BusinessApiError("schedule_not_found", "调度任务不存在。", 404)
    return {"api_version": API_VERSION, "schedule": schedule}


def control_schedule(store: Store, workspace_id: str, schedule_id: Any, action: str, actor: Any = "operator") -> dict[str, Any]:
    schedule_id = _required_text(schedule_id, "schedule_id", 120)
    actor = _required_text(actor, "actor", 120)
    try:
        schedule = store.control_scheduled_task(schedule_id, workspace_id, action, actor)
    except ValueError as exc:
        raise BusinessApiError("schedule_action_not_allowed", str(exc)) from exc
    if not schedule:
        raise BusinessApiError("schedule_not_found", "调度任务不存在。", 404)
    return {"api_version": API_VERSION, "schedule": schedule}


def trigger_schedule(store: Store, workspace_id: str, schedule_id: Any, actor: Any = "scheduler", scheduled_for: Any = None) -> dict[str, Any]:
    schedule_id = _required_text(schedule_id, "schedule_id", 120)
    actor = _required_text(actor, "actor", 120)
    schedule = store.get_scheduled_task(schedule_id, workspace_id)
    if not schedule:
        raise BusinessApiError("schedule_not_found", "调度任务不存在。", 404)
    plan = build_search_plan(schedule["criteria"], int(schedule["requested_limit"]))
    result = store.trigger_scheduled_task(schedule_id, workspace_id, plan, actor, _normalise_start_at(scheduled_for) if scheduled_for else None)
    if result is None:
        raise BusinessApiError("schedule_not_found", "调度任务不存在。", 404)
    return {"api_version": API_VERSION, **result}
