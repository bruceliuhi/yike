from __future__ import annotations

import re
from typing import Any


TERM_GROUPS: dict[str, tuple[str, ...]] = {
    "solution": ("ai客服", "知识库", "智能体", "agent", "工作流", "数字人", "aigc", "大模型", "人工智能"),
    "purchase": ("开发", "定制", "外包", "采购", "预算", "供应商", "合作", "落地", "招标", "招募"),
    "business": ("企业", "公司", "团队", "门店", "政企", "金融", "教育", "医疗", "电商", "制造"),
    "exclude": ("教程", "学习", "课程", "分享", "招聘信息", "广告", "推广", "同行", "自媒体"),
}

TERM_GROUPS_EN: dict[str, tuple[str, ...]] = {
    "solution": ("ai customer service", "enterprise knowledge base", "ai agent", "workflow automation", "digital human", "large language model"),
    "purchase": ("looking for vendor", "custom development", "procurement", "budget", "supplier", "implementation", "tender"),
    "business": ("enterprise", "company", "team", "retail", "government", "finance", "education", "healthcare", "ecommerce", "manufacturing"),
    "exclude": ("tutorial", "course", "learning", "job posting", "advertisement", "promotion", "competitor", "creator"),
}

DEFAULT_TERM_GROUPS: dict[str, tuple[str, ...]] = {
    "solution": ("AI客服", "企业知识库", "智能体", "AI工作流", "数字人"),
    "purchase": ("找服务商", "定制开发", "采购", "预算", "外包", "落地"),
    "business": ("企业", "公司", "团队"),
    "exclude": ("教程", "课程", "学习", "招聘", "广告", "推广", "同行"),
}

DEFAULT_TERM_GROUPS_EN: dict[str, tuple[str, ...]] = {
    "solution": ("AI customer service", "enterprise knowledge base", "AI agent", "workflow automation", "digital human"),
    "purchase": ("looking for vendor", "custom development", "procurement", "budget", "implementation"),
    "business": ("enterprise", "company", "team"),
    "exclude": ("tutorial", "course", "learning", "job posting", "advertisement", "competitor"),
}

SUPPORTED_LANGUAGES = {"zh-CN", "en-US"}


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
    language = str(supplied.get("language") or ("zh-CN" if any("\u4e00" <= character <= "\u9fff" for character in objective) else "en-US")).strip()
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError("language_not_supported")
    if language == "en-US":
        matched = {
            group: [term for term in terms if term in text]
            for group, terms in TERM_GROUPS_EN.items()
        }
        defaults = DEFAULT_TERM_GROUPS_EN
    else:
        defaults = DEFAULT_TERM_GROUPS
    return {
        "objective": objective.strip(),
        "language": language,
        "solution_terms": supplied.get("solution_terms") or matched["solution"] or list(defaults["solution"]),
        "purchase_terms": supplied.get("purchase_terms") or matched["purchase"] or list(defaults["purchase"]),
        "business_terms": supplied.get("business_terms") or matched["business"] or list(defaults["business"]),
        "exclude_terms": supplied.get("exclude_terms") or matched["exclude"] or list(defaults["exclude"]),
        "time_window_days": int(supplied.get("time_window_days", 180)),
        "regions": supplied.get("regions", []),
        "sources": supplied.get(
            "sources",
            ["public_web", "xiaohongshu_public", "douyin_public", "bilibili_public", "zhihu_public"],
        ),
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


def evidence_decision(item: dict[str, Any]) -> dict[str, Any]:
    """Return a machine-readable status decision and the next human action.

    The decision is deliberately conservative. A search result can be useful without
    being safe to contact; only a verified, allowed evidence item reaches SEND_READY.
    """

    missing_fields = [field for field in ("source_url", "snippet") if not str(item.get(field, "")).strip()]
    if missing_fields:
        return {
            "status": "EXCLUDE",
            "code": "MISSING_EVIDENCE_FIELDS",
            "reason": "缺少来源 URL 或原文片段，无法重开和复核。",
            "missing_fields": missing_fields,
            "next_action": "补齐原文证据后重新录入。",
        }
    if item.get("status") in {"OBSERVE", "EXCLUDE", "REVIEW"}:
        status = str(item["status"])
        return {
            "status": status,
            "code": "OPERATOR_OVERRIDE",
            "reason": "沿用人工指定的机会状态。",
            "missing_fields": [],
            "next_action": "按人工状态继续观察或补充证据。",
        }
    if item.get("evidence_level") == "VERIFIED" and item.get("source_permission") == "allowed":
        return {
            "status": "SEND_READY",
            "code": "VERIFIED_ALLOWED_EVIDENCE",
            "reason": "原文证据已人工核验，来源使用权状态为 allowed。",
            "missing_fields": [],
            "next_action": "可以进入人工联系队列，发送前仍需确认。",
        }
    if item.get("source_kind") == "authorized_search_api":
        reason = "授权搜索 API 返回了候选结果，但还没有逐条完成原文重开核验。"
        code = "PROVIDER_RESULT_NEEDS_REOPEN"
    elif item.get("source_kind") == "public_url_capture":
        reason = "公开网页已采集并保存内容指纹，但页面相关性仍需人工判断。"
        code = "CAPTURED_PAGE_NEEDS_REVIEW"
    elif item.get("source_permission") != "allowed":
        reason = "来源使用权尚未明确为 allowed，不能直接进入联系队列。"
        code = "SOURCE_PERMISSION_UNCONFIRMED"
    else:
        reason = "证据字段存在，但尚未满足人工核验和来源使用权条件。"
        code = "EVIDENCE_NEEDS_REVIEW"
    return {
        "status": "REVIEW",
        "code": code,
        "reason": reason,
        "missing_fields": [],
        "next_action": "人工打开来源、核对发布时间和采购意向，再决定有效或排除。",
    }


def evidence_status(item: dict[str, Any]) -> str:
    return str(evidence_decision(item)["status"])
