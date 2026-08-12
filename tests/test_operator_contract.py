from datetime import UTC, datetime
import sqlite3

import pytest

from app.db import connect, migrate
from app.repository import NormalizedSignal, Repository
from app.scorer import Scorer
from app.workflow import Workflow
from tests.test_scoring import valid_decision


class Clock:
    def __init__(self, value: str):
        self.value = datetime.fromisoformat(value.replace("Z", "+00:00"))

    def __call__(self) -> datetime:
        return self.value

    def set(self, value: str) -> None:
        self.value = datetime.fromisoformat(value.replace("Z", "+00:00"))


class SuccessfulClient:
    provider = "openai-compatible"
    model = "test-model"

    def complete(self, *, source_text):
        return valid_decision(), {"total_tokens": 12}


@pytest.fixture
def operator_facts(tmp_path):
    connection = connect(tmp_path / "operator.sqlite3")
    migrate(connection)
    repository = Repository(connection)
    run_id = repository.create_run(["bili", "dy"])
    signal_id = repository.import_signal(
        run_id,
        NormalizedSignal(
            platform="bili",
            external_source_id="av-operator",
            source_title="销售获客讨论",
            source_url="https://www.bilibili.com/video/av-operator",
            external_comment_id="comment-operator",
            parent_body="团队想改善获客流程",
            comment_url="https://www.bilibili.com/video/av-operator#reply",
            author_public_id="lead-operator",
            body="团队正在筛选销售线索，人工筛选效率低",
        ),
    ).signal_id
    scored = Scorer(repository, SuccessfulClient()).score(run_id, signal_id)
    workflow = Workflow(repository)
    workflow.present_score(run_id, signal_id, scored.score_run_id)
    yield connection, repository, run_id, signal_id, scored.score_run_id
    connection.close()


def _completed_session(workflow, run_id, signal_id, kind):
    session_id = workflow.start_activity(run_id, signal_id, kind)
    workflow.record_activity(session_id, "COMPLETE")
    return session_id


def test_activity_replays_server_received_events_and_excludes_idle_tail(operator_facts):
    connection, repository, run_id, signal_id, _ = operator_facts
    clock = Clock("2026-08-12T01:00:00Z")
    workflow = Workflow(repository, now=clock)

    session_id = workflow.start_activity(run_id, signal_id, "REVIEW")
    clock.set("2026-08-12T01:02:00Z")
    workflow.record_activity(session_id, "PAUSE_IDLE")
    clock.set("2026-08-12T01:03:00Z")
    workflow.record_activity(session_id, "RESUME")
    clock.set("2026-08-12T01:03:30Z")
    completed = workflow.record_activity(session_id, "COMPLETE")
    review_id = workflow.complete_review(
        run_id=run_id,
        signal_id=signal_id,
        label="HIGH_INTENT",
        reason="企业意图明确",
        note=None,
        activity_session_id=session_id,
    )

    assert completed.active_seconds == 90
    events = connection.execute(
        "SELECT event_kind, received_at FROM activity_events "
        "WHERE activity_session_id = ? ORDER BY sequence_no",
        (session_id,),
    ).fetchall()
    assert [tuple(row) for row in events] == [
        ("START", "2026-08-12T01:00:00Z"),
        ("PAUSE_IDLE", "2026-08-12T01:02:00Z"),
        ("RESUME", "2026-08-12T01:03:00Z"),
        ("COMPLETE", "2026-08-12T01:03:30Z"),
    ]
    review = connection.execute(
        "SELECT activity_session_id, started_at, completed_at, active_seconds "
        "FROM human_reviews WHERE review_id = ?",
        (review_id,),
    ).fetchone()
    assert tuple(review) == (
        session_id,
        "2026-08-12T01:00:00Z",
        "2026-08-12T01:03:30Z",
        90,
    )


