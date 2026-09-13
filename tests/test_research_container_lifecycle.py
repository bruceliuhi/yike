import importlib
import json
import os
import io
import threading
from time import time
from types import SimpleNamespace

import pytest


@pytest.fixture
def broker(tmp_path, monkeypatch):
    module = importlib.import_module('pilot.research_container_broker')
    monkeypatch.setattr(module, '_RUNTIME_UID', os.getuid())
    root = tmp_path.resolve()
    root.chmod(0o700)
    return module.TaskContainerBroker(image='sha256:'+'a'*64, tasks_root=root,
                                      ledger_root=root/'ledger')


def identity():
    return dict(tenant_id='00000000-0000-4000-8000-000000000001',
        task_id='00000000-0000-4000-8000-000000000002',
        run_id='00000000-0000-4000-8000-000000000003', generation=1)


def reserve(broker, key, expiry):
    path = broker.ledger_root/(key+'.json')
    path.write_text(json.dumps(dict(key=key, image=broker.image, expires_at=expiry)))
    path.chmod(0o600)


def test_deadline_reconcile_marks_stop_and_kills_running(broker, monkeypatch):
    module = importlib.import_module('pilot.research_container_broker')
    key = module.task_key(identity())
    reserve(broker, key, time()-1)
    state = {'Status':'running','Running':True}
    monkeypatch.setattr(broker, '_inspect', lambda k: state.copy())
    def run(command):
        assert 'kill' in command
        state.update(Status='exited',Running=False)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(module, '_run', run)
    assert broker.reconcile()[0]['status'] == 'STOPPED'
    assert (broker.ledger_root/(key+'.cancelled')).exists()


def test_created_with_unknown_start_never_claims_stopped(broker, monkeypatch):
    module = importlib.import_module('pilot.research_container_broker')
    key = module.task_key(identity())
    reserve(broker, key, time()+20)
    (broker.ledger_root/(key+'.started')).touch(mode=0o600)
    monkeypatch.setattr(broker, '_inspect', lambda k: {'Status':'created','Running':False})
    assert broker.stop(identity())['status'] == 'UNKNOWN'
    assert broker.status(identity())['status'] == 'UNKNOWN'


def test_recovery_cancels_old_started_task(broker, monkeypatch):
    module = importlib.import_module('pilot.research_container_broker')
    key = module.task_key(identity())
    reserve(broker,key,time()+100)
    (broker.ledger_root/(key+'.started')).touch(mode=0o600)
    monkeypatch.setattr(broker,'_inspect', lambda k: {'Status':'exited','Running':False})
    assert broker.reconcile(recover=True)[0]['status']=='STOPPED'
    assert (broker.ledger_root/(key+'.cancelled')).exists()


def test_execute_requires_active_supervisor(broker):
    with pytest.raises(ValueError,match='supervisor_required'):
        broker.execute(identity(), {}, emit=lambda data: None)


