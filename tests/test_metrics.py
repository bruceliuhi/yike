from datetime import UTC, datetime

import pytest

from app.db import connect, migrate
from app.metrics import MetricsEngine, conclusion_for
from app.model_contract import ScoreDecision
from app.repository import NormalizedSignal, Repository
from app.workflow import Workflow


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ({"incident": True, "loss_stop": True, "blocked_input": True,
          "all_success_thresholds": True, "terminal_eligible": True}, "STOP_DISCOVERY"),
        ({"loss_stop": True, "blocked_input": True,
          "all_success_thresholds": True, "terminal_eligible": True}, "STOP_DISCOVERY"),
        ({"blocked_input": True, "all_success_thresholds": True,
          "terminal_eligible": True}, "BLOCKED_INPUT"),
        ({"all_success_thresholds": True, "terminal_eligible": True},
         "PROCEED_TO_V03_REVIEW"),
        ({"terminal_eligible": True}, "REVISE_MVP"),
        ({}, "RUNNING"),
    ],
)
def test_conclusion_truth_table_is_ordered_and_exhaustive(flags, expected):
    assert conclusion_for(**flags) == expected


def test_empty_run_metrics_are_sql_derived_and_running(tmp_path):
    connection = connect(tmp_path / "facts.sqlite3")
    migrate(connection)
    repository = Repository(connection)
    run_id = repository.create_run(["bili", "dy"])

    snapshot = MetricsEngine(connection).calculate(
        run_id, now=datetime(2026, 8, 12, tzinfo=UTC)
    )

    assert snapshot.run_id == run_id
    assert snapshot.unique_verifiable_signals == 0
    assert snapshot.reviewed_signals == 0
    assert snapshot.first_outreach_subjects == 0
    assert snapshot.decision == "RUNNING"
    connection.close()