def test_activity_invalid_transition_and_second_open_session_fail_closed(operator_facts):
    connection, repository, run_id, signal_id, _ = operator_facts
    workflow = Workflow(repository)
    session_id = workflow.start_activity(run_id, signal_id, "DRAFT")

    assert workflow.start_activity(run_id, signal_id, "DRAFT") == session_id
    with pytest.raises(sqlite3.IntegrityError, match="ACTIVITY_MUST_START_OPEN"):
        connection.execute(
            """
            INSERT INTO activity_sessions (
                activity_session_id, mvp_run_id, signal_id, activity_kind,
                state, started_at, completed_at, active_seconds
            ) VALUES ('forged-terminal', ?, ?, 'REVIEW', 'COMPLETED',
                      '2026-08-12T00:00:00Z', '2026-08-12T00:01:00Z', 60)
            """,
            (run_id, signal_id),
        )
    with pytest.raises(sqlite3.IntegrityError, match="ACTIVITY_EVENT_INVALID_TRANSITION"):
        connection.execute(
            """
            INSERT INTO activity_events (
                activity_event_id, activity_session_id, mvp_run_id, signal_id,
                activity_kind, sequence_no, event_kind, received_at
            ) VALUES ('forged-resume', ?, ?, ?, 'DRAFT', 2, 'RESUME',
                      '2026-08-12T00:01:00Z')
            """,
            (session_id, run_id, signal_id),
        )
    with pytest.raises(sqlite3.IntegrityError, match="ACTIVITY_STATE_EVENT_REQUIRED"):
        connection.execute(
            "UPDATE activity_sessions SET state = 'PAUSED' "
            "WHERE activity_session_id = ?",
            (session_id,),
        )
    with pytest.raises(ValueError, match="transition"):
        workflow.record_activity(session_id, "RESUME")

    with pytest.raises(
        sqlite3.IntegrityError,
        match="ACTIVITY_(TERMINAL_EVENT_REQUIRED|SUMMARY_MISMATCH)",
    ):
        connection.execute(
            """
            UPDATE activity_sessions SET state = 'COMPLETED',
              completed_at = '2026-08-12T23:59:59Z', active_seconds = 999999
            WHERE activity_session_id = ?
            """,
            (session_id,),
        )

    workflow.record_activity(session_id, "CANCEL")
    replacement = workflow.start_activity(run_id, signal_id, "DRAFT")
    assert replacement != session_id


def test_review_and_human_draft_require_completed_matching_sessions(operator_facts):
    connection, repository, run_id, signal_id, _ = operator_facts
    workflow = Workflow(repository)
    review_session = workflow.start_activity(run_id, signal_id, "REVIEW")

    with pytest.raises(ValueError, match="completed REVIEW"):
        workflow.complete_review(
            run_id=run_id,
            signal_id=signal_id,
            label="POSSIBLE",
            reason="需确认",
            note=None,
            activity_session_id=review_session,
        )

    workflow.record_activity(review_session, "COMPLETE")
    review_id = workflow.complete_review(
        run_id=run_id,
        signal_id=signal_id,
        label="HIGH_INTENT",
        reason="企业意图明确",
        note=None,
        activity_session_id=review_session,
    )
    draft_session = _completed_session(workflow, run_id, signal_id, "DRAFT")
    draft_id = workflow.create_draft(
        run_id=run_id,
        signal_id=signal_id,
        body="你提到人工筛选效率低。想了解你们每周筛选多少条线索？",
        activity_session_id=draft_session,
    )

    assert tuple(connection.execute(
        "SELECT draft_kind, activity_session_id FROM draft_runs WHERE draft_run_id = ?",
        (draft_id,),
    ).fetchone()) == ("HUMAN_EDITED", draft_session)
    assert review_id


def test_outreach_requires_current_leaf_equal_score_and_verbatim_context(operator_facts):
    connection, repository, run_id, signal_id, score_run_id = operator_facts
    workflow = Workflow(repository)
    review_session = _completed_session(workflow, run_id, signal_id, "REVIEW")
    review_id = workflow.complete_review(
        run_id=run_id,
        signal_id=signal_id,
        label="HIGH_INTENT",
        reason="明确",
        note=None,
        activity_session_id=review_session,
    )
    draft_session = _completed_session(workflow, run_id, signal_id, "DRAFT")
    approved = "你提到人工筛选效率低。我们在研究 B2B 销售 Agent，你们每周筛选多少条线索？"
    draft_id = workflow.create_draft(
        run_id=run_id,
        signal_id=signal_id,
        body=approved,
        activity_session_id=draft_session,
    )

    with pytest.raises(ValueError, match="verbatim"):
        workflow.register_outreach(
            run_id=run_id,
            signal_id=signal_id,
            review_id=review_id,
            draft_run_id=draft_id,
            platform="bili",
            subject_key="bili:lead-operator",
            approved_text=approved,
            context_evidence="不存在的原文",
            sent_at="2026-08-12T09:00:00Z",
            source_url="https://www.bilibili.com/video/av-operator#reply",
            source_link_opened=True,
        )

    outreach_id = workflow.register_outreach(
        run_id=run_id,
        signal_id=signal_id,
        review_id=review_id,
        draft_run_id=draft_id,
        platform="bili",
        subject_key="bili:lead-operator",
        approved_text=approved,
        context_evidence="人工筛选效率低",
        sent_at="2026-08-12T09:00:00Z",
        source_url="https://www.bilibili.com/video/av-operator#reply",
        source_link_opened=True,
    )
    row = connection.execute(
        "SELECT score_run_id, context_evidence FROM outreach_actions "
        "WHERE outreach_action_id = ?",
        (outreach_id,),
    ).fetchone()
    assert tuple(row) == (score_run_id, "人工筛选效率低")

    revision_session = _completed_session(workflow, run_id, signal_id, "REVIEW")
    workflow.complete_review(
        run_id=run_id,
        signal_id=signal_id,
        label="NOT_LEAD",
        reason="重新核验",
        note=None,
        activity_session_id=revision_session,
        supersedes_review_id=review_id,
    )
    with pytest.raises(ValueError, match="current leaf"):
        workflow.register_outreach(
            run_id=run_id,
            signal_id=signal_id,
            review_id=review_id,
            draft_run_id=draft_id,
            platform="bili",
            subject_key="bili:lead-operator",
            approved_text=approved,
            context_evidence="人工筛选效率低",
            sent_at="2026-08-13T02:00:00Z",
            source_url="https://www.bilibili.com/video/av-operator#reply",
            source_link_opened=True,
            parent_outreach_action_id=outreach_id,
        )


