"""Explainable, deterministic qualification scoring for Lead Radar candidates."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


VERSION = "qualification-v1"
DEFAULT_SOLUTION_TERMS = (
    "ai客服", "智能客服", "企业知识库", "知识库", "智能体", "agent", "工作流", "数字人", "aigc", "大模型",
)
DEFAULT_PURCHASE_TERMS = (
    "找服务商", "寻找服务商", "找团队", "寻找团队", "定制开发", "开发", "采购", "预算", "供应商", "外包", "合作", "落地", "招标", "报价",
)
DEFAULT_BUSINESS_TERMS = (
    "企业", "公司", "团队", "门店", "政企", "金融", "教育", "医疗", "电商", "制造", "enterprise", "company",
)
DEFAULT_EXCLUDE_TERMS = (
    "教程", "学习", "课程", "招聘", "广告", "推广", "同行", "自媒体", "tutorial", "course", "job posting", "advertisement", "competitor",
)


def _text(value: Any) -> str:
    return str(value or "").strip().lower()


def _terms(criteria: dict[str, Any], primary: str, fallback: tuple[str, ...], *aliases: str) -> list[str]:
    values: list[Any] = []
    for key in (primary, *aliases):
        candidate = criteria.get(key)
        if isinstance(candidate, list):
            values.extend(candidate)
    result: list[str] = []
    seen: set[str] = set()
    for value in values or list(fallback):
        clean = _text(value)
        if clean and clean not in seen:
            result.append(clean)
            seen.add(clean)
    return result


def _hits(text: str, terms: list[str]) -> list[str]:
    compact_text = text.replace(" ", "")
    return [term for term in terms if term in text or term.replace(" ", "") in compact_text]


def _recency_score(published_at: Any, time_window_days: Any, now: datetime) -> tuple[int, str]:
    if not isinstance(published_at, str) or not published_at.strip():
        return 0, "published_at_missing"
    try:
        parsed = datetime.fromisoformat(published_at.strip().replace("Z", "+00:00"))
    except ValueError:
        return 0, "published_at_invalid"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    try:
        window = max(1, int(time_window_days or 180))
    except (TypeError, ValueError):
        window = 180
    age_days = max(0, (now - parsed.astimezone(timezone.utc)).days)
    if age_days <= window:
        return 10, f"within_{window}_days"
    if age_days <= window * 2:
        return 4, f"within_{window * 2}_days"
    return 0, "outside_time_window"


def score_opportunity(item: dict[str, Any], criteria: dict[str, Any] | None = None, *, now: datetime | None = None) -> dict[str, Any]:
    """Score one candidate from visible evidence only.

    This score ranks review work; it never grants contact permission. The
    evidence decision and source-rights gates remain authoritative.
    """

    criteria = criteria if isinstance(criteria, dict) else {}
    text = " ".join(_text(item.get(field)) for field in ("title", "intent_type", "snippet", "author"))
    solution_terms = _terms(criteria, "solution_terms", DEFAULT_SOLUTION_TERMS, "intent_types")
    purchase_terms = _terms(criteria, "purchase_terms", DEFAULT_PURCHASE_TERMS)
    business_terms = _terms(criteria, "business_terms", DEFAULT_BUSINESS_TERMS)
    exclude_terms = _terms(criteria, "exclude_terms", DEFAULT_EXCLUDE_TERMS)
    solution_hits = _hits(text, solution_terms)
    purchase_hits = _hits(text, purchase_terms)
    business_hits = _hits(text, business_terms)
    exclude_hits = _hits(text, exclude_terms)

    solution_points = min(30, len(solution_hits) * 10)
    purchase_points = min(30, len(purchase_hits) * 10)
    business_points = min(15, len(business_hits) * 5)
    recency_points, recency_signal = _recency_score(item.get("published_at"), criteria.get("time_window_days", 180), now or datetime.now(timezone.utc))
    evidence_points = 0
    if _text(item.get("source_url")) and urlparse(_text(item.get("source_url"))).scheme in {"http", "https"}:
        evidence_points += 5
    if _text(item.get("snippet")):
        evidence_points += 5
    if _text(item.get("published_at")):
        evidence_points += 3
    if item.get("evidence_level") in {"CAPTURED", "VERIFIED"}:
        evidence_points += 2
    penalty = min(50, len(exclude_hits) * 15)
    score = max(0, min(100, solution_points + purchase_points + business_points + recency_points + evidence_points - penalty))
    band = "HIGH" if score >= 70 else "MEDIUM" if score >= 45 else "LOW"
    return {
        "version": VERSION,
        "score": score,
        "band": band,
        "review_priority": "P1" if score >= 70 else "P2" if score >= 45 else "P3",
        "permission_granted": False,
        "components": {
            "solution": {"points": solution_points, "matched_terms": solution_hits},
            "purchase": {"points": purchase_points, "matched_terms": purchase_hits},
            "business": {"points": business_points, "matched_terms": business_hits},
            "recency": {"points": recency_points, "signal": recency_signal},
            "evidence": {"points": evidence_points},
            "exclusion_penalty": {"points": penalty, "matched_terms": exclude_hits},
        },
        "next_action": "优先人工打开原文，核对采购动作、发布时间、来源权利和实体；评分不会自动授权联系。",
    }
