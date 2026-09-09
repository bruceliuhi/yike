"""HTTP boundary tests only; durable strategy and real PG checks are separate."""
import asyncio
import importlib
import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from starlette.requests import Request

from pilot.auth import issue_token
from pilot.web import build_app
from tests.test_ui_api import FakeStore

SECRET = 'synthetic-strategy-transport-secret'
PRIVATE = 'synthetic-private-strategy-value'
PREFIX = '/api/ui'


def api():
    assert importlib.util.find_spec('pilot.research_strategy_api') is not None, 'strategy HTTP module missing'
    return importlib.import_module('pilot.research_strategy_api')


def configuration():
    return dict(schema_version='research-strategy-v1', name='测试采购研究', source='search',
                keywords=['寻找服务商'], exclusions=['招聘'], links=[], mode='once', schedule=None, research=None)


def payload(operation):
    body = dict(schema_version='strategy-confirmation-v1', request_id=str(uuid4()))
    if operation == 'prepare':
        body.update(draft_id=str(uuid4()), draft_revision=1, profile_version_id=str(uuid4()),
                    configuration=configuration(), platforms=['DOUYIN'], max_records=100, max_runtime_seconds=900)
    else:
        body['strategy_version_id'] = str(uuid4())
        if operation == 'confirm':
            body.update(configuration_sha256='a' * 64, human_confirmed=True)
    return body


def auth_headers():
    return {'Authorization': 'Bearer ' + issue_token('user-1', SECRET)}


def outside_event_loop():
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return True
    return False


class TransportStore:
    """Trusted service boundary; never substitutes for persistence validation."""
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def invoke(self, operation, claims, body):
        self.calls.append((operation, claims, body, outside_event_loop()))
        if self.error:
            raise self.error
        return {'transport_test': operation}

    def prepare(self, claims, body): return self.invoke('prepare', claims, body)
    def confirm(self, claims, body): return self.invoke('confirm', claims, body)
    def revoke(self, claims, body): return self.invoke('revoke', claims, body)
    def get_receipt(self, claims, key): return self.invoke('receipt', claims, key)
    def get_strategy(self, claims, key): return self.invoke('strategy', claims, key)


def client_for(service, *, base_url='https://pilot.example', claims_missing=False):
    module = api()
    auth_store = FakeStore()
    auth_threads = []
    register = module.register_research_strategy_api

    def observing_register(router, registered_service, identity, require_session_https):
        assert registered_service is service

        def observed_identity(request):
            auth_threads.append(outside_event_loop())
            current = identity(request)
            return SimpleNamespace(claims=None) if claims_missing else current

        register(router, registered_service, observed_identity, require_session_https)

    with patch.object(module, 'register_research_strategy_api', observing_register):
        app = build_app(auth_store, auth_secret=SECRET, research_strategies=service)
    client = TestClient(app, base_url=base_url)
    client.auth_threads = auth_threads
    return client


def test_module_is_present():
    assert callable(api().register_research_strategy_api)


@pytest.mark.parametrize('operation', ['prepare', 'confirm', 'revoke'])
def test_mutations_validate_and_forward_current_claims_in_worker_thread(operation):
    service = TransportStore()
    client = client_for(service)
    body = payload(operation)
    response = client.post(f'{PREFIX}/research-strategies/{operation}', json=body, headers=auth_headers())
    assert response.status_code == 200
    assert response.json() == {'transport_test': operation}
    assert response.headers['cache-control'] == 'no-store'
    name, claims, request, threaded = service.calls[0]
    assert name == operation and claims.user_id == 'user-1'
    assert claims.revocation_key and claims.expires_at
    assert request.model_dump(mode='json') == body
    assert threaded and client.auth_threads == [True]


