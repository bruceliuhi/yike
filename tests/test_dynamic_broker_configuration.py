import pytest
from types import SimpleNamespace

from tests.test_dynamic_research_config import base_environment, BoundedModel


def environment():
    return base_environment() | {
        'YIKE_PILOT_RESEARCH_AGENT_BROKER_SOCKET':'/run/yike/control.sock',
        'YIKE_PILOT_RESEARCH_AGENT_TASKS_ROOT':'/run/yike/tasks',
        'YIKE_PILOT_RESEARCH_AGENT_API_KEY':'synthetic-provider-key',
        'YIKE_PILOT_RESEARCH_AGENT_SEARCH_API_KEY':'synthetic-search-key',
        'YIKE_PILOT_RESEARCH_AGENT_MODEL':'qwen-test',
    }


def test_explicit_broker_config_does_not_require_host_binaries():
    from pilot.research_runtime_config import research_configuration
    value=research_configuration(environment(),model=BoundedModel(),auth_secret='s'*32).dynamic_agent
    assert value.broker_socket=='/run/yike/control.sock'
    assert value.tasks_root=='/run/yike/tasks'
    assert value.codex_binary=='/opt/codex/bin/codex'
    assert value.python_binary=='/app/.venv/bin/python'
    assert 'synthetic-provider-key' not in repr(value)


@pytest.mark.parametrize('patch', [
    {'YIKE_PILOT_RESEARCH_AGENT_TASKS_ROOT':''},
    {'YIKE_PILOT_RESEARCH_AGENT_TASKS_ROOT':'../tasks'},
    {'YIKE_PILOT_RESEARCH_AGENT_CODEX_BINARY':'/bin/sh'},
    {'YIKE_PILOT_RESEARCH_AGENT_API_KEY':''},
])
def test_partial_or_mixed_broker_config_fails_closed(patch):
    from pilot.research_runtime_config import research_configuration
    with pytest.raises(RuntimeError,match='invalid_research_configuration'):
        research_configuration(environment() | patch,model=BoundedModel(),auth_secret='s'*32)


def test_mission_identity_comes_from_elected_tenant_and_run():
    from pilot.dynamic_research_runtime import DynamicResearchRuntimeService
    service=object.__new__(DynamicResearchRuntimeService)
    client=object()
    service._broker_client=client
    service.agent=SimpleNamespace(tasks_root='/run/yike/tasks')
    tenant='00000000-0000-4000-8000-000000000001'
    task='00000000-0000-4000-8000-000000000002'
    run='00000000-0000-4000-8000-000000000003'
    result=service._mission_options({'tenant_id':tenant},task,run,7)['broker_execution']
    assert result.identity==dict(tenant_id=tenant,task_id=task,run_id=run,generation=7)
    assert result.client is client
    assert str(result.root)=='/run/yike/tasks'
    with pytest.raises(KeyError):
        service._mission_options({},task,run,7)


def test_runtime_assembly_uses_configured_private_broker(monkeypatch):
    from pilot import dynamic_research_runtime
    from pilot.runtime import build_runtime_app
    from pilot.research_runtime import ResearchRuntimeService
    from tests.test_pilot_runtime import _route_service
    client=object()
    sockets=[]
    def connect(path):
        sockets.append(path)
        return client
    monkeypatch.setattr(dynamic_research_runtime,'BrokerClient',connect)
    app=build_runtime_app(object(),auth_secret='s'*32,environment=environment() | {
        'YIKE_PILOT_ASSESSMENT_BASE_URL':'https://model.example/v1',
        'YIKE_PILOT_ASSESSMENT_API_KEY':'synthetic-assessment-key',
        'YIKE_PILOT_ASSESSMENT_MODEL':'synthetic/model-v1',
    })
    runtime=_route_service(app,'/api/ui/research-execution/capability',ResearchRuntimeService)
    try:
        assert runtime.dynamic._broker_client is client
        assert sockets==['/run/yike/control.sock']
    finally:
        runtime.dynamic.shutdown()


@pytest.mark.parametrize('code',['broker_stop_unknown','broker_stream_unknown'])
def test_cancel_does_not_overwrite_broker_unknown(monkeypatch,code):
    from pilot import dynamic_research_runtime as module
    service=object.__new__(module.DynamicResearchRuntimeService)
    service.execution=object()
    service.journal=object()
    service.owner='owner'
    service._broker_client=None
    service.agent=SimpleNamespace(codex_binary='',python_binary='',api_key='',model='',search_api_key='')
    monkeypatch.setattr(module,'CustomerResearchContextStore',lambda _: SimpleNamespace(
        load=lambda *a,**k: {'binding':'binding','context_json':'{"seller_description":"test"}'}))
    monkeypatch.setattr(module,'DurableResearchDispatcher',lambda *a,**k: object())
    service.mission=lambda *a,**k: {'status':'FAILED','code':code}
    service._cancelled=lambda *a: True
    settled=[]
    released=[]
    service._settle_cancellation=lambda *a: settled.append(a)
    service._release_if_owned=lambda *a: released.append(a)
    service._run('claims','task','run',7,{'sources':5,'modelCalls':20,'maxRecords':2,'seconds':30})
    assert not settled
    assert released==[('claims','task',7,'STOPPED',code)]
