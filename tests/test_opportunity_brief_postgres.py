"""Restricted PostgreSQL projection; all source facts are synthetic."""
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from pilot.auth import issue_token, verify_token_claims
from pilot.followup_service import FollowupService
from pilot.opportunity_brief import OpportunityBriefError, OpportunityBriefService
from tests.test_candidate_review_postgres import (
    execution_databases, execution_env, raw_databases, raw_env, databases, env,
)
from tests.test_confirmed_strategy_review_postgres import real_strategy_env
from tests.test_opportunity_evidence_postgres import include
from tests.test_candidate_review_postgres import SECRET, assessment, review_payload, verification_payload
from tests.test_confirmed_strategy_review_postgres import real_review
from tests.test_research_strategies_postgres import revoke_body


def test_verified_include_is_projected_read_only_for_exact_owner_and_profile(real_strategy_env):
    env = real_strategy_env
    with env.db.connect() as connection:
        role = connection.execute("SELECT current_user").fetchone()[0]
    with env.admin.connect() as connection:
        connection.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
        connection.execute((Path(__file__).parents[1] / "deploy/grant_structured_followups.sql").read_text())
    *_, opportunity_id = include(env)
    with env.admin.connect() as connection:
        profile_id, version = connection.execute(
            "SELECT profile_version_id,version FROM business_profile_versions WHERE profile_version_id=%s",
            (env.profile,),
        ).fetchone()
        before = connection.execute(
            "SELECT count(*) FROM pilot_followups WHERE tenant_id=%s", (env.tenant,)
        ).fetchone()[0]
    request = {"contractVersion":1, "requestId":str(uuid4()), "userId":env.claims.user_id,
               "accountScopeId":env.tenant, "scopeVersion":1, "profileId":profile_id,
               "profileVersion":version, "businessDate":datetime.now(UTC).date().isoformat(),
               "timezone":"UTC"}
    result = OpportunityBriefService(env.db).query(env.claims, request)
    assert result["groups"]["contact"]["total"] == 1
    assert result["groups"]["contact"]["items"][0]["opportunityId"] == opportunity_id
    assert result["groups"]["contact"]["items"][0]["basis"]["kind"] == "REVIEWED_DEMAND"
    assert result["groups"]["contact"]["items"][0]["basis"]["verifiedAt"].endswith("Z")
    assert len(result["groups"]["contact"]["items"][0]["basis"]["verifiedAt"].split(".")[1]) == 4
    assert result["groups"]["changes"] == {"items":[], "total":0}
    assert "原帖需求变化尚未核验" in result["uncheckedScope"]
    with env.admin.connect() as connection:
        after = connection.execute(
            "SELECT count(*) FROM pilot_followups WHERE tenant_id=%s", (env.tenant,)
        ).fetchone()[0]
    assert after == before


def test_contact_disappears_after_real_exclude_or_strategy_revoke_and_is_owner_scoped(real_strategy_env):
    env = real_strategy_env
    service, binding, assessed, _, _, _, _ = include(env)
    request = _request(env)
    brief = OpportunityBriefService(env.db)
    assert brief.query(env.claims, request)["groups"]["contact"]["total"] == 1
    service.verify_source(env.claims, verification_payload(binding, status="BLOCKED"))
    assert brief.query(env.claims, request | {"requestId":str(uuid4())})["groups"]["contact"]["total"] == 0
    excluded = service.review(env.claims, review_payload(binding, "EXCLUDE",
        assessmentId=assessed["assessment"]["id"], humanConfirmed=True,
        evidence=assessment()["evidence"], reason="需求已不适合"))
    assert excluded["receipt"]["outcome"] == "EXCLUDED"
    assert brief.query(env.claims, request | {"requestId":str(uuid4())})["groups"]["contact"]["total"] == 0
    other = verify_token_claims(issue_token(env.users[1], SECRET), SECRET)
    other_request = request | {"requestId":str(uuid4()), "userId":other.user_id}
    other_result = brief.query(other, other_request)
    assert other_result["coverage"] == "NOT_CHECKED"
    assert other_result["groups"]["contact"]["total"] == 0
    with pytest.raises(OpportunityBriefError, match="profile_unavailable"):
        brief.query(env.claims, request | {"requestId":str(uuid4()), "profileId":str(uuid4())})
    foreign = verify_token_claims(issue_token(env.users[2], SECRET), SECRET)
    with env.admin.connect() as connection:
        foreign_tenant = connection.execute("SELECT tenant_id FROM pilot_users WHERE user_id=%s", (foreign.user_id,)).fetchone()[0]
    with pytest.raises(OpportunityBriefError, match="profile_unavailable"):
        brief.query(foreign, request | {"requestId":str(uuid4()), "userId":foreign.user_id,
                                      "accountScopeId":foreign_tenant})
    env.strategies.revoke(env.claims, revoke_body(env.confirmed))
    assert brief.query(env.claims, request | {"requestId":str(uuid4())})["groups"]["contact"]["total"] == 0


