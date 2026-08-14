from datetime import UTC, datetime, timedelta
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
import socket
import sqlite3
from threading import Barrier

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import connect, migrate
from app.drafter import DraftGenerator
from app.model_client import OpenAICompatibleModelClient
from app.model_contract import DraftDecision, ScoreDecision
from app.repository import NormalizedSignal, Repository
from app.scorer import Scorer
from app.web import create_app
from app.workflow import Workflow, WorkflowConflictError
from tests.test_metrics_contract import FactBuilder
from tests.test_scoring import StubClient, valid_decision
from tests.test_web import facts as web_facts
from tests.test_web import settings_for


class Clock:
    def __init__(self, value: datetime):
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class DraftFailureClient:
    provider = "openai-compatible"
    model = "draft-model"

    def __init__(self, error: Exception):
        self.error = error

    def generate_draft(self, *, source_text: str):
        raise self.error


def unverified_facts(tmp_path):
    connection = connect(tmp_path / "unverified.sqlite3")
    migrate(connection)
    clock = Clock(datetime(2026, 8, 12, 8, tzinfo=UTC))
    repository = Repository(connection, now=clock)
    run_id = repository.create_run(["bili", "dy"])
    signal_id = repository.import_signal(
        run_id,
        NormalizedSignal(
            platform="bili",
            external_source_id="unverified-source",
            source_title="销售获客讨论",
            source_url="https://www.bilibili.com/video/av100",
            external_comment_id="unverified-comment",
            parent_body="团队想改善获客",
            comment_url="https://www.bilibili.com/video/av100#reply100",
            author_public_id="unverified-lead",
            body="团队正在筛选销售线索，人工筛选效率低",
        ),
    ).signal_id
    return connection, repository, clock, run_id, signal_id


def verified_facts(tmp_path):
    facts = FactBuilder(tmp_path / "verified.sqlite3")
    signal_id = facts.collect_signals([1])[0]
    return facts, signal_id


def valid_score_storage() -> tuple[dict[str, object], dict[str, object]]:
    decision = deepcopy(valid_decision())
    dimensions = decision.pop("dimension_scores")
    return dimensions, decision


def insert_score_fact(
    connection,
    *,
    run_id: str,
    signal_id: str,
    score_run_id: str,
    dimensions_json: str,
    total_score: object,
    grade: object,
    confidence: object,
    reason_json: str,
    created_at: str = "2026-08-12T00:00:02Z",
) -> None:
    connection.execute(
        """
        INSERT INTO score_runs (
            score_run_id, mvp_run_id, signal_id, provider, model,
            prompt_version, schema_version, dimension_scores_json,
            total_score, grade, confidence, reason_json, status, created_at
        ) VALUES (?, ?, ?, 'provider', 'model', 'prompt-v2', 'schema-v2',
                  ?, ?, ?, ?, ?, 'SUCCEEDED', ?)
        """,
        (
            score_run_id,
            run_id,
            signal_id,
            dimensions_json,
            total_score,
            grade,
            confidence,
            reason_json,
            created_at,
        ),
    )


def insert_generated_draft_fact(
    connection,
    *,
    run_id: str,
    signal_id: str,
    draft_run_id: str,
    body: str,
    contract_json: str,
    created_at: str = "2026-08-12T00:00:02Z",
) -> None:
    connection.execute(
        """
        INSERT INTO draft_runs (
            draft_run_id, mvp_run_id, signal_id, provider, model,
            prompt_version, draft_kind, body, status, contract_json, created_at
        ) VALUES (?, ?, ?, 'provider', 'model', 'draft-v2',
                  'GENERATED', ?, 'SUCCEEDED', ?, ?)
        """,
        (draft_run_id, run_id, signal_id, body, contract_json, created_at),
    )


D04_FACT_TABLES = (
    "score_runs",
    "score_presentations",
    "activity_sessions",
    "activity_events",
    "human_reviews",
    "draft_runs",
    "outreach_actions",
    "response_events",
    "interviews",
    "quote_opportunities",
)


def insert_minimal_d04_fact(
    connection, *, table: str, run_id: str, signal_id: str, timestamp: str
) -> None:
    prefix = f"matrix-{table}"
    statements: dict[str, tuple[str, tuple[object, ...]]] = {
        "score_runs": (
            """
            INSERT INTO score_runs (
                score_run_id, mvp_run_id, signal_id, prompt_version,
                schema_version, status, error_code, created_at
            ) VALUES (?, ?, ?, 'prompt-v2', 'schema-v2',
                      'FAILED', 'MODEL_UNAVAILABLE', ?)
            """,
            (prefix, run_id, signal_id, timestamp),
        ),
        "score_presentations": (
            """
            INSERT INTO score_presentations (
                presentation_id, mvp_run_id, signal_id, score_run_id, presented_at
            ) VALUES (?, ?, ?, 'missing-score', ?)
            """,
            (prefix, run_id, signal_id, timestamp),
        ),
        "activity_sessions": (
            """
            INSERT INTO activity_sessions (
                activity_session_id, mvp_run_id, signal_id,
                activity_kind, state, started_at
            ) VALUES (?, ?, ?, 'REVIEW', 'OPEN', ?)
            """,
            (prefix, run_id, signal_id, timestamp),
        ),
        "activity_events": (
            """
            INSERT INTO activity_events (
                activity_event_id, activity_session_id, mvp_run_id,
                signal_id, activity_kind, sequence_no, event_kind, received_at
            ) VALUES (?, 'missing-session', ?, ?, 'REVIEW', 1, 'START', ?)
            """,
            (prefix, run_id, signal_id, timestamp),
        ),
        "human_reviews": (
            """
            INSERT INTO human_reviews (
                review_id, mvp_run_id, signal_id, presented_score_run_id,
                label, reason, activity_session_id, started_at,
                completed_at, active_seconds
            ) VALUES (?, ?, ?, 'missing-score', 'POSSIBLE', '人工核验',
                      'missing-session', ?, ?, 0)
            """,
            (prefix, run_id, signal_id, timestamp, timestamp),
        ),
        "draft_runs": (
            """
            INSERT INTO draft_runs (
                draft_run_id, mvp_run_id, signal_id, prompt_version,
                draft_kind, status, error_code, created_at
            ) VALUES (?, ?, ?, 'draft-v2', 'GENERATED',
                      'FAILED', 'MODEL_UNAVAILABLE', ?)
            """,
            (prefix, run_id, signal_id, timestamp),
        ),
        "outreach_actions": (
            """
            INSERT INTO outreach_actions (
                outreach_action_id, mvp_run_id, signal_id, review_id,
                score_run_id, draft_run_id, platform, subject_key,
                approved_text, sent_at, source_url, context_evidence,
                evidence_summary, source_link_opened, status, created_at
            ) VALUES (?, ?, ?, 'missing-review', 'missing-score', 'missing-draft',
                      'bili', 'bili:unverified-lead', '人工筛选效率低', ?,
                      'https://www.bilibili.com/video/av100#reply100',
                      '人工筛选效率低', '人工筛选效率低', 1,
                      'SENT_VERIFIED', ?)
            """,
            (prefix, run_id, signal_id, timestamp, timestamp),
        ),
        "response_events": (
            """
            INSERT INTO response_events (
                response_event_id, mvp_run_id, outreach_action_id,
                responder_subject_key, response_type, summary,
                occurred_at, verified_at, evidence_summary, recorded_at
            ) VALUES (?, ?, 'missing-outreach', 'bili:unverified-lead',
                      'VALID', '愿意继续沟通', ?, ?, '每周 200 条', ?)
            """,
            (prefix, run_id, timestamp, timestamp, timestamp),
        ),
        "interviews": (
            """
            INSERT INTO interviews (
                interview_id, mvp_run_id, response_event_id,
                solution_fit, recorded_at
            ) VALUES (?, ?, 'missing-response', 'UNKNOWN', ?)
            """,
            (prefix, run_id, timestamp),
        ),
        "quote_opportunities": (
            """
            INSERT INTO quote_opportunities (
                quote_opportunity_id, mvp_run_id, response_event_id,
                scope_summary, agreed_to_receive_pricing_at,
                verified_at, recorded_at
            ) VALUES (?, ?, 'missing-response', '线索排序试点', ?, ?, ?)
            """,
            (prefix, run_id, timestamp, timestamp, timestamp),
        ),
    }
    sql, params = statements[table]
    connection.execute(sql, params)


def unverifiable_decision() -> ScoreDecision:
    payload = valid_decision() | {
        "grade": "D",
        "exclusion_reasons": ["SOURCE_UNVERIFIABLE"],
    }
    return ScoreDecision.model_validate(
        payload,
        context={
            "source_text": "销售获客讨论\n团队想改善获客\n团队正在筛选销售线索，人工筛选效率低",
        },
    )


def prepare_unverified_review_and_draft(tmp_path):
    connection, repository, clock, run_id, signal_id = unverified_facts(tmp_path)
    decision = unverifiable_decision()
    repository.append_score_success(
        score_run_id="unverified-score",
        run_id=run_id,
        signal_id=signal_id,
        provider="test-provider",
        model="test-model",
        prompt_version="DISCOVERY_SCORE_V2",
        schema_version="DISCOVERY_SCORE_SCHEMA_V2",
        decision=decision,
        token_usage=None,
    )
    workflow = Workflow(repository, now=clock)
    workflow.present_score(run_id, signal_id, "unverified-score")
    review_session = workflow.start_activity(run_id, signal_id, "REVIEW")
    workflow.record_activity(review_session, "COMPLETE")
    review_id = workflow.complete_review(
        run_id=run_id,
        signal_id=signal_id,
        label="UNVERIFIABLE",
        reason="来源不可核验",
        note=None,
        activity_session_id=review_session,
    )
    draft_session = workflow.start_activity(run_id, signal_id, "DRAFT")
    workflow.record_activity(draft_session, "COMPLETE")
    draft_id = workflow.create_draft(
        run_id=run_id,
        signal_id=signal_id,
        body="人工筛选效率低。我们正在研究销售 Agent，你们每周筛选多少条线索？",
        activity_session_id=draft_session,
    )
    return connection, repository, workflow, clock, run_id, signal_id, review_id, draft_id


def ready_for_outreach(facts: FactBuilder, signal_id: str):
    review_id = facts.review(signal_id, 1)
    draft_session = facts.workflow.start_activity(facts.run_id, signal_id, "DRAFT")
    facts.clock.move(1)
    facts.workflow.record_activity(draft_session, "COMPLETE")
    approved = "你提到人工筛选效率低。我们正在研究销售 Agent，你们每周筛选多少条线索？"
    draft_id = facts.workflow.create_draft(
        run_id=facts.run_id,
        signal_id=signal_id,
        body=approved,
        activity_session_id=draft_session,
    )
    return review_id, draft_id, approved


