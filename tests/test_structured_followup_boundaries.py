"""Restricted-PG follow-up boundaries; all business/platform inputs are synthetic."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest

from pilot.auth import issue_token, verify_token_claims
from pilot.followup_service import FollowupError, FollowupService, parse_mutation
from tests.test_signed_reply_http_postgres import env, setup, record, SECRET

pytest_plugins = ["tests.test_signed_reply_http_postgres"]
ROOT = Path(__file__).parents[1]


@pytest.fixture
def boundary_env(env):
    with env.admin.connect() as conn:
        conn.execute("SELECT set_config('yike.app_role',%s,true)", (env.app.role,))
        grant = (ROOT / "deploy/grant_structured_followups.sql").read_text()
        conn.execute(grant); conn.execute(grant)
    env.followups = FollowupService(env.app)
    yield env
    with env.admin.connect() as conn:
        for table in ("pilot_followup_operations", "pilot_followup_reply_reads", "pilot_structured_followup_revisions"):
            conn.execute(f"ALTER TABLE {table} DISABLE TRIGGER USER")
            conn.execute(f"DELETE FROM {table} WHERE tenant_id=%s", (env.tenant,))
            conn.execute(f"ALTER TABLE {table} ENABLE TRIGGER USER")


def binding(env, action="create", target="", revision=0, request=None, **changes):
    value = {"opportunityId": env.opp, "profileVersionId": env.profile, "action": action,
             "targetId": target, "targetRevision": revision, "requestId": request or str(uuid4())}
    value.update(changes)
    return value


def values(env, **changes):
    value = {"status": "CONTACTED", "note": "合成边界记录", "occurredAt": None,
             "nextStep": "人工核对", "nextFollowupAt": None, "ownerId": env.users[0]}
    value.update(changes)
    return value


def test_owner_tenant_member_and_profile_boundaries(boundary_env):
    env = boundary_env
    claims = verify_token_claims(env.client.headers["Authorization"].removeprefix("Bearer "), SECRET)
    created = env.followups.mutate(claims, {"binding": binding(env), "values": values(env)})
    same_tenant = verify_token_claims(issue_token(env.users[1], SECRET), SECRET)
    other_tenant = verify_token_claims(issue_token(env.users[2], SECRET), SECRET)
    assert env.followups.list(same_tenant)["records"] == []
    assert env.followups.list(other_tenant)["records"] == []
    members = env.followups.list(claims)["members"]
    assert env.users[1] in [member["id"] for member in members]
    assigned = env.followups.mutate(claims, {"binding": binding(env), "values": values(env, ownerId=env.users[1])})
    assert assigned["record"]["ownerId"] == env.users[1]
    assert env.followups.list(same_tenant)["records"] == []
    with pytest.raises(FollowupError, match="followup_not_found"):
        env.followups.mutate(same_tenant, {"binding": binding(env, "void", created["record"]["id"], 1), "reason": "无权"})
    with pytest.raises(FollowupError, match="opportunity_not_found"):
        env.followups.mutate(other_tenant, {"binding": binding(env), "values": values(env)})
    with pytest.raises(FollowupError, match="member_not_found"):
        env.followups.mutate(claims, {"binding": binding(env), "values": values(env, ownerId=env.users[2])})
    with pytest.raises(FollowupError, match="profile_conflict"):
        env.followups.mutate(claims, {"binding": binding(env, profileVersionId=str(uuid4())), "values": values(env)})


def test_same_target_revision_allows_only_one_correct_or_void(boundary_env):
    env = boundary_env
    claims = verify_token_claims(env.client.headers["Authorization"].removeprefix("Bearer "), SECRET)
    created = env.followups.mutate(claims, {"binding": binding(env), "values": values(env)})["record"]
    requests = [
        {"binding": binding(env, "correct", created["id"], 1), "values": values(env, note="合成纠正"), "reason": "纠正"},
        {"binding": binding(env, "void", created["id"], 1), "reason": "撤销"},
    ]
    def run(request):
        try:
            return env.followups.mutate(claims, request)
        except FollowupError as error:
            return error
    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(run, requests))
    assert sum(type(item) is dict for item in outcomes) == 1
    conflicts = [item for item in outcomes if isinstance(item, FollowupError)]
    assert [(item.code, item.status) for item in conflicts] == [("followup_revision_conflict", 409)]


def test_signed_reply_projection_app_read_and_original_request_replay(boundary_env):
    env = boundary_env
    claims = verify_token_claims(env.client.headers["Authorization"].removeprefix("Bearer "), SECRET)
    _queue, signed_request, key = setup(env)
    response = record(env, signed_request, key)
    assert response.status_code == 200, response.text
    reply_id = response.json()["event"]["event_id"]
    with env.admin.connect() as conn:
        before = conn.execute("SELECT payload,payload_sha256,device_attestation FROM pilot_reply_events WHERE event_id=%s ORDER BY revision", (reply_id,)).fetchall()
    projected = env.followups.replies(claims, env.opp)
    assert len(projected) == 1 and projected[0]["id"] == reply_id and projected[0]["read"] is False
    request = {"binding": binding(env, "mark-read", reply_id, projected[0]["revision"])}
    receipt = env.followups.mutate(claims, request)
    assert receipt["reply"]["read"] is True and receipt["reply"]["revision"] == projected[0]["revision"] + 1
    assert env.followups.mutate(claims, request) == receipt
    assert env.followups.operation(claims, request["binding"]) == receipt
    assert env.followups.replies(claims, env.opp) == [receipt["reply"]]
    with env.admin.connect() as conn:
        after = conn.execute("SELECT payload,payload_sha256,device_attestation FROM pilot_reply_events WHERE event_id=%s ORDER BY revision", (reply_id,)).fetchall()
    assert after == before


@pytest.mark.parametrize("state", ["VOID", "CORRECTED"])
def test_signed_reply_control_history_is_not_projected_as_live(boundary_env, state):
    import copy
    from datetime import UTC, datetime

    env = boundary_env
    claims = verify_token_claims(env.client.headers["Authorization"].removeprefix("Bearer "), SECRET)
    _queue, signed_request, key = setup(env)
    saved = record(env, signed_request, key)
    assert saved.status_code == 200, saved.text
    control = copy.deepcopy(signed_request)
    control["event"].update(event_id=str(uuid4()), state=state,
        corrects_event_id=saved.json()["event"]["event_id"], reason="合成历史控制事件",
        observed_at=datetime.now(UTC).isoformat())
    changed = record(env, control, key)
    assert changed.status_code == 200, changed.text
    assert env.followups.replies(claims, env.opp) == []
    with env.admin.connect() as conn:
        assert conn.execute("SELECT count(*) FROM pilot_reply_events WHERE event_id=ANY(%s)",
            ([saved.json()["event"]["event_id"], control["event"]["event_id"]],)).fetchone() == (2,)


@pytest.mark.parametrize("change", [
    {"values": {"note": "bad\x00note"}},
    {"binding": {"targetRevision": 2_147_483_648}},
    {"values": {"nextStep": "\ud800"}},
])
def test_invalid_text_and_out_of_range_revision_are_422(change):
    fake = type("E", (), {"opp": str(uuid4()), "profile": str(uuid4()), "users": [str(uuid4())]})()
    raw = {"binding": binding(fake), "values": values(fake)}
    for section, patch in change.items():
        raw[section].update(patch)
    with pytest.raises(FollowupError, match="invalid_request") as error:
        parse_mutation(raw)
    assert error.value.status == 422
