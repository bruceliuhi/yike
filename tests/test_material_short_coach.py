"""Focused material-grounded short coach contract tests; synthetic text only."""
import asyncio
import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from pathlib import Path
from contextlib import contextmanager

from pilot.short_coach import CoachInput, ShortCoachError, ShortCoachService, build_suggestion
from tests.test_short_coach import coach_input
from tests.test_confirmed_strategy_review_postgres import (databases, env, execution_databases,
    execution_env, raw_databases, raw_env, real_strategy_env, real_review)


def material_reference(**changes):
    return {"sourceProfileVersionId": str(uuid4()), "materialId": "case-1", "materialVersion": 3,
        "extractionId": "extract-1", "quote": "制造业案例"} | changes


def material_input(references=None):
    value = coach_input(content="参考制造业案例，请问项目还在推进吗？")
    value["materialReferences"] = [material_reference()] if references is None else references
    value["binding"]["draftHash"] = hashlib.sha256(value["content"].encode()).hexdigest()
    return value


@pytest.fixture
def material_coach_env(real_strategy_env):
    yield real_strategy_env
    with real_strategy_env.admin.connect() as connection:
        for table in ("pilot_short_coach_requests", "pilot_short_coach_daily_quota"):
            connection.execute(f"DELETE FROM {table} WHERE tenant_id=ANY(%s)", (real_strategy_env.tenants,))
        connection.execute("ALTER TABLE pilot_material_revisions DISABLE TRIGGER pilot_material_revisions_immutable")
        connection.execute("ALTER TABLE pilot_material_operations DISABLE TRIGGER pilot_material_operations_immutable")
        for table in ("pilot_material_impact_tokens", "pilot_material_operations", "pilot_material_revisions"):
            connection.execute(f"DELETE FROM {table} WHERE tenant_id=ANY(%s)", (real_strategy_env.tenants,))
        connection.execute("ALTER TABLE pilot_material_revisions ENABLE TRIGGER pilot_material_revisions_immutable")
        connection.execute("ALTER TABLE pilot_material_operations ENABLE TRIGGER pilot_material_operations_immutable")


def test_optional_material_references_bind_hash_and_policy_without_changing_legacy():
    model = SimpleNamespace(provider="synthetic", model="coach-v1", available=True,
        material_reference_version="short-coach-material-draft-v1")
    service = ShortCoachService(None, model)
    legacy = coach_input()
    legacy_preview = service.preview_unverified(legacy)
    assert legacy_preview["policyVersion"] == "short-coach-public-draft-v1"
    explicit_empty = legacy | {"materialReferences": []}
    assert service.preview_unverified(explicit_empty)["inputHash"] != legacy_preview["inputHash"]
    empty_result = build_suggestion(explicit_empty, {"content": "您好，请问预算范围？",
        "question": "请问预算范围？", "quote": "预算可聊"})
    assert empty_result["materialReferences"] == []
    material = material_input()
    preview = service.preview_unverified(material)
    assert preview["policyVersion"] == "short-coach-material-draft-v1"
    assert preview["inputHash"] != legacy_preview["inputHash"]
    with pytest.raises(Exception): CoachInput.model_validate(material | {"materialReferences": None})
    with pytest.raises(Exception): CoachInput.model_validate(material | {"materialReferences": material["materialReferences"] * 2})


def test_material_capability_is_rejected_before_any_database_or_quota_access():
    service = ShortCoachService(None, SimpleNamespace(provider="synthetic", model="coach-v1", available=True))
    with pytest.raises(ShortCoachError, match="capability_unavailable"):
        service.preview_unverified(material_input())


def test_material_result_uses_only_selected_grounded_substrings_and_rebuilds_references():
    raw = material_input([material_reference(quote="制造业案例原文")])
    raw["content"] = "参考制造业案例原文，请问还在推进吗？"
    raw["binding"]["draftHash"] = hashlib.sha256(raw["content"].encode()).hexdigest()
    result = build_suggestion(raw, {"content": "基于制造业案例，请问还在推进吗？", "question": "请问还在推进吗？",
        "quote": "需求", "materialQuotes": [{"referenceIndex": 0, "quote": "制造业案例"}]})
    assert result["materialReferences"] == [raw["materialReferences"][0] | {"quote": "制造业案例"}]
    for invalid in (
        [{"referenceIndex": 1, "quote": "制造业案例"}],
        [{"referenceIndex": 0, "quote": "伪造"}],
        [{"referenceIndex": 0, "quote": "制造业案例"}, {"referenceIndex": 0, "quote": "制造业"}],
    ):
        with pytest.raises(ValueError):
            build_suggestion(raw, {"content": "基于制造业案例，请问还在推进吗？", "question": "请问还在推进吗？",
                "quote": "需求", "materialQuotes": invalid})


