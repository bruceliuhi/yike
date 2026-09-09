"""Adversarial session checks against an already-migrated, synthetic PostgreSQL.

Requires migration 105 and a pre-provisioned non-superuser/NOBYPASSRLS app role.
This module never migrates, grants privileges, or changes roles. Only explicit
database-failure tests inject faults; all revocation state otherwise uses PG.
These checks do not prove customer login, platform login, or production readiness.
"""
import base64
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import logging
import os
import time
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import psycopg
import pytest

from pilot.auth import issue_token, verify_token_claims
from pilot.db import PilotDatabase
from pilot.store import PilotStore
from pilot.web import build_app


SECRET = "synthetic-revocation-test-secret"
FAULT_MARKER = "synthetic-db-fault password=synthetic-only-no-real-secret"


@pytest.fixture(scope="module")
def revocation_databases():
    admin_url = os.environ.get("YIKE_IDENTITY_TEST_DATABASE_URL")
    app_url = os.environ.get("YIKE_IDENTITY_TEST_APP_DATABASE_URL")
    if not admin_url or not app_url:
        pytest.skip("pre-migrated dedicated identity PostgreSQL database required")
    admin, database = PilotDatabase(admin_url), PilotDatabase(app_url)
    with admin.connect() as connection:
        assert connection.execute(
            "SELECT 1 FROM pilot_schema_meta WHERE version='v02-session-revocation'"
        ).fetchone(), "apply migration 105 in the dedicated test database first"
    with database.connect() as connection:
        assert connection.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user"
        ).fetchone() == (False, False)
        assert connection.execute(
            "SELECT row_security_active('pilot_session_revocations')"
        ).fetchone() == (True,)
    return admin, database


@pytest.fixture
def sessions(revocation_databases):
    admin, database = revocation_databases
    provisioner = PilotStore(admin)
    tenants, users = [], []
    try:
        for _ in range(2):
            tenants.append(provisioner.provision_tenant("synthetic-session-adversary"))
        for tenant in (tenants[0], tenants[0], tenants[1]):
            users.append(provisioner.provision_user(tenant, f"{uuid4()}@example.invalid"))
        yield SimpleNamespace(
            admin=admin, database=database, store=PilotStore(database),
            tenants=tenants, users=users,
        )
    finally:
        # Exact IDs created by this fixture only; never touch another test's rows.
        with admin.connect() as connection:
            connection.execute(
                "DELETE FROM pilot_session_revocations WHERE user_id=ANY(%s)", (users,)
            )
            connection.execute("DELETE FROM pilot_users WHERE user_id=ANY(%s)", (users,))
            connection.execute("DELETE FROM pilot_tenants WHERE tenant_id=ANY(%s)", (tenants,))


def client_for(sessions, *, dev_login=False, **kwargs):
    return TestClient(
        build_app(sessions.store, auth_secret=SECRET, dev_login=dev_login),
        base_url="https://testserver", **kwargs,
    )


def credentials(*, bearer=None, cookie=None):
    headers = {}
    if bearer is not None:
        headers["Authorization"] = "Bearer " + bearer
    if cookie is not None:
        headers["Cookie"] = "pilot_session=" + cookie
    return headers


def legacy_token(user_id):
    # Explicit old-format fixture: signed sub/exp only, without a jti.
    raw = base64.urlsafe_b64encode(json.dumps({
        "sub": user_id, "exp": int(time.time()) + 3600,
    }, separators=(",", ":")).encode()).rstrip(b"=")
    signature = hmac.new(SECRET.encode(), raw, hashlib.sha256).digest()
    return raw.decode() + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()


def assert_revoked(client, token):
    client.cookies.clear()
    for headers in (credentials(bearer=token), credentials(cookie=token)):
        for path in ("/api/ui/session", "/api/ui/devices", "/profile"):
            assert client.get(path, headers=headers).status_code == 401
    assert client.post("/api/ui/session", json={"token": token}).status_code == 401
    assert client.post("/session", data={"token": token}, follow_redirects=False).status_code == 401


