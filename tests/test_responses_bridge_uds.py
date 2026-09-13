import json
import os
from pathlib import Path
import socket
import stat
import tempfile
from time import monotonic

import httpx
import pytest

from pilot.responses_bridge import BridgeError, ResponsesBridge
import pilot.responses_bridge as module

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='POSIX task socket transport')


@pytest.fixture
def private_dir():
    with tempfile.TemporaryDirectory(prefix='yk-') as directory:
        yield Path(directory)


def bridge_at(path, **kwargs):
    return ResponsesBridge(api_key='test-secret', model='test-model', max_requests=1,
                           deadline=monotonic()+10, allowed_tools=(),
                           unix_socket_path=str(path), **kwargs)


def test_uds_roundtrip_preserves_auth_permit_and_limits(private_dir):
    path = private_dir/'bridge.sock'
    effects = []
    def provider(request):
        assert request.headers['authorization'] == 'Bearer test-secret'
        body = {'type':'response.completed','response':{'status':'completed','output':[]}}
        return httpx.Response(200, headers={'content-type':'text/event-stream'},
                              content=('data: '+json.dumps(body)+'\n\n').encode())
    def dispatch(kind, payload, deadline, perform):
        effects.append(kind)
        return perform(deadline)
    with bridge_at(path, transport=httpx.MockTransport(provider), effect_dispatcher=dispatch) as bridge:
        assert bridge._server.address_family == socket.AF_UNIX
        assert bridge.base_url is None  # No misleading TCP endpoint or fallback.
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        with httpx.Client(transport=httpx.HTTPTransport(uds=str(path)), base_url='http://task') as client:
            assert client.post('/v1/responses', json={}).status_code == 401
            headers={'Authorization':'Bearer '+bridge.token}
            assert client.post('/arbitrary-target', json={}, headers=headers).status_code == 404
            result=client.post('/v1/responses', json={'input':[], 'tools':[]}, headers=headers)
            assert result.status_code == 200
            assert 'test-secret' not in result.text
            assert client.post('/v1/responses', json={'input':[]}, headers=headers).status_code == 429
        assert effects == ['MODEL']
    assert not path.exists()
    assert bridge.token == ''
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        with pytest.raises(OSError): client.connect(str(path))


def test_uds_does_not_replace_existing_file(private_dir):
    path=private_dir/'bridge.sock'
    path.write_text('owned elsewhere')
    with pytest.raises(BridgeError, match='invalid_socket_path'):
        with bridge_at(path): pass
    assert path.read_text() == 'owned elsewhere'


def test_uds_rejects_non_private_parent(private_dir):
    private_dir.chmod(0o755)
    try:
        with pytest.raises(BridgeError, match='invalid_socket_path'):
            with bridge_at(private_dir/'bridge.sock'): pass
    finally:
        private_dir.chmod(0o700)


def test_uds_tokens_are_not_interchangeable(private_dir):
    with bridge_at(private_dir/'one.sock') as one, bridge_at(private_dir/'two.sock') as two:
        with httpx.Client(transport=httpx.HTTPTransport(uds=str(private_dir/'two.sock')),
                          base_url='http://task') as client:
            assert client.post('/v1/responses', json={},
                               headers={'Authorization':'Bearer '+one.token}).status_code == 401
        assert two.records == []


def test_uds_cleanup_preserves_replacement(private_dir):
    path=private_dir/'bridge.sock'
    with bridge_at(path):
        path.unlink()
        path.write_text('replacement')
    assert path.read_text() == 'replacement'


def test_uds_activation_failure_cleans_created_socket(private_dir, monkeypatch):
    def fail(server):
        raise OSError('synthetic listen failure')
    monkeypatch.setattr(module._UnixServer, 'server_activate', fail)
    path=private_dir/'bridge.sock'
    bridge=bridge_at(path)
    with pytest.raises(BridgeError, match='bridge_bind_failed'):
        bridge.__enter__()
    assert not path.exists()
    assert bridge.token == ''
    assert bridge._api_key == ''


def test_uds_cleanup_error_still_clears_secrets(private_dir, monkeypatch):
    bridge=bridge_at(private_dir/'bridge.sock')
    def fail():
        raise PermissionError('synthetic cleanup failure')
    with pytest.raises(PermissionError):
        with bridge:
            monkeypatch.setattr(bridge, '_remove_socket', fail)
    assert bridge.token == ''
    assert bridge._api_key == ''
