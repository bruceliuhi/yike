"""Transport checks only; real monitor persistence has separate PG coverage."""
import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient

from pilot.auth import issue_token
from pilot.web import build_app
from tests.test_ui_api import FakeStore

SECRET = 'synthetic-monitor-transport'


class Service:
    def __init__(self):
        self.calls = []

    def call(self, operation, claims, body=None):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise AssertionError('database call must run off event loop')
        self.calls.append((operation, claims, body))
        return {'execution_status': 'NOT_CONNECTED'}

    def create(self, claims, body): return self.call('create', claims, body)
    def set_state(self, claims, body): return self.call('state', claims, body)
    def list(self, claims): return self.call('list', claims)
    def get_receipt(self, claims, key): return self.call('receipt', claims, key)


def setup(service=None):
    service = service or Service()
    app = build_app(FakeStore(), auth_secret=SECRET, monitor_plans=service)
    client = TestClient(app, base_url='https://pilot.example')
    client.headers['Authorization'] = 'Bearer ' + issue_token('user-1', SECRET)
    return client, service


def create_body():
    return dict(schema_version='monitor-plans-v1', request_id=str(uuid4()),
                profile_version_id=str(uuid4()), strategy_version_id=str(uuid4()), human_confirmed=True)


def test_routes_are_authenticated_bounded_and_do_not_start_collection():
    client, service = setup()
    body = create_body()
    response = client.post('/api/ui/monitor-plans', json=body)
    assert response.status_code == 200
    assert response.json() == {'execution_status': 'NOT_CONNECTED'}
    assert response.headers['cache-control'] == 'no-store'
    assert client.get('/api/ui/monitor-plans').status_code == 200
    assert client.get('/api/ui/monitor-plan-operations/' + body['request_id']).status_code == 200
    state = dict(schema_version='monitor-plans-v1', request_id=str(uuid4()),
                 plan_id=body['request_id'], expected_revision=1, state='PAUSED', human_confirmed=True)
    assert client.post('/api/ui/monitor-plans/state', json=state).status_code == 200
    assert [call[0] for call in service.calls] == ['create', 'list', 'receipt', 'state']
    assert all(call[1].user_id == 'user-1' for call in service.calls)


def test_unapproved_or_injected_or_ambiguous_input_never_reaches_store():
    client, service = setup()
    body = create_body()
    for changed in (body | {'human_confirmed': 1}, body | {'next_due_at': 'tomorrow'},
                    body | {'human_confirmed': False}, body | {'owner_user_id': 'other'}):
        assert client.post('/api/ui/monitor-plans', json=changed).status_code == 422
    assert client.post('/api/ui/monitor-plans', content='{"request_id":"a","request_id":"b"}',
                       headers={'Content-Type': 'application/json'}).status_code == 422
    assert client.get('/api/ui/monitor-plans?owner=other').status_code == 422
    assert client.get('/api/ui/monitor-plan-operations/not-a-uuid').status_code == 422
    assert client.post('/api/ui/monitor-plans', content='x' * (128 * 1024 + 1),
                       headers={'Content-Type': 'application/json'}).status_code == 413
    assert service.calls == []


def test_session_https_origin_and_unavailable_are_not_silent_success():
    client, service = setup()
    client.headers.pop('Authorization')
    assert client.get('/api/ui/monitor-plans').status_code == 401
    client.headers['Authorization'] = 'Bearer ' + issue_token('user-1', SECRET)
    assert client.post('/api/ui/monitor-plans', json=create_body(),
                       headers={'Origin': 'https://other.example'}).status_code == 403
    client.base_url = 'http://pilot.example'
    response = client.get('/api/ui/monitor-plans')
    assert response.status_code == 400
    assert response.json()['detail']['code'] == 'https_required'
    assert service.calls == []
    unavailable = TestClient(build_app(FakeStore(), auth_secret=SECRET), base_url='https://pilot.example')
    unavailable.headers['Authorization'] = 'Bearer ' + issue_token('user-1', SECRET)
    assert unavailable.get('/api/ui/monitor-plans').status_code == 501


def test_runtime_reuses_current_strategy_resolver_without_granting_execution():
    from pilot.runtime import build_runtime_app
    from pilot.monitor_plans import MonitorPlanStore
    from pilot.research_strategies import ResearchStrategyStore
    from tests.test_pilot_runtime import _route_service

    db = object()
    app = build_runtime_app(db, auth_secret=SECRET, environment={})
    monitors = _route_service(app, '/api/ui/monitor-plans', MonitorPlanStore)
    strategies = _route_service(app, '/api/ui/research-strategies/prepare', ResearchStrategyStore)
    assert monitors.database is db
    assert monitors.strategy_resolver.__self__ is strategies
    capabilities = TestClient(app).get('/api/ui/capabilities').json()['capabilities']
    assert capabilities['task_execution'] == {'available': False}
