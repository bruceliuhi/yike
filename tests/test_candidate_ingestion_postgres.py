"""Signed synthetic observations on real restricted PostgreSQL; no platform proof."""
import copy
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import psycopg
from psycopg import sql
from pilot.auth import issue_token, verify_token_claims
from pilot.candidate_contract import validate_candidate_batch
from pilot.execution_contract import ExecutionRuntimeError
from pilot.execution_runtime import submission_signing_payload
from tests.test_device_keys import encoded
from tests.test_execution_runtime_postgres import (
    databases as execution_databases, env as execution_env, batch, claimed,
    change_strategy, apply, operation, start, SECRET,
    test_empty_database_migration_is_repeatable_with_current_constraints)

TABLES = ('pilot_candidate_observations', 'pilot_candidate_projections',
          'pilot_candidate_versions', 'pilot_candidate_sources', 'pilot_candidate_batches')

@pytest.fixture(scope='module')
def databases(execution_databases):
    admin, db = execution_databases
    grant = Path(__file__).parents[1] / 'deploy/grant_candidate_ingestion.sql'
    if grant.exists():
        with db.connect() as conn:
            role = conn.execute('SELECT current_user').fetchone()[0]
        with admin.connect() as conn:
            conn.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
            conn.execute(grant.read_text())
            conn.execute(grant.read_text())
    yield admin, db

@pytest.fixture
def env(execution_env):
    yield execution_env
    with execution_env.admin.connect() as conn:
        for table in TABLES:
            if conn.execute('SELECT to_regclass(%s)', (table,)).fetchone()[0]:
                conn.execute(f'DELETE FROM {table} WHERE tenant_id=ANY(%s)', (execution_env.tenants,))

def service(env):
    assert importlib.util.find_spec('pilot.candidate_ingestion') is not None, 'candidate ingestion service is missing'
    from pilot.candidate_ingestion import CandidateIngestionStore
    return CandidateIngestionStore(env.db, env.runtime)

def payload(env, begun, lease, **changes):
    # Preserve absent optional context; explicit null is deliberately invalid.
    # Unlike exclude_none, this retains required nullable wire fields.
    value = batch(env, begun, lease).model_dump(mode='json', exclude_unset=True)
    value.update(changes)
    return value

def test_synthetic_payload_preserves_absent_context_and_required_null_fields():
    from datetime import UTC, datetime
    from pilot.candidate_contract import CandidateContractError

    fixture_env = SimpleNamespace(profile='profile-1', device='device-1',
        snapshot={'strategy_version_id': 'strategy-1'})
    value = payload(fixture_env, {'task_id': 'task-1', 'run_id': 'run-1'},
        {'platform_run_id': 'platform-run-1', 'lease_id': 'lease-1',
         'execution_generation': 1})
    record = value['records'][0]
    assert 'source_context' not in record
    assert 'parent' in record and record['parent'] is None
    assert 'published_at' in record and record['published_at'] is None
    assert validate_candidate_batch(value, now=datetime.now(UTC)).records[0].body == 'synthetic observation'
    record['source_context'] = None
    with pytest.raises(CandidateContractError, match='INVALID_RECORD'):
        validate_candidate_batch(value, now=datetime.now(UTC))


def submit(env, store, value, claims=None):
    from datetime import UTC, datetime
    claims = claims or env.claims
    candidate = validate_candidate_batch(value, now=datetime.now(UTC))
    signature = encoded(env.key.sign(submission_signing_payload(
        tenant_id=env.tenant, claims=claims, batch=candidate).encode()).signature)
    return store.ingest(claims, value, signature)