def test_follow_up_cannot_predate_its_root_contact(operator_facts):
    connection, repository, run_id, signal_id, _ = operator_facts
    workflow = Workflow(repository)
    review_session = _completed_session(workflow, run_id, signal_id, "REVIEW")
    review_id = workflow.complete_review(
        run_id=run_id, signal_id=signal_id, label="HIGH_INTENT", reason="明确",
        note=None, activity_session_id=review_session,
    )
    draft_session = _completed_session(workflow, run_id, signal_id, "DRAFT")
    approved = "你提到人工筛选效率低。我们在研究销售 Agent，你们每周筛选多少条线索？"
    draft_id = workflow.create_draft(
        run_id=run_id, signal_id=signal_id, body=approved,
        activity_session_id=draft_session,
    )
    root = workflow.register_outreach(
        run_id=run_id, signal_id=signal_id, review_id=review_id,
        draft_run_id=draft_id, platform="bili",
        subject_key="bili:lead-operator", approved_text=approved,
        context_evidence="人工筛选效率低",
        sent_at="2026-08-13T12:00:00Z",
        source_url="https://www.bilibili.com/video/av-operator#reply",
        source_link_opened=True,
    )

    values = (
        run_id, signal_id, review_id, draft_id, root,
    )
    with pytest.raises(ValueError, match="first contact"):
        workflow.register_outreach(
            run_id=run_id, signal_id=signal_id, review_id=review_id,
            draft_run_id=draft_id, platform="bili",
            subject_key="bili:lead-operator", approved_text=approved,
            context_evidence="人工筛选效率低",
            sent_at="2026-08-13T11:00:00Z",
            source_url="https://www.bilibili.com/video/av-operator#reply",
            source_link_opened=True, parent_outreach_action_id=root,
        )
    with pytest.raises(sqlite3.IntegrityError, match="OUTREACH_TIME_CAUSALITY"):
        connection.execute(
            """
            INSERT INTO outreach_actions (
                outreach_action_id, mvp_run_id, signal_id, review_id,
                score_run_id, draft_run_id, platform, subject_key,
                approved_text, sent_at, source_url, context_evidence,
                evidence_summary, source_link_opened, status,
                parent_outreach_action_id, created_at
            ) VALUES ('backdated-follow-up', ?, ?, ?,
                      (SELECT presented_score_run_id FROM human_reviews WHERE review_id = ?),
                      ?, 'bili', 'bili:lead-operator', ?,
                      '2026-08-13T11:00:00Z',
                      'https://www.bilibili.com/video/av-operator#reply',
                      '人工筛选效率低', '人工筛选效率低', 1,
                      'SENT_VERIFIED', ?, '2026-08-13T13:00:00Z')
            """,
            (values[0], values[1], values[2], values[2], values[3], approved, values[4]),
        )


