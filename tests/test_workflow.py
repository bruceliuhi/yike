from datetime import UTC, datetime
import sqlite3

import pytest

from app.db import connect, migrate
from app.repository import NormalizedSignal, Repository
from app.scorer import Scorer
from app.workflow import Workflow
from tests.test_scoring import valid_decision


class SuccessfulClient:
    provider = "openai-compatible"
    model = "test-model"

    def complete(self, *, source_text):
        return valid_decision(), {"total_tokens": 42}


@pytest.fixture
def facts(tmp_path):
    connection = connect(tmp_path / "workflow.sqlite3")
    migrate(connection)
    clock = lambda: datetime(2026, 8, 12, 8, tzinfo=UTC)
    repository = Repository(connection, now=clock)
    run_id = repository.create_run(["bili", "dy"])
    signal_id = repository.import_signal(
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
    ).signal_id
    yield connection, repository, Workflow(repository, now=clock), run_id, signal_id
    connection.close()


def score(repository, run_id, signal_id):
    return Scorer(repository, SuccessfulClient()).score(run_id, signal_id)


def completed_session(workflow, run_id, signal_id, kind):
    session_id = workflow.start_activity(run_id, signal_id, kind)
    workflow.record_activity(session_id, "COMPLETE")
    return session_id


def prepare_reviewed_draft(facts):
    connection, repository, workflow, run_id, signal_id = facts
    scored = score(repository, run_id, signal_id)
    workflow.present_score(run_id, signal_id, scored.score_run_id)
    review_id = workflow.complete_review(
        run_id=run_id,
        signal_id=signal_id,
        label="HIGH_INTENT",
        reason="企业场景和行动意图明确",
        note=None,
        activity_session_id=completed_session(workflow, run_id, signal_id, "REVIEW"),
    )
    draft_id = workflow.create_draft(
        run_id=run_id,
        signal_id=signal_id,
        body="想了解一下，你们目前每周需要筛选多少条线索？",
        activity_session_id=completed_session(workflow, run_id, signal_id, "DRAFT"),
    )
    return review_id, draft_id, scored.score_run_id


def test_review_binds_first_presented_successful_score(facts):
    connection, repository, workflow, run_id, signal_id = facts
    first = score(repository, run_id, signal_id)
    second = score(repository, run_id, signal_id)

    assert workflow.present_score(run_id, signal_id, first.score_run_id) == first.score_run_id
    assert workflow.present_score(run_id, signal_id, second.score_run_id) == first.score_run_id
    review_id = workflow.complete_review(
        run_id=run_id,
        signal_id=signal_id,
        label="POSSIBLE",
        reason="需进一步确认采购信号",
        note="后续有重评但不换分母",
        activity_session_id=completed_session(workflow, run_id, signal_id, "REVIEW"),
    )

    row = connection.execute(
        "SELECT presented_score_run_id FROM human_reviews WHERE review_id = ?",
        (review_id,),
    ).fetchone()
    assert row["presented_score_run_id"] == first.score_run_id


def test_review_revisions_must_supersede_the_current_leaf(facts):
    _, repository, workflow, run_id, signal_id = facts
    scored = score(repository, run_id, signal_id)
    workflow.present_score(run_id, signal_id, scored.score_run_id)
    first_review = workflow.complete_review(
        run_id=run_id,
        signal_id=signal_id,
        label="POSSIBLE",
        reason="初次复核",
        note=None,
        activity_session_id=completed_session(workflow, run_id, signal_id, "REVIEW"),
    )

    with pytest.raises(ValueError, match="current review"):
        workflow.complete_review(
            run_id=run_id,
            signal_id=signal_id,
            label="NOT_LEAD",
            reason="断根改标",
            note=None,
            activity_session_id=completed_session(workflow, run_id, signal_id, "REVIEW"),
        )

    second_review = workflow.complete_review(
        run_id=run_id,
        signal_id=signal_id,
        label="HIGH_INTENT",
        reason="补充证据后改标",
        note=None,
        activity_session_id=completed_session(workflow, run_id, signal_id, "REVIEW"),
        supersedes_review_id=first_review,
    )
    assert second_review != first_review

    with pytest.raises(ValueError, match="current review"):
        workflow.complete_review(
            run_id=run_id,
            signal_id=signal_id,
            label="UNVERIFIABLE",
            reason="不允许从旧节点分叉",
            note=None,
            activity_session_id=completed_session(workflow, run_id, signal_id, "REVIEW"),
            supersedes_review_id=first_review,
        )


def test_failed_score_cannot_be_presented(facts):
    _, repository, workflow, run_id, signal_id = facts
    failed = Scorer(repository, client=None).score(run_id, signal_id)

    with pytest.raises(sqlite3.IntegrityError, match="PRESENTED_SCORE_NOT_SUCCEEDED"):
        workflow.present_score(run_id, signal_id, failed.score_run_id)


