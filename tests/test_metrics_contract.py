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
    def __init__(self, database, *, backend="MEDIACRAWLER_AUTHORIZED"):
        self.connection = connect(database)
        migrate(self.connection)
        self.clock = Clock(datetime(2026, 8, 12, tzinfo=UTC))
        self.repository = Repository(self.connection, now=self.clock)
        self.run_id = self.repository.create_run(["bili", "dy"])
        self.repository.begin_collection(
            run_id=self.run_id,
            collection_run_id="metrics-provenance",
            backend=backend,
            platform="bili",
            query_cluster="sales-agent",
            query_text="销售线索",
            max_contents=10,
            max_comments_per_content=50,
            started_by="test-operator",
            runtime_lock_sha256="a" * 64,
        )
        self.workflow = Workflow(self.repository, now=self.clock)
        self.decision = ScoreDecision.model_validate(
            valid_decision(),
            context={
                "source_text": "销售获客讨论\n团队正在筛选销售线索，人工筛选效率低"
            },
        )

    def signal_item(
        self,
        index: int,
        *,
        platform: str = "bili",
        collection_run_id: str = "metrics-provenance",
    ) -> NormalizedSignal:
        host = "www.bilibili.com" if platform == "bili" else "www.douyin.com"
        source_index = index % 10
        return NormalizedSignal(
            platform=platform,
            external_source_id=f"source-{platform}-{source_index}",
            source_title="销售获客讨论",
            source_url=f"https://{host}/video/source-{source_index}",
            source_author_public_id=f"source-author-{platform}-{source_index}",
            external_comment_id=f"comment-{platform}-{index}",
            comment_url=f"https://{host}/video/source-{source_index}#reply-{index}",
            author_public_id=f"lead-{platform}-{index}",
            body="团队正在筛选销售线索，人工筛选效率低",
            raw_sha256="b" * 64,
            envelope_sha256="c" * 64,
            query_cluster="sales-agent",
            query_text="销售线索",
            collection_run_id=collection_run_id,
            normalizer_version="test-normalizer-v1",
            verifiable=True,
        )

    def collect_signals(
        self,
        indices,
        *,
        collection_run_id: str = "metrics-provenance",
        platform: str = "bili",
        duplicate_count: int = 0,
        manifest_sha256: str = "d" * 64,
    ) -> list[str]:
        indices = list(indices)
        items = [
            self.signal_item(
                index,
                platform=platform,
                collection_run_id=collection_run_id,
            )
            for index in indices
        ]
        if duplicate_count:
            if duplicate_count > len(items):
                raise ValueError("fixture duplicate count exceeds batch size")
            items.extend(items[:duplicate_count])
        collection = self.connection.execute(
            """
            SELECT collection.platform, collection.backend,
                   campaign.query_cluster, campaign.query_text,
                   campaign.max_contents, campaign.max_comments_per_content
            FROM collection_runs collection
            JOIN campaigns campaign
              ON campaign.campaign_id = collection.campaign_id
             AND campaign.mvp_run_id = collection.mvp_run_id
             AND campaign.platform = collection.platform
            WHERE collection.collection_run_id = ?
            """,
            (collection_run_id,),
        ).fetchone()
        if collection is None:
            raise KeyError(collection_run_id)
        self.repository.advance_collection_state(collection_run_id, "RUNNING")
        self.repository.advance_collection_state(collection_run_id, "IMPORTING")
        results = self.repository.complete_collection_success(
            collection_run_id=collection_run_id,
            run_id=self.run_id,
            platform=collection["platform"],
            backend=collection["backend"],
            query_cluster=collection["query_cluster"],
            query_text=collection["query_text"],
            max_contents=collection["max_contents"],
            max_comments_per_content=collection["max_comments_per_content"],
            items=items,
            raw_count=len(items),
            output_manifest_sha256=manifest_sha256,
        )
        self.clock.move(1)
        return [result.signal_id for result in results[: len(indices)]]

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

    def outreach(
        self, signal_id: str, review_id: str, index: int, *, seconds: int = 1
    ):
        session_id = self.workflow.start_activity(self.run_id, signal_id, "DRAFT")
        self.clock.move(seconds)
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
            source_url=(
                f"https://www.bilibili.com/video/source-{index % 10}#reply-{index}"
            ),
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

    def finish_collection(self):
        state = self.connection.execute(
            "SELECT state FROM collection_runs "
            "WHERE collection_run_id = 'metrics-provenance'"
        ).fetchone()[0]
        assert state in ("SUCCEEDED", "SUCCEEDED_NO_DATA")

    def snapshot(self, now: datetime):
        return MetricsEngine(self.connection).calculate(self.run_id, now=now)


