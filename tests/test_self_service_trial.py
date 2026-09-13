"""Real isolated PostgreSQL registration checks; no external SMS is sent."""
from datetime import timedelta
from uuid import uuid4
import pytest
from pilot.phone_auth import PhoneAuthError
from pilot.trials import TrialPhoneAuthStore
from tests.test_ops_trials import databases, env, SECRET, otp
from fastapi.testclient import TestClient
from pilot.web import build_app
from pilot.store import PilotStore
from tests.test_phone_api import SenderFixture


def test_new_verified_phone_gets_three_days_once(databases):
    admin, opsdb, appdb = databases
    auth = TrialPhoneAuthStore(appdb, SECRET)
    phone = '199' + str(int(uuid4().hex[:8],16)%100000000).zfill(8)
    peer=str(uuid4())
    challenge = auth.reserve(phone,peer)
    assert challenge.eligible
    with admin.connect() as c:
        assert c.execute('SELECT user_id FROM pilot_phone_bindings WHERE phone_hash=%s',(auth._phone(phone),)).fetchone() is None
    auth.settle(phone,challenge.challenge_id,'ACCEPTED')
    user = auth.consume(phone,challenge.code)
    with admin.connect() as c:
        row = c.execute('SELECT days,activated_at,expires_at,credential_kind,phone_ciphertext,code_hash FROM pilot_trial_accounts WHERE user_id=%s',(user,)).fetchone()
    assert row[0]==3 and row[2]-row[1]==timedelta(hours=72)
    assert row[3:] == ('SELF_SERVICE_SMS',None,None)
    with pytest.raises(PhoneAuthError): auth.consume(phone,challenge.code)
    with admin.connect() as c:
        c.execute("UPDATE pilot_phone_challenges SET created_at=clock_timestamp()-interval '61 seconds' WHERE phone_hash=%s",(auth._phone(phone),))
    again=auth.reserve(phone,peer)
    auth.settle(phone,again.challenge_id,'ACCEPTED')
    assert auth.consume(phone,again.code)==user
    with admin.connect() as c:
        assert c.execute('SELECT activated_at,expires_at FROM pilot_trial_accounts WHERE user_id=%s',(user,)).fetchone()==row[1:3]


def test_pending_invitation_activates_without_code_and_expiry_is_not_reset(env):
    admin, appdb, ops, auth, phone, invite = env
    assert auth.consume(phone,otp(auth,phone))==invite['user_id']
    with admin.connect() as c:
        c.execute("UPDATE pilot_trial_accounts SET expires_at=clock_timestamp()-interval '1 second' WHERE user_id=%s",(invite['user_id'],))
        c.execute("UPDATE pilot_phone_challenges SET created_at=clock_timestamp()-interval '61 seconds' WHERE phone_hash=%s",(auth._phone(phone),))
    code=otp(auth,phone)
    with pytest.raises(PhoneAuthError) as expired: auth.consume(phone,code)
    assert expired.value.code=='trial_expired'
    client=TestClient(build_app(PilotStore(appdb),auth_secret='synthetic-test-secret',phone_auth=auth,
                               sms_sender=SenderFixture()),base_url='https://pilot.example')
    response=client.post('/api/ui/auth/sms-session',json={'phone':phone,'code':code})
    assert response.status_code==403 and response.json()['detail']['code']=='trial_expired'
    with admin.connect() as c:
        assert c.execute('SELECT expires_at<clock_timestamp() FROM pilot_trial_accounts WHERE user_id=%s',(invite['user_id'],)).fetchone()[0]


def test_wrong_otp_cannot_provision_and_app_has_no_direct_creation_rights(databases):
    admin, _, appdb=databases
    auth=TrialPhoneAuthStore(appdb,SECRET)
    phone='199'+str(int(uuid4().hex[:8],16)%100000000).zfill(8)
    challenge=auth.reserve(phone,str(uuid4()))
    auth.settle(phone,challenge.challenge_id,'ACCEPTED')
    bad='000000' if challenge.code!='000000' else '000001'
    with pytest.raises(PhoneAuthError): auth.consume(phone,bad)
    with admin.connect() as c:
        assert c.execute('SELECT user_id FROM pilot_phone_bindings WHERE phone_hash=%s',(auth._phone(phone),)).fetchone() is None
    with appdb.connect() as c:
        assert not c.execute("SELECT has_table_privilege(current_user,'pilot_users','INSERT')").fetchone()[0]
        assert not c.execute("SELECT has_column_privilege(current_user,'pilot_trial_accounts','phone_ciphertext','SELECT')").fetchone()[0]
