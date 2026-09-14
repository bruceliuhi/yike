"""Signed STOP HTTP operations against an isolated restricted PostgreSQL role."""
from uuid import uuid4

import pytest
from nacl.signing import SigningKey

from pilot.auth import issue_token, verify_token_claims
from pilot.execution_contract import ExecutionOperation
from tests.test_execution_runtime_postgres import databases, env, start, operation, change_strategy, SECRET
from tests.test_execution_http_postgres import http_client, send
from tests.test_execution_stop import stop_body


def stop(env, lease, **changes):
    return ExecutionOperation.model_validate(stop_body(device_id=env.device,
        task_id=lease['task_id'], platform_run_id=lease['platform_run_id'],
        lease_id=lease['lease_id'], execution_generation=lease['execution_generation']) | changes)


def begun_and_claimed(env):
    client, claims = http_client(env, env.runtime)
    response = send(client, env, claims, start(env))
    assert response.status_code == 200, response.text
    begun = response.json()
    response = send(client, env, claims, operation(env, 'CLAIM', begun))
    assert response.status_code == 200, response.text
    return client, claims, begun, response.json()


def cancel(client, env, claims, begun):
    request = operation(env, 'CANCEL', begun)
    response = send(client, env, claims, request)
    assert response.status_code == 200, response.text
    return request, response.json()


def test_stop_exact_receipt_detail_feed_and_immutable_history(env):
    client, claims, begun, lease = begun_and_claimed(env)
    cancel_request, cancel_receipt = cancel(client, env, claims, begun)
    assert cancel_receipt['status'] == 'CANCELLING'
    request = stop(env, lease)
    response = send(client, env, claims, request)
    assert response.status_code == 200, response.text
    receipt = response.json()
    assert receipt == dict(schema_version='execution-runtime-v1', request_id=request.request_id,
        operation='STOP', task_id=begun['task_id'], run_id=begun['run_id'],
        platform_run_id=lease['platform_run_id'], lease_id=lease['lease_id'], execution_generation=1,
        status='CANCELED', stop_confirmed=True)
    assert send(client, env, claims, request).json() == receipt
    assert send(client, env, claims, request.model_copy(update={'execution_generation':2})).status_code == 409
    assert send(client, env, claims, stop(env, lease)).json()['status'] == 'CANCELED'
    assert cancel(client, env, claims, begun)[1]['status'] == 'CANCELED'
    assert send(client, env, claims, cancel_request).json() == cancel_receipt
    detail = client.get('/api/ui/execution-tasks/' + begun['task_id']).json()
    assert detail['status'] == 'CANCELED' and detail['stop_confirmed'] is True
    feed = env.runtime.get_task_feed(claims)
    item = next(item for item in feed['items'] if item['task_id'] == begun['task_id'])
    assert item['status'] == 'CANCELED' and item['stop_confirmed'] is True
    env.store.revoke_device(env.users[0], env.device)
    assert send(client, env, claims, request).json() == receipt
    assert env.runtime.get_receipt(claims, request.request_id) == receipt
    assert send(client, env, claims, stop(env, lease)).status_code == 404


@pytest.mark.parametrize('field,value', [('lease_id', 'wrong-lease'), ('execution_generation', 2),
                                      ('platform_run_id', 'wrong-platform'), ('task_id', 'wrong-task')])
def test_stop_rejects_wrong_binding(env, field, value):
    client, claims, begun, lease = begun_and_claimed(env)
    cancel(client, env, claims, begun)
    response = send(client, env, claims, stop(env, lease, **{field:value}))
    assert response.status_code in (404, 409), response.text
    assert env.runtime.get_task(claims, begun['task_id'])['status'] == 'CANCELLING'


def test_stop_rejects_wrong_owner_device_key_and_credential(env):
    from types import SimpleNamespace
    from pilot.device_credentials import DeviceCredentialStore
    from tests.test_device_credentials_postgres import bind
    client, claims, begun, lease = begun_and_claimed(env)
    cancel(client, env, claims, begun)
    request = stop(env, lease)
    original_key = env.key
    env.key = SigningKey.generate()
    assert send(client, env, claims, request).status_code == 400
    env.key = original_key
    assert send(client, env, claims, stop(env, lease, credential_version=2)).status_code == 409
    other_device = env.store.register_device(env.users[0], 'other')['device_id']
    other_key = SigningKey.generate()
    bind(SimpleNamespace(service=DeviceCredentialStore(env.db), claims=claims, device=other_device), other_key)
    env.key = other_key
    assert send(client, env, claims, stop(env, lease, device_id=other_device)).status_code == 404
    other_token = issue_token(env.users[1], SECRET)
    other_claims = verify_token_claims(other_token, SECRET)
    client.headers['Authorization'] = 'Bearer ' + other_token
    foreign_device = env.store.register_device(env.users[1], 'foreign-owner')['device_id']
    bind(SimpleNamespace(service=DeviceCredentialStore(env.db), claims=other_claims, device=foreign_device), other_key)
    response = send(client, env, other_claims, stop(env, lease, device_id=foreign_device))
    assert response.status_code == 404 and response.json()['detail']['code'] == 'task_not_found'
    env.key = original_key
    assert env.runtime.get_task(claims, begun['task_id'])['status'] == 'CANCELLING'


