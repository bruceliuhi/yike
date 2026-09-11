"""Closed public-node backend contract; synthetic only, no network or database."""
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from pilot import foreground_collection as collection
from pilot.monitor_runtime import MonitorRuntime
from pilot.research_strategy_contract import ResearchStrategyConfiguration


def configuration(**changes):
    value = dict(schema_version="research-strategy-v1", name="公开板块", source="search",
                 keywords=["企业软件"], exclusions=["招聘"], links=[], mode="once",
                 schedule=None, research=None, publicSource="v2ex-qna-v1")
    return value | changes


def schedule():
    return dict(kind="daily", times=["09:30"], interval=1, start="09:00", end="18:00",
                timezone="Asia/Shanghai", policyVersion=1)


def runtime(policy):
    database = SimpleNamespace(connect=lambda: nullcontext(
        SimpleNamespace(cursor=lambda: nullcontext(object()))))
    return SimpleNamespace(database=database, _active=lambda *_: None, capability_check=policy)


def test_public_source_contract_accepts_both_fixed_ids_without_rewriting_qna():
    parsed = ResearchStrategyConfiguration.model_validate(configuration())
    assert parsed.publicSource == "v2ex-qna-v1"
    assert parsed.model_dump(mode="json")["publicSource"] == "v2ex-qna-v1"
    for invalid in ("qna", "https://www.v2ex.com/go/qna", "", None, True):
        value = configuration(publicSource=invalid)
        if invalid is None:
            assert "publicSource" not in ResearchStrategyConfiguration.model_validate(value).model_dump(mode="json")
        else:
            with pytest.raises(ValidationError):
                ResearchStrategyConfiguration.model_validate(value)


def test_new_mode_allows_fixed_nodes_once_and_policy_v1_monitor_only():
    policy = collection.configured_collection_policy({
        "YIKE_PILOT_COLLECTION_MODE": "four-platform-public-node-monitor-v1"})
    for source in ("v2ex-latest-v1", "v2ex-qna-v1"):
        once = configuration(publicSource=source)
        assert policy("PUBLIC_WEB", "PUBLIC_ANONYMOUS", once)
        monitored = once | {"mode": "monitor", "schedule": schedule()}
        original = deepcopy(monitored)
        assert policy("PUBLIC_WEB", "PUBLIC_ANONYMOUS", monitored)
        assert monitored == original
        assert not policy("PUBLIC_WEB", "PUBLIC_ANONYMOUS", monitored | {
            "schedule": schedule() | {"policyVersion": 2}})


@pytest.mark.parametrize("change", [
    {"source": "links", "links": ["https://www.v2ex.com/t/1"]},
    {"research": {"version": 1, "demandTypes": ["INQUIRY"], "maxSoubei": 10,
                  "limits": {"sources": 10, "minutes": 10, "modelCalls": 10},
                  "stopAtAnyLimit": True, "evidenceOrder": "SOURCE_MATCH_CONTEXT"}},
    {"publicSource": None},
])
def test_new_mode_rejects_links_research_and_missing_node(change):
    policy = collection.configured_collection_policy({
        "YIKE_PILOT_COLLECTION_MODE": "four-platform-public-node-monitor-v1"})
    assert not policy("PUBLIC_WEB", "PUBLIC_ANONYMOUS", configuration(**change))
    assert not policy("PUBLIC_WEB", "PLATFORM_ACCOUNT", configuration(**change))


def test_old_modes_remain_closed_to_qna():
    for mode in ("four-platform-public-monitor-v1", "four-platform-public-sampling-monitor-v1"):
        policy = collection.configured_collection_policy({"YIKE_PILOT_COLLECTION_MODE": mode})
        assert not policy("PUBLIC_WEB", "PUBLIC_ANONYMOUS", configuration())


def test_new_mode_support_advertises_closed_catalog_and_monitor_guard():
    policy = collection.configured_collection_policy({
        "YIKE_PILOT_COLLECTION_MODE": "four-platform-public-node-monitor-v1"})
    service = runtime(policy)
    expected_sources = ["v2ex-latest-v1", "v2ex-qna-v1"]
    assert collection.foreground_collection_support(service, "claims") == {
        "schema_version": "foreground-collection-support-v1",
        "mode": "four-platform-foreground-v1",
        "public_source": "v2ex-latest-v1",
        "public_sources": expected_sources,
        "public_monitor": True,
    }
    assert MonitorRuntime(service.database, service).support("claims") == {
        "schema_version": "monitor-runtime-support-v1",
        "mode": "four-platform-monitor-v1",
        "public_source": "v2ex-latest-v1",
        "public_sources": expected_sources,
    }


def test_new_mode_delegates_native_platforms_to_existing_four_platform_monitor_policy():
    policy = collection.configured_collection_policy({
        "YIKE_PILOT_COLLECTION_MODE": "four-platform-public-node-monitor-v1"})
    for platform in ("XIAOHONGSHU", "DOUYIN", "BILIBILI", "ZHIHU"):
        for value in (configuration(publicSource=None),
                      configuration(publicSource=None, mode="monitor", schedule=schedule())):
            assert policy(platform, "PLATFORM_ACCOUNT", value) == \
                collection.four_platform_monitor_policy(platform, "PLATFORM_ACCOUNT", value)

