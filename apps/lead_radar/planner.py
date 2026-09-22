from __future__ import annotations

from itertools import product
from typing import Any

try:
    from .connectors import list_capabilities
    from .usage import DISPLAY_UNIT, RULE_VERSION, UNIT, cost_estimate as source_cost_estimate
except ImportError:  # running server.py directly
    from connectors import list_capabilities
    from usage import DISPLAY_UNIT, RULE_VERSION, UNIT, cost_estimate as source_cost_estimate


SYNONYMS: dict[str, tuple[str, ...]] = {
    "AI客服": ("AI客服", "智能客服", "客服机器人"),
    "企业知识库": ("企业知识库", "内部知识库", "文档问答"),
    "智能体": ("智能体", "Agent", "业务助手"),
    "AI工作流": ("AI工作流", "自动化工作流", "业务自动化"),
    "数字人": ("数字人", "虚拟人", "数字员工"),
    "找服务商": ("找服务商", "寻找团队", "找供应商"),
    "定制开发": ("定制开发", "定制", "开发落地"),
    "采购": ("采购", "寻求采购", "招标采购"),
    "预算": ("预算", "报价", "项目预算"),
    "外包": ("外包", "合作开发", "项目外包"),
    "落地": ("落地", "实施", "上线"),
}


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = value.strip()
        if clean and clean not in seen:
            result.append(clean)
            seen.add(clean)
    return result


def _expand(terms: list[str]) -> list[str]:
    expanded: list[str] = []
    for term in terms:
        expanded.extend(SYNONYMS.get(term, (term,)))
    return _unique(expanded)


def _query(topic: str, action: str, business: str = "") -> str:
    suffix = f" {business}" if business else ""
    return f'"{topic}" "{action}"{suffix} -教程 -课程 -纯招聘'


def _capability_index(source_ids: list[str]) -> list[dict[str, Any]]:
    known = {item["id"]: item for item in list_capabilities()}
    result: list[dict[str, Any]] = []
    for source_id in source_ids:
        item = known.get(source_id)
        if item:
            result.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "status": item["status"],
                    "can_search": item["can_search"],
                    "note": item["note"],
                }
            )
        else:
            result.append(
                {
                    "id": source_id,
                    "name": source_id,
                    "status": "UNAVAILABLE",
                    "can_search": False,
                    "note": "未注册连接器。",
                }
            )
    return result


def build_search_plan(criteria: dict[str, Any], requested_limit: int) -> dict[str, Any]:
    topics = _expand(list(criteria.get("solution_terms", [])))[:8]
    actions = _expand(list(criteria.get("purchase_terms", [])))[:8]
    businesses = _unique(list(criteria.get("business_terms", [])))[:4]
    regions = _unique(list(criteria.get("regions", [])))[:6]
    if not topics:
        topics = ["企业AI应用"]
    if not actions:
        actions = ["找服务商"]

    combinations = list(product(topics[:4], actions[:4]))
    quick = [_query(topic, action) for topic, action in combinations[:8]]
    condition = [_query(topic, action, business) for topic, action, business in product(topics[:3], actions[:3], businesses[:2] or [""])][:10]
    broad = [_query(topic, action) for topic, action in product(topics[4:8] or topics[:2], actions[4:8] or actions[:2])][:10]
    if regions:
        region_hint = " OR ".join(regions)
        condition = [f"({query}) ({region_hint})" for query in condition]

    source_ids: list[str] = []
    for source_id in criteria.get("sources", []):
        normalized_source_id = str(source_id).strip()
        if normalized_source_id and normalized_source_id not in source_ids:
            source_ids.append(normalized_source_id)
    sources = _capability_index(source_ids)
    runnable = [item["id"] for item in sources if item["status"] == "READY" and item["can_search"]]
    blocked = [item["id"] for item in sources if item["status"] != "READY" or not item["can_search"]]
    execution = {
        "status": "READY" if runnable else "BLOCKED_REQUIRES_SOURCE",
        "can_start": bool(runnable),
        "runnable_sources": runnable,
        "blocked_sources": blocked,
        "summary": (
            "至少有一个来源通过自动搜索生产门禁，可以进入队列。"
            if runnable
            else "计划已生成，但当前没有通过自动搜索生产门禁的来源；可保存计划或改用受控公开 URL 导入。"
        ),
    }
    quick_credits = max(1, len(quick)) * 2
    condition_credits = max(1, len(condition)) * 3
    broad_credits = max(1, len(broad)) * 2
    source_quotes = [source_cost_estimate(item["id"], requested_limit) for item in sources]
    known_quotes = [item for item in source_quotes if item["maximum_credits"] is not None]
    estimated_min = quick_credits if known_quotes else None
    estimated_max = quick_credits + condition_credits + broad_credits if known_quotes else None
    return {
        "planner_version": "2026.09.23.1",
        "requested_limit": requested_limit,
        "strategies": [
            {"id": "quick", "name": "快速搜索", "purpose": "先拿到少量高相关候选", "queries": quick, "estimated_credits": quick_credits},
            {"id": "condition", "name": "条件核验", "purpose": "逐项核验时间、动作、行业和地域", "queries": condition, "estimated_credits": condition_credits},
            {"id": "broad", "name": "扩展搜索", "purpose": "用同义词、相邻场景和业务词继续发现", "queries": broad, "estimated_credits": broad_credits},
        ],
        "hard_filters": {
            "time_window_days": int(criteria.get("time_window_days", 180)),
            "regions": regions,
            "exclude_terms": list(criteria.get("exclude_terms", [])),
            "required_fields": list(criteria.get("required_fields", [])),
        },
        "source_plan": sources,
        "runnable_sources": runnable,
        "blocked_sources": blocked,
        "execution": execution,
        "coverage": {
            "requested_source_count": len(sources),
            "runnable_source_count": len(runnable),
            "blocked_source_count": len(blocked),
            "source_ids": [item["id"] for item in sources],
            "explanation": execution["summary"],
        },
        "cost_estimate": {
            "min_credits": estimated_min,
            "max_credits": estimated_max,
            "unit": UNIT,
            "display_unit": DISPLAY_UNIT,
            "rule_version": RULE_VERSION,
            "settlement": "NOT_STARTED" if known_quotes else "UNKNOWN",
            "source_results": source_quotes,
            "explanation": "仅为搜索路径估算；实际按来源结果结算，新增结果按 1 搜贝计，重复、失败和无结果为 0 搜贝。未接通来源不会扣费。",
        },
        "output_contract": ["title", "author", "published_at", "intent_type", "industry_location", "source_url", "snippet", "evidence_level"],
    }
