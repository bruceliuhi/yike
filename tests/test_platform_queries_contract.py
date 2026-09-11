"""Platform-specific ordinary-search terms; all values are synthetic."""
import json

import pytest
from pydantic import ValidationError

from pilot.research_strategy_contract import (
    PrepareStrategyRequest,
    ResearchStrategyConfiguration,
    configuration_digest,
    strategy_snapshot,
)


PROFILE = "11111111-1111-4111-8111-111111111111"
STRATEGY = "22222222-2222-4222-8222-222222222222"
REQUEST = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
DRAFT = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def configuration(**changes):
    return dict(
        schema_version="research-strategy-v1",
        name="平台搜索词",
        source="search",
        keywords=["通用需求"],
        exclusions=["招聘"],
        links=[],
        mode="once",
        schedule=None,
        research=None,
    ) | changes


def platform_queries():
    return {
        "version": "platform-queries-v1",
        "items": [
            {"platform": "XIAOHONGSHU", "keywords": ["找搭建团队"]},
            {"platform": "BILIBILI", "keywords": ["展台设计报价"]},
        ],
    }


def prepare(configuration_value=None, platforms=None):
    return {
        "schema_version": "strategy-confirmation-v1",
        "request_id": REQUEST,
        "draft_id": DRAFT,
        "draft_revision": 1,
        "profile_version_id": PROFILE,
        "configuration": configuration_value or configuration(),
        "platforms": platforms or ["XIAOHONGSHU", "BILIBILI"],
        "max_records": 10,
        "max_runtime_seconds": 600,
    }


def snapshot(configuration_value):
    return strategy_snapshot(
        PROFILE, STRATEGY, configuration_value,
        ["XIAOHONGSHU", "BILIBILI"], 10, 600,
    )


def test_platform_queries_round_trip_and_legacy_bytes_remain_unchanged():
    legacy = configuration()
    legacy_bytes = json.dumps(legacy, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert ResearchStrategyConfiguration.model_validate(legacy).model_dump(mode="json") == legacy
    assert json.dumps(
        ResearchStrategyConfiguration.model_validate(legacy).model_dump(mode="json"),
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ) == legacy_bytes

    current = configuration(platformQueries=platform_queries())
    assert ResearchStrategyConfiguration.model_validate(current).model_dump(mode="json") == current
    assert PrepareStrategyRequest.model_validate(prepare(current)).model_dump(mode="json") == prepare(current)
    assert snapshot(current)["configuration"]["platformQueries"] == platform_queries()
    assert configuration_digest(snapshot(current)) != configuration_digest(snapshot(legacy))


@pytest.mark.parametrize("platform_queries_value", [
    None,
    {"version": "platform-queries-v1", "items": []},
    {"version": "wrong", "items": [{"platform": "XIAOHONGSHU", "keywords": ["需求"]}]},
    {"version": "platform-queries-v1", "items": [
        {"platform": "XIAOHONGSHU", "keywords": ["需求"]},
        {"platform": "XIAOHONGSHU", "keywords": ["询价"]},
    ]},
    {"version": "platform-queries-v1", "items": [{"platform": "PUBLIC_WEB", "keywords": ["需求"]}]},
    {"version": "platform-queries-v1", "items": [{"platform": "XIAOHONGSHU", "keywords": []}]},
    {"version": "platform-queries-v1", "items": [{"platform": "XIAOHONGSHU", "keywords": [" 需求"]}]},
    {"version": "platform-queries-v1", "items": [{"platform": "XIAOHONGSHU", "keywords": ["需求,询价"]}]},
    {"version": "platform-queries-v1", "items": [{"platform": "XIAOHONGSHU", "keywords": ["招聘"]}]},
])
def test_platform_queries_reject_invalid_shape_and_terms(platform_queries_value):
    with pytest.raises(ValidationError):
        ResearchStrategyConfiguration.model_validate(
            configuration(platformQueries=platform_queries_value)
        )


@pytest.mark.parametrize("changes", [
    {"research": {"version": 1, "demandTypes": ["INQUIRY"], "maxSoubei": 1,
                  "limits": {"sources": 1, "minutes": 1, "modelCalls": 1},
                  "stopAtAnyLimit": True, "evidenceOrder": "SOURCE_MATCH_CONTEXT"}},
    {"source": "links", "links": ["https://example.com/demand"]},
])
def test_platform_queries_are_only_for_plain_search(changes):
    with pytest.raises(ValidationError):
        ResearchStrategyConfiguration.model_validate(
            configuration(platformQueries=platform_queries(), **changes)
        )


def test_platform_queries_must_be_scoped_to_selected_platforms():
    with pytest.raises(ValidationError):
        PrepareStrategyRequest.model_validate(
            prepare(configuration(platformQueries=platform_queries()), ["XIAOHONGSHU"])
        )