def test_full_persisted_success_thresholds_and_breakdowns_can_reach_proceed(tmp_path):
    facts = FactBuilder(tmp_path / "success.sqlite3")
    signals = facts.collect_signals(range(300), duplicate_count=20)
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
    snapshot = facts.snapshot(datetime(2026, 8, 27, tzinfo=UTC))

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


def test_simulation_only_reviews_cannot_trigger_a_loss_stop(tmp_path):
    facts = FactBuilder(
        tmp_path / "simulation-loss.sqlite3", backend="SIMULATION_ONLY"
    )
    signals = facts.collect_signals(range(200))
    for index, signal_id in enumerate(signals):
        facts.review(signal_id, index, label="NOT_LEAD")

    snapshot = facts.snapshot(datetime(2026, 8, 25, tzinfo=UTC))

    assert snapshot.unique_verifiable_signals == 0
    assert snapshot.reviewed_signals == 0
    assert snapshot.reviewed_ab == 0
    assert snapshot.loss_stop is False
    assert snapshot.decision == "RUNNING"
    assert snapshot.platform_breakdown["bili"]["reviewed"] == 0
    assert snapshot.industry_breakdown == {}
    assert snapshot.collection_breakdown == {}
    facts.close()


def test_simulation_only_funnel_cannot_complete_authorized_signal_success(
    tmp_path,
):
    facts = FactBuilder(tmp_path / "simulation-success.sqlite3")
    authorized = facts.collect_signals(range(300), duplicate_count=20)
    facts.finish_collection()
    facts.clock.set(datetime(2026, 8, 13, tzinfo=UTC))
    facts.repository.begin_collection(
        run_id=facts.run_id,
        collection_run_id="simulation-funnel",
        backend="SIMULATION_ONLY",
        platform="bili",
        query_cluster="sales-agent",
        query_text="销售线索",
        max_contents=10,
        max_comments_per_content=50,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )
    simulated = facts.collect_signals(
        range(1000, 1100),
        collection_run_id="simulation-funnel",
        manifest_sha256="e" * 64,
    )
    reviews = []
    for index, signal_id in enumerate(simulated):
        facts.clock.set(datetime(2026, 8, 19 + index % 5, 1, index // 5, tzinfo=UTC))
        reviews.append(facts.review(signal_id, index))
    outreach = [
        facts.outreach(simulated[index], reviews[index], index + 1000)
        for index in range(30)
    ]
    for index in range(30, 51):
        session_id = facts.workflow.start_activity(
            facts.run_id, simulated[index], "DRAFT"
        )
        facts.clock.move(1)
        facts.workflow.record_activity(session_id, "COMPLETE")
        facts.workflow.create_draft(
            run_id=facts.run_id,
            signal_id=simulated[index],
            body="人工筛选效率低。我们正在研究销售 Agent，你们每周筛选多少条线索？",
            activity_session_id=session_id,
        )
    responses = [
        facts.response(outreach[index], index + 1000) for index in range(5)
    ]
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
    snapshot = facts.snapshot(datetime(2026, 8, 25, tzinfo=UTC))

    assert len(authorized) == snapshot.unique_verifiable_signals == 300
    assert snapshot.reviewed_signals == 0
    assert snapshot.first_outreach_subjects == 0
    assert snapshot.valid_response_subjects == 0
    assert snapshot.completed_interviews == 0
    assert snapshot.verified_quotes == 0
    assert snapshot.all_success_thresholds is False
    assert snapshot.decision == "RUNNING"
    assert snapshot.platform_breakdown["bili"]["first_outreach"] == 0
    assert snapshot.industry_breakdown == {}
    assert snapshot.collection_breakdown["SUCCEEDED"] == {
        "runs": 1,
        "raw": 320,
        "unique": 300,
    }
    facts.close()


def test_later_authorized_observation_cannot_promote_earlier_simulation_funnel(
    tmp_path,
):
    facts = FactBuilder(
        tmp_path / "simulation-retroactive.sqlite3", backend="SIMULATION_ONLY"
    )
    signals = facts.collect_signals(range(300))
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

    facts.clock.set(datetime(2026, 8, 25, tzinfo=UTC))
    facts.repository.begin_collection(
        run_id=facts.run_id,
        collection_run_id="authorized-reobservation",
        backend="MEDIACRAWLER_AUTHORIZED",
        platform="bili",
        query_cluster="sales-agent",
        query_text="销售线索",
        max_contents=10,
        max_comments_per_content=50,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )
    reobserved = facts.collect_signals(
        range(300),
        collection_run_id="authorized-reobservation",
        manifest_sha256="e" * 64,
    )

    snapshot = facts.snapshot(datetime(2026, 8, 25, tzinfo=UTC))

    assert reobserved == signals
    assert snapshot.unique_verifiable_signals == 300
    assert snapshot.reviewed_signals == 0
    assert snapshot.reviewed_ab == 0
    assert snapshot.first_outreach_subjects == 0
    assert snapshot.valid_response_subjects == 0
    assert snapshot.completed_interviews == 0
    assert snapshot.verified_quotes == 0
    assert snapshot.all_success_thresholds is False
    assert snapshot.decision == "RUNNING"
    assert snapshot.platform_breakdown["bili"] == {
        "signals": 300,
        "reviewed": 0,
        "first_outreach": 0,
        "valid_responses": 0,
        "interviews": 0,
        "quotes": 0,
    }
    assert snapshot.industry_breakdown == {}
    assert snapshot.collection_breakdown["SUCCEEDED"] == {
        "runs": 1,
        "raw": 300,
        "unique": 0,
    }
    facts.close()


def test_later_authorized_observation_cannot_promote_earlier_model_block(
    tmp_path,
):
    facts = FactBuilder(
        tmp_path / "simulation-model-retroactive.sqlite3",
        backend="SIMULATION_ONLY",
    )
    signal_id = facts.collect_signals([1])[0]
    facts.finish_collection()
    facts.repository.append_score_failure(
        score_run_id="simulation-model-block",
        run_id=facts.run_id,
        signal_id=signal_id,
        provider=None,
        model=None,
        prompt_version="score-v1",
        schema_version="schema-v1",
        error_code="MODEL_UNAVAILABLE",
    )

    facts.clock.set(datetime(2026, 8, 13, tzinfo=UTC))
    facts.repository.begin_collection(
        run_id=facts.run_id,
        collection_run_id="authorized-model-reobservation",
        backend="MEDIACRAWLER_AUTHORIZED",
        platform="bili",
        query_cluster="sales-agent",
        query_text="销售线索",
        max_contents=10,
        max_comments_per_content=50,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )
    assert facts.collect_signals(
        [1],
        collection_run_id="authorized-model-reobservation",
        manifest_sha256="e" * 64,
    ) == [signal_id]

    snapshot = facts.snapshot(datetime(2026, 8, 14, tzinfo=UTC))

    assert snapshot.unique_verifiable_signals == 1
    assert snapshot.blocked_input is False
    facts.close()


def test_same_second_authorization_cannot_promote_prior_simulation_facts(
    tmp_path,
):
    facts = FactBuilder(
        tmp_path / "same-second-retroactive.sqlite3",
        backend="SIMULATION_ONLY",
    )
    signals = facts.collect_signals(range(300))
    boundary = datetime(2026, 8, 21, tzinfo=UTC)
    facts.clock.set(boundary)
    facts.finish_collection()

    reviews = [
        facts.review(signal_id, index, seconds=0)
        for index, signal_id in enumerate(signals[:100])
    ]
    outreach = [
        facts.outreach(signals[index], reviews[index], index, seconds=0)
        for index in range(30)
    ]
    for index in range(30, 51):
        session_id = facts.workflow.start_activity(
            facts.run_id, signals[index], "DRAFT"
        )
        facts.workflow.record_activity(session_id, "COMPLETE")
        facts.workflow.create_draft(
            run_id=facts.run_id,
            signal_id=signals[index],
            body="人工筛选效率低。我们正在研究销售 Agent，你们每周筛选多少条线索？",
            activity_session_id=session_id,
        )
    responses = [facts.response(outreach[index], index) for index in range(5)]
    interviews = [facts.interview(responses[index]) for index in range(2)]
    canonical_boundary = boundary.isoformat().replace("+00:00", "Z")
    facts.workflow.register_quote(
        run_id=facts.run_id,
        response_event_id=responses[0],
        interview_id=interviews[0],
        scope_summary="线索排序试点",
        agreed_to_receive_pricing_at=canonical_boundary,
        verified_at=canonical_boundary,
    )
    facts.repository.append_score_failure(
        score_run_id="same-second-model-block",
        run_id=facts.run_id,
        signal_id=signals[-1],
        provider=None,
        model=None,
        prompt_version="score-v1",
        schema_version="schema-v1",
        error_code="MODEL_UNAVAILABLE",
    )

    facts.repository.begin_collection(
        run_id=facts.run_id,
        collection_run_id="same-second-authorized",
        backend="MEDIACRAWLER_AUTHORIZED",
        platform="bili",
        query_cluster="sales-agent",
        query_text="销售线索",
        max_contents=10,
        max_comments_per_content=50,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )
    reobserved = facts.collect_signals(
        range(300),
        collection_run_id="same-second-authorized",
        manifest_sha256="e" * 64,
    )

    snapshot = facts.snapshot(boundary + timedelta(seconds=1))

    assert reobserved == signals
    assert (
        snapshot.unique_verifiable_signals,
        snapshot.reviewed_signals,
        snapshot.reviewed_ab,
        snapshot.first_outreach_subjects,
        snapshot.valid_response_subjects,
        snapshot.completed_interviews,
        snapshot.verified_quotes,
        snapshot.blocked_input,
        snapshot.all_success_thresholds,
        snapshot.loss_stop,
        snapshot.decision,
        snapshot.platform_breakdown["bili"],
        snapshot.industry_breakdown,
    ) == (
        300,
        0,
        0,
        0,
        0,
        0,
        0,
        False,
        False,
        False,
        "RUNNING",
        {
            "signals": 300,
            "reviewed": 0,
            "first_outreach": 0,
            "valid_responses": 0,
            "interviews": 0,
            "quotes": 0,
        },
        {},
    )
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
        signals = facts.collect_signals(range(count))
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

        snapshot = facts.snapshot(datetime(2026, 8, 25, tzinfo=UTC))
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
    spaced_signals = spaced.collect_signals(range(3))
    for index, day in enumerate((13, 15, 17)):
        spaced.clock.set(datetime(2026, 8, day, 1, tzinfo=UTC))
        spaced.review(spaced_signals[index], index, seconds=5401)
    spaced_snapshot = spaced.snapshot(datetime(2026, 8, 25, tzinfo=UTC))
    assert "THREE_OVER_90_MINUTE_DAYS" not in spaced_snapshot.loss_stop_reasons
    spaced.close()


def test_current_leaf_and_valid_evidence_are_the_only_quality_and_business_facts(tmp_path):
    facts = FactBuilder(tmp_path / "leaf.sqlite3")
    signal_id = facts.collect_signals([1])[0]
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

    snapshot = facts.snapshot(datetime(2026, 8, 28, tzinfo=UTC))

    assert snapshot.reviewed_signals == 1
    assert snapshot.reviewed_ab == 1
    assert snapshot.high_intent_ab == 0
    assert snapshot.precision == 0.0
    assert snapshot.valid_response_subjects == 0
    facts.close()


def test_open_activity_fails_time_gate_and_later_collection_success_resolves_block(tmp_path):
    facts = FactBuilder(tmp_path / "recovery.sqlite3")
    signal_id = facts.collect_signals([1])[0]
    facts.finish_collection()
    facts.clock.move(1)
    facts.workflow.start_activity(facts.run_id, signal_id, "REVIEW")
    facts.repository.begin_collection(
        run_id=facts.run_id,
        collection_run_id="blocked-attempt",
        backend="MEDIACRAWLER_AUTHORIZED",
        platform="bili",
        query_cluster="sales-agent",
        query_text="销售线索",
        max_contents=10,
        max_comments_per_content=50,
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
        backend="MEDIACRAWLER_AUTHORIZED",
        platform="bili",
        query_cluster="sales-agent",
        query_text="销售线索",
        max_contents=10,
        max_comments_per_content=50,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )
    assert facts.collect_signals(
        [1], collection_run_id="recovered-attempt"
    ) == [signal_id]

    snapshot = facts.snapshot(datetime(2026, 8, 25, tzinfo=UTC))

    assert snapshot.time_complete is False
    assert snapshot.blocked_input is False
    facts.close()


def test_future_activity_event_is_not_hard_but_keeps_time_gate_closed(tmp_path):
    facts = FactBuilder(tmp_path / "future-activity.sqlite3")
    signal_id = facts.collect_signals([1])[0]
    facts.finish_collection()
    facts.clock.move(1)
    session_id = facts.workflow.start_activity(facts.run_id, signal_id, "REVIEW")
    cutoff = facts.clock()
    cutoff_text = cutoff.isoformat().replace("+00:00", "Z")
    facts.clock.move(1)
    facts.workflow.record_activity(session_id, "COMPLETE")

    metrics = MetricsEngine(facts.connection)
    hard_sessions = metrics._hard_execute(
        "SELECT count(*) FROM hard_activity_sessions WHERE mvp_run_id = ?",
        facts.run_id,
        cutoff_text,
        extra=(facts.run_id,),
    ).fetchone()[0]
    snapshot = metrics.calculate(facts.run_id, now=cutoff)

    assert (hard_sessions, snapshot.time_complete) == (0, False)
    facts.close()


def test_model_availability_recovery_uses_one_cross_table_sequence(tmp_path):
    facts = FactBuilder(tmp_path / "model-order.sqlite3")
    signal_id = facts.collect_signals([1])[0]
    facts.finish_collection()
    facts.clock.move(1)
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

    recovered = facts.snapshot(datetime(2026, 8, 21, tzinfo=UTC))
    assert recovered.blocked_input is False

    facts.repository.append_draft_failure(
        draft_run_id="draft-blocked-again", run_id=facts.run_id,
        signal_id=signal_id, provider=None, model=None,
        prompt_version="draft-v1", error_code="MODEL_UNAVAILABLE",
    )
    blocked_again = facts.snapshot(datetime(2026, 8, 21, tzinfo=UTC))
    assert blocked_again.blocked_input is True
    facts.close()
