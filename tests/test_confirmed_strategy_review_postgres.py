"""Actual persisted strategy + signed raw + restricted PG; synthetic source/model only."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from pilot.auth import issue_token, verify_token_claims
from pilot.candidate_review import CandidateReviewStore
from pilot.candidate_ingestion import CandidateIngestionError
from pilot.execution_contract import ExecutionRuntimeError
from pilot.execution_runtime import ExecutionRuntime, ConfirmedExecutionStrategy
from pilot.research_strategies import ResearchStrategyStore
from pilot.store import PilotStore
from tests.test_candidate_review_postgres import (
    execution_databases, execution_env, raw_databases, raw_env, databases, env,
    BoundaryModel, seed, review_payload, verification_payload, assessment, DESCRIPTION,
)
from tests.test_execution_runtime_postgres import SECRET, apply, start, digest
from tests.test_research_strategies_postgres import prepare_body, confirm_body, revoke_body

ROOT = Path(__file__).parents[1]


@pytest.fixture
def real_strategy_env(env):
    with env.db.connect() as conn:
        role = conn.execute('SELECT current_user').fetchone()[0]
    with env.admin.connect() as conn:
        conn.execute((ROOT / 'migrations/114_v02_research_strategies.sql').read_text())
        conn.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
        conn.execute((ROOT / 'deploy/grant_research_strategies.sql').read_text())
    provisioner = PilotStore(env.admin)
    profile = provisioner.save_profile(env.claims.user_id, {'description': DESCRIPTION})
    provisioner.confirm_profile(env.claims.user_id, profile['version_id'])
    env.profile = profile['version_id']
    with env.admin.connect() as conn:
        env.profile_number = conn.execute('SELECT version FROM business_profile_versions WHERE profile_version_id=%s', (env.profile,)).fetchone()[0]
    env.strategies = ResearchStrategyStore(env.db)
    try:
        env.prepare_request = prepare_body(env)
        pending = env.strategies.prepare(env.claims, env.prepare_request)
        env.confirm_request = confirm_body(pending)
        env.confirmed = env.strategies.confirm(env.claims, env.confirm_request)
        env.snapshot = env.confirmed['snapshot']
        env.resolver = env.strategies.resolve
        env.runtime = ExecutionRuntime(env.db, strategy_resolver=env.resolver,
            capability_check=lambda *args: True)  # Synthetic source policy only.
        yield env
    finally:
        with env.admin.connect() as conn:
            conn.execute('DELETE FROM pilot_research_reservations WHERE tenant_id=ANY(%s)', (env.tenants,))
            for table in ('pilot_research_strategy_operations','pilot_research_strategy_versions','pilot_research_strategy_drafts'):
                conn.execute(f'DELETE FROM {table} WHERE tenant_id=ANY(%s)', (env.tenants,))


class BoundedDatabase:
    def __init__(self, database):
        self.database = database

    @contextmanager
    def connect(self):
        with self.database.connect() as connection:
            connection.execute("SET LOCAL lock_timeout='300ms'")
            connection.execute("SET LOCAL statement_timeout='2s'")
            yield connection


def real_review(env):
    return CandidateReviewStore(BoundedDatabase(env.db), model=BoundaryModel(),
        strategy_resolver=env.strategies.resolve, strategy_snapshot_reader=env.strategies.read_snapshot)


def prepare_review(env, service=None, **record_changes):
    service = service or real_review(env)
    binding = seed(env, **record_changes) | {'profileVersion': env.profile_number}
    assessed = service.review(env.claims, review_payload(binding))
    check = service.verify_source(env.claims, verification_payload(binding))
    decision = review_payload(binding, 'INCLUDE', assessmentId=assessed['assessment']['id'],
        sourceVerificationId=check['id'], humanConfirmed=True, evidence=assessment()['evidence'], reason='')
    return service, binding, assessed, check, decision


@contextmanager
def snapshot_cursor(env, *, user=None, tenant=None, scope=True, isolation='REPEATABLE READ', readonly=True):
    with env.db.connect() as conn, conn.cursor() as cursor:
        cursor.execute('SET TRANSACTION ISOLATION LEVEL '+isolation+(' READ ONLY' if readonly else ''))
        if scope:
            cursor.execute("SELECT set_config('yike.user_id',%s,true),set_config('yike.tenant_id',%s,true)",
                (user or env.claims.user_id, tenant or env.tenant))
        yield cursor


def read(env, cursor, claims=None, profile=None, strategy=None):
    return env.strategies.read_snapshot(cursor, claims or env.claims,
        profile or env.profile, strategy or env.snapshot['strategy_version_id'])


def test_real_strategy_can_project_current_candidate_without_waiting_on_own_session(real_strategy_env):
    env = real_strategy_env
    service, binding, assessed, check, decision = prepare_review(env)
    included = service.review(env.claims, decision)
    assert included['receipt']['outcome'] == 'IMPORTED'
    for options in ({'status': 'IMPORTED'}, {'ids': [binding['candidateId']],
            'review_request_id': decision['requestId'], 'page_size': 1}):
        page = service.list_candidates(env.claims, **options)
        assert page['total'] == 1
        assert page['items'][0]['currentBindingValid'] is True
        assert page['items'][0]['assessment']['id'] == assessed['assessment']['id']


def test_reader_uses_only_readonly_caller_snapshot_and_plain_json(real_strategy_env, monkeypatch):
    env = real_strategy_env
    def forbidden(*args, **kwargs):
        pytest.fail('reader must not authenticate, lock, or open a connection')
    with snapshot_cursor(env) as cursor:
        for name in ('_active', '_profile', '_draft', '_locked_version'):
            monkeypatch.setattr(env.strategies, name, forbidden)
        monkeypatch.setattr(env.strategies.database, 'connect', forbidden)
        result = read(env, cursor)
        assert type(result) is dict and not isinstance(result, ConfirmedExecutionStrategy)
        assert result == env.snapshot | {'configuration_sha256': env.confirmed['configuration_sha256']}
        result['configuration']['keywords'].append('local mutation')
        assert read(env, cursor)['configuration'] == env.snapshot['configuration']
        for sql in ('SELECT * FROM business_profile_versions FOR UPDATE',
                    "UPDATE business_profiles SET name='not allowed'"):
            with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
                with cursor.connection.transaction():
                    cursor.execute(sql)


@pytest.mark.parametrize('case', ['missing_scope','wrong_scope_user','wrong_owner','wrong_tenant',
    'wrong_profile','bad_profile_id','bad_strategy_id','read_committed','read_write','autocommit','bad_claims'])
def test_reader_rejects_invalid_scope_and_bindings(real_strategy_env, case):
    env = real_strategy_env
    options = {'scope': False} if case == 'missing_scope' else {}
    if case == 'wrong_scope_user': options['user'] = env.users[1]
    if case == 'wrong_owner': options['user'] = env.users[1]
    if case == 'wrong_tenant': options['tenant'] = env.tenants[1]
    if case == 'read_committed': options['isolation'] = 'READ COMMITTED'
    if case == 'read_write': options['readonly'] = False
    claims = verify_token_claims(issue_token(env.users[1], SECRET), SECRET) if case == 'wrong_owner' else env.claims
    if case == 'bad_claims': claims = replace(claims, expires_at=float(claims.expires_at))
    expected = 'invalid_session' if case in ('missing_scope','wrong_scope_user','bad_claims') else 'strategy_conflict'
    with pytest.raises(ExecutionRuntimeError) as error:
        with snapshot_cursor(env, **options) as cursor:
            if case == 'autocommit':
                cursor.connection.rollback()
                cursor.connection.autocommit = True
            read(env, cursor, claims=claims,
                profile=str(uuid4()) if case == 'wrong_profile' else 'bad' if case == 'bad_profile_id' else None,
                strategy='bad' if case == 'bad_strategy_id' else None)
    assert (error.value.code, error.value.status) == (expected, 401 if expected == 'invalid_session' else 409)


@pytest.mark.parametrize('case', ['draft','revoked','replaced','profile_payload','profile_hash',
    'profile_rehashed','profile_revoked','strategy_hash'])
def test_reader_rejects_noncurrent_or_corrupted_strategy(real_strategy_env, case):
    env = real_strategy_env
    if case == 'revoked': env.strategies.revoke(env.claims, revoke_body(env.confirmed))
    elif case in ('draft', 'replaced'):
        request = prepare_body(env)
        if case == 'replaced':
            request.update(draft_id=env.prepare_request['draft_id'], draft_revision=2)
        draft = env.strategies.prepare(env.claims, request)
        if case == 'draft': env.snapshot = draft['snapshot']
    else:
        with env.admin.connect() as conn:
            if case == 'profile_payload':
                conn.execute("UPDATE business_profile_versions SET payload=payload || '{\"other\":\"tampered\"}'::jsonb WHERE profile_version_id=%s", (env.profile,))
            elif case == 'profile_hash':
                conn.execute("UPDATE business_profile_versions SET content_sha256=%s WHERE profile_version_id=%s", ('0'*64, env.profile))
            elif case == 'profile_rehashed':
                changed = {'description': DESCRIPTION, 'other': 'tampered'}
                from psycopg.types.json import Jsonb
                conn.execute('UPDATE business_profile_versions SET payload=%s,content_sha256=%s WHERE profile_version_id=%s',
                    (Jsonb(changed), digest(changed), env.profile))
            elif case == 'profile_revoked':
                conn.execute("UPDATE business_profile_versions SET status='REVOKED' WHERE profile_version_id=%s", (env.profile,))
            else:
                conn.execute('ALTER TABLE pilot_research_strategy_versions DISABLE TRIGGER USER')
                conn.execute('UPDATE pilot_research_strategy_versions SET configuration_sha256=%s WHERE strategy_version_id=%s', ('0'*64, env.snapshot['strategy_version_id']))
                conn.execute('ALTER TABLE pilot_research_strategy_versions ENABLE TRIGGER USER')
    with snapshot_cursor(env) as cursor, pytest.raises(ExecutionRuntimeError, match='strategy_conflict'):
        read(env, cursor)


def test_another_owner_session_revokes_between_reads_without_mixing_snapshot(real_strategy_env):
    env = real_strategy_env
    service = real_review(env)
    rows = [prepare_review(env, service, public_url='https://example.com/synthetic-'+suffix)
            for suffix in ('one','two')]
    receipts = [service.review(env.claims, row[-1]) for row in rows]
    other_session = verify_token_claims(issue_token(env.claims.user_id, SECRET), SECRET)
    calls = 0
    def interleaved(cursor, claims, profile, strategy):
        nonlocal calls
        value = env.strategies.read_snapshot(cursor, claims, profile, strategy)
        calls += 1
        if calls == 1:
            env.strategies.revoke(other_session, revoke_body(env.confirmed))
        return value
    service.strategy_snapshot_reader = interleaved
    during = service.list_candidates(env.claims, status='IMPORTED')
    assert calls == 2 and during['total'] == len(during['items']) == 2
    assert {item['assessment']['id'] for item in during['items']} == {row[2]['assessment']['id'] for row in rows}
    service.strategy_snapshot_reader = env.strategies.read_snapshot
    after = service.list_candidates(env.claims)
    assert after['total'] == 2 and all(item['assessmentStale'] and not item['currentBindingValid'] for item in after['items'])
    assert service.list_candidates(env.claims, status='IMPORTED')['total'] == 0
    for row, receipt in zip(rows, receipts):
        for request in (review_payload(row[1]), row[-1] | {'requestId': str(uuid4())}):
            with pytest.raises(CandidateIngestionError, match='strategy_conflict'):
                service.review(env.claims, request)
        assert service.get_request(env.claims, row[-1]['requestId']) == receipt
    assert env.strategies.get_receipt(env.claims, env.confirm_request['request_id']) == env.confirmed
    with pytest.raises(ExecutionRuntimeError, match='strategy_conflict'):
        apply(env, start(env))


@pytest.mark.parametrize('operation', ['list','assess','include'])
@pytest.mark.parametrize('failure,status', [('strategy_store_unavailable',503), ('invalid_session',401)])
def test_strategy_failure_is_not_empty_or_stale(real_strategy_env, operation, failure, status):
    env = real_strategy_env
    service, binding, assessed, check, decision = prepare_review(env)
    def unavailable(*args): raise ExecutionRuntimeError(failure, status)
    service.strategy_snapshot_reader = unavailable
    service.strategy_resolver = unavailable
    with pytest.raises(CandidateIngestionError) as error:
        if operation == 'list': service.list_candidates(env.claims, status='IMPORTED')
        else: service.review(env.claims, review_payload(binding) if operation == 'assess' else decision)
    assert (error.value.code, error.value.status) == (failure, status)


def test_reader_database_failure_is_sanitized(real_strategy_env):
    env = real_strategy_env
    with snapshot_cursor(env) as cursor:
        cursor.close()
        with pytest.raises(ExecutionRuntimeError) as error:
            read(env, cursor)
    assert (error.value.code, error.value.status) == ('strategy_store_unavailable', 503)
    assert error.value.__context__ is None


def test_plain_snapshot_does_not_authorize_execution_or_review(real_strategy_env):
    env = real_strategy_env
    service, binding, assessed, check, decision = prepare_review(env)
    with snapshot_cursor(env) as cursor: value = read(env, cursor)
    plain = lambda *args: value
    env.runtime.strategy_resolver = plain
    service.strategy_resolver = plain
    with pytest.raises(ExecutionRuntimeError, match='strategy_conflict'):
        apply(env, start(env))
    with pytest.raises(CandidateIngestionError, match='strategy_conflict'):
        service.review(env.claims, decision)


@pytest.mark.parametrize('case', ['missing','extra_key','tuple_platforms','wrong_hash','wrong_binding'])
def test_list_requires_exact_explicit_snapshot_reader(real_strategy_env, case):
    env = real_strategy_env
    service, binding, assessed, check, decision = prepare_review(env)
    service.review(env.claims, decision)
    value = env.snapshot | {'configuration_sha256': env.confirmed['configuration_sha256']}
    if case == 'extra_key': value['authority'] = True
    if case == 'tuple_platforms': value['platforms'] = tuple(value['platforms'])
    if case == 'wrong_hash': value['configuration_sha256'] = '0'*64
    if case == 'wrong_binding': value['profile_version_id'] = str(uuid4())
    service.strategy_snapshot_reader = None if case == 'missing' else lambda *args: value
    def forbidden(*args): pytest.fail('list must never use write resolver')
    service.strategy_resolver = forbidden
    page = service.list_candidates(env.claims)
    assert page['total'] == 1 and page['items'][0]['assessmentStale']
    assert not page['items'][0]['currentBindingValid']