def revocations_for(sessions, user_id):
    with sessions.admin.connect() as connection:
        return connection.execute(
            "SELECT tenant_id,user_id,revocation_key,expires_at,revoked_at "
            "FROM pilot_session_revocations WHERE user_id=%s ORDER BY revocation_key",
            (user_id,),
        ).fetchall()


@pytest.mark.parametrize("logout_padding", ["", "="])
def test_legacy_logout_and_equivalent_signature_padding_cannot_revive(sessions, logout_padding):
    token = legacy_token(sessions.users[0])
    with client_for(sessions) as client:
        for variant in (token, token + "="):
            assert client.get("/api/ui/session", headers=credentials(bearer=variant)).status_code == 200
        assert client.delete(
            "/api/ui/session", headers=credentials(bearer=token + logout_padding)
        ).status_code == 200
        for variant in (token, token + "="):
            assert_revoked(client, variant)
    rows = revocations_for(sessions, sessions.users[0])
    assert len(rows) == 1
    assert rows[0][2] == hashlib.sha256(token.split(".")[0].encode()).hexdigest()
    assert token not in repr(rows) and SECRET not in repr(rows)


@pytest.mark.parametrize("cookie_user", [1, 2], ids=["same-tenant-other-user", "other-tenant"])
def test_logout_revokes_both_distinct_identities_in_bearer_and_cookie(sessions, cookie_user):
    bearer = issue_token(sessions.users[0], SECRET)
    cookie = issue_token(sessions.users[cookie_user], SECRET)
    with client_for(sessions) as client:
        assert client.delete(
            "/api/ui/session", headers=credentials(bearer=bearer, cookie=cookie)
        ).json() == {"authenticated": False}
        assert_revoked(client, bearer)
        assert_revoked(client, cookie)
    for user in (sessions.users[0], sessions.users[cookie_user]):
        assert len(revocations_for(sessions, user)) == 1


@pytest.mark.parametrize("invalid_kind", ["malformed", "expired"])
@pytest.mark.parametrize("valid_location", ["bearer", "cookie"])
def test_invalid_or_expired_credential_does_not_shadow_valid_logout(
    sessions, invalid_kind, valid_location,
):
    valid = issue_token(sessions.users[0], SECRET)
    invalid = "synthetic-invalid-token"
    if invalid_kind == "expired":
        invalid = issue_token(sessions.users[2], SECRET, now=int(time.time()) - 7200)
    pair = {valid_location: valid, "cookie" if valid_location == "bearer" else "bearer": invalid}
    with client_for(sessions) as client:
        response = client.delete("/api/ui/session", headers=credentials(**pair))
        assert response.status_code == 200
        assert_revoked(client, valid)
    assert len(revocations_for(sessions, sessions.users[0])) == 1
    assert revocations_for(sessions, sessions.users[2]) == []


def test_same_second_tokens_are_independent_and_repeated_logout_is_idempotent(sessions):
    issued_at = int(time.time())
    first, second = [issue_token(sessions.users[0], SECRET, now=issued_at) for _ in range(2)]
    assert first != second
    with client_for(sessions) as client:
        for _ in range(3):
            response = client.delete(
                "/api/ui/session", headers=credentials(bearer=first, cookie=first + "=")
            )
            assert response.status_code == 200
            assert response.json() == {"authenticated": False}
        assert_revoked(client, first)
        for headers in (credentials(bearer=second), credentials(cookie=second)):
            assert client.get("/api/ui/session", headers=headers).json() == {
                "authenticated": True, "user_id": sessions.users[0],
            }
        assert client.post("/api/ui/session", json={"token": second}).status_code == 200
    assert len(revocations_for(sessions, sessions.users[0])) == 1


def test_revoked_token_is_rejected_by_enabled_development_bridge(sessions):
    token = issue_token(sessions.users[0], SECRET)
    with client_for(sessions, dev_login=True) as client:
        assert client.get("/__dev/session", params={"token": token}, follow_redirects=False).status_code == 303
        assert client.delete("/api/ui/session").status_code == 200
        response = client.get("/__dev/session", params={"token": token}, follow_redirects=False)
        assert response.status_code == 401
        assert "set-cookie" not in response.headers


