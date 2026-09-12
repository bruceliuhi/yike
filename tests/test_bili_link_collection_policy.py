from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace

import pytest

from pilot.foreground_collection import configured_collection_policy, foreground_collection_support
from pilot.monitor_runtime import MonitorRuntime
from tests.test_foreground_collection import config

MODE = 'four-platform-public-bili-links-monitor-v1'
URL = 'https://www.bilibili.com/video/BV1xx411c7mD'


def policy():
    return configured_collection_policy({'YIKE_PILOT_COLLECTION_MODE': MODE})


@pytest.mark.parametrize('monitor', [False, True])
def test_links_policy_supports_bounded_bili_once_and_monitor_preserving_snapshot(monitor):
    data = config() | dict(source='links', keywords=[], links=[URL, 'https://space.bilibili.com/123'])
    if monitor:
        data.update(mode='monitor', schedule=dict(kind='daily',times=['09:30'],interval=2,
            start='09:00',end='18:00',timezone='Asia/Shanghai',policyVersion=1))
    original = deepcopy(data)
    assert policy()('BILIBILI','PLATFORM_ACCOUNT',data)
    assert data == original
    for platform in ('DOUYIN','XIAOHONGSHU','ZHIHU','PUBLIC_WEB'):
        assert not policy()(platform, 'PLATFORM_ACCOUNT', data)
    assert not policy()('BILIBILI','PUBLIC_ANONYMOUS',data)


@pytest.mark.parametrize('links', [[URL, URL+'/?tracking=1'], ['https://www.douyin.com/video/123'],
    [URL, 'https://www.douyin.com/video/123'], [URL.replace('BV1','BV0')]])
def test_bad_or_unsupported_link_plan_is_not_advertised_as_runnable(links):
    data = config() | dict(source='links',keywords=[],links=links)
    assert not policy()('BILIBILI','PLATFORM_ACCOUNT',data)


def test_search_and_fixed_public_sources_remain_supported():
    for platform in ('BILIBILI','DOUYIN','XIAOHONGSHU','ZHIHU'):
        assert policy()(platform,'PLATFORM_ACCOUNT',config())
    for source in ('v2ex-latest-v1','v2ex-qna-v1','v2ex-outsourcing-authors-v1'):
        assert policy()('PUBLIC_WEB','PUBLIC_ANONYMOUS',config() | {'publicSource':source})


def test_authenticated_support_exposes_only_opted_in_bili_links():
    calls = []
    database = SimpleNamespace(connect=lambda: nullcontext(SimpleNamespace(cursor=lambda: nullcontext(object()))))
    runtime = SimpleNamespace(database=database, capability_check=policy(), _active=lambda *args: calls.append(1))
    foreground = foreground_collection_support(runtime,'claims')
    monitor = MonitorRuntime(database, runtime).support('claims')
    assert foreground['native_links'] == monitor['native_links'] == ['BILIBILI']
    assert foreground['mode'] == monitor['mode'] == MODE
    assert foreground['public_sources'] == monitor['public_sources'] == ['v2ex-latest-v1','v2ex-qna-v1','v2ex-outsourcing-authors-v1']
    assert len(calls) == 4
    runtime.capability_check = configured_collection_policy({'YIKE_PILOT_COLLECTION_MODE':'four-platform-public-project-monitor-v1'})
    assert 'native_links' not in foreground_collection_support(runtime,'claims')
    assert 'native_links' not in MonitorRuntime(database, runtime).support('claims')
