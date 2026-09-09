"""Upgrade a SELECT-only identity role; never grant all tables to this role."""
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from fastapi.testclient import TestClient

from pilot.auth import issue_token, verify_token_claims
from pilot.db import PilotDatabase
from pilot.store import PilotStore
from pilot.web import build_app
from test_identity_postgres import databases  # dedicated test migration fixture


@pytest.mark.parametrize("target", ["", "missing_" + uuid4().hex, "postgres"])
def test_privilege_upgrade_rejects_missing_or_privileged_target(databases, target):
    admin, _ = databases
    upgrade = Path(__file__).parents[1] / "deploy/grant_session_revocations.sql"
    with pytest.raises(psycopg.errors.RaiseException, match="restricted application role"):
        with admin.connect() as connection:
            connection.execute("SELECT set_config('yike.app_role', %s, true)", (target,))
            connection.execute(upgrade.read_text(encoding="utf-8"))


def test_privilege_upgrade_rejects_identity_table_owner_before_granting(databases):
    admin, _ = databases
    role = "identity_owner_" + uuid4().hex
    upgrade = Path(__file__).parents[1] / "deploy/grant_session_revocations.sql"
    with pytest.raises(psycopg.errors.RaiseException, match="must not own identity registry tables"):
        with admin.connect() as connection:
            # The exception aborts this transaction, rolling back both ownership and role creation.
            connection.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS").format(sql.Identifier(role)))
            connection.execute(sql.SQL("ALTER TABLE public.pilot_devices OWNER TO {}").format(sql.Identifier(role)))
            connection.execute("SELECT set_config('yike.app_role', %s, true)", (role,))
            connection.execute(upgrade.read_text(encoding="utf-8"))


class _RoleDatabase(PilotDatabase):
    def __init__(self, admin, role):
        super().__init__(admin.url)
        self.role = role

    @contextmanager
    def connect(self):
        with super().connect() as connection:
            connection.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(self.role)))
            yield connection


