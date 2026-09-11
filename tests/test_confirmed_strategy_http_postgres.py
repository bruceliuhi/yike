"""Shared authenticated signed chain on restricted PG; sources/provider are synthetic."""
import copy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from pilot.auth import issue_token
from pilot.candidate_ingestion import CandidateIngestionStore
from pilot.candidate_review import CandidateReviewStore
from pilot.web import build_app
from tests.test_candidate_assessment_model import CONTENT, assessment
from tests.test_candidate_ingestion_postgres import payload
from tests.test_candidate_review_http_postgres import local_provider
from tests.test_candidate_review_postgres import review_payload, verification_payload
from tests.test_confirmed_strategy_review_postgres import (
    BoundedDatabase,
    databases,
    env,
    execution_databases,
    execution_env,
    raw_databases,
    raw_env,
    real_strategy_env,
)
from tests.test_device_keys import encoded
from tests.test_execution_runtime_postgres import SECRET, operation, start
from tests.test_research_strategies_postgres import confirm_body, prepare_body, revoke_body


def send_execution(client, env, request):
    response = client.post("/api/ui/execution-signing-payload",
        json={"request": request.model_dump(mode="json")})
    assert response.status_code == 200, response.text
    prepared = response.json()
    signature = encoded(env.key.sign(prepared["signing_payload"].encode("utf-8")).signature)
    return client.post("/api/ui/execution-operations", json={
        "request": request.model_dump(mode="json"), "signature": signature,
    })


def send_candidate(client, key, value):
    response = client.post("/api/ui/candidate-submission-signing-payload", json={"batch": value})
    assert response.status_code == 200, response.text
    prepared = response.json()
    signature = encoded(key.sign(prepared["signing_payload"].encode("utf-8")).signature)
    return client.post("/api/ui/candidate-batches", json={"batch": value, "signature": signature})


