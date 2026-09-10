"""Real restricted-PG reply persistence; all platform/origin inputs are synthetic."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from pilot.auth import issue_token, verify_token_claims
from pilot.reply_contract import ManualFollowupEvent, PlatformReplyEvent, mark_read
from pilot.reply_store import ReplyEventStore, ReplyStoreError
from pilot.store import PilotStore
from tests.test_execution_runtime_postgres import databases as execution_databases
from tests.test_reply_contract import manual_event, platform_event

SECRET = 'synthetic-reply-tests-only'


@pytest.fixture(scope='module')
def databases(execution_databases):
    admin, app = execution_databases
    with admin.connect() as conn:
        conn.execute("SELECT set_config('yike.app_role',%s,true)", (app.role,))
        for name in ('grant_reply_events.sql','grant_outreach_contract.sql'):
            source = (Path(__file__).parents[1] / 'deploy' / name).read_text()
            conn.execute(source); conn.execute(source)
        assert conn.execute("SELECT has_table_privilege(%s,'pilot_reply_events','UPDATE')", (app.role,)).fetchone() == (False,)
    return admin, app


@pytest.fixture
def env(databases):
    admin, app = databases
    provision = PilotStore(admin)
    tenants = [provision.provision_tenant('synthetic-reply-tests') for _ in range(2)]
    users = [provision.provision_user(tenant, f'{uuid4()}@example.invalid') for tenant in (tenants[0], tenants[0], tenants[1])]
    claims = [verify_token_claims(issue_token(user, SECRET), SECRET) for user in users]
    yield SimpleNamespace(admin=admin, app=app, tenants=tenants, users=users, claims=claims[0],
        others=claims[1:], tenant=tenants[0], store=ReplyEventStore(app))
    with admin.connect() as conn:
        # Only these fixture-created tenants; append-only facts are removed by
        # test administrator cleanup, never by the restricted product role.
        conn.execute("SET LOCAL session_replication_role='replica'")
        for table in ('pilot_reply_events','pilot_outreach_confirmations','pilot_session_revocations','pilot_users','pilot_tenants'):
            conn.execute(sql.SQL('DELETE FROM {} WHERE tenant_id=ANY(%s)').format(sql.Identifier(table)), (tenants,))


def manual(env, **changes):
    return manual_event(tenant_id=env.tenant, user_id=env.claims.user_id, **changes)


def platform(env, **changes):
    return platform_event(tenant_id=env.tenant, user_id=env.claims.user_id, **changes)


def origin(env, event):
    from pilot.outreach_store import snapshot_record
    from tests.test_outreach_store import objects
    snapshot = objects().model_copy(update=dict(request_id=event.outreach_request_id,
        opportunity_id=event.opportunity_id, source_id=event.source_id, channel=event.channel))
    record = snapshot_record(snapshot) | {'tenant_id':event.tenant_id,'owner_user_id':event.user_id}
    record['snapshot'] = Jsonb(record['snapshot'])
    # Fixture-only immutable prior confirmation; the tested reply writes below
    # always use the restricted role, never administrator success as evidence.
    with env.admin.connect() as conn:
        conn.execute(sql.SQL('INSERT INTO pilot_outreach_confirmations ({}) VALUES ({})').format(
            sql.SQL(',').join(map(sql.Identifier,record)), sql.SQL(',').join(sql.Placeholder() for _ in record)), list(record.values()))


def rows(env):
    with env.app.connect() as conn, conn.cursor() as cursor:
        env.store._active(cursor, env.claims)
        cursor.execute('SELECT event_id,revision,payload FROM pilot_reply_events ORDER BY revision,event_id')
        return cursor.fetchall()


def test_first_manual_and_exact_replay_are_append_only(env):
    event = manual(env)
    assert env.store.record(env.claims,event) == event
    assert env.store.record(env.claims,event) == event
    assert len(rows(env)) == 1
    with pytest.raises(ReplyStoreError,match='event_conflict'):
        env.store.record(env.claims,event.model_copy(update={'note':'changed'}))
    assert env.store.list_for_opportunity(env.claims,event.opportunity_id) == [event]


def test_first_platform_requires_original_owner_source_and_opportunity(env):
    event = platform(env)
    with pytest.raises(ReplyStoreError,match='reply_origin_unavailable'): env.store.record(env.claims,event)
    origin(env,event)
    assert env.store.record(env.claims,event) == event
    assert env.store.record(env.claims,event.model_copy(update={'event_id':str(uuid4())})) == event
    assert len(rows(env)) == 1
    with pytest.raises(ReplyStoreError,match='reply_origin_unavailable'):
        env.store.record(env.claims,event.model_copy(update={'event_id':str(uuid4()),'opportunity_id':str(uuid4())}))


def correction(event, **changes):
    return type(event).model_validate(event.model_dump() | dict(event_id=str(uuid4()),
        state='CORRECTED', corrects_event_id=event.event_id, reason='synthetic correction') | changes)


@pytest.mark.parametrize('state',['CORRECTED','VOID'])
@pytest.mark.parametrize('kind',['manual','platform'])
def test_valid_new_id_history_appends_and_replays(env, state, kind):
    event = manual(env) if kind=='manual' else platform(env)
    if kind=='platform': origin(env,event)
    env.store.record(env.claims,event)
    updated = correction(event,state=state)
    assert env.store.record(env.claims,updated) == updated
    assert env.store.record(env.claims,updated) == updated
    facts = rows(env)
    assert len(facts) == 2 and {row[0] for row in facts} == {event.event_id,updated.event_id}
    if kind=='platform': assert [row[1] for row in facts] == [1,2]


@pytest.mark.parametrize('field',['opportunity_id','source_id','profile_version_id','outreach_request_id'])
def test_correction_cannot_reassociate_same_owner_target(env, field):
    event=manual(env); env.store.record(env.claims,event)
    with pytest.raises(ReplyStoreError,match='event_transition_invalid'):
        env.store.record(env.claims,correction(event,**{field:str(uuid4())}))
    assert len(rows(env)) == 1


@pytest.mark.parametrize('field,value',[('platform','DOUYIN'),('channel','comment'),
    ('external_reply_id','other'),('sender_public_id','other')])
def test_platform_correction_keeps_public_identity(env,field,value):
    event=platform(env); origin(env,event); env.store.record(env.claims,event)
    with pytest.raises(ReplyStoreError,match='event_transition_invalid'):
        env.store.record(env.claims,correction(event,**{field:value}))


def test_correction_target_must_be_existing_same_owner_active_kind(env):
    event=manual(env); env.store.record(env.claims,event)
    for claims in env.others:
        with pytest.raises(ReplyStoreError,match='event_target_unavailable'):
            env.store.record(claims,correction(event,user_id=claims.user_id,
                tenant_id=env.tenant if claims==env.others[0] else env.tenants[1]))
    with pytest.raises(ReplyStoreError,match='event_target_unavailable'):
        env.store.record(env.claims,correction(event,corrects_event_id=str(uuid4())))
    wrong_kind=platform(env,opportunity_id=event.opportunity_id,source_id=event.source_id,
        profile_version_id=event.profile_version_id,outreach_request_id=event.outreach_request_id,
        state='CORRECTED',corrects_event_id=event.event_id,reason='synthetic')
    with pytest.raises(ReplyStoreError,match='event_transition_invalid'): env.store.record(env.claims,wrong_kind)
    updated=correction(event); env.store.record(env.claims,updated)
    with pytest.raises(ReplyStoreError,match='event_transition_invalid'):
        env.store.record(env.claims,correction(updated,state='VOID'))


def read_event(event):
    return mark_read(event,read_at=datetime(2026,9,10,2,2,tzinfo=timezone.utc),
                     observed_at=datetime(2026,9,10,2,3,tzinfo=timezone.utc))


def test_mark_read_appends_only_read_fact_and_replays_original_observation(env):
    event=platform(env); origin(env,event); env.store.record(env.claims,event)
    read=read_event(event)
    assert env.store.record(env.claims,read) == read
    assert env.store.record(env.claims,read) == read
    # Exact older observation is immutable historical replay, not an UNREAD update.
    assert env.store.record(env.claims,event) == event
    assert [row[1] for row in rows(env)] == [1,2]


@pytest.mark.parametrize('change',[{'body':'changed'},{'sender_public_id':'other'}, {'channel':'comment'},
    {'external_reply_id':'other'}, {'read_state':'UNKNOWN'}, {'observed_at':'2026-09-10T02:00:30Z'}])
def test_same_id_does_not_allow_arbitrary_platform_revision(env,change):
    event=platform(env); origin(env,event); env.store.record(env.claims,event)
    with pytest.raises(ReplyStoreError,match='event_conflict'):
        env.store.record(env.claims,event.model_copy(update=change))
    assert len(rows(env)) == 1


def test_unknown_to_read_and_read_rollback_are_not_new_facts(env):
    unknown=platform(env,read_state='UNKNOWN'); origin(env,unknown); env.store.record(env.claims,unknown)
    forged=unknown.model_copy(update={'read_state':'READ','read_at':'2026-09-10T02:02:00Z','observed_at':'2026-09-10T02:03:00Z'})
    with pytest.raises(ReplyStoreError,match='event_conflict'): env.store.record(env.claims,forged)
    event=platform(env,external_reply_id='second'); origin(env,event); env.store.record(env.claims,event)
    env.store.record(env.claims,read_event(event))
    with pytest.raises(ReplyStoreError,match='event_conflict'):
        env.store.record(env.claims,event.model_copy(update={'observed_at':'2026-09-10T02:04:00Z'}))


def test_same_event_id_cannot_be_reused_for_another_platform_identity(env):
    event=platform(env); origin(env,event); env.store.record(env.claims,event)
    changed=event.model_copy(update={'source_id':str(uuid4()),'outreach_request_id':str(uuid4())})
    origin(env,changed)
    with pytest.raises(ReplyStoreError,match='event_conflict'): env.store.record(env.claims,changed)


@pytest.mark.parametrize('kind',['manual','platform','correction'])
def test_concurrent_same_event_and_platform_duplicates_are_idempotent(env,kind):
    event=manual(env) if kind=='manual' else platform(env)
    if kind!='manual': origin(env,event)
    if kind=='correction': env.store.record(env.claims,event); event=correction(event)
    sessions=[verify_token_claims(issue_token(env.users[0],SECRET),SECRET) for _ in range(4)]
    events=[event]*4 if kind!='platform' else [event.model_copy(update={'event_id':str(uuid4())}) for _ in range(4)]
    with ThreadPoolExecutor(4) as pool:
        results=list(pool.map(lambda pair: env.store.record(*pair),zip(sessions,events)))
    assert all(result==results[0] for result in results)
    assert len(rows(env)) == (2 if kind=='correction' else 1)


def test_different_correction_ids_serialize_history_revision_for_active_target(env):
    event=platform(env); origin(env,event); env.store.record(env.claims,event)
    changes=[correction(event,body='corrected one'),correction(event,state='VOID')]
    sessions=[verify_token_claims(issue_token(env.users[0],SECRET),SECRET) for _ in changes]
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda pair: env.store.record(*pair),zip(sessions,changes)))
    assert results==changes
    assert [row[1] for row in rows(env)] == [1,2,3]


def test_replay_rechecks_session_after_read_and_writes_rollback(env,monkeypatch):
    event=manual(env); env.store.record(env.claims,event)
    original=env.store._active
    calls=0
    def expire(cursor,claims):
        nonlocal calls
        calls+=1
        if calls>=3: raise ReplyStoreError('invalid_session',401)
        return original(cursor,claims)
    monkeypatch.setattr(env.store,'_active',expire)
    with pytest.raises(ReplyStoreError,match='invalid_session'): env.store.record(env.claims,event)
    calls=0
    with pytest.raises(ReplyStoreError,match='invalid_session'):
        env.store.record(env.claims,manual(env))
    monkeypatch.setattr(env.store,'_active',original)
    assert len(rows(env)) == 1
    env.store.sessions.revoke([env.claims])
    with pytest.raises(ReplyStoreError,match='invalid_session'): env.store.record(env.claims,event)


@pytest.mark.parametrize('kind',['manual','platform'])
def test_concurrent_conflicting_same_event_id_is_fixed_conflict_not_unique_error(env,kind):
    event=manual(env) if kind=='manual' else platform(env)
    changed=event.model_copy(update={'source_id':str(uuid4()),'outreach_request_id':str(uuid4())})
    if kind=='platform': origin(env,event); origin(env,changed)
    sessions=[verify_token_claims(issue_token(env.users[0],SECRET),SECRET) for _ in range(2)]
    def attempt(pair):
        try: env.store.record(*pair); return 'recorded'
        except ReplyStoreError as error: return error.code
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(attempt,zip(sessions,[event,changed])))
    assert sorted(results)==['event_conflict','recorded']
    assert len(rows(env))==1


def test_real_session_expiry_while_waiting_for_event_lock(env):
    import time
    from pilot.auth import TokenClaims
    from tests.test_device_credentials_postgres import wait_for_lock
    event=manual(env)
    expires=int(time.time())+2
    claims=TokenClaims(env.users[0],expires,'synthetic-expiring-'+str(uuid4()))
    key=env.store._lock_key(__import__('json').dumps(('event',env.tenant,env.users[0],event.event_id),
        ensure_ascii=False,sort_keys=True,separators=(',',':')))
    with ThreadPoolExecutor(1) as pool:
        with env.admin.connect() as blocker:
            blocker.execute('SELECT pg_advisory_xact_lock(11801,%s)',(key,))
            future=pool.submit(env.store.record,claims,event)
            wait_for_lock(env.admin,'pg_advisory_xact_lock(11801')
            while time.time()<expires: time.sleep(0.01)
        with pytest.raises(ReplyStoreError,match='invalid_session'): future.result(timeout=5)
    assert rows(env)==[]
