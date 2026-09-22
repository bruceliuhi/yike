"""Localized presentation fields layered on top of immutable evidence."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


SUPPORTED_LANGUAGES = {"zh-CN", "en-US"}

_LABELS: dict[str, dict[str, dict[str, str]]] = {
    "status": {
        "REVIEW": {"zh-CN": "待复核", "en-US": "Review"},
        "OBSERVE": {"zh-CN": "观察", "en-US": "Observe"},
        "SEND_READY": {"zh-CN": "可进入人工联系队列", "en-US": "Ready for human action"},
        "EXCLUDE": {"zh-CN": "已排除", "en-US": "Excluded"},
        "DUPLICATE": {"zh-CN": "重复", "en-US": "Duplicate"},
        "CONTACTED": {"zh-CN": "已联系", "en-US": "Contacted"},
        "DEFERRED": {"zh-CN": "暂缓", "en-US": "Deferred"},
        "HANDOFF": {"zh-CN": "已转人工", "en-US": "Handed off"},
        "DO_NOT_CONTACT": {"zh-CN": "禁触达", "en-US": "Do not contact"},
    },
    "source_kind": {
        "manual_public_evidence": {"zh-CN": "人工提交公开证据", "en-US": "User-submitted public evidence"},
        "public_url_capture": {"zh-CN": "公开网页采集", "en-US": "Public page capture"},
        "public_feed_capture": {"zh-CN": "公开 RSS/Atom Feed", "en-US": "Public RSS/Atom feed"},
        "search_index_snippet": {"zh-CN": "授权搜索索引摘要", "en-US": "Authorized search index snippet"},
        "authorized_search_api": {"zh-CN": "授权搜索 API", "en-US": "Authorized search API"},
    },
    "decision_code": {
        "MISSING_EVIDENCE_FIELDS": {"zh-CN": "缺少必要证据", "en-US": "Required evidence is missing"},
        "CAPTURED_PAGE_NEEDS_REVIEW": {"zh-CN": "公开网页待复核", "en-US": "Captured page needs review"},
        "CAPTURED_FEED_NEEDS_REVIEW": {"zh-CN": "公开 Feed 待复核", "en-US": "Captured feed needs review"},
        "PROVIDER_RESULT_NEEDS_REOPEN": {"zh-CN": "搜索结果需要重开原文", "en-US": "Provider result needs original-page reopen"},
        "SOURCE_PERMISSION_UNCONFIRMED": {"zh-CN": "来源使用权未确认", "en-US": "Source permission is unconfirmed"},
        "EVIDENCE_NEEDS_REVIEW": {"zh-CN": "证据待人工复核", "en-US": "Evidence needs human review"},
    },
    "band": {
        "HIGH": {"zh-CN": "高优先级", "en-US": "High priority"},
        "MEDIUM": {"zh-CN": "中优先级", "en-US": "Medium priority"},
        "LOW": {"zh-CN": "低优先级", "en-US": "Low priority"},
    },
}


def _language(language: Any) -> str:
    normalized = str(language or "zh-CN").strip()
    if normalized not in SUPPORTED_LANGUAGES:
        raise ValueError("language_not_supported")
    return normalized


def _label(group: str, value: Any, language: str) -> str:
    normalized = str(value or "").strip()
    return _LABELS.get(group, {}).get(normalized, {}).get(language, normalized)


def localize_opportunity(item: dict[str, Any], language: str = "zh-CN") -> dict[str, Any]:
    normalized = _language(language)
    result = deepcopy(item)
    decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
    qualification = decision.get("qualification") if isinstance(decision.get("qualification"), dict) else {}
    result["presentation"] = {
        "language": normalized,
        "status_label": _label("status", item.get("status"), normalized),
        "source_kind_label": _label("source_kind", item.get("source_kind"), normalized),
        "decision_code_label": _label("decision_code", decision.get("code"), normalized),
        "decision_reason": {
            "zh-CN": str(decision.get("reason") or "待人工复核"),
            "en-US": _label("decision_code", decision.get("code"), normalized),
        }[normalized],
        "qualification_band_label": _label("band", qualification.get("band"), normalized),
        "qualification_priority": qualification.get("review_priority"),
        "source_evidence_is_original": True,
    }
    return result


def localize_opportunities(items: list[dict[str, Any]], language: str = "zh-CN") -> list[dict[str, Any]]:
    normalized = _language(language)
    return [localize_opportunity(item, normalized) for item in items]
