from pathlib import Path
from uuid import uuid4

import pytest

from pilot.followup_service import FollowupError, FollowupService
from tests.test_confirmed_strategy_review_postgres import real_strategy_env, prepare_review

pytest_plugins = ["tests.test_confirmed_strategy_review_postgres"]

ROOT = Path(__file__).parents[1]


@pytest.fixture
def followup_env(real_strategy_env):
    env = real_strategy_env
    service, binding, _, _, decision = prepare_review(env)
    included = service.review(env.claims, decision)
    with env.db.connect() as conn:
        role = conn.execute("SELECT current_user").fetchone()[0]
    with env.admin.connect() as conn:
        conn.execute((ROOT / "migrations/131_v02_structured_followups.sql").read_text())
        conn.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
        grant = (ROOT / "deploy/grant_structured_followups.sql").read_text()
        conn.execute(grant); conn.execute(grant)
    env.followups = FollowupService(env.db)
    env.opportunity = included["receipt"]["opportunityId"]
    yield env
    with env.admin.connect() as conn:
        for table in ("pilot_followup_operations", "pilot_followup_reply_reads", "pilot_structured_followup_revisions"):
            conn.execute(f"ALTER TABLE {table} DISABLE TRIGGER USER")
            conn.execute(f"DELETE FROM {table} WHERE tenant_id=ANY(%s)", (env.tenants,))
            conn.execute(f"ALTER TABLE {table} ENABLE TRIGGER USER")


def _binding(env, action="create", target="", revision=0, request=None):
    return {"opportunityId": env.opportunity, "profileVersionId": env.profile, "action": action,
            "targetId": target, "targetRevision": revision, "requestId": request or str(uuid4())}


def _values(env, note="已联系"):
    return {"status": "CONTACTED", "note": note, "occurredAt": "2026-09-10T02:00:00Z",
            "nextStep": "发送资料", "nextFollowupAt": "2026-09-12T01:00:00Z", "ownerId": env.claims.user_id}


def test_create_replay_conflict_correct_void_and_old_receipt_stays_frozen(followup_env):
    env = followup_env
    request = {"binding": _binding(env), "values": _values(env)}
    created = env.followups.mutate(env.claims, request)
    assert created["status"] == "SUCCEEDED" and created["confirmed"] is True
    assert env.followups.mutate(env.claims, request) == created
    assert env.followups.operation(env.claims, request["binding"]) == created
    with pytest.raises(FollowupError, match="request_conflict"):
        env.followups.mutate(env.claims, request | {"values": _values(env, "改写")})

    old = created["record"]
    correction = {"binding": _binding(env, "correct", old["id"], old["revision"]),
                  "values": _values(env, "已纠正"), "reason": "原记录时间有误"}
    corrected = env.followups.mutate(env.claims, correction)
    assert corrected["record"]["correctsId"] == old["id"]
    snapshot = env.followups.list(env.claims)
    assert {r["state"] for r in snapshot["records"]} == {"CORRECTED", "ACTIVE"}
    assert env.followups.operation(env.claims, request["binding"]) == created

    current = corrected["record"]
    voided = env.followups.mutate(env.claims, {"binding": _binding(env, "void", current["id"], 1), "reason": "客户要求撤销"})
    assert voided["record"]["state"] == "VOID" and voided["record"]["revision"] == 2
    with pytest.raises(FollowupError, match="followup_revision_conflict"):
        env.followups.mutate(env.claims, {"binding": _binding(env, "void", current["id"], 1), "reason": "重复撤销"})


def test_unknown_operation_is_not_fabricated_failed(followup_env):
    with pytest.raises(FollowupError, match="operation_not_found") as error:
        followup_env.followups.operation(followup_env.claims, _binding(followup_env))
    assert error.value.status == 404
