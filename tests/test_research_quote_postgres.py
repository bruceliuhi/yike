"""Restricted PostgreSQL proof for the confirmed-strategy quote boundary."""
from uuid import uuid4

import pytest

from pilot.research_quote import ResearchQuoteError, ResearchQuoteRule, ResearchQuoteService
from tests.test_candidate_review_postgres import (
    databases, env, execution_databases, execution_env, raw_databases, raw_env,
)
from tests.test_confirmed_strategy_review_postgres import real_review, real_strategy_env
from tests.test_opportunity_evidence_postgres import include
from tests.test_research_origin_postgres import _provenance, _research_config
from tests.test_research_strategies_postgres import confirm_body, prepare_body, revoke_body


def _confirmed_research(env):
    review, candidate, assessed, check, _, _, _opportunity = include(env, service=real_review(env))
    detail = env.store.get_opportunity(env.claims.user_id, _opportunity)
    binding = {"userId": env.claims.user_id, "opportunityId": _opportunity,
        "profileVersionId": env.profile, "sourceUrl": detail["public_url"],
        "evidenceVersion": candidate["sourceVersionId"],
        "accountScope": {"id": env.tenant, "version": 1}}
    from pilot.opportunity_research import OpportunityResearchService
    suggestion = OpportunityResearchService(env.db, supported_platforms=lambda _: ("PUBLIC_WEB",)).similar(
        env.claims, binding, str(uuid4()))
    pending = env.strategies.prepare(env.claims, prepare_body(env,
        configuration=_research_config(env, _provenance(env, suggestion))))
    return review, candidate, assessed, check, pending, env.strategies.confirm(env.claims, confirm_body(pending))


def _request(env, confirmed):
    return {"contractVersion": 1, "requestId": str(uuid4()), "userId": env.claims.user_id,
        "accountScopeId": env.tenant, "accountScopeVersion": 1,
        "draftId": confirmed["draft_id"], "revision": confirmed["draft_revision"],
        "configurationHash": "7" * 64, "maxSoubei": 10,
        "strategyBinding": {"strategyVersionId": confirmed["strategy_version_id"],
            "profileVersionId": confirmed["profile_version_id"],
            "configurationSha256": confirmed["configuration_sha256"]}}


def test_restricted_postgres_confirmed_quote_is_bound_and_read_only(real_strategy_env):
    env = real_strategy_env
    review, candidate, assessed, check, pending, confirmed = _confirmed_research(env)
    service = ResearchQuoteService(env.db, env.strategies,
        rule=ResearchQuoteRule("synthetic-review-rule-v1", 100, 200, 300),
        signing_secret=b"restricted-postgres-review-key!" * 2,
        research_capability=lambda snapshot: snapshot["platforms"] == ["PUBLIC_WEB"])
    request = _request(env, confirmed)
    tables = ("pilot_research_strategy_versions", "pilot_research_strategy_drafts",
              "pilot_research_strategy_operations", "pilot_candidate_review_requests")
    with env.admin.connect() as connection:
        before = {table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in tables}
    quote = service.quote(env.claims, request)
    assert quote["strategyBinding"] == request["strategyBinding"]
    assert quote["estimatedSoubei"] == 6
    assert service.verify(quote["authorizationToken"])["quoteId"] == quote["quoteId"]
    with env.admin.connect() as connection:
        after = {table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in tables}
    assert after == before

    for changed in ({"userId": env.users[1]}, {"accountScopeId": env.tenants[1]},
                    {"draftId": str(uuid4())}, {"revision": confirmed["draft_revision"] + 1},
                    {"maxSoubei": 9}, {"configurationHash": "8" * 64}):
        body = request | changed
        if "configurationHash" in changed:
            # Client edit identity is deliberately opaque and only echoed/bound.
            assert service.quote(env.claims, body)["configurationHash"] == "8" * 64
        else:
            with pytest.raises(ResearchQuoteError, match="strategy_conflict"):
                service.quote(env.claims, body)
    wrong_binding = request["strategyBinding"] | {"configurationSha256": "9" * 64}
    with pytest.raises(ResearchQuoteError, match="strategy_conflict"):
        service.quote(env.claims, request | {"strategyBinding": wrong_binding})

    env.strategies.revoke(env.claims, revoke_body(confirmed))
    with pytest.raises(ResearchQuoteError, match="strategy_conflict"):
        service.quote(env.claims, request)


def test_restricted_postgres_source_revocation_invalidates_quote(real_strategy_env):
    env = real_strategy_env
    review, candidate, assessed, check, _, confirmed = _confirmed_research(env)
    service = ResearchQuoteService(env.db, env.strategies,
        rule=ResearchQuoteRule("synthetic-review-rule-v1", 100, 200, 300),
        signing_secret=b"restricted-postgres-review-key!" * 2,
        research_capability=lambda _snapshot: True)
    request = _request(env, confirmed)
    assert service.quote(env.claims, request)["strategyBinding"] == request["strategyBinding"]
    from tests.test_candidate_review_postgres import assessment, review_payload
    review.review(env.claims, review_payload(candidate, "EXCLUDE",
        assessmentId=assessed["assessment"]["id"], sourceVerificationId=check["id"],
        humanConfirmed=True, evidence=assessment()["evidence"], reason="人工撤销认可"))
    with pytest.raises(ResearchQuoteError, match="strategy_conflict"):
        service.quote(env.claims, request)
