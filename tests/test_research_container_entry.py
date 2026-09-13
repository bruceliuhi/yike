import importlib
import os
from pathlib import Path
import sys
import signal
from time import time

import pytest


def payload():
    return dict(version=1, model='qwen-test', token='task-token', mission='Find recent buyer demand',
                instructions='Use verified citations only', entry_urls=[], max_reads=3,
                max_requests=4, max_searches=2, max_seconds=20, expires_at=time()+20)


@pytest.mark.parametrize('change', [dict(command='sh'), dict(max_seconds=True),
    dict(expires_at=0), dict(token='bad token'), dict(model='model\nconfig'), dict(version=2)])
def test_entry_rejects_invalid_manifest(change):
    module = importlib.import_module('pilot.research_container_entry')
    with pytest.raises(ValueError, match='invalid_task_manifest'):
        module.validate_manifest(payload() | change)


def test_entry_builds_fixed_command_and_cleans_workspace(tmp_path, monkeypatch):
    module = importlib.import_module('pilot.research_container_entry')
    observed = {}
    class Relay:
        base_url = 'http://127.0.0.1:12345/v1'
        def __init__(self, path, *, deadline):
            assert path == '/run/yike/bridge.sock'
        def __enter__(self):
            return self
        def __exit__(self, *args):
            observed['closed'] = True
    class Process:
        pid = 123
        returncode = 0
        def __init__(self, command, **kwargs):
            observed.update(command=command, options=kwargs)
        def communicate(self, data, timeout):
            assert data == b'Find recent buyer demand'
            assert 0 < timeout <= 20
        def wait(self):
            observed['waited'] = True
    monkeypatch.setattr(module, 'TaskSocketRelay', Relay)
    monkeypatch.setattr(module.subprocess, 'Popen', Process)
    monkeypatch.setattr(module, '_kill_group', lambda p: observed.update(killed=True))
    assert module.run_task(payload()) == 0
    command = observed['command']
    assert command[0] == '/opt/codex/bin/codex'
    joined = ' '.join(command)
    assert '/app/.venv/bin/python' in joined
    assert 'http://127.0.0.1:12345/v1/public-read' in joined
    assert 'http://127.0.0.1:12345/v1/public-search' in joined
    env = observed['options']['env']
    assert set(env) == {'PATH', 'HOME', 'CODEX_HOME', 'YIKE_BRIDGE_TOKEN'}
    assert not Path(env['HOME']).exists()
    assert observed['closed'] and observed['killed'] and observed['waited']


def test_entry_timeout_reaps_real_child(monkeypatch):
    module = importlib.import_module('pilot.research_container_entry')
    children = []
    class Relay:
        base_url = 'http://127.0.0.1:12345/v1'
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    original_popen = module.subprocess.Popen
    def start(*args, **kwargs):
        child = original_popen(*args, **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(module, 'TaskSocketRelay', Relay)
    monkeypatch.setattr(module, '_command', lambda *args, **kwargs:
        [sys.executable, '-c', 'import time; time.sleep(60)'])
    monkeypatch.setattr(module.subprocess, 'Popen', start)
    assert module.run_task(payload() | {'expires_at': time()+.2}) == 124
    assert len(children) == 1 and children[0].returncode is not None
    with pytest.raises(ChildProcessError):
        os.waitpid(children[0].pid, os.WNOHANG)


def test_cancel_during_spawn_reaps_child(monkeypatch):
    module = importlib.import_module('pilot.research_container_entry')
    monkeypatch.setattr(module, '_cancel_requested', False)
    children = []
    class Relay:
        base_url = 'http://127.0.0.1:12345/v1'
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    original_popen = module.subprocess.Popen
    def start(*args, **kwargs):
        child = original_popen(*args, **kwargs)
        children.append(child)
        os.kill(os.getpid(), signal.SIGTERM)
        return child
    monkeypatch.setattr(module, 'TaskSocketRelay', Relay)
    monkeypatch.setattr(module, '_command', lambda *args, **kwargs:
        [sys.executable, '-c', 'import time; time.sleep(60)'])
    monkeypatch.setattr(module.subprocess, 'Popen', start)
    previous = {s: signal.signal(s, module._cancel) for s in (signal.SIGTERM, signal.SIGINT)}
    try:
        with pytest.raises(module._Cancelled):
            module.run_task(payload())
        assert len(children) == 1 and children[0].returncode is not None
    finally:
        for s, handler in previous.items():
            signal.signal(s, handler)
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait()
