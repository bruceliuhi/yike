"""Synthetic keys, real Ed25519, real restricted-role PostgreSQL; no platform proof."""
import os
import json
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import psycopg
from psycopg import sql
from fastapi.testclient import TestClient
from nacl.signing import SigningKey

from pilot.auth import issue_token, verify_token_claims
from pilot.db import PilotDatabase
from pilot.device_credentials import DeviceCredentialStore
from pilot.device_keys import ChallengeRequest, CompletionProof, DeviceKeyError
from pilot.store import PilotStore
from pilot.web import build_app
from tests.test_device_keys import encoded

SECRET = "synthetic-device-test-secret"


@pytest.fixture(scope="module")
def databases():
    admin_url = os.environ.get("YIKE_IDENTITY_TEST_DATABASE_URL")
    app_url = os.environ.get("YIKE_IDENTITY_TEST_APP_DATABASE_URL")
    if not admin_url or not app_url:
        pytest.skip("dedicated identity PostgreSQL required")
    admin, app = PilotDatabase(admin_url), PilotDatabase(app_url)
    admin.migrate()
    admin.migrate()
    with app.connect() as conn:
        role = conn.execute("SELECT current_user").fetchone()[0]
    with admin.connect() as conn:
        conn.execute("SELECT set_config('yike.app_role', %s, true)", (role,))
        grants = (Path(__file__).parents[1] / "deploy/grant_device_credentials.sql").read_text()
        conn.execute(grants)
        conn.execute(grants)
    return admin, app


@pytest.fixture
def env(databases):
    admin, database = databases
    provisioner = PilotStore(admin)
    tenants = [provisioner.provision_tenant("synthetic-device") for _ in range(2)]
    users = [provisioner.provision_user(tenant, f"{uuid4()}@example.invalid")
             for tenant in (tenants[0], tenants[0], tenants[1])]
    store = PilotStore(database)
    token = issue_token(users[0], SECRET)
    claims = verify_token_claims(token, SECRET)
    device = store.register_device(users[0], "synthetic-device")["device_id"]
    yield SimpleNamespace(admin=admin, database=database, store=store, tenants=tenants,
                          users=users, claims=claims, token=token, device=device,
                          service=DeviceCredentialStore(database))
    with admin.connect() as conn:
        for table in ("pilot_device_key_requests", "pilot_device_credentials", "pilot_devices",
                      "pilot_session_revocations", "pilot_users", "pilot_tenants"):
            conn.execute(f"DELETE FROM {table} WHERE tenant_id=ANY(%s)", (tenants,))


def challenge(env, operation="BIND", version=0, key=None, **overrides):
    return env.service.create_challenge(env.claims, env.device, ChallengeRequest(**(
        dict(request_id=str(uuid4()), operation=operation, expected_credential_version=version,
             public_key=encoded(key.verify_key.encode()) if key else None) | overrides)))


def complete(env, item, key, previous=None):
    message = item["signing_payload"].encode()
    return env.service.complete_challenge(env.claims, env.device, item["challenge_id"],
        CompletionProof(signature=encoded(key.sign(message).signature),
                        previous_signature=encoded(previous.sign(message).signature) if previous else None))


def bind(env, key):
    return complete(env, challenge(env, key=key), key)


def test_bind_prove_rotate_and_stale_key_consumption(env):
    old, new = [SigningKey.generate() for _ in range(2)]
    assert bind(env, old)["credential_version"] == 1
    assert complete(env, challenge(env, "PROVE", 1), old)["credential_version"] == 1
    pending = challenge(env, "PROVE", 1)
    rotation = challenge(env, "ROTATE", 1, new)
    assert complete(env, rotation, new, old)["credential_version"] == 2
    with pytest.raises(DeviceKeyError, match="credential_conflict"):
        complete(env, pending, old)
    assert env.service.get_receipt(env.claims, pending["request_id"])["state"] == "REJECTED"
    assert complete(env, challenge(env, "PROVE", 2), new)["state"] == "SUCCEEDED"


def test_idempotency_restart_and_history_after_revoke(env):
    key = SigningKey.generate()
    item = challenge(env, key=key)
    assert challenge(env, key=key, request_id=item["request_id"]) == item
    result = complete(env, item, key)
    env.service = DeviceCredentialStore(env.database)
    assert complete(env, item, key) == result
    env.store.revoke_device(env.users[0], env.device)
    assert env.service.get_receipt(env.claims, item["request_id"]) == result
    assert complete(env, item, key) == result


