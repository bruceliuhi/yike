"""Ordinary HTTPS + real restricted PostgreSQL; only synthetic customer data."""
import csv
import io
from uuid import uuid4

from fastapi.testclient import TestClient
from psycopg import sql
import pytest

from pilot.auth import issue_token
from pilot.web import build_app
from tests.test_confirmed_strategy_review_postgres import (
    databases, env, execution_databases, execution_env, raw_databases, raw_env,
    real_strategy_env,
)
from tests.test_execution_runtime_postgres import SECRET
from tests.test_opportunity_evidence_postgres import include


@pytest.fixture
def managed(env):
    # Only the three pre-existing trial status column privileges. Deliberately
    # no tenant-name, phone, code, ciphertext or new write permission.
    with env.admin.connect() as conn:
        conn.execute(sql.SQL('GRANT SELECT(activated_at,expires_at,revoked_at,user_id) '
            'ON pilot_trial_accounts TO {}').format(sql.Identifier(env.db.role)))
    client = TestClient(build_app(env.store, auth_secret=SECRET), base_url='https://pilot.example')
    return env, client, {'Authorization': 'Bearer ' + issue_token(env.users[0], SECRET)}


def test_account_uses_authenticated_scope_and_keeps_unknown_license_device(managed):
    env, client, headers = managed
    response = client.get('/api/ui/management/account', headers=headers)
    assert response.status_code == 200
    result = response.json()
    assert result == {'userId': env.users[0], 'accountScope': {'id': env.tenant, 'version': 1},
        'spaceId': env.tenant, 'spaceName': '当前客户空间',
        'revision': result['revision'], 'license': {'status': 'UNKNOWN', 'expiresAt': None}, 'device': None}
    assert len(result['revision']) == 64
    assert response.headers['cache-control'] == 'no-store'
    assert client.get('/api/ui/management/account', headers=headers).json() == result
    with env.db.connect() as conn:
        assert not conn.execute("SELECT has_column_privilege(current_user,'pilot_trial_accounts','phone_ciphertext','SELECT')").fetchone()[0]
        assert not conn.execute("SELECT has_table_privilege(current_user,'pilot_tenants','SELECT')").fetchone()[0]


def test_cookie_reads_identify_the_current_user_even_within_the_same_tenant(managed):
    env, client, _ = managed
    for user in env.users[:2]:
        client.cookies.clear()
        assert client.post('/api/ui/session', json={'token': issue_token(user, SECRET)}).status_code == 200
        for path in ('/api/ui/management/account', '/api/ui/management/export?kind=csv'):
            response = client.get(path)
            assert response.status_code == 200
            assert response.json()['userId'] == user
            assert response.json()['accountScope'] == {'id': env.tenant, 'version': 1}


def test_real_trial_expiry_is_not_session_expiry_and_revocation_still_denies(managed):
    env, client, headers = managed
    phone_hash = uuid4().hex * 2
    with env.admin.connect() as conn:
        conn.execute('INSERT INTO pilot_phone_bindings(phone_hash,user_id) VALUES(%s,%s)', (phone_hash, env.users[0]))
        conn.execute("INSERT INTO pilot_trial_accounts(trial_id,user_id,phone_hash,days,activated_at,expires_at,credential_kind,activation_source) "
            "VALUES(%s,%s,%s,3,clock_timestamp(),clock_timestamp()+interval '72 hours','SELF_SERVICE_SMS','SMS')",
            (str(uuid4()), env.users[0], phone_hash))
    try:
        response = client.get('/api/ui/management/account', headers=headers)
        assert response.status_code == 200
        assert response.json()['license']['status'] == 'ACTIVE'
        assert response.json()['license']['expiresAt']
        with env.admin.connect() as conn:
            conn.execute('UPDATE pilot_trial_accounts SET revoked_at=clock_timestamp() WHERE user_id=%s', (env.users[0],))
        for path in ('/api/ui/management/account', '/api/ui/management/export?kind=csv'):
            assert client.get(path, headers=headers).status_code == 401
    finally:
        with env.admin.connect() as conn:
            conn.execute('DELETE FROM pilot_trial_accounts WHERE user_id=%s', (env.users[0],))
            conn.execute('DELETE FROM pilot_phone_bindings WHERE user_id=%s', (env.users[0],))


