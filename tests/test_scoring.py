import json

import httpx
import pytest
from pydantic import ValidationError

from app.db import connect, migrate
from app.model_client import OpenAICompatibleModelClient
from app.model_contract import ScoreDecision
from app.repository import NormalizedSignal, Repository
from app.scorer import Scorer
from tests.support import collect_verified_signal


def valid_decision() -> dict[str, object]:
    return {
        "grade": "A",
        "score": 10,
        "confidence": 0.88,
        "explicit_industry": "B2B 销售",
        "business_context": "团队正在筛选销售线索",
        "pain_summary": "人工筛选效率低",
        "intent_summary": "询问是否有可落地的工具",
        "evidence_snippets": ["团队正在筛选销售线索", "人工筛选效率低"],
        "dimension_scores": {
            "business_team_context": 2,
            "offer_fit": 2,
            "action_intent": 3,
            "buying_signal": 1,
            "contact_context": 1,
            "evidence_completeness": 1,
        },
        "exclusion_reasons": [],
        "recommended_question": "你们目前每周需要筛选多少条线索？",
    }


def test_score_decision_accepts_strict_valid_contract():
    source = "销售获客讨论\n父评论\n团队正在筛选销售线索，人工筛选效率低"

    decision = ScoreDecision.model_validate(valid_decision(), context={"source_text": source})

    assert decision.score == 10
    assert decision.grade == "A"


def test_score_decision_rejects_evidence_absent_from_source():
    payload = valid_decision()
    payload["evidence_snippets"] = ["已批准十万元预算"]

    with pytest.raises(ValidationError, match="evidence"):
        ScoreDecision.model_validate(payload, context={"source_text": "原文没有预算信息"})


def test_score_decision_rejects_dimension_sum_different_from_total():
    payload = valid_decision()
    payload["score"] = 9

    with pytest.raises(ValidationError, match="sum"):
        ScoreDecision.model_validate(
            payload,
            context={"source_text": "团队正在筛选销售线索，人工筛选效率低"},
        )


def test_missing_model_config_appends_failed_score_without_grade(tmp_path):
    connection = connect(tmp_path / "facts.sqlite3")
    migrate(connection)
    repository = Repository(connection)
    run_id = repository.create_run(["bili", "dy"])
    imported = repository.import_signal(
        run_id,
        NormalizedSignal(
            platform="bili",
            external_source_id="av1",
            source_title="销售获客讨论",
            source_url="https://www.bilibili.com/video/av1",
            source_author_public_id="source-author",
            external_comment_id="comment-1",
            comment_url="https://www.bilibili.com/video/av1#reply1",
            author_public_id="comment-author",
            body="团队正在筛选销售线索",
        ),
    )

    result = Scorer(repository, client=None).score(run_id, imported.signal_id)
    row = connection.execute(
        "SELECT * FROM score_runs WHERE score_run_id = ?", (result.score_run_id,)
    ).fetchone()

    assert result.status == "FAILED"
    assert result.error_code == "MODEL_NOT_CONFIGURED"
    assert row["status"] == "FAILED"
    assert row["error_code"] == "MODEL_NOT_CONFIGURED"
    assert row["total_score"] is None
    assert row["grade"] is None
    assert row["dimension_scores_json"] is None
    assert row["reason_json"] is None
    assert row["token_usage_json"] is None


class StubClient:
    provider = "openai-compatible"
    model = "test-model"

    def __init__(self, outcome):
        self.outcome = outcome

    def complete(self, *, source_text):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome, {"total_tokens": 12}


