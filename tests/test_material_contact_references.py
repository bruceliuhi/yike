"""Restricted PostgreSQL material-to-draft qualification; all data synthetic."""
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from pilot.contact_drafts import DraftSnapshot, snapshot_digest
from pilot.contact_material_references import draft_snapshot_sha
from pilot.auth import verify_token_claims
from pilot.material_contract import MaterialError
from pilot.materials import MaterialStore
from pilot.runtime import build_runtime_app
from pilot.outreach_dispatch import DispatchRequest
from tests.test_contact_drafts_http_postgres import (body, env, execution_databases,
    save)
from tests.test_outreach_dispatch_http_postgres import (databases, draft_databases, queue_databases,
    dispatch, queued)
from tests.test_materials_store import Model
from tests.test_outreach_context_http_postgres import prepared, context
from tests.test_outreach_queue_http_postgres import sign, confirm
from tests.test_device_credentials_postgres import bind
from pilot.device_credentials import DeviceCredentialStore
from nacl.signing import SigningKey
from types import SimpleNamespace
from datetime import UTC, datetime


def reference(env, **changes):
    return {"sourceProfileVersionId": env.profile, "materialId": "external-material",
        "materialVersion": 3, "extractionId": "extract-1", "quote": "真实案例原文"} | changes


def with_references(env, references):
    value = body(env, content="想基于真实案例原文交流一下")
    value["snapshot"]["draft"]["materialReferences"] = references
    value["binding"]["contentHash"] = snapshot_digest(DraftSnapshot.model_validate(value["snapshot"]))
    return value


def seed_material(env, *, visibility="external", status="READY"):
    with env.admin.connect() as connection:
        connection.execute("SELECT set_config('yike.app_role',%s,true)", (env.app.role,))
        connection.execute((Path(__file__).parents[1] / "deploy/grant_materials.sql").read_text())
    store = MaterialStore(env.app, Model({"fields": {"service": "交付结果"},
        "evidence": [{"field": "service", "quote": "真实案例原文"}]}))
    claims = verify_token_claims(env.client.headers["Authorization"].removeprefix("Bearer "),
                                 "synthetic-draft-test-secret")
    saved = store.mutate(claims, {"requestId": str(uuid4()), "profileVersionId": env.profile,
        "change": {"kind": "save", "materialId": "external-material", "expectedVersion": None,
            "input": {"name": "案例", "text": "真实案例原文与交付结果", "purpose": "真实案例",
                      "visibility": visibility}}})["record"]
    parsed = store.mutate(claims, {"requestId": str(uuid4()), "profileVersionId": env.profile,
        "change": {"kind": "parse", "materialId": saved["id"], "expectedVersion": 1}})["record"]
    ready = store.mutate(claims, {"requestId": str(uuid4()), "profileVersionId": env.profile,
        "change": {"kind": "confirm", "materialId": saved["id"], "expectedVersion": 2,
                   "extractionId": parsed["extraction"]["id"], "fields": {"service": "交付结果"}}})["record"]
    if status != "READY":
        impact = store.impact(claims, env.profile, saved["id"], 3, "revoke")
        ready = store.mutate(claims, {"requestId": str(uuid4()), "profileVersionId": env.profile,
            "change": {"kind": "revoke", "materialId": saved["id"], "expectedVersion": 3,
                       "impactToken": impact["token"]}})["record"]
    return ready


def test_valid_reference_changes_hash_and_round_trips_but_legacy_shape_is_unchanged(env):
    ready = seed_material(env)
    legacy = body(env)
    assert "materialReferences" not in legacy["snapshot"]["draft"]
    value = with_references(env, [reference(env, materialVersion=ready["version"],
        extractionId=ready["extraction"]["id"])])
    assert value["binding"]["contentHash"] != legacy["binding"]["contentHash"]
    response = save(env, value)
    assert response.status_code == 200, response.text
    assert response.json()["snapshot"]["draft"]["materialReferences"] == value["snapshot"]["draft"]["materialReferences"]


