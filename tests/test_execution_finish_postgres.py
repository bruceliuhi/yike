"""FINISH uses persisted synthetic uploads, restricted PostgreSQL and signed HTTP."""
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Event
from uuid import uuid4

import pytest

from pilot.execution_contract import ExecutionOperation, ExecutionRuntimeError
from tests.test_candidate_ingestion_postgres import (
    execution_databases, execution_env, databases, env, payload, submit, service,
    claimed, apply, operation, change_strategy, start, SECRET,
)
from tests.test_candidate_ingestion_http_postgres import http_client, started, signed
from tests.test_execution_http_postgres import send
from tests.test_execution_finish import finish_body


def finish(env, lease, upload_id, **changes):
    return ExecutionOperation.model_validate(finish_body(device_id=env.device,
        task_id=lease['task_id'], platform_run_id=lease['platform_run_id'],
        lease_id=lease['lease_id'], execution_generation=lease['execution_generation'],
        upload_request_id=upload_id, **changes))


@pytest.mark.parametrize('count', [0, 1, 2])
def test_http_finish_empty_and_exact_budget_and_historical_replay(env, count):
    client, claims = http_client(env)
    begun, lease = started(client, env, claims)
    raw = payload(env, begun, lease, request_id='original:upload.1')
    raw['records'] = [dict(raw['records'][0], public_url=f'https://example.com/{i}') for i in range(count)]
    uploaded = client.post('/api/ui/candidate-batches', json=signed(env, claims, raw))
    assert uploaded.status_code == 200, uploaded.text
    request = finish(env, lease, raw['request_id'])
    response = send(client, env, claims, request)
    assert response.status_code == 200, response.text
    receipt = response.json()
    assert receipt == dict(schema_version='execution-runtime-v1', request_id=request.request_id,
        operation='FINISH', task_id=begun['task_id'], run_id=begun['run_id'],
        platform_run_id=lease['platform_run_id'], lease_id=lease['lease_id'], execution_generation=1,
        upload_request_id=raw['request_id'], records_used=count, status='SUCCEEDED', stop_confirmed=True)
    current = env.runtime.get_task(claims, begun['task_id'])
    assert current['status'] == 'SUCCEEDED' and current['stop_confirmed'] is True
    for action in ['CLAIM', 'RENEW', 'CANCEL']:
        blocked = operation(env, action, begun, **({'lease_id':lease['lease_id'], 'execution_generation':1} if action == 'RENEW' else {}))
        denied = send(client, env, claims, blocked)
        assert denied.status_code == 409 and denied.json()['detail']['code'] == 'task_finished'
    raw2 = raw | {'request_id':'new-upload'}
    assert client.post('/api/ui/candidate-batches', json=signed(env, claims, raw2)).status_code == 409
    env.store.revoke_device(env.users[0], env.device)
    assert send(client, env, claims, request).json() == receipt
    assert env.runtime.get_receipt(claims, request.request_id) == receipt
    assert send(client, env, claims, request.model_copy(update={'upload_request_id':'other'})).json()['detail']['code'] == 'request_conflict'


def test_missing_and_other_task_upload_cannot_finish(env):
    begun, lease = claimed(env)
    other, other_lease = claimed(env)
    value = payload(env, other, other_lease, request_id='foreign-task')
    submit(env, service(env), value)
    for key in ['missing', 'foreign-task']:
        with pytest.raises(ExecutionRuntimeError, match='upload_unavailable'):
            apply(env, finish(env, lease, key))
    assert env.runtime.get_task(env.claims, begun['task_id'])['status'] == 'RUNNING'


@pytest.mark.parametrize('change', ['lease', 'generation', 'device', 'profile', 'strategy', 'cancel'])
def test_finish_revalidates_current_authority(env, change):
    begun, lease = claimed(env)
    value = payload(env, begun, lease)
    submit(env, service(env), value)
    request = finish(env, lease, value['request_id'])
    expected = 'lease_conflict'
    if change == 'lease': request = request.model_copy(update={'lease_id':str(uuid4())})
    if change == 'generation': request = request.model_copy(update={'execution_generation':2})
    if change == 'device':
        env.store.revoke_device(env.users[0], env.device)
        expected = 'device_unavailable'
    if change == 'profile':
        with env.admin.connect() as conn:
            conn.execute("UPDATE business_profile_versions SET status='REVOKED' WHERE profile_version_id=%s", (env.profile,))
        expected = 'profile_unavailable'
    if change == 'strategy':
        change_strategy(env, max_records=3)
        expected = 'strategy_conflict'
    if change == 'cancel':
        apply(env, operation(env, 'CANCEL', begun))
        expected = 'task_cancelled'
    with pytest.raises(ExecutionRuntimeError, match=expected): apply(env, request)