def test_atomic_receipt_replay_conflict_and_history(env):
    store = service(env)
    begun, lease = claimed(env)
    value = payload(env, begun, lease, request_id='opaque.batch-1')
    receipt = submit(env, store, value)
    assert receipt['accepted_count'] == 1
    assert receipt['items'][0]['revision'] == 1
    assert submit(env, service(env), value) == receipt
    changed = copy.deepcopy(value)
    changed['records'][0]['body'] = 'changed'
    from pilot.candidate_ingestion import CandidateIngestionError
    with pytest.raises(CandidateIngestionError, match='request_conflict'):
        submit(env, store, changed)
    apply(env, operation(env, 'CANCEL', begun))
    env.store.revoke_device(env.users[0],env.device)
    change_strategy(env,max_records=7)
    assert store.ingest(env.claims, value, 'historical-does-not-authorize') == receipt
    assert store.get_receipt(env.claims, lease['platform_run_id'], value['request_id']) == receipt
    assert env.runtime.get_task(env.claims, begun['task_id'])['records_used'] == 1

@pytest.mark.parametrize('sequence,revision,body,ambiguous', [
    ([('A',10),('A',20),('B',15)],1,'A',False),
    ([('A',10),('B',20),('A',30)],3,'A',False),
    ([('A',10),('B',10)],2,'A',True),
    ([('A',10),('B',10),('A',20)],3,'A',False)])
def test_temporal_projection(env, sequence, revision, body, ambiguous):
    store = service(env)
    change_strategy(env, max_records=10)
    begun, lease = claimed(env)
    for text, second in sequence:
        value = payload(env, begun, lease)
        value['records'][0].update(body=text, observed_at=f'2026-01-01T00:00:{second:02d}Z')
        receipt = submit(env, store, value)
    detail = store.get_candidate(env.claims, receipt['items'][0]['candidate_id'])
    candidate = detail['candidate']
    assert (candidate['revision'],candidate['current_version']['body'],candidate['ambiguous']) == (revision,body,ambiguous)
    assert detail['observations']['total'] == len(sequence)
    assert store.list_candidates(env.claims, task_id=begun['task_id'])['total'] == 1

def test_concurrent_replay_different_sessions_and_owner_isolation(env):
    store = service(env)
    begun, lease = claimed(env)
    value = payload(env, begun, lease)
    other_session = verify_token_claims(issue_token(env.users[0], SECRET), SECRET)
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(submit, env, store, value, claims) for claims in (env.claims, other_session)]
        receipts = [f.result(timeout=10) for f in futures]
    assert receipts[0] == receipts[1]
    from pilot.candidate_ingestion import CandidateIngestionError
    for user in env.users[1:]:
        claims = verify_token_claims(issue_token(user, SECRET), SECRET)
        assert store.list_candidates(claims)['total'] == 0
        with pytest.raises(CandidateIngestionError, match='not_found'):
            store.get_receipt(claims, lease['platform_run_id'], value['request_id'])
        with pytest.raises(CandidateIngestionError, match='not_found'):
            store.get_candidate(claims, receipts[0]['items'][0]['candidate_id'])

def test_final_fence_rollback(env):
    store = service(env)
    begun, lease = claimed(env)
    original = env.runtime.recheck_submission_fence
    def expired(cursor, claims, *, batch):
        cursor.execute("UPDATE pilot_collection_platform_runs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE platform_run_id=%s", (lease['platform_run_id'],))
        return original(cursor, claims, batch=batch)
    env.runtime.recheck_submission_fence = expired
    with pytest.raises(ExecutionRuntimeError, match='lease_expired'):
        submit(env, store, payload(env, begun, lease))
    assert store.list_candidates(env.claims)['total'] == 0
    assert env.runtime.get_task(env.claims, begun['task_id'])['records_used'] == 0

