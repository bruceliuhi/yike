"""Synthetic contracts: trial codes never replace phone OTP verification."""
import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
import psycopg
from fastapi.testclient import TestClient

from pilot.db import PilotDatabase
from pilot.store import PilotStore
from pilot.web import build_app
from pilot.auth import issue_token
from pilot.phone_auth import PhoneAuthError

SECRET = b'synthetic-phone-key-for-isolated-tests'
KEY = b'k' * 32


@pytest.fixture(scope='module')
def databases():
    url = os.environ.get('YIKE_OPS_TEST_DATABASE_URL')
    if not url:
        pytest.skip('explicit isolated ops PostgreSQL required')
    admin = PilotDatabase(url)
    admin.migrate()
    admin.migrate()
    with admin.connect() as c:
        for role in ('ops_test', 'ops_app'):
            if not c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (role,)).fetchone():
                c.execute(psycopg.sql.SQL('CREATE ROLE {} LOGIN').format(psycopg.sql.Identifier(role)))
        c.execute("SELECT set_config('yike.app_role','ops_app',true)")
        for line in Path('deploy/grant_runtime.sql').read_text().splitlines():
            if line.startswith('\\ir '):
                c.execute((Path('deploy') / line[4:]).read_text())
        c.execute("SELECT set_config('yike.ops_role','ops_test',true)")
        c.execute(Path('deploy/grant_ops.sql').read_text())
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    settings = conninfo_to_dict(url)
    def as_role(role):
        # PilotDatabase intentionally accepts URLs only; connection itself uses DSN.
        class RoleDatabase:
            def connect(self):
                return psycopg.connect(make_conninfo(**{**settings, 'user': role}))
        return RoleDatabase()
    return admin, as_role('ops_test'), as_role('ops_app')


@pytest.fixture
def env(databases):
    from pilot.ops_store import OpsStore
    from pilot.trials import TrialPhoneAuthStore
    admin, opsdb, appdb = databases
    ops = OpsStore(opsdb, phone_secret=SECRET, encryption_key=KEY)
    phone = '199' + str(int(uuid4().hex[:8], 16) % 100000000).zfill(8)
    invite = ops.issue(phone, '合成测试客户')
    auth = TrialPhoneAuthStore(appdb, SECRET)
    return admin, appdb, ops, auth, phone, invite


def otp(auth, phone):
    reservation = auth.reserve(phone, str(uuid4()))
    assert reservation.eligible
    auth.settle(phone, reservation.challenge_id, 'ACCEPTED')
    return reservation.code


def test_default_three_days_only_after_sms_activation(env):
    admin, appdb, ops, auth, phone, invite = env
    assert invite['days'] == 3 and invite['activated_at'] is None
    with pytest.raises(PhoneAuthError):
        auth.consume_trial(phone, '000000', invite['code'])
    code = otp(auth, phone)
    with pytest.raises(PhoneAuthError):
        auth.consume(phone, code)
    with pytest.raises(PhoneAuthError):
        auth.consume_trial(phone, code, 'wrong-trial-code')
    assert auth.consume_trial(phone, code, invite['code']) == invite['user_id']
    with admin.connect() as c:
        row = c.execute('SELECT activated_at,expires_at FROM pilot_trial_accounts WHERE user_id=%s', (invite['user_id'],)).fetchone()
        assert (row[1] - row[0]).total_seconds() == 72 * 3600
    with pytest.raises(PhoneAuthError):
        auth.consume_trial(phone, code, invite['code'])


def test_code_not_reusable_for_other_phone_or_renewal(env):
    admin, _, ops, auth, phone, invite = env
    other = '188' + phone[3:]
    second = ops.issue(other, '第二合成客户')
    with pytest.raises(PhoneAuthError):
        auth.consume_trial(other, otp(auth, other), invite['code'])
    auth.consume_trial(phone, otp(auth, phone), invite['code'])
    with admin.connect() as c:
        c.execute("UPDATE pilot_trial_accounts SET expires_at=clock_timestamp()-interval '1 second' WHERE user_id=%s", (invite['user_id'],))
        c.execute("UPDATE pilot_phone_challenges SET created_at=clock_timestamp()-interval '61 seconds' WHERE phone_hash=%s", (auth._phone(phone),))
    with pytest.raises(PhoneAuthError):
        auth.consume_trial(phone, otp(auth, phone), invite['code'])


