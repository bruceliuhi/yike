from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.db import connect, migrate
from app.metrics import MetricsEngine
from app.model_contract import ScoreDecision
from app.repository import NormalizedSignal, Repository
from app.workflow import Workflow
from tests.test_scoring import valid_decision


INTERVIEW_ANSWERS = {
    "customer_source_and_sales_process": "内容营销进入销售跟进",
    "weekly_lead_volume_and_loss_point": "每周 200 条，首轮筛选丢失最多",
    "most_manual_step": "销售逐条判断意图",
    "current_tools": "CRM 和表格",
    "minimum_agent_scenario_and_decision_process": "先试线索排序，由销售负责人决策",
}


class Clock:
    def __init__(self, value: datetime):
        self.value = value

    def __call__(self):
        return self.value

    def move(self, seconds: int):
        self.value += timedelta(seconds=seconds)

    def set(self, value: datetime):
        self.value = value


class FactBuilder:
    def __init__(self, database):
        self.connection = connect(database)
        migrate(self.connection)
        self.clock = Clock(datetime(2026, 8, 12, tzinfo=UTC))
        self.repository = Repository(self.connection, now=self.clock)
        self.run_id = self.repository.create_run(["bili", "dy"])
        self.repository.begin_collection(
            run_id=self.run_id,
            collection_run_id="metrics-provenance",
            platform="bili",
            query_cluster="sales-agent",
            query_text="销售线索",
            max_contents=1,
            max_comments_per_content=1,
            started_by="test-operator",
            runtime_lock_sha256="a" * 64,
        )
        self.repository.finish_collection(
            "metrics-provenance",
            state="SUCCEEDED",
            raw_count=320,
            unique_count=300,
            error_code=None,
        )
        self.clock.set(datetime(2026, 8, 20, tzinfo=UTC))
        self.workflow = Workflow(self.repository, now=self.clock)
        self.decision = ScoreDecision.model_validate(
            valid_decision(),
            context={
                "source_text": "销售获客讨论\n团队正在筛选销售线索，人工筛选效率低"
            },
        )

    def signal(self, index: int, *, platform: str = "bili") -> str:
        host = "www.bilibili.com" if platform == "bili" else "www.douyin.com"
        return self.repository.import_signal(
            self.run_id,
            NormalizedSignal(
                platform=platform,
                external_source_id=f"source-{platform}-{index}",
                source_title="销售获客讨论",
                source_url=f"https://{host}/video/source-{index}",
                external_comment_id=f"comment-{platform}-{index}",
                comment_url=f"https://{host}/video/source-{index}#reply-{index}",
                author_public_id=f"lead-{platform}-{index}",
                body="团队正在筛选销售线索，人工筛选效率低",
                raw_sha256="b" * 64,
                envelope_sha256="c" * 64,
                query_cluster="sales-agent",
                query_text="销售线索",
                collection_run_id="metrics-provenance",
                normalizer_version="test-normalizer-v1",
                verifiable=True,
            ),
        ).signal_id

    def review(self, signal_id: str, index: int, label: str = "HIGH_INTENT", seconds: int = 1):
        score_id = f"score-{uuid4()}"
        self.repository.append_score_success(
            score_run_id=score_id,
            run_id=self.run_id,
            signal_id=signal_id,
            provider="metrics-provider",
            model="metrics-model",
            prompt_version="score-v1",
            schema_version="schema-v1",
            decision=self.decision,
            token_usage=None,
        )
        self.workflow.present_score(self.run_id, signal_id, score_id)
        session_id = self.workflow.start_activity(self.run_id, signal_id, "REVIEW")
        self.clock.move(seconds)
        self.workflow.record_activity(session_id, "COMPLETE")
        return self.workflow.complete_review(
            run_id=self.run_id,
            signal_id=signal_id,
            label=label,
            reason="人工核验",
            note=None,
            activity_session_id=session_id,
        )

    def outreach(self, signal_id: str, review_id: str, index: int):
        session_id = self.workflow.start_activity(self.run_id, signal_id, "DRAFT")
        self.clock.move(1)
        self.workflow.record_activity(session_id, "COMPLETE")
        approved = "你提到人工筛选效率低。我们正在研究销售 Agent，你们每周筛选多少条线索？"
        draft_id = self.workflow.create_draft(
            run_id=self.run_id,
            signal_id=signal_id,
            body=approved,
            activity_session_id=session_id,
        )
        return self.workflow.register_outreach(
            run_id=self.run_id,
            signal_id=signal_id,
            review_id=review_id,
            draft_run_id=draft_id,
            platform="bili",
            subject_key=f"bili:lead-bili-{index}",
            approved_text=approved,
            context_evidence="人工筛选效率低",
            sent_at=self.clock().isoformat().replace("+00:00", "Z"),
            source_url=f"https://www.bilibili.com/video/source-{index}#reply-{index}",
            source_link_opened=True,
        )

    def response(self, outreach_id: str, index: int):
        now = self.clock().isoformat().replace("+00:00", "Z")
        return self.workflow.register_response(
            run_id=self.run_id,
            outreach_action_id=outreach_id,
            responder_subject_key=f"bili:lead-bili-{index}",
            response_type="VALID",
            summary="愿意继续沟通",
            occurred_at=now,
            verified_at=now,
            evidence_summary="我们每周约有 200 条线索",
        )

    def interview(self, response_id: str, solution_fit: str = "SOLVABLE"):
        now = self.clock().isoformat().replace("+00:00", "Z")
        return self.workflow.register_interview(
            run_id=self.run_id,
            response_event_id=response_id,
            scheduled_at=now,
            completed_at=now,
            summary=INTERVIEW_ANSWERS,
            solution_fit=solution_fit,
            next_step="试点",
        )

    def close(self):
        self.connection.close()


