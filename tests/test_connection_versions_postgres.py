"""Synthetic-only connection version tests against dedicated restricted PostgreSQL."""
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from pilot.auth import issue_token, verify_token_claims
from pilot.db import PilotDatabase
from pilot.store import PilotStore


@pytest.fixture(scope="module")
def databases():
    urls = [os.environ.get(name) for name in (
        "YIKE_IDENTITY_TEST_DATABASE_URL", "YIKE_IDENTITY_TEST_APP_DATABASE_URL")]
    if not all(urls):
        pytest.skip("dedicated identity PostgreSQL required")
    admin, app = map(PilotDatabase, urls)
    admin.migrate()
    grant = Path(__file__).parents[1] / "deploy/grant_connection_operations.sql"
    if grant.exists():
        with app.connect() as conn:
            role = conn.execute("SELECT current_user").fetchone()[0]
        with admin.connect() as conn:
            conn.execute("SELECT set_config('yike.app_role', %s, true)", (role,))
            conn.execute(grant.read_text())
    return admin, app


@pytest.fixture
def env(databases):
    admin, app = databases
    provisioner = PilotStore(admin)
    tenant = provisioner.provision_tenant("synthetic-connection")
    other_tenant = provisioner.provision_tenant("synthetic-connection-other")
    user = provisioner.provision_user(tenant, f"{uuid4()}@example.invalid")
    other_user = provisioner.provision_user(tenant, f"{uuid4()}@example.invalid")
    foreign_user = provisioner.provision_user(other_tenant, f"{uuid4()}@example.invalid")
    store = PilotStore(app)
    device = store.register_device(user, "synthetic")["device_id"]
    token = issue_token(user, "synthetic-connection-test-secret")
    claims = verify_token_claims(token, "synthetic-connection-test-secret")
    yield SimpleNamespace(admin=admin, database=app, store=store, tenant=tenant,
                          user=user, other_user=other_user, foreign_user=foreign_user,
                          device=device, claims=claims, token=token)
    with admin.connect() as conn:
        if conn.execute("SELECT to_regclass('pilot_connection_operations')").fetchone()[0]:
            conn.execute("DELETE FROM pilot_connection_operations WHERE tenant_id=ANY(%s)", ([tenant, other_tenant],))
        for table in ("pilot_platform_connections", "pilot_devices", "pilot_session_revocations",
                      "pilot_users", "pilot_tenants"):
            conn.execute(f"DELETE FROM {table} WHERE tenant_id=ANY(%s)", ([tenant, other_tenant],))


def test_explicit_registration_always_advances_version(env):
    first = env.store.connect_platform(env.user, "BILIBILI", env.device,
                                       "synthetic-id", "vault://synthetic")
    second = env.store.connect_platform(env.user, "BILIBILI", env.device,
                                        "synthetic-id", "vault://synthetic")
    assert first["connection_version"] == 1
    assert second["connection_id"] == first["connection_id"]
    assert second["connection_version"] == 2
    assert env.store.list_connections(env.user)[0]["connection_version"] == 2


def operation(env, **changes):
    from pilot.connection_versions import ConnectionOperation
    from tests.test_connection_versions import body
    return ConnectionOperation(**body(device_id=env.device, **changes))


def test_atomic_replay_conflict_and_expected_version(env):
    from pilot.connection_versions import ConnectionOperationStore, ConnectionOperationError
    service = ConnectionOperationStore(env.database)
    request = operation(env)
    first = service.apply(env.claims, request)
    assert first == dict(request_id=request.request_id, device_id=env.device, action="REGISTER",
                         state="SUCCEEDED", connection_id=first["connection_id"],
                         connection_version=1, connection_status="UNVERIFIED", error_code=None)
    assert service.apply(env.claims, request) == first
    with pytest.raises(ConnectionOperationError, match="request_conflict"):
        service.apply(env.claims, operation(env, request_id=request.request_id, session_ref="vault://changed"))
    rejected = service.apply(env.claims, operation(env))
    assert rejected["error_code"] == "connection_version_conflict"
    second = service.apply(env.claims, operation(env, expected_connection_version=1))
    assert second["connection_version"] == 2
    assert service.get_receipt(env.claims, request.request_id) == first
    disconnect = operation(env, action="DISCONNECT", connection_id=first["connection_id"],
                           expected_connection_version=1, platform=None, account_public_id=None, session_ref=None)
    assert service.apply(env.claims, disconnect)["state"] == "REJECTED"
    disconnected = service.apply(env.claims, disconnect.model_copy(update={
        "request_id": str(uuid4()), "expected_connection_version": 2}))
    assert disconnected["connection_version"] == 3
    assert disconnected["connection_status"] == "DISCONNECTED"
    env.store.revoke_device(env.user, env.device)
    assert ConnectionOperationStore(env.database).apply(env.claims, request) == first