def scoring_facts(tmp_path):
    connection = connect(tmp_path / "scoring.sqlite3")
    migrate(connection)
    repository = Repository(connection)
    run_id = repository.create_run(["bili", "dy"])
    signal_id = collect_verified_signal(
        repository,
        run_id,
        NormalizedSignal(
            platform="bili",
            external_source_id="av1",
            source_title="销售获客讨论",
            source_url="https://www.bilibili.com/video/av1",
            source_author_public_id="source-author",
            external_comment_id="comment-1",
            parent_body="父评论",
            comment_url="https://www.bilibili.com/video/av1#reply1",
            author_public_id="comment-author",
            body="团队正在筛选销售线索，人工筛选效率低",
        ),
    )
    return connection, repository, run_id, signal_id


def test_scorer_persists_valid_success_contract(tmp_path):
    connection, repository, run_id, signal_id = scoring_facts(tmp_path)

    result = Scorer(repository, StubClient(valid_decision())).score(run_id, signal_id)
    row = connection.execute(
        "SELECT * FROM score_runs WHERE score_run_id = ?", (result.score_run_id,)
    ).fetchone()

    assert result.status == "SUCCEEDED"
    assert result.error_code is None
    assert (row["provider"], row["model"], row["total_score"], row["grade"]) == (
        "openai-compatible",
        "test-model",
        10,
        "A",
    )
    assert json.loads(row["dimension_scores_json"])["action_intent"] == 3
    assert json.loads(row["token_usage_json"])["total_tokens"] == 12


def test_invalid_model_payload_fails_closed_without_grade(tmp_path):
    connection, repository, run_id, signal_id = scoring_facts(tmp_path)
    invalid = valid_decision() | {"invented_field": True}

    result = Scorer(repository, StubClient(invalid)).score(run_id, signal_id)
    row = connection.execute(
        "SELECT * FROM score_runs WHERE score_run_id = ?", (result.score_run_id,)
    ).fetchone()

    assert (result.status, result.error_code) == ("FAILED", "MODEL_OUTPUT_INVALID")
    assert row["total_score"] is None
    assert row["grade"] is None


def test_model_transport_failure_is_unavailable_without_fallback(tmp_path):
    connection, repository, run_id, signal_id = scoring_facts(tmp_path)
    request = httpx.Request("POST", "https://model.invalid/chat/completions")
    client = StubClient(httpx.ReadTimeout("timeout", request=request))

    result = Scorer(repository, client).score(run_id, signal_id)
    row = connection.execute(
        "SELECT total_score, grade FROM score_runs WHERE score_run_id = ?",
        (result.score_run_id,),
    ).fetchone()

    assert (result.status, result.error_code) == ("FAILED", "MODEL_UNAVAILABLE")
    assert tuple(row) == (None, None)


def test_openai_compatible_client_posts_strict_schema_and_parses_json():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(valid_decision())}}],
                "usage": {"total_tokens": 9},
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenAICompatibleModelClient(
        base_url="https://models.example/v1",
        api_key="test-secret",
        model="strict-model",
        http_client=http_client,
    )

    payload, usage = client.complete(source_text="source")

    assert captured["url"] == "https://models.example/v1/chat/completions"
    assert captured["authorization"] == "Bearer test-secret"
    assert captured["body"]["response_format"]["json_schema"]["strict"] is True
    assert captured["body"]["model"] == "strict-model"
    assert payload == valid_decision()
    assert usage == {"total_tokens": 9}


def test_openai_compatible_client_rejects_non_json_content():
    http_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"choices": [{"message": {"content": "not-json"}}]}
            )
        )
    )
    client = OpenAICompatibleModelClient(
        base_url="https://models.example/v1",
        api_key="test-secret",
        model="strict-model",
        http_client=http_client,
    )

    with pytest.raises(json.JSONDecodeError):
        client.complete(source_text="source")


def test_model_client_secret_is_excluded_from_repr_and_comparison():
    first = OpenAICompatibleModelClient(
        base_url="https://models.example/v1",
        api_key="first-secret",
        model="strict-model",
    )
    second = OpenAICompatibleModelClient(
        base_url="https://models.example/v1",
        api_key="second-secret",
        model="strict-model",
    )

    assert "first-secret" not in repr(first)
    assert first == second