def test_shared_http_actual_strategy_signed_review_and_revocation_chain(real_strategy_env, local_provider):
    env = real_strategy_env
    token = issue_token(env.claims.user_id, SECRET)
    review = CandidateReviewStore(BoundedDatabase(env.db), model=local_provider.model,
        strategy_resolver=env.strategies.resolve,
        strategy_snapshot_reader=env.strategies.read_snapshot)
    ingestion = CandidateIngestionStore(env.db, env.runtime)
    app = build_app(env.store, auth_secret=SECRET, execution_runtime=env.runtime,
        candidate_ingestion=ingestion, candidate_review=review,
        research_strategies=env.strategies)
    client = TestClient(app, base_url="https://pilot.example")
    client.headers["Authorization"] = "Bearer " + token

    env.prepare_request = prepare_body(env)
    prepared_response = client.post("/api/ui/research-strategies/prepare",
                                    json=env.prepare_request)
    assert prepared_response.status_code == 200, prepared_response.text
    prepared = prepared_response.json()
    env.confirm_request = confirm_body(prepared)
    confirmed_response = client.post("/api/ui/research-strategies/confirm",
                                     json=env.confirm_request)
    assert confirmed_response.status_code == 200, confirmed_response.text
    env.confirmed = confirmed_response.json()
    env.snapshot = env.confirmed["snapshot"]

    start_request = start(env)
    started_response = send_execution(client, env, start_request)
    assert started_response.status_code == 200, started_response.text
    begun = started_response.json()
    claim_request = operation(env, "CLAIM", begun)
    claimed_response = send_execution(client, env, claim_request)
    assert claimed_response.status_code == 200, claimed_response.text
    lease = claimed_response.json()

    raw = payload(env, begun, lease)
    raw["records"][0].update(
        title=CONTENT["title"], body=CONTENT["body"],
        published_at=(datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        observed_at=(datetime.now(UTC) - timedelta(seconds=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    uploaded_response = send_candidate(client, env.key, raw)
    assert uploaded_response.status_code == 200, uploaded_response.text
    uploaded = uploaded_response.json()
    item = uploaded["items"][0]
    binding = {
        "candidateId": item["candidate_id"],
        "candidateRevision": item["revision"],
        "sourceVersionId": item["version_id"],
        "profileId": env.profile,
        "profileVersion": env.profile_number,
    }

    assessment_request = review_payload(binding)
    assessed_response = client.post("/api/ui/candidate-reviews", json=assessment_request)
    assert assessed_response.status_code == 200, assessed_response.text
    assessed = assessed_response.json()
    assert assessed["kind"] == "assessment"
    assert len(local_provider.requests) == 1

    verification_request = verification_payload(binding)
    verified_response = client.post("/api/ui/candidate-source-verifications",
                                    json=verification_request)
    assert verified_response.status_code == 200, verified_response.text
    verified = verified_response.json()
    include_request = review_payload(
        binding, "INCLUDE", assessmentId=assessed["assessment"]["id"],
        sourceVerificationId=verified["id"], humanConfirmed=True,
        evidence=assessment()["evidence"], reason="",
    )
    included_response = client.post("/api/ui/candidate-reviews", json=include_request)
    assert included_response.status_code == 200, included_response.text
    included = included_response.json()
    assert included["receipt"]["outcome"] == "IMPORTED"

    detail_path = "/api/ui/opportunities/" + included["receipt"]["opportunityId"]
    detail_response = client.get(detail_path)
    assert detail_response.status_code == 200, detail_response.text
    assert detail_response.headers["cache-control"] == "no-store"
    evidence = detail_response.json()["opportunity"]["source_evidence"]
    assert evidence["status"] == "CAPTURED"
    fixed = evidence["snapshot"]
    assert fixed["source"]["version_id"] == binding["sourceVersionId"]
    assert fixed["source"]["body"] == raw["records"][0]["body"]
    assert fixed["observation"]["id"] == item["observation_id"]
    assert fixed["observation"]["received_at"] == uploaded["received_at"]
    assert fixed["assessment"]["id"] == assessed["assessment"]["id"]
    assert any(c["field"] == "source.body" for c in fixed["assessment"]["citations"])
    assert not any(c["field"] == "profile.description" for c in fixed["assessment"]["citations"])
    assert detail_response.json()["opportunity"]["source_status"] == "OPEN"
    colleague = {"Authorization": "Bearer " + issue_token(env.users[1], SECRET)}
    assert client.get(detail_path, headers=colleague).json()["opportunity"]["source_evidence"] == evidence
    assert client.get("/api/ui/candidates", headers=colleague).json()["total"] == 0
    stranger = {"Authorization": "Bearer " + issue_token(env.users[2], SECRET)}
    assert client.get(detail_path, headers=stranger).status_code == 404

    current_response = client.get("/api/ui/candidates", params={"status": "IMPORTED"})
    assert current_response.status_code == 200, current_response.text
    current = current_response.json()
    assert current["total"] == 1
    assert current["items"][0]["currentBindingValid"] is True
    assert current["items"][0]["assessment"]["id"] == assessed["assessment"]["id"]
    history_response = client.get("/api/ui/candidates", params={
        "ids": binding["candidateId"], "reviewRequestId": include_request["requestId"],
        "page": 1, "pageSize": 1,
    })
    assert history_response.status_code == 200, history_response.text
    history = history_response.json()
    assert history["total"] == 1
    assert history["items"][0]["lastReview"] == included["receipt"]
    assert history["items"][0]["assessment"]["id"] == assessed["assessment"]["id"]

    revoke_request = revoke_body(env.confirmed)
    revoked_response = client.post("/api/ui/research-strategies/revoke",
                                   json=revoke_request)
    assert revoked_response.status_code == 200, revoked_response.text
    assert revoked_response.json()["state"] == "REVOKED"
    stale_response = client.get("/api/ui/candidates")
    assert stale_response.status_code == 200, stale_response.text
    stale = stale_response.json()
    assert stale["total"] == 1
    assert stale["items"][0]["assessmentStale"] is True
    assert stale["items"][0]["currentBindingValid"] is False
    assert client.get("/api/ui/candidates", params={"status": "IMPORTED"}).json()["total"] == 0

    new_review = client.post("/api/ui/candidate-reviews", json=review_payload(binding))
    assert new_review.status_code == 409
    assert new_review.json()["detail"]["code"] == "strategy_conflict"
    rejected_raw = copy.deepcopy(raw)
    rejected_raw["request_id"] = str(uuid4())
    rejected_raw["records"][0]["body"] += " fresh write after revocation"
    rejected_upload = send_candidate(client, env.key, rejected_raw)
    assert rejected_upload.status_code == 409
    assert rejected_upload.json()["detail"]["code"] == "strategy_conflict"
    assert client.get(detail_path).json()["opportunity"]["source_evidence"] == evidence

    receipt_paths = {
        "/api/ui/research-strategy-operations/" + env.confirmed["request_id"]: env.confirmed,
        "/api/ui/execution-operations/" + start_request.request_id: begun,
        "/api/ui/execution-operations/" + claim_request.request_id: lease,
        "/api/ui/candidate-batches/" + lease["platform_run_id"] + "/" + raw["request_id"]: uploaded,
        "/api/ui/candidate-review-requests/" + assessment_request["requestId"]: assessed,
        "/api/ui/candidate-review-requests/" + verification_request["requestId"]: verified,
        "/api/ui/candidate-review-requests/" + include_request["requestId"]: included,
    }
    for path, expected in receipt_paths.items():
        receipt = client.get(path)
        assert receipt.status_code == 200, (path, receipt.text)
        assert receipt.json() == expected
    assert client.get("/api/ui/capabilities").json()["capabilities"]["task_execution"] == {"available": False}
    assert client.delete("/api/ui/session").status_code == 200
    assert client.get(next(iter(receipt_paths))).status_code == 401
    assert client.get(detail_path).status_code == 401


def test_registered_migration_is_repeatable_and_strategy_grant_stays_narrow(real_strategy_env):
    env = real_strategy_env
    env.admin.migrate()
    env.admin.migrate()
    with env.admin.connect() as connection:
        assert connection.execute(
            "SELECT checksum FROM pilot_schema_meta WHERE version='v02-research-strategies'"
        ).fetchone()[0] == "2f971d11f252ea525c0e29920c73f448007650a546a687d7cf17c13d9ac23ae3"
    with env.db.connect() as connection:
        role = connection.execute("SELECT current_user").fetchone()[0]
        expected = {
            "pilot_research_strategy_drafts": {"SELECT", "INSERT", "UPDATE"},
            "pilot_research_strategy_versions": {"SELECT", "INSERT", "UPDATE"},
            "pilot_research_strategy_operations": {"SELECT", "INSERT"},
        }
        for table, allowed in expected.items():
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
                actual = connection.execute(
                    "SELECT has_table_privilege(current_user,%s,%s)", (table, privilege)
                ).fetchone()[0]
                assert actual is (privilege in allowed), (role, table, privilege)
            assert connection.execute(
                "SELECT NOT pg_has_role(current_user,relowner,'MEMBER') FROM pg_class WHERE oid=%s::regclass",
                (table,),
            ).fetchone()[0]
        assert not connection.execute(
            "SELECT has_schema_privilege(current_user,'public','CREATE')"
        ).fetchone()[0]