def test_score_request_binds_offer_rubric_and_canonical_source_envelope(tmp_path):
    facts, signal_id = verified_facts(tmp_path)
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(valid_decision())}}]},
        )

    client = OpenAICompatibleModelClient(
        base_url="https://models.example/v1",
        api_key="must-not-appear",
        model="strict-model",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = Scorer(facts.repository, client).score(facts.run_id, signal_id)

    assert result.status == "SUCCEEDED"
    request = captured["request"]
    system = request["messages"][0]["content"]
    user = request["messages"][1]["content"]
    for required in (
        "意客AI",
        "中小企业",
        "business_team_context 0-2",
        "offer_fit 0-3",
        "action_intent 0-3",
        "buying_signal 0-2",
        "contact_context 0-1",
        "evidence_completeness 0-1",
        "A: 9-12",
        "B: 7-8",
        "C: 4-6",
        "D: 0-3",
        "business_team_context > 0",
        "offer_fit >= 2",
        "STUDENT_JOB_SEEKING_OR_HOBBY",
        "PEER_PROMOTION",
        "IRRELEVANT",
        "GENERIC_PRAISE",
        "ILLEGAL_AUTOMATION_REQUEST",
        "SOURCE_UNVERIFIABLE",
        "人工发送",
    ):
        assert required in system
    for required in (
        '"platform":"bili"',
        '"external_source_id":"source-bili-1"',
        '"external_comment_id":"comment-bili-1"',
        '"verifiable":true',
        '"source_url":"https://www.bilibili.com/video/source-1"',
        '"comment_url":"https://www.bilibili.com/video/source-1#reply-1"',
        '"title":"销售获客讨论"',
        '"parent_body":null',
        '"comment_body":"团队正在筛选销售线索，人工筛选效率低"',
        "团队正在筛选销售线索，人工筛选效率低",
    ):
        assert required in user
    assert "must-not-appear" not in json.dumps(request, ensure_ascii=False)
    row = facts.connection.execute(
        "SELECT prompt_version, schema_version FROM score_runs WHERE score_run_id = ?",
        (result.score_run_id,),
    ).fetchone()
    assert tuple(row) == ("DISCOVERY_SCORE_V2", "DISCOVERY_SCORE_SCHEMA_V2")
    facts.close()


def test_unverifiable_signal_cannot_become_a_high_grade(tmp_path):
    connection, repository, _, run_id, signal_id = unverified_facts(tmp_path)

    result = Scorer(repository, StubClient(valid_decision())).score(run_id, signal_id)

    assert (result.status, result.error_code) == ("FAILED", "MODEL_OUTPUT_INVALID")
    row = connection.execute(
        "SELECT grade, total_score FROM score_runs WHERE score_run_id = ?",
        (result.score_run_id,),
    ).fetchone()
    assert tuple(row) == (None, None)
    connection.close()


def test_unverifiable_signal_cannot_register_sent_outreach_via_workflow(tmp_path):
    (
        connection,
        _,
        workflow,
        _,
        run_id,
        signal_id,
        review_id,
        draft_id,
    ) = prepare_unverified_review_and_draft(tmp_path)

    with pytest.raises(ValueError, match="verifiable"):
        workflow.register_outreach(
            run_id=run_id,
            signal_id=signal_id,
            review_id=review_id,
            draft_run_id=draft_id,
            platform="bili",
            subject_key="bili:unverified-lead",
            approved_text="人工筛选效率低。请问你们每周筛选多少条线索？",
            context_evidence="人工筛选效率低",
            sent_at="2026-08-12T08:00:00Z",
            source_url="https://www.bilibili.com/video/av100#reply100",
            source_link_opened=True,
        )
    assert connection.execute("SELECT count(*) FROM outreach_actions").fetchone()[0] == 0
    connection.close()


def test_unverifiable_signal_cannot_register_sent_outreach_via_sql(tmp_path):
    (
        connection,
        _,
        _,
        _,
        run_id,
        signal_id,
        review_id,
        draft_id,
    ) = prepare_unverified_review_and_draft(tmp_path)

    with pytest.raises(sqlite3.IntegrityError, match="OUTREACH_SIGNAL_NOT_VERIFIABLE"):
        connection.execute(
            """
            INSERT INTO outreach_actions (
                outreach_action_id, mvp_run_id, signal_id, review_id, score_run_id,
                draft_run_id, platform, subject_key, approved_text, sent_at,
                source_url, context_evidence, evidence_summary,
                source_link_opened, status, created_at
            ) VALUES (
                'sql-unverified', ?, ?, ?, 'unverified-score', ?, 'bili',
                'bili:unverified-lead', '人工筛选效率低。请问每周多少条？',
                '2026-08-12T08:00:00Z',
                'https://www.bilibili.com/video/av100#reply100',
                '人工筛选效率低', '人工筛选效率低', 1,
                'SENT_VERIFIED', '2026-08-12T08:00:00Z'
            )
            """,
            (run_id, signal_id, review_id, draft_id),
        )
    connection.close()


def test_sql_rejects_semantically_invalid_succeeded_score(tmp_path):
    facts, signal_id = verified_facts(tmp_path)

    with pytest.raises(sqlite3.IntegrityError, match="SCORE_SEMANTICS_INVALID"):
        facts.connection.execute(
            """
            INSERT INTO score_runs (
                score_run_id, mvp_run_id, signal_id, provider, model,
                prompt_version, schema_version, dimension_scores_json,
                total_score, grade, confidence, reason_json, status, created_at
            ) VALUES (
                'forged-a', ?, ?, 'provider', 'model', 'prompt-v2', 'schema-v2',
                '{}', 12, 'A', 0.9, '{}', 'SUCCEEDED', '2026-08-12T00:00:02Z'
            )
            """,
            (facts.run_id, signal_id),
        )
    assert facts.connection.execute(
        "SELECT count(*) FROM score_runs WHERE score_run_id = 'forged-a'"
    ).fetchone()[0] == 0
    facts.close()


@pytest.mark.parametrize(
    "case",
    (
        "missing_dimension",
        "extra_dimension",
        "bool_dimension",
        "fraction_dimension",
        "out_of_range_dimension",
        "wrong_sum",
        "wrong_grade",
        "high_grade_with_exclusion",
        "mismatched_columns",
        "false_evidence",
        "missing_decision_key",
        "extra_decision_key",
        "duplicate_dimension_key",
        "duplicate_decision_key",
    ),
)
def test_sql_rejects_every_malformed_succeeded_score_without_downstream_fact(
    tmp_path, case
):
    facts, signal_id = verified_facts(tmp_path)
    dimensions, reason = valid_score_storage()
    total_score: object = reason["score"]
    grade: object = reason["grade"]
    confidence: object = reason["confidence"]
    dimensions_json: str | None = None
    reason_json: str | None = None

    if case == "missing_dimension":
        dimensions.pop("offer_fit")
    elif case == "extra_dimension":
        dimensions["unexpected"] = 1
    elif case == "bool_dimension":
        dimensions["offer_fit"] = True
    elif case == "fraction_dimension":
        dimensions["offer_fit"] = 2.5
    elif case == "out_of_range_dimension":
        dimensions["offer_fit"] = 4
    elif case == "wrong_sum":
        reason["score"] = total_score = 9
    elif case == "wrong_grade":
        reason["grade"] = grade = "B"
    elif case == "high_grade_with_exclusion":
        reason["exclusion_reasons"] = ["PEER_PROMOTION"]
    elif case == "mismatched_columns":
        total_score = 9
    elif case == "false_evidence":
        reason["evidence_snippets"] = ["原文不存在的十万元预算"]
    elif case == "missing_decision_key":
        reason.pop("business_context")
    elif case == "extra_decision_key":
        reason["unexpected"] = "forged"
    elif case == "duplicate_dimension_key":
        dimensions_json = (
            '{"business_team_context":2,"offer_fit":2,"offer_fit":2,'
            '"action_intent":3,"buying_signal":1,"contact_context":1,'
            '"evidence_completeness":1}'
        )
    elif case == "duplicate_decision_key":
        clean = json.dumps(reason, ensure_ascii=False, separators=(",", ":"))
        reason_json = clean[:-1] + ',"grade":"A"}'

    dimensions_json = dimensions_json or json.dumps(
        dimensions, ensure_ascii=False, separators=(",", ":")
    )
    reason_json = reason_json or json.dumps(
        reason, ensure_ascii=False, separators=(",", ":")
    )
    with pytest.raises(sqlite3.IntegrityError, match="SCORE_SEMANTICS_INVALID"):
        insert_score_fact(
            facts.connection,
            run_id=facts.run_id,
            signal_id=signal_id,
            score_run_id=f"malformed-{case}",
            dimensions_json=dimensions_json,
            total_score=total_score,
            grade=grade,
            confidence=confidence,
            reason_json=reason_json,
        )

    assert facts.connection.execute(
        "SELECT count(*) FROM score_runs WHERE score_run_id = ?",
        (f"malformed-{case}",),
    ).fetchone()[0] == 0
    assert facts.connection.execute(
        "SELECT count(*) FROM score_presentations WHERE score_run_id = ?",
        (f"malformed-{case}",),
    ).fetchone()[0] == 0
    facts.close()


def test_sql_rejects_high_grade_for_unverifiable_signal(tmp_path):
    connection, _, _, run_id, signal_id = unverified_facts(tmp_path)
    dimensions, reason = valid_score_storage()

    with pytest.raises(sqlite3.IntegrityError, match="SCORE_SEMANTICS_INVALID"):
        insert_score_fact(
            connection,
            run_id=run_id,
            signal_id=signal_id,
            score_run_id="unverifiable-forged-a",
            dimensions_json=json.dumps(dimensions, ensure_ascii=False),
            total_score=reason["score"],
            grade=reason["grade"],
            confidence=reason["confidence"],
            reason_json=json.dumps(reason, ensure_ascii=False),
            created_at="2026-08-12T08:00:00Z",
        )
    assert connection.execute(
        "SELECT count(*) FROM score_runs WHERE score_run_id = 'unverifiable-forged-a'"
    ).fetchone()[0] == 0
    connection.close()


def test_sql_rejects_semantically_invalid_generated_draft(tmp_path):
    facts, signal_id = verified_facts(tmp_path)

    with pytest.raises(sqlite3.IntegrityError, match="DRAFT_SEMANTICS_INVALID"):
        facts.connection.execute(
            """
            INSERT INTO draft_runs (
                draft_run_id, mvp_run_id, signal_id, provider, model,
                prompt_version, draft_kind, body, status, contract_json, created_at
            ) VALUES (
                'forged-draft', ?, ?, 'provider', 'model', 'draft-v2',
                'GENERATED', '不受约束的正文', 'SUCCEEDED', '{}',
                '2026-08-12T00:00:02Z'
            )
            """,
            (facts.run_id, signal_id),
        )
    facts.close()


@pytest.mark.parametrize(
    "case",
    (
        "empty_contract",
        "extra_contract_key",
        "body_mismatch",
        "false_source_snippet",
        "missing_research_purpose",
        "marker_only_research_purpose",
        "filler_only_research_purpose",
        "missing_question",
        "punctuation_only_question",
        "filler_only_question",
        "two_questions",
        "duplicate_contract_key",
    ),
)
def test_sql_rejects_every_malformed_generated_draft(tmp_path, case):
    facts, signal_id = verified_facts(tmp_path)
    body = "人工筛选效率低。我们正在研究销售 Agent。你们每周筛选多少条线索？"
    contract: dict[str, object] = {
        "body": body,
        "source_snippet": "人工筛选效率低",
        "research_purpose_sentence": "我们正在研究销售 Agent。",
        "diagnostic_question": "你们每周筛选多少条线索？",
    }
    contract_json: str | None = None
    stored_body = body

    if case == "empty_contract":
        contract = {}
    elif case == "extra_contract_key":
        contract["unexpected"] = "forged"
    elif case == "body_mismatch":
        stored_body = "与合同不同的草稿"
    elif case == "false_source_snippet":
        contract["source_snippet"] = "原文没有的预算"
    elif case == "missing_research_purpose":
        body = stored_body = "人工筛选效率低。我们提供销售 Agent。你们每周筛选多少条线索？"
        contract["body"] = body
        contract["research_purpose_sentence"] = "我们提供销售 Agent。"
    elif case == "marker_only_research_purpose":
        body = stored_body = "人工筛选效率低。研究。你们每周筛选多少条线索？"
        contract["body"] = body
        contract["research_purpose_sentence"] = "研究"
    elif case == "filler_only_research_purpose":
        body = stored_body = "人工筛选效率低。研究\u3164\u3164。你们每周筛选多少条线索？"
        contract["body"] = body
        contract["research_purpose_sentence"] = "研究\u3164\u3164"
    elif case == "missing_question":
        body = stored_body = "人工筛选效率低。我们正在研究销售 Agent。请介绍每周线索量。"
        contract["body"] = body
        contract["diagnostic_question"] = "请介绍每周线索量。"
    elif case == "punctuation_only_question":
        body = stored_body = "人工筛选效率低。我们正在研究销售 Agent。？"
        contract["body"] = body
        contract["diagnostic_question"] = "？"
    elif case == "filler_only_question":
        body = stored_body = "人工筛选效率低。我们正在研究销售 Agent。\u3164\u3164？"
        contract["body"] = body
        contract["diagnostic_question"] = "\u3164\u3164？"
    elif case == "two_questions":
        body = stored_body = (
            "人工筛选效率低。我们正在研究销售 Agent。"
            "你们每周筛选多少条线索？哪个环节最慢？"
        )
        contract["body"] = body
    elif case == "duplicate_contract_key":
        clean = json.dumps(contract, ensure_ascii=False, separators=(",", ":"))
        contract_json = clean[:-1] + f',"body":{json.dumps(body, ensure_ascii=False)}}}'

    contract_json = contract_json or json.dumps(
        contract, ensure_ascii=False, separators=(",", ":")
    )
    with pytest.raises(sqlite3.IntegrityError, match="DRAFT_SEMANTICS_INVALID"):
        insert_generated_draft_fact(
            facts.connection,
            run_id=facts.run_id,
            signal_id=signal_id,
            draft_run_id=f"malformed-draft-{case}",
            body=stored_body,
            contract_json=contract_json,
        )
    assert facts.connection.execute(
        "SELECT count(*) FROM draft_runs WHERE draft_run_id = ?",
        (f"malformed-draft-{case}",),
    ).fetchone()[0] == 0
    facts.close()


@pytest.mark.parametrize(
    "contract",
    (
        {
            "body": "人工筛选效率低。研究。你们每周筛选多少条线索？",
            "source_snippet": "人工筛选效率低",
            "research_purpose_sentence": "研究",
            "diagnostic_question": "你们每周筛选多少条线索？",
        },
        {
            "body": "人工筛选效率低。我们正在研究销售 Agent。？",
            "source_snippet": "人工筛选效率低",
            "research_purpose_sentence": "我们正在研究销售 Agent。",
            "diagnostic_question": "？",
        },
        {
            "body": "人工筛选效率低。研究\u3164\u3164。\u3164\u3164？",
            "source_snippet": "人工筛选效率低",
            "research_purpose_sentence": "研究\u3164\u3164",
            "diagnostic_question": "\u3164\u3164？",
        },
    ),
)
def test_draft_decision_rejects_marker_only_semantics(contract):
    with pytest.raises(ValueError):
        DraftDecision.model_validate(
            contract,
            context={"source_text": "人工筛选效率低"},
        )


def test_generated_draft_cannot_predate_signal_run_membership(tmp_path):
    facts = FactBuilder(tmp_path / "draft-membership-time.sqlite3")
    facts.clock.move(2)
    signal_id = facts.collect_signals([1])[0]
    added_at = facts.connection.execute(
        "SELECT added_at FROM mvp_run_signals WHERE mvp_run_id = ? AND signal_id = ?",
        (facts.run_id, signal_id),
    ).fetchone()[0]
    before_membership = (
        datetime.fromisoformat(str(added_at).replace("Z", "+00:00"))
        - timedelta(seconds=1)
    ).isoformat().replace("+00:00", "Z")
    body = "人工筛选效率低。我们正在研究销售 Agent。你们每周筛选多少条线索？"
    contract = {
        "body": body,
        "source_snippet": "人工筛选效率低",
        "research_purpose_sentence": "我们正在研究销售 Agent。",
        "diagnostic_question": "你们每周筛选多少条线索？",
    }

    with pytest.raises(sqlite3.IntegrityError, match="DRAFT_TIME_CAUSALITY"):
        insert_generated_draft_fact(
            facts.connection,
            run_id=facts.run_id,
            signal_id=signal_id,
            draft_run_id="draft-before-membership",
            body=body,
            contract_json=json.dumps(contract, ensure_ascii=False),
            created_at=before_membership,
        )
    assert facts.connection.execute(
        "SELECT count(*) FROM draft_runs WHERE draft_run_id = 'draft-before-membership'"
    ).fetchone()[0] == 0
    facts.close()


def test_activity_before_signal_membership_cannot_authorize_human_draft(tmp_path):
    facts = FactBuilder(tmp_path / "activity-membership-time.sqlite3")
    facts.clock.move(2)
    signal_id = facts.collect_signals([1])[0]
    added_at = str(facts.connection.execute(
        "SELECT added_at FROM mvp_run_signals WHERE mvp_run_id = ? AND signal_id = ?",
        (facts.run_id, signal_id),
    ).fetchone()[0])
    before_membership = (
        datetime.fromisoformat(added_at.replace("Z", "+00:00"))
        - timedelta(seconds=1)
    ).isoformat().replace("+00:00", "Z")

    with pytest.raises(sqlite3.IntegrityError, match="ACTIVITY_SIGNAL_TIME_CAUSALITY"):
        with facts.connection:
            facts.connection.execute(
                """
                INSERT INTO activity_sessions (
                    activity_session_id, mvp_run_id, signal_id,
                    activity_kind, state, started_at
                ) VALUES ('early-draft-session', ?, ?, 'DRAFT', 'OPEN', ?)
                """,
                (facts.run_id, signal_id, before_membership),
            )
            facts.connection.execute(
                """
                INSERT INTO activity_events (
                    activity_event_id, activity_session_id, mvp_run_id,
                    signal_id, activity_kind, sequence_no, event_kind, received_at
                ) VALUES ('early-draft-start', 'early-draft-session', ?, ?,
                          'DRAFT', 1, 'START', ?)
                """,
                (facts.run_id, signal_id, before_membership),
            )
            facts.connection.execute(
                """
                INSERT INTO activity_events (
                    activity_event_id, activity_session_id, mvp_run_id,
                    signal_id, activity_kind, sequence_no, event_kind, received_at
                ) VALUES ('early-draft-complete', 'early-draft-session', ?, ?,
                          'DRAFT', 2, 'COMPLETE', ?)
                """,
                (facts.run_id, signal_id, before_membership),
            )
            facts.connection.execute(
                """
                UPDATE activity_sessions
                SET state = 'COMPLETED', completed_at = ?, active_seconds = 0
                WHERE activity_session_id = 'early-draft-session'
                """,
                (before_membership,),
            )
            facts.connection.execute(
                """
                INSERT INTO draft_runs (
                    draft_run_id, mvp_run_id, signal_id, provider, model,
                    prompt_version, draft_kind, body, status,
                    activity_session_id, created_at
                ) VALUES ('draft-from-early-activity', ?, ?, 'human', NULL,
                          'HUMAN_DRAFT_V1', 'HUMAN_EDITED', '人工筛选效率低',
                          'SUCCEEDED', 'early-draft-session', ?)
                """,
                (facts.run_id, signal_id, added_at),
            )
    assert facts.connection.execute(
        "SELECT count(*) FROM activity_sessions WHERE activity_session_id = 'early-draft-session'"
    ).fetchone()[0] == 0
    assert facts.connection.execute(
        "SELECT count(*) FROM draft_runs WHERE draft_run_id = 'draft-from-early-activity'"
    ).fetchone()[0] == 0
    facts.close()


def test_sql_rejects_d04_fact_after_run_is_cancelled(tmp_path):
    connection, repository, _, run_id, signal_id = unverified_facts(tmp_path)
    repository.cancel_run(run_id)

    with pytest.raises(sqlite3.IntegrityError, match="D04_FACT_REQUIRES_ACTIVE_RUN"):
        connection.execute(
            """
            INSERT INTO score_runs (
                score_run_id, mvp_run_id, signal_id, prompt_version,
                schema_version, status, error_code, created_at
            ) VALUES (
                'cancelled-score', ?, ?, 'prompt-v2', 'schema-v2',
                'FAILED', 'MODEL_UNAVAILABLE', '2026-08-12T08:00:00Z'
            )
            """,
            (run_id, signal_id),
        )
    connection.close()


def test_sql_rejects_d04_fact_timestamp_after_day14(tmp_path):
    connection, _, _, run_id, signal_id = unverified_facts(tmp_path)

    with pytest.raises(sqlite3.IntegrityError, match="D04_FACT_OUTSIDE_RUN_WINDOW"):
        connection.execute(
            """
            INSERT INTO score_runs (
                score_run_id, mvp_run_id, signal_id, prompt_version,
                schema_version, status, error_code, created_at
            ) VALUES (
                'late-score', ?, ?, 'prompt-v2', 'schema-v2',
                'FAILED', 'MODEL_UNAVAILABLE', '2026-09-01T00:00:00Z'
            )
            """,
            (run_id, signal_id),
        )
    connection.close()


def test_sql_rejects_backdated_d04_fact_when_server_is_past_day14(tmp_path):
    connection = connect(tmp_path / "expired-backdated.sqlite3")
    migrate(connection)
    past = (datetime.now(UTC) - timedelta(days=30)).replace(microsecond=0)
    clock = Clock(past)
    repository = Repository(connection, now=clock)
    run_id = repository.create_run(["bili", "dy"])
    signal_id = repository.import_signal(
        run_id,
        NormalizedSignal(
            platform="bili",
            external_source_id="expired-source",
            source_title="销售获客讨论",
            source_url="https://www.bilibili.com/video/av-expired",
            external_comment_id="expired-comment",
            comment_url="https://www.bilibili.com/video/av-expired#reply-expired",
            author_public_id="expired-lead",
            body="人工筛选效率低",
        ),
    ).signal_id
    backdated = past.isoformat().replace("+00:00", "Z")

    with pytest.raises(sqlite3.IntegrityError, match="D04_FACT_OUTSIDE_RUN_WINDOW"):
        connection.execute(
            """
            INSERT INTO score_runs (
                score_run_id, mvp_run_id, signal_id, prompt_version,
                schema_version, status, error_code, created_at
            ) VALUES ('expired-backdated-score', ?, ?, 'prompt-v2', 'schema-v2',
                      'FAILED', 'MODEL_UNAVAILABLE', ?)
            """,
            (run_id, signal_id, backdated),
        )
    assert connection.execute(
        "SELECT count(*) FROM score_runs WHERE score_run_id = 'expired-backdated-score'"
    ).fetchone()[0] == 0
    connection.close()


@pytest.mark.parametrize("table", D04_FACT_TABLES)
@pytest.mark.parametrize("run_condition", ("DRAFT", "CANCELLED", "POST_DAY14"))
def test_every_d04_fact_table_fails_closed_outside_active_run_window(
    tmp_path, table, run_condition
):
    connection, repository, _, active_run_id, signal_id = unverified_facts(tmp_path)
    timestamp = "2026-08-12T08:00:00Z"
    if run_condition == "DRAFT":
        run_id = "matrix-draft-run"
        with connection:
            connection.execute(
                """
                INSERT INTO mvp_runs (
                    mvp_run_id, state, timezone, authorization_basis,
                    platform_scope_json, query_set_sha256, prompt_version,
                    schema_version, thresholds_sha256, started_at, day14_due_at
                )
                SELECT ?, 'DRAFT', timezone, authorization_basis,
                       platform_scope_json, query_set_sha256, prompt_version,
                       schema_version, thresholds_sha256, started_at, day14_due_at
                FROM mvp_runs WHERE mvp_run_id = ?
                """,
                (run_id, active_run_id),
            )
            connection.execute(
                "INSERT INTO mvp_run_signals (mvp_run_id, signal_id, added_at) "
                "VALUES (?, ?, ?)",
                (run_id, signal_id, timestamp),
            )
    elif run_condition == "CANCELLED":
        run_id = active_run_id
        repository.cancel_run(run_id)
    else:
        run_id = active_run_id
        timestamp = "2026-09-01T00:00:00Z"

    before = connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        insert_minimal_d04_fact(
            connection,
            table=table,
            run_id=run_id,
            signal_id=signal_id,
            timestamp=timestamp,
        )
    connection.rollback()
    after = connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    assert after == before
    connection.close()


@pytest.mark.parametrize(
    "presented_at", ("2026-08-12 00:00:00", "2026-08-12T00:00:00Z")
)
def test_presentation_requires_canonical_time_after_score(tmp_path, presented_at):
    facts, signal_id = verified_facts(tmp_path)
    facts.repository.append_score_success(
        score_run_id="valid-score",
        run_id=facts.run_id,
        signal_id=signal_id,
        provider="provider",
        model="model",
        prompt_version="prompt-v2",
        schema_version="schema-v2",
        decision=facts.decision,
        token_usage=None,
    )

    with pytest.raises(sqlite3.IntegrityError, match="PRESENTATION_TIME_CAUSALITY"):
        facts.connection.execute(
            """
            INSERT INTO score_presentations (
                presentation_id, mvp_run_id, signal_id, score_run_id, presented_at
            ) VALUES ('bad-time', ?, ?, 'valid-score', ?)
            """,
            (facts.run_id, signal_id, presented_at),
        )
    facts.close()


def test_score_cannot_be_backdated_before_signal_membership(tmp_path):
    facts = FactBuilder(tmp_path / "backdated-score.sqlite3")
    facts.clock.move(2)
    signal_id = facts.collect_signals([1])[0]
    dimensions, reason = valid_score_storage()

    with pytest.raises(sqlite3.IntegrityError, match="SCORE_SIGNAL_TIME_CAUSALITY"):
        insert_score_fact(
            facts.connection,
            run_id=facts.run_id,
            signal_id=signal_id,
            score_run_id="backdated-score",
            dimensions_json=json.dumps(dimensions, ensure_ascii=False),
            total_score=reason["score"],
            grade=reason["grade"],
            confidence=reason["confidence"],
            reason_json=json.dumps(reason, ensure_ascii=False),
            created_at="2026-08-12T00:00:01Z",
        )
    facts.close()


def test_review_reason_is_required_at_sql_boundary(tmp_path):
    facts, signal_id = verified_facts(tmp_path)
    facts.repository.append_score_success(
        score_run_id="review-score",
        run_id=facts.run_id,
        signal_id=signal_id,
        provider="provider",
        model="model",
        prompt_version="prompt-v2",
        schema_version="schema-v2",
        decision=facts.decision,
        token_usage=None,
    )
    facts.workflow.present_score(facts.run_id, signal_id, "review-score")
    session_id = facts.workflow.start_activity(facts.run_id, signal_id, "REVIEW")
    facts.clock.move(1)
    facts.workflow.record_activity(session_id, "COMPLETE")
    session = facts.connection.execute(
        "SELECT * FROM activity_sessions WHERE activity_session_id = ?", (session_id,)
    ).fetchone()

    with pytest.raises(sqlite3.IntegrityError):
        facts.connection.execute(
            """
            INSERT INTO human_reviews (
                review_id, mvp_run_id, signal_id, presented_score_run_id,
                label, reason, activity_session_id, started_at,
                completed_at, active_seconds
            ) VALUES (
                'reasonless', ?, ?, 'review-score', 'HIGH_INTENT', NULL,
                ?, ?, ?, ?
            )
            """,
            (
                facts.run_id,
                signal_id,
                session_id,
                session["started_at"],
                session["completed_at"],
                session["active_seconds"],
            ),
        )
    facts.close()


def test_review_revision_must_start_after_current_parent_completed(tmp_path):
    facts, signal_id = verified_facts(tmp_path)
    facts.repository.append_score_success(
        score_run_id="revision-score",
        run_id=facts.run_id,
        signal_id=signal_id,
        provider="provider",
        model="model",
        prompt_version="prompt-v2",
        schema_version="schema-v2",
        decision=facts.decision,
        token_usage=None,
    )
    facts.workflow.present_score(facts.run_id, signal_id, "revision-score")

    early_session = facts.workflow.start_activity(facts.run_id, signal_id, "REVIEW")
    facts.clock.move(1)
    facts.workflow.record_activity(early_session, "COMPLETE")
    early = facts.connection.execute(
        "SELECT * FROM activity_sessions WHERE activity_session_id = ?",
        (early_session,),
    ).fetchone()

    facts.clock.move(1)
    parent_session = facts.workflow.start_activity(facts.run_id, signal_id, "REVIEW")
    facts.clock.move(1)
    facts.workflow.record_activity(parent_session, "COMPLETE")
    parent_review = facts.workflow.complete_review(
        run_id=facts.run_id,
        signal_id=signal_id,
        label="HIGH_INTENT",
        reason="当前人工核验",
        note=None,
        activity_session_id=parent_session,
    )

    with pytest.raises(sqlite3.IntegrityError, match="REVIEW_REVISION_TIME_CAUSALITY"):
        facts.connection.execute(
            """
            INSERT INTO human_reviews (
                review_id, mvp_run_id, signal_id, presented_score_run_id,
                label, reason, activity_session_id, started_at,
                completed_at, active_seconds, supersedes_review_id
            ) VALUES (
                'backdated-revision', ?, ?, 'revision-score', 'POSSIBLE',
                '倒签修订', ?, ?, ?, ?, ?
            )
            """,
            (
                facts.run_id,
                signal_id,
                early_session,
                early["started_at"],
                early["completed_at"],
                early["active_seconds"],
                parent_review,
            ),
        )
    assert facts.connection.execute(
        "SELECT count(*) FROM human_reviews WHERE review_id = 'backdated-revision'"
    ).fetchone()[0] == 0
    facts.close()


def test_root_review_must_start_after_first_presentation(tmp_path):
    facts, signal_id = verified_facts(tmp_path)
    facts.repository.append_score_success(
        score_run_id="late-presentation-score",
        run_id=facts.run_id,
        signal_id=signal_id,
        provider="provider",
        model="model",
        prompt_version="prompt-v2",
        schema_version="schema-v2",
        decision=facts.decision,
        token_usage=None,
    )
    early_session = facts.workflow.start_activity(facts.run_id, signal_id, "REVIEW")
    facts.clock.move(1)
    facts.workflow.record_activity(early_session, "COMPLETE")
    early = facts.connection.execute(
        "SELECT * FROM activity_sessions WHERE activity_session_id = ?",
        (early_session,),
    ).fetchone()
    facts.clock.move(1)
    facts.workflow.present_score(facts.run_id, signal_id, "late-presentation-score")

    with pytest.raises(sqlite3.IntegrityError, match="REVIEW_PRESENTATION_TIME_CAUSALITY"):
        facts.connection.execute(
            """
            INSERT INTO human_reviews (
                review_id, mvp_run_id, signal_id, presented_score_run_id,
                label, reason, activity_session_id, started_at,
                completed_at, active_seconds
            ) VALUES (
                'review-before-presentation', ?, ?, 'late-presentation-score',
                'POSSIBLE', '时间倒签', ?, ?, ?, ?
            )
            """,
            (
                facts.run_id,
                signal_id,
                early_session,
                early["started_at"],
                early["completed_at"],
                early["active_seconds"],
            ),
        )
    facts.close()


def test_human_draft_cannot_be_backdated_before_completed_activity(tmp_path):
    facts, signal_id = verified_facts(tmp_path)
    session_id = facts.workflow.start_activity(facts.run_id, signal_id, "DRAFT")
    started_at = facts.connection.execute(
        "SELECT started_at FROM activity_sessions WHERE activity_session_id = ?",
        (session_id,),
    ).fetchone()[0]
    facts.clock.move(1)
    facts.workflow.record_activity(session_id, "COMPLETE")

    with pytest.raises(sqlite3.IntegrityError, match="DRAFT_TIME_CAUSALITY"):
        facts.connection.execute(
            """
            INSERT INTO draft_runs (
                draft_run_id, mvp_run_id, signal_id, provider, model,
                prompt_version, draft_kind, body, status,
                activity_session_id, created_at
            ) VALUES (
                'backdated-human-draft', ?, ?, 'human', NULL, 'HUMAN_DRAFT_V1',
                'HUMAN_EDITED', '人工筛选效率低', 'SUCCEEDED', ?, ?
            )
            """,
            (facts.run_id, signal_id, session_id, started_at),
        )
    facts.close()


def test_outreach_source_url_must_match_signal_comment_url(tmp_path):
    facts, signal_id = verified_facts(tmp_path)
    review_id = facts.review(signal_id, 1)
    draft_session = facts.workflow.start_activity(facts.run_id, signal_id, "DRAFT")
    facts.clock.move(1)
    facts.workflow.record_activity(draft_session, "COMPLETE")
    approved = "你提到人工筛选效率低。我们正在研究销售 Agent，你们每周筛选多少条线索？"
    draft_id = facts.workflow.create_draft(
        run_id=facts.run_id,
        signal_id=signal_id,
        body=approved,
        activity_session_id=draft_session,
    )

    with pytest.raises(ValueError, match="source URL"):
        facts.workflow.register_outreach(
            run_id=facts.run_id,
            signal_id=signal_id,
            review_id=review_id,
            draft_run_id=draft_id,
            platform="bili",
            subject_key="bili:lead-bili-1",
            approved_text=approved,
            context_evidence="人工筛选效率低",
            sent_at=facts.clock().isoformat().replace("+00:00", "Z"),
            source_url="https://unrelated.example/not-the-signal",
            source_link_opened=True,
        )
    facts.close()


def test_future_business_facts_are_rejected_before_insert(tmp_path):
    facts, signal_id = verified_facts(tmp_path)
    review_id = facts.review(signal_id, 1)
    draft_session = facts.workflow.start_activity(facts.run_id, signal_id, "DRAFT")
    facts.clock.move(1)
    facts.workflow.record_activity(draft_session, "COMPLETE")
    approved = "你提到人工筛选效率低。我们正在研究销售 Agent，你们每周筛选多少条线索？"
    draft_id = facts.workflow.create_draft(
        run_id=facts.run_id,
        signal_id=signal_id,
        body=approved,
        activity_session_id=draft_session,
    )
    future = (facts.clock() + timedelta(days=1)).isoformat().replace("+00:00", "Z")

    with pytest.raises(ValueError, match="future"):
        facts.workflow.register_outreach(
            run_id=facts.run_id,
            signal_id=signal_id,
            review_id=review_id,
            draft_run_id=draft_id,
            platform="bili",
            subject_key="bili:lead-bili-1",
            approved_text=approved,
            context_evidence="人工筛选效率低",
            sent_at=future,
            source_url="https://www.bilibili.com/video/source-1#reply-1",
            source_link_opened=True,
        )
    assert (
        facts.connection.execute("SELECT count(*) FROM outreach_actions").fetchone()[0]
        == 0
    )
    facts.close()


@pytest.mark.parametrize("fact_kind", ("response", "interview", "quote"))
def test_future_response_interview_and_quote_are_rejected_by_workflow(
    tmp_path, fact_kind
):
    facts, signal_id = verified_facts(tmp_path)
    review_id, _, _ = ready_for_outreach(facts, signal_id)
    outreach_id = facts.outreach(signal_id, review_id, 1)
    now = facts.clock().isoformat().replace("+00:00", "Z")
    future = (facts.clock() + timedelta(days=1)).isoformat().replace("+00:00", "Z")

    if fact_kind == "response":
        with pytest.raises(ValueError, match="future"):
            facts.workflow.register_response(
                run_id=facts.run_id,
                outreach_action_id=outreach_id,
                responder_subject_key="bili:lead-bili-1",
                response_type="VALID",
                summary="愿意继续沟通",
                occurred_at=future,
                verified_at=future,
                evidence_summary="每周 200 条",
            )
        table = "response_events"
    else:
        response_id = facts.workflow.register_response(
            run_id=facts.run_id,
            outreach_action_id=outreach_id,
            responder_subject_key="bili:lead-bili-1",
            response_type="VALID",
            summary="愿意继续沟通",
            occurred_at=now,
            verified_at=now,
            evidence_summary="每周 200 条",
        )
        if fact_kind == "interview":
            with pytest.raises(ValueError, match="future"):
                facts.workflow.register_interview(
                    run_id=facts.run_id,
                    response_event_id=response_id,
                    scheduled_at=future,
                    completed_at=future,
                    summary={
                        "customer_source_and_sales_process": "内容营销进入销售",
                        "weekly_lead_volume_and_loss_point": "每周 200 条",
                        "most_manual_step": "人工判断意图",
                        "current_tools": "CRM 和表格",
                        "minimum_agent_scenario_and_decision_process": "先试线索排序",
                    },
                    solution_fit="SOLVABLE",
                    next_step="试点",
                )
            table = "interviews"
        else:
            interview_id = facts.interview(response_id)
            with pytest.raises(ValueError, match="future"):
                facts.workflow.register_quote(
                    run_id=facts.run_id,
                    response_event_id=response_id,
                    interview_id=interview_id,
                    scope_summary="线索排序试点",
                    agreed_to_receive_pricing_at=future,
                    verified_at=future,
                )
            table = "quote_opportunities"

    assert facts.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    facts.close()


@pytest.mark.parametrize(
    ("fact_kind", "expected"),
    (
        ("response", "RESPONSE_TIME_OR_RUN_INVALID"),
        ("interview", "INTERVIEW_TIME_OR_RUN_INVALID"),
        ("quote", "QUOTE_TIME_OR_RUN_INVALID"),
    ),
)
def test_future_business_facts_are_rejected_at_sql_boundary(
    tmp_path, fact_kind, expected
):
    facts, signal_id = verified_facts(tmp_path)
    review_id = facts.review(signal_id, 1)
    outreach_id = facts.outreach(signal_id, review_id, 1)
    now = facts.clock().isoformat().replace("+00:00", "Z")
    future = (facts.clock() + timedelta(days=1)).isoformat().replace("+00:00", "Z")

    with pytest.raises(sqlite3.IntegrityError, match=expected):
        if fact_kind == "response":
            facts.connection.execute(
                """
                INSERT INTO response_events (
                    response_event_id, mvp_run_id, outreach_action_id,
                    responder_subject_key, response_type, summary, occurred_at,
                    verified_at, evidence_summary, recorded_at
                ) VALUES ('future-response', ?, ?, 'bili:lead-bili-1',
                          'VALID', '愿意继续沟通', ?, ?, '每周 200 条', ?)
                """,
                (facts.run_id, outreach_id, future, future, now),
            )
        else:
            response_id = facts.response(outreach_id, 1)
            if fact_kind == "interview":
                facts.connection.execute(
                    """
                    INSERT INTO interviews (
                        interview_id, mvp_run_id, response_event_id,
                        scheduled_at, completed_at, summary_json,
                        solution_fit, next_step, recorded_at
                    ) VALUES ('future-interview', ?, ?, ?, ?, ?,
                              'SOLVABLE', '试点', ?)
                    """,
                    (
                        facts.run_id,
                        response_id,
                        future,
                        future,
                        json.dumps({
                            "customer_source_and_sales_process": "内容营销进入销售",
                            "weekly_lead_volume_and_loss_point": "每周 200 条",
                            "most_manual_step": "人工判断意图",
                            "current_tools": "CRM 和表格",
                            "minimum_agent_scenario_and_decision_process": "先试线索排序",
                        }, ensure_ascii=False),
                        now,
                    ),
                )
            else:
                interview_id = facts.interview(response_id)
                facts.connection.execute(
                    """
                    INSERT INTO quote_opportunities (
                        quote_opportunity_id, mvp_run_id, response_event_id,
                        interview_id, scope_summary, agreed_to_receive_pricing_at,
                        verified_at, recorded_at
                    ) VALUES ('future-quote', ?, ?, ?, '线索排序试点', ?, ?, ?)
                    """,
                    (facts.run_id, response_id, interview_id, future, future, now),
                )
    facts.connection.rollback()
    facts.close()


def test_sql_requires_closed_outreach_status_and_exact_source_url(tmp_path):
    facts, signal_id = verified_facts(tmp_path)
    review_id, draft_id, approved = ready_for_outreach(facts, signal_id)
    score_id = facts.connection.execute(
        "SELECT presented_score_run_id FROM human_reviews WHERE review_id = ?",
        (review_id,),
    ).fetchone()[0]
    now = facts.clock().isoformat().replace("+00:00", "Z")

    for outreach_id, status, source_url, expected in (
        ("bad-status", "RECORDED", "https://www.bilibili.com/video/source-1#reply-1", "OUTREACH_STATUS_INVALID"),
        ("bad-source", "SENT_VERIFIED", "https://unrelated.example/evil", "OUTREACH_SOURCE_URL_MISMATCH"),
    ):
        with pytest.raises(sqlite3.IntegrityError, match=expected):
            facts.connection.execute(
                """
                INSERT INTO outreach_actions (
                    outreach_action_id, mvp_run_id, signal_id, review_id,
                    score_run_id, draft_run_id, platform, subject_key,
                    approved_text, sent_at, source_url, context_evidence,
                    evidence_summary, source_link_opened, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'bili', 'bili:lead-bili-1',
                          ?, ?, ?, '人工筛选效率低', '人工筛选效率低',
                          1, ?, ?)
                """,
                (
                    outreach_id,
                    facts.run_id,
                    signal_id,
                    review_id,
                    score_id,
                    draft_id,
                    approved,
                    now,
                    source_url,
                    status,
                    now,
                ),
            )
    assert facts.connection.execute("SELECT count(*) FROM outreach_actions").fetchone()[0] == 0
    facts.close()


def test_sql_rejects_punctuation_only_sent_outreach_text_and_evidence(tmp_path):
    facts, signal_id = verified_facts(tmp_path)
    review_id, draft_id, _ = ready_for_outreach(facts, signal_id)
    score_id = facts.connection.execute(
        "SELECT presented_score_run_id FROM human_reviews WHERE review_id = ?",
        (review_id,),
    ).fetchone()[0]
    now = facts.clock().isoformat().replace("+00:00", "Z")

    with pytest.raises(sqlite3.IntegrityError, match="OUTREACH_VISIBLE_TEXT_REQUIRED"):
        facts.connection.execute(
            """
            INSERT INTO outreach_actions (
                outreach_action_id, mvp_run_id, signal_id, review_id,
                score_run_id, draft_run_id, platform, subject_key,
                approved_text, sent_at, source_url, context_evidence,
                evidence_summary, source_link_opened, status, created_at
            ) VALUES ('punctuation-only-outreach', ?, ?, ?, ?, ?, 'bili',
                      'bili:lead-bili-1', '，', ?,
                      'https://www.bilibili.com/video/source-1#reply-1',
                      '，', '，', 1, 'SENT_VERIFIED', ?)
            """,
            (facts.run_id, signal_id, review_id, score_id, draft_id, now, now),
        )

    assert facts.connection.execute("SELECT count(*) FROM outreach_actions").fetchone()[0] == 0
    facts.close()


def test_model_availability_event_cannot_be_replaced_after_run_cancellation(tmp_path):
    facts, signal_id = verified_facts(tmp_path)
    facts.repository.append_score_failure(
        score_run_id="blocked-model-score",
        run_id=facts.run_id,
        signal_id=signal_id,
        provider=None,
        model=None,
        prompt_version="prompt-v2",
        schema_version="schema-v2",
        error_code="MODEL_UNAVAILABLE",
    )
    before = facts.connection.execute(
        "SELECT * FROM model_availability_events WHERE fact_id = 'blocked-model-score'"
    ).fetchone()
    facts.repository.cancel_run(facts.run_id)

    with pytest.raises(sqlite3.IntegrityError, match="APPEND_ONLY_FACT"):
        facts.connection.execute(
            """
            INSERT OR REPLACE INTO model_availability_events (
                event_sequence, mvp_run_id, fact_kind, fact_id,
                availability_state, recorded_at
            ) VALUES (?, ?, 'SCORE', 'blocked-model-score', 'BLOCKED',
                      '2099-01-01T00:00:00Z')
            """,
            (before["event_sequence"], facts.run_id),
        )
    after = facts.connection.execute(
        "SELECT * FROM model_availability_events WHERE fact_id = 'blocked-model-score'"
    ).fetchone()
    assert tuple(after) == tuple(before)
    facts.close()


@pytest.mark.parametrize("blank_sql", ("char(9)", "char(8203)"))
def test_human_draft_body_must_be_visible_text_at_sql_boundary(tmp_path, blank_sql):
    facts, signal_id = verified_facts(tmp_path)
    session_id = facts.workflow.start_activity(facts.run_id, signal_id, "DRAFT")
    facts.clock.move(1)
    facts.workflow.record_activity(session_id, "COMPLETE")
    now = facts.clock().isoformat().replace("+00:00", "Z")

    with pytest.raises(sqlite3.IntegrityError, match="DRAFT_BODY_REQUIRED"):
        facts.connection.execute(
            f"""
            INSERT INTO draft_runs (
                draft_run_id, mvp_run_id, signal_id, provider, model,
                prompt_version, draft_kind, body, status,
                activity_session_id, created_at
            ) VALUES (
                'blank-human-draft', ?, ?, 'human', NULL, 'HUMAN_DRAFT_V1',
                'HUMAN_EDITED', {blank_sql}, 'SUCCEEDED', ?, ?
            )
            """,
            (facts.run_id, signal_id, session_id, now),
        )
    facts.close()


@pytest.mark.parametrize("invisible", ("\u200b", "\u3164", "\u115f", "\uffa0"))
def test_invisible_review_reason_is_rejected_by_workflow_and_sql(
    tmp_path, invisible
):
    facts, signal_id = verified_facts(tmp_path)
    score_id = "invisible-review-score"
    facts.repository.append_score_success(
        score_run_id=score_id,
        run_id=facts.run_id,
        signal_id=signal_id,
        provider="provider",
        model="model",
        prompt_version="prompt-v2",
        schema_version="schema-v2",
        decision=facts.decision,
        token_usage=None,
    )
    facts.workflow.present_score(facts.run_id, signal_id, score_id)
    session_id = facts.workflow.start_activity(facts.run_id, signal_id, "REVIEW")
    facts.clock.move(1)
    facts.workflow.record_activity(session_id, "COMPLETE")

    with pytest.raises(ValueError, match="review reason"):
        facts.workflow.complete_review(
            run_id=facts.run_id,
            signal_id=signal_id,
            label="POSSIBLE",
            reason=invisible,
            note=None,
            activity_session_id=session_id,
        )
    assert facts.connection.execute(
        "SELECT count(*) FROM human_reviews WHERE activity_session_id = ?",
        (session_id,),
    ).fetchone()[0] == 0
    facts.close()


@pytest.mark.parametrize("invisible", ("\u200b", "\u3164", "\u115f", "\uffa0"))
def test_sql_nonblank_predicate_rejects_invisible_unicode_fillers(
    tmp_path, invisible
):
    connection = connect(tmp_path / "invisible-text.sqlite3")
    migrate(connection)
    assert connection.execute(
        "SELECT yike_nonblank_text(?)", (invisible,)
    ).fetchone()[0] == 0
    connection.close()


@pytest.mark.parametrize(
    ("response_type", "summary_sql", "evidence_sql", "expected"),
    (
        ("INVALID", "NULL", "NULL", "RESPONSE_SUMMARY_REQUIRED"),
        ("VALID", "'愿意继续沟通'", "char(9)", "RESPONSE_EVIDENCE_REQUIRED"),
        ("INVALID", "char(8203)", "NULL", "RESPONSE_SUMMARY_REQUIRED"),
        ("VALID", "'愿意继续沟通'", "char(8203)", "RESPONSE_EVIDENCE_REQUIRED"),
    ),
)
def test_response_business_text_is_nonblank_at_sql_boundary(
    tmp_path, response_type, summary_sql, evidence_sql, expected
):
    facts, signal_id = verified_facts(tmp_path)
    review_id = facts.review(signal_id, 1)
    outreach_id = facts.outreach(signal_id, review_id, 1)
    now = facts.clock().isoformat().replace("+00:00", "Z")

    with pytest.raises(sqlite3.IntegrityError, match=expected):
        facts.connection.execute(
            f"""
            INSERT INTO response_events (
                response_event_id, mvp_run_id, outreach_action_id,
                responder_subject_key, response_type, summary, occurred_at,
                verified_at, evidence_summary, recorded_at
            ) VALUES (
                'bad-response-text', ?, ?, 'bili:lead-bili-1', ?,
                {summary_sql}, ?, ?, {evidence_sql}, ?
            )
            """,
            (facts.run_id, outreach_id, response_type, now, now, now),
        )
    assert facts.connection.execute(
        "SELECT count(*) FROM response_events WHERE response_event_id = 'bad-response-text'"
    ).fetchone()[0] == 0
    facts.close()


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        ("blank_answer", "INTERVIEW_SUMMARY_NOT_EXACT"),
        ("invisible_answer", "INTERVIEW_SUMMARY_NOT_EXACT"),
        ("blank_next_step", "INTERVIEW_NEXT_STEP_REQUIRED"),
        ("invisible_next_step", "INTERVIEW_NEXT_STEP_REQUIRED"),
        ("scheduled_before_response", "INTERVIEW_TIME_CAUSALITY"),
    ),
)
def test_completed_interview_requires_visible_and_causal_business_facts(
    tmp_path, mutation, expected
):
    facts, signal_id = verified_facts(tmp_path)
    review_id = facts.review(signal_id, 1)
    outreach_id = facts.outreach(signal_id, review_id, 1)
    response_id = facts.response(outreach_id, 1)
    now = facts.clock().isoformat().replace("+00:00", "Z")
    response_time = datetime.fromisoformat(now.replace("Z", "+00:00"))
    prior = (response_time - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    summary = {
        "customer_source_and_sales_process": "内容营销进入销售跟进",
        "weekly_lead_volume_and_loss_point": "每周 200 条，首轮筛选丢失最多",
        "most_manual_step": "销售逐条判断意图",
        "current_tools": "CRM 和表格",
        "minimum_agent_scenario_and_decision_process": "先试线索排序，由销售负责人决策",
    }
    if mutation == "blank_answer":
        summary["most_manual_step"] = "\t"
    elif mutation == "invisible_answer":
        summary["most_manual_step"] = "\u200b"
    next_step = {
        "blank_next_step": "\t",
        "invisible_next_step": "\u200b",
    }.get(mutation, "试点")
    scheduled_at = prior if mutation == "scheduled_before_response" else now

    with pytest.raises(sqlite3.IntegrityError, match=expected):
        facts.connection.execute(
            """
            INSERT INTO interviews (
                interview_id, mvp_run_id, response_event_id, scheduled_at,
                completed_at, summary_json, solution_fit, next_step, recorded_at
            ) VALUES ('bad-interview', ?, ?, ?, ?, ?, 'SOLVABLE', ?, ?)
            """,
            (
                facts.run_id,
                response_id,
                scheduled_at,
                now,
                json.dumps(summary, ensure_ascii=False),
                next_step,
                now,
            ),
        )
    facts.close()


def test_scheduled_interview_must_follow_verified_response_without_completion(
    tmp_path,
):
    facts, signal_id = verified_facts(tmp_path)
    review_id = facts.review(signal_id, 1)
    outreach_id = facts.outreach(signal_id, review_id, 1)
    response_id = facts.response(outreach_id, 1)
    response_verified_at = str(facts.connection.execute(
        "SELECT verified_at FROM response_events WHERE response_event_id = ?",
        (response_id,),
    ).fetchone()[0])
    before_response = (
        datetime.fromisoformat(response_verified_at.replace("Z", "+00:00"))
        - timedelta(seconds=1)
    ).isoformat().replace("+00:00", "Z")
    recorded_at = facts.clock().isoformat().replace("+00:00", "Z")

    with pytest.raises(sqlite3.IntegrityError, match="INTERVIEW_TIME_CAUSALITY"):
        facts.connection.execute(
            """
            INSERT INTO interviews (
                interview_id, mvp_run_id, response_event_id, scheduled_at,
                completed_at, summary_json, solution_fit, next_step, recorded_at
            ) VALUES ('early-scheduled-interview', ?, ?, ?, NULL, NULL,
                      'UNKNOWN', NULL, ?)
            """,
            (facts.run_id, response_id, before_response, recorded_at),
        )
    assert facts.connection.execute(
        "SELECT count(*) FROM interviews WHERE interview_id = 'early-scheduled-interview'"
    ).fetchone()[0] == 0
    facts.close()


@pytest.mark.parametrize("blank_sql", ("char(9)", "char(8203)"))
def test_quote_scope_must_be_visible_text_at_sql_boundary(tmp_path, blank_sql):
    facts, signal_id = verified_facts(tmp_path)
    review_id = facts.review(signal_id, 1)
    outreach_id = facts.outreach(signal_id, review_id, 1)
    response_id = facts.response(outreach_id, 1)
    interview_id = facts.interview(response_id)
    now = facts.clock().isoformat().replace("+00:00", "Z")

    with pytest.raises(sqlite3.IntegrityError, match="QUOTE_SCOPE_REQUIRED"):
        facts.connection.execute(
            f"""
            INSERT INTO quote_opportunities (
                quote_opportunity_id, mvp_run_id, response_event_id,
                interview_id, scope_summary, agreed_to_receive_pricing_at,
                verified_at, recorded_at
            ) VALUES ('blank-quote', ?, ?, ?, {blank_sql}, ?, ?, ?)
            """,
            (facts.run_id, response_id, interview_id, now, now, now),
        )
    facts.close()


@pytest.mark.parametrize(
    "base_url",
    (
        "http://models.example/v1",
        "http://localhost:8000/v1",
        "ftp://models.example/v1",
        "https://user:password@models.example/v1",
        "https://models.example/v1?tenant=secret",
    ),
)
def test_model_endpoint_policy_rejects_unsafe_remote_urls(base_url):
    with pytest.raises(ValueError, match="model base URL"):
        OpenAICompatibleModelClient(
            base_url=base_url,
            api_key="do-not-leak",
            model="strict-model",
        )


@pytest.mark.parametrize(
    "error",
    (
        TimeoutError("timeout"),
        OSError("connection"),
        httpx.ReadTimeout(
            "timeout", request=httpx.Request("POST", "https://models.example/v1")
        ),
        httpx.ConnectError(
            "connection", request=httpx.Request("POST", "https://models.example/v1")
        ),
    ),
)
def test_builtin_model_transport_failures_are_unavailable(tmp_path, error):
    connection, repository, _, run_id, signal_id = unverified_facts(tmp_path)

    result = Scorer(repository, StubClient(error)).score(run_id, signal_id)

    assert (result.status, result.error_code) == ("FAILED", "MODEL_UNAVAILABLE")
    connection.close()


@pytest.mark.parametrize(
    "error",
    (
        TimeoutError("timeout"),
        OSError("connection"),
        httpx.ReadTimeout(
            "timeout", request=httpx.Request("POST", "https://models.example/v1")
        ),
        httpx.ConnectError(
            "connection", request=httpx.Request("POST", "https://models.example/v1")
        ),
    ),
)
def test_builtin_draft_transport_failures_are_unavailable(tmp_path, error):
    connection, repository, _, run_id, signal_id = unverified_facts(tmp_path)

    result = DraftGenerator(repository, DraftFailureClient(error)).generate(run_id, signal_id)

    assert (result.status, result.error_code) == ("FAILED", "MODEL_UNAVAILABLE")
    connection.close()


@pytest.mark.parametrize("invisible", ("\u200b", "\u3164"))
def test_workflow_rejects_invisible_interview_answers_before_sqlite(
    tmp_path, invisible
):
    facts, signal_id = verified_facts(tmp_path)
    review_id = facts.review(signal_id, 1)
    outreach_id = facts.outreach(signal_id, review_id, 1)
    response_id = facts.response(outreach_id, 1)
    summary = {
        "customer_source_and_sales_process": "内容营销进入销售跟进",
        "weekly_lead_volume_and_loss_point": "每周 200 条，首轮筛选丢失最多",
        "most_manual_step": invisible,
        "current_tools": "CRM 和表格",
        "minimum_agent_scenario_and_decision_process": "先试线索排序，由销售负责人决策",
    }
    now = facts.clock().isoformat().replace("+00:00", "Z")

    with pytest.raises(ValueError, match="five nonblank answers"):
        facts.workflow.register_interview(
            run_id=facts.run_id,
            response_event_id=response_id,
            scheduled_at=now,
            completed_at=now,
            summary=summary,
            solution_fit="SOLVABLE",
            next_step="试点",
        )
    assert facts.connection.execute("SELECT count(*) FROM interviews").fetchone()[0] == 0
    facts.close()


def test_web_maps_invisible_interview_answer_to_400_without_fact(tmp_path):
    settings = settings_for(tmp_path)
    facts = FactBuilder(settings.data_dir / "discovery.sqlite3")
    signal_id = facts.collect_signals([1])[0]
    review_id = facts.review(signal_id, 1)
    outreach_id = facts.outreach(signal_id, review_id, 1)
    response_id = facts.response(outreach_id, 1)
    run_id = facts.run_id
    now = facts.clock().isoformat().replace("+00:00", "Z")
    facts.close()

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/followups/interviews",
            data={
                "run_id": run_id,
                "response_event_id": response_id,
                "scheduled_at": now,
                "completed_at": now,
                "customer_source_and_sales_process": "内容营销进入销售跟进",
                "weekly_lead_volume_and_loss_point": "每周 200 条",
                "most_manual_step": "\u200b",
                "current_tools": "CRM 和表格",
                "minimum_agent_scenario_and_decision_process": "先试线索排序",
                "solution_fit": "SOLVABLE",
                "next_step": "试点",
            },
            follow_redirects=False,
        )

    assert response.status_code == 400
    connection = connect(settings.data_dir / "discovery.sqlite3")
    assert connection.execute("SELECT count(*) FROM interviews").fetchone()[0] == 0
    connection.close()


