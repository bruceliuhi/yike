"""Real restricted PostgreSQL evidence capture; source/model data is synthetic."""
import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from pilot.auth import issue_token, verify_token_claims
from pilot.candidate_ingestion import CandidateIngestionError
from pilot.opportunity_evidence import (
    OpportunityEvidenceError,
    canonical_json,
    evidence_digest,
)
from pilot.store import PilotStore
from tests.test_candidate_review_postgres import (
    BoundaryModel,
    SECRET,
    assessment,
    databases,
    env,
    execution_databases,
    execution_env,
    raw_databases,
    raw_env,
    review_payload,
    seed,
)
from tests.test_confirmed_strategy_review_postgres import (
    prepare_review,
    real_review,
    real_strategy_env,
)


ROOT = Path(__file__).parents[1]


def include(env, service=None, **record_changes):
    service, binding, assessed, check, decision = prepare_review(
        env, service=service, **record_changes
    )
    included = service.review(env.claims, decision)
    opportunity_id = included["receipt"]["opportunityId"]
    return service, binding, assessed, check, decision, included, opportunity_id


def test_real_include_captures_source_evidence(real_strategy_env):
    env = real_strategy_env
    old = (datetime.now(UTC) - timedelta(seconds=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    service, binding, assessed, check, decision = prepare_review(
        env, observed_at=old, published_at=old
    )
    with env.admin.connect() as conn:
        first_observation = conn.execute(
            "SELECT current_observation_id FROM pilot_candidate_projections WHERE candidate_id=%s",
            (binding["candidateId"],),
        ).fetchone()[0]
    same_binding = seed(env, published_at=old) | {"profileVersion": env.profile_number}
    assert same_binding == binding

    included = service.review(env.claims, decision)
    detail = env.store.get_opportunity(env.claims.user_id, included["receipt"]["opportunityId"])

    assert included["receipt"]["outcome"] == "IMPORTED"
    evidence = detail["source_evidence"]
    assert evidence["status"] == "CAPTURED"
    assert evidence["snapshot_sha256"] == evidence_digest(evidence["snapshot"])
    snapshot = evidence["snapshot"]
    assert snapshot["opportunity_id"] == detail["opportunity_id"]
    assert snapshot["source"]["version_id"] == binding["sourceVersionId"]
    assert snapshot["assessment"]["id"] == assessed["assessment"]["id"]
    assert snapshot["assessment"]["profile_version_id"] == env.profile
    assert snapshot["assessment"]["citations"] == [
        {"dimension": "businessMatch", "field": "source.title", "quote": "食品工厂"},
        {"dimension": "intent", "field": "source.body", "quote": "采购输送设备"},
        {"dimension": "urgency", "field": "source.body", "quote": "月底前"},
    ]
    assert snapshot["assessment"]["omitted_profile_citations"] == 1
    assert set(snapshot["verification"]) == {
        "method", "status_at_capture", "checked_at", "opening_method", "contact_method"
    }
    assert snapshot["verification"]["status_at_capture"] == "OPEN"
    assert "locator" not in snapshot["verification"] and "reason" not in snapshot["assessment"]
    with env.admin.connect() as conn:
        selected = conn.execute(
            "SELECT current_observation_id FROM pilot_candidate_projections WHERE candidate_id=%s",
            (binding["candidateId"],),
        ).fetchone()[0]
        raw_version = conn.execute(
            "SELECT content_version FROM pilot_candidate_versions WHERE version_id=%s",
            (binding["sourceVersionId"],),
        ).fetchone()[0]
    assert str(selected) == snapshot["observation"]["id"]
    assert selected != first_observation
    assert raw_version == snapshot["source"]["content_sha256"]


def test_comment_parent_roles_are_retained_without_reassignment(real_strategy_env):
    env = real_strategy_env
    service = real_review(env)

    def comment_assessment(**kwargs):
        value = assessment()
        value["businessMatch"]["citations"][1] = {
            "field": "parent.title", "quote": "食品工厂扩产"
        }
        value["businessMatch"]["citations"].append(
            {"field": "parent.body", "quote": "父评论  原文"}
        )
        return value, None

    service.model.assess = comment_assessment
    parent = {
        "external_comment_id": "parent-comment",
        "body": "父评论  原文",
        "author_public_id": "parent-author",
        "published_at": None,
        "public_url": None,
    }
    *_, opportunity_id = include(
        env,
        service,
        kind="COMMENT",
        external_source_id="parent-post",
        external_comment_id="current-comment",
        parent=parent,
    )

    source = env.store.get_opportunity(env.users[0], opportunity_id)["source_evidence"]["snapshot"]["source"]
    assert source["title"] is None
    assert source["container_title"] == "食品工厂扩产"
    assert source["body"] == "我们工厂想采购输送设备，月底前找团队报价。"
    assert source["parent"] == parent
    fields = [item["field"] for item in env.store.get_opportunity(
        env.users[0], opportunity_id
    )["source_evidence"]["snapshot"]["assessment"]["citations"]]
    assert "source.container_title" in fields and "source.parent.body" in fields


def test_same_tenant_shares_only_projection_and_other_tenant_cannot_read(real_strategy_env):
    env = real_strategy_env
    service, binding, assessed, check, decision, included, opportunity_id = include(env)
    same_tenant = env.store.get_opportunity(env.users[1], opportunity_id)
    assert same_tenant["source_evidence"]["status"] == "CAPTURED"
    assert "PRIVATE" not in repr(same_tenant["source_evidence"])

    other_claims = verify_token_claims(issue_token(env.users[1], SECRET), SECRET)
    assert service.list_candidates(other_claims)["total"] == 0
    with pytest.raises(CandidateIngestionError, match="request_not_found"):
        service.get_request(other_claims, decision["requestId"])
    with pytest.raises(KeyError, match="record not found in tenant"):
        env.store.get_opportunity(env.users[2], opportunity_id)


def test_replay_duplicate_and_later_signed_source_do_not_replace_evidence(real_strategy_env):
    env = real_strategy_env
    old = (datetime.now(UTC) - timedelta(seconds=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    service, binding, assessed, check, decision, first, opportunity_id = include(
        env, observed_at=old, published_at=old
    )
    before = env.store.get_opportunity(env.users[0], opportunity_id)["source_evidence"]
    assert service.review(env.claims, decision) == first
    duplicate = service.review(
        env.claims, decision | {"requestId": str(uuid4())}
    )
    assert duplicate["receipt"]["outcome"] == "ALREADY_IMPORTED"

    changed = seed(env, body="我们工厂已取消采购。", published_at=old)
    assert changed["candidateId"] == binding["candidateId"]
    after = env.store.get_opportunity(env.users[0], opportunity_id)["source_evidence"]
    assert after == before
    with env.admin.connect() as conn:
        assert str(conn.execute(
            "SELECT current_observation_id FROM pilot_candidate_projections WHERE candidate_id=%s",
            (binding["candidateId"],),
        ).fetchone()[0]) != before["snapshot"]["observation"]["id"]


def test_legacy_trusted_import_is_explicitly_not_captured(real_strategy_env):
    env = real_strategy_env
    imported = PilotStore(env.admin).import_opportunity(
        env.users[0],
        env.profile,
        "legacy-" + uuid4().hex,
        {
            "source_platform": "PUBLIC_WEB",
            "source_external_id": "legacy-" + uuid4().hex,
            "public_url": "https://example.com/legacy",
            "title": "legacy title",
            "buyer": "legacy buyer",
            "summary": "legacy summary",
            "contact_path": "PUBLIC_CONTACT",
            "public_excerpt": "legacy excerpt",
            "draft_comment": "legacy comment",
            "draft_dm": "legacy dm",
        },
    )
    detail = env.store.get_opportunity(env.users[0], imported["opportunity_id"])
    assert detail["source_evidence"] == {"status": "UNAVAILABLE", "reason": "NOT_CAPTURED"}


def test_migration_grant_rls_and_direct_invalid_insertions(real_strategy_env):
    env = real_strategy_env
    service, binding, assessed, check, decision, first, opportunity_id = include(env)
    duplicate_request = decision | {"requestId": str(uuid4())}
    duplicate = service.review(env.claims, duplicate_request)
    assert duplicate["receipt"]["outcome"] == "ALREADY_IMPORTED"
    with env.admin.connect() as conn:
        stored = conn.execute(
            "SELECT payload,payload_sha256 FROM pilot_opportunity_evidence WHERE tenant_id=%s AND opportunity_id=%s",
            (env.tenant, opportunity_id),
        ).fetchone()
        conn.execute(
            "DELETE FROM pilot_opportunity_evidence WHERE tenant_id=%s AND opportunity_id=%s",
            (env.tenant, opportunity_id),
        )
    payload, digest = stored

    def direct_insert(user, request_id, value):
        with env.db.connect() as conn:
            conn.execute(
                "SELECT set_config('yike.tenant_id',%s,true),set_config('yike.user_id',%s,true)",
                (env.tenant, user),
            )
            conn.execute(
                "INSERT INTO pilot_opportunity_evidence(tenant_id,opportunity_id,included_by_user_id,include_request_id,payload,payload_sha256) VALUES(%s,%s,%s,%s,%s::jsonb,%s)",
                (env.tenant, opportunity_id, user, request_id, canonical_json(value), evidence_digest(value)),
            )

    with pytest.raises((psycopg.errors.RaiseException, psycopg.errors.InsufficientPrivilege)):
        direct_insert(env.users[1], decision["requestId"], payload)
    with pytest.raises(psycopg.errors.RaiseException, match="binding mismatch"):
        direct_insert(env.users[0], duplicate_request["requestId"], payload)
    mismatched = copy.deepcopy(payload)
    mismatched["source"]["version_id"] = str(uuid4())
    with pytest.raises(psycopg.errors.RaiseException, match="binding mismatch"):
        direct_insert(env.users[0], decision["requestId"], mismatched)

    env.admin.migrate()
    env.admin.migrate()
    with env.db.connect() as conn:
        role = conn.execute("SELECT current_user").fetchone()[0]
    with env.admin.connect() as conn:
        conn.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
        grant = (ROOT / "deploy/grant_opportunity_evidence.sql").read_text()
        conn.execute(grant)
        conn.execute(grant)
        assert conn.execute(
            "SELECT count(*) FROM pilot_schema_meta WHERE version='v02-opportunity-evidence'"
        ).fetchone()[0] == 1
    with env.db.connect() as conn:
        assert conn.execute(
            "SELECT row_security_active('pilot_opportunity_evidence'::regclass)"
        ).fetchone()[0]
        assert conn.execute(
            "SELECT has_table_privilege(current_user,'pilot_opportunity_evidence','SELECT')"
        ).fetchone()[0]
        assert conn.execute(
            "SELECT has_table_privilege(current_user,'pilot_opportunity_evidence','INSERT')"
        ).fetchone()[0]
        for privilege in ("UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
            assert not conn.execute(
                "SELECT has_table_privilege(current_user,'pilot_opportunity_evidence',%s)",
                (privilege,),
            ).fetchone()[0]
        assert conn.execute(
            "SELECT relowner<>(SELECT oid FROM pg_roles WHERE rolname=current_user) FROM pg_class WHERE oid='pilot_opportunity_evidence'::regclass"
        ).fetchone()[0]


def test_evidence_failure_rolls_back_import_and_include_rows(real_strategy_env):
    env = real_strategy_env
    service, binding, assessed, check, decision = prepare_review(env)
    with env.admin.connect() as conn:
        conn.execute(
            "ALTER TABLE pilot_opportunity_evidence ADD CONSTRAINT synthetic_reject_evidence CHECK(included_by_user_id<>included_by_user_id) NOT VALID"
        )
    try:
        with pytest.raises(CandidateIngestionError, match="review_outcome_unknown"):
            service.review(env.claims, decision)
        with env.admin.connect() as conn:
            assert conn.execute(
                "SELECT count(*) FROM pilot_opportunities WHERE tenant_id=%s", (env.tenant,)
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT count(*) FROM pilot_sources WHERE tenant_id=%s", (env.tenant,)
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT count(*) FROM pilot_candidate_reviews WHERE tenant_id=%s AND request_id=%s",
                (env.tenant, decision["requestId"]),
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT count(*) FROM pilot_candidate_review_requests WHERE tenant_id=%s AND request_id=%s",
                (env.tenant, decision["requestId"]),
            ).fetchone()[0] == 0
    finally:
        with env.admin.connect() as conn:
            conn.execute(
                "ALTER TABLE pilot_opportunity_evidence DROP CONSTRAINT synthetic_reject_evidence"
            )


def test_corrupt_present_digest_raises_fixed_safe_error(real_strategy_env):
    env = real_strategy_env
    *_, opportunity_id = include(env)
    with env.admin.connect() as conn:
        conn.execute("ALTER TABLE pilot_opportunity_evidence DISABLE TRIGGER opportunity_evidence_immutable")
        conn.execute(
            "UPDATE pilot_opportunity_evidence SET payload_sha256=%s WHERE tenant_id=%s AND opportunity_id=%s",
            ("0" * 64, env.tenant, opportunity_id),
        )
        conn.execute("ALTER TABLE pilot_opportunity_evidence ENABLE TRIGGER opportunity_evidence_immutable")
    with pytest.raises(OpportunityEvidenceError, match="corrupt_opportunity_evidence") as caught:
        env.store.get_opportunity(env.users[0], opportunity_id)
    assert caught.value.__context__ is None
