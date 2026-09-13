import base64
import importlib
import json
import os
from pathlib import Path
import stat
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
