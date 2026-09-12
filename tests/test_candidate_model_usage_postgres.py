"""Ordinary ASSESS usage evidence on restricted PostgreSQL and authenticated HTTP.

All model/source values are synthetic. These tests do not establish provider billing,
platform collection, production deployment, or customer acceptance.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from threading import Event
from uuid import uuid4

import psycopg
import pytest

from pilot.auth import issue_token, verify_token_claims
from pilot.candidate_assessment_model import AssessmentModelError
from pilot.candidate_ingestion import CandidateIngestionError
from pilot.candidate_model_usage import CandidateModelUsageScope
from tests.test_assessment_provider_usage import USAGE
from tests.test_candidate_assessment_model import assessment
from tests.test_candidate_review_http_postgres import client_for, local_provider, request, upload
from tests.test_candidate_review_postgres import (
    BoundaryModel, databases, env, execution_databases, execution_env,
    raw_databases, raw_env, review_payload, seed, store,
)
from tests.test_execution_runtime_postgres import SECRET


def usable_seed(env):
    return seed(env)


class UsageModel(BoundaryModel):
    def __init__(self, responses):
        super().__init__()
        self.responses = list(responses)

    def assess(self, *, description, content):
        self.calls += 1
        self.last_input = (description, deepcopy(content))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def assert_usage(value, *, request_id, invocation_id, candidate_id, state,
                 usage, outcome, recorded):
    assert value == {
        "schema_version": "candidate-model-usage-v1",
        "requestId": request_id,
        "invocationRequestId": invocation_id,
        "candidateId": candidate_id,
        "state": state,
        "usage": usage,
        "outcome": outcome,
        "recordedAt": value["recordedAt"],
    }
    assert (value["recordedAt"] is not None) is recorded


def test_success_usage_cache_alias_and_owner_tenant_isolation(env):
    model = UsageModel([(deepcopy(assessment()), USAGE)])
    service = store(env, model)
    binding = usable_seed(env)
    original = review_payload(binding)
    assert service.review(env.claims, original)["kind"] == "assessment"
    usage = service.get_model_usage(env.claims, original["requestId"])
    assert_usage(usage, request_id=original["requestId"], invocation_id=original["requestId"],
        candidate_id=binding["candidateId"], state="REPORTED", usage=USAGE,
        outcome="SUCCEEDED", recorded=True)

    alias = review_payload(binding)
    replay = service.review(env.claims, alias)
    assert replay["invocationRequestId"] == original["requestId"]
    alias_usage = service.get_model_usage(env.claims, alias["requestId"])
    assert_usage(alias_usage, request_id=alias["requestId"], invocation_id=original["requestId"],
        candidate_id=binding["candidateId"], state="REPORTED", usage=USAGE,
        outcome="SUCCEEDED", recorded=True)
    assert alias_usage["recordedAt"] == usage["recordedAt"]
    assert model.calls == 1
    with env.admin.connect() as connection:
        rows = connection.execute("SELECT request_id,phase FROM pilot_candidate_model_usage_events "
            "WHERE tenant_id=%s ORDER BY request_id,phase", (env.tenant,)).fetchall()
    assert rows == [(original["requestId"], "DISPATCH"), (original["requestId"], "FINISH")]

    for user in env.users[1:]:
        other = verify_token_claims(issue_token(user, SECRET), SECRET)
        with pytest.raises(CandidateIngestionError, match="request_not_found"):
            service.get_model_usage(other, original["requestId"])


def test_invalid_answer_keeps_usage_and_retry_has_independent_unknown_usage(env):
    model = UsageModel([
        AssessmentModelError("invalid_assessment_result", 502, usage=USAGE),
        (deepcopy(assessment()),
         {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 3}),
    ])
    service = store(env, model)
    binding = usable_seed(env)
    original = review_payload(binding)
    assert service.review(env.claims, original)["status"] == "FAILED"
    failed = service.get_model_usage(env.claims, original["requestId"])
    assert_usage(failed, request_id=original["requestId"], invocation_id=original["requestId"],
        candidate_id=binding["candidateId"], state="REPORTED", usage=USAGE,
        outcome="FAILED", recorded=True)

    retry = review_payload(binding, retryOf=original["requestId"])
    assert service.review(env.claims, retry)["kind"] == "assessment"
    unknown = service.get_model_usage(env.claims, retry["requestId"])
    assert_usage(unknown, request_id=retry["requestId"], invocation_id=retry["requestId"],
        candidate_id=binding["candidateId"], state="UNKNOWN", usage=None,
        outcome="SUCCEEDED", recorded=True)
    assert model.calls == 2


def test_service_validation_failure_does_not_erase_returned_usage(env):
    invalid = deepcopy(assessment())
    invalid["intent"]["citations"][0]["quote"] = "not present in synthetic source"
    service = store(env, UsageModel([(invalid, USAGE)]))
    binding = usable_seed(env)
    payload = review_payload(binding)
    assert service.review(env.claims, payload)["status"] == "FAILED"
    usage = service.get_model_usage(env.claims, payload["requestId"])
    assert usage["state"] == "REPORTED" and usage["usage"] == USAGE
    assert usage["outcome"] == "FAILED"


@pytest.mark.parametrize("reported", [None,
    {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 3}])
def test_success_without_valid_usage_is_unknown_not_zero(env, reported):
    service = store(env, UsageModel([(deepcopy(assessment()), reported)]))
    binding = usable_seed(env)
    payload = review_payload(binding)
    assert service.review(env.claims, payload)["kind"] == "assessment"
    usage = service.get_model_usage(env.claims, payload["requestId"])
    assert_usage(usage, request_id=payload["requestId"], invocation_id=payload["requestId"],
        candidate_id=binding["candidateId"], state="UNKNOWN", usage=None,
        outcome="SUCCEEDED", recorded=True)


def test_model_timeout_finishes_unknown_without_estimating_usage(env):
    service = store(env, UsageModel([
        AssessmentModelError("assessment_result_unknown", 504)]))
    binding = usable_seed(env)
    payload = review_payload(binding)
    assert service.review(env.claims, payload)["status"] == "UNKNOWN"
    usage = service.get_model_usage(env.claims, payload["requestId"])
    assert_usage(usage, request_id=payload["requestId"], invocation_id=payload["requestId"],
        candidate_id=binding["candidateId"], state="UNKNOWN", usage=None,
        outcome="UNKNOWN", recorded=True)


def test_finish_persistence_failure_does_not_retry_model(env):
    service = store(env, UsageModel([(deepcopy(assessment()), USAGE)]))
    binding = usable_seed(env)
    payload = review_payload(binding)
    original_finish = service.model_usage.finish

    def unavailable(*_args, **_kwargs):
        raise CandidateIngestionError("assessment_outcome_unknown", 503)

    service.model_usage.finish = unavailable
    with pytest.raises(CandidateIngestionError, match="assessment_outcome_unknown"):
        service.review(env.claims, payload)
    assert service.model.calls == 1
    service.model_usage.finish = original_finish
    recovered = service.review(env.claims, payload)
    assert recovered["status"] == "PROCESSING" and service.model.calls == 1


def test_dispatch_is_pending_then_expired_unknown_without_a_fabricated_finish(env):
    entered, release = Event(), Event()
    model = UsageModel([])

    def blocked(**_kwargs):
        model.calls += 1
        entered.set()
        assert release.wait(5)
        return deepcopy(assessment()), USAGE

    model.assess = blocked
    service = store(env, model)
    binding = usable_seed(env)
    payload = review_payload(binding)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(service.review, env.claims, payload)
        assert entered.wait(5)
        pending = service.get_model_usage(env.claims, payload["requestId"])
        assert_usage(pending, request_id=payload["requestId"], invocation_id=payload["requestId"],
            candidate_id=binding["candidateId"], state="PENDING", usage=None,
            outcome=None, recorded=False)
        with env.admin.connect() as connection:
            connection.execute("ALTER TABLE pilot_candidate_review_requests DISABLE TRIGGER candidate_review_immutable")
            connection.execute("UPDATE pilot_candidate_review_requests SET created_at=created_at-interval '91 seconds',"
                "deadline_at=deadline_at-interval '91 seconds' WHERE tenant_id=%s AND request_id=%s",
                (env.tenant, payload["requestId"]))
            connection.execute("ALTER TABLE pilot_candidate_review_requests ENABLE TRIGGER candidate_review_immutable")
        expired = service.get_model_usage(env.claims, payload["requestId"])
        assert_usage(expired, request_id=payload["requestId"], invocation_id=payload["requestId"],
            candidate_id=binding["candidateId"], state="UNKNOWN", usage=None,
            outcome=None, recorded=False)
        release.set()
        business = future.result(timeout=5)
    assert business["status"] == "UNKNOWN"
    finished = service.get_model_usage(env.claims, payload["requestId"])
    assert finished["state"] == "REPORTED" and finished["outcome"] == "SUCCEEDED"


@pytest.mark.parametrize("change", ["profile", "session"])
def test_finish_survives_authority_change_without_business_result(env, change):
    entered, release = Event(), Event()
    model = UsageModel([])

    def blocked(**_kwargs):
        model.calls += 1
        entered.set()
        assert release.wait(5)
        return deepcopy(assessment()), USAGE

    model.assess = blocked
    service = store(env, model)
    binding = usable_seed(env)
    payload = review_payload(binding)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(service.review, env.claims, payload)
        assert entered.wait(5)
        if change == "profile":
            with env.admin.connect() as connection:
                connection.execute("UPDATE business_profile_versions SET status='REVOKED' "
                    "WHERE profile_version_id=%s", (env.profile,))
        else:
            service.sessions.revoke([env.claims])
        release.set()
        with pytest.raises(CandidateIngestionError,
                match="profile_conflict" if change == "profile" else "invalid_session"):
            future.result(timeout=5)

    fresh = (env.claims if change == "profile" else
        verify_token_claims(issue_token(env.users[0], SECRET), SECRET))
    usage = service.get_model_usage(fresh, payload["requestId"])
    assert_usage(usage, request_id=payload["requestId"], invocation_id=payload["requestId"],
        candidate_id=binding["candidateId"], state="REPORTED", usage=USAGE,
        outcome="SUCCEEDED", recorded=True)
    with env.admin.connect() as connection:
        assert connection.execute("SELECT count(*) FROM pilot_candidate_assessments "
            "WHERE tenant_id=%s AND request_id=%s", (env.tenant, payload["requestId"])).fetchone()[0] == 0


def test_event_constraints_permissions_immutability_and_repeatable_migration(env):
    model = UsageModel([(deepcopy(assessment()), USAGE)])
    service = store(env, model)
    binding = usable_seed(env)
    original = review_payload(binding)
    service.review(env.claims, original)
    verify = service.verify_source(env.claims, binding | {
        "requestId": str(uuid4()), "humanConfirmed": True, "status": "OPEN",
        "openingMethod": "DIRECT", "locator": "https://example.com/synthetic",
        "excerpt": "采购输送设备", "contactMethod": "COMMENT"})
    alias = review_payload(binding)
    service.review(env.claims, alias)
    verification_usage = service.get_model_usage(env.claims, verify["requestId"])
    assert verification_usage["state"] == "NOT_RECORDED"
    assert verification_usage["usage"] is None and verification_usage["recordedAt"] is None
    env.admin.migrate()
    env.admin.migrate()

    with env.admin.connect() as connection:
        snapshot_key = connection.execute("SELECT snapshot_key FROM pilot_candidate_review_requests "
            "WHERE tenant_id=%s AND request_id=%s", (env.tenant, original["requestId"])).fetchone()[0]
    scope = CandidateModelUsageScope(env.tenant, env.claims.user_id,
        original["requestId"], snapshot_key)
    assert service.model_usage.finish(scope, outcome="SUCCEEDED", usage=USAGE)["usage"] == USAGE
    with pytest.raises(CandidateIngestionError, match="assessment_outcome_unknown"):
        service.model_usage.finish(scope, outcome="UNKNOWN", usage=None)

    with env.db.connect() as connection:
        assert connection.execute("SELECT row_security_active('pilot_candidate_model_usage_events')").fetchone()[0]
        assert not connection.execute("SELECT has_table_privilege(current_user,"
            "'pilot_candidate_model_usage_events','UPDATE')").fetchone()[0]
        assert not connection.execute("SELECT has_table_privilege(current_user,"
            "'pilot_candidate_model_usage_events','DELETE')").fetchone()[0]
        assert not connection.execute("SELECT has_schema_privilege(current_user,'public','CREATE')").fetchone()[0]

    with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
        with env.admin.connect() as connection:
            connection.execute("UPDATE pilot_candidate_model_usage_events SET outcome='UNKNOWN' "
                "WHERE tenant_id=%s AND request_id=%s AND phase='FINISH'", (env.tenant, original["requestId"]))
    for rejected_request in (alias["requestId"], verify["requestId"]):
        with pytest.raises(psycopg.errors.RaiseException, match="invalid candidate model usage event"):
            with env.admin.connect() as connection:
                connection.execute("INSERT INTO pilot_candidate_model_usage_events"
                    "(tenant_id,owner_user_id,request_id,snapshot_key,phase) VALUES(%s,%s,%s,%s,'DISPATCH')",
                    (env.tenant, env.claims.user_id, rejected_request, "a" * 64))
    unfinished = str(uuid4())
    with env.admin.connect() as connection:
        connection.execute("""INSERT INTO pilot_candidate_review_requests(
            tenant_id,owner_user_id,request_id,candidate_id,fingerprint,action,binding_hash,
            snapshot_key,invocation_id,attempt,status,created_at,deadline_at,payload,snapshot,result)
            SELECT tenant_id,owner_user_id,%s,candidate_id,fingerprint,action,binding_hash,
                snapshot_key,NULL,attempt,status,created_at,deadline_at,
                payload,snapshot,result FROM pilot_candidate_review_requests
            WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s""",
            (unfinished, env.tenant, env.claims.user_id, original["requestId"]))
    with pytest.raises(psycopg.errors.RaiseException, match="invalid candidate model usage event"):
        with env.admin.connect() as connection:
            connection.execute("INSERT INTO pilot_candidate_model_usage_events"
                "(tenant_id,owner_user_id,request_id,snapshot_key,phase,outcome) "
                "VALUES(%s,%s,%s,%s,'FINISH','UNKNOWN')",
                (env.tenant, env.claims.user_id, unfinished, snapshot_key))
    for invalid in (
        {"prompt_tokens": "1", "completion_tokens": 1, "total_tokens": 2},
        {"prompt_tokens": None, "completion_tokens": 1, "total_tokens": 1},
        {"prompt_tokens": True, "completion_tokens": 1, "total_tokens": 2},
    ):
        invalid_id = str(uuid4())
        with env.admin.connect() as connection:
            connection.execute("""INSERT INTO pilot_candidate_review_requests(
                tenant_id,owner_user_id,request_id,candidate_id,fingerprint,action,binding_hash,
                snapshot_key,invocation_id,attempt,status,created_at,deadline_at,payload,snapshot,result)
                SELECT tenant_id,owner_user_id,%s,candidate_id,fingerprint,action,binding_hash,
                    snapshot_key,NULL,attempt,status,created_at,deadline_at,
                    payload,snapshot,result FROM pilot_candidate_review_requests
                WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s""",
                (invalid_id, env.tenant, env.claims.user_id, original["requestId"]))
            connection.execute("INSERT INTO pilot_candidate_model_usage_events"
                "(tenant_id,owner_user_id,request_id,snapshot_key,phase) VALUES(%s,%s,%s,%s,'DISPATCH')",
                (env.tenant, env.claims.user_id, invalid_id, snapshot_key))
        with pytest.raises(psycopg.errors.CheckViolation):
            with env.admin.connect() as connection:
                connection.execute("INSERT INTO pilot_candidate_model_usage_events"
                    "(tenant_id,owner_user_id,request_id,snapshot_key,phase,outcome,usage) "
                    "VALUES(%s,%s,%s,%s,'FINISH','SUCCEEDED',%s::jsonb)",
                    (env.tenant, env.claims.user_id, invalid_id, snapshot_key,
                     json.dumps(invalid)))
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with env.admin.connect() as connection:
            connection.execute("INSERT INTO pilot_candidate_model_usage_events"
                "(tenant_id,owner_user_id,request_id,snapshot_key,phase) VALUES(%s,%s,%s,%s,'DISPATCH')",
                (env.tenant, env.claims.user_id, str(uuid4()), "a" * 64))


def test_usage_read_rechecks_session_after_data_snapshot(env):
    service = store(env, UsageModel([(deepcopy(assessment()), USAGE)]))
    binding = usable_seed(env)
    payload = review_payload(binding)
    service.review(env.claims, payload)
    original_get = service.model_usage.get

    def revoke_after_read(cursor, **kwargs):
        value = original_get(cursor, **kwargs)
        with env.admin.connect() as connection:
            connection.execute("INSERT INTO pilot_session_revocations"
                "(tenant_id,user_id,revocation_key,expires_at) VALUES(%s,%s,%s,to_timestamp(%s))",
                (env.tenant, env.claims.user_id, env.claims.revocation_key,
                 env.claims.expires_at))
        return value

    service.model_usage.get = revoke_after_read
    with pytest.raises(CandidateIngestionError, match="invalid_session"):
        service.get_model_usage(env.claims, payload["requestId"])


def test_authenticated_http_query_reports_original_usage_and_never_calls_model_again(env, local_provider):
    client, claims = client_for(env, local_provider.model)
    binding, _ = upload(client, env, claims)
    payload = request(binding)
    assessed = client.post("/api/ui/candidate-reviews", json=payload)
    assert assessed.status_code == 200, assessed.text
    path = "/api/ui/candidate-review-requests/" + payload["requestId"] + "/model-usage"
    response = client.get(path)
    assert response.status_code == 200, response.text
    assert response.json()["usage"] == {"prompt_tokens": 20, "completion_tokens": 10,
        "total_tokens": 30}
    assert response.json()["state"] == "REPORTED"
    assert len(local_provider.requests) == 1
    assert client.get(path + "?provider=true").status_code == 422
    assert len(local_provider.requests) == 1
    for user in env.users[1:]:
        foreign = {"Authorization": "Bearer " + issue_token(user, SECRET)}
        denied = client.get(path, headers=foreign)
        assert denied.status_code == 404
        assert "prompt_tokens" not in denied.text
    missing = client.get("/api/ui/candidate-review-requests/" + str(uuid4()) + "/model-usage")
    assert missing.status_code == 404 and "prompt_tokens" not in missing.text
