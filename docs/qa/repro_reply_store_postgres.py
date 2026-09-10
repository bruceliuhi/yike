"""Diagnostic reproductions, NOT passing product acceptance tests."""
from pathlib import Path
from uuid import uuid4
import pytest
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from pilot.auth import issue_token, verify_token_claims
from pilot.store import PilotStore
from pilot.reply_store import ReplyEventStore, event_record
from pilot.reply_contract import ManualFollowupEvent, PlatformReplyEvent, transition_state
from tests.test_execution_runtime_postgres import databases
from tests.test_reply_contract import manual_event, platform_event

ROOT = Path(__file__).resolve().parents[2]

@pytest.fixture
def context(databases):
    admin, app = databases
    provision = PilotStore(admin)
    tenant = provision.provision_tenant('synthetic-reply-review')
    user = provision.provision_user(tenant, f'{uuid4()}@example.invalid')
    claims = verify_token_claims(issue_token(user, 'synthetic-reply-review'), 'synthetic-reply-review')
    with admin.connect() as conn:
        conn.execute("SELECT set_config('yike.app_role',%s,true)", (app.role,))
        conn.execute((ROOT / 'deploy/grant_reply_events.sql').read_text())
    return admin, app, claims, tenant

def test_reproduce_restricted_new_manual_write_permission_failure(context):
    admin, app, claims, tenant = context
    event = manual_event(tenant_id=tenant, user_id=claims.user_id)
    with pytest.raises(psycopg.errors.InsufficientPrivilege) as error:
        ReplyEventStore(app).record(claims, event)
    assert error.value.sqlstate == '42501'
    assert 'pilot_reply_events' in str(error.value)
    with admin.connect() as conn:
        assert conn.execute('SELECT count(*) FROM pilot_reply_events WHERE event_id=%s', (event.event_id,)).fetchone() == (0,)
    print('REPRO: restricted valid new manual followup rejected SQLSTATE 42501')

def test_reproduce_platform_correction_unique_conflict(context):
    admin, app, claims, tenant = context
    original = platform_event(tenant_id=tenant, user_id=claims.user_id)
    # Admin-only seed isolates correction SQL from origin/role gates. No real reply claim.
    record = event_record(original) | {'tenant_id': tenant, 'owner_user_id': claims.user_id}
    record['payload'] = Jsonb(record['payload'])
    with admin.connect() as conn:
        conn.execute(sql.SQL('INSERT INTO pilot_reply_events ({}) VALUES ({})').format(
            sql.SQL(',').join(map(sql.Identifier, record)), sql.SQL(',').join(sql.Placeholder() for _ in record)), list(record.values()))
    correction = PlatformReplyEvent.model_validate(original.model_dump() | {
        'event_id': str(uuid4()), 'state': 'CORRECTED', 'corrects_event_id': original.event_id, 'reason': 'synthetic correction'})
    assert transition_state(original, correction) == correction
    with pytest.raises(psycopg.errors.UniqueViolation) as error:
        ReplyEventStore(admin).record(claims, correction)
    assert error.value.sqlstate == '23505'
    with admin.connect() as conn:
        assert conn.execute('SELECT count(*) FROM pilot_reply_events WHERE tenant_id=%s', (tenant,)).fetchone() == (1,)
    print('REPRO: contract-valid platform correction conflicts SQLSTATE 23505; original retained')

def test_reproduce_correction_scope_validation_bypass(context):
    admin, app, claims, tenant = context
    original = manual_event(tenant_id=tenant, user_id=claims.user_id)
    ReplyEventStore(admin).record(claims, original)
    correction = ManualFollowupEvent.model_validate(original.model_dump() | {
        'event_id': str(uuid4()), 'state': 'CORRECTED', 'corrects_event_id': original.event_id,
        'opportunity_id': str(uuid4()), 'reason': 'synthetic invalid reassociation'})
    with pytest.raises(ValueError, match='scope mismatch'):
        transition_state(original, correction)
    assert ReplyEventStore(admin).record(claims, correction) == correction
    assert ReplyEventStore(admin).list_for_opportunity(claims, correction.opportunity_id) == [correction]
    print('REPRO: correction rejected by contract transition is persisted under another opportunity (admin diagnostic only)')


