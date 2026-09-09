"""Actual HTTPS app/Ed25519/restricted-PG roundtrip, synthetic strategy only."""
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from pilot.auth import issue_token, verify_token_claims
from pilot.execution_contract import ExecutionRuntimeError
from pilot.execution_runtime import ExecutionRuntime, execution_signing_payload
from pilot.web import build_app
from tests.test_device_keys import encoded
from tests.test_execution_runtime_postgres import (
    SECRET, databases, env, start, operation, batch, guard,
)


def http_client(env, runtime):
    token = issue_token(env.claims.user_id, SECRET)
    claims = verify_token_claims(token, SECRET)
    client = TestClient(build_app(env.store, auth_secret=SECRET, execution_runtime=runtime),
                        base_url="https://pilot.example")
    client.headers["Authorization"] = "Bearer " + token
    return client, claims


def send(client, env, claims, request):
    signature = encoded(env.key.sign(execution_signing_payload(
        tenant_id=env.tenant, claims=claims, operation=request).encode()).signature)
    return client.post("/api/ui/execution-operations", json={
        "request": request.model_dump(mode="json"), "signature": signature,
    })


def test_start_claim_cancel_and_original_receipt_survive_server_recreation(env):
    client, claims = http_client(env, env.runtime)
    request = start(env)
    response = send(client, env, claims, request)
    assert response.status_code == 200, response.text
    begun = response.json()
    assert begun["status"] == "PENDING"
    assert send(client, env, claims, request).json() == begun
    lease_request = operation(env, "CLAIM", begun)
    response = send(client, env, claims, lease_request)
    assert response.status_code == 200, response.text
    lease = response.json()
    assert lease["execution_generation"] == 1
    candidate = batch(env, begun, lease)
    with env.db.connect() as connection:
        assert guard(env, connection.cursor(), candidate)["remaining_records"] == 2

    # A different web/runtime instance uses persistent rows, not process state.
    recreated = ExecutionRuntime(env.db, strategy_resolver=env.resolver,
                                 capability_check=lambda *args: True)
    second, second_claims = http_client(env, recreated)
    cancel = operation(env, "CANCEL", begun)
    response = send(second, env, second_claims, cancel)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CANCELLING"
    assert response.json()["stop_confirmed"] is False
    assert second.get("/api/ui/execution-tasks/" + begun["task_id"]).json()["status"] == "CANCELLING"
    assert second.get("/api/ui/execution-operations/" + request.request_id).json() == begun
    assert second.get("/api/ui/execution-operations/" + lease_request.request_id).json() == lease
    with pytest.raises(ExecutionRuntimeError, match="task_cancelled"):
        with env.db.connect() as connection:
            guard(env, connection.cursor(), candidate)
    assert second.get("/api/ui/capabilities").json()["capabilities"]["task_execution"] == {"available": False}


def test_http_missing_real_strategy_or_foreign_owner_cannot_create_execution(env):
    client, claims = http_client(env, ExecutionRuntime(env.db))
    response = send(client, env, claims, start(env))
    assert response.status_code == 501
    assert response.json()["detail"]["code"] == "capability_unavailable"
    with env.admin.connect() as connection:
        assert connection.execute("SELECT count(*) FROM pilot_collection_tasks WHERE tenant_id=%s",
                                  (env.tenant,)).fetchone()[0] == 0
    client, claims = http_client(env, env.runtime)
    begun = send(client, env, claims, start(env)).json()
    client.headers["Authorization"] = "Bearer " + issue_token(env.users[1], SECRET)
    response = client.get("/api/ui/execution-tasks/" + begun["task_id"])
    assert response.status_code == 404
    assert begun["task_id"] not in response.text
    assert client.get("/api/ui/execution-operations/" + str(uuid4())).status_code == 404