def test_finish_waits_for_upload_before_taking_device_lock(env, monkeypatch):
    begun, lease = claimed(env)
    value = payload(env, begun, lease)
    entered, release = Event(), Event()
    original = env.runtime.lock_submission
    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)
    monkeypatch.setattr(env.runtime, 'lock_submission', delayed)
    with ThreadPoolExecutor(2) as pool:
        upload = pool.submit(submit, env, service(env), value)
        assert entered.wait(10)
        from pilot.auth import issue_token, verify_token_claims
        other_session = verify_token_claims(issue_token(env.users[0], SECRET), SECRET)
        done = pool.submit(apply, env, finish(env, lease, value['request_id']), other_session)
        from tests.test_device_credentials_postgres import wait_for_lock
        try:
            wait_for_lock(env.admin, 'pg_advisory_xact_lock(11201')
            assert not done.done()
        finally: release.set()
        assert upload.result(timeout=10)['accepted_count'] == 1
        assert done.result(timeout=10)['status'] == 'SUCCEEDED'


def test_finish_cancel_race_never_reverts_success(env):
    begun, lease = claimed(env)
    value = payload(env, begun, lease)
    submit(env, service(env), value)
    def attempt(request):
        try: return apply(env, request)['status']
        except ExecutionRuntimeError as error: return error.code
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(attempt, [finish(env, lease, value['request_id']), operation(env, 'CANCEL', begun)]))
    assert set(results) in ({'SUCCEEDED','task_finished'}, {'CANCELLING','task_cancelled'})


def test_finish_final_fence_rolls_back_after_wait(env, monkeypatch):
    begun, lease = claimed(env)
    value = payload(env, begun, lease)
    submit(env, service(env), value)
    request = finish(env, lease, value['request_id'])
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_collection_platform_runs SET lease_expires_at=clock_timestamp()+interval '2 seconds' WHERE platform_run_id=%s", (lease['platform_run_id'],))
    original = env.runtime._active
    def delayed(cursor, claims):
        result = original(cursor, claims)
        cursor.execute('SELECT 1 FROM pilot_execution_operations WHERE request_id=%s', (request.request_id,))
        if cursor.fetchone():
            cursor.execute('SELECT pg_sleep(2.1)')
        return result
    monkeypatch.setattr(env.runtime, '_active', delayed)
    with pytest.raises(ExecutionRuntimeError, match='lease_expired'): apply(env, request)
    monkeypatch.setattr(env.runtime, '_active', original)
    assert env.runtime.get_task(env.claims, begun['task_id'])['status'] == 'RUNNING'
    with pytest.raises(ExecutionRuntimeError, match='request_not_found'): env.runtime.get_receipt(env.claims, request.request_id)
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_collection_platform_runs SET lease_expires_at=clock_timestamp()+interval '120 seconds' WHERE platform_run_id=%s", (lease['platform_run_id'],))
    assert apply(env, request)['status'] == 'SUCCEEDED'


def account_target(env):
    from pilot.connection_versions import ConnectionOperation, ConnectionOperationStore
    store = ConnectionOperationStore(env.db)
    registered = store.apply(env.claims, ConnectionOperation(request_id=str(uuid4()), action='REGISTER',
        device_id=env.device, connection_id=None, expected_connection_version=0,
        platform='BILIBILI', account_public_id='synthetic', session_ref='vault://synthetic'))
    verified = store.apply(env.claims, ConnectionOperation(request_id=str(uuid4()), action='VERIFY',
        device_id=env.device, connection_id=registered['connection_id'], expected_connection_version=1,
        platform='BILIBILI', account_public_id='synthetic', session_ref='vault://synthetic'))
    return dict(platform='BILIBILI', access_mode='PLATFORM_ACCOUNT',
        connection_id=registered['connection_id'], connection_version=verified['connection_version'])


def empty_account_upload(env, begun, lease, target):
    value = payload(env, begun, lease, platform=target['platform'], records=[])
    value['execution'].update({k:v for k,v in target.items() if k != 'platform'})
    submit(env, service(env), value)
    return value


