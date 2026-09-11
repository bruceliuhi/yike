"""Opt-in policy/serialization only; synthetic configuration, no platform or PG."""
from contextlib import nullcontext
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

from fastapi import FastAPI
import pytest
from pydantic import ValidationError

from pilot import foreground_collection as collection
from pilot.monitor_runtime import MonitorRuntime
from pilot.research_strategy_contract import (
    PrepareStrategyRequest, ResearchStrategyConfiguration, configuration_digest,
    strategy_snapshot,
)


def config():
    return dict(schema_version='research-strategy-v1', name='近期主题', source='search',
                keywords=['需求'], exclusions=['招聘'], links=[], mode='once', schedule=None, research=None)


def schedule():
    return dict(kind='daily', times=['09:30'], interval=2, start='09:00', end='18:00',
                timezone='Asia/Shanghai', policyVersion=1)


def public_policy():
    try:
        return collection.configured_collection_policy({'YIKE_PILOT_COLLECTION_MODE': 'four-platform-public-monitor-v1'})
    except RuntimeError:
        pytest.fail('explicit public collection policy must be configurable')


def runtime(policy):
    calls = []
    database = SimpleNamespace(connect=lambda: nullcontext(SimpleNamespace(cursor=lambda: nullcontext(object()))))
    return SimpleNamespace(database=database, _active=lambda *_: calls.append(True), capability_check=policy), calls