@pytest.mark.parametrize('resource,operation', [('research-strategy-operations', 'receipt'), ('research-strategies', 'strategy')])
def test_get_queries_original_key_without_mutation(resource, operation):
    service = TransportStore()
    key = str(uuid4())
    response = client_for(service).get(f'{PREFIX}/{resource}/{key}', headers=auth_headers())
    assert response.status_code == 200
    assert service.calls[0][0] == operation and service.calls[0][2] == key
    assert service.calls[0][3]
    assert response.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('method,path', [
    ('POST', 'research-strategies/prepare'), ('POST', 'research-strategies/confirm'),
    ('POST', 'research-strategies/revoke'), ('GET', 'research-strategies/00000000-0000-0000-0000-000000000001'),
    ('GET', 'research-strategy-operations/00000000-0000-0000-0000-000000000001'),
])
def test_all_routes_require_auth_and_absent_service_is_explicit(method, path):
    client = client_for(None)
    # Authentication precedes body decoding and service availability.
    response = client.request(method, f'{PREFIX}/{path}', content='malformed')
    assert response.status_code == 401
    response = client.request(method, f'{PREFIX}/{path}', content='malformed', headers=auth_headers())
    assert response.status_code == 501
    assert response.json()['detail']['code'] == 'capability_unavailable'
    assert response.headers['cache-control'] == 'no-store'
    assert client.get(f'{PREFIX}/capabilities').json()['capabilities']['task_execution'] == {'available': False}


def test_https_origin_revocation_and_missing_claims_never_reach_service():
    service = TransportStore()
    path = f'{PREFIX}/research-strategies/prepare'
    body = payload('prepare')
    assert client_for(service, base_url='http://pilot.example').post(path, json=body, headers=auth_headers()).status_code == 400
    client = client_for(service)
    headers = auth_headers()
    assert client.post(path, json=body, headers=headers | {'Origin': 'https://foreign.example'}).status_code == 403
    assert client.delete(f'{PREFIX}/session', headers=headers).status_code == 200
    assert client.post(path, json=body, headers=headers).status_code == 401
    assert client_for(service, claims_missing=True).post(path, json=body, headers=auth_headers()).status_code == 401
    assert not service.calls


@pytest.mark.parametrize('operation', ['prepare', 'confirm', 'revoke'])
def test_bad_fields_never_echo_private_input_or_reach_service(operation):
    service = TransportStore()
    body = payload(operation) | {'tenant_id': PRIVATE}
    response = client_for(service).post(f'{PREFIX}/research-strategies/{operation}', json=body, headers=auth_headers())
    assert response.status_code == 422 and response.json()['detail']['code'] == 'invalid_request'
    assert PRIVATE not in response.text
    assert not service.calls


@pytest.mark.parametrize('raw', [
    '{"request_id":"a","request_id":"b"}', '{"nested":{"a":1,"a":2}}',
    '{"value":NaN}', '{"value":Infinity}', '[]', 'null', 'true', '"text"',
    b'\xff', '{"x":1}'.encode('utf-16'), '\ufeff{"x":1}', '{"x":',
])
def test_invalid_json_is_safe(raw):
    service = TransportStore()
    response = client_for(service).post(f'{PREFIX}/research-strategies/prepare', content=raw,
                                        headers=auth_headers() | {'content-type': 'application/json'})
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'invalid_request'
    assert not service.calls


@pytest.mark.parametrize('location', ['request', 'configuration'])
def test_duplicate_keys_in_otherwise_valid_requests_are_rejected(location):
    body = payload('prepare')
    raw = json.dumps(body, ensure_ascii=False)
    if location == 'request':
        original = json.dumps(body['request_id'])
        raw = raw.replace('"request_id": ' + original,
                          '"request_id": ' + original + ', "request_id": ' + json.dumps(str(uuid4())))
    else:
        original = json.dumps(body['configuration']['name'], ensure_ascii=False)
        raw = raw.replace('"name": ' + original, '"name": ' + original + ', "name": "另一个合法名称"')
    service = TransportStore()
    response = client_for(service).post(f'{PREFIX}/research-strategies/prepare', content=raw.encode('utf-8'),
                                        headers=auth_headers() | {'content-type': 'application/json'})
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'invalid_request'
    assert not service.calls


@pytest.mark.parametrize('content_type', ['', 'text/plain', 'application/octet-stream'])
def test_json_content_type_required(content_type):
    service = TransportStore()
    response = client_for(service).post(f'{PREFIX}/research-strategies/prepare', content=json.dumps(payload('prepare')),
                                        headers=auth_headers() | {'content-type': content_type})
    assert response.status_code == 415 and not service.calls