def test_raw_order_null_unicode_origins_and_empty(env):
    store = service(env)
    change_strategy(env, max_records=10)
    begun, lease = claimed(env)
    value = payload(env, begun, lease)
    record = value['records'][0]
    record.update(external_source_id='same', body='  中文\n原文  ')
    value['records'].append(record | {'public_url':'https://other.example/synthetic'})
    receipt = submit(env, store, value)
    assert [item['index'] for item in receipt['items']] == [0,1]
    assert len(set(item['candidate_id'] for item in receipt['items'])) == 2
    detail = store.get_candidate(env.claims, receipt['items'][0]['candidate_id'])['candidate']
    assert detail['current_version']['body'] == '  中文\n原文  '
    assert detail['current_version']['published_at'] is None
    assert submit(env, store, payload(env, begun, lease, records=[]))['accepted_count'] == 0

@pytest.mark.parametrize('change', ['device','run','generation','cancel','expiry','revoked_session','strategy'])
def test_new_work_denial_leaves_no_rows(env, change):
    store = service(env)
    begun, lease = claimed(env)
    value = payload(env,begun,lease)
    if change == 'device': value['execution']['device_id'] = str(uuid4())
    if change == 'run': value['execution']['run_id'] = str(uuid4())
    if change == 'generation': value['execution']['execution_generation'] += 1
    if change == 'cancel': apply(env,operation(env,'CANCEL',begun))
    if change == 'revoked_session': store.sessions.revoke([env.claims])
    if change == 'strategy': change_strategy(env, max_records=9)
    if change == 'expiry':
        with env.admin.connect() as conn:
            conn.execute("UPDATE pilot_collection_platform_runs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE platform_run_id=%s",(lease['platform_run_id'],))
    from pilot.candidate_ingestion import CandidateIngestionError
    with pytest.raises((CandidateIngestionError,ExecutionRuntimeError)):
        submit(env,store,value)
    with env.admin.connect() as conn:
        for table in TABLES:
            assert conn.execute(f'SELECT count(*) FROM {table} WHERE tenant_id=%s',(env.tenant,)).fetchone()[0] == 0
        assert conn.execute('SELECT records_used FROM pilot_collection_platform_runs WHERE platform_run_id=%s',(lease['platform_run_id'],)).fetchone()[0] == 0

def test_shared_budget_two_platforms_compete_for_last_record(env):
    from pilot.connection_versions import ConnectionOperation, ConnectionOperationStore
    registered = ConnectionOperationStore(env.db).apply(env.claims,ConnectionOperation(request_id=str(uuid4()),action='REGISTER',
        device_id=env.device,connection_id=None,expected_connection_version=0,platform='BILIBILI',account_public_id='synthetic',session_ref='vault://synthetic'))
    connection = registered['connection_id']
    with env.admin.connect() as conn:
        version = conn.execute("UPDATE pilot_platform_connections SET status='CONNECTED' WHERE connection_id=%s RETURNING connection_version",(connection,)).fetchone()[0]
    change_strategy(env,platforms=['PUBLIC_WEB','BILIBILI'],max_records=1)
    targets = [dict(platform='PUBLIC_WEB',access_mode='PUBLIC_ANONYMOUS',connection_id=None,connection_version=None),
        dict(platform='BILIBILI',access_mode='PLATFORM_ACCOUNT',connection_id=connection,connection_version=version)]
    begun = apply(env,start(env,targets=targets))
    web_lease = apply(env,operation(env,'CLAIM',begun))
    bili_lease = apply(env,operation(env,'CLAIM',begun,platform_run_id=begun['platform_runs'][1]['platform_run_id']))
    web = payload(env,begun,web_lease)
    bili = payload(env,begun,bili_lease,platform='BILIBILI')
    bili['execution'].update(access_mode='PLATFORM_ACCOUNT',connection_id=connection,connection_version=version)
    bili['records'][0].update(kind='POST',external_source_id='synthetic',public_url='https://www.bilibili.com/video/synthetic')
    second_session = verify_token_claims(issue_token(env.users[0],SECRET),SECRET)
    store = service(env)
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(submit,env,store,value,claims) for value,claims in ((web,env.claims),(bili,second_session))]
        results = []
        for future in futures:
            try: results.append(future.result(timeout=10))
            except ExecutionRuntimeError as error: assert error.code == 'budget_exhausted'
    assert len(results) == 1
    assert store.list_candidates(env.claims)['total'] == 1
    assert env.runtime.get_task(env.claims,begun['task_id'])['records_used'] == 1

