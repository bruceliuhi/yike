from __future__ import annotations

from typing import Any

# Preserve the documented direct-script entry point while sharing the packaged
# customer planner; pilot never imports this standalone application.
if not __package__:
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from pilot.radar_plan import build_search_directions

try:
    from .connectors import list_capabilities
    from .usage import DISPLAY_UNIT, RULE_VERSION, UNIT, cost_estimate as source_cost_estimate
except ImportError:  # running server.py directly
    from connectors import list_capabilities
    from usage import DISPLAY_UNIT, RULE_VERSION, UNIT, cost_estimate as source_cost_estimate


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = value.strip()
        if clean and clean not in seen:
            result.append(clean)
            seen.add(clean)
    return result


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
    language = str(criteria.get("language") or "zh-CN")
    regions = _unique(list(criteria.get("regions", [])))[:6]
    directions = build_search_directions(
        query_seeds=list(criteria.get("solution_terms", []))[:20],
        intent_signals=list(criteria.get("purchase_terms", []))[:20],
        exclusions=list(criteria.get("exclude_terms", []))[:25],
        region=" OR ".join(regions),
        business_terms=list(criteria.get("business_terms", []))[:20],
        max_queries=28,
    )
    quick, condition, broad = [stage["queries"] for stage in directions["strategies"]]

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
        "query_planner_version": directions["version"],
        "language": language,
        "requested_limit": requested_limit,
        "strategies": [
            stage | {"estimated_credits": credits}
            for stage, credits in zip(directions["strategies"],
                                      (quick_credits, condition_credits, broad_credits))
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