def test_latest_void_followup_does_not_revive_older_due_plan(real_strategy_env):
    env = real_strategy_env
    *_, opportunity_id = include(env)
    request = _request(env)
    due = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    if due <= datetime.now(UTC):
        due = datetime.now(UTC)
    contacted_id, record_id = str(uuid4()), str(uuid4())
    with env.admin.connect() as connection:
        connection.execute("""INSERT INTO pilot_structured_followup_revisions
          (tenant_id,owner_user_id,record_id,revision,opportunity_id,profile_version_id,status,note,next_step,assignee_user_id,state)
          VALUES(%s,%s,%s,1,%s,%s,'CONTACTED','已经真实联系','',%s,'ACTIVE')""",
          (env.tenant,env.claims.user_id,contacted_id,opportunity_id,env.profile,env.claims.user_id))
        connection.execute("""INSERT INTO pilot_structured_followup_revisions
          (tenant_id,owner_user_id,record_id,revision,opportunity_id,profile_version_id,status,note,next_step,next_followup_at,assignee_user_id,state)
          VALUES(%s,%s,%s,1,%s,%s,'CONTACTED','已联系','今天复核',%s,%s,'ACTIVE')""",
          (env.tenant,env.claims.user_id,record_id,opportunity_id,env.profile,due,env.claims.user_id))
    brief = OpportunityBriefService(env.db)
    assert brief.query(env.claims, request)["groups"]["followup"]["total"] == 1
    with env.admin.connect() as connection:
        connection.execute("ALTER TABLE pilot_structured_followup_revisions DISABLE TRIGGER pilot_structured_followup_revisions_immutable")
        connection.execute("""INSERT INTO pilot_structured_followup_revisions
          (tenant_id,owner_user_id,record_id,revision,opportunity_id,profile_version_id,status,note,next_step,next_followup_at,assignee_user_id,state,reason)
          VALUES(%s,%s,%s,2,%s,%s,'CONTACTED','已联系','今天复核',%s,%s,'VOID','计划撤销')""",
          (env.tenant,env.claims.user_id,record_id,opportunity_id,env.profile,due,env.claims.user_id))
        connection.execute("ALTER TABLE pilot_structured_followup_revisions ENABLE TRIGGER pilot_structured_followup_revisions_immutable")
    assert brief.query(env.claims, request | {"requestId":str(uuid4())})["groups"]["followup"]["total"] == 0
    assert brief.query(env.claims, request | {"requestId":str(uuid4())})["groups"]["contact"]["total"] == 0
    with env.admin.connect() as connection:
        connection.execute("ALTER TABLE pilot_structured_followup_revisions DISABLE TRIGGER pilot_structured_followup_revisions_immutable")
        connection.execute("DELETE FROM pilot_structured_followup_revisions WHERE tenant_id=%s", (env.tenant,))
        connection.execute("ALTER TABLE pilot_structured_followup_revisions ENABLE TRIGGER pilot_structured_followup_revisions_immutable")


def test_include_without_literal_own_demand_citation_is_not_recommended(real_strategy_env):
    env = real_strategy_env
    service = real_review(env)
    value = assessment()
    value["intent"]["citations"] = []
    value["intent"]["level"] = "UNKNOWN"
    value["urgency"]["citations"] = []
    value["urgency"]["level"] = "UNKNOWN"
    value["actionability"]["citations"] = []
    value["actionability"]["level"] = "UNKNOWN"
    service.model.assess = lambda **_: (value, None)
    include(env, service=service)
    result = OpportunityBriefService(env.db).query(env.claims, _request(env))
    assert result["coverage"] == "PARTIAL"
    assert result["groups"]["contact"]["total"] == 0


def _request(env):
    with env.admin.connect() as connection:
        version = connection.execute("SELECT version FROM business_profile_versions WHERE profile_version_id=%s", (env.profile,)).fetchone()[0]
    return {"contractVersion":1,"requestId":str(uuid4()),"userId":env.claims.user_id,
            "accountScopeId":env.tenant,"scopeVersion":1,"profileId":env.profile,
            "profileVersion":version,"businessDate":datetime.now(UTC).date().isoformat(),"timezone":"UTC"}
