import importlib
import json
import os
from pathlib import Path
import socket
import tempfile
from time import monotonic

import httpx
import pytest

from pilot.responses_bridge import ResponsesBridge

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='POSIX task transport')


def test_relay_preserves_gateway_auth_and_has_only_one_destination():
    relay_type = importlib.import_module('pilot.research_socket_relay').TaskSocketRelay
    with tempfile.TemporaryDirectory(prefix='yk-') as directory:
        path=Path(directory)/'bridge.sock'
        def provider(request):
            body={'type':'response.completed','response':{'status':'completed','output':[]}}
            return httpx.Response(200,headers={'content-type':'text/event-stream'},
                                  content=('data: '+json.dumps(body)+'\n\n').encode())
        with ResponsesBridge(api_key='synthetic',model='synthetic',max_requests=1,
                             deadline=monotonic()+10,allowed_tools=(),unix_socket_path=str(path),
                             transport=httpx.MockTransport(provider)) as bridge:
            with relay_type(str(path),deadline=monotonic()+5) as relay:
                assert relay.base_url.startswith('http://127.0.0.1:')
                assert httpx.post(relay.base_url+'/responses',json={}).status_code==401
                response=httpx.post(relay.base_url+'/responses',json={'input':[]},
                                    headers={'Authorization':'Bearer '+bridge.token})
                assert response.status_code==200
                assert 'synthetic' not in response.text
                assert httpx.get(relay.base_url+'/arbitrary').status_code==405
                address=relay.address
            with pytest.raises(OSError):
                socket.create_connection(address,timeout=.2)
            assert path.exists()  # Relay never owns/deletes the host socket.


@pytest.mark.parametrize('value', ['relative.sock','http://example.com','/missing/socket'])
def test_relay_rejects_non_socket_targets(value):
    relay_type = importlib.import_module('pilot.research_socket_relay').TaskSocketRelay
    with pytest.raises(ValueError,match='invalid_relay_configuration'):
        relay_type(value,deadline=monotonic()+5)


def test_relay_deadline_closes_idle_clients():
    relay_type = importlib.import_module('pilot.research_socket_relay').TaskSocketRelay
    with tempfile.TemporaryDirectory(prefix='yk-') as directory:
        path=Path(directory)/'bridge.sock'
        with ResponsesBridge(api_key='synthetic',model='synthetic',max_requests=1,
                             deadline=monotonic()+10,allowed_tools=(),unix_socket_path=str(path)):
            started=monotonic()
            with relay_type(str(path),deadline=started+.4) as relay:
                with socket.create_connection(relay.address,timeout=2) as client:
                    client.sendall(b'POST /v1/responses HTTP/1.1\r\n')
                    assert client.recv(1)==b''
            assert monotonic()-started < 2


def test_relay_rejects_symlink_and_expired_deadline():
    relay_type = importlib.import_module('pilot.research_socket_relay').TaskSocketRelay
    with tempfile.TemporaryDirectory(prefix='yk-') as directory:
        path = Path(directory) / 'bridge.sock'
        with ResponsesBridge(api_key='synthetic', model='synthetic', max_requests=1,
                             deadline=monotonic()+10, allowed_tools=(), unix_socket_path=str(path)):
            alias = Path(directory) / 'alias.sock'
            alias.symlink_to(path)
            for target, deadline in [(alias, monotonic()+5), (path, monotonic()-1), (path, float('nan'))]:
                with pytest.raises(ValueError, match='invalid_relay_configuration'):
                    relay_type(str(target), deadline=deadline)


def test_listener_closed_when_thread_start_fails(monkeypatch):
    module = importlib.import_module('pilot.research_socket_relay')
    with tempfile.TemporaryDirectory(prefix='yk-') as directory:
        path = Path(directory) / 'gateway.sock'
        with socket.socket(socket.AF_UNIX) as gateway:
            gateway.bind(str(path))
            relay = module.TaskSocketRelay(str(path), deadline=monotonic()+5)
            def fail(*args):
                raise RuntimeError('thread unavailable')
            monkeypatch.setattr(module.threading.Thread, 'start', fail)
            with pytest.raises(RuntimeError):
                relay.__enter__()
            assert relay._listener.fileno() == -1


def test_upstream_allocation_failure_releases_client_and_slot(monkeypatch):
    module = importlib.import_module('pilot.research_socket_relay')
    with tempfile.TemporaryDirectory(prefix='yk-') as directory:
        path = Path(directory) / 'gateway.sock'
        with socket.socket(socket.AF_UNIX) as gateway:
            gateway.bind(str(path))
            relay = module.TaskSocketRelay(str(path), deadline=monotonic()+5)
            client, peer = socket.socketpair()
            try:
                relay._sockets.add(client)
                relay._slots.acquire()
                def fail(*args):
                    raise OSError('socket unavailable')
                monkeypatch.setattr(module.socket, 'socket', fail)
                try:
                    relay._serve(client)
                except OSError:
                    pass
                assert client.fileno() == -1
                assert client not in relay._sockets
                assert all(relay._slots.acquire(blocking=False) for _ in range(4))
            finally:
                client.close()
                peer.close()