@pytest.mark.parametrize("user_index", [1, 2])
def test_stranger_cannot_bind_or_query(env, user_index):
    item = challenge(env, key=SigningKey.generate())
    env.claims = verify_token_claims(issue_token(env.users[user_index], SECRET), SECRET)
    with pytest.raises(DeviceKeyError, match="device_unavailable"):
        challenge(env, key=SigningKey.generate())
    with pytest.raises(DeviceKeyError, match="request_not_found"):
        env.service.get_receipt(env.claims, item["request_id"])


def test_registration_owner_and_historical_null_owner(env):
    with env.admin.connect() as conn:
        assert conn.execute("SELECT owner_user_id FROM pilot_devices WHERE device_id=%s",
                            (env.device,)).fetchone() == (env.users[0],)
        conn.execute("UPDATE pilot_devices SET owner_user_id=NULL WHERE device_id=%s", (env.device,))
    with pytest.raises(DeviceKeyError, match="device_unavailable"):
        challenge(env, key=SigningKey.generate())


def test_wrong_signature_consumes_and_new_session_cannot_complete(env):
    key, wrong = [SigningKey.generate() for _ in range(2)]
    item = challenge(env, key=key)
    with pytest.raises(DeviceKeyError, match="invalid_proof"):
        complete(env, item, wrong)
    assert env.service.get_receipt(env.claims, item["request_id"])["state"] == "REJECTED"
    with pytest.raises(DeviceKeyError):
        complete(env, item, key)
    item = challenge(env, key=key)
    env.claims = verify_token_claims(issue_token(env.users[0], SECRET), SECRET)
    with pytest.raises(DeviceKeyError, match="invalid_proof"):
        complete(env, item, key)


def test_expiry_conflict_and_limit(env):
    key = SigningKey.generate()
    item = challenge(env, key=key)
    with pytest.raises(DeviceKeyError, match="request_conflict"):
        challenge(env, key=SigningKey.generate(), request_id=item["request_id"])
    for _ in range(4):
        challenge(env, key=key)
    assert challenge(env, key=key, request_id=item["request_id"]) == item
    with pytest.raises(DeviceKeyError, match="challenge_limit"):
        challenge(env, key=key)
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_device_key_requests SET expires_at=clock_timestamp()-interval '1 second' "
                     "WHERE request_id=%s", (item["request_id"],))
    with pytest.raises(DeviceKeyError, match="challenge_expired"):
        complete(env, item, key)
    assert env.service.get_receipt(env.claims, item["request_id"])["state"] == "EXPIRED"
    challenge(env, key=key)


def test_exact_signing_bytes_and_no_private_material_persisted(env):
    key = SigningKey.generate()
    item = challenge(env, key=key)
    payload = json.loads(item["signing_payload"])
    assert item["signing_payload"] == json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert payload.keys() == {"protocol", "tenant_id", "user_id", "device_id", "request_id", "challenge_id",
                              "session_digest", "operation", "expected_credential_version", "target_public_key", "nonce", "expires_at"}
    assert payload["protocol"] == "yike-device-proof-v1"
    assert payload["session_digest"] == env.claims.revocation_key
    assert len(payload["nonce"]) == 43
    signature = encoded(key.sign(item["signing_payload"].encode()).signature)
    complete(env, item, key)
    with env.admin.connect() as conn:
        row = conn.execute("SELECT row_to_json(r)::text FROM pilot_device_key_requests r WHERE request_id=%s",
                           (item["request_id"],)).fetchone()[0]
    for secret in (signature, env.token, encoded(key.encode())):
        assert secret not in row


def test_rotation_requires_both_keys_and_wrong_payload_consumes(env):
    old, new = [SigningKey.generate() for _ in range(2)]
    bind(env, old)
    for previous in (None, new):
        item = challenge(env, "ROTATE", 1, new)
        with pytest.raises(DeviceKeyError, match="invalid_proof"):
            complete(env, item, new, previous)
        assert env.service.get_receipt(env.claims, item["request_id"])["state"] == "REJECTED"
    with pytest.raises(DeviceKeyError, match="credential_conflict"):
        challenge(env, "ROTATE", 1, old)
    item = challenge(env, "PROVE", 1)
    proof = CompletionProof(signature=encoded(old.sign(b"not server payload").signature))
    with pytest.raises(DeviceKeyError, match="invalid_proof"):
        env.service.complete_challenge(env.claims, env.device, item["challenge_id"], proof)
    assert complete(env, challenge(env, "PROVE", 1), old)["credential_version"] == 1