def test_existing_read_only_identity_role_works_after_explicit_upgrade(databases):
    admin, _ = databases
    role = "session_upgrade_" + uuid4().hex
    provisioner = PilotStore(admin)
    tenant = provisioner.provision_tenant("synthetic-upgrade")
    user = provisioner.provision_user(tenant, "upgrade@example.invalid")
    other_tenant = provisioner.provision_tenant("synthetic-upgrade-other")
    other_user = provisioner.provision_user(other_tenant, "upgrade-other@example.invalid")
    task_id = provisioner.claim_task(user, "synthetic-upgrade-task", "synthetic-admin-seed")["task_id"]
    try:
        with admin.connect() as connection:
            connection.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS").format(sql.Identifier(role)))
            connection.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
            connection.execute(sql.SQL("GRANT SELECT ON public.pilot_users TO {}").format(sql.Identifier(role)))
            # Pre-existing task permissions are not part of the identity-registry release repair.
            connection.execute(sql.SQL("GRANT SELECT, UPDATE ON public.pilot_tasks TO {}").format(sql.Identifier(role)))
        store = PilotStore(_RoleDatabase(admin, role))
        secret = "synthetic-upgrade-secret"
        token = issue_token(user, secret)
        headers = {"Authorization": "Bearer " + token}
        client = TestClient(build_app(store, auth_secret=secret), base_url="https://testserver", raise_server_exceptions=False)
        # Migration alone must not be mistaken for an operational upgrade.
        assert client.get("/api/ui/session", headers=headers).status_code == 500
        upgrade = Path(__file__).parents[1] / "deploy/grant_session_revocations.sql"
        assert upgrade.is_file(), "the release must include the minimal session privilege upgrade"
        with admin.connect() as connection:
            connection.execute("SELECT set_config('yike.app_role', %s, true)", (role,))
            connection.execute(upgrade.read_text(encoding="utf-8"))
            connection.execute(upgrade.read_text(encoding="utf-8"))  # repeatable
        with store.database.connect() as connection:
            assert connection.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone() == (False, False)
            assert connection.execute("SELECT has_table_privilege(current_user,'pilot_users','UPDATE')").fetchone() == (False,)
            assert connection.execute("SELECT has_table_privilege(current_user,'pilot_session_revocations','UPDATE')").fetchone() == (False,)
            assert connection.execute("SELECT has_table_privilege(current_user,'pilot_session_revocations','DELETE')").fetchone() == (False,)
            for table in ("pilot_devices", "pilot_platform_connections"):
                assert connection.execute(
                    "SELECT has_table_privilege(current_user,%s,'DELETE')", (table,)
                ).fetchone() == (False,)
            for privilege in ("UPDATE", "DELETE"):
                assert connection.execute(
                    "SELECT has_table_privilege(current_user,'pilot_execution_events',%s)", (privilege,)
                ).fetchone() == (False,)
        assert store.sessions.authenticate(verify_token_claims(token, secret)) == tenant
        assert client.get("/api/ui/session", headers=headers).status_code == 200
        assert client.get("/api/ui/devices", headers=headers).json() == {"items": []}
        assert client.get(
            "/api/ui/devices",
            headers={"Authorization": "Bearer " + issue_token(other_user, secret)},
        ).json() == {"items": []}
        device_response = client.post(
            "/api/ui/devices", headers=headers, json={"device_label": "synthetic-upgrade-device"}
        )
        assert device_response.status_code == 201
        device = device_response.json()["device_id"]
        connection_response = client.post(
            "/api/ui/connections",
            headers=headers,
            json={
                "platform": "BILIBILI",
                "device_id": device,
                "account_public_id": "synthetic-upgrade-account",
                "session_ref": "vault://synthetic-upgrade-reference",
            },
        )
        assert connection_response.status_code == 201
        connection_id = connection_response.json()["connection_id"]
        assert client.post(
            "/api/ui/connections",
            headers={"Authorization": "Bearer " + issue_token(other_user, secret)},
            json={
                "platform": "BILIBILI",
                "device_id": device,
                "account_public_id": "synthetic-cross-tenant-account",
                "session_ref": "vault://synthetic-cross-tenant-reference",
            },
        ).status_code == 404
        # Synthetic administrator seeding only; this is not platform connectivity proof.
        with admin.connect() as connection:
            connection.execute(
                "UPDATE pilot_platform_connections SET status='CONNECTED' WHERE connection_id=%s",
                (connection_id,),
            )
        event_response = client.post(
            "/api/ui/execution-events",
            headers=headers,
            json={
                "device_id": device,
                "connection_id": connection_id,
                "execution_generation": 1,
                "event_type": "COLLECTION_STARTED",
                "payload": {},
                "task_id": task_id,
            },
        )
        assert event_response.status_code == 201
        assert client.post(
            f"/api/ui/connections/{connection_id}/disconnect", headers=headers
        ).json() == {"connection_id": connection_id, "status": "DISCONNECTED"}
        assert client.post(f"/api/ui/devices/{device}/revoke", headers=headers).json() == {
            "device_id": device,
            "status": "REVOKED",
        }
        assert client.post("/api/ui/session", json={"token": token}).status_code == 200
        assert client.delete("/api/ui/session").json() == {"authenticated": False}
        assert client.get("/api/ui/session", headers=headers).status_code == 401
    finally:
        with admin.connect() as connection:
            connection.execute("DELETE FROM pilot_execution_events WHERE tenant_id IN (%s,%s)", (tenant, other_tenant))
            connection.execute("DELETE FROM pilot_platform_connections WHERE tenant_id IN (%s,%s)", (tenant, other_tenant))
            connection.execute("DELETE FROM pilot_devices WHERE tenant_id IN (%s,%s)", (tenant, other_tenant))
            connection.execute("DELETE FROM pilot_tasks WHERE tenant_id IN (%s,%s)", (tenant, other_tenant))
            connection.execute("DELETE FROM pilot_session_revocations WHERE user_id=%s", (user,))
            connection.execute("DELETE FROM pilot_users WHERE user_id IN (%s,%s)", (user, other_user))
            connection.execute("DELETE FROM pilot_tenants WHERE tenant_id IN (%s,%s)", (tenant, other_tenant))
            # Drop only the permissions owned by this generated test role.
            if connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                connection.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
                connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
