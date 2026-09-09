"""Actual ASGI/Ed25519/restricted PG; synthetic source inputs, not platform proof."""
import copy
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from pilot.auth import issue_token, verify_token_claims
from pilot.candidate_ingestion import CandidateIngestionStore
from pilot.web import build_app
from tests.test_candidate_ingestion_postgres import TABLES, payload
from tests.test_confirmed_strategy_review_postgres import (
    databases, env, execution_databases, execution_env, raw_databases, raw_env,
    real_strategy_env,
)
from tests.test_device_keys import encoded
from tests.test_device_credentials_postgres import wait_for_lock
from tests.test_execution_runtime_postgres import SECRET, operation, start
from tests.test_execution_signing_payload_http_postgres import execution_counts, prepare, submit
from tests.test_research_strategies_postgres import revoke_body

PATH = "/api/ui/candidate-submission-signing-payload"


def client_for(env, *, token=None, with_runtime=True):
    app = build_app(env.store, auth_secret=SECRET, execution_runtime=env.runtime,
        candidate_ingestion=CandidateIngestionStore(env.db, env.runtime if with_runtime else None),
        research_strategies=env.strategies)
    client = TestClient(app, base_url="https://pilot.example")
    client.headers["Authorization"] = "Bearer " + (token or issue_token(env.claims.user_id, SECRET))
    return client


def execute(client, env, request):
    response = submit(client, env.key, request, prepare(client, request))
    assert response.status_code == 200, response.text
    return response.json()


def batch_for(client, env):
    begun = execute(client, env, start(env))
    lease = execute(client, env, operation(env, "CLAIM", begun))
    return payload(env, begun, lease), begun


def prepare_candidate(client, value):
    response = client.post(PATH, json={"batch": value})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def upload(client, key, value, prepared):
    return client.post("/api/ui/candidate-batches", json={"batch": value,
        "signature": encoded(key.sign(prepared["signing_payload"].encode("utf-8")).signature)})


def facts(env):
    # Trusted test inspector, not an unscoped RLS query that always returns empty.
    with env.admin.connect() as connection:
        counts = {table: connection.execute(
            f"SELECT count(*) FROM {table} WHERE tenant_id=%s", (env.tenant,)
        ).fetchone()[0] for table in TABLES}
        leases = connection.execute("SELECT platform_run_id,records_used,lease_id,"
            "execution_generation,lease_expires_at FROM pilot_collection_platform_runs "
            "WHERE tenant_id=%s ORDER BY platform_run_id", (env.tenant,)).fetchall()
    return counts, execution_counts(env), leases