def test_full_phone_only_ops_and_duplicate_issue_atomic(env):
    admin, appdb, ops, auth, phone, invite = env
    from pilot.ops_store import OpsError
    assert next(x for x in ops.users() if x['user_id'] == invite['user_id'])['phone'] == phone
    with pytest.raises(OpsError):
        ops.issue(phone, '不应重复创建')
    with admin.connect() as c:
        row = c.execute('SELECT phone_ciphertext,code_hash FROM pilot_trial_accounts WHERE user_id=%s', (invite['user_id'],)).fetchone()
        assert phone.encode() not in bytes(row[0]) and invite['code'] not in row[1]
    with appdb.connect() as c:
        assert c.execute('SELECT user_id FROM pilot_trial_accounts').fetchall() == []
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute('SELECT phone_ciphertext FROM pilot_trial_accounts')
    with pytest.raises(OpsError):
        from pilot.ops_store import OpsStore
        OpsStore(admin, phone_secret=SECRET, encryption_key=KEY)


def test_unactivated_revoked_and_expired_existing_sessions_denied(env):
    admin, appdb, ops, auth, phone, invite = env
    client = TestClient(build_app(PilotStore(appdb), auth_secret='synthetic-session'), base_url='https://pilot.example')
    client.cookies.set('pilot_session', issue_token(invite['user_id'], 'synthetic-session'))
    assert client.get('/api/ui/session').status_code == 401
    auth.consume_trial(phone, otp(auth, phone), invite['code'])
    assert client.get('/api/ui/session').status_code == 200
    ops.revoke(invite['trial_id'])
    assert client.get('/api/ui/session').status_code == 401
    with admin.connect() as c:
        c.execute("UPDATE pilot_trial_accounts SET revoked_at=NULL,expires_at=clock_timestamp()-interval '1 second' WHERE user_id=%s", (invite['user_id'],))
    assert client.get('/api/ui/session').status_code == 401


def test_http_first_activation_then_normal_sms_login(env, caplog):
    admin, appdb, ops, auth, phone, invite = env
    class SyntheticSender:
        code = None
        def send_code(self, target, code):
            self.code = code
            return True
    sender = SyntheticSender()
    client = TestClient(build_app(PilotStore(appdb), auth_secret='synthetic-session', phone_auth=auth, sms_sender=sender), base_url='https://pilot.example')
    assert client.post('/api/ui/auth/sms-code', json={'phone': phone}).status_code == 200
    response = client.post('/api/ui/auth/sms-session', json={'phone':phone,'code':sender.code,'trial_code':invite['code']})
    assert response.status_code == 200
    assert phone not in response.text and invite['code'] not in response.text
    assert 'HttpOnly' in response.headers['set-cookie']
    assert client.get('/api/ui/profiles').status_code == 200
    assert client.delete('/api/ui/session').status_code == 200
    with admin.connect() as c:
        c.execute("UPDATE pilot_phone_challenges SET created_at=clock_timestamp()-interval '61 seconds' WHERE phone_hash=%s", (auth._phone(phone),))
    assert client.post('/api/ui/auth/sms-code', json={'phone':phone}).status_code == 200
    assert client.post('/api/ui/auth/sms-session', json={'phone':phone,'code':sender.code}).status_code == 200
    assert phone not in caplog.text and invite['code'] not in caplog.text


def test_ops_login_csrf_full_phone_logout_and_revoke(env):
    _, _, ops, _, phone, invite = env
    from pilot.ops_web import build_ops_app
    client = TestClient(build_ops_app(ops, password='synthetic-operator-password', origin='https://ops.example'), base_url='https://ops.example', follow_redirects=False)
    assert client.get('/ops/users').status_code == 303
    assert client.post('/ops/login', data={'password':'synthetic-operator-password'}).status_code == 403
    headers={'Origin':'https://ops.example'}
    assert client.post('/ops/login', data={'password':'wrong'}, headers=headers).status_code == 401
    response = client.post('/ops/login', data={'password':'synthetic-operator-password'}, headers=headers)
    assert response.status_code == 303
    cookie = client.cookies.get('yike_ops_session')
    page = client.get('/ops/users')
    assert phone in page.text and 'no-store' in page.headers['cache-control']
    assert client.post('/ops/revoke', data={'trial_id':invite['trial_id']}, headers=headers).status_code == 403
    import re
    csrf = re.search('name="csrf" value="([^"]+)"', page.text)[1]
    assert client.post('/ops/revoke', data={'trial_id':invite['trial_id'],'csrf':csrf}, headers=headers).status_code == 303
    assert client.post('/ops/logout', data={'csrf':csrf}, headers=headers).status_code == 303
    client.cookies.set('yike_ops_session', cookie)
    assert client.get('/ops/users').status_code == 303