def test_invalid_model_response_fails_closed_without_secret_disclosure(tmp_path, caplog):
    facts, signal_id = verified_facts(tmp_path)
    secret = "MODEL-SECRET-MUST-NOT-LEAK"
    client = OpenAICompatibleModelClient(
        base_url="https://models.example/v1",
        api_key=secret,
        model="strict-model",
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"unexpected": "shape"})
            )
        ),
    )

    result = Scorer(facts.repository, client).score(facts.run_id, signal_id)

    assert (result.status, result.error_code) == ("FAILED", "MODEL_OUTPUT_INVALID")
    assert secret not in repr(client)
    assert secret not in "\n".join(facts.connection.iterdump())
    assert secret not in caplog.text
    facts.close()


@pytest.mark.parametrize("operation", ["score", "draft"])
def test_duplicate_model_json_key_fails_closed_before_persistence(tmp_path, operation):
    facts, signal_id = verified_facts(tmp_path)
    if operation == "score":
        content = json.dumps(valid_decision(), ensure_ascii=False).replace(
            '"grade": "A"', '"grade": "D", "grade": "A"', 1
        )
    else:
        draft = {
            "body": (
                "你提到人工筛选效率低。我们正在研究 B2B 销售 Agent 的线索流程。"
                "你们每周需要筛选多少条线索？"
            ),
            "source_snippet": "人工筛选效率低",
            "research_purpose_sentence": "我们正在研究 B2B 销售 Agent 的线索流程。",
            "diagnostic_question": "你们每周需要筛选多少条线索？",
        }
        content = json.dumps(draft, ensure_ascii=False).replace(
            '"body":', '"body": "歧义草稿", "body":', 1
        )
    client = OpenAICompatibleModelClient(
        base_url="https://models.example/v1",
        api_key="test-secret",
        model="strict-model",
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={"choices": [{"message": {"content": content}}]},
                )
            )
        ),
    )

    if operation == "score":
        result = Scorer(facts.repository, client).score(facts.run_id, signal_id)
        row = facts.connection.execute(
            "SELECT status, error_code, grade FROM score_runs WHERE score_run_id = ?",
            (result.score_run_id,),
        ).fetchone()
        assert tuple(row) == ("FAILED", "MODEL_OUTPUT_INVALID", None)
    else:
        result = DraftGenerator(facts.repository, client).generate(
            facts.run_id, signal_id
        )
        row = facts.connection.execute(
            "SELECT status, error_code, body FROM draft_runs WHERE draft_run_id = ?",
            (result.draft_run_id,),
        ).fetchone()
        assert tuple(row) == ("FAILED", "MODEL_OUTPUT_INVALID", None)
    facts.close()


