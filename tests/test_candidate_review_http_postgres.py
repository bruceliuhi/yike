"""HTTP -> owned model worker -> restricted PostgreSQL, using synthetic sources.

The only provider is a local HTTP fixture. This is not platform collection,
buyer intent, paid-model quality, a send, or customer acceptance evidence.
"""
import copy
import json
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from pilot.auth import issue_token, verify_token_claims
from pilot.candidate_assessment_model import OpenAICompatibleCandidateAssessmentModel
from pilot.candidate_ingestion import CandidateIngestionStore
from pilot.candidate_review import _hash
from pilot.web import build_app
from tests.test_candidate_assessment_model import CONTENT, assessment
from tests.test_candidate_ingestion_http_postgres import started, signed
from tests.test_candidate_ingestion_postgres import payload
from tests.test_candidate_review_postgres import (
    execution_databases, execution_env, raw_databases, raw_env, databases, env, snapshot_reader,
)
from tests.test_execution_runtime_postgres import SECRET


@pytest.fixture
def local_provider():
    state = SimpleNamespace(requests=[], result=assessment(), http_status=200)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            state.requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            raw = json.dumps({"choices": [{"finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps(state.result, ensure_ascii=False)}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}}).encode()
            self.send_response(state.http_status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever)
    thread.start()
    try:
        state.model = OpenAICompatibleCandidateAssessmentModel(
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
            api_key="synthetic-test-only", model="synthetic-http-fixture", timeout_seconds=5)
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


def client_for(env, model, *, with_resolver=True):
    from pilot.candidate_review import CandidateReviewStore

    token = issue_token(env.claims.user_id, SECRET)
    claims = verify_token_claims(token, SECRET)
    review = CandidateReviewStore(env.db, model=model,
        strategy_resolver=env.resolver if with_resolver else None,
        strategy_snapshot_reader=snapshot_reader(env) if with_resolver else None)
    client = TestClient(build_app(env.store, auth_secret=SECRET, execution_runtime=env.runtime,
        candidate_ingestion=CandidateIngestionStore(env.db, env.runtime), candidate_review=review),
        base_url="https://pilot.example")
    client.headers["Authorization"] = "Bearer " + token
    return client, claims


def upload(client, env, claims, **changes):
    begun, lease = started(client, env, claims)
    raw = payload(env, begun, lease)
    raw["records"][0].update({"title": CONTENT["title"], "body": CONTENT["body"],
        "published_at": (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "observed_at": (datetime.now(UTC) - timedelta(seconds=10)).strftime("%Y-%m-%dT%H:%M:%SZ")} | changes)
    response = client.post("/api/ui/candidate-batches", json=signed(env, claims, raw))
    assert response.status_code == 200, response.text
    cid = response.json()["items"][0]["candidate_id"]
    listing = client.get("/api/ui/candidates", params={"ids": cid})
    assert listing.status_code == 200, listing.text
    candidate = listing.json()["items"][0]
    binding = {"candidateId": cid, "candidateRevision": candidate["revision"],
        "sourceVersionId": candidate["sourceVersionId"], "profileId": env.profile, "profileVersion": 1}
    return binding, candidate


def request(binding, action="ASSESS", **changes):
    return binding | {"action": action, "requestId": str(uuid4())} | changes


def verify(client, binding):
    value = binding | {"requestId": str(uuid4()), "humanConfirmed": True, "status": "OPEN",
        "openingMethod": "DIRECT", "locator": "https://example.com/synthetic",
        "excerpt": "采购输送设备", "contactMethod": "COMMENT"}
    response = client.post("/api/ui/candidate-source-verifications", json=value)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["kind"] == "sourceVerification"
    assert result["status"] == "OPEN"
    assert result["method"] == "HUMAN_REOPENED"
    assert result["binding"] == binding
    assert client.get("/api/ui/candidate-review-requests/" + value["requestId"]).json() == result
    return result


def test_http_owned_provider_assessment_is_not_approval_and_replay_does_not_call_again(env, local_provider):
    client, claims = client_for(env, local_provider.model)
    binding, before = upload(client, env, claims)
    assert before["status"] == "PENDING_REVIEW"
    assert before["sourceStatus"] == "UNVERIFIED"
    assert "assessment" not in before or before["assessment"] is None
    value = request(binding)
    result = client.post("/api/ui/candidate-reviews", json=value)
    assert result.status_code == 200, result.text
    assessed = result.json()
    assert assessed["kind"] == "assessment"
    assert assessed["requestId"] == value["requestId"]
    assert assessed["assessment"]["candidateRevision"] == binding["candidateRevision"]
    assert assessed["assessment"]["sourceVersionId"] == binding["sourceVersionId"]
    assert len(local_provider.requests) == 1
    assert local_provider.requests[0]["model"] == "synthetic-http-fixture"
    assert client.get("/api/ui/opportunities").json() == {"items": []}
    current = client.get("/api/ui/candidates", params={"ids": binding["candidateId"]}).json()["items"][0]
    assert current["status"] == "PENDING_REVIEW"
    assert current["sourceStatus"] == "UNVERIFIED"
    assert client.post("/api/ui/candidate-reviews", json=value).json() == assessed
    recovered = client.get("/api/ui/candidate-review-requests/" + value["requestId"])
    assert recovered.status_code == 200, recovered.text
    assert recovered.json() == assessed
    assert len(local_provider.requests) == 1
    changed = client.post("/api/ui/candidate-reviews", json=value | {"candidateRevision": 2})
    assert changed.status_code == 409
    assert len(local_provider.requests) == 1
    assert client.get("/api/ui/capabilities").json()["capabilities"]["task_execution"] == {"available": False}


def test_http_review_history_is_private_and_new_session_can_recover_without_model(env, local_provider, caplog):
    client, claims = client_for(env, local_provider.model)
    binding, _ = upload(client, env, claims)
    value = request(binding)
    response = client.post("/api/ui/candidate-reviews", json=value)
    assert response.status_code == 200, response.text
    path = "/api/ui/candidate-review-requests/" + value["requestId"]
    for user in env.users[1:]:
        foreign = {"Authorization": "Bearer " + issue_token(user, SECRET)}
        assert client.get(path, headers=foreign).status_code == 404
        assert client.get("/api/ui/candidates", headers=foreign).json()["total"] == 0
    other, _ = client_for(env, None, with_resolver=False)
    assert other.get(path).json() == response.json()
    assert len(local_provider.requests) == 1
    assert client.delete("/api/ui/session").status_code == 200
    assert client.get(path).status_code == 401
    assert other.get(path).status_code == 200
    assert "synthetic-test-only" not in caplog.text


def test_http_bad_model_quote_is_durable_failure_and_retry_must_be_explicit(env, local_provider, caplog):
    client, claims = client_for(env, local_provider.model)
    binding, _ = upload(client, env, claims)
    local_provider.result["intent"]["citations"][0]["quote"] = "synthetic-secret-not-in-source"
    value = request(binding)
    response = client.post("/api/ui/candidate-reviews", json=value)
    assert response.status_code == 200, response.text
    failed = response.json()
    assert failed["status"] == "FAILED"
    assert "synthetic-secret-not-in-source" not in response.text + caplog.text
    path = "/api/ui/candidate-review-requests/" + value["requestId"]
    assert client.get(path).json() == failed
    assert client.post("/api/ui/candidate-reviews", json=value).json() == failed
    assert client.post("/api/ui/candidate-reviews", json=request(binding)).status_code == 409
    assert len(local_provider.requests) == 1
    assert client.get("/api/ui/opportunities").json()["items"] == []
    local_provider.result = assessment()
    retry = request(binding, retryOf=value["requestId"])
    success = client.post("/api/ui/candidate-reviews", json=retry)
    assert success.status_code == 200, success.text
    assert success.json()["kind"] == "assessment"
    assert len(local_provider.requests) == 2
    assert client.get(path).json() == failed
    assert client.post("/api/ui/candidate-reviews", json=retry).json() == success.json()
    assert len(local_provider.requests) == 2


@pytest.mark.parametrize("reason", ["", "已自行打开原页，准备先确认现有产线。"])
def test_http_human_check_and_review_import_exact_words_with_durable_original_receipt(env, local_provider, reason):
    client, claims = client_for(env, local_provider.model)
    binding, _ = upload(client, env, claims)
    response = client.post("/api/ui/candidate-reviews", json=request(binding))
    assert response.status_code == 200, response.text
    assessed = response.json()["assessment"]
    check = verify(client, binding)
    assert check["checkedBy"] == claims.user_id
    evidence = copy.deepcopy(assessment()["evidence"])
    evidence["matchReason"] = "人工确认：本次只讨论输送设备安装，不能替客户假定已有预算。"
    value = request(binding, "INCLUDE", assessmentId=assessed["id"], evidence=evidence,
        reason=reason, humanConfirmed=True, sourceVerificationId=check["id"])
    response = client.post("/api/ui/candidate-reviews", json=value)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["kind"] == "decision"
    receipt = result["receipt"]
    assert (receipt["status"], receipt["outcome"]) == ("SUCCEEDED", "IMPORTED")
    assert receipt["reviewedBy"] == claims.user_id
    assert receipt["review"]["evidence"] == evidence
    assert receipt["review"]["reason"] == value["reason"]
    assert receipt["review"]["sourceVerificationId"] == check["id"]
    assert result["candidate"]["lastReview"] == receipt
    oid = receipt["opportunityId"]
    assert result["candidate"]["opportunityId"] == oid
    assert result["candidate"]["status"] == "IMPORTED"
    detail = client.get("/api/ui/opportunities/" + oid)
    assert detail.status_code == 200, detail.text
    opportunity = detail.json()["opportunity"]
    assert opportunity["source_status"] == "UNVERIFIED"
    assert opportunity["match_reason"] == evidence["matchReason"]
    assert opportunity["draft_comment"] == assessment()["draftComment"]
    assert opportunity["draft_dm"] == assessment()["draftDm"]
    assert opportunity["reviewed_by"] == claims.user_id
    assert len(client.get("/api/ui/opportunities").json()["items"]) == 1
    assert client.post("/api/ui/candidate-reviews", json=value).json() == result
    later_check = verify(client, binding)
    assert later_check["id"] != check["id"]
    assert client.post("/api/ui/candidate-reviews", json=value).json() == result
    conflict = client.post("/api/ui/candidate-reviews",
        json=value | {"sourceVerificationId": later_check["id"]})
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["detail"]["code"] == "request_conflict"
    changed_binding, current = upload(client, env, claims, body="原文已改：暂缓设备采购。",
        observed_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    assert changed_binding["candidateId"] == binding["candidateId"]
    assert changed_binding["candidateRevision"] > binding["candidateRevision"]
    assert current.get("assessment") is None
    path = "/api/ui/candidate-review-requests/" + value["requestId"]
    other, _ = client_for(env, None, with_resolver=False)
    assert other.get(path).json() == result
    historical = other.get("/api/ui/candidates", params={"ids": binding["candidateId"],
        "reviewRequestId": value["requestId"], "page": 1, "pageSize": 1})
    assert historical.status_code == 200, historical.text
    original = historical.json()["items"][0]
    assert original["lastReview"] == receipt
    assert original["revision"] == binding["candidateRevision"]
    assert len(local_provider.requests) == 1
    # Only this approved opportunity is tenant-shared, never raw private history.
    same_tenant = {"Authorization": "Bearer " + issue_token(env.users[1], SECRET)}
    foreign = {"Authorization": "Bearer " + issue_token(env.users[2], SECRET)}
    assert client.get("/api/ui/candidates", headers=same_tenant).json()["total"] == 0
    assert len(client.get("/api/ui/opportunities", headers=same_tenant).json()["items"]) == 1
    assert client.get("/api/ui/opportunities/" + oid, headers=foreign).status_code == 404


@pytest.mark.parametrize("verification_input", ["omitted", "null", "provided"])
def test_http_exclude_receipt_preserves_optional_verification_and_replays(env, local_provider, verification_input):
    client, claims = client_for(env, local_provider.model)
    binding, _ = upload(client, env, claims)
    assessed = client.post("/api/ui/candidate-reviews", json=request(binding))
    assert assessed.status_code == 200, assessed.text
    fields = {}
    if verification_input == "null":
        fields["sourceVerificationId"] = None
    elif verification_input == "provided":
        fields["sourceVerificationId"] = verify(client, binding)["id"]
    value = request(binding, "EXCLUDE", assessmentId=assessed.json()["assessment"]["id"],
        evidence=assessment()["evidence"], reason="人工排除：交付范围不适合。",
        humanConfirmed=True, **fields)
    response = client.post("/api/ui/candidate-reviews", json=value)
    assert response.status_code == 200, response.text
    result = response.json()
    receipt = result["receipt"]
    assert receipt["outcome"] == "EXCLUDED"
    assert receipt["review"]["sourceVerificationId"] == fields.get("sourceVerificationId")
    assert result["candidate"]["lastReview"] == receipt
    assert client.post("/api/ui/candidate-reviews", json=value).json() == result
    other, _ = client_for(env, None)
    assert other.get("/api/ui/candidate-review-requests/" + value["requestId"]).json() == result
    historical = other.get("/api/ui/candidates", params={"ids": binding["candidateId"],
        "reviewRequestId": value["requestId"], "page": 1, "pageSize": 1})
    assert historical.status_code == 200, historical.text
    assert historical.json()["items"][0]["lastReview"] == receipt
    assert client.get("/api/ui/opportunities").json()["items"] == []
    assert len(local_provider.requests) == 1


@pytest.mark.parametrize("action", ["INCLUDE", "EXCLUDE"])
def test_http_legacy_decision_receipt_is_not_backfilled_from_latest_verification(env, local_provider, action):
    client, claims = client_for(env, local_provider.model)
    binding, _ = upload(client, env, claims)
    assessed = client.post("/api/ui/candidate-reviews", json=request(binding))
    assert assessed.status_code == 200, assessed.text
    check = verify(client, binding)
    value = request(binding, action, assessmentId=assessed.json()["assessment"]["id"],
        evidence=assessment()["evidence"], reason="人工确认此范围。",
        humanConfirmed=True, sourceVerificationId=check["id"])
    response = client.post("/api/ui/candidate-reviews", json=value)
    assert response.status_code == 200, response.text
    legacy = response.json()
    assert legacy["receipt"]["review"]["sourceVerificationId"] == check["id"]
    original_request_id = value["requestId"]
    value = value | {"requestId": str(uuid4())}
    legacy["requestId"] = value["requestId"]
    legacy["receipt"]["requestId"] = value["requestId"]
    legacy["candidate"]["lastReview"]["requestId"] = value["requestId"]
    del legacy["receipt"]["review"]["sourceVerificationId"]
    del legacy["candidate"]["lastReview"]["review"]["sourceVerificationId"]
    # Trusted fixture insertion only: old-shaped evidence under a distinct request.
    # Preserve DB immutability and the real verification FK; never disable triggers.
    with env.admin.connect() as connection:
        inserted = connection.execute("""INSERT INTO pilot_candidate_review_requests
            (tenant_id,owner_user_id,request_id,candidate_id,fingerprint,action,binding_hash,
             snapshot_key,invocation_id,attempt,status,payload,snapshot,result)
            SELECT tenant_id,owner_user_id,%s,candidate_id,%s,action,binding_hash,
                snapshot_key,invocation_id,attempt,status,%s::jsonb,snapshot,%s::jsonb
            FROM pilot_candidate_review_requests
            WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s""",
            (value["requestId"], _hash(value), json.dumps(value), json.dumps(legacy),
             env.tenant, claims.user_id, original_request_id))
        assert inserted.rowcount == 1
        inserted = connection.execute("""INSERT INTO pilot_candidate_reviews
            (tenant_id,owner_user_id,request_id,binding_hash,assessment_id,verification_id,opportunity_id,result)
            SELECT tenant_id,owner_user_id,%s,binding_hash,assessment_id,verification_id,opportunity_id,%s::jsonb
            FROM pilot_candidate_reviews WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s""",
            (value["requestId"], json.dumps(legacy), env.tenant, claims.user_id, original_request_id))
        assert inserted.rowcount == 1
    later_check = verify(client, binding)
    assert later_check["id"] != check["id"]
    other, _ = client_for(env, None)
    replay = other.post("/api/ui/candidate-reviews", json=value)
    assert replay.status_code == 200, replay.text
    assert replay.json() == legacy
    assert other.get("/api/ui/candidate-review-requests/" + value["requestId"]).json() == legacy
    for params in ({"ids": binding["candidateId"]}, {"ids": binding["candidateId"],
            "reviewRequestId": value["requestId"], "page": 1, "pageSize": 1}):
        page = other.get("/api/ui/candidates", params=params)
        assert page.status_code == 200, page.text
        assert page.json()["items"][0]["lastReview"] == legacy["receipt"]
    assert len(local_provider.requests) == 1