@pytest.mark.parametrize('path', ['/api/ui/management/account', '/api/ui/management/export?kind=csv'])
def test_reads_require_authentication_and_reject_scope_injection(managed, path):
    _, client, headers = managed
    assert client.get(path).status_code == 401
    separator = '&' if '?' in path else '?'
    for forged in ('tenant_id=other', 'userId=other', 'deviceId=other'):
        assert client.get(path + separator + forged, headers=headers).status_code == 422
    assert client.post(path, headers=headers).status_code == 405
    assert client.delete('/api/ui/session', headers=headers).status_code == 200
    assert client.get(path, headers=headers).status_code == 401


def test_csv_is_owner_scoped_allowlisted_and_formula_safe(real_strategy_env):
    env = real_strategy_env
    _, _, _, _, _, _, opportunity = include(env)
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_opportunities SET title=%s,buyer=%s,draft_dm=%s,contact_path=%s WHERE opportunity_id=%s",
            ('=HYPERLINK("https://evil.invalid")', '买方,甲', 'PRIVATE MESSAGE', '13800000000', opportunity))
        conn.execute("UPDATE pilot_sources SET public_url='https://example.com/item?token=PRIVATE_TOKEN#PRIVATE_FRAGMENT' "
            "WHERE source_id=(SELECT source_id FROM pilot_opportunities WHERE opportunity_id=%s)", (opportunity,))
    client = TestClient(build_app(env.store, auth_secret=SECRET), base_url='https://pilot.example')
    def get(user):
        return client.get('/api/ui/management/export?kind=csv', headers={'Authorization': 'Bearer ' + issue_token(user, SECRET)})
    exported = get(env.users[0])
    assert exported.status_code == 200
    result = exported.json()
    assert result['spaceId'] == env.tenant and result['name'].endswith('.csv')
    rows = list(csv.DictReader(io.StringIO(result['content'].lstrip('\ufeff'))))
    assert len(rows) == 1
    assert rows[0]['商机标题'].startswith("'=HYPERLINK")
    assert rows[0]['需求方'] == '买方,甲'
    assert rows[0]['来源页面（不含参数）'] == 'https://example.com/item'
    for private in ('PRIVATE MESSAGE', '13800000000', 'PRIVATE_TOKEN', 'PRIVATE_FRAGMENT', 'payload_sha256', 'draft_dm'):
        assert private not in exported.text
    for user in env.users[1:]:
        other = get(user)
        assert other.status_code == 200
        assert list(csv.DictReader(io.StringIO(other.json()['content'].lstrip('\ufeff')))) == []
    # Actual limited role + RLS, not only a supplied WHERE predicate.
    with env.db.connect() as conn:
        conn.execute("SELECT set_config('yike.tenant_id',%s,true)", (env.tenants[1],))
        assert conn.execute('SELECT count(*) FROM pilot_opportunities WHERE opportunity_id=%s', (opportunity,)).fetchone()[0] == 0


@pytest.mark.parametrize('boundary', ['csv_bytes', 'json_bytes', 'row_count'])
def test_csv_size_limit_is_explicit_and_backup_is_not_enabled(real_strategy_env, monkeypatch, boundary):
    env = real_strategy_env
    _, _, _, _, _, _, opportunity = include(env)
    title = '大' * 800000 if boundary == 'csv_bytes' else '\t' * 1100000
    if boundary == 'row_count':
        # Exercise the row boundary with real rows and the same limited DB role.
        from pilot import management_read_api
        assert management_read_api.MAX_EXPORT_ROWS == 1000
        monkeypatch.setattr(management_read_api, 'MAX_EXPORT_ROWS', 0)
        title = '正常大小的商机标题'
    with env.admin.connect() as conn:
        conn.execute('UPDATE pilot_opportunities SET title=%s WHERE opportunity_id=%s', (title, opportunity))
    client = TestClient(build_app(env.store, auth_secret=SECRET), base_url='https://pilot.example')
    headers = {'Authorization': 'Bearer ' + issue_token(env.users[0], SECRET)}
    response = client.get('/api/ui/management/export?kind=csv', headers=headers)
    assert response.status_code == 413
    assert response.json()['detail']['code'] == 'management_export_too_large'
    assert 'content' not in response.json()
    assert client.get('/api/ui/management/export?kind=backup-json', headers=headers).status_code == 501
