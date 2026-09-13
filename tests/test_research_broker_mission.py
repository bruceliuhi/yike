import importlib
import json
from pathlib import Path
import tempfile
import threading
from time import monotonic, time

import pytest

from tests.test_codex_research_worker import (
    research_context, search_event, read_event, citation_read_event, citation_final_events,
    final_events,
)


def test_controlled_mission_uses_broker_without_local_executable(monkeypatch):
    worker=importlib.import_module('pilot.codex_research_worker')
    backend_module=importlib.import_module('pilot.research_broker_mission')
    identity=dict(tenant_id='00000000-0000-4000-8000-000000000001',
        task_id='00000000-0000-4000-8000-000000000002',
        run_id='00000000-0000-4000-8000-000000000003',generation=1)
    captured={}
    event=citation_read_event(read_event())
    data=b''.join(json.dumps(item,ensure_ascii=False).encode()+b'\n'
                  for item in [search_event(),event,*citation_final_events(event)])
    class Client:
        def create(self, value, *, expires_at):
            assert value==identity
            return {'status':'CREATED'}
        def events(self, value, manifest):
            captured.update(manifest)
            yield {'type':'heartbeat'}
            yield {'type':'chunk','data':data[:37]}
            yield {'type':'chunk','data':data[37:]}
            yield {'type':'result','value':{'status':'STOPPED','code':None}}
        def stop(self, value):
            raise AssertionError('verified terminal should not need another stop')
    def no_local(*args,**kwargs):
        raise AssertionError('must not fall back to local execution')
    monkeypatch.setattr(worker,'_execute',no_local)
    with tempfile.TemporaryDirectory(prefix='b',dir='/tmp') as directory:
        backend=backend_module.BrokerMissionExecution(identity,Client(),Path(directory).resolve())
        result=worker.run_public_research_mission('研究公开需求。',
            codex_binary='/missing/codex',python_binary='/missing/python',
            api_key='synthetic-provider-key',search_api_key='synthetic-search-key',
            model='test-model',research_context=research_context(),max_seconds=10,
            effect_dispatcher=lambda kind,payload,deadline,perform:perform(deadline),
            broker_execution=backend)
        assert result['status']=='COMPLETED'
        assert result['reads']
    serialized=json.dumps(captured)
    assert 'synthetic-provider-key' not in serialized and 'synthetic-search-key' not in serialized
    assert captured['mission'].startswith('HOST_RESEARCH_CONTEXT_JSON')
    assert captured['instructions'] and captured['token']


def test_abort_fences_effects_before_stop_and_preserves_unknown():
    module=importlib.import_module('pilot.research_broker_mission')
    identity=dict(tenant_id='00000000-0000-4000-8000-000000000001',
        task_id='00000000-0000-4000-8000-000000000002',
        run_id='00000000-0000-4000-8000-000000000003',generation=1)
    revoked,stopped=threading.Event(),threading.Event()
    class Client:
        def create(self,*args,**kwargs):
            return {'status':'CREATED'}
        def events(self,*args):
            stopped.wait(2)
            return
            yield
        def stop(self,*args):
            assert revoked.is_set()
            stopped.set()
            return {'status':'UNKNOWN'}
    backend=module.BrokerMissionExecution(identity,Client(),'/unused')
    assert backend.execute({'expires_at':time()+5},deadline=monotonic()+5,
        cancelled=lambda:True,events=object(),revoke=revoked.set)==('FAILED','broker_stop_unknown')


@pytest.mark.parametrize(('search_completed','expected_code'), [
    (False,'no_verified_reads'), (True,'no_verified_reads'), (True,'runtime_failed'),
])
def test_terminal_broker_failure_does_not_start_host_fallback(monkeypatch, search_completed, expected_code):
    worker=importlib.import_module('pilot.codex_research_worker')
    backend_module=importlib.import_module('pilot.research_broker_mission')
    identity=dict(tenant_id='00000000-0000-4000-8000-000000000001',
        task_id='00000000-0000-4000-8000-000000000002',
        run_id='00000000-0000-4000-8000-000000000003',generation=1)
    frames=[search_event()] if search_completed else []
    frames.extend([{'type':'turn.failed'}] if expected_code=='runtime_failed' else final_events())
    data=b''.join(json.dumps(item).encode()+b'\n' for item in frames)
    class Client:
        def create(self, value, *, expires_at):
            return {'status':'CREATED'}
        def events(self, value, manifest):
            yield {'type':'chunk','data':data}
            yield {'type':'result','value':{'status':'STOPPED','code':None}}
        def stop(self, value):
            raise AssertionError('confirmed terminal must not be restarted or stopped again')
    attempted=[]
    original_search=worker.PublicSearchSession.search
    def record_search(session, query):
        attempted.append(query)
        return original_search(session, query)
    monkeypatch.setattr(worker.PublicSearchSession,'search',record_search)
    backend=backend_module.BrokerMissionExecution(identity,Client(),'/unused')
    # Use the actual bridge's loopback transport so the lifecycle test is portable;
    # filesystem/Unix socket binding has separate integration coverage above.
    monkeypatch.setattr(backend,'prepare_socket',lambda:None)
    effects=[]
    def dispatch(kind, payload, deadline, perform):
        effects.append(kind)
        raise AssertionError('no provider effect is allowed after terminal broker output')
    result=worker.run_public_research_mission('研究公开需求。',
        codex_binary='/missing/codex',python_binary='/missing/python',
        api_key='synthetic-provider-key',search_api_key='synthetic-search-key',
        model='test-model',research_context=research_context(),max_seconds=10,
        effect_dispatcher=dispatch,broker_execution=backend)
    assert attempted==[], 'terminal research must not initiate an unplanned host fallback'
    assert effects==[]
    assert (result['status'],result['code'])==('FAILED',expected_code)
    assert result['reads']==[]


def test_confirmed_broker_terminal_revokes_before_return():
    worker=importlib.import_module('pilot.codex_research_worker')
    module=importlib.import_module('pilot.research_broker_mission')
    identity=dict(tenant_id='00000000-0000-4000-8000-000000000001',
        task_id='00000000-0000-4000-8000-000000000002',
        run_id='00000000-0000-4000-8000-000000000003',generation=1)
    class Client:
        def create(self,*args,**kwargs): return {'status':'CREATED'}
        def events(self,*args):
            yield {'type':'chunk','data':b'{"type":"turn.completed"}\n'}
            yield {'type':'result','value':{'status':'STOPPED','code':None}}
        def stop(self,*args):
            raise AssertionError('confirmed terminal does not need another stop')
    revoked=threading.Event()
    result=module.BrokerMissionExecution(identity,Client(),'/unused').execute(
        {'expires_at':time()+5},deadline=monotonic()+5,cancelled=lambda:False,
        events=worker._ReadEvents(search_enabled=False),revoke=revoked.set)
    assert result==('FAILED','no_verified_reads')
    assert revoked.is_set(), 'confirmed terminal must fence effects before returning to caller'