@pytest.mark.parametrize('fail_drain', [False, True])
@pytest.mark.parametrize('exit_code,expected_code',[(0,None),(124,'timeout'),(130,'cancelled'),(1,'runtime_failed')])
def test_execute_streams_once_without_persisting_token(broker, monkeypatch, fail_drain,exit_code,expected_code):
    module = importlib.import_module('pilot.research_container_broker')
    key = module.task_key(identity())
    reserve(broker, key, time()+20)
    state = {'Status':'created','Running':False}
    monkeypatch.setattr(broker,'_inspect', lambda k: state.copy())
    captured = {}
    class Input(io.BytesIO):
        def close(self):
            if not self.closed:
                captured['input'] = self.getvalue()
            super().close()
    class Process:
        pid = 123
        returncode = exit_code
        def __init__(self, command, **kwargs):
            captured['command'] = command
            captured['env'] = kwargs['env']
            self.stdin = Input()
            self.stdout = io.BytesIO(b'{"event":"synthetic"}\n')
            state.update(Status='exited',Running=False)
        def poll(self):
            return exit_code
        def wait(self, timeout=None):
            return exit_code
    monkeypatch.setattr(module.subprocess,'Popen',Process)
    monkeypatch.setattr(importlib.import_module('pilot.research_container_lifecycle'),
                        '_kill_group',lambda p: None)
    manifest = dict(version=1,model='qwen-test',token='synthetic-task-token',mission='buyer demand',
        instructions='use citations',entry_urls=[],max_reads=1,max_requests=1,
        max_searches=1,max_seconds=10,expires_at=time()+10)
    output = []
    with broker:
        if fail_drain:
            original_start = threading.Thread.start
            def start_thread(thread):
                if getattr(thread._target, '__name__', '') == 'drain':
                    raise RuntimeError('thread unavailable')
                return original_start(thread)
            monkeypatch.setattr(threading.Thread, 'start', start_thread)
            with pytest.raises(RuntimeError):
                broker.execute(identity(),manifest,emit=output.append)
            assert broker._slots.acquire(blocking=False)
            assert broker._slots.acquire(blocking=False)
            return
        result=broker.execute(identity(),manifest,emit=output.append)
        assert result['status']=='STOPPED'
        assert result['code']==expected_code
        with pytest.raises(ValueError,match='task_not_startable'):
            broker.execute(identity(),manifest,emit=output.append)
    assert b''.join(output) == b'{"event":"synthetic"}\n'
    assert json.loads(captured['input'])['token'] == 'synthetic-task-token'
    assert captured['command'] == ['docker','start','--attach','--interactive','yike-r-'+key]
    assert 'synthetic-task-token' not in str(captured['env'])
    assert all(b'synthetic-task-token' not in p.read_bytes() for p in broker.ledger_root.iterdir())


def test_duplicate_start_loser_cannot_cancel_winner(broker, monkeypatch):
    module = importlib.import_module('pilot.research_container_broker')
    key = module.task_key(identity())
    reserve(broker,key,time()+20)
    manifest = dict(version=1,model='qwen-test',token='synthetic-token',mission='buyer',
        instructions='cite',entry_urls=[],max_reads=1,max_requests=1,
        max_searches=1,max_seconds=10,expires_at=time()+10)
    with broker:
        (broker.ledger_root/(key+'.started')).touch(mode=0o600)
        monkeypatch.setattr(broker,'status',lambda identity: {'status':'CREATED'})
        with pytest.raises(ValueError,match='task_not_startable'):
            broker.execute(identity(),manifest,emit=lambda data:None)
        assert not (broker.ledger_root/(key+'.cancelled')).exists()


def test_watchdog_reaps_without_execution_polling(broker, monkeypatch):
    module = importlib.import_module('pilot.research_container_broker')
    key = module.task_key(identity())
    reserve(broker,key,time()+.2)
    reaped = threading.Event()
    def stop(k):
        assert k == key
        reaped.set()
        return {'key':k,'status':'STOPPED'}
    monkeypatch.setattr(broker,'_stop_key',stop)
    with broker:
        assert reaped.wait(2)


def test_reconcile_prioritizes_active_and_bounds_history(broker, monkeypatch):
    module = importlib.import_module('pilot.research_container_broker')
    active = module.task_key(identity())
    reserve(broker,active,time()-1)
    monkeypatch.setattr(broker,'_active',{active},raising=False)
    terminal = '0'*64
    reserve(broker,terminal,time()-1)
    (broker.ledger_root/(terminal+'.terminal')).touch(mode=0o600)
    for i in range(1,6):
        reserve(broker,str(i)*64,time()-1)
    calls=[]
    monkeypatch.setattr(broker,'_stop_key',lambda k:calls.append(k) or {'key':k,'status':'UNKNOWN'})
    broker.reconcile()
    assert calls[0] == active
    assert len(calls) == 2
    assert terminal not in calls