def test_trigger_changes_noop_invalid_and_overflow(env):
    import psycopg
    connected = env.store.connect_platform(env.user, "BILIBILI", env.device, "synthetic-id", "vault://synthetic")
    cid = connected["connection_id"]
    with env.admin.connect() as conn:
        for field, value in (("session_ref", "vault://changed"), ("account_public_id", "changed"),
                             ("platform", "DOUYIN"), ("status", "CONNECTED")):
            before = conn.execute("SELECT connection_version FROM pilot_platform_connections WHERE connection_id=%s", (cid,)).fetchone()[0]
            conn.execute(f"UPDATE pilot_platform_connections SET {field}=%s WHERE connection_id=%s", (value, cid))
            assert conn.execute("SELECT connection_version FROM pilot_platform_connections WHERE connection_id=%s", (cid,)).fetchone()[0] == before + 1
        conn.execute("UPDATE pilot_platform_connections SET status=status WHERE connection_id=%s", (cid,))
        assert conn.execute("SELECT connection_version FROM pilot_platform_connections WHERE connection_id=%s", (cid,)).fetchone()[0] == 5
        with pytest.raises(psycopg.Error) as caught, conn.transaction():
            conn.execute("UPDATE pilot_platform_connections SET connection_version=8 WHERE connection_id=%s", (cid,))
        assert caught.value.sqlstate == "YC002"
        # Synthetic boundary setup only; trigger restored before checked writes.
        conn.execute("ALTER TABLE pilot_platform_connections DISABLE TRIGGER pilot_connection_version_guard")
        conn.execute("UPDATE pilot_platform_connections SET connection_version=2147483647 WHERE connection_id=%s", (cid,))
        conn.execute("ALTER TABLE pilot_platform_connections ENABLE TRIGGER pilot_connection_version_guard")
        with pytest.raises(psycopg.Error) as caught, conn.transaction():
            conn.execute("UPDATE pilot_platform_connections SET status='EXPIRED' WHERE connection_id=%s", (cid,))
        assert caught.value.sqlstate == "YC001"
        with pytest.raises(psycopg.errors.NumericValueOutOfRange), conn.transaction():
            conn.execute("UPDATE pilot_platform_connections SET connection_version=connection_version+1,status='EXPIRED' WHERE connection_id=%s", (cid,))
        assert conn.execute("SELECT connection_version,status FROM pilot_platform_connections WHERE connection_id=%s", (cid,)).fetchone() == (2147483647, "CONNECTED")
    from pilot.connection_versions import ConnectionOperationStore
    result = ConnectionOperationStore(env.database).apply(env.claims, operation(env,
        platform="DOUYIN", account_public_id="changed", expected_connection_version=2147483647))
    assert result["error_code"] == "connection_version_exhausted"


def test_checker_requires_current_connected_and_uses_callers_transaction(env):
    from pilot.connection_versions import ConnectionOperationStore, ConnectionOperationError
    service = ConnectionOperationStore(env.database)
    result = service.apply(env.claims, operation(env))
    def check(cursor, version):
        return service.lock_current(cursor, env.claims, device_id=env.device,
            connection_id=result["connection_id"], connection_version=version, platform="BILIBILI")
    with env.database.connect() as conn:
        with pytest.raises(ConnectionOperationError, match="connection_unavailable"), conn.transaction():
            check(conn.cursor(), 1)
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_platform_connections SET status='CONNECTED' WHERE connection_id=%s", (result["connection_id"],))
    with env.database.connect() as conn:
        safe = check(conn.cursor(), 2)
        assert safe == dict(connection_id=result["connection_id"], connection_version=2,
                            platform="BILIBILI", account_public_id="synthetic-id")
        conn.rollback()
        with pytest.raises(ConnectionOperationError, match="connection_version_conflict"), conn.transaction():
            check(conn.cursor(), 1)