def test_workflow_rejects_post_day14_backfill_and_open_activity_events(tmp_path):
    connection = connect(tmp_path / "late-operator.sqlite3")
    migrate(connection)
    clock = Clock("2026-08-12T00:00:00Z")
    repository = Repository(connection, now=clock)
    run_id = repository.create_run(["bili", "dy"])
    signal_id = repository.import_signal(
        run_id,
        NormalizedSignal(
            platform="bili", external_source_id="late-source",
            source_url="https://www.bilibili.com/video/late-source",
            external_comment_id="late-comment",
            comment_url="https://www.bilibili.com/video/late-source#reply",
            author_public_id="late-lead",
            body="团队正在筛选销售线索，人工筛选效率低",
        ),
    ).signal_id
    score = Scorer(repository, SuccessfulClient()).score(run_id, signal_id)
    workflow = Workflow(repository, now=clock)
    workflow.present_score(run_id, signal_id, score.score_run_id)
    review_session = _completed_session(workflow, run_id, signal_id, "REVIEW")
    review_id = workflow.complete_review(
        run_id=run_id, signal_id=signal_id, label="HIGH_INTENT",
        reason="明确", note=None, activity_session_id=review_session,
    )
    draft_session = _completed_session(workflow, run_id, signal_id, "DRAFT")
    approved = "你提到人工筛选效率低。我们在研究销售 Agent，你们每周筛选多少条线索？"
    draft_id = workflow.create_draft(
        run_id=run_id, signal_id=signal_id, body=approved,
        activity_session_id=draft_session,
    )
    root = workflow.register_outreach(
        run_id=run_id, signal_id=signal_id, review_id=review_id,
        draft_run_id=draft_id, platform="bili", subject_key="bili:late-lead",
        approved_text=approved, context_evidence="人工筛选效率低",
        sent_at="2026-08-12T01:00:00Z",
        source_url="https://www.bilibili.com/video/late-source#reply",
        source_link_opened=True,
    )
    dangling = workflow.start_activity(run_id, signal_id, "REVIEW")
    clock.set("2026-08-27T00:00:00Z")

    with pytest.raises(ValueError, match="Day 14"):
        workflow.record_activity(dangling, "COMPLETE")
    with pytest.raises(ValueError, match="Day 14"):
        workflow.start_activity(run_id, signal_id, "DRAFT")
    with pytest.raises(ValueError, match="Day 14"):
        workflow.present_score(run_id, signal_id, score.score_run_id)
    with pytest.raises(ValueError, match="Day 14"):
        workflow.register_outreach(
            run_id=run_id, signal_id=signal_id, review_id=review_id,
            draft_run_id=draft_id, platform="bili", subject_key="bili:late-lead",
            approved_text=approved, context_evidence="人工筛选效率低",
            sent_at="2026-08-13T01:00:00Z",
            source_url="https://www.bilibili.com/video/late-source#reply",
            source_link_opened=True, parent_outreach_action_id=root,
        )
    with pytest.raises(ValueError, match="Day 14"):
        workflow.register_response(
            run_id=run_id, outreach_action_id=root,
            responder_subject_key="bili:late-lead", response_type="VALID",
            summary="愿意沟通", occurred_at="2026-08-13T02:00:00Z",
            verified_at="2026-08-13T02:01:00Z", evidence_summary="愿意继续",
        )

    assert connection.execute(
        "SELECT state FROM activity_sessions WHERE activity_session_id = ?",
        (dangling,),
    ).fetchone()[0] == "OPEN"
    assert connection.execute(
        "SELECT count(*) FROM activity_events WHERE activity_session_id = ?",
        (dangling,),
    ).fetchone()[0] == 1
    assert connection.execute(
        "SELECT count(*) FROM outreach_actions WHERE mvp_run_id = ?", (run_id,)
    ).fetchone()[0] == 1
    assert connection.execute(
        "SELECT count(*) FROM response_events WHERE mvp_run_id = ?", (run_id,)
    ).fetchone()[0] == 0
    connection.close()


