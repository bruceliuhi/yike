"""Isolated PostgreSQL evidence only; synthetic invitees, no real SMS."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import re
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from pilot.auth import verify_token_claims
from pilot.ops_store import OpsStore, OpsError
from pilot.runtime import build_runtime_app
from pilot.store import PilotStore
from pilot.trials import TrialPhoneAuthStore
from pilot.web import build_app
from tests.test_ops_trials import databases, SECRET, KEY, otp

AUTH_SECRET = 'synthetic-access-session-key-at-least-32'


@pytest.fixture
def access_env(databases):
    admin, opsdb, appdb = databases
    ops = OpsStore(opsdb, phone_secret=SECRET, encryption_key=KEY)
    phone = '166' + str(int(uuid4().hex[:8], 16) % 100000000).zfill(8)
    invite = ops.issue(phone, '合成临时访问客户')
    return admin, appdb, ops, phone, invite


def client(appdb, peer=None):
    app = build_runtime_app(appdb, auth_secret=AUTH_SECRET,
                            environment={'YIKE_PILOT_PHONE_AUTH_SECRET': SECRET.decode()})
    return TestClient(app, base_url='https://pilot.example', client=(peer or str(uuid4()), 50000))


def login(http, code):
    return http.post('/api/ui/auth/access-session', json={'access_code': code})


def row(admin, user):
    with admin.connect() as c:
        return c.execute('SELECT activated_at,expires_at,activation_source,credential_kind FROM pilot_trial_accounts WHERE user_id=%s', (user,)).fetchone()


def test_first_access_activates_72_hours_and_persistent_scoped_session(access_env):
    admin, appdb, ops, phone, invite = access_env
    assert callable(getattr(ops, 'issue_access', None)), 'explicit ops access issuance is missing'
    access = ops.issue_access(invite['trial_id'])
    http = client(appdb)
    result = login(http, access['code'])
    assert result.status_code == 200, result.text
    assert result.json()['user_id'] == invite['user_id']
    activated, expires, source, kind = row(admin, invite['user_id'])
    assert expires - activated == timedelta(hours=72)
    assert (source, kind) == ('TEMPORARY_ACCESS', 'TEMPORARY_ACCESS')
    cookie = result.headers['set-cookie']
    assert all(x in cookie for x in ('HttpOnly', 'Secure', 'SameSite=strict'))
    maximum = int(re.search(r'Max-Age=(\d+)', cookie)[1])
    assert 259190 <= maximum <= 259200
    claims = verify_token_claims(http.cookies.get('pilot_session'), AUTH_SECRET)
    assert claims.expires_at <= int(expires.timestamp())
    assert claims.auth_source == 'temporary_access'
    restored = client(appdb)
    restored.cookies.set('pilot_session', http.cookies.get('pilot_session'))
    assert restored.get('/api/ui/session').status_code == 200
    assert phone not in result.text and access['code'] not in result.text
    with admin.connect() as c:
        assert c.execute('SELECT phone_verified_at FROM pilot_phone_bindings WHERE user_id=%s', (invite['user_id'],)).fetchone()[0] is None


def test_concurrent_and_repeated_access_never_extend_or_duplicate(access_env):
    admin, appdb, ops, _, invite = access_env
    access = ops.issue_access(invite['trial_id'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: login(client(appdb), access['code']), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    before = row(admin, invite['user_id'])
    assert login(client(appdb), access['code']).status_code == 200
    assert row(admin, invite['user_id']) == before
    with admin.connect() as c:
        assert c.execute('SELECT count(*) FROM pilot_users WHERE user_id=%s', (invite['user_id'],)).fetchone()[0] == 1


def test_old_trial_code_cannot_login_and_conversion_invalidates_sms_code(access_env):
    _, appdb, ops, phone, invite = access_env
    assert login(client(appdb), invite['code']).status_code == 401
    access = ops.issue_access(invite['trial_id'])
    assert login(client(appdb), invite['code']).status_code == 401
    auth = TrialPhoneAuthStore(appdb, SECRET)
    from pilot.phone_auth import PhoneAuthError
    with pytest.raises(PhoneAuthError):
        auth.consume_trial(phone, otp(auth, phone), invite['code'])
    assert login(client(appdb), access['code']).status_code == 200


def test_wrong_code_rate_limit_survives_new_app_and_no_secret_output(access_env, caplog):
    _, appdb, _, _, _ = access_env
    peer = str(uuid4())
    bad = 'YA-' + 'a' * 32
    for _ in range(10):
        response = login(client(appdb, peer), bad)
        assert response.status_code == 401
        assert response.json()['detail']['code'] == 'access_auth_failed'
    response = login(client(appdb, peer), bad)
    assert response.status_code == 429
    assert response.json()['detail']['code'] == 'auth_rate_limited'
    assert bad not in caplog.text and bad not in response.text


@pytest.mark.parametrize('change', ['revoke', 'expire'])
def test_expired_or_revoked_access_and_existing_sessions_denied(access_env, change):
    admin, appdb, ops, _, invite = access_env
    access = ops.issue_access(invite['trial_id'])
    http = client(appdb)
    assert login(http, access['code']).status_code == 200
    if change == 'revoke':
        ops.revoke(invite['trial_id'])
    else:
        with admin.connect() as c:
            c.execute("UPDATE pilot_trial_accounts SET expires_at=clock_timestamp()-interval '1 second' WHERE user_id=%s", (invite['user_id'],))
    assert http.get('/api/ui/session').status_code == 401
    denied = login(client(appdb), access['code'])
    assert denied.status_code == 401 and denied.json()['detail']['code'] == 'access_auth_failed'
    with pytest.raises(OpsError):
        ops.issue_access(invite['trial_id'])


def test_access_reissue_invalidates_old_code_without_extending_trial(access_env):
    admin, appdb, ops, _, invite = access_env
    first = ops.issue_access(invite['trial_id'])
    assert login(client(appdb), first['code']).status_code == 200
    before = row(admin, invite['user_id'])
    second = ops.issue_access(invite['trial_id'])
    assert second['user_id'] == first['user_id']
    assert login(client(appdb), first['code']).status_code == 401
    assert login(client(appdb), second['code']).status_code == 200
    assert row(admin, invite['user_id']) == before
    with pytest.raises(OpsError):
        ops.reissue(invite['trial_id'])


def test_real_otp_after_access_verifies_original_phone_preserves_expiry(access_env):
    admin, appdb, ops, phone, invite = access_env
    access = ops.issue_access(invite['trial_id'])
    assert login(client(appdb), access['code']).status_code == 200
    before = row(admin, invite['user_id'])
    auth = TrialPhoneAuthStore(appdb, SECRET)
    assert auth.consume(phone, otp(auth, phone)) == invite['user_id']
    assert row(admin, invite['user_id']) == before
    with admin.connect() as c:
        assert c.execute('SELECT phone_verified_at FROM pilot_phone_bindings WHERE user_id=%s', (invite['user_id'],)).fetchone()[0] is not None
    listed = next(x for x in ops.users() if x['user_id'] == invite['user_id'])
    assert listed['phone_verified_at'] is not None


def test_access_routing_requires_https_origin_and_configuration(access_env):
    _, appdb, ops, _, invite = access_env
    access = ops.issue_access(invite['trial_id'])
    unconfigured = TestClient(build_app(PilotStore(appdb), auth_secret=AUTH_SECRET), base_url='https://pilot.example')
    assert login(unconfigured, access['code']).status_code == 501
    http = client(appdb)
    assert http.get('/api/ui/capabilities').json()['capabilities']['access_login'] == {'available': True}
    assert http.post('http://pilot.example/api/ui/auth/access-session', json={'access_code': access['code']}).status_code == 400
    assert http.post('/api/ui/auth/access-session', json={'access_code': access['code']}, headers={'Origin': 'https://evil.example'}).status_code == 403
    assert http.post('/api/ui/auth/access-session', json={'access_code': access['code'], 'user_id': invite['user_id']}).status_code == 422


def test_two_accounts_scope_logout_and_restricted_grants(access_env):
    _, appdb, ops, phone, first = access_env
    second = ops.issue('155' + phone[3:], '第二临时客户')
    a, b = client(appdb), client(appdb)
    ra = login(a, ops.issue_access(first['trial_id'])['code'])
    rb = login(b, ops.issue_access(second['trial_id'])['code'])
    assert ra.status_code == rb.status_code == 200
    assert ra.json()['account_scope']['id'] != rb.json()['account_scope']['id']
    old = a.cookies.get('pilot_session')
    assert a.delete('/api/ui/session').status_code == 200
    a.cookies.set('pilot_session', old)
    assert a.get('/api/ui/session').status_code == 401
    assert b.get('/api/ui/session').status_code == 200
    with appdb.connect() as c:
        assert c.execute('SELECT access_code_hash FROM pilot_trial_accounts').fetchall() == []
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("UPDATE pilot_trial_accounts SET credential_kind='TEMPORARY_ACCESS'")


def test_ops_explicit_form_and_real_verified_label(access_env):
    _, appdb, ops, phone, invite = access_env
    from pilot.ops_web import build_ops_app
    http = TestClient(build_ops_app(ops, password='synthetic-operator-password', origin='https://ops.example'), base_url='https://ops.example')
    headers = {'Origin': 'https://ops.example'}
    http.post('/ops/login', data={'password': 'synthetic-operator-password'}, headers=headers)
    form = http.get('/ops/access', params={'trial_id': invite['trial_id']})
    assert form.status_code == 200 and '临时登录访问码' in form.text
    csrf = re.search('name="csrf" value="([^"]+)"', form.text)[1]
    assert http.post('/ops/access', data={'trial_id': invite['trial_id']}, headers=headers).status_code == 403
    issued = http.post('/ops/access', data={'trial_id': invite['trial_id'], 'csrf': csrf}, headers=headers)
    assert issued.status_code == 200
    code = re.search(r'YA-[A-Za-z0-9_-]{32}', issued.text)[0]
    assert login(client(appdb), code).status_code == 200
    listed = http.get('/ops/users')
    assert code not in listed.text and '未短信验证' in listed.text
    assert '临时访问' in listed.text


def test_revocation_between_access_check_and_session_returns_uniform_error(access_env, monkeypatch):
    _, appdb, ops, _, invite = access_env
    access = ops.issue_access(invite['trial_id'])
    from pilot.sessions import authenticate_session
    def revoke_before_session(*args):
        ops.revoke(invite['trial_id'])
        return authenticate_session(*args)
    monkeypatch.setattr('pilot.access_api.authenticate_session', revoke_before_session)
    response = login(client(appdb), access['code'])
    assert response.status_code == 401
    assert response.json()['detail']['code'] == 'access_auth_failed'
    assert 'set-cookie' not in response.headers
