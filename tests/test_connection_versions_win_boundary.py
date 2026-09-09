"""Independent connection consumers; synthetic identities, restricted PostgreSQL."""
from fastapi.testclient import TestClient
import pytest

from pilot.connection_versions import ConnectionOperationError, ConnectionOperationStore
from pilot.web import build_app
from tests.test_connection_versions_postgres import databases, env, operation


def connection_snapshot(env):
    with env.admin.connect() as conn:
        return conn.execute(
            "SELECT connection_id,device_id,platform,account_public_id,session_ref,status,"
            "connection_version,disconnected_at FROM pilot_platform_connections "
            "WHERE tenant_id=%s ORDER BY connection_id", (env.tenant,)
        ).fetchall()


def disconnect_request(env, item, **changes):
    return operation(env, action="DISCONNECT", connection_id=item["connection_id"],
                     expected_connection_version=item["connection_version"], platform=None,
                     account_public_id=None, session_ref=None).model_copy(update=changes)


def test_same_owner_wrong_device_disconnect_is_durable_rejection_without_mutation(env):
    service = ConnectionOperationStore(env.database)
    item = service.apply(env.claims, operation(env))
    second_device = env.store.register_device(env.user, "synthetic-second")["device_id"]
    service.apply(env.claims, operation(env).model_copy(update={"device_id": second_device}))
    before = connection_snapshot(env)
    request = disconnect_request(env, item, device_id=second_device)

    result = service.apply(env.claims, request)

    assert result == dict(request_id=request.request_id, device_id=second_device,
                         action="DISCONNECT", state="REJECTED", connection_id=None,
                         connection_version=None, connection_status=None,
                         error_code="connection_unavailable")
    assert service.get_receipt(env.claims, request.request_id) == result
    assert service.apply(env.claims, request) == result
    assert connection_snapshot(env) == before


@pytest.mark.parametrize("wrong_binding", ["device", "platform"])
def test_current_checker_rejects_same_owner_wrong_binding_without_mutation(env, wrong_binding):
    service = ConnectionOperationStore(env.database)
    item = service.apply(env.claims, operation(env))
    second_device = env.store.register_device(env.user, "synthetic-second")["device_id"]
    second = service.apply(env.claims, operation(env).model_copy(update={"device_id": second_device}))
    # Trusted synthetic readiness only; this does not prove platform login.
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_platform_connections SET status='CONNECTED' WHERE connection_id=ANY(%s)",
                     ([item["connection_id"], second["connection_id"]],))
    before = connection_snapshot(env)
    arguments = dict(device_id=env.device, connection_id=item["connection_id"],
                     connection_version=2, platform="BILIBILI")
    with env.database.connect() as conn:
        assert service.lock_current(conn.cursor(), env.claims, **arguments)["connection_version"] == 2
        assert service.lock_current(conn.cursor(), env.claims, **(
            arguments | {"device_id": second_device, "connection_id": second["connection_id"]}
        ))["connection_version"] == 2
    if wrong_binding == "device":
        arguments.update(device_id=second_device)
    else:
        arguments.update(platform="DOUYIN")

    with env.database.connect() as conn:
        with pytest.raises(ConnectionOperationError, match="^connection_unavailable$"):
            service.lock_current(conn.cursor(), env.claims, **arguments)

    assert connection_snapshot(env) == before


@pytest.fixture
def client(env):
    app = build_app(env.store, auth_secret="synthetic-connection-test-secret")
    with TestClient(app, base_url="https://testserver") as client:
        client.headers.update({"Authorization": "Bearer " + env.token, "Origin": "https://testserver"})
        yield client


def post_operation(client, request):
    response = client.post("/api/ui/connection-operations", json=request.model_dump())
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "vault://" not in response.text
    return response.json()


def test_http_200_rejected_disconnect_preserves_current_connection(env, client):
    initial = post_operation(client, operation(env))
    current = post_operation(client, operation(env, expected_connection_version=1))
    before = connection_snapshot(env)
    request = disconnect_request(env, initial)

    rejected = post_operation(client, request)

    assert rejected == dict(request_id=request.request_id, device_id=env.device,
                           action="DISCONNECT", state="REJECTED",
                           connection_id=initial["connection_id"], connection_version=2,
                           connection_status="UNVERIFIED", error_code="connection_version_conflict")
    assert client.get("/api/ui/connection-operations/" + request.request_id).json() == rejected
    assert current["connection_id"] == initial["connection_id"]
    assert connection_snapshot(env) == before


def test_http_original_success_remains_historical_after_reconnect_and_disconnect(env, client):
    request = operation(env)
    original = post_operation(client, request)
    reconnected = post_operation(client, operation(env, expected_connection_version=1))
    disconnected = post_operation(client, disconnect_request(env, reconnected))
    before = connection_snapshot(env)

    queried = client.get("/api/ui/connection-operations/" + request.request_id)
    assert queried.status_code == 200
    assert queried.headers["cache-control"] == "no-store"
    assert queried.json() == original
    assert post_operation(client, request) == original
    current = client.get("/api/ui/connections").json()["items"]

    assert original["state"] == "SUCCEEDED" and original["connection_version"] == 1
    assert original["connection_status"] == "UNVERIFIED"
    assert disconnected["connection_version"] == 3 and disconnected["connection_status"] == "DISCONNECTED"
    assert len(current) == 1
    assert current[0]["connection_id"] == original["connection_id"]
    assert current[0]["connection_version"] == 3 and current[0]["status"] == "DISCONNECTED"
    assert connection_snapshot(env) == before
