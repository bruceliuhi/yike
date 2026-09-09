"""Real HTTP/signature/restricted-PG path, with synthetic strategy/source only."""
import copy
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from pilot.auth import issue_token, verify_token_claims
from pilot.candidate_contract import validate_candidate_batch
from pilot.candidate_ingestion import CandidateIngestionStore
from pilot.execution_runtime import submission_signing_payload
from pilot.web import build_app
from tests.test_candidate_ingestion_postgres import (
    execution_databases, execution_env, databases, env, payload, TABLES,
)
from tests.test_device_keys import encoded
from tests.test_execution_http_postgres import send
from tests.test_execution_runtime_postgres import SECRET, start, operation


def http_client(env, *, runtime=True):
    token = issue_token(env.claims.user_id, SECRET)
    claims = verify_token_claims(token, SECRET)
    service = CandidateIngestionStore(env.db, env.runtime if runtime else None)
    client = TestClient(build_app(env.store, auth_secret=SECRET, execution_runtime=env.runtime,
                                 candidate_ingestion=service), base_url="https://pilot.example")
    client.headers["Authorization"] = "Bearer " + token
    return client, claims


def started(client, env, claims):
    result = send(client, env, claims, start(env))
    assert result.status_code == 200, result.text
    begun = result.json()
    result = send(client, env, claims, operation(env, "CLAIM", begun))
    assert result.status_code == 200, result.text
    return begun, result.json()


def signed(env, claims, value):
    dto = validate_candidate_batch(value, now=datetime.now(UTC))
    signature = encoded(env.key.sign(submission_signing_payload(
        tenant_id=env.tenant, claims=claims, batch=dto).encode()).signature)
    return {"batch": value, "signature": signature}


def test_raw_candidate_upload_read_replay_conflict_and_cancelled_history(env):
    client, claims = http_client(env)
    begun, lease = started(client, env, claims)
    raw = payload(env, begun, lease, request_id="http:opaque.batch-1")
    body = signed(env, claims, raw)
    response = client.post("/api/ui/candidate-batches", json=body)
    assert response.status_code == 200, response.text
    receipt = response.json()
    assert receipt["schema_version"] == "candidate-receipt-v1"
    assert receipt["accepted_count"] == 1
    assert receipt["request_id"] == raw["request_id"]
    candidate_id = receipt["items"][0]["candidate_id"]
    response = client.get("/api/ui/raw-candidates", params={"task_id": begun["task_id"]})
    assert response.status_code == 200, response.text
    assert response.json()["schema_version"] == "candidate-inbox-v1"
    assert response.json()["total"] == 1
    candidate = response.json()["items"][0]
    assert candidate["candidate_id"] == candidate_id
    assert candidate["status"] == "UNVERIFIED"
    assert candidate["current_version"]["published_at"] is None
    assert candidate["current_version"]["body"] == raw["records"][0]["body"]
    detail = client.get("/api/ui/raw-candidates/" + candidate_id).json()
    assert detail["candidate"] == candidate
    assert detail["observations"]["total"] == 1
    assert detail["observations"]["items"][0]["task_id"] == begun["task_id"]
    assert client.post("/api/ui/candidate-batches", json=body).json() == receipt
    changed = copy.deepcopy(raw)
    changed["records"][0]["body"] = "Changed synthetic body"
    conflict = client.post("/api/ui/candidate-batches", json=signed(env, claims, changed))
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "request_conflict"
    assert send(client, env, claims, operation(env, "CANCEL", begun)).status_code == 200

    # Recreated service/session retrieves original immutable facts after cancel;
    # even an old signature is not treated as a fresh execution authorization.
    other, _ = http_client(env, runtime=False)
    path = "/api/ui/candidate-batches/" + lease["platform_run_id"] + "/" + raw["request_id"]
    assert other.get(path).json() == receipt
    assert other.post("/api/ui/candidate-batches", json=body).json() == receipt
    assert other.get("/api/ui/raw-candidates/" + candidate_id).json()["observations"]["total"] == 1
    assert client.get("/api/ui/execution-tasks/" + begun["task_id"]).json()["records_used"] == 1
    assert client.get("/api/ui/capabilities").json()["capabilities"]["task_execution"] == {"available": False}


def test_http_foreign_owner_revoked_session_and_bad_signatures_leave_no_rows(env, caplog):
    client, claims = http_client(env)
    begun, lease = started(client, env, claims)
    raw = payload(env, begun, lease)
    body = signed(env, claims, raw)
    bad = client.post("/api/ui/candidate-batches", json=body | {"signature": "A" * 86})
    assert bad.status_code == 400
    assert bad.json()["detail"]["code"] == "invalid_proof"
    assert client.get("/api/ui/raw-candidates").json()["total"] == 0
    assert client.get("/api/ui/execution-tasks/" + begun["task_id"]).json()["records_used"] == 0
    forged = copy.deepcopy(body)
    forged["batch"]["execution"]["credential_version"] = True
    assert client.post("/api/ui/candidate-batches", json=forged).status_code == 422
    response = client.post("/api/ui/candidate-batches", json=body)
    assert response.status_code == 200, response.text
    receipt = response.json()
    cid = receipt["items"][0]["candidate_id"]
    for user in env.users[1:]:
        foreign = {"Authorization": "Bearer " + issue_token(user, SECRET)}
        assert client.get("/api/ui/raw-candidates", headers=foreign).json()["total"] == 0
        assert client.get("/api/ui/raw-candidates/" + cid, headers=foreign).status_code == 404
        path = "/api/ui/candidate-batches/" + lease["platform_run_id"] + "/" + raw["request_id"]
        assert client.get(path, headers=foreign).status_code == 404
    assert client.delete("/api/ui/session").status_code == 200
    assert client.post("/api/ui/candidate-batches", json=body).status_code == 401
    assert client.get("/api/ui/raw-candidates/" + cid).status_code == 401
    assert body["signature"] not in caplog.text


def test_http_new_batch_after_cancel_fails_without_new_source_or_budget(env):
    client, claims = http_client(env)
    begun, lease = started(client, env, claims)
    raw = payload(env, begun, lease)
    assert send(client, env, claims, operation(env, "CANCEL", begun)).status_code == 200
    result = client.post("/api/ui/candidate-batches", json=signed(env, claims, raw))
    assert result.status_code == 409
    assert result.json()["detail"]["code"] == "task_cancelled"
    with env.admin.connect() as connection:
        for table in TABLES:
            assert connection.execute(f"SELECT count(*) FROM {table} WHERE tenant_id=%s", (env.tenant,)).fetchone()[0] == 0
    assert client.get("/api/ui/execution-tasks/" + begun["task_id"]).json()["records_used"] == 0
    missing = client.get("/api/ui/candidate-batches/" + lease["platform_run_id"] + "/not-submitted")
    assert missing.status_code == 404
