"""Real HTTP/runtime, restricted PostgreSQL and private model worker.

Provider is a loopback synthetic server, not real customer/model acceptance.
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from uuid import uuid4

from fastapi.testclient import TestClient

from pilot.auth import issue_token
from pilot.runtime import build_runtime_app
from tests.test_materials_store import database, env, SECRET, save_request
from tests.test_material_model import TEXT, envelope


def client(env, environment=None, owner=0):
    value = TestClient(build_runtime_app(env.db, auth_secret=SECRET,
        environment=environment or {}), base_url='https://synthetic.invalid')
    value.headers['Authorization'] = 'Bearer ' + issue_token(env.users[owner], SECRET)
    return value


def change(profile, material, version, kind, **extra):
    return {'requestId': str(uuid4()), 'profileVersionId': profile,
            'change': {'kind': kind, 'materialId': material, 'expectedVersion': version, **extra}}


def send(http, value):
    response = http.post('/api/ui/materials/mutate', json=value)
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'SUCCEEDED', response.text
    return response.json()


def test_materials_runtime_end_to_end_private_worker_and_restart(env):
    calls = []
    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(body)
            encoded = json.dumps(envelope()).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
    provider = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    thread = Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    try:
        http = client(env, {'YIKE_PILOT_ASSESSMENT_BASE_URL': f'http://127.0.0.1:{provider.server_port}/v1',
            'YIKE_PILOT_ASSESSMENT_API_KEY': 'synthetic-secret', 'YIKE_PILOT_ASSESSMENT_MODEL': 'synthetic'})
        profile = env.profiles[0]
        request = save_request(profile, text=TEXT)
        material = request['change']['materialId']
        saved = send(http, request)
        assert saved['record']['status'] == 'DRAFT'
        parse = change(profile, material, 1, 'parse')
        parsed = send(http, parse)
        assert parsed['record']['status'] == 'REVIEW_REQUIRED'
        assert len(calls) == 1 and json.loads(calls[0]['messages'][1]['content']) == {'text': TEXT}
        assert send(http, parse) == parsed and len(calls) == 1
        confirmed = send(http, change(profile, material, 2, 'confirm',
            extractionId=parsed['record']['extraction']['id'], fields={'service': '质量检测系统'}))
        assert confirmed['record']['status'] == 'READY'
        # Restart without model: the original parse receipt remains the original version.
        restarted = client(env)
        assert restarted.get('/api/ui/materials/operation', params={
            'profileVersionId': profile, 'requestId': parse['requestId']}).json() == parsed
        impact = restarted.post('/api/ui/materials/impact', json={
            'profileVersionId': profile, 'materialId': material, 'version': 3, 'action': 'revoke'}).json()
        assert impact['references'] == []  # Copied local profile text is not a managed reference.
        revoked = send(restarted, change(profile, material, 3, 'revoke', impactToken=impact['token']))
        assert revoked['record']['status'] == 'REVOKED'
        assert revoked['record']['extraction']['materialVersion'] == 4
        listed = restarted.get('/api/ui/materials', params={'profileVersionId': profile}).json()
        assert listed == [revoked['record']]
        impact = restarted.post('/api/ui/materials/impact', json={
            'profileVersionId': profile, 'materialId': material, 'version': 4, 'action': 'remove'}).json()
        send(restarted, change(profile, material, 4, 'remove', impactToken=impact['token']))
        assert restarted.get('/api/ui/materials', params={'profileVersionId': profile}).json() == []
        assert client(env, owner=1).get('/api/ui/materials/operation', params={
            'profileVersionId': profile, 'requestId': parse['requestId']}).status_code == 404
    finally:
        provider.shutdown()
        provider.server_close()
        thread.join(timeout=2)


def test_absent_model_is_visible_failure_not_mock_or_pending(env):
    http = client(env)
    request = save_request(env.profiles[0])
    send(http, request)
    result = send(http, change(env.profiles[0], request['change']['materialId'], 1, 'parse'))
    assert result['record']['status'] == 'FAILED'
    assert 'extraction' not in result['record']
    assert http.delete('/api/ui/session').status_code == 200
    assert http.get('/api/ui/materials', params={'profileVersionId': env.profiles[0]}).status_code == 401
