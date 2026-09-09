"""Isolated PostgreSQL checks; synthetic identities, never platform proof."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
import time
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from pilot.auth import issue_token
from pilot.db import PilotDatabase
from pilot.store import PilotStore
from pilot.web import build_app


@pytest.fixture(scope="module")
def databases():
    admin_url = os.environ.get("YIKE_IDENTITY_TEST_DATABASE_URL")
    app_url = os.environ.get("YIKE_IDENTITY_TEST_APP_DATABASE_URL")
    if not admin_url or not app_url:
        pytest.skip("dedicated identity PostgreSQL test database required")
    admin = PilotDatabase(admin_url)
    admin.migrate()
    admin.migrate()
    with admin.connect() as connection:
        connection.execute("DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='identity_app') THEN CREATE ROLE identity_app LOGIN PASSWORD 'test-only' NOSUPERUSER NOBYPASSRLS; END IF; END $$")
        connection.execute("GRANT USAGE ON SCHEMA public TO identity_app")
        connection.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO identity_app")
    return admin, PilotDatabase(app_url)


@pytest.fixture
def identities(databases):
    admin, database = databases
    admin_store, store = PilotStore(admin), PilotStore(database)
    tenant = admin_store.provision_tenant("synthetic-identity")
    user = admin_store.provision_user(tenant, "identity@example.invalid")
    device = store.register_device(user, "synthetic-device")["device_id"]
    connection_id = store.connect_platform(user, "BILIBILI", device, "synthetic-public-id", "vault://synthetic-reference")["connection_id"]
    # A future verified connector owns this promotion; not evidence of login.
    with admin.connect() as connection:
        connection.execute("UPDATE pilot_platform_connections SET status='CONNECTED' WHERE connection_id=%s", (connection_id,))
    return admin, database, store, tenant, user, device, connection_id


def test_customer_registration_does_not_prove_platform_login(identities):
    _, _, store, _, user, device, _ = identities
    result = store.connect_platform(user, "DOUYIN", device, "synthetic-dy", "vault://synthetic-dy")
    assert result["status"] == "UNVERIFIED"


def test_unverified_registration_can_be_disconnected(identities):
    _, _, store, _, user, device, _ = identities
    item = store.connect_platform(user, "DOUYIN", device, "synthetic-dy", "vault://synthetic-dy")
    assert store.disconnect_platform(user, item["connection_id"]) is True


def test_revoked_device_disconnects_unverified_registrations(identities):
    _, _, store, _, user, device, _ = identities
    store.connect_platform(user, "DOUYIN", device, "synthetic-dy", "vault://synthetic-dy")
    assert store.revoke_device(user, device) is True
    assert {item["status"] for item in store.list_connections(user)} == {"DISCONNECTED"}


def test_identity_api_uses_server_tenant_and_keeps_capabilities_honest(identities):
    admin, _, store, _, user, device, _ = identities
    admin_store = PilotStore(admin)
    other = admin_store.provision_user(admin_store.provision_tenant("other-api"), "other@example.invalid")
    client = TestClient(build_app(store, auth_secret="synthetic-test-secret", dev_login=True))
    headers = {"Authorization": "Bearer " + issue_token(user, "synthetic-test-secret")}
    other_headers = {"Authorization": "Bearer " + issue_token(other, "synthetic-test-secret")}
    assert client.get("/api/ui/devices").status_code == 401
    assert client.get("/api/ui/devices", headers=other_headers).json()["items"] == []
    assert client.post("/api/ui/devices", headers=headers, json={"device_label": "label", "tenant_id": "forged"}).status_code == 422
    connection = client.post("/api/ui/connections", headers=headers, json={"platform": "DOUYIN", "device_id": device, "account_public_id": "public-id", "session_ref": "vault://synthetic"})
    assert connection.status_code == 201
    assert connection.json()["status"] == "UNVERIFIED"
    assert "session_ref" not in client.get("/api/ui/connections", headers=headers).text
    assert client.post("/api/ui/connections", headers=other_headers, json={"platform": "DOUYIN", "device_id": device, "account_public_id": "public-id", "session_ref": "vault://synthetic"}).status_code == 404
    assert client.get("/api/ui/capabilities").json()["capabilities"]["platform_connections"] == {"available": False}
    rejected = client.post("/api/ui/execution-events", headers=headers, json={"device_id": device, "connection_id": connection.json()["connection_id"], "execution_generation": 1, "event_type": "COLLECTION_PROGRESS", "payload": {"access_token": "synthetic-sensitive"}})
    assert rejected.status_code == 400
    assert "synthetic-sensitive" not in rejected.text


def test_events_reject_unknown_and_cross_tenant_tasks(identities):
    admin, _, store, _, user, device, connection_id = identities
    admin_store = PilotStore(admin)
    other_tenant = admin_store.provision_tenant("synthetic-other")
    other_user = admin_store.provision_user(other_tenant, "other@example.invalid")
    other_task = store.claim_task(other_user, "other-task", "other-worker")["task_id"]
    for task_id in (other_task, str(uuid4())):
        with pytest.raises(KeyError):
            store.append_execution_event(user, device, connection_id, 1, "COLLECTION_STARTED", {}, task_id)
    own_task = store.claim_task(user, "own-task", device)["task_id"]
    assert store.append_execution_event(user, device, connection_id, 1, "COLLECTION_STARTED", {}, own_task)["event_id"]


def test_database_enforces_task_and_device_connection_links(identities):
    admin, _, store, tenant, user, device, connection_id = identities
    different_device = store.register_device(user, "other-device")["device_id"]
    query = "INSERT INTO pilot_execution_events(event_id,tenant_id,device_id,connection_id,task_id,execution_generation,event_type) VALUES (%s,%s,%s,%s,%s,1,'COLLECTION_STARTED')"
    for event_device, task_id in ((device, str(uuid4())), (different_device, None)):
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            with admin.connect() as connection:
                connection.execute(query, (str(uuid4()), tenant, event_device, connection_id, task_id))


def test_application_role_cannot_read_another_tenant_devices(identities):
    _, database, _, tenant, _, _, _ = identities
    with database.connect() as connection:
        connection.execute("SELECT set_config('yike.tenant_id', %s, false)", (str(uuid4()),))
        assert connection.execute("SELECT count(*) FROM pilot_devices WHERE tenant_id=%s", (tenant,)).fetchone()[0] == 0


class _ObservedDatabase(PilotDatabase):
    @contextmanager
    def connect(self):
        with psycopg.connect(self.url, application_name="identity-revoke-race", connect_timeout=5) as connection:
            yield connection


@pytest.mark.parametrize("action", ["device", "connection"])
def test_event_waits_for_concurrent_revocation_and_fails_closed(identities, action):
    admin, database, _, tenant, user, device, connection_id = identities
    store = PilotStore(_ObservedDatabase(database.url))
    with ThreadPoolExecutor(max_workers=1) as executor:
        with admin.connect() as blocker:
            if action == "device":
                blocker.execute("UPDATE pilot_devices SET status='REVOKED' WHERE tenant_id=%s AND device_id=%s", (tenant, device))
            else:
                blocker.execute("UPDATE pilot_platform_connections SET status='DISCONNECTED' WHERE tenant_id=%s AND connection_id=%s", (tenant, connection_id))
            future = executor.submit(store.append_execution_event, user, device, connection_id, 1, "COLLECTION_STARTED", {})
            locked = False
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not future.done():
                with admin.connect() as observer:
                    locked = observer.execute("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name='identity-revoke-race' AND wait_event_type='Lock')").fetchone()[0]
                if locked:
                    break
                time.sleep(0.01)
            # Commit/rollback blocker before any assertion exits the executor.
            blocker.commit()
        with pytest.raises(ValueError, match="not active"):
            future.result(timeout=5)
        assert locked, "event did not lock the identity rows before checking revocation"
    with admin.connect() as connection:
        assert connection.execute("SELECT count(*) FROM pilot_execution_events WHERE tenant_id=%s", (tenant,)).fetchone()[0] == 0
