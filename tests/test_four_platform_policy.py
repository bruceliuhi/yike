from contextlib import nullcontext
from types import SimpleNamespace

from pilot.foreground_collection import configured_collection_policy, foreground_collection_support
from pilot.monitor_runtime import MonitorRuntime


def configuration(mode='once'):
    return dict(schema_version='research-strategy-v1', name='需求', source='search', keywords=['知识库'],
        exclusions=['招聘'], links=[], mode=mode, research=None, schedule=None if mode=='once' else
        dict(kind='daily',times=['09:30'],interval=2,start='09:00',end='18:00',timezone='Asia/Shanghai',policyVersion=1))


def test_four_platform_opt_in_preserves_old_modes_and_configuration_boundaries():
    for mode in ('four-platform-foreground-v1','four-platform-monitor-v1'):
        policy=configured_collection_policy({'YIKE_PILOT_COLLECTION_MODE':mode})
        for platform in ('XIAOHONGSHU','DOUYIN','BILIBILI','ZHIHU'):
            assert policy(platform,'PLATFORM_ACCOUNT',configuration())
            assert policy(platform,'PLATFORM_ACCOUNT',configuration('monitor')) == ('monitor' in mode)
        assert not policy('PUBLIC_WEB','PUBLIC_ANONYMOUS',configuration())
        assert not policy('ZHIHU','PUBLIC_ANONYMOUS',configuration())
        assert not policy('ZHIHU','PLATFORM_ACCOUNT',configuration() | {'keywords':['a,b']})
        assert not policy('ZHIHU','PLATFORM_ACCOUNT',configuration() | {'source':'links','links':['https://example.org']})
    for mode in ('xhs-foreground-v1','three-platform-foreground-v1','three-platform-monitor-v1'):
        assert not configured_collection_policy({'YIKE_PILOT_COLLECTION_MODE':mode})('ZHIHU','PLATFORM_ACCOUNT',configuration())


def test_four_platform_support_is_explicit_and_authenticated():
    calls=[]
    database=SimpleNamespace(connect=lambda:nullcontext(SimpleNamespace(cursor=lambda:nullcontext(object()))))
    runtime=SimpleNamespace(database=database,_active=lambda *_:calls.append(True))
    for mode in ('four-platform-foreground-v1','four-platform-monitor-v1'):
        runtime.capability_check=configured_collection_policy({'YIKE_PILOT_COLLECTION_MODE':mode})
        assert foreground_collection_support(runtime,'claims')['mode']=='four-platform-foreground-v1'
        assert MonitorRuntime(database,runtime).support('claims')['mode']==(mode if 'monitor' in mode else None)
    assert len(calls)==8
