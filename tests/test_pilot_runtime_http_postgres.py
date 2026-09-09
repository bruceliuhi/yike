"""Ordinary CLI -> actual HTTP/stores/restricted PG; source/provider are synthetic.

Only process launch and application-DB selection are replaced in the launcher.
Source seeding is explicitly trusted test setup, not production collection.
"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from pilot import cli
from pilot.auth import issue_token, verify_token_claims
from tests.test_candidate_assessment_model import CONTENT, assessment
from tests.test_candidate_ingestion_postgres import claimed, payload, service, submit
from tests.test_candidate_review_http_postgres import local_provider
from tests.test_candidate_review_postgres import review_payload, verification_payload
from tests.test_confirmed_strategy_http_postgres import send_execution
from tests.test_confirmed_strategy_review_postgres import (
    BoundedDatabase, databases, env, execution_databases, execution_env,
    raw_databases, raw_env, real_strategy_env,
)
from tests.test_execution_runtime_postgres import SECRET, start
from tests.test_research_strategies_postgres import prepare_body, confirm_body, revoke_body


def ordinary_client(monkeypatch, env, provider=None):
    for name in (
        "ADMIN_DATABASE_URL", "ASSESSMENT_BASE_URL", "ASSESSMENT_API_KEY",
        "ASSESSMENT_MODEL", "DEV_LOGIN", "PROXY_HEADERS", "FORWARDED_ALLOW_IPS",
    ):
        monkeypatch.delenv("YIKE_PILOT_" + name, raising=False)
    monkeypatch.setenv("YIKE_PILOT_AUTH_SECRET", SECRET)
    if provider is not None:
        monkeypatch.setenv("YIKE_PILOT_ASSESSMENT_BASE_URL", provider.model.base_url)
        monkeypatch.setenv("YIKE_PILOT_ASSESSMENT_API_KEY", provider.model.api_key)
        monkeypatch.setenv("YIKE_PILOT_ASSESSMENT_MODEL", provider.model.model)
    monkeypatch.setattr(cli.PilotDatabase, "from_environment", lambda: BoundedDatabase(env.db))
    launched = {}

    def capture(app, **options):
        launched.update(app=app, options=options)

    monkeypatch.setattr(cli.uvicorn, "run", capture)
    cli.web()
    assert launched["options"]["access_log"] is False
    client = TestClient(launched["app"], base_url="https://pilot.example")
    client.headers["Authorization"] = "Bearer " + issue_token(env.claims.user_id, SECRET)
    return client


def seed_signed_synthetic_candidate(env):
    # Fixture runtime has a synthetic source policy ONLY for trusted test input.
    # The ordinary CLI app under test never receives that runtime or policy.
    begun, lease = claimed(env)
    raw = payload(env, begun, lease)
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    raw["records"][0].update(title=CONTENT["title"], body=CONTENT["body"],
                             published_at=now, observed_at=now)
    uploaded = submit(env, service(env), raw)
    item = uploaded["items"][0]
    binding = {
        "candidateId": item["candidate_id"], "candidateRevision": item["revision"],
        "sourceVersionId": item["version_id"], "profileId": env.profile,
        "profileVersion": env.profile_number,
    }
    return binding, begun, lease, raw, uploaded


def test_ordinary_cli_serves_actual_persistent_strategies_and_review(
    monkeypatch, real_strategy_env, local_provider,
):
    env = real_strategy_env
    with ordinary_client(monkeypatch, env, local_provider) as client:
        response = client.post("/api/ui/research-strategies/prepare", json=prepare_body(env))
        assert response.status_code == 200, response.text
        confirmed_response = client.post("/api/ui/research-strategies/confirm",
                                         json=confirm_body(response.json()))
        assert confirmed_response.status_code == 200, confirmed_response.text
        env.confirmed = confirmed_response.json()
        env.snapshot = env.confirmed["snapshot"]
        strategy_path = "/api/ui/research-strategies/" + env.confirmed["strategy_version_id"]
        assert client.get(strategy_path).json()["state"] == "CONFIRMED"

        binding, begun, lease, raw, uploaded = seed_signed_synthetic_candidate(env)
        before = client.get("/api/ui/candidates")
        assert before.status_code == 200, before.text
        assert before.json()["items"][0]["status"] == "PENDING_REVIEW"
        assert client.get("/api/ui/raw-candidates").json()["total"] == 1
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").status_code == 200
        flags = client.get("/api/ui/capabilities").json()["capabilities"]
        for key in ("task_execution", "platform_connections", "search_suggestions",
                    "sms_login", "outreach", "replies"):
            assert flags[key] == {"available": False}
        assert local_provider.requests == []

        assess_request = review_payload(binding)
        assessed_response = client.post("/api/ui/candidate-reviews", json=assess_request)
        assert assessed_response.status_code == 200, assessed_response.text
        assessed = assessed_response.json()
        assert assessed["kind"] == "assessment"
        assert assessed["assessment"]["sendingAuthorized"] is False
        assert len(local_provider.requests) == 1
        assert local_provider.requests[0]["model"] == "synthetic-http-fixture"
        assert client.post("/api/ui/candidate-reviews", json=assess_request).json() == assessed

        verified_response = client.post("/api/ui/candidate-source-verifications",
                                        json=verification_payload(binding))
        assert verified_response.status_code == 200, verified_response.text
        verified = verified_response.json()
        include_request = review_payload(binding, "INCLUDE",
            assessmentId=assessed["assessment"]["id"], sourceVerificationId=verified["id"],
            humanConfirmed=True, evidence=assessment()["evidence"], reason="")
        included_response = client.post("/api/ui/candidate-reviews", json=include_request)
        assert included_response.status_code == 200, included_response.text
        included = included_response.json()
        assert included["receipt"]["outcome"] == "IMPORTED"
        detail_path = "/api/ui/opportunities/" + included["receipt"]["opportunityId"]
        detail = client.get(detail_path)
        assert detail.status_code == 200, detail.text
        assert detail.headers["cache-control"] == "no-store"
        evidence = detail.json()["opportunity"]["source_evidence"]
        assert evidence["status"] == "CAPTURED"
        assert evidence["snapshot"]["source"]["body"] == raw["records"][0]["body"]
        assert evidence["snapshot"]["source"]["version_id"] == binding["sourceVersionId"]
        current = client.get("/api/ui/candidates", params={"status": "IMPORTED"})
        assert current.status_code == 200, current.text
        assert current.json()["items"][0]["currentBindingValid"] is True

        for other_user in env.users[1:]:
            headers = {"Authorization": "Bearer " + issue_token(other_user, SECRET)}
            assert client.get("/api/ui/candidates", headers=headers).json()["total"] == 0
            assert client.get("/api/ui/raw-candidates/" + binding["candidateId"],
                              headers=headers).status_code == 404
        outsider = {"Authorization": "Bearer " + issue_token(env.users[2], SECRET)}
        assert client.get(detail_path, headers=outsider).status_code == 404

        revoked = client.post("/api/ui/research-strategies/revoke", json=revoke_body(env.confirmed))
        assert revoked.status_code == 200, revoked.text
        assert client.get(strategy_path).json()["state"] == "REVOKED"
        stale = client.get("/api/ui/candidates").json()["items"][0]
        assert stale["assessmentStale"] is True
        assert stale["currentBindingValid"] is False
        assert client.get("/api/ui/candidates", params={"status": "IMPORTED"}).json()["total"] == 0
        assert client.get(detail_path).json()["opportunity"]["source_evidence"] == evidence
        history = client.get("/api/ui/candidates", params={
            "ids": binding["candidateId"], "reviewRequestId": include_request["requestId"],
            "page": 1, "pageSize": 1,
        })
        assert history.status_code == 200, history.text
        assert history.json()["items"][0]["lastReview"] == included["receipt"]

        receipt_paths = {
            "/api/ui/research-strategy-operations/" + env.confirmed["request_id"]: env.confirmed,
            "/api/ui/candidate-batches/" + lease["platform_run_id"] + "/" + raw["request_id"]: uploaded,
            "/api/ui/candidate-review-requests/" + assess_request["requestId"]: assessed,
            "/api/ui/candidate-review-requests/" + include_request["requestId"]: included,
        }
        for path, expected in receipt_paths.items():
            recovered = client.get(path)
            assert recovered.status_code == 200, (path, recovered.text)
            assert recovered.json() == expected
        task = client.get("/api/ui/execution-tasks/" + begun["task_id"])
        assert task.status_code == 200, task.text
        assert len(local_provider.requests) == 1
        assert client.delete("/api/ui/session").status_code == 200
        assert client.get(detail_path).status_code == 401
        assert len(local_provider.requests) == 1


def test_ordinary_cli_without_model_or_source_does_not_create_authority(monkeypatch, real_strategy_env):
    env = real_strategy_env
    binding, _, _, _, _ = seed_signed_synthetic_candidate(env)
    with ordinary_client(monkeypatch, env) as client:
        claims = verify_token_claims(client.headers["Authorization"].removeprefix("Bearer "), SECRET)
        start_request = start(env)
        started = send_execution(client, env, claims, start_request)
        assert started.status_code == 501, started.text
        assert started.json()["detail"]["code"] == "capability_unavailable"
        missing_receipt = client.get("/api/ui/execution-operations/" + start_request.request_id)
        assert missing_receipt.status_code == 404, missing_receipt.text
        assessed = client.post("/api/ui/candidate-reviews", json=review_payload(binding))
        assert assessed.status_code == 501, assessed.text
        assert assessed.json()["detail"]["code"] == "capability_unavailable"
        with env.db.connect() as connection:
            assert connection.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone() == (False, False)
        # Administrative test inspection cannot mistake an unscoped RLS-empty
        # result for proof that the ordinary app wrote no assessment.
        with env.admin.connect() as connection:
            assert connection.execute("SELECT count(*) FROM pilot_candidate_assessments WHERE tenant_id=%s",
                                      (env.tenant,)).fetchone()[0] == 0
