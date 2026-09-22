from __future__ import annotations

import re
from typing import Any


TERM_GROUPS: dict[str, tuple[str, ...]] = {
    "solution": ("ai客服", "知识库", "智能体", "agent", "工作流", "数字人", "aigc", "大模型", "人工智能"),
    "purchase": ("开发", "定制", "外包", "采购", "预算", "供应商", "合作", "落地", "招标", "招募"),
    "business": ("企业", "公司", "团队", "门店", "政企", "金融", "教育", "医疗", "电商", "制造"),
    "exclude": ("教程", "学习", "课程", "分享", "招聘信息", "广告", "推广", "同行", "自媒体"),
}

DEFAULT_TERM_GROUPS: dict[str, tuple[str, ...]] = {
    "solution": ("AI客服", "企业知识库", "智能体", "AI工作流", "数字人"),
    "purchase": ("找服务商", "定制开发", "采购", "预算", "外包", "落地"),
    "business": ("企业", "公司", "团队"),
    "exclude": ("教程", "课程", "学习", "招聘", "广告", "推广", "同行"),
}


def now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def compile_intent(objective: str, supplied: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compile a human objective into a versioned, inspectable search profile.

    This deliberately stays deterministic in the foundation layer. An LLM planner can
    be added later, but its output must still land in this same schema and remain editable.
    """

    text = normalize(objective)
    matched = {
        group: [term for term in terms if term in text]
        for group, terms in TERM_GROUPS.items()
    }
    supplied = supplied or {}
    return {
        "objective": objective.strip(),
        "solution_terms": supplied.get("solution_terms") or matched["solution"] or list(DEFAULT_TERM_GROUPS["solution"]),
        "purchase_terms": supplied.get("purchase_terms") or matched["purchase"] or list(DEFAULT_TERM_GROUPS["purchase"]),
        "business_terms": supplied.get("business_terms") or matched["business"] or list(DEFAULT_TERM_GROUPS["business"]),
        "exclude_terms": supplied.get("exclude_terms") or matched["exclude"] or list(DEFAULT_TERM_GROUPS["exclude"]),
        "time_window_days": int(supplied.get("time_window_days", 180)),
        "regions": supplied.get("regions", []),
        "sources": supplied.get("sources", ["public_web", "xiaohongshu_public"]),
        "required_fields": supplied.get(
            "required_fields",
            ["title", "author", "published_at", "intent_type", "source_url", "snippet"],
        ),
        "explanation": {
            "solution": "命中场景词后作为候选需求主题",
            "purchase": "命中采购动作词后提高意向等级",
            "exclude": "命中排除词后进入人工复核或排除",
        },
    }


def evidence_status(item: dict[str, Any]) -> str:
    """Return a safe first-pass status; it never grants automatic send permission."""

    if not item.get("source_url") or not item.get("snippet"):
        return "EXCLUDE"
    if item.get("status") in {"OBSERVE", "EXCLUDE", "REVIEW"}:
        return item["status"]
    if item.get("evidence_level") == "VERIFIED" and item.get("source_permission") == "allowed":
        return "SEND_READY"
    return "REVIEW"