def test_http_session_origin_https_strict_body_and_no_store(env):
    key = SigningKey.generate()
    body = dict(request_id=str(uuid4()), operation="BIND", expected_credential_version=0,
                public_key=encoded(key.verify_key.encode()))
    path = f"/api/ui/devices/{env.device}/key-challenges"
    headers = {"Authorization": "Bearer " + env.token}
    app = build_app(env.store, auth_secret=SECRET)
    with TestClient(app, base_url="https://testserver") as client:
        assert client.post(path, json=body).status_code == 401
        assert client.post(path, json=body, headers=headers | {"Origin": "https://foreign.invalid"}).status_code == 403
        for bad in (body | {"extra": env.token}, body | {"expected_credential_version": True},
                    body | {"public_key": body["public_key"] + "="}):
            response = client.post(path, json=bad, headers=headers)
            assert response.status_code == 422
            assert response.json()["detail"]["code"] == "invalid_request"
            assert env.token not in response.text and body["public_key"] not in response.text
            assert response.headers["cache-control"] == "no-store"
        foreign = {"Authorization": "Bearer " + issue_token(env.users[1], SECRET)}
        assert client.post(path, json=body, headers=foreign).status_code == 404
        response = client.post(path, json=body, headers=headers)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        item = response.json()
        signature = encoded(key.sign(item["signing_payload"].encode()).signature)
        response = client.post(path + f'/{item["challenge_id"]}/complete',
                               json={"signature": signature}, headers=headers)
        assert response.status_code == 200
        assert signature not in response.text and body["public_key"] not in response.text
        receipt_path = f'/api/ui/device-key-requests/{body["request_id"]}'
        assert client.get(receipt_path, headers=headers).json()["state"] == "SUCCEEDED"
        client.delete("/api/ui/session", headers=headers)
        assert client.get(receipt_path, headers=headers).status_code == 401
        assert client.post(path, json=body, headers=headers).status_code == 401
    with TestClient(app, base_url="http://testserver") as client:
        response = client.post(path, json=body, headers=headers)
        assert response.status_code == 400
        assert response.headers["cache-control"] == "no-store"


def wait_for_lock(admin, query_fragment, count=1):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        with admin.connect() as conn:
            rows = conn.execute("SELECT pid,wait_event,query FROM pg_stat_activity WHERE datname=current_database() "
                                "AND wait_event_type='Lock' AND query LIKE %s",
                                ("%" + query_fragment + "%",)).fetchall()
        if len(rows) >= count:
            assert all(row[1] in ("advisory", "transactionid", "tuple") for row in rows)
            return rows
        time.sleep(0.01)
    pytest.fail(f"no PostgreSQL lock-wait evidence for {query_fragment}")


def test_logout_wins_lock_and_denies_pending_completion(env):
    key = SigningKey.generate()
    item = challenge(env, key=key)
    with ThreadPoolExecutor(1) as pool:
        with env.admin.connect() as blocker:
            env.store.sessions.lock_session(blocker.cursor(), env.claims)
            future = pool.submit(complete, env, item, key)
            wait_for_lock(env.admin, "pg_advisory_xact_lock")
            blocker.execute("INSERT INTO pilot_session_revocations(tenant_id,user_id,revocation_key,expires_at) "
                            "VALUES (%s,%s,%s,to_timestamp(%s))",
                            (env.tenants[0], env.users[0], env.claims.revocation_key, env.claims.expires_at))
        with pytest.raises(DeviceKeyError, match="invalid_session"):
            future.result(timeout=5)
    with env.admin.connect() as conn:
        assert conn.execute("SELECT count(*) FROM pilot_device_credentials WHERE device_id=%s", (env.device,)).fetchone()[0] == 0