def test_unconfirmed_stop_blocks_new_tasks_without_restart(broker, monkeypatch):
    module = importlib.import_module('pilot.research_container_broker')
    key = module.task_key(identity())
    reserve(broker,key,time()+20)
    manifest = dict(version=1,model='qwen-test',token='synthetic-token',mission='buyer',
        instructions='cite',entry_urls=[],max_reads=1,max_requests=1,
        max_searches=1,max_seconds=10,expires_at=time()+10)
    monkeypatch.setattr(broker,'status',lambda identity: {'status':'CREATED'})
    monkeypatch.setattr(broker,'_stop_key',lambda k:{'key':k,'status':'UNKNOWN'})
    with broker:
        assert broker.execute(identity(),manifest,emit=lambda d:None,
                              cancelled=lambda:True)['status']=='UNKNOWN'
        assert key in broker._active
        with pytest.raises(ValueError,match='broker_recovery_pending'):
            broker.execute(identity() | {'generation':2},manifest,emit=lambda d:None)


@pytest.mark.parametrize('shutdown', [False, True])
def test_recovery_is_rechecked_after_slow_status(broker, monkeypatch, shutdown):
    module = importlib.import_module('pilot.research_container_broker')
    reserve(broker,module.task_key(identity()),time()+20)
    manifest = dict(version=1,model='qwen-test',token='synthetic-token',mission='buyer',
        instructions='cite',entry_urls=[],max_reads=1,max_requests=1,
        max_searches=1,max_seconds=10,expires_at=time()+10)
    with broker:
        def status(_):
            if shutdown:
                broker._halt.set()
            else:
                broker._recovery_keys.add('f'*64)
            return {'status':'CREATED'}
        def mark(*args):
            raise AssertionError('must not reserve after recovery became pending')
        monkeypatch.setattr(broker,'status',status)
        monkeypatch.setattr(broker,'_mark',mark)
        with pytest.raises(ValueError,match='supervisor_required' if shutdown else 'broker_recovery_pending'):
            broker.execute(identity(),manifest,emit=lambda d:None)


def test_shutdown_waits_for_start_handoff(broker, monkeypatch):
    module=importlib.import_module('pilot.research_container_lifecycle')
    core=importlib.import_module('pilot.research_container_broker')
    reserve(broker,core.task_key(identity()),time()+20)
    entered,release,closing = threading.Event(),threading.Event(),threading.Event()
    state={'Status':'created','Running':False}
    monkeypatch.setattr(broker,'_inspect',lambda k:state.copy())
    class Process:
        pid=123
        returncode=0
        def __init__(self,*args,**kwargs):
            entered.set()
            assert release.wait(3)
            self.stdin,self.stdout=io.BytesIO(),io.BytesIO()
            state.update(Status='exited',Running=False)
        def poll(self):
            return 0
        def wait(self,timeout=None):
            return 0
    monkeypatch.setattr(module.subprocess,'Popen',Process)
    monkeypatch.setattr(module,'_kill_group',lambda p:None)
    manifest=dict(version=1,model='qwen-test',token='synthetic-token',mission='buyer',
        instructions='cite',entry_urls=[],max_reads=1,max_requests=1,
        max_searches=1,max_seconds=10,expires_at=time()+10)
    errors=[]
    def execute():
        try:
            broker.execute(identity(),manifest,emit=lambda d:None)
        except Exception as error:
            errors.append(error)
    def close():
        closing.set()
        broker.__exit__()
    broker.__enter__()
    task=threading.Thread(target=execute)
    shutdown_thread=threading.Thread(target=close)
    try:
        task.start()
        assert entered.wait(2)
        shutdown_thread.start()
        assert closing.wait(2)
        assert not broker._halt.wait(.1)
    finally:
        release.set()
        task.join(3)
        shutdown_thread.join(3)
    assert not errors