def test_detail_render_does_not_implicitly_present_score_and_ack_is_explicit(tmp_path):
    settings = settings_for(tmp_path)
    connection, _, _, run_id, signal_id, _ = web_facts(settings)

    with TestClient(create_app(settings)) as client:
        response = client.get(f"/signals/{signal_id}", params={"run_id": run_id})
        assert response.status_code == 200
        assert connection.execute("SELECT count(*) FROM score_presentations").fetchone()[0] == 0
        assert "data-score-presentation" in response.text

        acknowledged = client.post(
            f"/signals/{signal_id}/score-presentations",
            data={"run_id": run_id, "score_run_id": "web-score"},
        )
        assert acknowledged.status_code == 200
        assert acknowledged.json()["score_run_id"] == "web-score"

    assert connection.execute("SELECT count(*) FROM score_presentations").fetchone()[0] == 1
    connection.close()


def test_frozen_presentation_prevents_later_rescore_from_becoming_ack_candidate(tmp_path):
    settings = settings_for(tmp_path)
    connection, repository, workflow, run_id, signal_id, _ = web_facts(settings)
    workflow.present_score(run_id, signal_id, "web-score")
    # A valid later score may be stored, but it must never replace the score
    # already acknowledged as the first human presentation.
    decision = ScoreDecision.model_validate(
        valid_decision(),
        context={
            "source_text": (
                "销售获客讨论\n我们需要改善获客\n"
                "团队正在筛选销售线索，人工筛选效率低"
            ),
            "source_verifiable": True,
        },
    )
    repository.append_score_success(
        score_run_id="zz-later-score",
        run_id=run_id,
        signal_id=signal_id,
        provider="provider",
        model="model",
        prompt_version="prompt-v2",
        schema_version="schema-v2",
        decision=decision,
        token_usage=None,
    )

    with TestClient(create_app(settings)) as client:
        response = client.get(f"/signals/{signal_id}", params={"run_id": run_id})

    assert response.status_code == 200
    assert " data-score-presentation data-run-id=" not in response.text
    assert connection.execute("SELECT count(*) FROM score_presentations").fetchone()[0] == 1
    connection.close()


