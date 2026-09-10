"""HTTP contract only; signatures, cycle state and RLS are tested in real PG."""
import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient

from pilot.auth import issue_token
from pilot.execution_contract import ExecutionRuntimeError
from pilot.web import build_app
from tests.test_ui_api import FakeStore

SECRET = 'synthetic-monitor-pulse'


def payload():
    return dict(schema_version='monitor-runtime-v1', plan_id=str(uuid4()), device_id=str(uuid4()),
                monitor_session_id=str(uuid4()), credential_version=1, can_start=True,
                targets=[dict(platform='BILIBILI', access_mode='PLATFORM_ACCOUNT',
                              connection_id=str(uuid4()), connection_version=1)])


class Service:
    def __init__(self, error=None):
        self.calls, self.error = [], error

    def pulse(self, claims, body):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise AssertionError('DB call must not block ASGI loop')
        self.calls.append((claims.user_id, body.model_dump(mode='json')))
        if self.error:
            raise self.error
        return {'state': 'WAITING', 'occurrence': None}

    def support(self, claims):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise AssertionError('DB call must not block ASGI loop')
        return {'schema_version': 'monitor-runtime-support-v1', 'mode': 'three-platform-monitor-v1'}


def client_for(service):
    client = TestClient(build_app(FakeStore(), auth_secret=SECRET, monitor_runtime=service),
                        base_url='https://pilot.example')
    client.headers['Authorization'] = 'Bearer ' + issue_token('user-1', SECRET)
    return client


def test_authenticated_pulse_runs_off_event_loop_and_keeps_request_binding():
    service = Service()
    client = client_for(service)
    body = payload()
    result = client.post('/api/ui/monitor-runtime/pulse', json=body)
    assert result.status_code == 200
    assert result.json() == {'state': 'WAITING', 'occurrence': None}
    assert result.headers['cache-control'] == 'no-store'
    assert service.calls == [('user-1', body)]


def test_pulse_rejects_injected_authority_ambiguous_json_and_query():
    service = Service()
    client = client_for(service)
    for changed in (payload() | {'server_time': 'tomorrow'}, payload() | {'human_confirmed': True},
                    payload() | {'credential_version': True}, payload() | {'owner_user_id': 'other'},
                    payload() | {'targets': []}, payload() | {'can_start': 1},
                    payload() | {'can_start': 'false'}):
        assert client.post('/api/ui/monitor-runtime/pulse', json=changed).status_code == 422
    assert client.post('/api/ui/monitor-runtime/pulse?plan=other', json=payload()).status_code == 422
    assert client.post('/api/ui/monitor-runtime/pulse', content='{"plan_id":"a","plan_id":"b"}',
                       headers={'Content-Type': 'application/json'}).status_code == 422
    assert service.calls == []


def test_monitor_support_is_authenticated_strict_read_only_metadata():
    client = client_for(Service())
    response = client.get('/api/ui/monitor-runtime/support')
    assert response.status_code == 200
    assert response.json() == {'schema_version': 'monitor-runtime-support-v1', 'mode': 'three-platform-monitor-v1'}
    assert response.headers['cache-control'] == 'no-store'
    assert client.get('/api/ui/monitor-runtime/support?override=1').status_code == 422
    client.headers.pop('Authorization')
    assert client.get('/api/ui/monitor-runtime/support').status_code == 401
    assert client_for(None).get('/api/ui/monitor-runtime/support').status_code == 501


def test_pulse_auth_origin_https_unavailable_and_store_error_boundaries():
    service = Service(ExecutionRuntimeError('monitor_runtime_unavailable', 503))
    client = client_for(service)
    result = client.post('/api/ui/monitor-runtime/pulse', json=payload())
    assert result.status_code == 503
    assert result.json()['detail']['code'] == 'monitor_runtime_unavailable'
    client.headers.pop('Authorization')
    assert client.post('/api/ui/monitor-runtime/pulse', json=payload()).status_code == 401
    client.headers['Authorization'] = 'Bearer ' + issue_token('user-1', SECRET)
    assert client.post('/api/ui/monitor-runtime/pulse', json=payload(),
                       headers={'Origin': 'https://other.example'}).status_code == 403
    client.base_url = 'http://pilot.example'
    assert client.post('/api/ui/monitor-runtime/pulse', json=payload()).status_code == 400
    assert client_for(None).post('/api/ui/monitor-runtime/pulse', json=payload()).status_code == 501
    assert len(service.calls) == 1


def test_ordinary_runtime_composes_same_execution_instance_without_client_capability_claim():
    from pilot.runtime import build_runtime_app
    from pilot.monitor_runtime import MonitorRuntime
    from pilot.execution_runtime import ExecutionRuntime
    from pilot.foreground_collection import three_platform_monitor_policy
    from tests.test_pilot_runtime import _route_service

    db = object()
    app = build_runtime_app(db, auth_secret=SECRET,
                           environment={'YIKE_PILOT_COLLECTION_MODE': 'three-platform-monitor-v1'})
    monitor = _route_service(app, '/api/ui/monitor-runtime/pulse', MonitorRuntime)
    execution = _route_service(app, '/api/ui/execution-operations', ExecutionRuntime)
    assert monitor.database is db and monitor.execution_runtime is execution
    assert execution.monitor_runtime is monitor
    assert execution.capability_check is three_platform_monitor_policy
    capabilities = TestClient(app).get('/api/ui/capabilities').json()['capabilities']
    assert capabilities['task_execution'] == {'available': False}
