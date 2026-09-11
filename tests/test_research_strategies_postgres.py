"""Real isolated PostgreSQL strategy authority; synthetic source policy only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import importlib
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from pilot.auth import issue_token, verify_token_claims
from pilot.db import PilotDatabase
from pilot.execution_contract import ExecutionRuntimeError
from pilot.research_strategy_contract import StrategyStoreError
from pilot.store import PilotStore

ROOT = Path(__file__).parents[1]
MIGRATION = ROOT / 'migrations/114_v02_research_strategies.sql'
GRANT = ROOT / 'deploy/grant_research_strategies.sql'
TABLES = ('pilot_research_strategy_drafts', 'pilot_research_strategy_versions', 'pilot_research_strategy_operations')
SECRET = 'synthetic-strategy-test-key'
DESCRIPTION = '我们为食品工厂提供输送设备与定制交付。'
RECEIPT_FIELDS = {'schema_version','request_id','operation','strategy_version_id','draft_id','draft_revision',
    'profile_version_id','profile_sha256','configuration_sha256','snapshot','state','recorded_at'}


def implementation():
    assert importlib.util.find_spec('pilot.research_strategies') is not None, 'missing real research strategy store'
    assert MIGRATION.is_file(), 'missing migration 114'
    assert GRANT.is_file(), 'missing strategy least-privilege grant'
    return importlib.import_module('pilot.research_strategies')


def claims(user):
    return verify_token_claims(issue_token(user, SECRET), SECRET)


def configuration(**changes):
    return dict(schema_version='research-strategy-v1', name='设备采购', source='search',
        keywords=['输送设备 采购'], exclusions=['招聘'], links=[], mode='once', schedule=None, research=None) | changes


def prepare_body(env, **changes):
    return dict(schema_version='strategy-confirmation-v1', request_id=str(uuid4()), draft_id=str(uuid4()),
        draft_revision=1, profile_version_id=env.profile, configuration=configuration(),
        platforms=['PUBLIC_WEB'], max_records=10, max_runtime_seconds=600) | changes


def confirm_body(receipt, **changes):
    return dict(schema_version='strategy-confirmation-v1', request_id=str(uuid4()),
        strategy_version_id=receipt['strategy_version_id'], configuration_sha256=receipt['configuration_sha256'],
        human_confirmed=True) | changes


def revoke_body(receipt, **changes):
    return dict(schema_version='strategy-confirmation-v1', request_id=str(uuid4()),
        strategy_version_id=receipt['strategy_version_id']) | changes


@pytest.fixture(scope='module')
def databases():
    urls = [os.environ.get(name) for name in ('YIKE_RESEARCH_STRATEGY_TEST_DATABASE_URL',
        'YIKE_RESEARCH_STRATEGY_TEST_APP_DATABASE_URL')]
    if not all(urls):
        pytest.skip('dedicated research strategy PostgreSQL required')
    for url in urls:
        parsed = urlsplit(url)
        assert parsed.hostname == '127.0.0.1' and parsed.path == '/win_research_strategy'
    admin, app = map(PilotDatabase, urls)
    parts = urlsplit(urls[1])
    assert parts.username == 'strategy_app'
    admin.migrate()
    admin.migrate()
    with admin.connect() as conn:
        conn.execute(sql.SQL('CREATE ROLE strategy_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB PASSWORD {}').format(sql.Literal(parts.password)))
        conn.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
        conn.execute('GRANT USAGE ON SCHEMA public TO strategy_app')
        conn.execute('GRANT SELECT ON pilot_users,business_profiles,business_profile_versions TO strategy_app')
        conn.execute('GRANT UPDATE(name) ON business_profiles TO strategy_app')
        conn.execute('GRANT UPDATE(status) ON business_profile_versions TO strategy_app')
        conn.execute("SELECT set_config('yike.app_role','strategy_app',true)")
        for name in ('grant_session_revocations.sql','grant_device_credentials.sql','grant_connection_operations.sql',
                     'grant_execution_runtime.sql','grant_candidate_ingestion.sql'):
            conn.execute((ROOT / 'deploy' / name).read_text(encoding='utf-8'))
        if MIGRATION.exists():
            conn.execute(MIGRATION.read_text(encoding='utf-8'))
            conn.execute(MIGRATION.read_text(encoding='utf-8'))
        if GRANT.exists():
            conn.execute(GRANT.read_text(encoding='utf-8'))
            conn.execute(GRANT.read_text(encoding='utf-8'))
    return admin, app


@pytest.fixture
def env(databases):
    admin, db = databases
    provisioner = PilotStore(admin)
    tenants = [provisioner.provision_tenant('synthetic-strategy') for _ in range(2)]
    users = [provisioner.provision_user(tenant, f'{uuid4()}@example.invalid')
             for tenant in (tenants[0], tenants[0], tenants[1])]
    profile = provisioner.save_profile(users[0], {'description': DESCRIPTION})
    provisioner.confirm_profile(users[0], profile['version_id'])
    return SimpleNamespace(admin=admin, db=db, provisioner=provisioner, tenants=tenants, tenant=tenants[0],
        users=users, claims=claims(users[0]), profile=profile['version_id'], profile_id=profile['profile_id'])


def service(env):
    return implementation().ResearchStrategyStore(env.db)


def prepare(env, body=None, auth=None):
    return service(env).prepare(auth or env.claims, body or prepare_body(env))


def confirmed(env):
    pending = prepare(env)
    return service(env).confirm(env.claims, confirm_body(pending))


def resolve(env, receipt, auth=None):
    with env.db.connect() as conn, conn.cursor() as cursor:
        return service(env).resolve(cursor, auth or env.claims, receipt['profile_version_id'], receipt['strategy_version_id'])


def test_prepare_confirm_resolve_and_restart_receipts(env):
    req = prepare_body(env)
    draft = prepare(env, req)
    assert set(draft) == RECEIPT_FIELDS
    assert draft['state'] == 'DRAFT' and draft['operation'] == 'PREPARE'
    with pytest.raises(ExecutionRuntimeError, match='strategy_conflict'):
        resolve(env, draft)
    auth = confirm_body(draft)
    receipt = service(env).confirm(env.claims, auth)
    assert receipt['state'] == 'CONFIRMED' and receipt['operation'] == 'CONFIRM'
    assert service(env).get_receipt(env.claims, auth['request_id']) == receipt
    assert prepare(env, req) == draft
    value = resolve(env, receipt)
    from pilot.execution_runtime import ConfirmedExecutionStrategy
    assert isinstance(value, ConfirmedExecutionStrategy)
    assert value.configuration_sha256 == receipt['configuration_sha256']
    assert value.platforms == ('PUBLIC_WEB',)
    view = service(env).get_strategy(env.claims, draft['strategy_version_id'])
    assert set(view) == (RECEIPT_FIELDS - {'request_id','operation','recorded_at'}) | {'created_at','confirmed_at','revoked_at','is_current','profile_current'}
    assert view['state'] == 'CONFIRMED' and view['is_current'] and view['profile_current']


def test_platform_queries_survive_prepare_confirm_resolve_and_change_digest(env):
    queries = {'version': 'platform-queries-v1', 'items': [
        {'platform': 'XIAOHONGSHU', 'keywords': ['找搭建团队']},
        {'platform': 'BILIBILI', 'keywords': ['展台设计报价']},
    ]}
    request = prepare_body(env, configuration=configuration(platformQueries=queries),
                           platforms=['XIAOHONGSHU', 'BILIBILI'])
    pending = prepare(env, request)
    receipt = service(env).confirm(env.claims, confirm_body(pending))
    assert receipt['snapshot']['configuration']['platformQueries'] == queries
    assert resolve(env, receipt).configuration['platformQueries'] == queries

    changed_queries = deepcopy(queries)
    changed_queries['items'][1]['keywords'] = ['展台设计预算']
    newer = prepare(env, request | {
        'request_id': str(uuid4()), 'draft_revision': 2,
        'configuration': configuration(platformQueries=changed_queries),
    })
    assert newer['configuration_sha256'] != receipt['configuration_sha256']
    confirmed_newer = service(env).confirm(env.claims, confirm_body(newer))
    assert resolve(env, confirmed_newer).configuration['platformQueries'] == changed_queries


@pytest.mark.parametrize('change', ['body','operation'])
def test_same_request_conflicts_with_changed_body_or_operation(env, change):
    req = prepare_body(env)
    receipt = prepare(env, req)
    with pytest.raises(StrategyStoreError, match='request_conflict'):
        if change == 'body':
            prepare(env, req | {'draft_revision': 2})
        else:
            service(env).revoke(env.claims, revoke_body(receipt, request_id=req['request_id']))


@pytest.mark.parametrize('change', ['profile','configuration','platform_order','max_records','max_runtime'])
def test_same_revision_full_binding_conflict(env, change):
    req = prepare_body(env, platforms=['PUBLIC_WEB','BILIBILI'])
    receipt = prepare(env, req)
    another = req | {'request_id': str(uuid4())}
    assert prepare(env, another)['strategy_version_id'] == receipt['strategy_version_id']
    if change == 'profile':
        new = env.provisioner.save_profile(env.users[0], {'description':'另一份已确认画像'})
        env.provisioner.confirm_profile(env.users[0],new['version_id'])
        another['profile_version_id'] = new['version_id']
    elif change == 'configuration': another['configuration'] = configuration(name='另一个名称')
    elif change == 'platform_order': another['platforms'] = ['BILIBILI','PUBLIC_WEB']
    elif change == 'max_records': another['max_records'] = 11
    else: another['max_runtime_seconds'] = 601
    with pytest.raises(StrategyStoreError, match='draft_conflict'):
        prepare(env, another | {'request_id': str(uuid4())})


def test_higher_revision_invalidates_old_confirmations_without_changing_receipts(env):
    req = prepare_body(env)
    draft = prepare(env, req)
    auth = confirm_body(draft)
    old = service(env).confirm(env.claims, auth)
    newer = prepare(env, req | {'request_id':str(uuid4()), 'draft_revision':2})
    assert newer['strategy_version_id'] != old['strategy_version_id']
    for receipt in (old, newer):
        with pytest.raises(ExecutionRuntimeError, match='strategy_conflict'): resolve(env, receipt)
    with pytest.raises(StrategyStoreError, match='strategy_conflict'):
        service(env).confirm(env.claims, confirm_body(old))
    with pytest.raises(StrategyStoreError, match='draft_conflict'):
        prepare(env, req | {'request_id':str(uuid4())})
    assert service(env).confirm(env.claims, auth) == old
    assert service(env).get_receipt(env.claims, auth['request_id']) == old
    assert not service(env).get_strategy(env.claims, old['strategy_version_id'])['is_current']
    service(env).confirm(env.claims, confirm_body(newer))
    resolve(env, newer)


@pytest.mark.parametrize('change', ['status','payload','digest'])
def test_profile_changes_block_confirm_and_resolve_but_allow_revoke(env, change):
    pending = prepare(env)
    current = confirmed(env)
    with env.admin.connect() as conn:
        if change == 'status': conn.execute("UPDATE business_profile_versions SET status='REVOKED' WHERE profile_version_id=%s",(env.profile,))
        elif change == 'payload': conn.execute('UPDATE business_profile_versions SET payload=%s::jsonb WHERE profile_version_id=%s',(json.dumps({'description':'tampered'}),env.profile))
        else: conn.execute("UPDATE business_profile_versions SET content_sha256=%s WHERE profile_version_id=%s",('0'*64,env.profile))
    with pytest.raises(StrategyStoreError, match='profile_unavailable|strategy_conflict'):
        service(env).confirm(env.claims, confirm_body(pending))
    with pytest.raises(ExecutionRuntimeError, match='strategy_conflict'): resolve(env,current)
    assert not service(env).get_strategy(env.claims,current['strategy_version_id'])['profile_current']
    assert service(env).revoke(env.claims,revoke_body(current))['state'] == 'REVOKED'


def test_revoke_is_durable_cannot_restore_and_replays_prior_success(env):
    current = confirmed(env)
    request = revoke_body(current)
    revoked = service(env).revoke(env.claims,request)
    assert revoked['state'] == 'REVOKED'
    assert service(env).revoke(env.claims,request) == revoked
    assert service(env).revoke(env.claims,revoke_body(current))['state'] == 'REVOKED'
    assert service(env).get_receipt(env.claims,current['request_id']) == current
    with pytest.raises(StrategyStoreError, match='strategy_conflict'): service(env).confirm(env.claims,confirm_body(current))
    with pytest.raises(ExecutionRuntimeError, match='strategy_conflict'): resolve(env,current)


@pytest.mark.parametrize('index',[1,2])
def test_other_owner_cannot_read_or_mutate_strategy(env,index):
    current = confirmed(env)
    stranger = claims(env.users[index])
    for method, argument in [('get_receipt',current['request_id']),('get_strategy',current['strategy_version_id']),
                             ('confirm',confirm_body(current)),('revoke',revoke_body(current))]:
        with pytest.raises(StrategyStoreError, match='request_not_found|strategy_not_found'):
            getattr(service(env),method)(stranger,argument)
    with pytest.raises(ExecutionRuntimeError,match='strategy_conflict'): resolve(env,current,stranger)
    if index == 1:
        own = prepare(env,auth=stranger)
        assert own['profile_version_id'] == current['profile_version_id']
    else:
        with pytest.raises(StrategyStoreError,match='profile_unavailable'): prepare(env,auth=stranger)


def test_concurrent_prepare_and_confirm_produce_one_version_and_original_receipt(env):
    req = prepare_body(env)
    sessions = [claims(env.users[0]) for _ in range(4)]
    with ThreadPoolExecutor(4) as pool:
        drafts = list(pool.map(lambda auth: prepare(env,req,auth),sessions))
    assert all(item == drafts[0] for item in drafts)
    confirm = confirm_body(drafts[0])
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda auth: service(env).confirm(auth,confirm),sessions))
    assert all(item == results[0] for item in results)
    with env.admin.connect() as conn:
        assert conn.execute('SELECT count(*) FROM pilot_research_strategy_versions WHERE tenant_id=%s',(env.tenant,)).fetchone()[0] == 1
        assert conn.execute('SELECT count(*) FROM pilot_research_strategy_operations WHERE tenant_id=%s',(env.tenant,)).fetchone()[0] == 2


def test_bad_hash_and_forged_model_never_confirm(env):
    pending = prepare(env)
    with pytest.raises(StrategyStoreError,match='strategy_conflict'):
        service(env).confirm(env.claims,confirm_body(pending,configuration_sha256='0'*64))
    contract = importlib.import_module('pilot.research_strategy_contract')
    forged = contract.ConfirmStrategyRequest.model_validate(confirm_body(pending)).model_copy(update={'human_confirmed':1})
    with pytest.raises(StrategyStoreError,match='invalid_request'): service(env).confirm(env.claims,forged)
    forged = contract.PrepareStrategyRequest.model_validate(prepare_body(env)).model_copy(update={'draft_revision':True})
    with pytest.raises(StrategyStoreError,match='invalid_request'): prepare(env,forged)


@pytest.mark.parametrize('bad',[None,{},'token','unicode','expired','revoked'])
def test_bad_session_is_safe_and_never_persists(env,bad):
    auth = bad
    if bad == 'unicode': auth = replace(env.claims,user_id='\ud800')
    if bad == 'expired': auth = replace(env.claims,expires_at=1)
    if bad == 'revoked':
        service(env).sessions.revoke([env.claims])
        auth = env.claims
    with pytest.raises(StrategyStoreError,match='invalid_session') as caught:
        service(env).prepare(auth,prepare_body(env))
    assert caught.value.__context__ is None


def wait_for_profile_lock(admin):
    deadline = time.monotonic()+5
    while time.monotonic()<deadline:
        with admin.connect() as conn:
            if conn.execute("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE '%business_profiles%FOR UPDATE%')").fetchone()[0]: return
        time.sleep(.02)
    pytest.fail('profile lock wait not observed')


def test_confirm_rechecks_expiry_after_profile_lock_wait(env):
    pending=prepare(env)
    auth=replace(env.claims,expires_at=int(time.time())+2)
    with ThreadPoolExecutor(1) as pool:
        with env.admin.connect() as conn:
            conn.execute('SELECT 1 FROM business_profiles WHERE profile_id=%s FOR UPDATE',(env.profile_id,))
            future=pool.submit(service(env).confirm,auth,confirm_body(pending))
            wait_for_profile_lock(env.admin)
            while time.time()<=auth.expires_at: time.sleep(.04)
        with pytest.raises(StrategyStoreError,match='invalid_session'): future.result(timeout=5)
    assert service(env).get_strategy(env.claims,pending['strategy_version_id'])['state']=='DRAFT'


def test_resolver_uses_callers_transaction_and_blocks_revision_until_rollback(env):
    current=confirmed(env)
    next_request=prepare_body(env,draft_id=current['draft_id'],draft_revision=2)
    with ThreadPoolExecutor(1) as pool:
        with env.db.connect() as conn, conn.cursor() as cursor:
            service(env).resolve(cursor,env.claims,env.profile,current['strategy_version_id'])
            cursor.execute("SELECT set_config('yike.strategy_rollback_test','in_transaction',true)")
            future=pool.submit(prepare,env,next_request,claims(env.users[0]))
            wait_for_profile_lock(env.admin)
            assert not future.done()
            conn.rollback()
            assert cursor.execute("SELECT current_setting('yike.strategy_rollback_test',true)").fetchone()[0]==''
        assert future.result(timeout=5)['draft_revision']==2
    with env.db.connect() as conn:
        conn.autocommit=True
        with pytest.raises(ExecutionRuntimeError,match='strategy_conflict'):
            service(env).resolve(conn.cursor(),env.claims,env.profile,current['strategy_version_id'])


def test_rls_fk_immutability_and_repeatable_minimal_grants(env):
    current=confirmed(env)
    with env.db.connect() as conn:
        for table in TABLES:
            assert conn.execute('SELECT row_security_active(%s::regclass)',(table,)).fetchone()[0]
            assert conn.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table))).fetchone()[0]==0
        conn.execute("SELECT set_config('yike.tenant_id',%s,true),set_config('yike.user_id',%s,true)",(env.tenant,env.users[1]))
        for table in TABLES:
            assert conn.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table))).fetchone()[0]==0
        conn.execute("SELECT set_config('yike.user_id',%s,true)",(env.users[0],))
        for statement in ("UPDATE pilot_research_strategy_versions SET snapshot='{}'::jsonb", "UPDATE pilot_research_strategy_versions SET state='DRAFT'",
            "UPDATE pilot_research_strategy_versions SET owner_user_id='other'", "UPDATE pilot_research_strategy_drafts SET current_revision=current_revision-1"):
            with pytest.raises(psycopg.Error),conn.transaction(): conn.execute(statement)
        for table in TABLES:
            for operation in ('DELETE FROM','TRUNCATE'):
                with pytest.raises(psycopg.errors.InsufficientPrivilege),conn.transaction():
                    conn.execute(sql.SQL('{} {}').format(sql.SQL(operation),sql.Identifier(table)))
        with pytest.raises(psycopg.errors.InsufficientPrivilege),conn.transaction():
            conn.execute("UPDATE pilot_research_strategy_operations SET receipt='{}'::jsonb")
    with env.admin.connect() as conn:
        conn.execute(MIGRATION.read_text(encoding='utf-8'))
        conn.execute("SELECT set_config('yike.app_role','strategy_app',true)")
        conn.execute(GRANT.read_text(encoding='utf-8'))
    assert service(env).get_receipt(env.claims,current['request_id'])==current


@pytest.mark.parametrize('privilege',['public_column','member_column','member_delete','owner','privileged'])
def test_grant_rejects_reachable_excess_privileges(env,privilege):
    implementation()
    with env.admin.connect() as conn:
        with conn.transaction(force_rollback=True):
            if privilege=='public_column': conn.execute('GRANT UPDATE(receipt) ON pilot_research_strategy_operations TO PUBLIC')
            else:
                role='strategy_parent_'+uuid4().hex
                conn.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
                conn.execute(sql.SQL('GRANT {} TO strategy_app WITH INHERIT FALSE').format(sql.Identifier(role)))
                if privilege=='member_column': conn.execute(sql.SQL('GRANT UPDATE(receipt) ON pilot_research_strategy_operations TO {}').format(sql.Identifier(role)))
                if privilege=='member_delete': conn.execute(sql.SQL('GRANT DELETE ON pilot_research_strategy_versions TO {}').format(sql.Identifier(role)))
                if privilege=='owner': conn.execute(sql.SQL('ALTER TABLE pilot_research_strategy_versions OWNER TO {}').format(sql.Identifier(role)))
                if privilege=='privileged': conn.execute(sql.SQL('ALTER ROLE {} BYPASSRLS').format(sql.Identifier(role)))
            conn.execute("SELECT set_config('yike.app_role','strategy_app',true)")
            with pytest.raises(psycopg.errors.RaiseException),conn.transaction(): conn.execute(GRANT.read_text(encoding='utf-8'))


def test_real_ed25519_execution_signed_ingestion_revoke_and_cancel(env):
    from nacl.signing import SigningKey
    from pilot.execution_runtime import ExecutionRuntime
    from pilot.device_credentials import DeviceCredentialStore
    from tests.test_device_credentials_postgres import bind
    from tests.test_execution_runtime_postgres import claimed,apply,operation
    from tests.test_candidate_ingestion_postgres import payload,submit
    from pilot.candidate_ingestion import CandidateIngestionStore
    current=confirmed(env)
    env.snapshot=current['snapshot']
    env.store=PilotStore(env.db)
    env.device=env.store.register_device(env.users[0],'synthetic-strategy-device')['device_id']
    env.key=SigningKey.generate()
    bind(SimpleNamespace(service=DeviceCredentialStore(env.db),claims=env.claims,device=env.device),env.key)
    env.runtime=ExecutionRuntime(env.db,strategy_resolver=service(env).resolve,
        capability_check=lambda platform,access,config: platform=='PUBLIC_WEB' and access=='PUBLIC_ANONYMOUS')
    begun,lease=claimed(env)
    ingestion=CandidateIngestionStore(env.db,env.runtime)
    first=submit(env,ingestion,payload(env,begun,lease))
    assert first['accepted_count']==1
    service(env).revoke(env.claims,revoke_body(current))
    with pytest.raises(ExecutionRuntimeError,match='strategy_conflict'):
        submit(env,ingestion,payload(env,begun,lease))
    assert env.runtime.get_task(env.claims,begun['task_id'])['records_used']==1
    assert apply(env,operation(env,'CANCEL',begun))['status']=='CANCELLING'


def test_same_revision_uses_canonical_hash_not_python_numeric_equality(env):
    schedule=dict(kind='interval',times=[],interval=1,start='09:00',end='18:00',timezone='UTC')
    req=prepare_body(env,configuration=configuration(mode='monitor',schedule=schedule))
    first=prepare(env,req)
    changed=req | {'request_id':str(uuid4()),'configuration':configuration(mode='monitor',schedule=schedule | {'interval':1.0})}
    from pilot.research_strategy_contract import strategy_snapshot,configuration_digest
    candidate=strategy_snapshot(env.profile,first['strategy_version_id'],changed['configuration'],changed['platforms'],10,600)
    assert configuration_digest(candidate)!=first['configuration_sha256']
    with pytest.raises(StrategyStoreError,match='draft_conflict'): prepare(env,changed)


def test_resolver_mismatched_profile_never_locks_another_profile(env):
    current=confirmed(env)
    with env.db.connect() as conn,conn.cursor() as cursor:
        with pytest.raises(ExecutionRuntimeError,match='strategy_conflict'):
            service(env).resolve(cursor,env.claims,str(uuid4()),current['strategy_version_id'])
        rows=cursor.execute("SELECT relation::regclass::text FROM pg_locks WHERE pid=pg_backend_pid() "
            "AND mode='RowShareLock' AND relation IN ('business_profiles'::regclass,'business_profile_versions'::regclass)").fetchall()
        assert rows==[], 'wrong binding must not acquire another profile row lock'


def test_database_insert_error_rolls_back_strategy_and_has_no_private_exception_context(env):
    implementation()
    marker='postgresql://synthetic:private@invalid/secret'
    with env.admin.connect() as conn:
        conn.execute(sql.SQL("CREATE FUNCTION strategy_test_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION {}; END $$").format(sql.Literal(marker)))
        conn.execute('CREATE TRIGGER strategy_test_failure BEFORE INSERT ON pilot_research_strategy_operations FOR EACH ROW EXECUTE FUNCTION strategy_test_failure()')
    try:
        with pytest.raises(StrategyStoreError,match='strategy_store_unavailable') as caught: prepare(env)
        assert caught.value.status==503
        assert caught.value.__context__ is None and caught.value.__cause__ is None
        assert marker not in str(caught.value)
        with env.admin.connect() as conn:
            for table in TABLES:
                assert conn.execute(sql.SQL('SELECT count(*) FROM {} WHERE tenant_id=%s').format(sql.Identifier(table)),(env.tenant,)).fetchone()[0]==0
    finally:
        with env.admin.connect() as conn:
            conn.execute('DROP TRIGGER strategy_test_failure ON pilot_research_strategy_operations')
            conn.execute('DROP FUNCTION strategy_test_failure()')


@pytest.mark.parametrize('field',['owner_user_id','draft_id','profile_version_id'])
def test_versions_have_real_composite_foreign_keys(env,field):
    current=prepare(env)
    with env.admin.connect() as conn:
        row=conn.execute('SELECT tenant_id,owner_user_id,draft_id,profile_version_id,profile_sha256,snapshot,configuration_sha256 '
            'FROM pilot_research_strategy_versions WHERE strategy_version_id=%s',(current['strategy_version_id'],)).fetchone()
        data=dict(zip(('tenant_id','owner_user_id','draft_id','profile_version_id','profile_sha256','snapshot','configuration_sha256'),row))
        data[field]=str(uuid4())
        with pytest.raises(psycopg.errors.ForeignKeyViolation),conn.transaction():
            conn.execute('INSERT INTO pilot_research_strategy_versions(tenant_id,owner_user_id,draft_id,profile_version_id,profile_sha256,snapshot,'
                'configuration_sha256,strategy_version_id,draft_revision) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,2)',
                (data['tenant_id'],data['owner_user_id'],data['draft_id'],data['profile_version_id'],data['profile_sha256'],
                 json.dumps(data['snapshot']),data['configuration_sha256'],str(uuid4())))


@pytest.mark.parametrize('change',['snapshot','configuration_digest'])
def test_resolver_rechecks_stored_snapshot_after_corruption(env,change):
    current=confirmed(env)
    with env.admin.connect() as conn:
        conn.execute('ALTER TABLE pilot_research_strategy_versions DISABLE TRIGGER pilot_research_strategy_version_guard')
        if change=='snapshot':
            snapshot=current['snapshot'] | {'max_records':100}
            conn.execute('UPDATE pilot_research_strategy_versions SET snapshot=%s::jsonb WHERE strategy_version_id=%s',
                (json.dumps(snapshot),current['strategy_version_id']))
        else:
            conn.execute('UPDATE pilot_research_strategy_versions SET configuration_sha256=%s WHERE strategy_version_id=%s',
                ('0'*64,current['strategy_version_id']))
        conn.execute('ALTER TABLE pilot_research_strategy_versions ENABLE TRIGGER pilot_research_strategy_version_guard')
    with pytest.raises(ExecutionRuntimeError,match='strategy_conflict'): resolve(env,current)


def client_for(env):
    from fastapi.testclient import TestClient
    from pilot.web import build_app
    auth_store=PilotStore(env.db)
    app=build_app(auth_store,auth_secret=SECRET,research_strategies=service(env))
    return TestClient(app,base_url='https://pilot.example')


def headers(user):
    return {'Authorization':'Bearer '+issue_token(user,SECRET),'Origin':'https://pilot.example'}


def test_real_http_confirm_current_receipts_revoke_restart_and_session_logout(env):
    auth=headers(env.users[0])
    with client_for(env) as client:
        prepared=client.post('/api/ui/research-strategies/prepare',json=prepare_body(env),headers=auth)
        assert prepared.status_code==200 and prepared.headers['cache-control']=='no-store'
        draft=prepared.json()
        failed=client.post('/api/ui/research-strategies/confirm',json=confirm_body(draft,configuration_sha256='0'*64),headers=auth)
        assert failed.status_code==409
        assert service(env).get_strategy(env.claims,draft['strategy_version_id'])['state']=='DRAFT'
        response=client.post('/api/ui/research-strategies/confirm',json=confirm_body(draft),headers=auth)
        assert response.status_code==200
        receipt=response.json()
        assert client.get('/api/ui/research-strategy-operations/'+receipt['request_id'],headers=auth).json()==receipt
        assert client.get('/api/ui/research-strategies/'+receipt['strategy_version_id'],headers=auth).json()['state']=='CONFIRMED'
        revoked=client.post('/api/ui/research-strategies/revoke',json=revoke_body(receipt),headers=auth)
        assert revoked.status_code==200 and revoked.json()['state']=='REVOKED'
        assert service(env).get_receipt(env.claims,receipt['request_id'])==receipt
        assert client.delete('/api/ui/session',headers=auth).status_code in (200,204)
        stale=client.get('/api/ui/research-strategy-operations/'+receipt['request_id'],headers=auth)
        assert stale.status_code==401 and stale.json()['detail']['code']=='invalid_session'


@pytest.mark.parametrize('index',[1,2])
def test_real_http_owner_and_origin_fences(env,index):
    current=confirmed(env)
    with client_for(env) as client:
        stranger=headers(env.users[index])
        assert client.get('/api/ui/research-strategy-operations/'+current['request_id'],headers=stranger).status_code==404
        assert client.get('/api/ui/research-strategies/'+current['strategy_version_id'],headers=stranger).status_code==404
        assert client.post('/api/ui/research-strategies/revoke',json=revoke_body(current),headers=stranger).status_code==404
        assert client.post('/api/ui/research-strategies/prepare',json=prepare_body(env),
            headers=headers(env.users[0]) | {'Origin':'https://untrusted.example'}).status_code==403
    assert service(env).get_strategy(env.claims,current['strategy_version_id'])['state']=='CONFIRMED'


def test_distinct_confirmation_requests_do_not_reset_confirmation_time(env):
    pending=prepare(env)
    sessions=[claims(env.users[0]) for _ in range(4)]
    with ThreadPoolExecutor(4) as pool:
        receipts=list(pool.map(lambda auth:service(env).confirm(auth,confirm_body(pending)),sessions))
    assert len({row['request_id'] for row in receipts})==4
    assert len({row['strategy_version_id'] for row in receipts})==1
    initial=service(env).get_strategy(env.claims,pending['strategy_version_id'])['confirmed_at']
    service(env).confirm(env.claims,confirm_body(pending))
    assert service(env).get_strategy(env.claims,pending['strategy_version_id'])['confirmed_at']==initial


@pytest.mark.parametrize('field',['tenant_id','owner_user_id'])
def test_restricted_insert_rls_rejects_forged_owner_or_tenant(env,field):
    implementation()
    values={'tenant_id':env.tenant,'owner_user_id':env.users[0]}
    values[field]=env.tenants[1] if field=='tenant_id' else env.users[1]
    with env.db.connect() as conn:
        conn.execute("SELECT set_config('yike.tenant_id',%s,true),set_config('yike.user_id',%s,true)",(env.tenant,env.users[0]))
        with pytest.raises(psycopg.errors.InsufficientPrivilege),conn.transaction():
            conn.execute('INSERT INTO pilot_research_strategy_drafts(tenant_id,owner_user_id,draft_id,current_revision,current_version_id) '
                'VALUES (%s,%s,%s,1,%s)',(values['tenant_id'],values['owner_user_id'],str(uuid4()),str(uuid4())))


def test_resolver_rechecks_expiry_after_profile_lock_wait(env):
    current=confirmed(env)
    auth=replace(env.claims,expires_at=int(time.time())+2)
    with ThreadPoolExecutor(1) as pool:
        with env.admin.connect() as conn:
            conn.execute('SELECT 1 FROM business_profiles WHERE profile_id=%s FOR UPDATE',(env.profile_id,))
            future=pool.submit(resolve,env,current,auth)
            wait_for_profile_lock(env.admin)
            while time.time()<=auth.expires_at: time.sleep(.04)
        with pytest.raises(ExecutionRuntimeError,match='invalid_session') as caught:
            future.result(timeout=5)
        assert caught.value.status==401 and caught.value.__context__ is None
    assert service(env).get_strategy(env.claims,current['strategy_version_id'])['state']=='CONFIRMED'


def test_confirm_waits_for_profile_confirmation_and_rejects_replaced_profile(env):
    pending=prepare(env)
    next_profile=env.provisioner.save_profile(env.users[0],{'description':'新的画像原文'})
    with ThreadPoolExecutor(1) as pool:
        with env.admin.connect() as conn:
            conn.execute('SELECT 1 FROM business_profiles WHERE profile_id=%s FOR UPDATE',(env.profile_id,))
            future=pool.submit(service(env).confirm,env.claims,confirm_body(pending))
            wait_for_profile_lock(env.admin)
            conn.execute("UPDATE business_profile_versions SET status='REVOKED' WHERE profile_version_id=%s",(env.profile,))
            conn.execute("UPDATE business_profile_versions SET status='CONFIRMED' WHERE profile_version_id=%s",(next_profile['version_id'],))
        with pytest.raises(StrategyStoreError,match='profile_unavailable'): future.result(timeout=5)
    assert service(env).get_strategy(env.claims,pending['strategy_version_id'])['state']=='DRAFT'


def test_real_node_client_strategy_roundtrip(env):
    """Real renderer -> fixed main transport -> loopback HTTP -> restricted PG.

    Explicit test-only HTTP does not prove production TLS, platforms or sending.
    No request/receipt is stubbed and synthetic credentials never reach argv/logs.
    """
    import shutil
    import socket
    import subprocess
    import threading
    import uvicorn
    from pilot.web import build_app

    node = os.environ.get('YIKE_STRATEGY_NODE_BINARY') or shutil.which('node')
    if not node:
        pytest.skip('Node 24 required for actual desktop client consumer')
    version = subprocess.run([node, '--version'], capture_output=True, text=True, timeout=10, check=True)
    assert version.stdout.strip().startswith('v24.'), 'Node 24 required'
    auth_store = PilotStore(env.db)
    # Consume the shared composition, including its real identity/Origin checks.
    # The existing dev-only HTTP option is restricted to this loopback listener.
    app = build_app(auth_store, auth_secret=SECRET, dev_login=True, research_strategies=service(env))
    paths = [route.path for route in app.routes
             if route.path.startswith(('/api/ui/research-strategies/', '/api/ui/research-strategy-operations/'))]
    assert len(paths) == len(set(paths)) == 5, 'strategy routes must not be shadowed by a test router'
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(64)
        server = uvicorn.Server(uvicorn.Config(app, log_level='critical', access_log=False, lifespan='off'))
        thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(.02)
            assert server.started and thread.is_alive(), 'isolated HTTP fixture failed to start'
            child_env = os.environ.copy()
            # The Node consumer receives no database credentials.
            for key in list(child_env):
                if 'DATABASE' in key.upper() or key.upper().startswith('POSTGRES_'):
                    child_env.pop(key)
            child_env.update(YIKE_STRATEGY_LIVE_BASE=f'http://127.0.0.1:{listener.getsockname()[1]}',
                YIKE_STRATEGY_LIVE_TOKEN=issue_token(env.users[0], SECRET), YIKE_STRATEGY_LIVE_PROFILE=env.profile)
            result = subprocess.run([node, 'node_modules/vitest/vitest.mjs', 'run',
                'tests/integration/research-strategy-live.test.ts'], cwd=ROOT / 'desktop', env=child_env,
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=50)
            # Keep diagnostics while redacting the synthetic credential and DB URLs.
            output = result.stdout + result.stderr
            for secret in (child_env['YIKE_STRATEGY_LIVE_TOKEN'],
                           os.environ.get('YIKE_RESEARCH_STRATEGY_TEST_DATABASE_URL'),
                           os.environ.get('YIKE_RESEARCH_STRATEGY_TEST_APP_DATABASE_URL')):
                if secret:
                    output = output.replace(secret, '[redacted]')
            assert result.returncode == 0, output
            assert '1 passed' in output and '1 skipped' not in output, output
            print('actual Node 24 renderer/fixed-IPC/HTTP/PG: 1 passed')
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive(), 'isolated HTTP fixture did not stop'