def test_business_fact_registration_performs_no_network_io(tmp_path, monkeypatch):
    facts, signal_id = verified_facts(tmp_path)
    review_id = facts.review(signal_id, 1)

    def unexpected_network(*args, **kwargs):
        raise AssertionError("business fact registration attempted network I/O")

    monkeypatch.setattr(httpx.Client, "request", unexpected_network)
    monkeypatch.setattr(socket, "create_connection", unexpected_network)
    outreach_id = facts.outreach(signal_id, review_id, 1)
    root = facts.connection.execute(
        "SELECT * FROM outreach_actions WHERE outreach_action_id = ?", (outreach_id,)
    ).fetchone()
    follow_up_id = facts.workflow.register_outreach(
        run_id=facts.run_id,
        signal_id=signal_id,
        review_id=review_id,
        draft_run_id=str(root["draft_run_id"]),
        platform="bili",
        subject_key="bili:lead-bili-1",
        approved_text=str(root["approved_text"]),
        context_evidence=str(root["context_evidence"]),
        sent_at=str(root["sent_at"]),
        source_url=str(root["source_url"]),
        source_link_opened=True,
        parent_outreach_action_id=outreach_id,
    )
    response_id = facts.response(outreach_id, 1)
    interview_id = facts.interview(response_id)
    now = facts.clock().isoformat().replace("+00:00", "Z")
    quote_id = facts.workflow.register_quote(
        run_id=facts.run_id,
        response_event_id=response_id,
        interview_id=interview_id,
        scope_summary="线索识别试点",
        agreed_to_receive_pricing_at=now,
        verified_at=now,
    )

    assert quote_id and follow_up_id
    facts.close()