def test_candidate_client_signs_response_uploads_and_recovers_without_internal_identity(real_strategy_env):
    env = real_strategy_env
    client = client_for(env)
    value, begun = batch_for(client, env)
    value["records"][0]["body"] = "  企业知识库与销售 Agent\n保留原文 😀  "
    before = facts(env)
    prepared = prepare_candidate(client, value)
    assert set(prepared) == {"signing_payload", "request_id", "device_id",
        "credential_version", "batch_fingerprint"}
    canonical = json.dumps({k: v for k, v in value.items() if k != "request_id"},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert prepared["batch_fingerprint"] == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert (prepared["request_id"], prepared["device_id"], prepared["credential_version"]) == (
        value["request_id"], value["execution"]["device_id"], 1)
    proof = json.loads(prepared["signing_payload"])
    assert proof["protocol"] == "yike-candidate-submission-v1"
    assert proof["batch_fingerprint"] == prepared["batch_fingerprint"]
    assert proof["request_id"] == value["request_id"]
    equivalent = dict(reversed(list(value.items())))
    assert prepare_candidate(client, equivalent) == prepared
    equivalent = copy.deepcopy(value)
    equivalent["execution"] = {k: v for k, v in value["execution"].items()
        if k != "connection_version"}
    assert prepare_candidate(client, equivalent) == prepared
    assert facts(env) == before
    response = upload(client, env.key, value, prepared)
    assert response.status_code == 200, response.text
    receipt = response.json()
    assert receipt["accepted_count"] == 1
    assert upload(client, env.key, value, prepared).json() == receipt
    path = f'/api/ui/candidate-batches/{receipt["platform_run_id"]}/{receipt["request_id"]}'
    assert client.get(path).json() == receipt
    detail = client.get("/api/ui/raw-candidates/" + receipt["items"][0]["candidate_id"]).json()
    assert detail["candidate"]["current_version"]["body"] == value["records"][0]["body"]
    assert env.runtime.get_task(env.claims, begun["task_id"])["records_used"] == 1


def test_preparation_neither_calls_source_nor_writes_execution_and_accepts_empty_batch(real_strategy_env, monkeypatch):
    env = real_strategy_env
    client = client_for(env)
    value, _ = batch_for(client, env)
    before = facts(env)

    def forbidden(*args, **kwargs):
        pytest.fail("preparation must not acquire execution authority or call source")

    for name in ("_submission", "lock_submission", "_strategy", "_connection",
                 "_locks", "strategy_resolver", "capability_check"):
        monkeypatch.setattr(env.runtime, name, forbidden)
    prepare_candidate(client, value)
    empty = copy.deepcopy(value)
    empty["records"] = []
    assert prepare_candidate(client, empty)["batch_fingerprint"] != prepare_candidate(client, value)["batch_fingerprint"]
    assert facts(env) == before


@pytest.mark.parametrize("case,status,code", [
    ("other_owner", 404, "device_unavailable"),
    ("other_tenant", 404, "device_unavailable"),
    ("missing_device", 404, "device_unavailable"),
    ("revoked_device", 404, "device_unavailable"),
    ("old_credential", 409, "credential_conflict"),
])
def test_preparation_requires_current_owner_device(real_strategy_env, case, status, code):
    env = real_strategy_env
    owner = client_for(env)
    value, _ = batch_for(owner, env)
    user = env.users[1] if case == "other_owner" else env.users[2] if case == "other_tenant" else env.users[0]
    client = client_for(env, token=issue_token(user, SECRET))
    if case == "missing_device":
        value["execution"]["device_id"] = str(uuid4())
    if case == "revoked_device":
        env.store.revoke_device(env.users[0], env.device)
    if case == "old_credential":
        value["execution"]["credential_version"] = 2
    before = facts(env)
    response = client.post(PATH, json={"batch": value})
    assert response.status_code == status, response.text
    assert response.json()["detail"]["code"] == code
    assert "signing_payload" not in response.text
    assert facts(env) == before


def test_new_session_rejects_old_signature_but_history_survives_device_revocation(real_strategy_env):
    env = real_strategy_env
    client = client_for(env)
    value, _ = batch_for(client, env)
    prepared = prepare_candidate(client, value)
    fresh = client_for(env)
    current = prepare_candidate(fresh, value)
    assert current["batch_fingerprint"] == prepared["batch_fingerprint"]
    assert current["signing_payload"] != prepared["signing_payload"]
    before = facts(env)
    response = upload(fresh, env.key, value, prepared)
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "invalid_proof"
    assert facts(env) == before
    accepted = upload(fresh, env.key, value, current)
    assert accepted.status_code == 200, accepted.text
    receipt = accepted.json()
    env.store.revoke_device(env.users[0], env.device)
    assert fresh.post(PATH, json={"batch": value}).status_code == 404
    recovered = client_for(env, with_runtime=False)
    before_replay = facts(env)
    assert recovered.get(f'/api/ui/candidate-batches/{receipt["platform_run_id"]}/{receipt["request_id"]}').json() == receipt
    assert upload(recovered, env.key, value, prepared).json() == receipt
    assert facts(env) == before_replay


@pytest.mark.parametrize("field", ["request_id", "body", "lease_id"])
def test_changed_batch_cannot_reuse_prepared_signature(real_strategy_env, field):
    env = real_strategy_env
    client = client_for(env)
    value, _ = batch_for(client, env)
    prepared = prepare_candidate(client, value)
    changed = copy.deepcopy(value)
    if field == "request_id":
        changed[field] = str(uuid4())
    elif field == "body":
        changed["records"][0][field] += " changed"
    else:
        changed["execution"][field] = str(uuid4())
    before = facts(env)
    rejected = upload(client, env.key, changed, prepared)
    assert rejected.status_code == 400, rejected.text
    assert rejected.json()["detail"]["code"] == "invalid_proof"
    assert facts(env) == before


@pytest.mark.parametrize("case,code", [
    ("cancel", "task_cancelled"), ("strategy", "strategy_conflict"),
    ("lease", "lease_expired"), ("budget", "budget_exhausted"),
])
def test_preparation_does_not_preapprove_new_upload(real_strategy_env, case, code):
    env = real_strategy_env
    client = client_for(env)
    value, begun = batch_for(client, env)
    prepared = prepare_candidate(client, value)
    if case == "cancel":
        execute(client, env, operation(env, "CANCEL", begun))
    elif case == "strategy":
        response = client.post("/api/ui/research-strategies/revoke", json=revoke_body(env.confirmed))
        assert response.status_code == 200, response.text
    else:
        with env.admin.connect() as connection:
            if case == "lease":
                connection.execute("UPDATE pilot_collection_platform_runs SET lease_expires_at="
                    "clock_timestamp()-interval '1 second' WHERE platform_run_id=%s",
                    (value["execution"]["platform_run_id"],))
            else:
                connection.execute("UPDATE pilot_collection_platform_runs SET records_used=%s "
                    "WHERE platform_run_id=%s", (env.snapshot["max_records"], value["execution"]["platform_run_id"]))
    before = facts(env)
    assert prepare_candidate(client, value) == prepared
    rejected = upload(client, env.key, value, prepared)
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["detail"]["code"] == code
    assert facts(env) == before


@pytest.mark.parametrize("case", ["bool_version", "missing_connection_id", "too_many", "future_time", "duplicate", "unsafe_url"])
def test_preparation_validates_batch_with_database_clock(real_strategy_env, case, caplog):
    env = real_strategy_env
    client = client_for(env)
    value, _ = batch_for(client, env)
    value["records"][0]["body"] = "synthetic-private-body-marker"
    if case == "bool_version":
        value["execution"]["credential_version"] = True
    elif case == "missing_connection_id":
        del value["execution"]["connection_id"]
    elif case == "too_many":
        value["records"] *= 101
    elif case == "future_time":
        value["records"][0]["observed_at"] = "2999-01-01T00:00:00Z"
    elif case == "duplicate":
        value["records"] *= 2
    else:
        value["records"][0]["public_url"] = "https://example.com/?token=synthetic-private-token-marker"
    before = facts(env)
    response = client.post(PATH, json={"batch": value})
    assert response.status_code == 422, response.text
    assert "signing_payload" not in response.text
    assert "synthetic-private-" not in response.text + caplog.text
    assert facts(env) == before


def test_preparation_with_missing_runtime_remains_unavailable(real_strategy_env):
    env = real_strategy_env
    value, _ = batch_for(client_for(env), env)
    before = facts(env)
    response = client_for(env, with_runtime=False).post(PATH, json={"batch": value})
    assert response.status_code == 501, response.text
    assert response.json()["detail"]["code"] == "capability_unavailable"
    assert facts(env) == before


def test_preparation_rechecks_session_after_real_device_lock_wait(real_strategy_env):
    env = real_strategy_env
    value, _ = batch_for(client_for(env), env)
    token = issue_token(env.users[0], SECRET, ttl_seconds=3)
    deadline = verify_token_claims(token, SECRET).expires_at
    client = client_for(env, token=token)
    before = facts(env)
    with ThreadPoolExecutor(1) as pool:
        with env.admin.connect() as blocker:
            blocker.execute("SELECT 1 FROM pilot_devices WHERE device_id=%s FOR UPDATE", (env.device,))
            future = pool.submit(client.post, PATH, json={"batch": value})
            wait_for_lock(env.admin, "pilot_devices")
            while time.time() <= deadline:
                time.sleep(0.01)
        response = future.result(timeout=5)
    assert response.status_code == 401, response.text
    assert response.json()["detail"]["code"] == "invalid_session"
    assert "signing_payload" not in response.text
    assert facts(env) == before
