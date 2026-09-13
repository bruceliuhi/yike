import base64
import importlib
import json
import os
from pathlib import Path
import stat
import socket
import select
import subprocess
import sys
import tempfile

import httpx
import pytest


def test_private_broker_routes_and_streaming():
    module = importlib.import_module('pilot.research_broker_service')
    calls = []
    class Broker:
        def create(self, identity, *, expires_at):
            calls.append('create')
            return {'key':'a'*64,'status':'CREATED'}
        def status(self, identity):
            return {'key':'a'*64,'status':'RUNNING'}
        def stop(self, identity):
            calls.append('stop')
            return {'key':'a'*64,'status':'STOPPED'}
        def execute(self, identity, manifest, *, emit):
            emit(b'{"event":"synthetic"}\n')
            return {'key':'a'*64,'status':'STOPPED','code':None}
    with tempfile.TemporaryDirectory(prefix='yb-',dir='/tmp') as directory:
        path = str(Path(directory)/'control.sock')
        with module.BrokerServer(Broker(), path):
            assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
            with httpx.Client(transport=httpx.HTTPTransport(uds=path),base_url='http://broker') as client:
                assert client.post('/v1/create',json={'identity':{},'expires_at':123}).status_code==200
                assert client.post('/v1/status',json={'identity':{}}).json()['status']=='RUNNING'
                assert client.post('/v1/stop',json={'identity':{}}).json()['status']=='STOPPED'
                response=client.post('/v1/execute',json={'identity':{},'manifest':{}})
                frames=[json.loads(line) for line in response.text.splitlines()]
                assert base64.b64decode(frames[0]['data']) == b'{"event":"synthetic"}\n'
                assert frames[-1]['type']=='result'
                assert client.post('/v1/execute',json={'identity':{},'manifest':{},'command':'sh'}).status_code==400
                assert client.post('/arbitrary',json={}).status_code==404
                assert client.get('/v1/status').status_code==405
            assert calls==['create','stop']
        assert not os.path.exists(path)


def test_server_does_not_replace_existing_socket_path():
    module=importlib.import_module('pilot.research_broker_service')
    with tempfile.TemporaryDirectory(prefix='yb-',dir='/tmp') as directory:
        path=Path(directory)/'control.sock'
        path.write_text('existing')
        with pytest.raises(Exception):
            with module.BrokerServer(object(),str(path)):
                pass
        assert path.read_text()=='existing'


def test_control_recovery_removes_only_dead_socket():
    module = importlib.import_module('pilot.research_broker_service')
    with tempfile.TemporaryDirectory(prefix='yb-', dir='/tmp') as directory:
        path = str(Path(directory) / 'control.sock')
        with socket.socket(socket.AF_UNIX) as abandoned:
            abandoned.bind(path)
        module._recover_control_socket(path)
        with module.BrokerServer(object(), path):
            assert os.path.exists(path)


@pytest.mark.parametrize('kind', ['live', 'file', 'symlink'])
def test_control_recovery_preserves_other_paths(kind):
    module = importlib.import_module('pilot.research_broker_service')
    with tempfile.TemporaryDirectory(prefix='yb-', dir='/tmp') as directory:
        path = Path(directory) / 'control.sock'
        with socket.socket(socket.AF_UNIX) as live:
            if kind == 'live':
                live.bind(str(path))
                live.listen(1)
            elif kind == 'file':
                path.write_text('keep')
            else:
                path.symlink_to(Path(directory) / 'missing')
            inode = path.lstat().st_ino
            with pytest.raises(ValueError):
                module._recover_control_socket(str(path))
            assert path.lstat().st_ino == inode


def test_control_socket_recovers_after_server_process_is_killed():
    module = importlib.import_module('pilot.research_broker_service')
    script = ('import sys,time;from pilot.research_broker_service import BrokerServer;'
              's=BrokerServer(object(),sys.argv[1]);s.__enter__();'
              'print("ready",flush=True);time.sleep(30)')
    with tempfile.TemporaryDirectory(prefix='yb-', dir='/tmp') as directory:
        path = str(Path(directory) / 'control.sock')
        child = subprocess.Popen([sys.executable, '-c', script, path],
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            assert select.select([child.stdout], [], [], 5)[0], 'server startup timed out'
            assert child.stdout.readline() == b'ready\n'
            child.kill()
            child.wait(timeout=5)
            assert os.path.exists(path), 'crash must leave the socket for recovery'
            module._recover_control_socket(path)
            with module.BrokerServer(object(), path):
                with httpx.Client(transport=httpx.HTTPTransport(uds=path),
                                  base_url='http://broker') as client:
                    assert client.get('/v1/status').status_code == 405
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            child.stdout.close()
