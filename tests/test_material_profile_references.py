import hashlib
import json

import pytest

from tests.test_materials_store import database, env, save_request, mutate, Model
from pilot.materials import MaterialStore
from pilot.store import PilotStore
from pilot.search_suggestions import SearchSuggestionStore, SearchSuggestionStoreError
from uuid import uuid4


DESCRIPTION = "\n".join([
    '服务内容："知识库实施"',
    '目标客户："制造企业"',
    '服务地区："上海"',
    '项目偏好："明确预算"',
    '排除项："招聘"',
])


def test_canonical_description_parses_exactly_five_bounded_fields():
    from pilot.material_references import parse_profile_description

    assert parse_profile_description(DESCRIPTION) == {
        "service": "知识库实施",
        "customer": "制造企业",
        "regions": "上海",
        "preference": "明确预算",
        "exclusions": "招聘",
    }
    with pytest.raises(ValueError):
        parse_profile_description(DESCRIPTION + '\n服务内容："重复"')
    with pytest.raises(ValueError):
        parse_profile_description(DESCRIPTION.replace('服务内容："知识库实施"', '服务内容：123'))


def test_reference_identity_changes_profile_digest_without_trusting_client_summary():
    from pilot.material_references import profile_content_digest

    first = [{"field": "service", "source_owner_user_id": "owner-a", "material_id": "m",
              "material_version": 4, "extraction_id": "e", "adopted_value_sha256": "0" * 64}]
    second = [{**first[0], "source_owner_user_id": "owner-b"}]
    payload = {"description": DESCRIPTION}
    assert profile_content_digest(payload, first) != profile_content_digest(payload, second)
    assert profile_content_digest(payload, first) == hashlib.sha256(json.dumps(
        {"payload": payload, "material_references": first}, ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def test_minimal_reference_output_never_contains_private_source_fields():
    from pilot.material_references import minimal_references

    rows = [{"field_name": "service", "reference_id": "ref", "valid": True,
             "material_id": "secret", "source_owner_user_id": "owner", "extraction_id": "extract"}]
    assert minimal_references(rows) == [{"field": "service", "referenceId": "ref", "valid": True}]


def _ready(env, *, owner=0, material_id=None):
    model = Model({"fields": {"service": "知识库实施"},
                   "evidence": [{"field": "service", "quote": "知识库实施"}]})
    materials = MaterialStore(env.db, model)
    source = env.profiles[owner]
    saved = mutate(materials, env, save_request(source, material_id=material_id or "m-" + uuid4().hex,
        text="我们提供知识库实施。"), owner=owner)["record"]
    parsed = mutate(materials, env, {"requestId": str(uuid4()), "profileVersionId": source,
        "change": {"kind": "parse", "materialId": saved["id"], "expectedVersion": 1}}, owner=owner)["record"]
    ready = mutate(materials, env, {"requestId": str(uuid4()), "profileVersionId": source,
        "change": {"kind": "confirm", "materialId": saved["id"], "expectedVersion": 2,
                   "extractionId": parsed["extraction"]["id"], "fields": {"service": "知识库实施"}}}, owner=owner)["record"]
    return materials, source, ready


def test_ready_reference_save_reopen_and_same_text_different_source_do_not_deduplicate(env):
    materials, source, ready = _ready(env)
    store = PilotStore(env.admin)
    raw = [{"field": "service", "sourceProfileVersionId": source, "materialId": ready["id"],
            "materialVersion": ready["version"], "extractionId": ready["extraction"]["id"]}]
    first = store.save_profile(env.users[0], {"description": DESCRIPTION}, material_references=raw)
    assert first["material_references"][0]["valid"] is True
    assert store.get_profile_version(env.users[0], first["version_id"])["material_references"] == first["material_references"]
    _, source2, ready2 = _ready(env, material_id="other-" + uuid4().hex)
    second = store.save_profile(env.users[0], {"description": DESCRIPTION}, material_references=[raw[0] | {
        "sourceProfileVersionId": source2, "materialId": ready2["id"], "materialVersion": ready2["version"],
        "extractionId": ready2["extraction"]["id"]}])
    assert second["version_id"] != first["version_id"]


def test_reference_inheritance_shares_only_minimal_metadata_and_rejects_changed_value(env):
    _, source, ready = _ready(env)
    store = PilotStore(env.admin)
    created = store.save_profile(env.users[0], {"description": DESCRIPTION}, material_references=[{
        "field": "service", "sourceProfileVersionId": source, "materialId": ready["id"],
        "materialVersion": ready["version"], "extractionId": ready["extraction"]["id"]}])
    inherited = store.save_profile(env.users[1], {"description": DESCRIPTION},
        base_profile_version_id=created["version_id"], material_references=[{
            "field": "service", "referenceId": created["material_references"][0]["referenceId"]}])
    assert set(inherited["material_references"][0]) == {"field", "referenceId", "valid"}
    changed = DESCRIPTION.replace('服务内容："知识库实施"', '服务内容："人工修改"')
    with pytest.raises(ValueError, match="reference"):
        store.save_profile(env.users[1], {"description": changed}, base_profile_version_id=created["version_id"],
            material_references=[{"field": "service", "referenceId": created["material_references"][0]["referenceId"]}])


def test_impact_binds_reference_snapshot_and_revoke_invalidates_qualification_not_profile_text(env):
    materials, source, ready = _ready(env)
    store = PilotStore(env.admin)
    target = store.save_profile(env.users[0], {"description": DESCRIPTION}, material_references=[{
        "field": "service", "sourceProfileVersionId": source, "materialId": ready["id"],
        "materialVersion": ready["version"], "extractionId": ready["extraction"]["id"]}])
    store.confirm_profile(env.users[0], target["version_id"])
    suggestions = SearchSuggestionStore(env.admin)
    assert suggestions.preview(env.claims[0], target["version_id"], provider="synthetic", model="synthetic")["description"] == DESCRIPTION
    impact = materials.impact(env.claims[0], source, ready["id"], ready["version"], "revoke")
    assert impact["references"] == [{"kind": "profile", "label": "业务画像 / 服务内容"}]
    result = mutate(materials, env, {"requestId": str(uuid4()), "profileVersionId": source,
        "change": {"kind": "revoke", "materialId": ready["id"], "expectedVersion": ready["version"],
                   "impactToken": impact["token"]}}, owner=0)
    assert result["status"] == "SUCCEEDED"
    reopened = store.get_profile_version(env.users[0], target["version_id"])
    assert reopened["payload"]["description"] == DESCRIPTION
    assert reopened["status"] == "CONFIRMED"
    assert reopened["material_references"][0]["valid"] is False
    with pytest.raises(SearchSuggestionStoreError, match="profile_unavailable"):
        suggestions.preview(env.claims[0], target["version_id"], provider="synthetic", model="synthetic")
    with pytest.raises(ValueError, match="reference"):
        store.confirm_profile(env.users[0], target["version_id"])
