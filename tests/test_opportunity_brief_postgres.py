"""Restricted PostgreSQL projection; all source facts are synthetic."""
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pilot.opportunity_brief import OpportunityBriefService
from tests.test_candidate_review_postgres import (
    execution_databases, execution_env, raw_databases, raw_env, databases, env,
)
from tests.test_confirmed_strategy_review_postgres import real_strategy_env
from tests.test_opportunity_evidence_postgres import include


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
    assert result["groups"]["changes"] == {"items":[], "total":0}
    assert "原帖需求变化尚未核验" in result["uncheckedScope"]
    with env.admin.connect() as connection:
        after = connection.execute(
            "SELECT count(*) FROM pilot_followups WHERE tenant_id=%s", (env.tenant,)
        ).fetchone()[0]
    assert after == before
