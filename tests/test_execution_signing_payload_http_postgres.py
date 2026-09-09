"""Actual authenticated preparation/Ed25519/PG; synthetic source policy, not collection."""
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from pilot.auth import issue_token, verify_token_claims
from pilot.web import build_app
from tests.test_confirmed_strategy_http_postgres import (
    databases, env, execution_databases, execution_env, raw_databases, raw_env,
    real_strategy_env,
)
from tests.test_device_keys import encoded
from tests.test_device_credentials_postgres import wait_for_lock
from tests.test_execution_runtime_postgres import SECRET, TABLES, operation, start
from tests.test_research_strategies_postgres import revoke_body


def client_for(env, *, runtime=None, token=None):
    app = build_app(env.store, auth_secret=SECRET,
        execution_runtime=runtime or env.runtime, research_strategies=env.strategies)
    client = TestClient(app, base_url="https://pilot.example")
    client.headers["Authorization"] = "Bearer " + (token or issue_token(env.claims.user_id, SECRET))
    return client


def prepare(client, request):
    response = client.post("/api/ui/execution-signing-payload",
        json={"request": request.model_dump(mode="json")})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def submit(client, key, request, prepared):
    return client.post("/api/ui/execution-operations", json={
        "request": request.model_dump(mode="json"),
        "signature": encoded(key.sign(prepared["signing_payload"].encode("utf-8")).signature),
    })


def execution_counts(env):
    # Trusted test inspection, not an RLS-empty unscoped application query.
    with env.admin.connect() as connection:
        return {table: connection.execute(
            f"SELECT count(*) FROM {table} WHERE tenant_id=%s", (env.tenant,)
        ).fetchone()[0] for table in TABLES + ("pilot_device_key_requests",)}


