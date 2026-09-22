"""Evidence-bound research briefs assembled from one local search task."""
from __future__ import annotations

from collections import Counter
from typing import Any

try:
    from .business_api import API_VERSION, BusinessApiError, _required_text
    from .storage import Store
except ImportError:
    from business_api import API_VERSION, BusinessApiError, _required_text
    from storage import Store


def get_research_brief(store: Store, workspace_id: str, task_id: Any) -> dict[str, Any]:
    normalized = _required_text(task_id, "task_id", 120)
    replay = store.task_replay(workspace_id, normalized)
    if not replay:
        raise BusinessApiError("task_not_found", "任务不存在。", 404)
    task = replay.get("task") or {}
    candidates = [item for item in replay.get("candidates", []) if item]
    status_counts = Counter(str(item.get("status") or "UNKNOWN") for item in candidates)
    evidence_gap_count = sum(
        1
        for item in candidates
        if (item.get("decision") or {}).get("missing_fields")
    )
    source_counts = Counter(str(item.get("source_kind") or "UNKNOWN") for item in candidates)
    entity_counts = Counter(
        entity.get("canonical_name")
        for item in candidates
        for entity in item.get("entities", [])
        if entity.get("canonical_name")
    )
    prioritized = sorted(
        candidates,
        key=lambda item: (
            {"SEND_READY": 0, "REVIEW": 1, "OBSERVE": 2, "EXCLUDE": 3}.get(item.get("status"), 4),
            -float(item.get("score") or 0),
        ),
    )
    candidate_summaries = [
        {
            "opportunity_id": item["id"],
            "title": item.get("title"),
            "status": item.get("status"),
            "source_url": item.get("source_url"),
            "source_kind": item.get("source_kind"),
            "snippet": item.get("snippet"),
            "evidence_level": item.get("evidence_level"),
            "entity_names": [entity.get("canonical_name") for entity in item.get("entities", [])],
            "decision": item.get("decision") or {},
            "evidence_count": len(item.get("evidence") or []),
            "feedback_count": len(item.get("feedback_events") or []),
        }
        for item in prioritized[:50]
    ]
    if not candidates:
        summary = "当前任务没有候选，不能生成有效商机结论。"
        next_actions = ["检查来源能力和来源权利", "确认任务目标与排除条件", "来源接通后重新运行任务"]
    elif status_counts.get("SEND_READY", 0):
        summary = f"任务产生 {len(candidates)} 条候选，其中 {status_counts['SEND_READY']} 条已达到人工动作前的证据门槛。"
        next_actions = ["人工打开原文并确认触达资格", "对 REVIEW 候选补齐缺失证据", "记录联系结果和退订状态"]
    else:
        summary = f"任务产生 {len(candidates)} 条候选，当前没有候选达到 SEND_READY。"
        next_actions = ["优先复核 REVIEW 候选并人工打开原文", "对 OBSERVE 候选补充采购动作证据", "不要把当前结果直接当成可发送名单"]

    return {
        "api_version": API_VERSION,
        "task_id": normalized,
        "brief": {
            "title": f"研究简报：{task.get('objective', normalized)}",
            "summary": summary,
            "task_status": task.get("status"),
            "candidate_count": len(candidates),
            "status_counts": dict(status_counts),
            "evidence_gap_count": evidence_gap_count,
            "source_kind_counts": dict(source_counts),
            "top_entities": [
                {"name": name, "candidate_count": count}
                for name, count in entity_counts.most_common(20)
            ],
            "candidates": candidate_summaries,
            "next_actions": next_actions,
        },
        "provenance": {
            "generated_by": "deterministic-local-brief-v1",
            "task_replay_used": True,
            "evidence_bound": True,
            "source_urls_preserved": True,
            "external_lookup_performed": False,
            "external_actions_sent": False,
            "contact_permission": "manual_confirmation_required",
            "limitations": [
                "简报只汇总当前任务已经入账的候选和证据。",
                "不会自动查询工商、联系方式、平台账户或第三方画像。",
                "候选相关性不等于采购意向，成交和跨行业效果不能从简报推出。",
            ],
        },
    }
