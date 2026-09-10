import pytest
from pilot.foreground_collection import foreground_collection_policy, configured_collection_policy


def config():
    return dict(schema_version='research-strategy-v1',name='原文',source='search',keywords=['设计'],exclusions=[],links=[],mode='once',schedule=None,research=None)


def test_only_explicit_named_configuration_enables_policy():
    assert configured_collection_policy({}) is None
    assert configured_collection_policy({'YIKE_PILOT_COLLECTION_MODE':'xhs-foreground-v1'}) is foreground_collection_policy
    with pytest.raises(RuntimeError,match='invalid_collection_configuration'):
        configured_collection_policy({'YIKE_PILOT_COLLECTION_MODE':'all'})


def test_supported_normal_xhs_once_search_configuration():
    assert foreground_collection_policy('XIAOHONGSHU','PLATFORM_ACCOUNT',config()) is True


@pytest.mark.parametrize('key,value',[('source','links'),('links',['https://example.org']),('exclusions',['招聘']),('mode','monitor'),('schedule',{}),('research',{}),('keywords',['设计,搭建']),('keywords',[]),('keywords',[' 设计']),('keywords',['\n']),('extra',True)])
def test_unsupported_configuration_is_never_enabled(key,value):
    value_config=config();value_config[key]=value
    assert foreground_collection_policy('XIAOHONGSHU','PLATFORM_ACCOUNT',value_config) is False


@pytest.mark.parametrize('platform,mode',[('DOUYIN','PLATFORM_ACCOUNT'),('BILIBILI','PLATFORM_ACCOUNT'),('XIAOHONGSHU','PUBLIC_ANONYMOUS')])
def test_no_other_platform_or_access_mode_enabled(platform,mode):
    assert foreground_collection_policy(platform,mode,config()) is False


def test_support_is_authenticated_and_only_reports_explicit_bounded_policy():
    from contextlib import nullcontext
    from types import SimpleNamespace
    from pilot.foreground_collection import foreground_collection_support
    calls = []
    cursor = object()
    runtime = SimpleNamespace(database=SimpleNamespace(connect=lambda: nullcontext(SimpleNamespace(cursor=lambda: nullcontext(cursor)))),
                              _active=lambda c, claims: calls.append((c,claims)), capability_check=foreground_collection_policy)
    assert foreground_collection_support(runtime,'claims') == {'schema_version':'foreground-collection-support-v1','mode':'xhs-foreground-v1'}
    assert calls == [(cursor,'claims'),(cursor,'claims')]
    runtime.capability_check = lambda *args: True
    assert foreground_collection_support(runtime,'claims')['mode'] is None


def test_support_rejects_revoked_session_at_final_fence():
    from contextlib import nullcontext
    from types import SimpleNamespace
    from pilot.foreground_collection import foreground_collection_support
    calls = []
    def active(*args):
        calls.append(1)
        if len(calls) == 2: raise PermissionError()
    runtime = SimpleNamespace(database=SimpleNamespace(connect=lambda: nullcontext(SimpleNamespace(cursor=lambda: nullcontext(object())))),
                              _active=active, capability_check=foreground_collection_policy)
    with pytest.raises(PermissionError): foreground_collection_support(runtime,'claims')


def test_monitor_policy_is_explicit_versioned_and_preserves_once():
    from copy import deepcopy
    from pilot.foreground_collection import three_platform_monitor_policy, three_platform_collection_policy
    schedule = dict(kind='daily', times=['09:30'], interval=2, start='09:00', end='18:00',
                    timezone='Asia/Shanghai', policyVersion=1)
    value = config() | {'mode': 'monitor', 'schedule': schedule}
    original = deepcopy(value)
    assert configured_collection_policy({'YIKE_PILOT_COLLECTION_MODE': 'three-platform-monitor-v1'}) is three_platform_monitor_policy
    for platform in ('XIAOHONGSHU', 'DOUYIN', 'BILIBILI'):
        assert three_platform_monitor_policy(platform, 'PLATFORM_ACCOUNT', value)
        assert three_platform_monitor_policy(platform, 'PLATFORM_ACCOUNT', config())
        assert not three_platform_collection_policy(platform, 'PLATFORM_ACCOUNT', value)
    assert value == original  # Capability validation never rewrites confirmed intent.
    for replacement in (None, schedule | {'policyVersion': True}, {k: v for k, v in schedule.items() if k != 'policyVersion'}):
        assert not three_platform_monitor_policy('XIAOHONGSHU', 'PLATFORM_ACCOUNT', value | {'schedule': replacement})
    assert not three_platform_monitor_policy('PUBLIC_WEB', 'PUBLIC_ANONYMOUS', value)
    assert not three_platform_monitor_policy('XIAOHONGSHU', 'PLATFORM_ACCOUNT', value | {'exclusions': ['招聘']})