def set_identity(connection, tenant_id, user_id):
    if tenant_id is not None:
        connection.execute("SELECT set_config('yike.tenant_id', %s, true)", (tenant_id,))
    if user_id is not None:
        connection.execute("SELECT set_config('yike.user_id', %s, true)", (user_id,))


@pytest.mark.parametrize("context", ["none", "tenant-only", "user-only", "sibling", "wrong-tenant", "other"])
def test_revocation_rls_rejects_missing_or_different_identity(sessions, context):
    user, tenant = sessions.users[0], sessions.tenants[0]
    claims = verify_token_claims(issue_token(user, SECRET), SECRET)
    sessions.store.sessions.revoke([claims])
    context_tenant, context_user = {
        "none": (None, None), "tenant-only": (tenant, None),
        "user-only": (None, user), "sibling": (tenant, sessions.users[1]),
        "wrong-tenant": (sessions.tenants[1], user),
        "other": (sessions.tenants[1], sessions.users[2]),
    }[context]
    with sessions.database.connect() as connection:
        set_identity(connection, context_tenant, context_user)
        assert connection.execute(
            "SELECT count(*) FROM pilot_session_revocations WHERE user_id=%s", (user,)
        ).fetchone()[0] == 0
        assert connection.execute(
            "UPDATE pilot_session_revocations SET expires_at=CURRENT_TIMESTAMP WHERE user_id=%s",
            (user,),
        ).rowcount == 0
        assert connection.execute(
            "DELETE FROM pilot_session_revocations WHERE user_id=%s", (user,)
        ).rowcount == 0
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with sessions.database.connect() as connection:
            set_identity(connection, context_tenant, context_user)
            connection.execute(
                "INSERT INTO pilot_session_revocations(tenant_id,user_id,revocation_key,expires_at) "
                "VALUES (%s,%s,%s,%s)",
                (tenant, user, hashlib.sha256(uuid4().bytes).hexdigest(), datetime.now(UTC) + timedelta(hours=1)),
            )
    assert len(revocations_for(sessions, user)) == 1


def test_owner_can_read_insert_but_cannot_update_or_delete_revocations(sessions):
    user, tenant = sessions.users[0], sessions.tenants[0]
    token = issue_token(user, SECRET)
    claims = verify_token_claims(token, SECRET)
    sessions.store.sessions.revoke([claims])
    with sessions.database.connect() as connection:
        set_identity(connection, tenant, user)
        assert connection.execute(
            "SELECT revocation_key FROM pilot_session_revocations WHERE user_id=%s", (user,)
        ).fetchone() == (claims.revocation_key,)
        connection.execute(
            "INSERT INTO pilot_session_revocations(tenant_id,user_id,revocation_key,expires_at) "
            "VALUES (%s,%s,%s,%s)",
            (tenant, user, hashlib.sha256(uuid4().bytes).hexdigest(), datetime.now(UTC) + timedelta(hours=1)),
        )
        assert connection.execute(
            "UPDATE pilot_session_revocations SET expires_at=CURRENT_TIMESTAMP WHERE user_id=%s", (user,)
        ).rowcount == 0
        assert connection.execute(
            "DELETE FROM pilot_session_revocations WHERE user_id=%s", (user,)
        ).rowcount == 0
    assert len(revocations_for(sessions, user)) == 2
    with client_for(sessions) as client:
        assert_revoked(client, token)


def test_real_composite_fk_prevents_reparenting_user_with_revocation(sessions):
    user = sessions.users[0]
    token = issue_token(user, SECRET)
    sessions.store.sessions.revoke([verify_token_claims(token, SECRET)])
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with sessions.admin.connect() as connection:
            connection.execute(
                "UPDATE pilot_users SET tenant_id=%s WHERE user_id=%s", (sessions.tenants[1], user)
            )
    with sessions.admin.connect() as connection:
        assert connection.execute(
            "SELECT tenant_id FROM pilot_users WHERE user_id=%s", (user,)
        ).fetchone() == (sessions.tenants[0],)
    with client_for(sessions) as client:
        assert_revoked(client, token)


