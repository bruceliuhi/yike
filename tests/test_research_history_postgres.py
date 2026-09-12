"""Restricted PostgreSQL coverage for bounded, owner-visible research history."""
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from pilot.research_history import load_research_history
from tests.test_confirmed_strategy_review_postgres import (
    prepare_review,
    real_review,
    real_strategy_env,
)

pytest_plugins = ["tests.test_confirmed_strategy_review_postgres"]


ROOT = Path(__file__).parents[1]


@pytest.fixture
def history_env(real_strategy_env):
    env = real_strategy_env
    with env.db.connect() as connection:
        role = connection.execute("SELECT current_user").fetchone()[0]
    with env.admin.connect() as connection:
        connection.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
        connection.execute((ROOT / "deploy/grant_customer_research_context.sql").read_text())
        env.profile_id = connection.execute(
            "SELECT profile_id FROM business_profile_versions WHERE profile_version_id=%s",
            (env.profile,),
        ).fetchone()[0]
    yield env
    with env.admin.connect() as connection:
        connection.execute("SET LOCAL session_replication_role='replica'")
        for table in (
            "pilot_outreach_results",
            "pilot_outreach_claims",
            "pilot_outreach_queue",
            "pilot_structured_followup_revisions",
        ):
            connection.execute(f"DELETE FROM {table} WHERE tenant_id=ANY(%s)", (env.tenants,))


def history(env, *, owner=None, tenant=None, profile_id=None):
    with env.db.connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('yike.user_id',%s,true),set_config('yike.tenant_id',%s,true)",
            (owner or env.claims.user_id, tenant or env.tenant),
        )
        return load_research_history(
            cursor,
            tenant=tenant or env.tenant,
            owner=owner or env.claims.user_id,
            profile_id=profile_id or env.profile_id,
        )


def included_candidate(env, **changes):
    service, binding, _, _, decision = prepare_review(env, real_review(env), **changes)
    receipt = service.review(env.claims, decision)["receipt"]
    return binding, receipt["opportunityId"]


def insert_followup(env, opportunity_id, *, status, state="ACTIVE", revision=1, record_id=None, happened=None):
    record_id = record_id or str(uuid4())
    happened = happened or datetime.now(UTC)
    with env.admin.connect() as connection:
        connection.execute(
            """INSERT INTO pilot_structured_followup_revisions(
                tenant_id,owner_user_id,record_id,revision,opportunity_id,profile_version_id,
                status,note,occurred_at,next_step,next_followup_at,assignee_user_id,state,
                corrects_id,reason,recorded_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,'合成历史',%s,'',NULL,%s,%s,NULL,NULL,%s)""",
            (env.tenant, env.claims.user_id, record_id, revision, opportunity_id, env.profile,
             status, happened, env.claims.user_id, state, happened),
        )
    return record_id