@pytest.mark.parametrize("change", [
    {"quote": "伪造原文"}, {"materialVersion": 2}, {"extractionId": "old"},
])
def test_stale_or_mismatched_reference_cannot_be_saved(env, change):
    ready = seed_material(env)
    base = {"materialVersion": ready["version"], "extractionId": ready["extraction"]["id"]}
    ref = reference(env, **(base | change))
    value = body(env, content="想基于" + ref["quote"] + "交流一下")
    value["snapshot"]["draft"]["materialReferences"] = [ref]
    value["binding"]["contentHash"] = snapshot_digest(DraftSnapshot.model_validate(value["snapshot"]))
    response = save(env, value)
    assert response.status_code == 409


def test_internal_material_and_duplicate_or_null_references_are_rejected(env):
    ready = seed_material(env, visibility="internal")
    valid = reference(env, materialVersion=ready["version"], extractionId=ready["extraction"]["id"])
    assert save(env, with_references(env, [valid])).status_code == 409
    with pytest.raises(Exception):
        DraftSnapshot.model_validate(body(env)["snapshot"] | {"draft": body(env)["snapshot"]["draft"] |
            {"materialReferences": [valid, valid]}})
    with pytest.raises(Exception):
        DraftSnapshot.model_validate(body(env)["snapshot"] | {"draft": body(env)["snapshot"]["draft"] |
            {"materialReferences": None}})


def test_validate_action_has_claim_shape_and_strict_qualified_contract_inputs():
    base = {"action": "VALIDATE", "requestId": str(uuid4()), "claimId": str(uuid4()),
        "deviceId": str(uuid4()), "credentialVersion": 1, "contextSha256": "a" * 64,
        "resultId": None, "outcome": None}
    assert DispatchRequest.model_validate(base).model_dump() == base
    for change in ({"resultId": str(uuid4())}, {"outcome": {"status": "UNKNOWN"}}):
        with pytest.raises(Exception):
            DispatchRequest.model_validate(base | change)


def test_signed_validate_rechecks_existing_unknown_claim_without_reclaim(env):
    _, claim, key = queued(env)
    claimed = dispatch(env, claim, key)
    assert claimed.status_code == 200 and claimed.json()["state"] == "UNKNOWN"
    validate = claim | {"action": "VALIDATE", "resultId": None, "outcome": None}
    qualified = dispatch(env, validate, key)
    assert qualified.status_code == 200, qualified.text
    assert qualified.json() == {"state": "QUALIFIED", "requestId": claim["requestId"],
        "claimId": claim["claimId"], "contextSha256": claim["contextSha256"],
        "dispatchBefore": claimed.json()["dispatchBefore"]}


def test_draft_is_in_material_impact_and_new_head_invalidates_old_token(env):
    ready = seed_material(env)
    valid = reference(env, materialVersion=ready["version"], extractionId=ready["extraction"]["id"])
    first = with_references(env, [valid])
    assert save(env, first).status_code == 200
    claims = verify_token_claims(env.client.headers["Authorization"].removeprefix("Bearer "),
                                 "synthetic-draft-test-secret")
    materials = MaterialStore(env.app)
    scope = dict(tenant=env.tenant, owner=env.users[0], source_profile_version_id=env.profile,
                 material_id="external-material", material_version=ready["version"])
    with env.admin.connect() as connection, connection.cursor() as cursor:
        before_sha = draft_snapshot_sha(cursor, **scope)
    impact = materials.impact(claims, env.profile, "external-material", ready["version"], "revoke")
    assert {item["kind"] for item in impact["references"]} == {"draft"}
    second = body(env, content="继续基于真实案例原文交流", version=3, saved=first["snapshot"]["draft"]["content"],
                  previous=first["binding"]["requestId"])
    second["snapshot"]["draft"]["materialReferences"] = [valid]
    second["binding"]["contentHash"] = snapshot_digest(DraftSnapshot.model_validate(second["snapshot"]))
    assert save(env, second).status_code == 200
    with env.admin.connect() as connection, connection.cursor() as cursor:
        assert draft_snapshot_sha(cursor, **scope) != before_sha
    request = {"requestId": str(uuid4()), "profileVersionId": env.profile,
        "change": {"kind": "revoke", "materialId": "external-material", "expectedVersion": ready["version"],
                   "impactToken": impact["token"]}}
    failed = materials.mutate(claims, request)
    assert failed["status"] == "FAILED" and failed["confirmedNoChange"] is True