def test_web_outreach_registration_performs_no_socket_io(tmp_path, monkeypatch):
    settings = settings_for(tmp_path)
    connection, _, workflow, run_id, signal_id, _ = web_facts(settings)
    workflow.present_score(run_id, signal_id, "web-score")
    review_session = workflow.start_activity(run_id, signal_id, "REVIEW")
    workflow.record_activity(review_session, "COMPLETE")
    review_id = workflow.complete_review(
        run_id=run_id,
        signal_id=signal_id,
        label="HIGH_INTENT",
        reason="人工核验",
        note=None,
        activity_session_id=review_session,
    )
    draft_session = workflow.start_activity(run_id, signal_id, "DRAFT")
    workflow.record_activity(draft_session, "COMPLETE")
    approved = "人工筛选效率低。我们正在研究销售 Agent。你们每周筛选多少条线索？"
    draft_id = workflow.create_draft(
        run_id=run_id,
        signal_id=signal_id,
        body=approved,
        activity_session_id=draft_session,
    )
    connection.close()

    def unexpected_socket(*args, **kwargs):
        raise AssertionError("web outreach registration attempted socket I/O")

    monkeypatch.setattr(socket, "create_connection", unexpected_socket)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            f"/signals/{signal_id}/outreach",
            data={
                "run_id": run_id,
                "review_id": review_id,
                "draft_run_id": draft_id,
                "platform": "bili",
                "approved_text": approved,
                "context_evidence": "人工筛选效率低",
                "sent_at": "2026-08-12T08:00:00Z",
                "source_url": "https://www.bilibili.com/video/av-web#reply-web",
                "source_link_opened": "yes",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    connection = connect(settings.data_dir / "discovery.sqlite3")
    assert connection.execute("SELECT count(*) FROM outreach_actions").fetchone()[0] == 1
    connection.close()


def test_duplicate_identical_root_outreach_returns_frozen_fact_not_raw_sqlite(tmp_path):
    facts, signal_id = verified_facts(tmp_path)
    review_id = facts.review(signal_id, 1)
    outreach_id = facts.outreach(signal_id, review_id, 1)
    row = facts.connection.execute(
        "SELECT * FROM outreach_actions WHERE outreach_action_id = ?",
        (outreach_id,),
    ).fetchone()

    repeated = facts.workflow.register_outreach(
        run_id=facts.run_id,
        signal_id=signal_id,
        review_id=review_id,
        draft_run_id=str(row["draft_run_id"]),
        platform="bili",
        subject_key="bili:lead-bili-1",
        approved_text=str(row["approved_text"]),
        context_evidence=str(row["context_evidence"]),
        sent_at=str(row["sent_at"]),
        source_url=str(row["source_url"]),
        source_link_opened=True,
    )

    assert repeated == outreach_id
    assert facts.connection.execute("SELECT count(*) FROM outreach_actions").fetchone()[0] == 1
    facts.close()


def test_two_connections_converge_on_one_first_presentation(tmp_path):
    database = tmp_path / "presentation-race.sqlite3"
    facts = FactBuilder(database)
    signal_id = facts.collect_signals([1])[0]
    for score_id in ("race-score-a", "race-score-b"):
        facts.repository.append_score_success(
            score_run_id=score_id,
            run_id=facts.run_id,
            signal_id=signal_id,
            provider="provider",
            model="model",
            prompt_version="prompt-v2",
            schema_version="schema-v2",
            decision=facts.decision,
            token_usage=None,
        )
    run_id = facts.run_id
    clock = facts.clock
    facts.close()
    barrier = Barrier(2)

    def acknowledge(score_id: str) -> str:
        connection = connect(database)
        migrate(connection)
        try:
            barrier.wait()
            return Workflow(Repository(connection, now=clock), now=clock).present_score(
                run_id, signal_id, score_id
            )
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(acknowledge, ("race-score-a", "race-score-b")))

    connection = connect(database)
    assert len(set(results)) == 1
    assert connection.execute("SELECT count(*) FROM score_presentations").fetchone()[0] == 1
    assert connection.execute("SELECT score_run_id FROM score_presentations").fetchone()[0] == results[0]
    connection.close()