def test_completion_wins_session_lock_then_logout_preserves_history(env):
    key = SigningKey.generate()
    item = challenge(env, key=key)
    with ThreadPoolExecutor(2) as pool:
        with env.admin.connect() as blocker:
            blocker.execute("SELECT 1 FROM pilot_devices WHERE device_id=%s FOR UPDATE", (env.device,))
            completed = pool.submit(complete, env, item, key)
            wait_for_lock(env.admin, "owner_user_id=")
            logout = pool.submit(env.store.sessions.revoke, [env.claims])
            wait_for_lock(env.admin, "pg_advisory_xact_lock")
        result = completed.result(timeout=5)
        logout.result(timeout=5)
    with pytest.raises(DeviceKeyError, match="invalid_session"):
        challenge(env, "PROVE", 1)
    env.claims = verify_token_claims(issue_token(env.users[0], SECRET), SECRET)
    assert env.service.get_receipt(env.claims, item["request_id"]) == result


def test_device_revoke_wins_lock(env):
    key = SigningKey.generate()
    item = challenge(env, key=key)
    with ThreadPoolExecutor(1) as pool:
        with env.admin.connect() as blocker:
            blocker.execute("UPDATE pilot_devices SET status='REVOKED' WHERE device_id=%s", (env.device,))
            future = pool.submit(complete, env, item, key)
            wait_for_lock(env.admin, "owner_user_id=")
        with pytest.raises(DeviceKeyError, match="device_unavailable"):
            future.result(timeout=5)


@pytest.mark.parametrize("expiry", ["challenge", "session"])
def test_expiry_rechecked_after_lock_wait(env, expiry):
    key = SigningKey.generate()
    item = challenge(env, key=key)
    deadline = int(time.time()) + 2
    if expiry == "session":
        from dataclasses import replace
        env.claims = replace(env.claims, expires_at=deadline)
    else:
        with env.admin.connect() as conn:
            conn.execute("UPDATE pilot_device_key_requests SET expires_at=to_timestamp(%s) WHERE request_id=%s",
                         (deadline, item["request_id"]))
    with ThreadPoolExecutor(1) as pool:
        with env.admin.connect() as blocker:
            blocker.execute("SELECT 1 FROM pilot_devices WHERE device_id=%s FOR UPDATE", (env.device,))
            future = pool.submit(complete, env, item, key)
            wait_for_lock(env.admin, "owner_user_id=")
            while time.time() <= deadline:
                time.sleep(0.01)
        with pytest.raises(DeviceKeyError, match="invalid_session" if expiry == "session" else "challenge_expired"):
            future.result(timeout=5)


@pytest.mark.parametrize("rotation", [False, True])
@pytest.mark.parametrize("same_request", [False, True])
def test_duplicate_bind_and_rotate_races(env, rotation, same_request):
    old, key = [SigningKey.generate() for _ in range(2)]
    if rotation:
        bind(env, old)
    item = challenge(env, "ROTATE" if rotation else "BIND", 1 if rotation else 0, key)
    second = item if same_request else challenge(env, "ROTATE" if rotation else "BIND", 1 if rotation else 0, key)
    with ThreadPoolExecutor(2) as pool:
        with env.admin.connect() as blocker:
            blocker.execute("SELECT 1 FROM pilot_devices WHERE device_id=%s FOR UPDATE", (env.device,))
            first = pool.submit(complete, env, item, key, old if rotation else None)
            wait_for_lock(env.admin, "owner_user_id=")
            other = pool.submit(complete, env, second, key, old if rotation else None)
            wait_for_lock(env.admin, "pg_advisory_xact_lock")
        assert first.result(timeout=5)["credential_version"] == (2 if rotation else 1)
        if same_request:
            assert other.result(timeout=5) == first.result()
        else:
            with pytest.raises(DeviceKeyError, match="credential_conflict"):
                other.result(timeout=5)


class RoleDatabase(PilotDatabase):
    def __init__(self, admin, role):
        super().__init__(admin.url)
        self.role = role

    @contextmanager
    def connect(self):
        with super().connect() as conn:
            conn.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(self.role)))
            yield conn