@pytest.mark.parametrize("method", ["connect", "disconnect", "revoke"])
def test_legacy_mutation_rechecks_revoked_session(env, method):
    from pilot.auth import InvalidPilotToken
    item = env.store.connect_platform(env.user, "BILIBILI", env.device, "synthetic-id", "vault://synthetic")
    env.store.sessions.revoke([env.claims])
    with pytest.raises(InvalidPilotToken):
        if method == "connect":
            env.store.connect_platform(env.user, "BILIBILI", env.device, "synthetic-id", "vault://synthetic", claims=env.claims)
        elif method == "disconnect":
            env.store.disconnect_platform(env.user, item["connection_id"], claims=env.claims)
        else:
            env.store.revoke_device(env.user, env.device, claims=env.claims)


def test_legacy_registration_exhaustion_is_safe(env):
    from pilot.connection_versions import ConnectionOperationError
    item = env.store.connect_platform(env.user, "BILIBILI", env.device, "synthetic-id", "vault://synthetic")
    with env.admin.connect() as conn:
        conn.execute("ALTER TABLE pilot_platform_connections DISABLE TRIGGER pilot_connection_version_guard")
        conn.execute("UPDATE pilot_platform_connections SET connection_version=2147483647 WHERE connection_id=%s", (item["connection_id"],))
        conn.execute("ALTER TABLE pilot_platform_connections ENABLE TRIGGER pilot_connection_version_guard")
    with pytest.raises(ConnectionOperationError, match="connection_version_exhausted"):
        env.store.connect_platform(env.user, "BILIBILI", env.device, "synthetic-id", "vault://synthetic")


def test_real_http_operations_and_safe_transport(env):
    from fastapi.testclient import TestClient
    from pilot.web import build_app
    request = operation(env).model_dump()
    app = build_app(env.store, auth_secret="synthetic-connection-test-secret")
    headers = {"Authorization": "Bearer " + env.token, "Origin": "https://testserver"}
    with TestClient(app, base_url="https://testserver") as client:
        reply = client.post("/api/ui/connection-operations", json=request, headers=headers)
        assert reply.status_code == 200
        assert reply.headers["cache-control"] == "no-store"
        receipt = reply.json()
        assert receipt["connection_version"] == 1
        assert "vault" not in reply.text
        capabilities = client.get("/api/ui/capabilities").json()["capabilities"]
        for name in ("platform_connections", "task_execution", "outreach", "replies"):
            assert capabilities[name] == {"available": False}
        assert client.get("/api/ui/connection-operations/" + request["request_id"], headers=headers).json() == receipt
        bad = client.post("/api/ui/connection-operations", json=request | {"unexpected": "private-marker"}, headers=headers)
        assert bad.status_code == 422 and "private-marker" not in bad.text
        assert client.post("/api/ui/connection-operations", json=request, headers=headers | {"Origin": "https://evil.invalid"}).status_code == 403
        assert client.post("/api/ui/connection-operations", json=request).status_code == 401
        assert client.get("/api/ui/connection-operations/" + str(uuid4()), headers=headers).status_code == 404
        env.store.sessions.revoke([env.claims])
        assert client.get("/api/ui/connection-operations/" + request["request_id"], headers=headers).status_code == 401
    with TestClient(app, base_url="http://testserver") as client:
        assert client.post("/api/ui/connection-operations", json=request, headers=headers).status_code in (400, 403)


def wait_for_lock(admin, fragment, count=1):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with admin.connect() as conn:
            rows = conn.execute("SELECT pid FROM pg_stat_activity WHERE datname=current_database() "
                "AND wait_event_type='Lock' AND query LIKE %s", ("%" + fragment + "%",)).fetchall()
        if len(rows) >= count:
            return rows
        time.sleep(0.01)
    pytest.fail("no observed PostgreSQL lock wait: " + fragment)