def test_seeded_metrics_count_unique_verified_fact_chains(tmp_path):
    connection = connect(tmp_path / "facts.sqlite3")
    migrate(connection)
    clock = lambda: datetime(2026, 8, 12, 8, tzinfo=UTC)
    repository = Repository(connection, now=clock)
    run_id = repository.create_run(["bili", "dy"])
    signal_id = repository.import_signal(
        run_id,
        NormalizedSignal(
            platform="bili",
            external_source_id="av-metric",
            source_title="企业获客讨论",
            source_url="https://www.bilibili.com/video/av-metric",
            source_author_public_id="source-metric",
            external_comment_id="metric-comment",
            comment_url="https://www.bilibili.com/video/av-metric#reply-metric",
            author_public_id="lead-metric",
            body="团队需要更快筛选销售线索",
            query_cluster="sales-agent",
            query_text="销售线索",
        ),
    ).signal_id
    decision = ScoreDecision.model_validate(
        {
            "grade": "A",
            "score": 10,
            "confidence": 0.9,
            "explicit_industry": "B2B 销售",
            "business_context": "团队筛选销售线索",
            "pain_summary": "筛选速度慢",
            "intent_summary": "需要更快筛选",
            "evidence_snippets": ["团队需要更快筛选销售线索"],
            "dimension_scores": {
                "business_team_context": 2,
                "offer_fit": 2,
                "action_intent": 3,
                "buying_signal": 1,
                "contact_context": 1,
                "evidence_completeness": 1,
            },
            "exclusion_reasons": [],
            "recommended_question": "每周需要筛选多少条？",
        },
        context={"source_text": "团队需要更快筛选销售线索"},
    )
    repository.append_score_success(
        score_run_id="metric-score",
        run_id=run_id,
        signal_id=signal_id,
        provider="provider-that-must-not-export",
        model="model-that-must-not-export",
        prompt_version="prompt-secretish",
        schema_version="schema-v1",
        decision=decision,
        token_usage={"total_tokens": 99},
    )
    workflow = Workflow(repository, now=clock)
    workflow.present_score(run_id, signal_id, "metric-score")
    review_session = workflow.start_activity(run_id, signal_id, "REVIEW")
    workflow.record_activity(review_session, "COMPLETE")
    review_id = workflow.complete_review(
        run_id=run_id,
        signal_id=signal_id,
        label="HIGH_INTENT",
        reason="企业意图明确",
        note=None,
        activity_session_id=review_session,
    )
    draft_session = workflow.start_activity(run_id, signal_id, "DRAFT")
    workflow.record_activity(draft_session, "COMPLETE")
    draft_id = workflow.create_draft(
        run_id=run_id, signal_id=signal_id,
        body="团队需要更快筛选销售线索，想了解每周线索量。",
        activity_session_id=draft_session,
    )
    outreach_id = workflow.register_outreach(
        run_id=run_id,
        signal_id=signal_id,
        review_id=review_id,
        draft_run_id=draft_id,
        platform="bili",
        subject_key="bili:lead-metric",
        approved_text="团队需要更快筛选销售线索，想了解每周线索量。",
        context_evidence="团队需要更快筛选销售线索",
        sent_at="2026-08-12T09:00:00Z",
        source_url="https://www.bilibili.com/video/av-metric#reply-metric",
        source_link_opened=True,
    )
    response_id = workflow.register_response(
        run_id=run_id,
        outreach_action_id=outreach_id,
        responder_subject_key="bili:lead-metric",
        response_type="VALID",
        summary="愿意沟通",
        occurred_at="2026-08-12T10:00:00Z",
        verified_at="2026-08-12T10:01:00Z",
        evidence_summary="愿意沟通",
    )
    interview_id = workflow.register_interview(
        run_id=run_id,
        response_event_id=response_id,
        scheduled_at="2026-08-13T01:00:00Z",
        completed_at="2026-08-13T01:30:00Z",
        summary={
            "customer_source_and_sales_process": "内容营销进入销售",
            "weekly_lead_volume_and_loss_point": "每周二百条",
            "most_manual_step": "人工判断",
            "current_tools": "CRM",
            "minimum_agent_scenario_and_decision_process": "先试排序",
        },
        solution_fit="SOLVABLE",
        next_step="报价",
    )
    workflow.register_quote(
        run_id=run_id,
        response_event_id=response_id,
        interview_id=interview_id,
        scope_summary="线索筛选试点",
        agreed_to_receive_pricing_at="2026-08-13T01:31:00Z",
        verified_at="2026-08-13T01:32:00Z",
    )

    snapshot = MetricsEngine(connection).calculate(
        run_id, now=datetime(2026, 8, 13, 2, tzinfo=UTC)
    )

    assert (
        snapshot.unique_verifiable_signals,
        snapshot.reviewed_signals,
        snapshot.reviewed_ab,
        snapshot.high_intent_ab,
        snapshot.first_outreach_subjects,
        snapshot.valid_response_subjects,
        snapshot.completed_interviews,
        snapshot.verified_quotes,
    ) == (1, 1, 1, 1, 1, 1, 1, 1)
    assert snapshot.precision == 1.0
    assert snapshot.all_success_thresholds is False

    revision_session = workflow.start_activity(run_id, signal_id, "REVIEW")
    workflow.record_activity(revision_session, "COMPLETE")
    workflow.complete_review(
        run_id=run_id,
        signal_id=signal_id,
        label="NOT_LEAD",
        reason="复核后确认无采购意图",
        note=None,
        activity_session_id=revision_session,
        supersedes_review_id=review_id,
    )
    workflow.register_quote(
        run_id=run_id,
        response_event_id=response_id,
        interview_id=interview_id,
        scope_summary="同一主体的追加范围",
        agreed_to_receive_pricing_at="2026-08-13T01:40:00Z",
        verified_at="2026-08-13T01:45:00Z",
    )
    repository.append_score_failure(
        score_run_id="metric-model-block",
        run_id=run_id,
        signal_id=signal_id,
        provider=None,
        model=None,
        prompt_version="prompt-v1",
        schema_version="schema-v1",
        error_code="MODEL_NOT_CONFIGURED",
    )
    revised = MetricsEngine(connection).calculate(
        run_id, now=datetime(2026, 8, 13, 3, tzinfo=UTC)
    )

    assert revised.reviewed_signals == 1
    assert revised.reviewed_ab == 1
    assert revised.high_intent_ab == 0
    assert revised.precision == 0.0
    assert revised.verified_quotes == 1
    assert revised.blocked_input is True
    assert revised.decision == "BLOCKED_INPUT"
    connection.close()
