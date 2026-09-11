"""Real restricted PostgreSQL coverage for research provenance eligibility."""
from uuid import uuid4

import pytest

from pilot.execution_contract import ExecutionRuntimeError
from pilot.opportunity_research import OpportunityResearchService
from pilot.research_origin import validate_research_origin
from pilot.research_strategy_contract import StrategyStoreError
from tests.test_candidate_review_postgres import (
    assessment, review_payload, databases, env, execution_databases, execution_env, raw_databases, raw_env,
)
from tests.test_confirmed_strategy_review_postgres import real_review, real_strategy_env, snapshot_cursor
from tests.test_opportunity_evidence_postgres import include
from tests.test_research_strategies_postgres import confirm_body, prepare_body


def test_legacy_configuration_returns_before_any_origin_query():
    class ForbiddenCursor:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("legacy strategy queried opportunity tables")
    validate_research_origin(ForbiddenCursor(), object(), object(), "tenant", "profile",
        {"research": {"version": 1}})


@pytest.mark.parametrize("projection", ["read_snapshot", "resolve"])
@pytest.mark.parametrize("code,status,expected", [
    ("invalid_session", 401, ("invalid_session", 401)),
    ("strategy_store_unavailable", 503, ("strategy_store_unavailable", 503)),
    ("research_origin_unavailable", 409, ("strategy_conflict", 409)),
])
def test_origin_errors_map_safely_in_runtime_projection(
        real_strategy_env, monkeypatch, projection, code, status, expected):
    env = real_strategy_env
    def unavailable(*_args, **_kwargs):
        raise StrategyStoreError(code, status)
    monkeypatch.setattr("pilot.research_strategies.validate_research_origin", unavailable)
    if projection == "read_snapshot":
        with snapshot_cursor(env) as cursor:
            with pytest.raises(ExecutionRuntimeError) as caught:
                env.strategies.read_snapshot(cursor, env.claims, env.profile,
                    env.confirmed["strategy_version_id"])
    else:
        with env.db.connect() as conn, conn.cursor() as cursor:
            with pytest.raises(ExecutionRuntimeError) as caught:
                env.strategies.resolve(cursor, env.claims, env.profile,
                    env.confirmed["strategy_version_id"])
    assert (caught.value.code, caught.value.status) == expected


def _provenance(env, suggestion):
    return {"requestId": suggestion["requestId"], "suggestionId": suggestion["suggestionId"],
        **suggestion["binding"], "originalScope": suggestion["originalScope"],
        "additionalScope": suggestion["additionalScope"]}


def _research_config(env, provenance):
    value = env.prepare_request["configuration"] | {"research": {
        "version": 1, "demandTypes": ["INQUIRY"], "maxSoubei": 10,
        "limits": {"sources": 10, "minutes": 10, "modelCalls": 10},
        "stopAtAnyLimit": True, "evidenceOrder": "SOURCE_MATCH_CONTEXT",
        "provenance": provenance}}
    return value


def test_origin_round_trip_and_current_recognition_gate(real_strategy_env):
    env = real_strategy_env
    review, candidate, assessed, check, _, _, opportunity_id = include(env, service=real_review(env))
    detail = env.store.get_opportunity(env.claims.user_id, opportunity_id)
    binding = {"userId": env.claims.user_id, "opportunityId": opportunity_id,
        "profileVersionId": env.profile, "sourceUrl": detail["public_url"],
        "evidenceVersion": candidate["sourceVersionId"],
        "accountScope": {"id": env.tenant, "version": 1}}
    suggestion = OpportunityResearchService(env.db, supported_platforms=lambda _: ("PUBLIC_WEB",)).similar(
        env.claims, binding, str(uuid4()))
    provenance = _provenance(env, suggestion)
    request = prepare_body(env, configuration=_research_config(env, provenance))
    pending = env.strategies.prepare(env.claims, request)
    assert pending["snapshot"]["configuration"]["research"]["provenance"] == provenance
    confirm_request = confirm_body(pending)
    confirmed = env.strategies.confirm(env.claims, confirm_request)
    pending_after = env.strategies.prepare(env.claims,
        prepare_body(env, configuration=_research_config(env, provenance)))
    with snapshot_cursor(env) as cursor:
        projected = env.strategies.read_snapshot(cursor, env.claims, env.profile, confirmed["strategy_version_id"])
    assert projected["configuration"]["research"]["provenance"] == provenance
    with env.db.connect() as conn, conn.cursor() as cursor:
        resolved = env.strategies.resolve(cursor, env.claims, env.profile, confirmed["strategy_version_id"])
    assert resolved.configuration["research"]["provenance"] == provenance

    excluded = review_payload(candidate, "EXCLUDE", assessmentId=assessed["assessment"]["id"],
        sourceVerificationId=check["id"], humanConfirmed=True, evidence=assessment()["evidence"],
        reason="人工撤销认可")
    review.review(env.claims, excluded)
    assert env.strategies.get_strategy(env.claims, confirmed["strategy_version_id"])["snapshot"]["configuration"]["research"]["provenance"] == provenance
    assert env.strategies.get_receipt(env.claims, confirmed["request_id"]) == confirmed
    with pytest.raises(StrategyStoreError, match="research_origin_unavailable"):
        env.strategies.confirm(env.claims, confirm_request)
    with pytest.raises(StrategyStoreError, match="research_origin_unavailable"):
        env.strategies.confirm(env.claims, confirm_body(pending_after))
    with snapshot_cursor(env) as cursor:
        with pytest.raises(ExecutionRuntimeError, match="strategy_conflict"):
            env.strategies.read_snapshot(cursor, env.claims, env.profile, confirmed["strategy_version_id"])
    with env.db.connect() as conn, conn.cursor() as cursor:
        with pytest.raises(ExecutionRuntimeError, match="strategy_conflict"):
            env.strategies.resolve(cursor, env.claims, env.profile, confirmed["strategy_version_id"])

    request2 = prepare_body(env, configuration=_research_config(env, provenance))
    with pytest.raises(StrategyStoreError, match="research_origin_unavailable"):
        env.strategies.prepare(env.claims, request2)


@pytest.mark.parametrize("field", ["userId", "opportunityId", "profileVersionId", "sourceUrl", "evidenceVersion", "accountScope"])
def test_origin_binding_mismatch_is_rejected_by_server(real_strategy_env, field):
    env = real_strategy_env
    _, candidate, _, _, _, _, opportunity_id = include(env, service=real_review(env))
    detail = env.store.get_opportunity(env.claims.user_id, opportunity_id)
    provenance = {"requestId": str(uuid4()), "suggestionId": "suggestion_" + "a" * 64,
        "userId": env.claims.user_id, "opportunityId": opportunity_id,
        "profileVersionId": env.profile, "sourceUrl": detail["public_url"],
        "evidenceVersion": candidate["sourceVersionId"],
        "accountScope": {"id": env.tenant, "version": 1},
        "originalScope": "原范围", "additionalScope": "扩展范围"}
    provenance[field] = ({"id": str(uuid4()), "version": 1} if field == "accountScope"
        else "https://example.com/other" if field == "sourceUrl" else str(uuid4()))
    with pytest.raises(StrategyStoreError, match="research_origin_unavailable"):
        env.strategies.prepare(env.claims, prepare_body(env, configuration=_research_config(env, provenance)))