def test_restricted_upgrade_rls_and_composite_fk(env):
    role = "device_upgrade_" + uuid4().hex
    grant_path = Path(__file__).parents[1] / "deploy"
    try:
        with env.admin.connect() as conn:
            conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE").format(sql.Identifier(role)))
            conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
            conn.execute(sql.SQL("GRANT SELECT ON pilot_users TO {}").format(sql.Identifier(role)))
            conn.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
            conn.execute((grant_path / "grant_session_revocations.sql").read_text())
        restricted = RoleDatabase(env.admin, role)
        with restricted.connect() as conn:
            assert not conn.execute("SELECT has_table_privilege(current_user,'pilot_device_credentials','INSERT')").fetchone()[0]
        with env.admin.connect() as conn:
            conn.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
            for _ in range(2):
                conn.execute((grant_path / "grant_device_credentials.sql").read_text())
        with restricted.connect() as conn:
            assert conn.execute("SELECT rolsuper,rolbypassrls,rolcreaterole FROM pg_roles WHERE rolname=current_user").fetchone() == (False, False, False)
            assert not conn.execute("SELECT has_schema_privilege(current_user,'public','CREATE')").fetchone()[0]
            assert not conn.execute("SELECT has_table_privilege(current_user,'pilot_users','UPDATE')").fetchone()[0]
            for table in ("pilot_device_credentials", "pilot_device_key_requests"):
                assert not conn.execute("SELECT has_table_privilege(current_user,%s,'DELETE')", (table,)).fetchone()[0]
                assert conn.execute("SELECT row_security_active(%s::regclass)", (table,)).fetchone()[0]
        env.service = DeviceCredentialStore(restricted)
        key = SigningKey.generate()
        assert bind(env, key)["state"] == "SUCCEEDED"
        for tenant, user in ((None, None), (env.tenants[0], None), (None, env.users[0]),
                             (env.tenants[0], env.users[1]), (env.tenants[1], env.users[0])):
            with restricted.connect() as conn:
                if tenant:
                    conn.execute("SELECT set_config('yike.tenant_id',%s,true)", (tenant,))
                if user:
                    conn.execute("SELECT set_config('yike.user_id',%s,true)", (user,))
                for table in ("pilot_device_credentials", "pilot_device_key_requests"):
                    assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
                    assert conn.execute(f"UPDATE {table} SET owner_user_id=owner_user_id").rowcount == 0
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            with env.admin.connect() as conn:
                conn.execute("UPDATE pilot_device_credentials SET owner_user_id=%s WHERE device_id=%s",
                             (env.users[1], env.device))
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            with env.admin.connect() as conn:
                conn.execute("UPDATE pilot_device_key_requests SET owner_user_id=%s WHERE device_id=%s",
                             (env.users[1], env.device))
    finally:
        with env.admin.connect() as conn:
            conn.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_completion_wins_device_lock_then_revoke_preserves_receipt(env):
    key = SigningKey.generate()
    bind(env, key)
    item = challenge(env, "PROVE", 1)
    with ThreadPoolExecutor(2) as pool:
        with env.admin.connect() as blocker:
            blocker.execute("SELECT 1 FROM pilot_device_credentials WHERE device_id=%s FOR UPDATE", (env.device,))
            proof = pool.submit(complete, env, item, key)
            wait_for_lock(env.admin, "SELECT public_key,credential_version")
            revoke = pool.submit(env.store.revoke_device, env.users[0], env.device)
            wait_for_lock(env.admin, "UPDATE pilot_devices")
        result = proof.result(timeout=5)
        assert revoke.result(timeout=5)
    assert env.service.get_receipt(env.claims, item["request_id"]) == result


def test_unknown_and_substituted_device_are_not_failed_receipts(env):
    key = SigningKey.generate()
    item = challenge(env, key=key)
    assert env.service.get_receipt(env.claims, item["request_id"])["state"] == "PENDING"
    with pytest.raises(DeviceKeyError, match="request_not_found"):
        env.service.get_receipt(env.claims, str(uuid4()))
    other_device = env.store.register_device(env.users[0], "other synthetic")["device_id"]
    proof = CompletionProof(signature=encoded(key.sign(item["signing_payload"].encode()).signature))
    with pytest.raises(DeviceKeyError, match="request_not_found"):
        env.service.complete_challenge(env.claims, other_device, item["challenge_id"], proof)
    assert complete(env, item, key)["state"] == "SUCCEEDED"


@pytest.mark.parametrize("target", ["", "missing_device_role", "postgres"])
def test_new_grant_rejects_invalid_role(databases, target):
    admin, _ = databases
    with pytest.raises(psycopg.errors.RaiseException, match="restricted application role"):
        with admin.connect() as conn:
            conn.execute("SELECT set_config('yike.app_role',%s,true)", (target,))
            conn.execute((Path(__file__).parents[1] / "deploy/grant_device_credentials.sql").read_text())