def test_full_persisted_success_thresholds_and_breakdowns_can_reach_proceed(tmp_path):
    facts = FactBuilder(tmp_path / "success.sqlite3")
    signals = [facts.signal(index) for index in range(300)]
    reviews = []
    for index, signal_id in enumerate(signals[:100]):
        facts.clock.set(datetime(2026, 8, 19 + index % 5, 1, index // 5, tzinfo=UTC))
        reviews.append(facts.review(signal_id, index))
    outreach = [
        facts.outreach(signals[index], reviews[index], index) for index in range(30)
    ]
    for index in range(30, 51):
        session_id = facts.workflow.start_activity(facts.run_id, signals[index], "DRAFT")
        facts.clock.move(1)
        facts.workflow.record_activity(session_id, "COMPLETE")
        facts.workflow.create_draft(
            run_id=facts.run_id,
            signal_id=signals[index],
            body="人工筛选效率低。我们正在研究销售 Agent，你们每周筛选多少条线索？",
            activity_session_id=session_id,
        )
    responses = [facts.response(outreach[index], index) for index in range(5)]
    interviews = [facts.interview(responses[index]) for index in range(2)]
    now = facts.clock().isoformat().replace("+00:00", "Z")
    facts.workflow.register_quote(
        run_id=facts.run_id,
        response_event_id=responses[0],
        interview_id=interviews[0],
        scope_summary="线索排序试点",
        agreed_to_receive_pricing_at=now,
        verified_at=now,
    )
    snapshot = MetricsEngine(facts.connection).calculate(
        facts.run_id, now=datetime(2026, 8, 27, tzinfo=UTC)
    )

    assert snapshot.all_success_thresholds is True
    assert snapshot.decision == "PROCEED_TO_V03_REVIEW"
    assert snapshot.time_complete is True
    assert snapshot.daily_time_within_limit is True
    assert snapshot.day8_12_median_seconds == 1
    assert snapshot.platform_breakdown["bili"]["signals"] == 300
    assert snapshot.platform_breakdown["bili"]["first_outreach"] == 30
    assert snapshot.platform_breakdown["bili"]["valid_responses"] == 5
    assert snapshot.platform_breakdown["bili"]["interviews"] == 2
    assert snapshot.platform_breakdown["bili"]["quotes"] == 1
    assert snapshot.industry_breakdown["B2B 销售"]["reviewed"] == 100
    assert snapshot.industry_breakdown["B2B 销售"]["high_intent"] == 100
    assert snapshot.industry_breakdown["B2B 销售"]["first_outreach"] == 30
    assert snapshot.industry_breakdown["B2B 销售"]["valid_responses"] == 5
    assert snapshot.collection_breakdown["SUCCEEDED"]["runs"] == 1
    assert snapshot.collection_breakdown["SUCCEEDED"]["raw"] == 320
    facts.close()


def test_all_six_loss_stop_rules_are_derived_from_persisted_facts(tmp_path):
    reasons_seen = set()
    for scenario in (
        "LOW_HIGH_INTENT",
        "LOW_VALID_RESPONSE",
        "NO_INTERVIEW",
        "NO_PERSONALIZED_CONTEXT",
        "THREE_OVER_90_MINUTE_DAYS",
        "UNSOLVABLE_INTERVIEW",
    ):
        facts = FactBuilder(tmp_path / f"{scenario}.sqlite3")
        count = {
            "LOW_HIGH_INTENT": 200,
            "LOW_VALID_RESPONSE": 30,
            "NO_INTERVIEW": 40,
            "NO_PERSONALIZED_CONTEXT": 20,
            "THREE_OVER_90_MINUTE_DAYS": 3,
            "UNSOLVABLE_INTERVIEW": 1,
        }[scenario]
        signals = [facts.signal(index) for index in range(count)]
        reviews = []
        for index, signal_id in enumerate(signals):
            if scenario == "THREE_OVER_90_MINUTE_DAYS":
                facts.clock.set(datetime(2026, 8, 13 + index, 1, tzinfo=UTC))
            label = "NOT_LEAD" if scenario == "LOW_HIGH_INTENT" else "HIGH_INTENT"
            seconds = 5401 if scenario == "THREE_OVER_90_MINUTE_DAYS" else 1
            reviews.append(facts.review(signal_id, index, label=label, seconds=seconds))

        outreach = []
        if scenario in {
            "LOW_VALID_RESPONSE", "NO_INTERVIEW",
            "UNSOLVABLE_INTERVIEW",
        }:
            outreach = [
                facts.outreach(signals[index], reviews[index], index)
                for index in range(count)
            ]
        if scenario == "LOW_VALID_RESPONSE":
            for index in range(2):
                facts.response(outreach[index], index)
        if scenario == "UNSOLVABLE_INTERVIEW":
            response_id = facts.response(outreach[0], 0)
            facts.interview(response_id, solution_fit="UNSOLVABLE")

        snapshot = MetricsEngine(facts.connection).calculate(
            facts.run_id, now=datetime(2026, 8, 25, tzinfo=UTC)
        )
        assert snapshot.loss_stop is True
        assert snapshot.decision == "STOP_DISCOVERY"
        reasons_seen.update(snapshot.loss_stop_reasons)
        facts.close()

    assert reasons_seen == {
        "LOW_HIGH_INTENT",
        "LOW_VALID_RESPONSE",
        "NO_INTERVIEW",
        "NO_PERSONALIZED_CONTEXT",
        "THREE_OVER_90_MINUTE_DAYS",
        "UNSOLVABLE_INTERVIEW",
    }

    spaced = FactBuilder(tmp_path / "nonconsecutive.sqlite3")
    for index, day in enumerate((13, 15, 17)):
        signal_id = spaced.signal(index)
        spaced.clock.set(datetime(2026, 8, day, 1, tzinfo=UTC))
        spaced.review(signal_id, index, seconds=5401)
    spaced_snapshot = MetricsEngine(spaced.connection).calculate(
        spaced.run_id, now=datetime(2026, 8, 25, tzinfo=UTC)
    )
    assert "THREE_OVER_90_MINUTE_DAYS" not in spaced_snapshot.loss_stop_reasons
    spaced.close()


def test_current_leaf_and_valid_evidence_are_the_only_quality_and_business_facts(tmp_path):
    facts = FactBuilder(tmp_path / "leaf.sqlite3")
    signal_id = facts.signal(1)
    first_review = facts.review(signal_id, 1, label="HIGH_INTENT")
    revision_session = facts.workflow.start_activity(facts.run_id, signal_id, "REVIEW")
    facts.clock.move(1)
    facts.workflow.record_activity(revision_session, "COMPLETE")
    current_review = facts.workflow.complete_review(
        run_id=facts.run_id,
        signal_id=signal_id,
        label="NOT_LEAD",
        reason="复核后排除",
        note=None,
        activity_session_id=revision_session,
        supersedes_review_id=first_review,
    )
    facts.clock.set(datetime(2026, 8, 27, tzinfo=UTC))
    with pytest.raises(ValueError, match="Day 14"):
        facts.workflow.start_activity(facts.run_id, signal_id, "REVIEW")

    snapshot = MetricsEngine(facts.connection).calculate(
        facts.run_id, now=datetime(2026, 8, 28, tzinfo=UTC)
    )

    assert snapshot.reviewed_signals == 1
    assert snapshot.reviewed_ab == 1
    assert snapshot.high_intent_ab == 0
    assert snapshot.precision == 0.0
    assert snapshot.valid_response_subjects == 0
    facts.close()


def test_open_activity_fails_time_gate_and_later_collection_success_resolves_block(tmp_path):
    facts = FactBuilder(tmp_path / "recovery.sqlite3")
    signal_id = facts.signal(1)
    facts.workflow.start_activity(facts.run_id, signal_id, "REVIEW")
    facts.repository.begin_collection(
        run_id=facts.run_id,
        collection_run_id="blocked-attempt",
        platform="bili",
        query_cluster="sales-agent",
        query_text="销售线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )
    facts.repository.finish_collection(
        "blocked-attempt", state="BLOCKED_INPUT", raw_count=0,
        unique_count=0, error_code="PLATFORM_AUTH_REQUIRED",
    )
    facts.repository.begin_collection(
        run_id=facts.run_id,
        collection_run_id="recovered-attempt",
        platform="bili",
        query_cluster="sales-agent",
        query_text="销售线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )
    facts.repository.finish_collection(
        "recovered-attempt", state="SUCCEEDED", raw_count=1,
        unique_count=1, error_code=None,
    )

    snapshot = MetricsEngine(facts.connection).calculate(
        facts.run_id, now=datetime(2026, 8, 25, tzinfo=UTC)
    )

    assert snapshot.time_complete is False
    assert snapshot.blocked_input is False
    facts.close()


def test_model_availability_recovery_uses_one_cross_table_sequence(tmp_path):
    facts = FactBuilder(tmp_path / "model-order.sqlite3")
    signal_id = facts.signal(1)
    facts.repository.append_draft_failure(
        draft_run_id="draft-blocked", run_id=facts.run_id,
        signal_id=signal_id, provider=None, model=None,
        prompt_version="draft-v1", error_code="MODEL_NOT_CONFIGURED",
    )
    facts.repository.append_score_success(
        score_run_id="score-recovered", run_id=facts.run_id,
        signal_id=signal_id, provider="provider", model="model",
        prompt_version="score-v1", schema_version="schema-v1",
        decision=facts.decision, token_usage=None,
    )

    recovered = MetricsEngine(facts.connection).calculate(
        facts.run_id, now=facts.clock()
    )
    assert recovered.blocked_input is False

    facts.repository.append_draft_failure(
        draft_run_id="draft-blocked-again", run_id=facts.run_id,
        signal_id=signal_id, provider=None, model=None,
        prompt_version="draft-v1", error_code="MODEL_UNAVAILABLE",
    )
    blocked_again = MetricsEngine(facts.connection).calculate(
        facts.run_id, now=facts.clock()
    )
    assert blocked_again.blocked_input is True
    facts.close()