@pytest.mark.parametrize('industry', [False, True])
def test_public_source_roundtrip_does_not_rewrite_legacy_nested_hashes(industry):
    old = config()
    if industry:
        old['industryStrategy'] = dict(version='industry-task-strategy-v1', sourceTypes=['SOCIAL_POST'],
                                       intentSignals=['采购'], counterSignals=['招聘'])
    identifiers = dict(profile_version_id='11111111-1111-4111-8111-111111111111',
                       strategy_version_id='22222222-2222-4222-8222-222222222222',
                       platforms=['PUBLIC_WEB'], max_records=10, max_runtime_seconds=30)
    expected = identifiers | {'configuration': old}
    original = strategy_snapshot(configuration=old, **identifiers)
    assert original == expected
    expected_bytes = json.dumps(expected, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    assert configuration_digest(original) == hashlib.sha256(expected_bytes).hexdigest()
    modern = old | {'publicSource': 'v2ex-latest-v1'}
    try:
        modern_snapshot = strategy_snapshot(configuration=modern, **identifiers)
    except ValueError:
        pytest.fail('new publicSource must survive validated strategy snapshots')
    assert modern_snapshot == identifiers | {'configuration': modern}
    assert configuration_digest(modern_snapshot) != configuration_digest(original)
    request = dict(schema_version='strategy-confirmation-v1', request_id='33333333-3333-4333-8333-333333333333',
                   draft_id='44444444-4444-4444-8444-444444444444', draft_revision=1,
                   **{key: value for key, value in identifiers.items() if key != 'strategy_version_id'})
    for configuration in (old, modern):
        raw = request | {'configuration': configuration}
        model = PrepareStrategyRequest.model_validate(raw)
        assert model.model_dump(mode='json') == raw
        assert json.loads(model.model_dump_json()) == raw
        assert PrepareStrategyRequest.model_validate(model).model_dump(mode='json') == raw
    assert strategy_snapshot(configuration=old | {'publicSource': None}, **identifiers) == original


@pytest.mark.parametrize('source', ['other', '', 1, True, {}, ['v2ex-latest-v1']])
def test_public_source_is_a_closed_strict_literal(source):
    with pytest.raises(ValidationError):
        ResearchStrategyConfiguration.model_validate(config() | {'publicSource': source})


def test_public_policy_enables_only_explicit_bounded_anonymous_once_search():
    policy = public_policy()
    value = config() | {'publicSource': 'v2ex-latest-v1'}
    before = deepcopy(value)
    assert policy('PUBLIC_WEB', 'PUBLIC_ANONYMOUS', value) is True
    assert value == before
    assert not policy('PUBLIC_WEB', 'PLATFORM_ACCOUNT', value)
    assert not policy('PUBLIC_WEB', 'PUBLIC_WEB', value)
    assert not policy('PUBLIC_WEB', 'PUBLIC_ANONYMOUS', config())
    assert not policy('PUBLIC_WEB', 'PUBLIC_ANONYMOUS', value | {'publicSource': None})
    assert not policy('OTHER', 'PUBLIC_ANONYMOUS', value)


@pytest.mark.parametrize('change', [
    {'mode': 'monitor', 'schedule': schedule()}, {'schedule': schedule()},
    {'source': 'links', 'links': ['https://example.org']}, {'links': ['https://example.org']},
    {'research': {}}, {'keywords': []}, {'keywords': ['需求,服务']}, {'keywords': [' 需求']},
    {'keywords': ['\n']}, {'exclusions': ['需求']}, {'extra': True},
])
def test_public_policy_rejects_other_execution_surfaces(change):
    assert not public_policy()('PUBLIC_WEB', 'PUBLIC_ANONYMOUS', config() | {'publicSource': 'v2ex-latest-v1'} | change)


def test_new_policy_reuses_account_once_and_monitor_without_opening_old_public_modes():
    policy = public_policy()
    configurations = (config(), config() | {'mode': 'monitor', 'schedule': schedule()})
    for platform in ('XIAOHONGSHU', 'DOUYIN', 'BILIBILI', 'ZHIHU'):
        for configuration in configurations:
            assert policy(platform, 'PLATFORM_ACCOUNT', configuration) == collection.four_platform_monitor_policy(platform, 'PLATFORM_ACCOUNT', configuration)
            assert not policy(platform, 'PUBLIC_ANONYMOUS', configuration)
    for mode in ('xhs-foreground-v1', 'three-platform-foreground-v1', 'three-platform-monitor-v1',
                 'four-platform-foreground-v1', 'four-platform-monitor-v1'):
        old = collection.configured_collection_policy({'YIKE_PILOT_COLLECTION_MODE': mode})
        assert not old('PUBLIC_WEB', 'PUBLIC_ANONYMOUS', config() | {'publicSource': 'v2ex-latest-v1'})


def test_support_keeps_legacy_modes_and_only_new_policy_adds_public_source():
    value, calls = runtime(public_policy())
    assert collection.foreground_collection_support(value, 'claims') == {
        'schema_version': 'foreground-collection-support-v1', 'mode': 'four-platform-foreground-v1',
        'public_source': 'v2ex-latest-v1'}
    assert MonitorRuntime(value.database, value).support('claims') == {
        'schema_version': 'monitor-runtime-support-v1', 'mode': 'four-platform-monitor-v1'}
    assert len(calls) == 4
    value.capability_check = collection.four_platform_monitor_policy
    assert collection.foreground_collection_support(value, 'claims') == {
        'schema_version': 'foreground-collection-support-v1', 'mode': 'four-platform-foreground-v1'}


def test_ui_research_capability_lookup_uses_the_real_anonymous_access_mode(monkeypatch):
    from pilot.ui_api import register_ui_api
    from tests.test_ui_api import FakeStore
    captured = []
    monkeypatch.setattr('pilot.opportunity_research_api.register_opportunity_research_api',
                        lambda router, service, *_: captured.append(service))
    calls = []
    def check(platform, access_mode, configuration):
        calls.append((platform, access_mode, configuration))
        return platform == 'PUBLIC_WEB' and access_mode == 'PUBLIC_ANONYMOUS'
    register_ui_api(FastAPI(), FakeStore(), auth_secret='synthetic',
                    execution_runtime=SimpleNamespace(capability_check=check))
    value = config() | {'publicSource': 'v2ex-latest-v1'}
    assert captured[0].supported_platforms(value) == ['web']
    assert calls[-1] == ('PUBLIC_WEB', 'PUBLIC_ANONYMOUS', value)
    assert all(access == 'PLATFORM_ACCOUNT' for _, access, _ in calls[:-1])