def assert_generic_database_failure(response, caplog, tokens):
    assert response.status_code == 500
    assert "set-cookie" not in response.headers
    if response.headers.get("content-type", "").startswith("application/json"):
        assert "authenticated" not in response.json()
    for secret in (FAULT_MARKER, SECRET, *tokens):
        assert secret not in response.text
        assert secret not in repr(dict(response.headers))
        assert secret not in caplog.text


@pytest.mark.parametrize("surface", ["json-bearer", "json-cookie", "html", "json-exchange", "html-exchange", "dev-bridge"])
def test_database_read_failure_never_authorizes_or_leaks(sessions, monkeypatch, caplog, surface):
    """Explicit DB-unavailable fault injection; no session-registry double."""
    token = issue_token(sessions.users[0], SECRET)
    caplog.set_level(logging.INFO, logger="yike.pilot.access")
    with client_for(
        sessions, dev_login=surface == "dev-bridge", raise_server_exceptions=False,
    ) as client:
        assert client.get("/api/ui/session", headers=credentials(bearer=token)).status_code == 200

        def unavailable():
            raise psycopg.OperationalError(FAULT_MARKER + " " + token)

        monkeypatch.setattr(sessions.database, "connect", unavailable)
        if surface == "json-bearer":
            response = client.get("/api/ui/session", headers=credentials(bearer=token))
        elif surface == "json-cookie":
            response = client.get("/api/ui/session", headers=credentials(cookie=token))
        elif surface == "html":
            response = client.get("/profile", headers=credentials(bearer=token))
        elif surface == "json-exchange":
            response = client.post("/api/ui/session", json={"token": token})
        elif surface == "html-exchange":
            response = client.post("/session", data={"token": token}, follow_redirects=False)
        else:
            response = client.get("/__dev/session", params={"token": token}, follow_redirects=False)
    assert_generic_database_failure(response, caplog, [token])


@pytest.mark.parametrize("failure_at", ["first-write", "second-write", "before-commit"])
def test_logout_database_failure_is_atomic_and_does_not_claim_success(
    sessions, monkeypatch, caplog, failure_at,
):
    """Explicit write/commit fault injection over real PostgreSQL transactions."""
    tokens = [issue_token(sessions.users[index], SECRET) for index in (0, 2)]
    caplog.set_level(logging.INFO, logger="yike.pilot.access")
    writes = 0

    class FailingCursor(psycopg.Cursor):
        def execute(self, query, params=None, **kwargs):
            nonlocal writes
            if isinstance(query, str) and query.startswith("INSERT INTO pilot_session_revocations"):
                writes += 1
                if (failure_at, writes) in (("first-write", 1), ("second-write", 2)):
                    raise psycopg.OperationalError(FAULT_MARKER + " " + tokens[0])
            return super().execute(query, params, **kwargs)

    @contextmanager
    def failing_connection():
        with psycopg.connect(sessions.database.url, cursor_factory=FailingCursor) as connection:
            yield connection
            if failure_at == "before-commit":
                raise psycopg.OperationalError(FAULT_MARKER + " " + tokens[0])

    with client_for(sessions, raise_server_exceptions=False) as client:
        with monkeypatch.context() as failure:
            failure.setattr(sessions.database, "connect", failing_connection)
            response = client.delete(
                "/api/ui/session", headers=credentials(bearer=tokens[0], cookie=tokens[1])
            )
        assert_generic_database_failure(response, caplog, tokens)
        assert writes == (1 if failure_at == "first-write" else 2)
        for token in tokens:
            assert client.get("/api/ui/session", headers=credentials(bearer=token)).status_code == 200
    for user in (sessions.users[0], sessions.users[2]):
        assert revocations_for(sessions, user) == []