def test_two_connections_converge_on_one_open_activity(tmp_path):
    database = tmp_path / "activity-race.sqlite3"
    facts = FactBuilder(database)
    signal_id = facts.collect_signals([1])[0]
    run_id = facts.run_id
    clock = facts.clock
    facts.close()
    barrier = Barrier(2)

    def start() -> str:
        connection = connect(database)
        migrate(connection)
        try:
            barrier.wait()
            return Workflow(Repository(connection, now=clock), now=clock).start_activity(
                run_id, signal_id, "REVIEW"
            )
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: start(), range(2)))

    connection = connect(database)
    assert len(set(results)) == 1
    assert connection.execute(
        "SELECT count(*) FROM activity_sessions WHERE state = 'OPEN'"
    ).fetchone()[0] == 1
    assert connection.execute("SELECT count(*) FROM activity_events").fetchone()[0] == 1
    connection.close()


def test_two_different_pause_events_do_not_both_report_idempotent_success(tmp_path):
    database = tmp_path / "activity-pause-race.sqlite3"
    facts = FactBuilder(database)
    signal_id = facts.collect_signals([1])[0]
    session_id = facts.workflow.start_activity(facts.run_id, signal_id, "REVIEW")
    run_clock = facts.clock
    facts.close()
    barrier = Barrier(2)

    class CoordinatedCursor:
        def __init__(self, cursor):
            self.cursor = cursor

        def fetchone(self):
            row = self.cursor.fetchone()
            barrier.wait()
            return row

        def __getattr__(self, name):
            return getattr(self.cursor, name)

    class CoordinatedConnection:
        def __init__(self, connection):
            self.connection = connection

        @property
        def in_transaction(self):
            return self.connection.in_transaction

        def execute(self, statement, parameters=()):
            cursor = self.connection.execute(statement, parameters)
            if "SELECT sequence_no, received_at FROM activity_events" in statement:
                return CoordinatedCursor(cursor)
            return cursor

        def commit(self):
            return self.connection.commit()

        def rollback(self):
            return self.connection.rollback()

        def __enter__(self):
            self.connection.__enter__()
            return self

        def __exit__(self, *args):
            return self.connection.__exit__(*args)

    def pause(event_kind: str) -> str:
        raw = connect(database)
        migrate(raw)
        connection = CoordinatedConnection(raw)
        try:
            workflow = Workflow(Repository(connection, now=run_clock), now=run_clock)
            try:
                workflow.record_activity(session_id, event_kind)
            except WorkflowConflictError:
                return "conflict"
            return "success"
        finally:
            raw.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(pause, ("PAUSE_HIDDEN", "PAUSE_IDLE")))

    connection = connect(database)
    persisted = connection.execute(
        "SELECT event_kind FROM activity_events "
        "WHERE activity_session_id = ? ORDER BY sequence_no",
        (session_id,),
    ).fetchall()
    assert sorted(results) == ["conflict", "success"]
    assert [row[0] for row in persisted] in (
        ["START", "PAUSE_HIDDEN"],
        ["START", "PAUSE_IDLE"],
    )
    connection.close()


def test_two_connections_register_identical_root_as_one_fact(tmp_path):
    database = tmp_path / "outreach-race.sqlite3"
    facts = FactBuilder(database)
    signal_id = facts.collect_signals([1])[0]
    review_id, draft_id, approved = ready_for_outreach(facts, signal_id)
    run_id = facts.run_id
    clock = facts.clock
    sent_at = clock().isoformat().replace("+00:00", "Z")
    facts.close()
    barrier = Barrier(2)

    def register() -> str:
        connection = connect(database)
        migrate(connection)
        try:
            barrier.wait()
            return Workflow(Repository(connection, now=clock), now=clock).register_outreach(
                run_id=run_id,
                signal_id=signal_id,
                review_id=review_id,
                draft_run_id=draft_id,
                platform="bili",
                subject_key="bili:lead-bili-1",
                approved_text=approved,
                context_evidence="人工筛选效率低",
                sent_at=sent_at,
                source_url="https://www.bilibili.com/video/source-1#reply-1",
                source_link_opened=True,
            )
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: register(), range(2)))

    connection = connect(database)
    assert len(set(results)) == 1
    assert connection.execute("SELECT count(*) FROM outreach_actions").fetchone()[0] == 1
    connection.close()