def test_real_adapter_sends_only_numbered_quotes_and_requires_strict_material_result():
    from pilot.candidate_assessment_model import OpenAICompatibleCandidateAssessmentModel
    from pilot.short_coach_model import ShortCoachModel, ShortCoachModelError
    seen = {}
    async def handler(request):
        seen.update(json.loads(request.content)["messages"][1])
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"role": "assistant",
            "content": json.dumps({"content": "基于制造业案例，请问推进吗？", "question": "请问推进吗？", "quote": "需求",
                "materialQuotes": [{"referenceIndex": 0, "quote": "制造业案例"}]}),
            "refusal": None, "tool_calls": None, "function_call": None}}]})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    config = OpenAICompatibleCandidateAssessmentModel(base_url="http://localhost:9999", api_key="synthetic", model="coach-v1")
    model = ShortCoachModel(config, http_client=client)
    assert model.generate(sourceText="需求", content="草稿", channel="dm", purpose="materials",
        materialQuotes=[{"referenceIndex": 0, "quote": "制造业案例"}])["materialQuotes"][0]["referenceIndex"] == 0
    assert set(json.loads(seen["content"])) == {"sourceText", "content", "channel", "purpose", "materialQuotes"}
    asyncio.run(client.aclose())


def test_restricted_pg_material_generate_replay_revoke_and_mid_call_failure(material_coach_env):
    from pilot.materials import MaterialStore
    from tests.test_materials_store import Model, save_request
    from tests.test_opportunity_evidence_postgres import include
    from tests.test_pilot_runtime import _route_service
    from tests.test_execution_runtime_postgres import SECRET
    from pilot.auth import issue_token, verify_token_claims
    from pilot.runtime import build_runtime_app
    env = material_coach_env; root = Path(__file__).parents[1]
    with env.admin.connect() as connection:
        connection.execute(f"REVOKE ALL ON pilot_material_revisions FROM {env.db.role}")
        connection.execute("SELECT set_config('yike.app_role',%s,true)", (env.db.role,))
        connection.execute((root / "deploy/grant_short_coach.sql").read_text())
    with env.db.connect() as connection:
        assert connection.execute("SELECT has_table_privilege(current_user,'pilot_material_revisions','SELECT'),has_table_privilege(current_user,'pilot_material_revisions','INSERT')").fetchone() == (True, False)
    _, candidate, _, _, _, _, opportunity = include(env, service=real_review(env))
    evidence = env.store.get_opportunity(env.claims.user_id, opportunity)["source_evidence"]["snapshot"]

    def ready_material(material_id):
        materials = MaterialStore(env.admin, Model({"fields": {"service": "制造业案例"},
            "evidence": [{"field": "service", "quote": "制造业案例"}]}))
        saved = materials.mutate(env.claims, save_request(env.profile, material_id=material_id,
            text="制造业案例原文", expected=None) | {"change": save_request(env.profile,
                material_id=material_id, text="制造业案例原文")["change"] | {"input": {
                    "name": "案例", "text": "制造业案例原文", "purpose": "真实案例", "visibility": "external"}}})["record"]
        parsed = materials.mutate(env.claims, {"requestId": str(uuid4()), "profileVersionId": env.profile,
            "change": {"kind": "parse", "materialId": material_id, "expectedVersion": 1}})["record"]
        ready = materials.mutate(env.claims, {"requestId": str(uuid4()), "profileVersionId": env.profile,
            "change": {"kind": "confirm", "materialId": material_id, "expectedVersion": 2,
                "extractionId": parsed["extraction"]["id"], "fields": {"service": "制造业案例"}}})["record"]
        return materials, ready

    def request_for(ready):
        raw = material_input([{**material_reference(), "sourceProfileVersionId": env.profile,
            "materialId": ready["id"], "materialVersion": ready["version"],
            "extractionId": ready["extraction"]["id"], "quote": "制造业案例"}])
        raw["sourceText"] = evidence["source"]["body"]
        raw["binding"].update(accountScope={"id": env.tenant, "version": 1}, opportunityId=opportunity,
            profileVersionId=env.profile, sourceEvidenceVersion=candidate["sourceVersionId"],
            sourceUrl=evidence["source"]["public_url"], sourceObservedAt=evidence["observation"]["observed_at"])
        return raw

    class GroundedModel:
        available=True; provider="synthetic"; model="coach-v1"; material_reference_version="short-coach-material-draft-v1"
        calls=0
        def generate(self, **kwargs):
            self.calls += 1
            assert kwargs["materialQuotes"] == [{"referenceIndex": 0, "quote": "制造业案例"}]
            return {"content": "基于制造业案例，请问还在推进吗？", "question": "请问还在推进吗？",
                "quote": kwargs["sourceText"][:2], "materialQuotes": [{"referenceIndex": 0, "quote": "制造业案例"}]}

    materials, ready = ready_material("coach-case-" + uuid4().hex)
    raw = request_for(ready)
    app = build_runtime_app(env.db, auth_secret=SECRET, environment={})
    service = _route_service(app, "/api/ui/short-coach/preview", ShortCoachService)
    service.model = GroundedModel()
    token = issue_token(env.claims.user_id, SECRET)
    client_claims = verify_token_claims(token, SECRET)
    client = TestClient(app, base_url="https://pilot.example.invalid",
        headers={"Authorization": "Bearer " + token})
    preview = client.post("/api/ui/short-coach/preview", json=raw)
    assert preview.status_code == 200, preview.text
    disclosure = {"accepted": True, **preview.json()}
    generated = client.post("/api/ui/short-coach/generate", json=raw | {"disclosure": disclosure})
    assert generated.status_code == 200, generated.text
    first = generated.json()
    assert first["materialReferences"][0]["quote"] == "制造业案例"
    assert client.post("/api/ui/short-coach/generate", json=raw | {"disclosure": disclosure}).json() == first and service.model.calls == 1
    impact = materials.impact(env.claims, env.profile, ready["id"], ready["version"], "revoke")
    assert materials.mutate(env.claims, {"requestId": str(uuid4()), "profileVersionId": env.profile,
        "change": {"kind": "revoke", "materialId": ready["id"], "expectedVersion": ready["version"],
            "impactToken": impact["token"]}})["status"] == "SUCCEEDED"
    rejected = client.post("/api/ui/short-coach/preview", json=raw | {"binding": raw["binding"] | {"requestId": str(uuid4())}})
    assert rejected.status_code == 409 and rejected.json()["detail"]["code"] == "short_coach_material_unavailable"

    materials2, ready2 = ready_material("coach-case-" + uuid4().hex)
    second = request_for(ready2); entered, release = Event(), Event()
    class PausedModel(GroundedModel):
        def generate(self, **kwargs):
            entered.set(); assert release.wait(3); return super().generate(**kwargs)
    service.model = PausedModel()
    preview2 = client.post("/api/ui/short-coach/preview", json=second)
    disclosure2 = {"accepted": True, **preview2.json()}
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(client.post, "/api/ui/short-coach/generate", json=second | {"disclosure": disclosure2})
        assert entered.wait(2)
        impact = materials2.impact(env.claims, env.profile, ready2["id"], ready2["version"], "revoke")
        materials2.mutate(env.claims, {"requestId": str(uuid4()), "profileVersionId": env.profile,
            "change": {"kind": "revoke", "materialId": ready2["id"], "expectedVersion": ready2["version"],
                "impactToken": impact["token"]}})
        release.set()
        failed = running.result(timeout=4)
        assert failed.status_code == 409 and failed.json()["detail"]["code"] == "short_coach_material_unavailable"
    with env.admin.connect() as connection:
        assert connection.execute("SELECT state,error_code FROM pilot_short_coach_requests WHERE request_id=%s",
            (second["binding"]["requestId"],)).fetchone() == ("FAILED", "short_coach_failed")

    materials4, ready4 = ready_material("coach-case-" + uuid4().hex)
    fourth = request_for(ready4); tracking = {"facts_cursor": None, "published": False}
    class TrackingCursor:
        def __init__(self, inner): self.inner = inner
        def __enter__(self): self.inner.__enter__(); return self
        def __exit__(self, *args): return self.inner.__exit__(*args)
        def execute(self, query, params=None):
            if query.startswith("UPDATE pilot_short_coach_requests SET state=%s"):
                assert self is tracking["facts_cursor"]
                tracking["published"] = True
            self.inner.execute(query, params); return self
        def fetchone(self): return self.inner.fetchone()
    class TrackingConnection:
        def __init__(self, inner): self.inner = inner
        def __enter__(self): self.inner.__enter__(); return self
        def __exit__(self, *args): return self.inner.__exit__(*args)
        def cursor(self): return TrackingCursor(self.inner.cursor())
    class TrackingDatabase:
        @contextmanager
        def connect(self):
            with env.db.connect() as connection:
                yield TrackingConnection(connection)
    tracked = ShortCoachService(TrackingDatabase(), GroundedModel())
    original_facts = tracked._facts
    def tracked_facts(cursor, claims, value):
        result = original_facts(cursor, claims, value)
        tracking["facts_cursor"] = cursor
        return result
    tracked._facts = tracked_facts
    disclosure4 = {"accepted": True, **tracked.preview(env.claims, fourth)}
    tracked.generate(env.claims, fourth | {"disclosure": disclosure4})
    assert tracking["published"] is True

    materials3, ready3 = ready_material("coach-case-" + uuid4().hex)
    third = request_for(ready3); entered3, release3 = Event(), Event()
    class LogoutPausedModel(GroundedModel):
        def generate(self, **kwargs):
            entered3.set(); assert release3.wait(3); return super().generate(**kwargs)
    service.model = LogoutPausedModel()
    preview3 = client.post("/api/ui/short-coach/preview", json=third)
    disclosure3 = {"accepted": True, **preview3.json()}
    from pilot.sessions import PilotSessionRegistry
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(client.post, "/api/ui/short-coach/generate", json=third | {"disclosure": disclosure3})
        assert entered3.wait(2)
        PilotSessionRegistry(env.db).revoke([client_claims])
        release3.set()
        failed = running.result(timeout=4)
        assert failed.status_code == 401
    with env.admin.connect() as connection:
        assert connection.execute("SELECT state,result,error_code FROM pilot_short_coach_requests WHERE request_id=%s",
            (third["binding"]["requestId"],)).fetchone() == ("FAILED", None, "short_coach_failed")