def test_database_permissions_immutable_and_repeated_grant(env):
    store = service(env)
    begun,lease = claimed(env)
    submit(env,store,payload(env,begun,lease))
    with env.db.connect() as conn:
        for table in TABLES:
            assert conn.execute('SELECT row_security_active(%s::regclass)',(table,)).fetchone()[0]
            assert not conn.execute("SELECT has_table_privilege(current_user,%s,'DELETE')",(table,)).fetchone()[0]
            assert conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0
    with pytest.raises(psycopg.errors.RaiseException,match='immutable'):
        with env.admin.connect() as conn:
            conn.execute("UPDATE pilot_candidate_versions SET content='{}' WHERE tenant_id=%s",(env.tenant,))

def test_task_filter_keeps_old_observations_and_bounds_detail(env):
    store = service(env)
    change_strategy(env,max_records=110)
    begun,lease = claimed(env)
    first = submit(env,store,payload(env,begun,lease))
    later,later_lease = claimed(env)
    second = submit(env,store,payload(env,later,later_lease))
    assert first['items'][0]['candidate_id'] == second['items'][0]['candidate_id']
    assert store.list_candidates(env.claims,task_id=begun['task_id'])['total'] == 1
    assert store.list_candidates(env.claims,task_id=later['task_id'])['total'] == 1
    # Fill immutable observations through the real ingest path; no projection fixtures.
    for _ in range(99): submit(env,store,payload(env,later,later_lease))
    detail = store.get_candidate(env.claims,first['items'][0]['candidate_id'])
    assert detail['observations']['total'] == 101
    assert detail['observations']['truncated'] is True
    assert len(detail['observations']['items']) == 100

def test_database_rejects_observation_with_different_strategy_binding(env):
    store = service(env)
    begun,lease = claimed(env)
    receipt = submit(env,store,payload(env,begun,lease))
    old = receipt['items'][0]
    candidate,observation = uuid4(),uuid4()
    with pytest.raises(psycopg.errors.RaiseException,match='candidate execution binding'):
        with env.admin.connect() as conn:
            conn.execute('''INSERT INTO pilot_candidate_batches SELECT tenant_id,owner_user_id,platform_run_id,
                'tampered',task_id,run_id,platform,profile_version_id,strategy_version_id,execution_context,
                fingerprint,accepted_count,received_at,receipt FROM pilot_candidate_batches
                WHERE tenant_id=%s AND request_id=%s''',(env.tenant,receipt['request_id']))
            conn.execute('''INSERT INTO pilot_candidate_projections SELECT tenant_id,owner_user_id,source_id,%s,
                profile_version_id,'wrong-strategy',version_id,%s,revision,ambiguous,latest_observed_at
                FROM pilot_candidate_projections WHERE candidate_id=%s''',(candidate,observation,old['candidate_id']))
            conn.execute('''INSERT INTO pilot_candidate_observations SELECT tenant_id,owner_user_id,%s,%s,
                source_id,version_id,platform_run_id,'tampered',%s,observed_at,received_at,query,collector_version,normalizer_version
                FROM pilot_candidate_observations WHERE observation_id=%s''',(observation,candidate,0,old['observation_id']))