@pytest.mark.parametrize('remaining_claimed', [False, True])
def test_partial_finish_cancel_only_unfinished_platforms(env, remaining_claimed):
    target = account_target(env)
    change_strategy(env, platforms=['BILIBILI','PUBLIC_WEB'])
    begun = apply(env, start(env, targets=[target, dict(platform='PUBLIC_WEB', access_mode='PUBLIC_ANONYMOUS', connection_id=None)]))
    lease = apply(env, operation(env, 'CLAIM', begun))
    value = empty_account_upload(env, begun, lease, target)
    receipt = apply(env, finish(env, lease, value['request_id']))
    assert receipt['status'] == 'RUNNING' and receipt['stop_confirmed'] is False
    for action in ['CLAIM','RENEW']:
        req = operation(env, action, begun, **({'lease_id':lease['lease_id'], 'execution_generation':1} if action=='RENEW' else {}))
        with pytest.raises(ExecutionRuntimeError, match='lease_conflict'): apply(env, req)
    if remaining_claimed:
        apply(env, operation(env, 'CLAIM', begun, platform_run_id=begun['platform_runs'][1]['platform_run_id']))
    result = apply(env, operation(env, 'CANCEL', begun))
    assert result['status'] == ('CANCELLING' if remaining_claimed else 'CANCELED')
    assert result['stop_confirmed'] is (not remaining_claimed)
    current = env.runtime.get_task(env.claims, begun['task_id'])
    assert current['platform_runs'][0]['status'] == 'SUCCEEDED'
    assert current['stop_confirmed'] is (not remaining_claimed)
    assert env.runtime.get_receipt(env.claims, receipt['request_id']) == receipt


def test_all_platforms_must_finish_before_aggregate_success(env):
    target = account_target(env)
    change_strategy(env, platforms=['BILIBILI','PUBLIC_WEB'])
    begun = apply(env, start(env, targets=[target, dict(platform='PUBLIC_WEB', access_mode='PUBLIC_ANONYMOUS', connection_id=None)]))
    first = apply(env, operation(env, 'CLAIM', begun))
    uploaded = empty_account_upload(env, begun, first, target)
    assert apply(env, finish(env, first, uploaded['request_id']))['status'] == 'RUNNING'
    second = apply(env, operation(env, 'CLAIM', begun, platform_run_id=begun['platform_runs'][1]['platform_run_id']))
    uploaded = payload(env, begun, second, records=[])
    submit(env, service(env), uploaded)
    assert apply(env, finish(env, second, uploaded['request_id']))['status'] == 'SUCCEEDED'


def test_finish_rechecks_current_connection_version(env):
    target = account_target(env)
    change_strategy(env, platforms=['BILIBILI'])
    begun = apply(env, start(env, targets=[target]))
    lease = apply(env, operation(env, 'CLAIM', begun))
    uploaded = empty_account_upload(env, begun, lease, target)
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_platform_connections SET status='EXPIRED' WHERE connection_id=%s", (target['connection_id'],))
    with pytest.raises(ExecutionRuntimeError, match='connection_'):
        apply(env, finish(env, lease, uploaded['request_id']))


def test_old_generation_upload_cannot_finish_reclaimed_lease(env):
    begun, lease = claimed(env)
    uploaded = payload(env, begun, lease, records=[])
    submit(env, service(env), uploaded)
    with env.admin.connect() as conn:
        conn.execute('UPDATE pilot_collection_platform_runs SET lease_expires_at=clock_timestamp() WHERE platform_run_id=%s', (lease['platform_run_id'],))
    current = apply(env, operation(env, 'CLAIM', begun))
    with pytest.raises(ExecutionRuntimeError, match='upload_unavailable'):
        apply(env, finish(env, current, uploaded['request_id']))


@pytest.mark.parametrize('field', ['device_id','credential_version','task_id','run_id','platform_run_id',
    'lease_id','execution_generation','access_mode','connection_id','connection_version'])
def test_stored_batch_context_is_exact_not_just_receipt_id(env, field):
    begun, lease = claimed(env)
    uploaded = payload(env, begun, lease, records=[])
    submit(env, service(env), uploaded)
    context = dict(uploaded['execution'])
    context[field] = 2 if field in ('credential_version','execution_generation','connection_version') else str(uuid4())
    # A fixture-owned malformed historical row; production app cannot mutate batches.
    with env.admin.connect() as conn:
        conn.execute("INSERT INTO pilot_candidate_batches(tenant_id,owner_user_id,platform_run_id,request_id,task_id,run_id,fingerprint,accepted_count,received_at,receipt,platform,profile_version_id,strategy_version_id,execution_context) SELECT tenant_id,owner_user_id,platform_run_id,'malformed',task_id,run_id,fingerprint,accepted_count,received_at,jsonb_set(receipt,'{request_id}','\"malformed\"'),platform,profile_version_id,strategy_version_id,%s::jsonb FROM pilot_candidate_batches WHERE tenant_id=%s AND request_id=%s",
            (json.dumps(context), env.tenant, uploaded['request_id']))
    with pytest.raises(ExecutionRuntimeError, match='upload_unavailable'):
        apply(env, finish(env, lease, 'malformed'))


