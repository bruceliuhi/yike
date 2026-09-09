"""Synthetic DB-only strategy; real PostgreSQL/RLS and Ed25519, no platform proof."""
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql
import pytest
from nacl.signing import SigningKey

from pilot.auth import issue_token, verify_token_claims
from pilot.candidate_contract import validate_candidate_batch
from pilot.db import PilotDatabase
from pilot.execution_contract import ExecutionOperation, ExecutionRuntimeError
from pilot.execution_runtime import (ConfirmedExecutionStrategy, ExecutionRuntime,
    execution_signing_payload, submission_signing_payload)
from pilot.store import PilotStore
from tests.test_device_credentials_postgres import bind, wait_for_lock, RoleDatabase
from pilot.device_credentials import DeviceCredentialStore
from tests.test_device_keys import encoded
from tests.test_execution_contract import start_body

SECRET = 'synthetic-execution-test-key'
TABLES = ('pilot_execution_operations', 'pilot_collection_platform_runs',
          'pilot_collection_runs', 'pilot_collection_tasks')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


@pytest.fixture(scope='module')
def databases():
    admin_url, app_url = (os.environ.get(key) for key in
        ('YIKE_IDENTITY_TEST_DATABASE_URL', 'YIKE_IDENTITY_TEST_APP_DATABASE_URL'))
    if not admin_url or not app_url:
        pytest.skip('dedicated identity PostgreSQL required')
    admin, app = PilotDatabase(admin_url), PilotDatabase(app_url)
    admin.migrate()
    admin.migrate()
    role = 'execution_test_' + uuid4().hex
    app = RoleDatabase(admin, role)
    with admin.connect() as conn:
        conn.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE').format(sql.Identifier(role)))
        conn.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('GRANT SELECT ON pilot_users,business_profiles,business_profile_versions TO {}').format(sql.Identifier(role)))
        # FOR UPDATE needs a column UPDATE privilege; no profile content/owner edits.
        conn.execute(sql.SQL('GRANT UPDATE(name) ON business_profiles TO {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('GRANT UPDATE(status) ON business_profile_versions TO {}').format(sql.Identifier(role)))
        conn.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
        for filename in ('grant_session_revocations.sql', 'grant_device_credentials.sql',
                         'grant_connection_operations.sql', 'grant_execution_runtime.sql'):
            grant = (Path(__file__).parents[1] / 'deploy' / filename).read_text()
            conn.execute(grant)
            conn.execute(grant)
    yield admin, app
    with admin.connect() as conn:
        conn.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


@pytest.fixture
def env(databases):
    admin, db = databases
    provisioner, store = PilotStore(admin), PilotStore(db)
    tenants = [provisioner.provision_tenant('synthetic-execution') for _ in range(2)]
    users = [provisioner.provision_user(t, f'{uuid4()}@example.invalid')
             for t in (tenants[0], tenants[0], tenants[1])]
    claims = verify_token_claims(issue_token(users[0], SECRET), SECRET)
    device = store.register_device(users[0], 'synthetic-execution')['device_id']
    key = SigningKey.generate()
    bind(SimpleNamespace(service=DeviceCredentialStore(db), claims=claims, device=device), key)
    profile = provisioner.save_profile(users[0], {'description': 'synthetic only'})['version_id']
    provisioner.confirm_profile(users[0], profile)
    snapshot = dict(profile_version_id=profile, strategy_version_id='synthetic-strategy',
                    configuration={'query': 'synthetic'}, platforms=['PUBLIC_WEB'],
                    max_records=2, max_runtime_seconds=600)
    # Strategy persistence is deliberately fixture-owned, not a production resolver.
    with admin.connect() as conn:
        conn.execute('UPDATE business_profile_versions SET payload=%s::jsonb WHERE profile_version_id=%s',
                     (json.dumps({'synthetic_strategy': snapshot}), profile))
    def resolver(cursor, owner, profile_id, strategy_id):
        cursor.execute('SELECT payload FROM business_profile_versions WHERE profile_version_id=%s', (profile_id,))
        row = cursor.fetchone()
        value = row[0].get('synthetic_strategy') if row else None
        if not value or value['strategy_version_id'] != strategy_id:
            raise ExecutionRuntimeError('strategy_unavailable', 409)
        return ConfirmedExecutionStrategy(**(value | {'platforms': tuple(value['platforms']),
                                                      'configuration_sha256': digest(value)}))
    runtime = ExecutionRuntime(db, strategy_resolver=resolver, capability_check=lambda *args: True)
    yield SimpleNamespace(admin=admin, db=db, claims=claims, device=device, key=key,
        tenant=tenants[0], tenants=tenants, users=users, profile=profile, snapshot=snapshot,
        runtime=runtime, store=store, resolver=resolver)
    with admin.connect() as conn:
        for table in TABLES + ('pilot_execution_events', 'pilot_connection_operations',
             'pilot_platform_connections', 'pilot_device_key_requests', 'pilot_device_credentials',
             'pilot_devices', 'pilot_tasks', 'business_profile_versions', 'business_profiles',
             'pilot_session_revocations', 'pilot_users', 'pilot_tenants'):
            conn.execute(f'DELETE FROM {table} WHERE tenant_id=ANY(%s)', (tenants,))


def start(env, **changes):
    return ExecutionOperation.model_validate(start_body(device_id=env.device,
        profile_version_id=env.profile, strategy_version_id=env.snapshot['strategy_version_id'],
        configuration_sha256=digest(env.snapshot), **changes))


def operation(env, action, receipt, **changes):
    return ExecutionOperation.model_validate(start_body(operation=action, device_id=env.device,
        task_id=receipt['task_id'], platform_run_id=None if action == 'CANCEL' else receipt['platform_runs'][0]['platform_run_id'],
        profile_version_id=None, strategy_version_id=None, configuration_sha256=None, targets=None,
        lease_id=receipt.get('lease_id') if action == 'RENEW' else None,
        execution_generation=receipt.get('execution_generation') if action == 'RENEW' else None) | changes)


def apply(env, request, claims=None, key=None):
    claims = claims or env.claims
    signature = encoded((key or env.key).sign(execution_signing_payload(
        tenant_id=env.tenant, claims=claims, operation=request).encode()).signature)
    return env.runtime.apply(claims, request, signature)


def claimed(env):
    begun = apply(env, start(env))
    lease = apply(env, operation(env, 'CLAIM', begun))
    return begun, lease


def batch(env, begun, lease):
    return validate_candidate_batch(dict(schema_version='candidate-upload-v1', request_id=str(uuid4()),
        platform='PUBLIC_WEB', profile_version_id=env.profile, strategy_version_id=env.snapshot['strategy_version_id'],
        execution=dict(device_id=env.device, credential_version=1, task_id=begun['task_id'],
            run_id=begun['run_id'], platform_run_id=lease['platform_run_id'],
            lease_id=lease['lease_id'], execution_generation=lease['execution_generation'],
            access_mode='PUBLIC_ANONYMOUS', connection_id=None, connection_version=None),
        records=[dict(kind='PAGE', external_source_id=None, external_comment_id=None,
            public_url='https://example.com/synthetic', title=None, author_public_id=None,
            body='synthetic observation', published_at=None, observed_at='2026-01-01T00:00:00Z',
            parent=None, collector_version='synthetic-v1', normalizer_version='synthetic-v1', query=None)]),
        now=datetime.now(UTC))


def guard(env, cursor, candidate):
    signature = encoded(env.key.sign(submission_signing_payload(tenant_id=env.tenant,
        claims=env.claims, batch=candidate).encode()).signature)
    return env.runtime.lock_submission(cursor, env.claims, batch=candidate, signature=signature)


def test_start_idempotent_and_conflict_without_refill(env):
    request = start(env)
    first = apply(env, request)
    assert first['status'] == 'PENDING'
    assert apply(env, request) == first
    assert env.runtime.get_receipt(env.claims, request.request_id) == first
    with pytest.raises(ExecutionRuntimeError, match='request_conflict'):
        apply(env, request.model_copy(update={'configuration_sha256': 'b' * 64}))
    with env.admin.connect() as conn:
        assert conn.execute('SELECT count(*) FROM pilot_collection_tasks WHERE tenant_id=%s', (env.tenant,)).fetchone()[0] == 1


def test_claim_renew_replay_and_cancel_invalidate_submission(env):
    begun, lease = claimed(env)
    assert lease['execution_generation'] == 1
    with pytest.raises(ExecutionRuntimeError, match='lease_conflict'):
        apply(env, operation(env, 'CLAIM', begun))
    renew = operation(env, 'RENEW', begun, lease_id=lease['lease_id'], execution_generation=1)
    renewed = apply(env, renew)
    assert apply(env, renew) == renewed
    candidate = batch(env, begun, lease)
    with env.db.connect() as conn:
        assert guard(env, conn.cursor(), candidate)['remaining_records'] == 2
    cancel = operation(env, 'CANCEL', begun)
    canceled = apply(env, cancel)
    assert canceled['status'] == 'CANCELLING' and canceled['stop_confirmed'] is False
    assert apply(env, cancel) == canceled
    for request in (renew.model_copy(update={'request_id': str(uuid4())}), operation(env, 'CLAIM', begun)):
        with pytest.raises(ExecutionRuntimeError, match='task_cancelled'):
            apply(env, request)
    with pytest.raises(ExecutionRuntimeError, match='task_cancelled'):
        with env.db.connect() as conn:
            guard(env, conn.cursor(), candidate)


def test_cancel_before_any_lease_can_confirm_stop(env):
    begun = apply(env, start(env))
    result = apply(env, operation(env, 'CANCEL', begun))
    assert result['status'] == 'CANCELED' and result['stop_confirmed'] is True


@pytest.mark.parametrize('reason', ['missing_resolver', 'missing_capability', 'false_capability', 'profile', 'strategy', 'digest', 'limit'])
def test_start_fail_closed_creates_no_authority(env, reason):
    request = start(env)
    if reason == 'missing_resolver': env.runtime = ExecutionRuntime(env.db)
    if reason == 'missing_capability': env.runtime = ExecutionRuntime(env.db, strategy_resolver=env.resolver)
    if reason == 'false_capability': env.runtime = ExecutionRuntime(env.db, strategy_resolver=env.resolver, capability_check=lambda *args: False)
    if reason in ('profile', 'strategy', 'limit'):
        with env.admin.connect() as conn:
            if reason == 'profile': conn.execute("UPDATE business_profile_versions SET status='REVOKED' WHERE profile_version_id=%s", (env.profile,))
            else:
                value = {} if reason == 'strategy' else {'synthetic_strategy': env.snapshot | {'max_records': True}}
                conn.execute('UPDATE business_profile_versions SET payload=%s::jsonb WHERE profile_version_id=%s', (json.dumps(value), env.profile))
    if reason == 'digest': request = request.model_copy(update={'configuration_sha256': 'b' * 64})
    with pytest.raises(ExecutionRuntimeError): apply(env, request)
    with env.admin.connect() as conn:
        assert conn.execute('SELECT count(*) FROM pilot_collection_tasks WHERE tenant_id=%s', (env.tenant,)).fetchone()[0] == 0


def test_wrong_signature_and_history_after_device_revoke_new_session(env):
    request = start(env)
    with pytest.raises(ExecutionRuntimeError, match='invalid_proof'):
        apply(env, request, key=SigningKey.generate())
    first = apply(env, request)
    env.store.revoke_device(env.users[0], env.device)
    new_claims = verify_token_claims(issue_token(env.users[0], SECRET), SECRET)
    assert apply(env, request, claims=new_claims) == first
    env.store.sessions.revoke([new_claims])
    with pytest.raises(ExecutionRuntimeError, match='invalid_session'):
        apply(env, request, claims=new_claims)


@pytest.mark.parametrize('user_index', [1, 2])
def test_other_owner_reads_and_mutations_denied(env, user_index):
    request = start(env)
    begun = apply(env, request)
    other = verify_token_claims(issue_token(env.users[user_index], SECRET), SECRET)
    for call in (lambda: env.runtime.get_receipt(other, request.request_id),
                 lambda: env.runtime.get_task(other, begun['task_id']),
                 lambda: apply(env, operation(env, 'CANCEL', begun), claims=other)):
        with pytest.raises(ExecutionRuntimeError): call()


def test_expired_lease_takeover_fences_old_generation_and_never_claims_stop(env):
    begun, lease = claimed(env)
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_collection_platform_runs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE platform_run_id=%s", (lease['platform_run_id'],))
    with pytest.raises(ExecutionRuntimeError, match='lease_expired'):
        apply(env, operation(env, 'RENEW', begun, lease_id=lease['lease_id'], execution_generation=1))
    newer = apply(env, operation(env, 'CLAIM', begun))
    assert newer['execution_generation'] == 2 and newer['lease_id'] != lease['lease_id']
    with pytest.raises(ExecutionRuntimeError, match='lease_conflict'):
        with env.db.connect() as conn: guard(env, conn.cursor(), batch(env, begun, lease))
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_collection_platform_runs SET status='PENDING',lease_expires_at=clock_timestamp()-interval '1 second' WHERE platform_run_id=%s", (lease['platform_run_id'],))
    assert apply(env, operation(env, 'CANCEL', begun))['stop_confirmed'] is False


def test_caller_owned_budget_rollback_and_final_fence_after_consumption(env):
    begun, lease = claimed(env)
    candidate = batch(env, begun, lease)
    with env.db.connect() as conn:
        cursor = conn.cursor()
        with pytest.raises(ExecutionRuntimeError, match='submission_guard_required'):
            env.runtime.recheck_submission_fence(cursor, env.claims, batch=candidate)
        assert guard(env, cursor, candidate)['remaining_records'] == 2
        cursor.execute('UPDATE pilot_collection_platform_runs SET records_used=2 WHERE platform_run_id=%s', (lease['platform_run_id'],))
        env.runtime.recheck_submission_fence(cursor, env.claims, batch=candidate)
        conn.rollback()
        with pytest.raises(ExecutionRuntimeError, match='submission_guard_required'):
            env.runtime.recheck_submission_fence(cursor, env.claims, batch=candidate)
    with env.db.connect() as conn:
        cursor = conn.cursor()
        assert guard(env, cursor, candidate)['remaining_records'] == 2
        cursor.execute('UPDATE pilot_collection_platform_runs SET records_used=2 WHERE platform_run_id=%s', (lease['platform_run_id'],))
        env.runtime.recheck_submission_fence(cursor, env.claims, batch=candidate)
    with pytest.raises(ExecutionRuntimeError, match='budget_exhausted'):
        with env.db.connect() as conn: guard(env, conn.cursor(), candidate)
    with env.db.connect() as conn:
        conn.commit()
        conn.autocommit = True
        with pytest.raises(ExecutionRuntimeError, match='transaction_required'):
            guard(env, conn.cursor(), candidate)


def test_concurrent_original_request_has_one_effect(env):
    request = start(env)
    with ThreadPoolExecutor(2) as pool:
        a, b = [pool.submit(apply, env, request) for _ in range(2)]
        assert a.result(timeout=10) == b.result(timeout=10)
    with env.admin.connect() as conn:
        assert conn.execute('SELECT count(*) FROM pilot_collection_tasks WHERE tenant_id=%s', (env.tenant,)).fetchone()[0] == 1


def test_cancel_remains_available_after_profile_strategy_failure(env):
    begun, _ = claimed(env)
    with env.admin.connect() as conn:
        conn.execute("UPDATE business_profile_versions SET status='REVOKED',payload='{}' WHERE profile_version_id=%s", (env.profile,))
    assert apply(env, operation(env, 'CANCEL', begun))['status'] == 'CANCELLING'


def test_restricted_grants_rls_and_immutable_snapshot_receipt(env):
    request = start(env)
    begun = apply(env, request)
    with env.db.connect() as conn:
        for table in TABLES:
            assert conn.execute('SELECT row_security_active(%s::regclass)', (table,)).fetchone()[0]
            assert not conn.execute("SELECT has_table_privilege(current_user,%s,'DELETE')", (table,)).fetchone()[0]
            assert conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0
        for table, column in (('pilot_collection_tasks', 'configuration_snapshot'), ('pilot_execution_operations', 'receipt'), ('pilot_collection_tasks', 'owner_user_id')):
            assert not conn.execute('SELECT has_column_privilege(current_user,%s,%s,\'UPDATE\')', (table, column)).fetchone()[0]
        assert not conn.execute("SELECT has_table_privilege(current_user,'pilot_users','UPDATE')").fetchone()[0]
    for query, params in (
        ("UPDATE pilot_collection_tasks SET configuration_snapshot='{}' WHERE task_id=%s", (begun['task_id'],)),
        ("UPDATE pilot_execution_operations SET receipt='{}' WHERE request_id=%s", (request.request_id,))):
        with pytest.raises(psycopg.errors.RaiseException, match='immutable'):
            with env.admin.connect() as conn: conn.execute(query, params)


def test_session_expiry_after_device_lock_wait_is_live_database_clock(env):
    deadline = int(time.time()) + 2
    env.claims = replace(env.claims, expires_at=deadline)
    with ThreadPoolExecutor(1) as pool:
        with env.admin.connect() as blocker:
            blocker.execute('SELECT 1 FROM pilot_devices WHERE device_id=%s FOR UPDATE', (env.device,))
            future = pool.submit(apply, env, start(env))
            wait_for_lock(env.admin, 'pilot_devices')
            while time.time() <= deadline: time.sleep(0.01)
        with pytest.raises(ExecutionRuntimeError, match='invalid_session'):
            future.result(timeout=5)


def change_strategy(env, **changes):
    env.snapshot.update(changes)
    with env.admin.connect() as conn:
        conn.execute('UPDATE business_profile_versions SET payload=%s::jsonb WHERE profile_version_id=%s',
                     (json.dumps({'synthetic_strategy': env.snapshot}), env.profile))


def test_strategy_limit_change_does_not_refill_existing_task(env):
    begun = apply(env, start(env))
    change_strategy(env, max_records=20)
    with pytest.raises(ExecutionRuntimeError, match='strategy_conflict'):
        apply(env, operation(env, 'CLAIM', begun))
    assert env.runtime.get_task(env.claims, begun['task_id'])['max_records'] == 2


@pytest.mark.parametrize('configuration', [[], {'x': float('nan')}, {'x': 'x'*65537}, {'x': 1}])
def test_resolver_bad_snapshot_is_rejected(env, configuration):
    original = env.resolver
    env.runtime.strategy_resolver = lambda *args: replace(original(*args), configuration=configuration)
    with pytest.raises(ExecutionRuntimeError, match='strategy_conflict'):
        apply(env, start(env))


def test_signature_covers_batch_request_and_full_body(env):
    begun, lease = claimed(env)
    candidate = batch(env, begun, lease)
    signature = encoded(env.key.sign(submission_signing_payload(tenant_id=env.tenant,
        claims=env.claims, batch=candidate).encode()).signature)
    with pytest.raises(ExecutionRuntimeError, match='invalid_proof'):
        with env.db.connect() as conn:
            env.runtime.lock_submission(conn.cursor(), env.claims,
                batch=candidate.model_copy(update={'request_id': str(uuid4())}), signature=signature)
    forged = candidate.model_copy(update={'execution': candidate.execution.model_copy(update={'credential_version': True})})
    with pytest.raises(ExecutionRuntimeError, match='invalid_batch'):
        with env.db.connect() as conn: guard(env, conn.cursor(), forged)


@pytest.mark.parametrize('signature', [None, '', 123, 'not-a-signature'])
def test_submission_never_accepts_missing_or_invalid_signature(env, signature):
    begun, lease = claimed(env)
    with pytest.raises(ExecutionRuntimeError, match='invalid_proof'):
        with env.db.connect() as conn:
            env.runtime.lock_submission(conn.cursor(), env.claims,
                batch=batch(env, begun, lease), signature=signature)


@pytest.mark.parametrize('changes', [{'max_records':10001}, {'max_runtime_seconds':86401}])
def test_confirmed_limits_are_bounded_even_with_valid_digest(env, changes):
    change_strategy(env, **changes)
    with pytest.raises(ExecutionRuntimeError, match='strategy_conflict'):
        apply(env, start(env))


def test_start_rechecks_deadline_after_receipt_insert_wait(env):
    change_strategy(env, max_runtime_seconds=1)
    # Test-only trigger induces a bounded real server-side final-write delay.
    function = 'synthetic_execution_wait_' + uuid4().hex
    trigger = function
    with env.admin.connect() as conn:
        conn.execute(sql.SQL("CREATE FUNCTION {}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.tenant_id={} THEN PERFORM pg_sleep(1.1); END IF; RETURN NEW; END $$").format(sql.Identifier(function), sql.Literal(env.tenant)))
        conn.execute(sql.SQL('CREATE TRIGGER {} BEFORE INSERT ON pilot_execution_operations FOR EACH ROW EXECUTE FUNCTION {}()').format(sql.Identifier(trigger), sql.Identifier(function)))
    try:
        with pytest.raises(ExecutionRuntimeError, match='task_expired'):
            apply(env, start(env))
        with env.admin.connect() as conn:
            assert conn.execute('SELECT count(*) FROM pilot_collection_tasks WHERE tenant_id=%s', (env.tenant,)).fetchone()[0] == 0
    finally:
        with env.admin.connect() as conn:
            conn.execute(sql.SQL('DROP TRIGGER {} ON pilot_execution_operations').format(sql.Identifier(trigger)))
            conn.execute(sql.SQL('DROP FUNCTION {}()').format(sql.Identifier(function)))


def test_rotated_key_fences_old_lease_and_new_claim_binds_new_version(env):
    from tests.test_device_credentials_postgres import challenge, complete
    begun, lease = claimed(env)
    new_key = SigningKey.generate()
    key_env = SimpleNamespace(service=DeviceCredentialStore(env.db), claims=env.claims, device=env.device)
    complete(key_env, challenge(key_env, 'ROTATE', 1, new_key), new_key, env.key)
    with pytest.raises(ExecutionRuntimeError, match='credential_conflict'):
        with env.db.connect() as conn: guard(env, conn.cursor(), batch(env, begun, lease))
    env.key = new_key
    with pytest.raises(ExecutionRuntimeError, match='lease_conflict'):
        apply(env, operation(env, 'RENEW', begun, credential_version=2,
                            lease_id=lease['lease_id'], execution_generation=1))
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_collection_platform_runs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE platform_run_id=%s", (lease['platform_run_id'],))
    assert apply(env, operation(env, 'CLAIM', begun, credential_version=2))['execution_generation'] == 2


def test_connection_versions_and_disconnect_fence_but_cancel_survives(env):
    from pilot.connection_versions import ConnectionOperation, ConnectionOperationStore
    service = ConnectionOperationStore(env.db)
    registered = service.apply(env.claims, ConnectionOperation(request_id=str(uuid4()), action='REGISTER',
        device_id=env.device, connection_id=None, expected_connection_version=0,
        platform='BILIBILI', account_public_id='synthetic', session_ref='vault://synthetic'))
    connection = registered['connection_id']
    with env.admin.connect() as conn:
        version = conn.execute("UPDATE pilot_platform_connections SET status='CONNECTED' WHERE connection_id=%s RETURNING connection_version", (connection,)).fetchone()[0]
    change_strategy(env, platforms=['BILIBILI'])
    target = dict(platform='BILIBILI', access_mode='PLATFORM_ACCOUNT', connection_id=connection, connection_version=version)
    begun = apply(env, start(env, targets=[target]))
    lease = apply(env, operation(env, 'CLAIM', begun))
    with env.admin.connect() as conn:
        conn.execute('UPDATE pilot_platform_connections SET connection_version=connection_version+1 WHERE connection_id=%s', (connection,))
    with pytest.raises(ExecutionRuntimeError, match='connection_version_conflict'):
        apply(env, operation(env, 'RENEW', begun, lease_id=lease['lease_id'], execution_generation=1))
    assert apply(env, operation(env, 'CANCEL', begun))['stop_confirmed'] is False


def test_lease_expiry_rechecked_after_task_lock_wait(env):
    begun, lease = claimed(env)
    deadline = int(time.time()) + 2
    with env.admin.connect() as conn:
        conn.execute('UPDATE pilot_collection_platform_runs SET lease_expires_at=to_timestamp(%s) WHERE platform_run_id=%s', (deadline, lease['platform_run_id']))
    with ThreadPoolExecutor(1) as pool:
        with env.admin.connect() as blocker:
            blocker.execute('SELECT 1 FROM pilot_collection_tasks WHERE task_id=%s FOR UPDATE', (begun['task_id'],))
            future = pool.submit(apply, env, operation(env, 'RENEW', begun,
                lease_id=lease['lease_id'], execution_generation=1))
            wait_for_lock(env.admin, 'pilot_collection_tasks')
            while time.time() <= deadline: time.sleep(0.01)
        with pytest.raises(ExecutionRuntimeError, match='lease_expired'):
            future.result(timeout=5)


def test_cancel_wins_device_lock_then_queued_submission_is_rejected(env):
    begun, lease = claimed(env)
    candidate = batch(env, begun, lease)
    def submit():
        with env.db.connect() as conn: return guard(env, conn.cursor(), candidate)
    with ThreadPoolExecutor(2) as pool:
        with env.admin.connect() as blocker:
            blocker.execute('SELECT 1 FROM pilot_devices WHERE device_id=%s FOR UPDATE', (env.device,))
            cancel = pool.submit(apply, env, operation(env, 'CANCEL', begun))
            wait_for_lock(env.admin, 'pilot_devices')
            submission = pool.submit(submit)
            wait_for_lock(env.admin, 'pg_advisory_xact_lock')
        assert cancel.result(timeout=5)['status'] == 'CANCELLING'
        with pytest.raises(ExecutionRuntimeError, match='task_cancelled'):
            submission.result(timeout=5)


def test_final_fence_checks_expired_lease_even_after_budget_consumption(env):
    begun, lease = claimed(env)
    candidate = batch(env, begun, lease)
    with pytest.raises(ExecutionRuntimeError, match='lease_expired'):
        with env.db.connect() as conn:
            cursor = conn.cursor()
            guard(env, cursor, candidate)
            cursor.execute('UPDATE pilot_collection_platform_runs SET records_used=2,lease_expires_at=clock_timestamp()-interval \'1 second\' WHERE platform_run_id=%s', (lease['platform_run_id'],))
            env.runtime.recheck_submission_fence(cursor, env.claims, batch=candidate)
    assert env.runtime.get_task(env.claims, begun['task_id'])['records_used'] == 0


def test_database_budget_constraint_blocks_overspend(env):
    begun, lease = claimed(env)
    with pytest.raises(psycopg.errors.RaiseException, match='budget exceeded'):
        with env.db.connect() as conn:
            guard(env, conn.cursor(), batch(env, begun, lease))
            conn.execute('UPDATE pilot_collection_platform_runs SET records_used=3 WHERE platform_run_id=%s', (lease['platform_run_id'],))


@pytest.mark.parametrize('target', ['', 'postgres', 'not_an_execution_role'])
def test_grant_rejects_unrestricted_or_missing_role(databases, target):
    admin, _ = databases
    with pytest.raises(psycopg.errors.RaiseException, match='restricted application role'):
        with admin.connect() as conn:
            conn.execute("SELECT set_config('yike.app_role',%s,true)", (target,))
            conn.execute((Path(__file__).parents[1] / 'deploy/grant_execution_runtime.sql').read_text())


def test_empty_database_migration_is_repeatable_with_current_constraints(databases):
    admin, _ = databases
    name = 'synthetic_execution_fresh_' + uuid4().hex
    fresh = PilotDatabase(urlunsplit(urlsplit(admin.url)._replace(path='/' + name)))
    created = False
    try:
        with admin.connect() as conn:
            conn.autocommit = True
            conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
            created = True
        fresh.migrate()
        fresh.migrate()
        with fresh.connect() as conn:
            assert conn.execute('SELECT count(*) FROM pilot_schema_meta').fetchone()[0] == len(PilotDatabase.migration_paths)
            for table in TABLES:
                assert conn.execute('SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=%s::regclass', (table,)).fetchone() == (True, True)
            constraints = [row[0] for row in conn.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='pilot_collection_tasks'::regclass")]
            assert any('max_records <= 10000' in item for item in constraints)
            assert any('max_runtime_seconds <= 86400' in item for item in constraints)
    finally:
        if created:
            with admin.connect() as conn:
                conn.autocommit = True
                conn.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