def service_for(env):
    from pilot.connection_versions import ConnectionOperationStore
    return ConnectionOperationStore(env.database)


@pytest.mark.parametrize("owner", ["missing", "other_user", "foreign_user"])
def test_unavailable_device_receipts_are_durable_and_private(env, owner):
    from pilot.connection_versions import ConnectionOperationError
    service = service_for(env)
    device = str(uuid4()) if owner == "missing" else env.store.register_device(getattr(env, owner), "synthetic-other")["device_id"]
    request = operation(env).model_copy(update={"device_id": device})
    receipt = service.apply(env.claims, request)
    assert receipt == dict(request_id=request.request_id, device_id=device, action="REGISTER",
        state="REJECTED", connection_id=None, connection_version=None, connection_status=None, error_code="device_unavailable")
    assert service.apply(env.claims, request) == receipt
    assert service.get_receipt(env.claims, request.request_id) == receipt
    with pytest.raises(ConnectionOperationError, match="request_conflict"):
        service.apply(env.claims, request.model_copy(update={"session_ref": "vault://changed"}))
    with env.admin.connect() as conn:
        assert conn.execute("SELECT authorized_device_id FROM pilot_connection_operations WHERE request_id=%s", (request.request_id,)).fetchone() == (None,)
        if owner == "missing":
            conn.execute("INSERT INTO pilot_devices(device_id,tenant_id,owner_user_id,device_label) VALUES (%s,%s,%s,'synthetic-later')", (device, env.tenant, env.user))
    assert service.apply(env.claims, request) == receipt
    assert env.store.list_connections(env.user) == []


@pytest.mark.parametrize("owner", ["other_user", "foreign_user"])
def test_receipt_and_checker_owner_denial(env, owner):
    from pilot.connection_versions import ConnectionOperationError
    service = service_for(env)
    request = operation(env)
    item = service.apply(env.claims, request)
    claims = verify_token_claims(issue_token(getattr(env, owner), "synthetic-connection-test-secret"), "synthetic-connection-test-secret")
    with pytest.raises(ConnectionOperationError, match="request_not_found"):
        service.get_receipt(claims, request.request_id)
    with env.database.connect() as conn:
        with pytest.raises(ConnectionOperationError, match="device_unavailable"):
            service.lock_current(conn.cursor(), claims, device_id=env.device,
                connection_id=item["connection_id"], connection_version=1, platform="BILIBILI")


def test_receipt_insert_failure_rolls_back_mutation(env):
    import psycopg
    service = service_for(env)
    request = operation(env)
    # A narrowly scoped synthetic rejection constraint fails only this request.
    from psycopg import sql
    name = "synthetic_receipt_" + uuid4().hex
    with env.admin.connect() as conn:
        conn.execute(sql.SQL("ALTER TABLE pilot_connection_operations ADD CONSTRAINT {} CHECK(request_id <> {})").format(sql.Identifier(name), sql.Literal(request.request_id)))
    try:
        with pytest.raises(psycopg.errors.CheckViolation):
            service.apply(env.claims, request)
        assert env.store.list_connections(env.user) == []
    finally:
        with env.admin.connect() as conn:
            conn.execute(sql.SQL("ALTER TABLE pilot_connection_operations DROP CONSTRAINT {}").format(sql.Identifier(name)))


@pytest.mark.parametrize("same_request", [False, True])
def test_concurrent_expected_version_and_replay(env, same_request):
    service = service_for(env)
    request = operation(env)
    second = request if same_request else operation(env)
    # Different sessions make the request/device fences independently observable.
    other_claims = verify_token_claims(issue_token(env.user, "synthetic-connection-test-secret"), "synthetic-connection-test-secret")
    with ThreadPoolExecutor(2) as pool:
        with env.admin.connect() as blocker:
            blocker.execute("SELECT 1 FROM pilot_devices WHERE device_id=%s FOR UPDATE", (env.device,))
            first = pool.submit(service.apply, env.claims, request)
            wait_for_lock(env.admin, "owner_user_id=")
            other = pool.submit(service.apply, other_claims, second)
            wait_for_lock(env.admin, "pg_advisory_xact_lock" if same_request else "owner_user_id=", 1 if same_request else 2)
        result = first.result(timeout=5)
        assert result["connection_version"] == 1
        if same_request:
            assert other.result(timeout=5) == result
        else:
            assert other.result(timeout=5)["error_code"] == "connection_version_conflict"
    assert env.store.list_connections(env.user)[0]["connection_version"] == 1