def test_valid_response_interview_and_quote_require_governed_evidence_chain(operator_facts):
    _, repository, run_id, signal_id, _ = operator_facts
    workflow = Workflow(repository)
    review_session = _completed_session(workflow, run_id, signal_id, "REVIEW")
    review_id = workflow.complete_review(
        run_id=run_id, signal_id=signal_id, label="HIGH_INTENT", reason="明确",
        note=None, activity_session_id=review_session,
    )
    draft_session = _completed_session(workflow, run_id, signal_id, "DRAFT")
    approved = "你提到人工筛选效率低。我们在研究销售 Agent，你们每周筛选多少条线索？"
    draft_id = workflow.create_draft(
        run_id=run_id, signal_id=signal_id, body=approved,
        activity_session_id=draft_session,
    )
    outreach_id = workflow.register_outreach(
        run_id=run_id, signal_id=signal_id, review_id=review_id,
        draft_run_id=draft_id, platform="bili", subject_key="bili:lead-operator",
        approved_text=approved, context_evidence="人工筛选效率低",
        sent_at="2026-08-12T09:00:00Z",
        source_url="https://www.bilibili.com/video/av-operator#reply",
        source_link_opened=True,
    )

    with pytest.raises(ValueError, match="evidence"):
        workflow.register_response(
            run_id=run_id, outreach_action_id=outreach_id,
            responder_subject_key="bili:lead-operator", response_type="VALID",
            summary="愿意沟通", occurred_at="2026-08-12T10:00:00Z",
            verified_at="2026-08-12T10:01:00Z", evidence_summary="",
        )
    invalid_id = workflow.register_response(
        run_id=run_id, outreach_action_id=outreach_id,
        responder_subject_key="bili:lead-operator", response_type="INVALID",
        summary="只有表情", occurred_at="2026-08-12T10:00:00Z",
        verified_at="2026-08-12T10:01:00Z", evidence_summary=None,
    )
    with pytest.raises(ValueError, match="VALID"):
        workflow.register_quote(
            run_id=run_id, response_event_id=invalid_id, interview_id=None,
            scope_summary="试点", agreed_to_receive_pricing_at="2026-08-12T10:10:00Z",
            verified_at="2026-08-12T10:11:00Z",
        )

    response_id = workflow.register_response(
        run_id=run_id, outreach_action_id=outreach_id,
        responder_subject_key="bili:lead-operator", response_type="VALID",
        summary="说明了现有流程并愿意继续", occurred_at="2026-08-12T10:00:00Z",
        verified_at="2026-08-12T10:01:00Z", evidence_summary="我们每周约有 200 条线索",
    )
    answers = {
        "customer_source_and_sales_process": "内容营销进入销售跟进",
        "weekly_lead_volume_and_loss_point": "每周 200 条，首轮筛选丢失最多",
        "most_manual_step": "销售逐条判断意图",
        "current_tools": "CRM 和表格",
        "minimum_agent_scenario_and_decision_process": "先试线索排序，由销售负责人决策",
    }
    with pytest.raises(ValueError, match="exactly five"):
        workflow.register_interview(
            run_id=run_id, response_event_id=response_id,
            scheduled_at="2026-08-13T01:00:00Z", completed_at="2026-08-13T01:30:00Z",
            summary={"customer_source_and_sales_process": "内容营销"},
            solution_fit="SOLVABLE", next_step="试点",
        )
    interview_id = workflow.register_interview(
        run_id=run_id, response_event_id=response_id,
        scheduled_at="2026-08-13T01:00:00Z", completed_at="2026-08-13T01:30:00Z",
        summary=answers, solution_fit="SOLVABLE", next_step="试点",
    )
    quote_id = workflow.register_quote(
        run_id=run_id, response_event_id=response_id, interview_id=interview_id,
        scope_summary="线索识别试点", agreed_to_receive_pricing_at="2026-08-13T01:31:00Z",
        verified_at="2026-08-13T01:32:00Z",
    )
    assert quote_id


def test_sql_rejects_outreach_score_mismatch_even_outside_workflow(operator_facts):
    connection, repository, run_id, signal_id, score_run_id = operator_facts
    workflow = Workflow(repository)
    review_session = _completed_session(workflow, run_id, signal_id, "REVIEW")
    review_id = workflow.complete_review(
        run_id=run_id, signal_id=signal_id, label="HIGH_INTENT", reason="明确",
        note=None, activity_session_id=review_session,
    )
    other_score = Scorer(repository, SuccessfulClient()).score(run_id, signal_id).score_run_id
    draft_session = _completed_session(workflow, run_id, signal_id, "DRAFT")
    draft_id = workflow.create_draft(
        run_id=run_id, signal_id=signal_id,
        body="人工筛选效率低。我们在研究销售 Agent，你们每周处理多少条？",
        activity_session_id=draft_session,
    )

    assert other_score != score_run_id
    with pytest.raises(sqlite3.IntegrityError, match="OUTREACH_SCORE_REVIEW_MISMATCH"):
        connection.execute(
            """
            INSERT INTO outreach_actions (
              outreach_action_id, mvp_run_id, signal_id, review_id, score_run_id,
              draft_run_id, platform, subject_key, approved_text, context_evidence,
              sent_at, source_url, evidence_summary, source_link_opened, status, created_at
            ) VALUES ('sql-mismatch', ?, ?, ?, ?, ?, 'bili', 'bili:lead-operator',
                      '人工筛选效率低。请问每周多少条？', '人工筛选效率低',
                      '2026-08-12T05:00:00Z',
                      'https://www.bilibili.com/video/av-operator#reply',
                      '人工筛选效率低', 1, 'SENT_VERIFIED',
                      '2026-08-12T05:00:00Z')
            """,
            (run_id, signal_id, review_id, other_score, draft_id),
        )