def test_stop_current_rotated_credential_cannot_ack_old_lease(env):
    from types import SimpleNamespace
    from pilot.device_credentials import DeviceCredentialStore
    from tests.test_device_credentials_postgres import challenge, complete
    client, claims, begun, lease = begun_and_claimed(env)
    cancel(client, env, claims, begun)
    new_key = SigningKey.generate()
    key_env = SimpleNamespace(service=DeviceCredentialStore(env.db), claims=claims, device=env.device)
    complete(key_env, challenge(key_env, 'ROTATE', 1, new_key), new_key, env.key)
    env.key = new_key
    response = send(client, env, claims, stop(env, lease, credential_version=2))
    assert response.status_code == 409 and response.json()['detail']['code'] == 'lease_conflict'
    assert env.runtime.get_task(claims, begun['task_id'])['status'] == 'CANCELLING'


def test_stop_revoked_session_cannot_mutate_or_read_history(env):
    client, claims, begun, lease = begun_and_claimed(env)
    cancel(client, env, claims, begun)
    env.store.sessions.revoke([claims])
    assert send(client, env, claims, stop(env, lease)).status_code == 401
    assert env.runtime.get_task(env.claims, begun['task_id'])['status'] == 'CANCELLING'


def test_stop_allows_expiry_and_revoked_strategy(env):
    change_strategy(env, max_runtime_seconds=2)
    client, claims, begun, lease = begun_and_claimed(env)
    cancel(client, env, claims, begun)
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_collection_platform_runs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE task_id=%s", (begun['task_id'],))
        conn.execute("UPDATE business_profile_versions SET status='REVOKED',payload='{}'::jsonb WHERE profile_version_id=%s", (env.profile,))
        conn.execute('SELECT pg_sleep(2.1)')
    response = send(client, env, claims, stop(env, lease))
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'CANCELED'


@pytest.mark.parametrize('status,code', [('RUNNING','task_not_cancelling'), ('SUCCEEDED','task_finished')])
def test_stop_requires_cancellation_and_never_downgrades_success(env, status, code):
    client, claims, begun, lease = begun_and_claimed(env)
    with env.admin.connect() as conn:
        for table in ('pilot_collection_tasks','pilot_collection_runs','pilot_collection_platform_runs'):
            conn.execute(f'UPDATE {table} SET status=%s WHERE task_id=%s', (status, begun['task_id']))
    response = send(client, env, claims, stop(env, lease))
    assert response.status_code == 409, response.text
    assert response.json()['detail']['code'] == code
    assert env.runtime.get_task(claims, begun['task_id'])['status'] == status


def test_stop_rejects_research_task(env):
    from pilot.execution_runtime import execution_signing_payload
    from tests.test_device_keys import encoded
    change_strategy(env, configuration={'research': {}})
    client, claims = http_client(env, env.runtime)
    request = start(env)
    signature = encoded(env.key.sign(execution_signing_payload(
        tenant_id=env.tenant, claims=claims, operation=request).encode()).signature)
    begun = env.runtime.apply_research(claims, request, signature, research_hook=lambda *args: None)
    cancel(client, env, claims, begun)
    lease = dict(task_id=begun['task_id'], platform_run_id=begun['platform_runs'][0]['platform_run_id'],
                 lease_id='unclaimed', execution_generation=1)
    response = send(client, env, claims, stop(env, lease))
    assert response.status_code == 409 and response.json()['detail']['code'] == 'capability_unavailable'


@pytest.mark.parametrize('second_state', ['claimed', 'pending', 'succeeded'])
def test_stop_multiple_platforms_only_confirms_when_all_stopped(env, second_state):
    from tests.test_execution_finish_postgres import account_target
    target = account_target(env)
    change_strategy(env, platforms=['BILIBILI', 'PUBLIC_WEB'])
    client, claims = http_client(env, env.runtime)
    begun = send(client, env, claims, start(env, targets=[target, dict(platform='PUBLIC_WEB',
        access_mode='PUBLIC_ANONYMOUS', connection_id=None)])).json()
    first = send(client, env, claims, operation(env, 'CLAIM', begun)).json()
    second = None
    if second_state != 'pending':
        second = send(client, env, claims, operation(env, 'CLAIM', begun,
            platform_run_id=begun['platform_runs'][1]['platform_run_id'])).json()
    if second_state == 'succeeded':
        with env.admin.connect() as conn:
            conn.execute("UPDATE pilot_collection_platform_runs SET status='SUCCEEDED' WHERE platform_run_id=%s", (second['platform_run_id'],))
    cancel(client, env, claims, begun)
    if second_state == 'succeeded':
        assert send(client, env, claims, stop(env, second)).status_code == 409
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_platform_connections SET status='EXPIRED' WHERE connection_id=%s", (target['connection_id'],))
    response = send(client, env, claims, stop(env, first))
    assert response.status_code == 200, response.text
    assert response.json()['stop_confirmed'] is (second_state != 'claimed')
    assert response.json()['status'] == ('CANCELLING' if second_state == 'claimed' else 'CANCELED')
    if second_state == 'claimed':
        assert cancel(client, env, claims, begun)[1]['status'] == 'CANCELLING'
        assert send(client, env, claims, stop(env, second)).json()['status'] == 'CANCELED'
    assert env.runtime.get_task(claims, begun['task_id'])['stop_confirmed'] is True
    if second_state == 'succeeded':
        assert next(p for p in env.runtime.get_task(claims, begun['task_id'])['platform_runs']
                    if p['platform_run_id'] == second['platform_run_id'])['status'] == 'SUCCEEDED'