def test_new_grant_rejects_owner(databases):
    admin, _ = databases
    role = "device_owner_" + uuid4().hex
    with pytest.raises(psycopg.errors.RaiseException, match="must not own"):
        with admin.connect() as conn:
            conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS").format(sql.Identifier(role)))
            conn.execute(sql.SQL("ALTER TABLE pilot_device_credentials OWNER TO {}").format(sql.Identifier(role)))
            conn.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
            conn.execute((Path(__file__).parents[1] / "deploy/grant_device_credentials.sql").read_text())


def test_historical_replay_rechecks_expiry_after_request_wait(env):
    from dataclasses import replace
    key = SigningKey.generate()
    item = challenge(env, key=key)
    complete(env, item, key)
    deadline = int(time.time()) + 2
    env.claims = replace(env.claims, expires_at=deadline)
    with ThreadPoolExecutor(1) as pool:
        with env.admin.connect() as blocker:
            blocker.execute("SELECT 1 FROM pilot_device_key_requests WHERE request_id=%s FOR UPDATE", (item["request_id"],))
            future = pool.submit(complete, env, item, key)
            wait_for_lock(env.admin, "challenge_id=")
            while time.time() <= deadline:
                time.sleep(0.01)
        with pytest.raises(DeviceKeyError, match="invalid_session"):
            future.result(timeout=5)


def test_fresh_105_upgrade_twice_and_explicit_restricted_grants(databases):
    from urllib.parse import urlsplit, urlunsplit
    admin, _ = databases
    database_name = "device_upgrade_" + uuid4().hex
    role = "device_fresh_" + uuid4().hex
    parts = urlsplit(admin.url)
    fresh = PilotDatabase(urlunsplit(parts._replace(path="/" + database_name)))
    created = False
    try:
        with admin.connect() as conn:
            conn.autocommit = True
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
            created = True
        fresh.migration_paths = tuple(item for item in PilotDatabase.migration_paths
                                      if item[0] not in ("v02-device-credentials", "v02-connection-versions"))
        fresh.migrate()
        with fresh.connect() as conn:
            assert not conn.execute("SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='pilot_devices' AND column_name='owner_user_id')").fetchone()[0]
            conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE").format(sql.Identifier(role)))
            conn.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
            conn.execute(sql.SQL("GRANT SELECT ON pilot_users TO {}").format(sql.Identifier(role)))
            conn.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
            conn.execute((Path(__file__).parents[1] / "deploy/grant_session_revocations.sql").read_text())
        fresh.migration_paths = PilotDatabase.migration_paths
        fresh.migrate()
        fresh.migrate()
        with fresh.connect() as conn:
            assert conn.execute("SELECT count(*) FROM pilot_schema_meta").fetchone()[0] == len(PilotDatabase.migration_paths)
            conn.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
            grant = (Path(__file__).parents[1] / "deploy/grant_device_credentials.sql").read_text()
            conn.execute(grant)
            conn.execute(grant)
        restricted = RoleDatabase(fresh, role)
        provisioner = PilotStore(fresh)
        tenant = provisioner.provision_tenant("synthetic-fresh")
        user = provisioner.provision_user(tenant, f"{uuid4()}@example.invalid")
        device = PilotStore(restricted).register_device(user, "fresh")["device_id"]
        isolated = SimpleNamespace(service=DeviceCredentialStore(restricted), device=device,
                                  claims=verify_token_claims(issue_token(user, SECRET), SECRET))
        assert bind(isolated, SigningKey.generate())["state"] == "SUCCEEDED"
        with restricted.connect() as conn:
            for table in ("pilot_users", "pilot_devices", "pilot_device_credentials", "pilot_device_key_requests"):
                assert not conn.execute("SELECT has_table_privilege(current_user,%s,'DELETE')", (table,)).fetchone()[0]
            assert not conn.execute("SELECT has_table_privilege(current_user,'pilot_users','UPDATE')").fetchone()[0]
            assert not conn.execute("SELECT has_schema_privilege(current_user,'public','CREATE')").fetchone()[0]
    finally:
        if created:
            with admin.connect() as conn:
                conn.autocommit = True
                conn.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
                if conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                    conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