@pytest.mark.parametrize("logout_first", [False, True])
def test_session_logout_ordering(env, logout_first):
    from pilot.connection_versions import ConnectionOperationError
    service = service_for(env)
    with ThreadPoolExecutor(2) as pool:
        if logout_first:
            with env.admin.connect() as blocker:
                env.store.sessions.lock_session(blocker.cursor(), env.claims)
                blocker.execute("INSERT INTO pilot_session_revocations(tenant_id,user_id,revocation_key,expires_at) VALUES (%s,%s,%s,to_timestamp(%s))",
                    (env.tenant, env.user, env.claims.revocation_key, env.claims.expires_at))
                future = pool.submit(service.apply, env.claims, operation(env))
                wait_for_lock(env.admin, "pg_advisory_xact_lock")
            with pytest.raises(ConnectionOperationError, match="invalid_session"):
                future.result(timeout=5)
            assert env.store.list_connections(env.user) == []
        else:
            with env.admin.connect() as blocker:
                blocker.execute("SELECT 1 FROM pilot_devices WHERE device_id=%s FOR UPDATE", (env.device,))
                request = operation(env)
                future = pool.submit(service.apply, env.claims, request)
                wait_for_lock(env.admin, "owner_user_id=")
                logout = pool.submit(env.store.sessions.revoke, [env.claims])
                wait_for_lock(env.admin, "pg_advisory_xact_lock")
            receipt = future.result(timeout=5)
            logout.result(timeout=5)
            fresh = verify_token_claims(issue_token(env.user, "synthetic-connection-test-secret"), "synthetic-connection-test-secret")
            assert service.get_receipt(fresh, request.request_id) == receipt


def test_session_expires_while_device_blocked(env):
    from pilot.connection_versions import ConnectionOperationError
    claims = replace(env.claims, expires_at=int(time.time()) + 2)
    with ThreadPoolExecutor(1) as pool:
        with env.admin.connect() as blocker:
            blocker.execute("SELECT 1 FROM pilot_devices WHERE device_id=%s FOR UPDATE", (env.device,))
            future = pool.submit(service_for(env).apply, claims, operation(env))
            wait_for_lock(env.admin, "owner_user_id=")
            while time.time() <= claims.expires_at:
                time.sleep(0.01)
        with pytest.raises(ConnectionOperationError, match="invalid_session"):
            future.result(timeout=5)
    assert env.store.list_connections(env.user) == []


def synthetic_connected(env):
    item = env.store.connect_platform(env.user, "BILIBILI", env.device, "synthetic-id", "vault://synthetic")
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_platform_connections SET status='CONNECTED' WHERE connection_id=%s", (item["connection_id"],))
    return item["connection_id"]


def check_connection(env, cid, connection=None):
    def check(cursor):
        return service_for(env).lock_current(cursor, env.claims, device_id=env.device,
            connection_id=cid, connection_version=2, platform="BILIBILI")
    if connection is not None:
        return check(connection.cursor())
    with env.database.connect() as conn:
        return check(conn.cursor())


def legacy_mutation(env, cid, method):
    if method == "connect":
        return env.store.connect_platform(env.user, "BILIBILI", env.device, "synthetic-id", "vault://synthetic")
    if method == "disconnect":
        return env.store.disconnect_platform(env.user, cid)
    return env.store.revoke_device(env.user, env.device)