def test_reference_quote_must_also_be_present_in_saved_draft_content(env):
    ready = seed_material(env)
    ref = reference(env, materialVersion=ready["version"], extractionId=ready["extraction"]["id"])
    value = body(env)
    value["snapshot"]["draft"]["materialReferences"] = [ref]
    with pytest.raises(Exception):
        DraftSnapshot.model_validate(value["snapshot"])


def test_xhs_channel_accepts_only_strict_already_qualified_material_references():
    from app.xhs_comment_channel import _snapshot
    from tests.test_xhs_comment_channel import context
    value = context()
    value["draft"]["materialReferences"] = [{"sourceProfileVersionId": value["profileVersionId"],
        "materialId": "external-material", "materialVersion": 3, "extractionId": "extract-1",
        "quote": "逐字引用"}]
    assert _snapshot(value)[0]["draft"]["materialReferences"][0]["quote"] == "逐字引用"
    value["draft"]["materialReferences"][0]["extra"] = True
    with pytest.raises(RuntimeError, match="^CHANNEL_UNAVAILABLE$"):
        _snapshot(value)


def test_revoke_after_claim_makes_final_validate_fail_closed_and_keeps_unknown(env):
    ready = seed_material(env)
    context_request, _ = prepared(env)
    prior = env.client.get(f"/api/ui/opportunities/{env.opp}/contact-drafts/dm").json()
    ref = reference(env, materialVersion=ready["version"], extractionId=ready["extraction"]["id"])
    update = body(env, content="发送前核对真实案例原文", saved=prior["snapshot"]["draft"]["content"],
        version=prior["snapshot"]["draft"]["version"] + 1, previous=prior["binding"]["requestId"])
    update["snapshot"]["draft"].update(accountId=prior["snapshot"]["draft"]["accountId"],
        recipient=prior["snapshot"]["draft"]["recipient"], materialReferences=[ref])
    update["binding"]["contentHash"] = snapshot_digest(DraftSnapshot.model_validate(update["snapshot"]))
    assert save(env, update).status_code == 200
    context_request["binding"] = update["binding"]
    current = context(env, context_request)
    key = SigningKey.generate()
    claims = verify_token_claims(env.client.headers["Authorization"].removeprefix("Bearer "),
                                 "synthetic-draft-test-secret")
    bind(SimpleNamespace(service=DeviceCredentialStore(env.app), claims=claims,
                         device=context_request["deviceId"]), key)
    queued_request = {"requestId": str(uuid4()), "context": context_request,
        "contextSha256": current.json()["contextSha256"], "credentialVersion": 1,
        "humanConfirmed": True, "channelCheck": {"status": "AVAILABLE",
            "observedAt": datetime.now(UTC).isoformat()}}
    assert confirm(env, queued_request, sign(env, queued_request, key)).status_code == 200
    original = env.client
    env.client = TestClient(build_runtime_app(env.app, auth_secret="synthetic-draft-test-secret",
        environment={"YIKE_PILOT_OUTREACH_PLATFORMS": "BILIBILI"}), base_url="https://pilot.example")
    env.client.headers.update(original.headers)
    claim = {"action": "CLAIM", "requestId": queued_request["requestId"], "claimId": str(uuid4()),
        "deviceId": context_request["deviceId"], "credentialVersion": 1,
        "contextSha256": queued_request["contextSha256"]}
    assert dispatch(env, claim, key).json()["state"] == "UNKNOWN"
    materials = MaterialStore(env.app)
    impact = materials.impact(claims, env.profile, ready["id"], ready["version"], "revoke")
    assert materials.mutate(claims, {"requestId": str(uuid4()), "profileVersionId": env.profile,
        "change": {"kind": "revoke", "materialId": ready["id"], "expectedVersion": ready["version"],
                   "impactToken": impact["token"]}})["status"] == "SUCCEEDED"
    validate = claim | {"action": "VALIDATE", "resultId": None, "outcome": None}
    assert dispatch(env, validate, key).status_code == 409
    assert env.client.get("/api/ui/outreach/queue/" + queued_request["requestId"]).json()["state"] == "UNKNOWN"