def test_actual_body_limit_ignores_declared_length_and_accepts_exact_boundary():
    service = TransportStore()
    client = client_for(service)
    raw = json.dumps(payload('prepare')).encode()
    exact = raw + b' ' * (128 * 1024 - len(raw))
    headers = auth_headers() | {'content-type': 'application/json; charset=utf-8'}
    assert client.post(f'{PREFIX}/research-strategies/prepare', content=exact, headers=headers).status_code == 200
    response = client.post(f'{PREFIX}/research-strategies/prepare',
                           content=iter([exact[:50000], exact[50000:], b' ']), headers=headers | {'content-length': '1'})
    assert response.status_code == 413
    assert response.json()['detail']['code'] == 'request_too_large'
    assert len(service.calls) == 1


@pytest.mark.parametrize('extra_byte', [False, True])
def test_body_reader_counts_real_asgi_fragments_and_stops_at_limit(extra_byte):
    from pilot.research_strategy_contract import PrepareStrategyRequest

    body = payload('prepare')
    raw = json.dumps(body).encode()
    exact = raw + b' ' * (128 * 1024 - len(raw))
    chunks = [exact[:50000], exact[50000:100000], exact[100000:] + (b' ' if extra_byte else b'')]
    received = []

    async def receive():
        # A fourth read would mean the reader did not stop on overflow.
        index = len(received)
        assert index < 3
        received.append(index)
        return {'type': 'http.request', 'body': chunks[index], 'more_body': index < 2 or extra_byte}

    request = Request({'type': 'http', 'headers': [(b'content-type', b'application/json'),
                                                  (b'content-length', b'1')]}, receive)
    if extra_byte:
        with pytest.raises(HTTPException) as error:
            asyncio.run(api()._body(request, PrepareStrategyRequest))
        assert error.value.status_code == 413
        assert error.value.detail['code'] == 'request_too_large'
    else:
        assert asyncio.run(api()._body(request, PrepareStrategyRequest)).model_dump(mode='json') == body
    assert received == [0, 1, 2]


@pytest.mark.parametrize('method,path', [('POST', 'research-strategies/prepare'),
                                       ('POST', 'research-strategies/confirm'), ('POST', 'research-strategies/revoke'),
                                       ('GET', 'research-strategies/' + str(uuid4())),
                                       ('GET', 'research-strategy-operations/' + str(uuid4()))])
def test_queries_are_not_accepted(method, path):
    service = TransportStore()
    response = client_for(service).request(method, f'{PREFIX}/{path}?user_id=x&user_id=y',
                                          json=payload('prepare'), headers=auth_headers())
    assert response.status_code == 422 and not service.calls


@pytest.mark.parametrize('key', ['not-a-uuid', '00000000000000000000000000000001', 'AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA'])
@pytest.mark.parametrize('resource', ['research-strategies', 'research-strategy-operations'])
def test_lookup_ids_are_canonical(resource, key):
    service = TransportStore()
    response = client_for(service).get(f'{PREFIX}/{resource}/{key}', headers=auth_headers())
    assert response.status_code == 422 and not service.calls


@pytest.mark.parametrize('code,status', [('strategy_conflict', 409), ('request_not_found', 404),
                                       ('invalid_session', 401), ('strategy_store_unavailable', 503)])
def test_stable_domain_errors(code, status):
    from pilot.research_strategy_contract import StrategyStoreError
    service = TransportStore(StrategyStoreError(code))
    response = client_for(service).post(f'{PREFIX}/research-strategies/confirm', json=payload('confirm'), headers=auth_headers())
    assert response.status_code == status and response.json()['detail']['code'] == code
    assert response.headers['cache-control'] == 'no-store'
    assert len(service.calls) == 1


def test_unexpected_failure_is_unknown_not_success_or_retry(caplog):
    service = TransportStore(RuntimeError(PRIVATE))
    response = client_for(service).post(f'{PREFIX}/research-strategies/confirm', json=payload('confirm'), headers=auth_headers())
    assert response.status_code == 500 and response.json()['detail']['code'] == 'internal_error'
    assert PRIVATE not in response.text + caplog.text
    assert response.headers['cache-control'] == 'no-store'
    assert len(service.calls) == 1
