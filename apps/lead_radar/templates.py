"""Curated task templates for the first-use and developer surfaces."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


TASK_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "id": "ai_custom_development",
        "title": "AI 定制开发需求",
        "title_en": "AI custom development demand",
        "description": "寻找正在评估 AI 应用、智能体或企业软件定制开发的团队。",
        "description_en": "Find teams evaluating custom AI applications, agents, or enterprise software.",
        "objective": "寻找最近 180 天公开表达过 AI 定制开发、企业 AI 应用或智能体落地需求的企业，排除招聘、课程和同行推广。",
        "objective_en": "Find companies that publicly expressed demand for custom AI development, enterprise AI applications, or agent implementation in the last 180 days. Exclude hiring, courses, and competitor promotion.",
        "criteria": {
            "intent_types": ["定制开发", "AI 应用", "智能体"],
            "exclude_terms": ["招聘", "课程", "同行推广"],
            "time_window_days": 180,
        },
    },
    {
        "id": "enterprise_knowledge_base",
        "title": "企业知识库需求",
        "title_en": "Enterprise knowledge base demand",
        "description": "寻找文档问答、内部知识库和企业检索增强需求。",
        "description_en": "Find document Q&A, internal knowledge base, and enterprise retrieval needs.",
        "objective": "寻找最近 180 天公开表达过企业知识库、文档问答、内部检索或 RAG 落地需求的企业，排除教程、招聘和泛讨论。",
        "objective_en": "Find companies that publicly expressed needs for enterprise knowledge bases, document Q&A, internal search, or RAG implementation in the last 180 days. Exclude tutorials, hiring, and generic discussion.",
        "criteria": {
            "intent_types": ["企业知识库", "文档问答", "RAG"],
            "exclude_terms": ["教程", "招聘", "泛讨论"],
            "time_window_days": 180,
        },
    },
    {
        "id": "ai_customer_service",
        "title": "AI 客服采购需求",
        "title_en": "AI customer service demand",
        "description": "寻找客服自动化、智能问答和人工转接场景。",
        "description_en": "Find customer support automation, intelligent Q&A, and human handoff use cases.",
        "objective": "寻找最近 90 天公开表达过 AI 客服、智能问答、客服自动化或人工转接需求的企业，排除招聘和服务商广告。",
        "objective_en": "Find companies that publicly expressed demand for AI customer service, intelligent Q&A, support automation, or human handoff in the last 90 days. Exclude hiring and vendor advertisements.",
        "criteria": {
            "intent_types": ["AI 客服", "智能问答", "客服自动化"],
            "exclude_terms": ["招聘", "服务商广告"],
            "time_window_days": 90,
        },
    },
    {
        "id": "ai_agent_workflow",
        "title": "智能体与工作流需求",
        "title_en": "AI agent and workflow demand",
        "description": "寻找业务流程自动化、Agent 和系统集成需求。",
        "description_en": "Find business automation, agent, and system integration needs.",
        "objective": "寻找最近 180 天公开表达过 AI Agent、工作流自动化、系统集成或业务流程改造需求的企业，排除学习内容和同行案例营销。",
        "objective_en": "Find companies that publicly expressed demand for AI agents, workflow automation, system integration, or business process redesign in the last 180 days. Exclude learning content and competitor case marketing.",
        "criteria": {
            "intent_types": ["AI Agent", "工作流自动化", "系统集成"],
            "exclude_terms": ["学习", "同行案例营销"],
            "time_window_days": 180,
        },
    },
    {
        "id": "digital_human_aigc",
        "title": "数字人与 AIGC 采购",
        "title_en": "Digital human and AIGC procurement",
        "description": "寻找数字人、企业视频和 AIGC 内容生产需求。",
        "description_en": "Find digital human, enterprise video, and AIGC production demand.",
        "objective": "寻找最近 180 天公开表达过数字人、企业视频、AIGC 内容生产或虚拟主播定制需求的企业，排除课程和纯工具测评。",
        "objective_en": "Find companies that publicly expressed demand for digital humans, enterprise video, AIGC production, or virtual host customization in the last 180 days. Exclude courses and tool-only reviews.",
        "criteria": {
            "intent_types": ["数字人", "AIGC", "企业视频"],
            "exclude_terms": ["课程", "工具测评"],
            "time_window_days": 180,
        },
    },
    {
        "id": "tender_procurement",
        "title": "AI 招标与采购公告",
        "title_en": "AI tenders and procurement notices",
        "description": "寻找公开采购、招标、询价和供应商征集信号。",
        "description_en": "Find public procurement, tenders, quotations, and supplier requests.",
        "objective": "寻找最近 90 天公开发布的 AI、智能客服、知识库、数字化或智能体招标采购公告，排除培训、招聘和无明确采购动作的文章。",
        "objective_en": "Find AI, intelligent customer service, knowledge base, digitalization, or agent tenders and procurement notices published in the last 90 days. Exclude training, hiring, and articles without a procurement action.",
        "criteria": {
            "intent_types": ["招标", "采购", "询价"],
            "exclude_terms": ["培训", "招聘", "无采购动作"],
            "time_window_days": 90,
        },
    },
    {
        "id": "website_change_monitor",
        "title": "客户与竞品官网变化",
        "title_en": "Customer and competitor website changes",
        "description": "监控指定官网的产品、招聘、案例和公告变化。",
        "description_en": "Monitor product, hiring, case study, and notice changes on selected websites.",
        "objective": "监控目标企业或竞品官网最近 30 天的新产品、招聘、案例、采购和页面内容变化，保留变化前后证据。",
        "objective_en": "Monitor target or competitor websites for new products, hiring, case studies, procurement, and content changes in the last 30 days, preserving before-and-after evidence.",
        "criteria": {
            "intent_types": ["官网变化", "竞品变化", "招聘"],
            "time_window_days": 30,
        },
    },
)


def list_task_templates(language: str = "zh-CN") -> list[dict[str, Any]]:
    normalized = str(language or "zh-CN").strip()
    if normalized not in {"zh-CN", "en-US"}:
        raise ValueError("language_not_supported")
    result: list[dict[str, Any]] = []
    for template in TASK_TEMPLATES:
        item = deepcopy(template)
        if normalized == "en-US":
            item["title"] = item.pop("title_en")
            item["description"] = item.pop("description_en")
            item["objective"] = item.pop("objective_en")
        else:
            item.pop("title_en", None)
            item.pop("description_en", None)
            item.pop("objective_en", None)
        item["language"] = normalized
        result.append(item)
    return result


def get_task_template(template_id: Any, language: str = "zh-CN") -> dict[str, Any] | None:
    normalized_id = str(template_id or "").strip()
    if not normalized_id:
        return None
    for item in list_task_templates(language):
        if item["id"] == normalized_id:
            return item
    return None
