"""Shared planning checks; no live search, provider, or customer result claims."""
from copy import deepcopy

import pytest

from pilot.radar_plan import VERSION, build_search_directions


def test_three_directions_stay_with_confirmed_business_without_ai_defaults():
    arguments = dict(query_seeds=["展台搭建"], intent_signals=["寻找搭建商", "询价"],
                     exclusions=["培训课程"], region="深圳", max_queries=12)
    original = deepcopy(arguments)
    plan = build_search_directions(**arguments)
    assert arguments == original
    assert plan["version"] == VERSION
    assert [stage["id"] for stage in plan["strategies"]] == ["quick", "condition", "broad"]
    assert all(stage["queries"] for stage in plan["strategies"])
    assert all("展台搭建" in query and query.startswith("深圳 ") for query in plan["queries"])
    assert any("-培训课程" in query for query in plan["strategies"][1]["queries"])
    assert not any(term in " ".join(plan["queries"]) for term in ("AI", "知识库", "客服", "外包开发"))
    assert set(plan) == {"version", "strategies", "queries"}
    assert all(set(stage) == {"id", "name", "purpose", "queries"} for stage in plan["strategies"])


def test_empty_terms_never_invent_targets_or_purchase_intent():
    assert build_search_directions(query_seeds=[], intent_signals=["采购"])["queries"] == []
    plan = build_search_directions(query_seeds=["食品输送设备"], intent_signals=[])
    assert plan["queries"] == ["食品输送设备"]
    assert plan["strategies"][1]["queries"] == []


def test_query_bound_prioritizes_every_confirmed_seed_and_deduplicates_groups():
    seeds = [f"产品{i}" for i in range(20)]
    plan = build_search_directions(query_seeds=seeds + [], intent_signals=["询价", "询价", "找供应商"],
                                   exclusions=["课程"], max_queries=24)
    assert len(plan["queries"]) == len(set(plan["queries"])) == 24
    assert plan["queries"][:20] == [seed + " 询价" for seed in seeds]
    assert sum(len(stage["queries"]) for stage in plan["strategies"]) == 24
    assert set(plan["queries"]) == {query for stage in plan["strategies"] for query in stage["queries"]}
    assert build_search_directions(query_seeds=seeds, intent_signals=["询价"], max_queries=1)["queries"] == ["产品0 询价"]


def test_exact_declared_synonyms_are_available_without_cross_industry_defaults():
    plan = build_search_directions(query_seeds=["AI customer service"],
                                   intent_signals=["looking for vendor"], exclusions=["job posting"])
    assert any("AI support agent" in query for query in plan["queries"])
    assert any('-"job posting"' in query for query in plan["queries"])
    assert not any("企业" in query or "教程" in query for query in plan["queries"])


@pytest.mark.parametrize("override", [
    {"query_seeds": ["api_key=private"]}, {"query_seeds": ["x\ncommand"]},
    {"query_seeds": ["x\u200b"]}, {"intent_signals": ["x\ud800"]},
    {"query_seeds": ["x"] * 21}, {"exclusions": "课程"},
    {"region": "password=private"}, {"max_queries": True}, {"max_queries": 65},
])
def test_bad_inputs_fail_before_any_execution(override):
    with pytest.raises(ValueError, match="^invalid_search_directions$"):
        build_search_directions(**(dict(query_seeds=["设备"], intent_signals=["采购"]) | override))


def test_standalone_wrapper_reuses_directions_but_keeps_pricing_out_of_core():
    from apps.lead_radar.planner import build_search_plan
    criteria = {"solution_terms": ["输送设备"], "purchase_terms": ["采购"],
                "business_terms": ["食品工厂"], "regions": ["杭州"], "exclude_terms": ["二手"], "sources": []}
    plan = build_search_plan(criteria, 10)
    shared = build_search_directions(query_seeds=criteria["solution_terms"],
        intent_signals=criteria["purchase_terms"], business_terms=criteria["business_terms"],
        region="杭州", exclusions=criteria["exclude_terms"], max_queries=28)
    assert plan["query_planner_version"] == shared["version"]
    assert [{key: value for key, value in stage.items() if key != "estimated_credits"}
            for stage in plan["strategies"]] == shared["strategies"]
    assert plan["execution"]["can_start"] is False
    assert plan["cost_estimate"]["max_credits"] is None