def insert_outreach(env, opportunity_id, *, status):
    request_id, claim_id, result_id = map(lambda _: str(uuid4()), range(3))
    binding = {"opportunityId": opportunity_id, "channel": "dm"}
    context = {"contextSha256": "b" * 64, "binding": binding,
               "ownerUserId": env.claims.user_id, "accountScope": {"id": env.tenant}}
    request = {"requestId": request_id, "humanConfirmed": True,
               "channelCheck": {"status": "AVAILABLE"}, "context": {"binding": binding},
               "contextSha256": "b" * 64}
    claim = {"action": "CLAIM", "requestId": request_id, "claimId": claim_id}
    result = {"action": "RESULT", "requestId": request_id, "claimId": claim_id,
              "resultId": result_id, "outcome": {"status": status}}
    receipt = {"state": status, "requestId": request_id, "claimId": claim_id,
               "resultId": result_id, "dispatchAllowed": False}
    with env.admin.connect() as connection:
        connection.execute(
            """INSERT INTO pilot_outreach_queue(tenant_id,owner_user_id,request_id,
                opportunity_id,channel,state,request_sha256,request_payload,context_payload)
                VALUES(%s,%s,%s,%s,'dm','QUEUED',%s,%s,%s)""",
            (env.tenant, env.claims.user_id, request_id, opportunity_id, "a" * 64,
             Jsonb(request), Jsonb(context)),
        )
        if status == "QUEUED":
            return
        connection.execute(
            """INSERT INTO pilot_outreach_claims(tenant_id,owner_user_id,request_id,claim_id,
                request_sha256,payload,dispatch_before) VALUES(%s,%s,%s,%s,%s,%s,clock_timestamp()+interval '30 seconds')""",
            (env.tenant, env.claims.user_id, request_id, claim_id, "c" * 64, Jsonb(claim)),
        )
        connection.execute(
            """INSERT INTO pilot_outreach_results(tenant_id,owner_user_id,result_id,request_id,
                claim_id,request_sha256,payload,receipt) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
            (env.tenant, env.claims.user_id, result_id, request_id, claim_id, "d" * 64,
             Jsonb(result), Jsonb(receipt)),
        )


def test_successful_exclude_wins_but_include_does_not_exclude(history_env):
    env = history_env
    excluded_service, excluded, _, _, decision = prepare_review(
        env, real_review(env), public_url="https://example.com/excluded"
    )
    excluded_service.review(env.claims, decision | {"action": "EXCLUDE", "reason": "不匹配"})
    included, _ = included_candidate(env, public_url="https://example.com/included")
    failed_request = str(uuid4())
    with env.admin.connect() as connection:
        connection.execute(
            """INSERT INTO pilot_candidate_review_requests(
                tenant_id,owner_user_id,request_id,candidate_id,fingerprint,action,
                binding_hash,snapshot_key,invocation_id,attempt,status,payload,snapshot,result)
                SELECT tenant_id,owner_user_id,%s,candidate_id,fingerprint,'EXCLUDE',
                    binding_hash,NULL,NULL,0,'FAILED','{}'::jsonb,snapshot,'{}'::jsonb
                FROM pilot_candidate_review_requests
                WHERE tenant_id=%s AND owner_user_id=%s AND candidate_id=%s AND action='INCLUDE'""",
            (failed_request, env.tenant, env.claims.user_id, included["candidateId"]),
        )
    scope, rows = history(env)
    states = {row["source_urls"][0]: row["state"] for row in rows}
    assert scope == "PARTIAL"
    assert states == {
        "https://example.com/excluded": "EXCLUDED",
        "https://example.com/included": "KNOWN",
    }


def test_latest_active_manual_and_only_actual_sent_outreach_are_contact_facts(history_env):
    env = history_env
    _, contacted = included_candidate(env, public_url="https://example.com/manual-contact")
    _, closed = included_candidate(env, public_url="https://example.com/manual-closed")
    _, voided = included_candidate(env, public_url="https://example.com/manual-void")
    _, sent = included_candidate(env, public_url="https://example.com/sent")
    _, unknown = included_candidate(env, public_url="https://example.com/unknown")
    _, queued = included_candidate(env, public_url="https://example.com/queued")
    insert_followup(env, contacted, status="CONTACTED")
    insert_followup(env, closed, status="WON")
    record = insert_followup(env, voided, status="CONTACTED")
    insert_followup(env, voided, status="CONTACTED", state="VOID", revision=2, record_id=record)
    insert_outreach(env, sent, status="SENT")
    insert_outreach(env, unknown, status="UNKNOWN")
    insert_outreach(env, queued, status="QUEUED")

    _, rows = history(env)
    states = {row["source_urls"][0]: row["state"] for row in rows}
    assert states["https://example.com/manual-contact"] == "CONTACTED"
    assert states["https://example.com/manual-closed"] == "CLOSED"
    assert states["https://example.com/sent"] == "CONTACTED"
    assert states["https://example.com/manual-void"] == "KNOWN"
    assert states["https://example.com/unknown"] == "KNOWN"
    assert states["https://example.com/queued"] == "KNOWN"


def test_history_dedupes_source_caps_30_and_does_not_cross_scope_or_emit_unsafe_url(history_env):
    env = history_env
    now = datetime.now(UTC)
    from tests.test_candidate_review_postgres import seed
    bindings = [seed(
        env,
        public_url=("https://example.com/cap-%02d" % index),
        observed_at=(now - timedelta(minutes=index)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        published_at=(now - timedelta(minutes=index)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    ) for index in range(32)]
    # A later version of an existing stable source must remain one history row.
    repeated = seed(env, public_url="https://example.com/cap-00", body="更新版本")
    assert repeated["candidateId"] == bindings[0]["candidateId"]
    unsafe = seed(env, public_url="https://example.com/unsafe", body="不安全 URL")
    # Simulate a persisted legacy row predating today's ingestion URL guard.
    with env.admin.connect() as connection:
        connection.execute("ALTER TABLE pilot_candidate_versions DISABLE TRIGGER USER")
        connection.execute(
            """UPDATE pilot_candidate_versions SET content=jsonb_set(
                content,'{public_url}',to_jsonb(%s::text)) WHERE version_id=%s""",
            ("http://127.0.0.1/private", unsafe["sourceVersionId"]),
        )
        connection.execute("ALTER TABLE pilot_candidate_versions ENABLE TRIGGER USER")

    scope, rows = history(env)
    assert scope == "PARTIAL" and len(rows) == 30
    assert len({row["project_key"] for row in rows}) == 30
    assert all(row["source_urls"] != ["http://127.0.0.1/private"] for row in rows)
    assert history(env, owner=env.users[1])[1] == []
    assert history(env, tenant=env.tenants[1], owner=env.users[2])[1] == []
    assert history(env, profile_id=str(uuid4())) == ("NONE", [])