@pytest.mark.parametrize("method", ["connect", "disconnect", "revoke"])
@pytest.mark.parametrize("checker_first", [False, True])
def test_checker_and_mutation_lock_order_both_directions(env, method, checker_first):
    from pilot.connection_versions import ConnectionOperationError
    cid = synthetic_connected(env)
    with ThreadPoolExecutor(2) as pool:
        if checker_first:
            with env.database.connect() as conn:
                assert check_connection(env, cid, conn)["connection_version"] == 2
                mutation = pool.submit(legacy_mutation, env, cid, method)
                wait_for_lock(env.admin, "UPDATE pilot_devices" if method == "revoke" else "FROM pilot_devices")
                # Fence does not commit its caller: competitor remains blocked.
                assert not mutation.done()
                conn.rollback()
            mutation.result(timeout=5)
        else:
            with env.admin.connect() as blocker:
                blocker.execute("SELECT 1 FROM pilot_platform_connections WHERE connection_id=%s FOR UPDATE", (cid,))
                mutation = pool.submit(legacy_mutation, env, cid, method)
                wait_for_lock(env.admin, "SELECT connection_version" if method == "connect" else "UPDATE pilot_platform_connections")
                checked = pool.submit(check_connection, env, cid)
                wait_for_lock(env.admin, "owner_user_id=")
            mutation.result(timeout=5)
            with pytest.raises(ConnectionOperationError, match="device_unavailable" if method == "revoke" else "connection_version_conflict"):
                checked.result(timeout=5)
    assert env.store.list_connections(env.user)[0]["connection_version"] == 3


def test_disconnect_noop_and_device_bound_field(env):
    cid = synthetic_connected(env)
    assert env.store.disconnect_platform(env.user, cid)
    assert not env.store.disconnect_platform(env.user, cid)
    assert env.store.list_connections(env.user)[0]["connection_version"] == 3
    other = env.store.register_device(env.user, "synthetic-second")["device_id"]
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_platform_connections SET device_id=%s WHERE connection_id=%s", (other, cid))
    assert env.store.list_connections(env.user)[0]["connection_version"] == 4


def test_replay_expiry_while_receipt_query_blocked(env):
    from pilot.connection_versions import ConnectionOperationError
    service = service_for(env)
    request = operation(env)
    service.apply(env.claims, request)
    claims = replace(env.claims, expires_at=int(time.time()) + 2)
    with ThreadPoolExecutor(1) as pool:
        with env.admin.connect() as blocker:
            blocker.execute("LOCK TABLE pilot_connection_operations IN ACCESS EXCLUSIVE MODE")
            future = pool.submit(service.apply, claims, request)
            wait_for_lock(env.admin, "SELECT request_id,requested_device_id")
            while time.time() <= claims.expires_at:
                time.sleep(0.01)
        with pytest.raises(ConnectionOperationError, match="invalid_session"):
            future.result(timeout=5)


@pytest.mark.parametrize("target", ["", "missing_" + uuid4().hex, "postgres"])
def test_connection_grant_rejects_unsafe_targets(databases, target):
    import psycopg
    admin, _ = databases
    with pytest.raises(psycopg.errors.RaiseException, match="restricted application role"):
        with admin.connect() as conn:
            conn.execute("SELECT set_config('yike.app_role',%s,true)", (target,))
            conn.execute((Path(__file__).parents[1] / "deploy/grant_connection_operations.sql").read_text())


def test_connection_grant_rejects_owner(databases):
    import psycopg
    from psycopg import sql
    admin, _ = databases
    role = "connection_owner_" + uuid4().hex
    with pytest.raises(psycopg.errors.RaiseException, match="must not own"):
        with admin.connect() as conn:
            conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS").format(sql.Identifier(role)))
            conn.execute(sql.SQL("ALTER TABLE pilot_connection_operations OWNER TO {}").format(sql.Identifier(role)))
            conn.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
            conn.execute((Path(__file__).parents[1] / "deploy/grant_connection_operations.sql").read_text())


