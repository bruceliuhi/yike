import importlib
import json
import os
import socket
import tempfile
from pathlib import Path
from types import SimpleNamespace
from time import time

import pytest


@pytest.fixture
def tmp_path():
    with tempfile.TemporaryDirectory(prefix='b', dir='/tmp') as directory:
        yield Path(directory).resolve()


def test_broker_reserves_once_and_verifies_stop(tmp_path, monkeypatch):
    module = importlib.import_module('pilot.research_container_broker')
    monkeypatch.setattr(module, '_RUNTIME_UID', os.getuid(), raising=False)
    identity = dict(tenant_id='00000000-0000-4000-8000-000000000001',
        task_id='00000000-0000-4000-8000-000000000002',
        run_id='00000000-0000-4000-8000-000000000003', generation=1)
    key = module.task_key(identity)
    tasks = tmp_path
    directory = tasks/key
    directory.mkdir(mode=0o700)
    commands = []
    state = {'value': 'created'}
    image = 'sha256:'+'a'*64
    def run(command):
        commands.append(command)
        if 'inspect' in command:
            value = {'state': {'Status': state['value'], 'Running': state['value']=='running'},
                     'labels': {'yike.research.key': key, 'yike.research.image': image}}
            return SimpleNamespace(returncode=0, stdout=json.dumps(value))
        if 'kill' in command:
            state['value'] = 'exited'
        return SimpleNamespace(returncode=0, stdout='')
    monkeypatch.setattr(module, '_run', run)
    with socket.socket(socket.AF_UNIX) as gateway:
        gateway.bind(str(directory/'bridge.sock'))
        broker = module.TaskContainerBroker(image=image, tasks_root=tasks, ledger_root=tmp_path/'ledger')
        assert broker.create(identity, expires_at=time()+20)['status'] == 'CREATED'
        assert broker.create(identity, expires_at=time()+20)['status'] == 'CREATED'
        assert sum('create' in command for command in commands) == 1
        create = next(command for command in commands if 'create' in command)
        assert '--network=none' in create and '--read-only' in create
        assert '--entrypoint=/app/.venv/bin/python' in create
        assert create[-3:] == ['-I', '-m', 'pilot.research_container_entry']
        state['value'] = 'running'
        upgraded = module.TaskContainerBroker(image='sha256:'+'b'*64, tasks_root=tasks,
                                             ledger_root=tmp_path/'ledger')
        assert upgraded.stop(identity)['status'] == 'STOPPED'
        assert '--user='+str(os.getuid())+':'+str(os.getuid()) in create and '--log-driver=none' in create


def test_unknown_create_is_not_reissued_after_restart(tmp_path, monkeypatch):
    module = importlib.import_module('pilot.research_container_broker')
    monkeypatch.setattr(module, '_RUNTIME_UID', os.getuid(), raising=False)
    identity = dict(tenant_id='00000000-0000-4000-8000-000000000001',
        task_id='00000000-0000-4000-8000-000000000002',
        run_id='00000000-0000-4000-8000-000000000003', generation=2)
    tasks = tmp_path
    directory = tasks/module.task_key(identity)
    directory.mkdir(mode=0o700)
    commands = []
    def run(command):
        commands.append(command)
        return SimpleNamespace(returncode=1, stdout='')
    monkeypatch.setattr(module, '_run', run)
    kwargs = dict(image='sha256:'+'a'*64, tasks_root=tasks, ledger_root=tmp_path/'ledger')
    with socket.socket(socket.AF_UNIX) as gateway:
        gateway.bind(str(directory/'bridge.sock'))
        assert module.TaskContainerBroker(**kwargs).create(identity, expires_at=time()+20)['status']=='UNKNOWN'
        assert module.TaskContainerBroker(**kwargs).create(identity, expires_at=time()+20)['status']=='UNKNOWN'
        assert sum('create' in command for command in commands) == 1


@pytest.mark.parametrize('value', [{}, {'tenant_id': '../other'}, {'generation': True}])
def test_broker_rejects_free_form_identity(value):
    module = importlib.import_module('pilot.research_container_broker')
    with pytest.raises(ValueError):
        module.task_key(value)


def test_broker_rejects_incompatible_runtime_uid(tmp_path, monkeypatch):
    module = importlib.import_module('pilot.research_container_broker')
    monkeypatch.setattr(module.os, 'getuid', lambda: 0)
    with pytest.raises(ValueError, match='runtime_uid_required'):
        module.TaskContainerBroker(image='sha256:'+'a'*64, tasks_root=tmp_path,
                                   ledger_root=tmp_path/'ledger')