def test_draft_and_outreach_are_manual_facts_with_link_confirmation(facts):
    connection, _, workflow, run_id, signal_id = facts
    review_id, draft_id, _ = prepare_reviewed_draft(facts)

    with pytest.raises(ValueError, match="source link"):
        workflow.register_outreach(
            run_id=run_id,
            signal_id=signal_id,
            review_id=review_id,
            draft_run_id=draft_id,
            platform="bili",
            subject_key="bili:comment-author",
            approved_text="人工筛选效率低，人工编辑后的文本",
            context_evidence="人工筛选效率低",
            sent_at="2026-08-12T09:05:00Z",
            source_url="https://www.bilibili.com/video/av1#reply1",
            source_link_opened=False,
        )

    outreach_id = workflow.register_outreach(
        run_id=run_id,
        signal_id=signal_id,
        review_id=review_id,
        draft_run_id=draft_id,
        platform="bili",
        subject_key="bili:comment-author",
        approved_text="人工筛选效率低，人工编辑后的文本",
        context_evidence="人工筛选效率低",
        sent_at="2026-08-12T09:05:00Z",
        source_url="https://www.bilibili.com/video/av1#reply1",
        source_link_opened=True,
    )

    row = connection.execute(
        "SELECT approved_text, sent_at, source_link_opened, status "
        "FROM outreach_actions WHERE outreach_action_id = ?",
        (outreach_id,),
    ).fetchone()
    assert tuple(row) == (
        "人工筛选效率低，人工编辑后的文本",
        "2026-08-12T09:05:00Z",
        1,
        "SENT_VERIFIED",
    )


def test_follow_up_must_reference_the_root_first_contact(facts):
    _, _, workflow, run_id, signal_id = facts
    review_id, draft_id, _ = prepare_reviewed_draft(facts)
    values = dict(
        run_id=run_id,
        signal_id=signal_id,
        review_id=review_id,
        draft_run_id=draft_id,
        platform="bili",
        subject_key="bili:comment-author",
        approved_text="人工筛选效率低，人工确认的跟进文本",
        context_evidence="人工筛选效率低",
        source_url="https://www.bilibili.com/video/av1#reply1",
        source_link_opened=True,
    )
    first = workflow.register_outreach(
        **values, sent_at="2026-08-12T09:05:00Z"
    )
    follow_up = workflow.register_outreach(
        **values,
        sent_at="2026-08-13T09:05:00Z",
        parent_outreach_action_id=first,
    )

    with pytest.raises(ValueError, match="first contact"):
        workflow.register_outreach(
            **values,
            sent_at="2026-08-14T09:05:00Z",
            parent_outreach_action_id=follow_up,
        )


def test_response_interview_and_quote_preserve_fact_causality(facts):
    connection, _, workflow, run_id, signal_id = facts
    review_id, draft_id, _ = prepare_reviewed_draft(facts)
    outreach_id = workflow.register_outreach(
        run_id=run_id,
        signal_id=signal_id,
        review_id=review_id,
        draft_run_id=draft_id,
        platform="bili",
        subject_key="bili:comment-author",
        approved_text="人工筛选效率低，想了解你们的线索筛选流程",
        context_evidence="人工筛选效率低",
        sent_at="2026-08-12T09:05:00Z",
        source_url="https://www.bilibili.com/video/av1#reply1",
        source_link_opened=True,
    )
    response_id = workflow.register_response(
        run_id=run_id,
        outreach_action_id=outreach_id,
        responder_subject_key="bili:comment-author",
        response_type="VALID",
        summary="愿意进一步沟通",
        occurred_at="2026-08-12T10:00:00Z",
        verified_at="2026-08-12T10:01:00Z",
        evidence_summary="愿意进一步沟通",
    )
    interview_id = workflow.register_interview(
        run_id=run_id,
        response_event_id=response_id,
        scheduled_at="2026-08-13T02:00:00Z",
        completed_at="2026-08-13T02:30:00Z",
        summary={
            "customer_source_and_sales_process": "内容营销进入销售跟进",
            "weekly_lead_volume_and_loss_point": "每周二百条，筛选环节损失",
            "most_manual_step": "销售逐条判断",
            "current_tools": "CRM 和表格",
            "minimum_agent_scenario_and_decision_process": "先试排序，由负责人决策",
        },
        solution_fit="SOLVABLE",
        next_step="准备报价范围",
    )
    quote_id = workflow.register_quote(
        run_id=run_id,
        response_event_id=response_id,
        interview_id=interview_id,
        scope_summary="线索识别与人工复核试点",
        agreed_to_receive_pricing_at="2026-08-13T02:31:00Z",
        verified_at="2026-08-13T02:32:00Z",
    )

    row = connection.execute(
        "SELECT response_event_id, interview_id FROM quote_opportunities "
        "WHERE quote_opportunity_id = ?",
        (quote_id,),
    ).fetchone()
    assert tuple(row) == (response_id, interview_id)