def test_unknown_malformed_upload_receipt_is_not_success(env):
    begun, lease = claimed(env)
    uploaded = payload(env, begun, lease, records=[])
    submit(env, service(env), uploaded)
    with env.admin.connect() as conn:
        conn.execute("INSERT INTO pilot_candidate_batches(tenant_id,owner_user_id,platform_run_id,request_id,task_id,run_id,fingerprint,accepted_count,received_at,receipt,platform,profile_version_id,strategy_version_id,execution_context) SELECT tenant_id,owner_user_id,platform_run_id,'malformed',task_id,run_id,fingerprint,accepted_count,received_at,jsonb_set(jsonb_set(receipt,'{request_id}','\"malformed\"'),'{accepted_count}','false'),platform,profile_version_id,strategy_version_id,execution_context FROM pilot_candidate_batches WHERE tenant_id=%s AND request_id=%s",
            (env.tenant, uploaded['request_id']))
    with pytest.raises(ExecutionRuntimeError, match='upload_unavailable'):
        apply(env, finish(env, lease, 'malformed'))


def test_socket_https_finish_origin_signature_owner_and_session_fences(env, tmp_path):
    import os, shutil, socket, ssl, subprocess, threading, time
    import httpx, uvicorn
    from pilot.auth import issue_token, verify_token_claims
    from pilot.candidate_ingestion import CandidateIngestionStore
    from pilot.web import build_app
    openssl = shutil.which('openssl')
    if not openssl: pytest.skip('OpenSSL required for isolated local TLS')
    cert, key = tmp_path/'cert.pem', tmp_path/'key.pem'
    subprocess.run([openssl, 'req', '-config', os.devnull, '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
        '-subj', '/CN=127.0.0.1', '-addext', 'subjectAltName=IP:127.0.0.1', '-keyout', str(key), '-out', str(cert)],
        check=True, capture_output=True, timeout=20)
    app = build_app(env.store, auth_secret=SECRET, execution_runtime=env.runtime,
                    candidate_ingestion=CandidateIngestionStore(env.db, env.runtime))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0)); listener.listen(32)
        base = f'https://127.0.0.1:{listener.getsockname()[1]}'
        server = uvicorn.Server(uvicorn.Config(app, log_level='critical', access_log=False, lifespan='off',
            ssl_certfile=str(cert), ssl_keyfile=str(key)))
        thread = threading.Thread(target=server.run, kwargs={'sockets':[listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic()+10
            while not server.started and thread.is_alive() and time.monotonic()<deadline: time.sleep(0.02)
            assert server.started
            token = issue_token(env.users[0], SECRET)
            claims = verify_token_claims(token, SECRET)
            with httpx.Client(base_url=base, verify=ssl.create_default_context(cafile=str(cert)), trust_env=False,
                              timeout=10, headers={'Authorization':'Bearer '+token, 'Origin':base}) as client:
                support_path = '/api/ui/execution-support'
                assert client.get(support_path).json() == {'schema_version':'foreground-collection-support-v1', 'mode':None}
                from pilot.foreground_collection import foreground_collection_policy
                synthetic_policy = env.runtime.capability_check
                env.runtime.capability_check = foreground_collection_policy
                assert client.get(support_path).json() == {'schema_version':'foreground-collection-support-v1', 'mode':'xhs-foreground-v1'}
                env.runtime.capability_check = synthetic_policy
                assert client.get('/api/ui/capabilities').json()['capabilities']['task_execution'] == {'available':False}
                del client.headers['Authorization']
                assert client.get(support_path).status_code == 401
                client.headers['Authorization'] = 'Bearer '+token
                begun, lease = started(client, env, claims)
                raw = payload(env, begun, lease, records=[])
                assert client.post('/api/ui/candidate-batches', json=signed(env, claims, raw)).status_code == 200
                request = finish(env, lease, raw['request_id'])
                bad = client.post('/api/ui/execution-operations', json={'request':request.model_dump(mode='json'), 'signature':'A'*86})
                assert bad.status_code == 400 and bad.json()['detail']['code'] == 'invalid_proof'
                client.headers['Origin'] = 'https://evil.invalid'
                assert send(client, env, claims, request).status_code == 403
                client.headers['Origin'] = base
                foreign = verify_token_claims(issue_token(env.users[1], SECRET), SECRET)
                client.headers['Authorization'] = 'Bearer '+issue_token(env.users[1], SECRET)
                assert send(client, env, foreign, request).status_code == 404
                client.headers['Authorization'] = 'Bearer '+token
                result = send(client, env, claims, request)
                assert result.status_code == 200 and result.json()['status'] == 'SUCCEEDED'
                assert send(client, env, claims, request).json() == result.json()
                env.store.sessions.revoke([claims])
                assert send(client, env, claims, request).status_code == 401
                assert client.get(support_path).status_code == 401
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive()
    from fastapi.testclient import TestClient
    with TestClient(app, base_url='http://pilot.example') as insecure:
        insecure.headers['Authorization'] = 'Bearer '+issue_token(env.users[0], SECRET)
        assert insecure.get('/api/ui/execution-support').status_code == 400