def test_parent_only_version_change_and_execution_snapshot_survive_reclaim(env):
    store = service(env)
    change_strategy(env,max_records=10)
    begun,lease = claimed(env)
    value = payload(env,begun,lease)
    value['records'][0].update(kind='COMMENT',external_comment_id='child',parent={
        'external_comment_id':'parent','body':None,'author_public_id':None,'published_at':None,'public_url':None})
    first = submit(env,store,value)
    second_value = copy.deepcopy(value)
    second_value['request_id'] = str(uuid4())
    second_value['records'][0]['parent']['body'] = 'parent context'
    second_value['records'][0]['observed_at'] = '2026-01-01T00:00:01Z'
    second = submit(env,store,second_value)
    assert first['items'][0]['version_id'] != second['items'][0]['version_id']
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_collection_platform_runs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE platform_run_id=%s",(lease['platform_run_id'],))
    newer = apply(env,operation(env,'CLAIM',begun))
    assert newer['execution_generation'] == 2
    detail = store.get_candidate(env.claims,first['items'][0]['candidate_id'])
    for observation in detail['observations']['items']:
        assert observation['execution_context'] == value['execution']
        assert observation['profile_version_id'] == value['profile_version_id']
        assert observation['strategy_version_id'] == value['strategy_version_id']


class InterposedReadDatabase:
    """Test-only second-session commit after the first candidate count statement."""
    def __init__(self, database, after_read):
        self.database, self.after_read, self.fired = database, after_read, False

    @contextmanager
    def connect(self):
        with self.database.connect() as connection:
            fixture = self
            class Connection:
                @contextmanager
                def cursor(self):
                    with connection.cursor() as cursor:
                        class Cursor:
                            def __getattr__(self, name):
                                return getattr(cursor, name)

                            def execute(self, query, params=None):
                                result = cursor.execute(query, params)
                                if not fixture.fired and 'count(*)' in query and 'pilot_candidate_' in query:
                                    fixture.fired = True
                                    fixture.after_read()
                                return result
                        yield Cursor()
            yield Connection()


def test_detail_read_snapshot_during_second_session_101st_observation(env):
    from pilot.candidate_ingestion import CandidateIngestionStore
    store = service(env)
    change_strategy(env, max_records=110)
    begun, lease = claimed(env)
    for _ in range(100):
        first = submit(env, store, payload(env, begun, lease))
    candidate_id = first['items'][0]['candidate_id']
    new_value = payload(env, begun, lease)
    new_value['records'][0].update(body='second-session-new-content', observed_at='2026-01-01T00:00:01Z')
    other = verify_token_claims(issue_token(env.users[0], SECRET), SECRET)
    assert other.revocation_key != env.claims.revocation_key
    interposed = InterposedReadDatabase(env.db, lambda: submit(env, store, new_value, other))
    detail = CandidateIngestionStore(interposed).get_candidate(env.claims, candidate_id)
    assert interposed.fired
    observations = detail['observations']
    newest = observations['items'][0]
    assert detail['candidate']['current_version']['version_id'] == newest['version_id']
    # A coherent earlier snapshot has100 old observations; a later one has101 and truncation.
    assert observations['total'] == (101 if newest['content']['body'] == 'second-session-new-content' else 100)
    assert observations['truncated'] == (observations['total'] > 100)
    assert store.get_candidate(env.claims, candidate_id)['observations']['total'] == 101


def test_list_read_snapshot_during_second_session_insert_and_empty_page_total(env):
    from pilot.candidate_ingestion import CandidateIngestionStore
    store = service(env)
    begun, lease = claimed(env)
    submit(env, store, payload(env, begun, lease))
    new_value = payload(env, begun, lease)
    new_value['records'][0]['public_url'] = 'https://example.com/second-source'
    other = verify_token_claims(issue_token(env.users[0], SECRET), SECRET)
    assert other.revocation_key != env.claims.revocation_key
    interposed = InterposedReadDatabase(env.db, lambda: submit(env, store, new_value, other))
    result = CandidateIngestionStore(interposed).list_candidates(env.claims)
    assert interposed.fired
    assert result['total'] == len(result['items'])
    assert store.list_candidates(env.claims, page=2)['total'] == 2
    assert store.list_candidates(env.claims, page=2)['items'] == []