def test_upgrade_106_to_107_twice_and_immutable_owner_rls(databases):
    import psycopg
    from psycopg import sql
    from urllib.parse import urlsplit, urlunsplit
    from tests.test_device_credentials_postgres import RoleDatabase
    from pilot.connection_versions import ConnectionOperationStore
    admin, _ = databases
    dbname, role = "connection_upgrade_" + uuid4().hex, "connection_role_" + uuid4().hex
    fresh = PilotDatabase(urlunsplit(urlsplit(admin.url)._replace(path="/" + dbname)))
    created = False
    try:
        with admin.connect() as conn:
            conn.autocommit = True
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
            created = True
        fresh.migration_paths = tuple(item for item in PilotDatabase.migration_paths if item[0] != "v02-connection-versions")
        fresh.migrate()
        provisioner = PilotStore(fresh)
        tenant = provisioner.provision_tenant("synthetic-upgrade")
        user = provisioner.provision_user(tenant, f"{uuid4()}@example.invalid")
        device = provisioner.register_device(user, "synthetic-upgrade")["device_id"]
        cid = str(uuid4())
        with fresh.connect() as conn:
            conn.execute("INSERT INTO pilot_platform_connections(connection_id,tenant_id,device_id,platform,account_public_id,session_ref) VALUES (%s,%s,%s,'BILIBILI','synthetic-id','vault://synthetic')", (cid, tenant, device))
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
            assert conn.execute("SELECT status,account_public_id,session_ref,connection_version FROM pilot_platform_connections WHERE connection_id=%s", (cid,)).fetchone() == ("UNVERIFIED", "synthetic-id", "vault://synthetic", 1)
            assert conn.execute("SELECT count(*) FROM pilot_schema_meta").fetchone()[0] == len(PilotDatabase.migration_paths)
            conn.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
            grant = (Path(__file__).parents[1] / "deploy/grant_connection_operations.sql").read_text()
            conn.execute(grant)
            conn.execute(grant)
        restricted = RoleDatabase(fresh, role)
        isolated = SimpleNamespace(device=device)
        claims = verify_token_claims(issue_token(user, "synthetic-connection-test-secret"), "synthetic-connection-test-secret")
        service = ConnectionOperationStore(restricted)
        request = operation(isolated, expected_connection_version=1)
        receipt = service.apply(claims, request)
        assert receipt["connection_version"] == 2
        assert service.get_receipt(claims, request.request_id) == receipt
        with restricted.connect() as conn:
            assert conn.execute("SELECT row_security_active('pilot_connection_operations'::regclass)").fetchone()[0]
            assert conn.execute("SELECT count(*) FROM pilot_connection_operations").fetchone()[0] == 0
            for table, privilege in (("pilot_connection_operations", "UPDATE"), ("pilot_connection_operations", "DELETE"), ("pilot_users", "UPDATE")):
                assert not conn.execute("SELECT has_table_privilege(current_user,%s,%s)", (table, privilege)).fetchone()[0]
            assert not conn.execute("SELECT has_schema_privilege(current_user,'public','CREATE')").fetchone()[0]
            conn.execute("SELECT set_config('yike.tenant_id',%s,true)", (tenant,))
            conn.execute("SELECT set_config('yike.user_id',%s,true)", (user,))
            assert conn.execute("SELECT count(*) FROM pilot_connection_operations").fetchone()[0] == 1
            for statement in ("UPDATE pilot_connection_operations SET state=state", "DELETE FROM pilot_connection_operations"):
                with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                    conn.execute(statement)
            conn.execute("SELECT set_config('yike.user_id',%s,true)", (str(uuid4()),))
            assert conn.execute("SELECT count(*) FROM pilot_connection_operations").fetchone()[0] == 0
        with fresh.connect() as conn:
            with pytest.raises(psycopg.errors.ForeignKeyViolation), conn.transaction():
                conn.execute("UPDATE pilot_connection_operations SET owner_user_id=%s WHERE request_id=%s", (str(uuid4()), request.request_id))
    finally:
        if created:
            with admin.connect() as conn:
                conn.autocommit = True
                conn.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(dbname)))
                if conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                    conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