def test_ops_and_trial_implementation_exists():
    assert importlib.util.find_spec('pilot.trials') is not None
    assert importlib.util.find_spec('pilot.ops_store') is not None
    assert importlib.util.find_spec('pilot.ops_web') is not None


def test_ops_http_issue_and_one_time_secret_display(env, caplog):
    _, _, ops, _, phone, _ = env
    from pilot.ops_web import build_ops_app
    import re
    client = TestClient(build_ops_app(ops,password='synthetic-operator-password',origin='https://ops.example'),base_url='https://ops.example')
    headers={'Origin':'https://ops.example'}
    client.post('/ops/login',data={'password':'synthetic-operator-password'},headers=headers)
    form=client.get('/ops/trials')
    assert 'value="3"' in form.text
    csrf=re.search('name="csrf" value="([^"]+)"',form.text)[1]
    new_phone='177'+phone[3:]
    response=client.post('/ops/trials',data={'phone':new_phone,'name':'<script>测试</script>','csrf':csrf},headers=headers)
    assert response.status_code == 200
    code=re.search(r'YK-[A-Za-z0-9_-]{32}',response.text)[0]
    assert new_phone in response.text
    listed=client.get('/ops/users').text
    assert code not in listed and '&lt;script&gt;' in listed and '<script>测试' not in listed
    assert code not in caplog.text and new_phone not in caplog.text
    duplicate=client.post('/ops/trials',data={'phone':new_phone,'name':'重复','csrf':csrf},headers=headers)
    assert duplicate.status_code == 400
    assert '不能重复' in duplicate.text


def test_unknown_or_invalid_ops_requests_fail_closed(env):
    _, _, ops, _, _, _ = env
    from pilot.ops_web import build_ops_app
    client=TestClient(build_ops_app(ops,password='synthetic-operator-password',origin='https://ops.example'),base_url='https://ops.example')
    assert client.get('/ops/login',headers={'Host':'evil.example'}).status_code == 400
    response=client.post('/ops/login',content='x',headers={'Origin':'https://ops.example','Content-Length':'broken'})
    assert response.status_code == 400
    for _ in range(10):
        client.post('/ops/login',data={'password':'bad'},headers={'Origin':'https://ops.example'})
    assert client.post('/ops/login',data={'password':'synthetic-operator-password'},headers={'Origin':'https://ops.example'}).status_code == 429


def test_reissue_unactivated_code_without_duplicate_user(env):
    _, _, ops, auth, phone, invite = env
    from pilot.ops_store import OpsError
    replacement=ops.reissue(invite['trial_id'])
    assert replacement['user_id'] == invite['user_id'] and replacement['code'] != invite['code']
    code=otp(auth,phone)
    with pytest.raises(PhoneAuthError):
        auth.consume_trial(phone,code,invite['code'])
    auth.consume_trial(phone,code,replacement['code'])
    with pytest.raises(OpsError):
        ops.reissue(invite['trial_id'])


def test_concurrent_activation_consumes_one_sms_once(env):
    from concurrent.futures import ThreadPoolExecutor
    _, appdb, _, auth, phone, invite=env
    code=otp(auth,phone)
    def activate(_):
        from pilot.trials import TrialPhoneAuthStore
        try:
            return TrialPhoneAuthStore(appdb,SECRET).consume_trial(phone,code,invite['code'])
        except PhoneAuthError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(activate,range(2)))
    assert results.count(invite['user_id']) == 1 and results.count(None) == 1


def test_runtime_sender_missing_stays_unavailable(env):
    _, appdb, _, _, phone, invite=env
    from pilot.runtime import build_runtime_app
    app=build_runtime_app(appdb,auth_secret='synthetic-session',environment={'YIKE_PILOT_PHONE_AUTH_SECRET':SECRET.decode()})
    client=TestClient(app,base_url='https://pilot.example')
    assert client.post('/api/ui/auth/sms-code',json={'phone':phone}).status_code == 501
    assert client.post('/api/ui/auth/sms-session',json={'phone':phone,'code':'123456','trial_code':invite['code']}).status_code == 501


@pytest.mark.parametrize('name',['YIKE_OPS_DATABASE_URL','YIKE_OPS_PHONE_ENCRYPTION_KEY','YIKE_OPS_PASSWORD'])
def test_ops_credentials_forbidden_in_customer_runtime(name):
    from pilot.runtime import build_runtime_app
    with pytest.raises(RuntimeError,match='ops_credentials_forbidden'):
        build_runtime_app(None,auth_secret='synthetic-session',environment={name:'synthetic-secret'})