def test_client_signs_server_bytes_without_constructing_session_context(real_strategy_env):
    env = real_strategy_env
    client = client_for(env)
    request = start(env)
    prepared = prepare(client, request)
    assert set(prepared) == {"signing_payload", "request_id", "device_id",
        "credential_version", "request_sha256"}
    canonical = json.dumps(request.model_dump(mode="json"), ensure_ascii=False,
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    assert prepared["request_sha256"] == hashlib.sha256(canonical).hexdigest()
    assert prepared["request_id"] == request.request_id
    assert prepared["device_id"] == env.device
    assert prepared["credential_version"] == 1
    assert json.loads(prepared["signing_payload"])["operation"] == request.model_dump(mode="json")
    assert prepare(client, request) == prepared
    applied = submit(client, env.key, request, prepared)
    assert applied.status_code == 200, applied.text
    assert applied.json()["status"] == "PENDING"


def test_preparation_creates_no_execution_or_challenge_and_calls_no_source(real_strategy_env, monkeypatch):
    env = real_strategy_env
    client = client_for(env)
    original = execution_counts(env)
    assert original["pilot_device_key_requests"] > 0

    def forbidden(*args, **kwargs):
        pytest.fail("preparation must not call task/strategy/connection/source code")

    for name in ("_strategy", "_connection", "_start", "_mutate", "_locks",
                 "strategy_resolver", "capability_check"):
        monkeypatch.setattr(env.runtime, name, forbidden)
    requests = [start(env)]
    synthetic_task = {"task_id": str(uuid4()), "platform_runs": [{"platform_run_id": str(uuid4())}]}
    requests += [operation(env, "CLAIM", synthetic_task),
        operation(env, "RENEW", synthetic_task, lease_id=str(uuid4()), execution_generation=1),
        operation(env, "CANCEL", synthetic_task)]
    for request in requests:
        assert prepare(client, request) == prepare(client, request)
    assert execution_counts(env) == original
    assert client.get("/api/ui/capabilities").json()["capabilities"]["task_execution"] == {"available": False}


@pytest.mark.parametrize("case,status,code", [
    ("other_owner", 404, "device_unavailable"),
    ("other_tenant", 404, "device_unavailable"),
    ("revoked_device", 404, "device_unavailable"),
    ("old_credential", 409, "credential_conflict"),
    ("missing_device", 404, "device_unavailable"),
])
def test_preparation_rejects_wrong_device_owner_and_version(real_strategy_env, case, status, code):
    env = real_strategy_env
    user = env.users[1] if case == "other_owner" else env.users[2] if case == "other_tenant" else env.claims.user_id
    client = client_for(env, token=issue_token(user, SECRET))
    request = start(env)
    if case == "revoked_device":
        with env.admin.connect() as connection:
            connection.execute("UPDATE pilot_devices SET status='REVOKED' WHERE device_id=%s", (env.device,))
    if case == "old_credential":
        with env.admin.connect() as connection:
            connection.execute("UPDATE pilot_device_credentials SET credential_version=2 WHERE device_id=%s", (env.device,))
    if case == "missing_device":
        request = request.model_copy(update={"device_id": str(uuid4())})
    original = execution_counts(env)
    response = client.post("/api/ui/execution-signing-payload", json={"request": request.model_dump(mode="json")})
    assert response.status_code == status, response.text
    assert response.json()["detail"]["code"] == code
    assert "signing_payload" not in response.text
    assert execution_counts(env) == original


def test_new_session_rejects_old_signature_for_new_work_but_reads_history(real_strategy_env):
    env = real_strategy_env
    client = client_for(env)
    request = start(env)
    previous = prepare(client, request)
    assert client.delete("/api/ui/session").status_code == 200
    assert client.post("/api/ui/execution-signing-payload", json={"request": request.model_dump(mode="json")}).status_code == 401
    fresh = client_for(env)
    current = prepare(fresh, request)
    assert current["request_sha256"] == previous["request_sha256"]
    assert current["signing_payload"] != previous["signing_payload"]
    before = execution_counts(env)
    rejected = submit(fresh, env.key, request, previous)
    assert rejected.status_code == 400
    assert rejected.json()["detail"]["code"] == "invalid_proof"
    assert execution_counts(env) == before
    accepted = submit(fresh, env.key, request, current)
    assert accepted.status_code == 200, accepted.text
    receipt = accepted.json()
    newest = client_for(env)
    assert newest.get("/api/ui/execution-operations/" + request.request_id).json() == receipt
    # A known successful UUID returns history, not new authority or a second task.
    assert submit(newest, env.key, request, previous).json() == receipt
    assert execution_counts(env)["pilot_collection_tasks"] == before["pilot_collection_tasks"] + 1


def test_signed_claim_renew_and_cancel_survive_strategy_revocation(real_strategy_env):
    env = real_strategy_env
    client = client_for(env)

    def execute(request):
        response = submit(client, env.key, request, prepare(client, request))
        assert response.status_code == 200, response.text
        return response.json()

    begun = execute(start(env))
    lease = execute(operation(env, "CLAIM", begun))
    renewal = operation(env, "RENEW", begun,
        lease_id=lease["lease_id"], execution_generation=lease["execution_generation"])
    renewed = execute(renewal)
    assert renewed["lease_id"] == lease["lease_id"]
    response = client.post("/api/ui/research-strategies/revoke", json=revoke_body(env.confirmed))
    assert response.status_code == 200
    cancelled = execute(operation(env, "CANCEL", begun))
    assert cancelled["status"] == "CANCELLING"
    assert cancelled["stop_confirmed"] is False
    assert client.get("/api/ui/execution-operations/" + renewal.request_id).json() == renewed


def test_normal_cli_preparation_does_not_enable_unavailable_source(monkeypatch, real_strategy_env):
    from tests.test_pilot_runtime_http_postgres import ordinary_client
    env = real_strategy_env
    with ordinary_client(monkeypatch, env) as client:
        request = start(env)
        original = execution_counts(env)
        prepared = prepare(client, request)
        denied = submit(client, env.key, request, prepared)
        assert denied.status_code == 501
        assert denied.json()["detail"]["code"] == "capability_unavailable"
        assert execution_counts(env) == original
        assert client.get("/api/ui/capabilities").json()["capabilities"]["task_execution"] == {"available": False}


def test_preparation_rechecks_session_after_actual_device_lock_wait(real_strategy_env):
    env = real_strategy_env
    token = issue_token(env.claims.user_id, SECRET, ttl_seconds=3)
    deadline = verify_token_claims(token, SECRET).expires_at
    client = client_for(env, token=token)
    request = start(env)
    with ThreadPoolExecutor(1) as pool:
        with env.admin.connect() as blocker:
            blocker.execute("SELECT 1 FROM pilot_devices WHERE device_id=%s FOR UPDATE", (env.device,))
            future = pool.submit(client.post, "/api/ui/execution-signing-payload",
                json={"request": request.model_dump(mode="json")})
            wait_for_lock(env.admin, "pilot_devices")
            while time.time() <= deadline:
                time.sleep(0.01)
        response = future.result(timeout=5)
    assert response.status_code == 401, response.text
    assert response.json()["detail"]["code"] == "invalid_session"
    assert "signing_payload" not in response.text