@pytest.mark.parametrize("method", ["connect", "disconnect", "revoke"])
def test_legacy_http_exhaustion_returns_safe_409(env, method):
    from fastapi.testclient import TestClient
    from pilot.web import build_app
    cid = synthetic_connected(env)
    with env.admin.connect() as conn:
        conn.execute("ALTER TABLE pilot_platform_connections DISABLE TRIGGER pilot_connection_version_guard")
        conn.execute("UPDATE pilot_platform_connections SET connection_version=2147483647 WHERE connection_id=%s", (cid,))
        conn.execute("ALTER TABLE pilot_platform_connections ENABLE TRIGGER pilot_connection_version_guard")
    with TestClient(build_app(env.store, auth_secret="synthetic-connection-test-secret"), base_url="https://testserver") as client:
        headers = {"Authorization": "Bearer " + env.token}
        if method == "connect":
            reply = client.post("/api/ui/connections", headers=headers, json=dict(platform="BILIBILI",
                device_id=env.device, account_public_id="synthetic-id", session_ref="vault://synthetic"))
        else:
            route = f"connections/{cid}/disconnect" if method == "disconnect" else f"devices/{env.device}/revoke"
            reply = client.post("/api/ui/" + route, headers=headers)
        assert reply.status_code == 409
        assert reply.json()["detail"]["code"] == "connection_version_exhausted"
        assert reply.headers["cache-control"] == "no-store"
        assert "vault" not in reply.text and "SQL" not in reply.text
    assert env.store.list_connections(env.user)[0]["status"] == "CONNECTED"
    assert env.store.list_devices(env.user)[0]["status"] == "ACTIVE"


@pytest.mark.parametrize("method", ["connect", "disconnect", "revoke"])
def test_legacy_http_rechecks_expiry_after_lock_wait(env, method):
    from fastapi.testclient import TestClient
    from pilot.web import build_app
    cid = synthetic_connected(env)
    deadline = int(time.time()) + 2
    token = issue_token(env.user, "synthetic-connection-test-secret", now=deadline - 2, ttl_seconds=2)
    with TestClient(build_app(env.store, auth_secret="synthetic-connection-test-secret"), base_url="https://testserver") as client, ThreadPoolExecutor(1) as pool:
        headers = {"Authorization": "Bearer " + token}
        with env.admin.connect() as blocker:
            blocker.execute("SELECT 1 FROM pilot_devices WHERE device_id=%s FOR UPDATE", (env.device,))
            if method == "connect":
                future = pool.submit(client.post, "/api/ui/connections", headers=headers, json=dict(platform="BILIBILI",
                    device_id=env.device, account_public_id="synthetic-id", session_ref="vault://synthetic"))
            else:
                route = f"connections/{cid}/disconnect" if method == "disconnect" else f"devices/{env.device}/revoke"
                future = pool.submit(client.post, "/api/ui/" + route, headers=headers)
            wait_for_lock(env.admin, "UPDATE pilot_devices" if method == "revoke" else "FROM pilot_devices")
            while time.time() <= deadline:
                time.sleep(0.01)
        reply = future.result(timeout=5)
        assert reply.status_code == 401
        assert reply.json()["detail"]["code"] == "invalid_session"
    assert env.store.list_connections(env.user)[0]["connection_version"] == 2
    assert env.store.list_devices(env.user)[0]["status"] == "ACTIVE"


def test_insert_version_and_explicit_bump_guards(env):
    import psycopg
    cid = synthetic_connected(env)
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_platform_connections SET connection_version=connection_version+1,status='EXPIRED' WHERE connection_id=%s", (cid,))
        assert conn.execute("SELECT connection_version FROM pilot_platform_connections WHERE connection_id=%s", (cid,)).fetchone()[0] == 3
        for version in (0, 2, 7, None):
            with pytest.raises(psycopg.Error) as caught, conn.transaction():
                conn.execute("UPDATE pilot_platform_connections SET connection_version=%s WHERE connection_id=%s", (version, cid))
            assert caught.value.sqlstate == "YC002"
        with pytest.raises(psycopg.Error) as caught, conn.transaction():
            conn.execute("INSERT INTO pilot_platform_connections(connection_id,tenant_id,device_id,platform,account_public_id,session_ref,connection_version) VALUES (%s,%s,%s,'BILIBILI','synthetic-new','vault://synthetic',2)", (str(uuid4()), env.tenant, env.device))
        assert caught.value.sqlstate == "YC002"
