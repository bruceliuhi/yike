import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tests.test_confirmed_strategy_review_postgres import (
    databases, env, execution_databases, execution_env, raw_databases, raw_env,
    real_strategy_env,
)


def coach_input(source="需求😀预算可聊", content="您好，请问预算范围？"):
    draft_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return {
        "binding": {
            "accountScope": {"id": str(uuid4()), "version": 1},
            "requestId": str(uuid4()), "opportunityId": str(uuid4()),
            "profileVersionId": str(uuid4()), "sourceEvidenceVersion": str(uuid4()),
            "sourceUrl": "https://example.invalid/post/1",
            "sourceObservedAt": "2026-09-11T01:02:03.456Z", "channel": "comment",
            "draftVersion": 1, "draftHash": draft_hash, "purpose": "requirement",
        }, "content": content, "sourceText": source,
    }


def test_preview_hash_is_exact_javascript_json_array_and_never_calls_model():
    from pilot.short_coach import ShortCoachService
    raw = coach_input()
    model = SimpleNamespace(provider="openai-compatible", model="coach-v1", available=True,
                            generate=lambda **_: pytest.fail("preview called model"))
    service = ShortCoachService(None, model=model)
    expected = hashlib.sha256(json.dumps([
        raw["binding"]["accountScope"]["id"], 1, raw["binding"]["requestId"],
        raw["binding"]["opportunityId"], raw["binding"]["profileVersionId"],
        raw["binding"]["sourceEvidenceVersion"], raw["binding"]["sourceUrl"],
        raw["binding"]["sourceObservedAt"], "comment", 1, raw["binding"]["draftHash"],
        "requirement", raw["content"], raw["sourceText"],
    ], ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    assert service.preview_unverified(raw) == {"inputHash": expected,
        "modelProvider": "openai-compatible", "modelName": "coach-v1",
        "policyVersion": "short-coach-public-draft-v1"}


@pytest.mark.parametrize("change", ["draftHash", "sourceText", "nul"])
def test_input_rejects_changed_hash_or_invalid_unicode(change):
    from pilot.short_coach import CoachInput
    raw = coach_input()
    if change == "draftHash": raw["binding"]["draftHash"] = "0" * 64
    elif change == "sourceText": raw["sourceText"] = ""
    else: raw["content"] = "bad\0text"
    with pytest.raises(ValueError):
        CoachInput.model_validate(raw)


def test_suggestion_uses_utf16_offsets_and_rejects_two_questions_or_fake_quote():
    from pilot.short_coach import build_suggestion
    raw = coach_input()
    suggestion = build_suggestion(raw, {"content": "您好，请问预算范围？",
        "question": "请问预算范围？", "quote": "预算可聊"})
    quote = suggestion["quotes"][0]
    assert (quote["start"], quote["end"]) == (4, 8)
    with pytest.raises(ValueError):
        build_suggestion(raw, {"content": "预算多少？时间呢？", "question": "预算多少？", "quote": "预算可聊"})
    with pytest.raises(ValueError):
        build_suggestion(raw, {"content": "您好，请问预算范围？", "question": "请问预算范围？", "quote": "不存在"})


def test_restricted_postgres_real_inclusion_generate_replay_and_owner(real_strategy_env):
    from pathlib import Path
    from pilot.short_coach import ShortCoachService, ShortCoachError
    from tests.test_confirmed_strategy_review_postgres import real_review
    from tests.test_opportunity_evidence_postgres import include
    env = real_strategy_env
    root = Path(__file__).parents[1]
    with env.db.connect() as conn:
        role = conn.execute("SELECT current_user").fetchone()[0]
    with env.admin.connect() as conn:
        conn.execute((root / "migrations/130_v02_short_coach.sql").read_text())
        conn.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
        conn.execute((root / "deploy/grant_short_coach.sql").read_text())
    try:
        _, candidate, _, _, _, _, opportunity_id = include(env, service=real_review(env))
        evidence = env.store.get_opportunity(env.claims.user_id, opportunity_id)["source_evidence"]["snapshot"]
        class Model:
            provider, model, available, calls = "synthetic", "coach-v1", True, 0
            def generate(self, **kwargs):
                self.calls += 1
                return {"content":"您好，请问具体需求？","question":"请问具体需求？","quote":kwargs["sourceText"][:2]}
        model=Model(); service=ShortCoachService(env.db,model)
        raw=coach_input(source=evidence["source"]["body"],content="")
        raw["binding"].update(accountScope={"id":env.tenant,"version":1},opportunityId=opportunity_id,
            profileVersionId=env.profile,sourceEvidenceVersion=candidate["sourceVersionId"],
            sourceUrl=evidence["source"]["public_url"],sourceObservedAt=evidence["observation"]["observed_at"],
            draftHash=hashlib.sha256(b"").hexdigest())
        preview=service.preview(env.claims,raw)
        disclosure={"accepted":True,**preview}
        first=service.generate(env.claims,raw|{"disclosure":disclosure})
        assert service.generate(env.claims,raw|{"disclosure":disclosure})==first and model.calls==1
        from pilot.auth import issue_token, verify_token_claims
        from tests.test_execution_runtime_postgres import SECRET
        colleague=verify_token_claims(issue_token(env.users[2],SECRET),SECRET)
        with pytest.raises(ShortCoachError):
            service.generate(colleague,raw|{"disclosure":disclosure})
    finally:
        with env.admin.connect() as conn:
            conn.execute("DELETE FROM pilot_short_coach_requests WHERE tenant_id=ANY(%s)",(env.tenants,))
