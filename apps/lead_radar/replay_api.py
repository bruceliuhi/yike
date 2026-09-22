"""Read-only, evidence-bound end-to-end replay for one search task."""
from __future__ import annotations

from typing import Any

try:
    from .business_api import API_VERSION, BusinessApiError, _required_text
    from .storage import Store
except ImportError:
    from business_api import API_VERSION, BusinessApiError, _required_text
    from storage import Store


def get_task_replay(store: Store, workspace_id: str, task_id: Any) -> dict[str, Any]:
    normalized = _required_text(task_id, "task_id", 120)
    replay = store.task_replay(workspace_id, normalized)
    if not replay:
        raise BusinessApiError("task_not_found", "任务不存在。", 404)
    task = replay["task"] or {}
    plan = task.get("plan") or {}
    rights = []
    for source_id in plan.get("coverage", {}).get("source_ids", []):
        rights.extend(right for right in store.list_source_rights(workspace_id) if right.get("source_id") == source_id)
    return {
        "api_version": API_VERSION,
        "task_id": normalized,
        "replay": replay,
        "explainability": {
            "objective_to_criteria": True,
            "criteria_to_search_plan": bool(plan),
            "source_gate_visible": True,
            "source_rights": rights,
            "evidence_reopen_required": True,
            "human_feedback_visible": True,
            "human_action_boundary": "动作草稿可以生成和审批，但系统不会代替人工发送。",
            "external_actions_sent": False,
        },
    }
