"""Versioned ICP definitions for the first paid Lead Radar wedge."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


SUPPORTED_LANGUAGES = {"zh-CN", "en-US"}


_PROFILES: tuple[dict[str, Any], ...] = (
    {
        "id": "ai_solution_buyer_v1",
        "version": "1.0",
        "name": {"zh-CN": "AI 解决方案采购方", "en-US": "AI solution buyer"},
        "description": {
            "zh-CN": "正在评估或采购 AI 定制开发、企业知识库、AI 客服、智能体或数字人落地的企业团队。",
            "en-US": "Teams evaluating or procuring custom AI development, enterprise knowledge bases, AI customer service, agents, or digital-human implementations.",
        },
        "buyer_roles": {"zh-CN": ["业务负责人", "数字化负责人", "IT/信息化负责人", "采购负责人"], "en-US": ["Business owner", "Digital transformation lead", "IT/technology lead", "Procurement lead"]},
        "positive_signal_groups": [
            "problem_or_solution_signal",
            "purchase_action_signal",
            "business_context_signal",
            "time_or_budget_signal",
        ],
        "required_evidence": {
            "zh-CN": ["原文明确描述问题或目标", "出现采购/寻找服务商/定制/预算/招标等动作", "能确认企业或组织场景", "保留可重开 URL、发布时间和原文片段"],
            "en-US": ["Original text states a problem or target", "A procurement, vendor-search, custom-build, budget, or tender action is present", "An enterprise or organization context can be established", "A reopenable URL, publication time, and original excerpt are retained"],
        },
        "exclude_signals": {
            "zh-CN": ["教程、课程、学习内容", "招聘岗位", "服务商自我推广或同行案例", "只有泛泛讨论，没有采购动作"],
            "en-US": ["Tutorials, courses, or learning content", "Job postings", "Vendor self-promotion or competitor case marketing", "Generic discussion without a purchase action"],
        },
        "qualification_policy": {
            "minimum_score_for_priority_review": 45,
            "minimum_score_for_send_ready_review": 70,
            "required_human_review": True,
            "source_reopen_required": True,
            "contact_permission": "manual_confirmation_required",
        },
        "pilot_acceptance": {
            "zh-CN": ["30 条真实候选人工校准", "来源可重开率 100%", "人工标注准确率至少 80%", "安全误触达 0"],
            "en-US": ["30 real candidates manually calibrated", "100% source reopen rate", "At least 80% human-label accuracy", "Zero unsafe outreach"],
        },
        "status": "READY_LOCAL",
        "requires_external_source_proof": True,
    },
)


def list_icp_profiles(language: str = "zh-CN") -> list[dict[str, Any]]:
    normalized = str(language or "zh-CN").strip()
    if normalized not in SUPPORTED_LANGUAGES:
        raise ValueError("language_not_supported")
    result: list[dict[str, Any]] = []
    for profile in _PROFILES:
        item = deepcopy(profile)
        item["language"] = normalized
        item["name"] = profile["name"][normalized]
        item["description"] = profile["description"][normalized]
        item["buyer_roles"] = profile["buyer_roles"][normalized]
        item["required_evidence"] = profile["required_evidence"][normalized]
        item["exclude_signals"] = profile["exclude_signals"][normalized]
        item["pilot_acceptance"] = profile["pilot_acceptance"][normalized]
        result.append(item)
    return result


def get_icp_profile(profile_id: Any, language: str = "zh-CN") -> dict[str, Any] | None:
    normalized_id = str(profile_id or "").strip()
    return next((item for item in list_icp_profiles(language) if item["id"] == normalized_id), None)
