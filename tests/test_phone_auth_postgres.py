"""Synthetic isolated PostgreSQL evidence, not SMS/provider evidence."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path

import pytest

from pilot.db import PilotDatabase
from pilot.store import PilotStore


@pytest.fixture
def env():
    from pilot.phone_auth import PhoneAuthStore
    urls = [os.environ.get(k) for k in ('YIKE_IDENTITY_TEST_DATABASE_URL', 'YIKE_IDENTITY_TEST_APP_DATABASE_URL')]
    if not all(urls):
        pytest.skip('dedicated phone auth PostgreSQL required')
    admin, app = map(PilotDatabase, urls)
    admin.migrate()
    admin.migrate()
    with admin.connect() as c:
        c.execute("SELECT set_config('yike.app_role','identity_app',true)")
        c.execute(Path('deploy/grant_phone_login.sql').read_text())
        c.execute('TRUNCATE pilot_phone_rates, pilot_phone_challenges, pilot_phone_bindings')
    store = PilotStore(admin)
    user = store.provision_user(store.provision_tenant('phone-synthetic'), 'phone@example.invalid')
    trusted = PhoneAuthStore(admin, b'x' * 32)
    trusted.bind_user('13800000000', user)
    return admin, app, trusted, PhoneAuthStore(app, b'x' * 32), user


def age(admin):
    with admin.connect() as c:
        c.execute("UPDATE pilot_phone_challenges SET created_at=clock_timestamp()-interval '61 seconds'")


def test_acl_binding_and_no_context(env):
    from pilot.phone_auth import PhoneAuthError
    admin, app, trusted, store, user = env
    trusted.bind_user('13800000000', user)
    with pytest.raises(PhoneAuthError):
        trusted.bind_user('13800000001', user)
    with pytest.raises(PhoneAuthError):
        store.bind_user('13800000000', user)
    store.reserve('13800000000', 'peer')
    with app.connect() as c:
        for table in ('pilot_phone_bindings', 'pilot_phone_challenges', 'pilot_phone_rates'):
            assert c.execute('SELECT count(*) FROM ' + table).fetchone()[0] == 0
        assert not c.execute("SELECT has_table_privilege(current_user,'pilot_phone_bindings','INSERT')").fetchone()[0]
        assert not c.execute("SELECT has_table_privilege(current_user,'pilot_phone_bindings','UPDATE')").fetchone()[0]
        assert c.execute('SELECT count(*) FROM pilot_users').fetchone()[0] == 0
    other = PilotStore(admin).provision_user(PilotStore(admin).provision_tenant('other'), 'other@example.invalid')
    with pytest.raises(PhoneAuthError):
        trusted.bind_user('13800000000', other)


def test_digest_cooldown_and_unknown(env):
    from pilot.phone_auth import PhoneAuthError, PhoneAuthStore
    admin, app, _, store, _ = env
    r = store.reserve('13800000000', '127.0.0.1')
    assert r.eligible
    assert r.code not in repr(r)
    with pytest.raises(PhoneAuthError, match='auth_rate_limited'):
        PhoneAuthStore(app, b'x'*32).reserve('13800000000', '127.0.0.2')
    unknown = store.reserve('13800000001', '127.0.0.1')
    assert not unknown.eligible
    with admin.connect() as c:
        value = str(c.execute('SELECT * FROM pilot_phone_challenges').fetchall())
        assert '13800000000' not in value and r.code not in value and '127.0.0.1' not in value


def test_failure_count_and_single_consumption(env):
    from pilot.phone_auth import PhoneAuthError, PhoneAuthStore
    _, app, _, store, user = env
    r = store.reserve('13800000000', 'peer')
    store.settle('13800000000', r.challenge_id, 'ACCEPTED')
    bad = '000000' if r.code != '000000' else '999999'
    for _ in range(5):
        with pytest.raises(PhoneAuthError):
            PhoneAuthStore(app, b'x'*32).consume('13800000000', bad)
    with pytest.raises(PhoneAuthError):
        store.consume('13800000000', r.code)


def test_two_consumers_only_one(env):
    from pilot.phone_auth import PhoneAuthError
    _, _, _, store, user = env
    r = store.reserve('13800000000', 'peer')
    store.settle('13800000000', r.challenge_id, 'ACCEPTED')
    def consume():
        try:
            return store.consume('13800000000', r.code)
        except PhoneAuthError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: consume(), range(2)), key=str) == sorted([None, user], key=str)


def test_old_receipt_expiry_and_rejected(env):
    from pilot.phone_auth import PhoneAuthError
    admin, _, _, store, _ = env
    old = store.reserve('13800000000', 'peer')
    age(admin)
    new = store.reserve('13800000000', 'peer')
    store.settle('13800000000', old.challenge_id, 'ACCEPTED')
    with pytest.raises(PhoneAuthError):
        store.consume('13800000000', old.code)
    store.settle('13800000000', new.challenge_id, 'UNKNOWN')
    store.settle('13800000000', new.challenge_id, 'ACCEPTED')
    with pytest.raises(PhoneAuthError):
        store.consume('13800000000', new.code)
    age(admin)
    last = store.reserve('13800000000', 'peer')
    store.settle('13800000000', last.challenge_id, 'ACCEPTED')
    with admin.connect() as c:
        c.execute("UPDATE pilot_phone_challenges SET expires_at=clock_timestamp()-interval '1 second'")
    with pytest.raises(PhoneAuthError):
        store.consume('13800000000', last.code)


def test_phone_peer_and_global_quota(env):
    from pilot.phone_auth import PhoneAuthError
    admin, _, _, store, _ = env
    for _ in range(3):
        store.reserve('13800000000', 'peer')
        age(admin)
    with pytest.raises(PhoneAuthError, match='auth_rate_limited'):
        store.reserve('13800000000', 'other')
    for i in range(7):
        store.reserve(f'139{i:08d}', 'peer')
    with pytest.raises(PhoneAuthError, match='auth_rate_limited'):
        store.reserve('13700000000', 'peer')
    for i in range(90):
        store.reserve(f'136{i:08d}', f'peer-{i}')
    with pytest.raises(PhoneAuthError, match='auth_rate_limited'):
        store.reserve('13700000000', 'new-peer')


def test_concurrent_reservations_share_cooldown(env):
    from pilot.phone_auth import PhoneAuthError
    _, _, _, store, _ = env
    def reserve(i):
        try:
            return store.reserve('13800000000', f'peer-{i}').challenge_id
        except PhoneAuthError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, range(2)))
    assert results.count('auth_rate_limited') == 1


def test_sql_exception_is_sanitized(env):
    from pilot.phone_auth import PhoneAuthError
    _, _, trusted, _, _ = env
    with pytest.raises(PhoneAuthError) as error:
        trusted.bind_user('13800000001', 'sensitive-nonexistent-user')
    assert str(error.value) == 'phone_auth_failed'
    assert error.value.__suppress_context__


def test_rejected_never_consumable(env):
    from pilot.phone_auth import PhoneAuthError
    admin, _, _, store, _ = env
    r = store.reserve('13800000000', 'peer')
    store.settle('13800000000', r.challenge_id, 'REJECTED')
    store.settle('13800000000', r.challenge_id, 'ACCEPTED')
    with pytest.raises(PhoneAuthError):
        store.consume('13800000000', r.code)


def test_expiry_is_rechecked_after_waiting_for_row_lock(env):
    from pilot.phone_auth import PhoneAuthError
    admin, _, _, store, _ = env
    r = store.reserve('13800000000', 'peer')
    store.settle('13800000000', r.challenge_id, 'ACCEPTED')
    with admin.connect() as c:
        c.execute("UPDATE pilot_phone_challenges SET expires_at=clock_timestamp()+interval '1 second'")
    with ThreadPoolExecutor(max_workers=1) as pool:
        with admin.connect() as blocker:
            blocker.execute('SELECT * FROM pilot_phone_challenges FOR UPDATE')
            result = pool.submit(store.consume, '13800000000', r.code)
            blocker.execute('SELECT pg_sleep(1.2)')
        with pytest.raises(PhoneAuthError):
            result.result(timeout=5)


def test_expired_pending_cannot_be_accepted(env):
    from pilot.phone_auth import PhoneAuthError
    admin, _, _, store, _ = env
    r = store.reserve('13800000000', 'peer')
    with admin.connect() as c:
        c.execute("UPDATE pilot_phone_challenges SET expires_at=clock_timestamp()-interval '1 second'")
    store.settle('13800000000', r.challenge_id, 'ACCEPTED')
    with pytest.raises(PhoneAuthError):
        store.consume('13800000000', r.code)
