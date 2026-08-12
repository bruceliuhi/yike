from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import sqlite3
from statistics import median
from zoneinfo import ZoneInfo


def conclusion_for(
    *, incident: bool = False,
    loss_stop: bool = False,
    blocked_input: bool = False,
    all_success_thresholds: bool = False,
    terminal_eligible: bool = False,
) -> str:
    if incident or loss_stop:
        return "STOP_DISCOVERY"
    if blocked_input:
        return "BLOCKED_INPUT"
    if all_success_thresholds:
        return "PROCEED_TO_V03_REVIEW"
    if terminal_eligible:
        return "REVISE_MVP"
    return "RUNNING"


@dataclass(frozen=True)
class MetricsSnapshot:
    run_id: str
    unique_verifiable_signals: int
    reviewed_signals: int
    first_outreach_subjects: int
    valid_response_subjects: int
    completed_interviews: int
    verified_quotes: int
    reviewed_ab: int
    high_intent_ab: int
    precision: float | None
    incident: bool
    loss_stop: bool
    loss_stop_reasons: tuple[str, ...]
    blocked_input: bool
    time_complete: bool
    daily_time_within_limit: bool
    day8_12_median_seconds: float | None
    all_success_thresholds: bool
    terminal_eligible: bool
    decision: str
    platform_breakdown: dict[str, dict[str, int]]
    industry_breakdown: dict[str, dict[str, int]]
    collection_breakdown: dict[str, dict[str, int]]

    def facts(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_facts(cls, facts: dict[str, object]) -> "MetricsSnapshot":
        values = dict(facts)
        values["loss_stop_reasons"] = tuple(values["loss_stop_reasons"])
        return cls(**values)


class MetricsEngine:
    """Derive every count and conclusion from one run-scoped SQLite snapshot."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def calculate(self, run_id: str, *, now: datetime | None = None) -> MetricsSnapshot:
        run = self.connection.execute(
            "SELECT state, started_at, day14_due_at FROM mvp_runs WHERE mvp_run_id = ?",
            (run_id,),
        ).fetchone()
        if run is None:
            raise KeyError(f"unknown mvp run: {run_id}")
        instant = now or datetime.now(UTC)
        due_at = _dt(str(run["day14_due_at"]))
        cutoff = min(instant, due_at).isoformat(timespec="seconds").replace("+00:00", "Z")

        unique_signals = self._scalar(
            """
            SELECT COUNT(*) FROM mvp_run_signals member
            JOIN signals signal ON signal.signal_id = member.signal_id
            JOIN sources source ON source.source_id = signal.source_id
                               AND source.platform = signal.platform
            WHERE member.mvp_run_id = ? AND signal.verifiable = 1
              AND member.added_at <= ?
              AND length(trim(source.external_source_id)) > 0
              AND source.canonical_url IS NOT NULL
              AND length(trim(source.canonical_url)) > 0
              AND signal.external_comment_id IS NOT NULL
              AND length(trim(signal.external_comment_id)) > 0
              AND length(trim(signal.normalized_comment_url)) > 0
              AND length(trim(signal.author_public_id)) > 0
              AND length(trim(signal.body)) > 0
              AND length(signal.body_sha256) = 64
              AND signal.body_sha256 NOT GLOB '*[^0-9a-f]*'
              AND signal.body_sha256 = yike_sha256_text(signal.body)
              AND signal.normalizer_version IS NOT NULL
              AND length(trim(signal.normalizer_version)) > 0
              AND EXISTS (
                  SELECT 1
                  FROM signal_observations observation
                  JOIN collection_runs collection
                    ON collection.collection_run_id = observation.collection_run_id
                   AND collection.mvp_run_id = observation.mvp_run_id
                  JOIN campaigns campaign
                    ON campaign.campaign_id = collection.campaign_id
                   AND campaign.mvp_run_id = collection.mvp_run_id
                   AND campaign.platform = collection.platform
                  WHERE observation.mvp_run_id = member.mvp_run_id
                    AND observation.signal_id = member.signal_id
                    AND observation.query_cluster IS NOT NULL
                    AND length(trim(observation.query_cluster)) > 0
                    AND observation.query_text IS NOT NULL
                    AND length(trim(observation.query_text)) > 0
                    AND campaign.query_cluster = observation.query_cluster
                    AND campaign.query_text = observation.query_text
                    AND strftime(
                        '%Y-%m-%dT%H:%M:%SZ', observation.observed_at
                    ) = observation.observed_at
                    AND observation.observed_at <= ?
                    AND length(observation.raw_sha256) = 64
                    AND observation.raw_sha256 NOT GLOB '*[^0-9a-f]*'
                    AND observation.envelope_sha256 IS NOT NULL
                    AND length(observation.envelope_sha256) = 64
                    AND observation.envelope_sha256 NOT GLOB '*[^0-9a-f]*'
                    AND collection.platform = signal.platform
                    AND collection.state = 'SUCCEEDED'
                    AND collection.started_at IS NOT NULL
                    AND collection.finished_at IS NOT NULL
                    AND strftime(
                        '%Y-%m-%dT%H:%M:%SZ', collection.started_at
                    ) = collection.started_at
                    AND strftime(
                        '%Y-%m-%dT%H:%M:%SZ', collection.finished_at
                    ) = collection.finished_at
                    AND collection.started_at <= observation.observed_at
                    AND observation.observed_at <= collection.finished_at
                    AND collection.finished_at <= ?
                    AND collection.raw_count > 0
                    AND collection.unique_count >= 0
                    AND collection.unique_count <= collection.raw_count
                    AND collection.error_code IS NULL
                    AND collection.output_manifest_sha256 IS NOT NULL
                    AND length(collection.output_manifest_sha256) = 64
                    AND collection.output_manifest_sha256 NOT GLOB '*[^0-9a-f]*'
                    AND length(collection.runtime_lock_sha256) = 64
                    AND collection.runtime_lock_sha256 NOT GLOB '*[^0-9a-f]*'
              )
            """,
            run_id,
            extra=(cutoff, cutoff, cutoff),
        )
        reviewed = self._scalar(self._leaf_review_count(), run_id, extra=(cutoff, cutoff))
        first_outreach = self._scalar(
            """
            SELECT COUNT(DISTINCT platform || ':' || subject_key)
            FROM outreach_actions
            WHERE mvp_run_id = ? AND parent_outreach_action_id IS NULL
              AND status = 'SENT_VERIFIED'
              AND context_evidence IS NOT NULL AND length(trim(context_evidence)) > 0
              AND sent_at <= ? AND created_at <= ?
            """,
            run_id,
            extra=(cutoff, cutoff),
        )
        valid_responses = self._scalar(
            """
            SELECT COUNT(DISTINCT response.responder_subject_key)
            FROM response_events response
            JOIN outreach_actions outreach
              ON outreach.outreach_action_id = response.outreach_action_id
             AND outreach.mvp_run_id = response.mvp_run_id
            WHERE response.mvp_run_id = ? AND response.response_type = 'VALID'
              AND outreach.status = 'SENT_VERIFIED'
              AND response.verified_at IS NOT NULL
              AND length(trim(response.verified_at)) > 0
              AND response.evidence_summary IS NOT NULL
              AND length(trim(response.evidence_summary)) > 0
              AND response.occurred_at <= ? AND response.verified_at <= ?
              AND response.recorded_at <= ?
              AND outreach.sent_at <= ? AND outreach.created_at <= ?
            """,
            run_id,
            extra=(cutoff, cutoff, cutoff, cutoff, cutoff),
        )
        interviews = self._scalar(
            """
            SELECT COUNT(DISTINCT response.responder_subject_key)
            FROM interviews interview
            JOIN response_events response
              ON response.response_event_id = interview.response_event_id
             AND response.mvp_run_id = interview.mvp_run_id
            JOIN outreach_actions outreach
              ON outreach.outreach_action_id = response.outreach_action_id
             AND outreach.mvp_run_id = response.mvp_run_id
            WHERE interview.mvp_run_id = ? AND interview.completed_at IS NOT NULL
              AND response.response_type = 'VALID'
              AND outreach.status = 'SENT_VERIFIED'
              AND interview.completed_at <= ? AND response.verified_at <= ?
              AND interview.recorded_at <= ? AND response.recorded_at <= ?
              AND outreach.sent_at <= ? AND outreach.created_at <= ?
            """,
            run_id,
            extra=(cutoff, cutoff, cutoff, cutoff, cutoff, cutoff),
        )
        quotes = self._scalar(
            """
            SELECT COUNT(DISTINCT response.responder_subject_key)
            FROM quote_opportunities quote
            LEFT JOIN interviews interview
              ON interview.interview_id = quote.interview_id
             AND interview.mvp_run_id = quote.mvp_run_id
            JOIN response_events response
              ON response.mvp_run_id = quote.mvp_run_id
             AND response.response_event_id = coalesce(
                   quote.response_event_id, interview.response_event_id
                 )
            JOIN outreach_actions outreach
              ON outreach.outreach_action_id = response.outreach_action_id
             AND outreach.mvp_run_id = response.mvp_run_id
            WHERE quote.mvp_run_id = ? AND response.response_type = 'VALID'
              AND outreach.status = 'SENT_VERIFIED'
              AND quote.verified_at IS NOT NULL
              AND quote.agreed_to_receive_pricing_at IS NOT NULL
              AND quote.agreed_to_receive_pricing_at <= ?
              AND quote.verified_at <= ? AND response.verified_at <= ?
              AND quote.recorded_at <= ? AND response.recorded_at <= ?
              AND (quote.interview_id IS NULL OR interview.recorded_at <= ?)
              AND outreach.sent_at <= ? AND outreach.created_at <= ?
            """,
            run_id,
            extra=(cutoff, cutoff, cutoff, cutoff, cutoff, cutoff, cutoff, cutoff),
        )
        reviewed_ab, high_intent_ab = self.connection.execute(
            """
            WITH leaf_reviews AS (
              SELECT review.* FROM human_reviews review
              WHERE review.mvp_run_id = ? AND review.completed_at <= ?
                AND NOT EXISTS (
                  SELECT 1 FROM human_reviews child
                  WHERE child.supersedes_review_id = review.review_id
                    AND child.completed_at <= ?
                )
            )
            SELECT COUNT(DISTINCT presentation.signal_id),
                   COUNT(DISTINCT CASE WHEN leaf.label = 'HIGH_INTENT'
                                       THEN presentation.signal_id END)
            FROM score_presentations presentation
            JOIN score_runs score
              ON score.score_run_id = presentation.score_run_id
             AND score.mvp_run_id = presentation.mvp_run_id
             AND score.signal_id = presentation.signal_id
            JOIN leaf_reviews leaf
              ON leaf.presented_score_run_id = presentation.score_run_id
             AND leaf.signal_id = presentation.signal_id
            WHERE presentation.mvp_run_id = ? AND score.grade IN ('A', 'B')
              AND presentation.presented_at <= ?
            """,
            (run_id, cutoff, cutoff, run_id, cutoff),
        ).fetchone()
        precision = high_intent_ab / reviewed_ab if reviewed_ab else None
        incident = bool(
            self._scalar(
                "SELECT COUNT(*) FROM risk_events WHERE mvp_run_id = ? "
                "AND forces_stop = 1 AND verified_at <= ?",
                run_id,
                extra=(cutoff,),
            )
        )
        blocked_input = bool(
            self._scalar(
                """
                SELECT COUNT(*) FROM collection_runs
                WHERE mvp_run_id = ? AND state = 'BLOCKED_INPUT'
                  AND coalesce(finished_at, started_at) <= ?
                  AND NOT EXISTS (
                    SELECT 1 FROM collection_runs recovered
                    WHERE recovered.mvp_run_id = collection_runs.mvp_run_id
                      AND recovered.platform = collection_runs.platform
                      AND recovered.state IN ('SUCCEEDED', 'SUCCEEDED_NO_DATA')
                      AND (
                        coalesce(recovered.finished_at, recovered.started_at)
                          > coalesce(collection_runs.finished_at, collection_runs.started_at)
                        OR (
                          coalesce(recovered.finished_at, recovered.started_at)
                            = coalesce(collection_runs.finished_at, collection_runs.started_at)
                          AND recovered.rowid > collection_runs.rowid
                        )
                      )
                      AND coalesce(recovered.finished_at, recovered.started_at) <= ?
                  )
                """,
                run_id,
                extra=(cutoff, cutoff),
            )
            or self._scalar(
                """
                SELECT COUNT(*) FROM model_availability_events event
                WHERE event.mvp_run_id = ? AND event.availability_state = 'BLOCKED'
                  AND event.recorded_at <= ?
                  AND NOT EXISTS (
                    SELECT 1 FROM model_availability_events later
                    WHERE later.mvp_run_id = event.mvp_run_id
                      AND later.recorded_at <= ?
                      AND later.event_sequence > event.event_sequence
                  )
                """,
                run_id,
                extra=(cutoff, cutoff),
            )
        )
        high_intent = self._scalar(
            """
            SELECT COUNT(*) FROM human_reviews review
            WHERE review.mvp_run_id = ? AND review.label = 'HIGH_INTENT'
              AND review.completed_at <= ?
              AND NOT EXISTS (
                SELECT 1 FROM human_reviews child
                WHERE child.supersedes_review_id = review.review_id
                  AND child.completed_at <= ?
              )
            """,
            run_id,
            extra=(cutoff, cutoff),
        )
        personalized_high_intent = self._scalar(
            """
            SELECT COUNT(DISTINCT outreach.signal_id)
            FROM outreach_actions outreach
            JOIN human_reviews review
              ON review.mvp_run_id = outreach.mvp_run_id
             AND review.signal_id = outreach.signal_id
            WHERE outreach.mvp_run_id = ? AND outreach.parent_outreach_action_id IS NULL
              AND outreach.status = 'SENT_VERIFIED'
              AND review.label = 'HIGH_INTENT'
              AND outreach.context_evidence IS NOT NULL
              AND length(trim(outreach.context_evidence)) > 0
              AND outreach.sent_at <= ? AND outreach.created_at <= ?
              AND NOT EXISTS (
                SELECT 1 FROM human_reviews child
                WHERE child.supersedes_review_id = review.review_id
                  AND child.completed_at <= ?
              )
              AND review.completed_at <= ?
            """,
            run_id,
            extra=(cutoff, cutoff, cutoff, cutoff),
        )

        sessions = self.connection.execute(
            """
            SELECT session.*, member.added_at
            FROM activity_sessions session
            JOIN mvp_run_signals member
              ON member.mvp_run_id = session.mvp_run_id
             AND member.signal_id = session.signal_id
            WHERE session.mvp_run_id = ?
              AND session.started_at <= ?
            """,
            (run_id, cutoff),
        ).fetchall()
        required_count = self._scalar(
            "SELECT COUNT(*) FROM human_reviews WHERE mvp_run_id = ? AND completed_at <= ?",
            run_id,
            extra=(cutoff,),
        ) + self._scalar(
            "SELECT COUNT(*) FROM draft_runs WHERE mvp_run_id = ? "
            "AND draft_kind = 'HUMAN_EDITED' AND status = 'SUCCEEDED' "
            "AND created_at <= ?",
            run_id,
            extra=(cutoff,),
        )
        completed_required = self._scalar(
            """
            SELECT COUNT(*) FROM (
              SELECT activity_session_id FROM human_reviews
              WHERE mvp_run_id = ? AND completed_at <= ?
              UNION ALL
              SELECT activity_session_id FROM draft_runs
              WHERE mvp_run_id = ? AND draft_kind = 'HUMAN_EDITED'
                AND status = 'SUCCEEDED' AND created_at <= ?
            ) required
            JOIN activity_sessions session
              ON session.activity_session_id = required.activity_session_id
             AND session.state = 'COMPLETED'
            """,
            run_id,
            extra=(cutoff, run_id, cutoff),
        )
        open_activity = any(
            session["state"] in ("OPEN", "PAUSED")
            or (
                session["completed_at"] is not None
                and str(session["completed_at"]) > cutoff
            )
            for session in sessions
        )
        abandoned_cancelled = False
        for session in sessions:
            if session["state"] != "CANCELLED" or str(session["completed_at"]) > cutoff:
                continue
            fact_table = "human_reviews" if session["activity_kind"] == "REVIEW" else "draft_runs"
            recovered = self.connection.execute(
                f"""
                SELECT 1 FROM activity_sessions replacement
                JOIN {fact_table} fact
                  ON fact.activity_session_id = replacement.activity_session_id
                WHERE replacement.mvp_run_id = ? AND replacement.signal_id = ?
                  AND replacement.activity_kind = ? AND replacement.state = 'COMPLETED'
                  AND replacement.started_at >= ? AND replacement.completed_at <= ?
                LIMIT 1
                """,
                (
                    run_id, session["signal_id"], session["activity_kind"],
                    session["completed_at"], cutoff,
                ),
            ).fetchone()
            if recovered is None:
                abandoned_cancelled = True
                break
        time_complete = (
            required_count == completed_required
            and not open_activity
            and not abandoned_cancelled
        )
        shanghai = ZoneInfo("Asia/Shanghai")
        day_seconds: dict[str, int] = {}
        day8_12_by_signal: dict[str, int] = {}
        started = _dt(str(run["started_at"]))
        started_local_date = started.astimezone(shanghai).date()
        for session in sessions:
            if session["completed_at"] is not None and str(session["completed_at"]) > cutoff:
                continue
            if session["state"] not in ("COMPLETED", "CANCELLED") or session["active_seconds"] is None:
                continue
            received = _dt(str(session["started_at"]))
            local_day = received.astimezone(shanghai).date().isoformat()
            day_seconds[local_day] = day_seconds.get(local_day, 0) + int(
                session["active_seconds"]
            )
            experiment_day = (
                received.astimezone(shanghai).date() - started_local_date
            ).days
            if session["state"] == "COMPLETED" and 8 <= experiment_day <= 12:
                signal_id = str(session["signal_id"])
                day8_12_by_signal[signal_id] = day8_12_by_signal.get(signal_id, 0) + int(
                    session["active_seconds"]
                )
        daily_time_within_limit = time_complete and all(
            seconds <= 90 * 60 for seconds in day_seconds.values()
        )
        day8_12_median = (
            median(day8_12_by_signal.values()) if day8_12_by_signal else None
        )
        day8_12_gate = day8_12_median is not None and day8_12_median <= 240

        overworked_dates = []
        for local_day, seconds in day_seconds.items():
            personalized_that_day = self._scalar(
                """
                SELECT COUNT(*) FROM outreach_actions
                WHERE mvp_run_id = ? AND parent_outreach_action_id IS NULL
                  AND status = 'SENT_VERIFIED'
                  AND context_evidence IS NOT NULL AND length(trim(context_evidence)) > 0
                  AND date(sent_at, '+8 hours') = ?
                  AND sent_at <= ? AND created_at <= ?
                """,
                run_id,
                extra=(local_day, cutoff, cutoff),
            )
            if seconds > 90 * 60 and personalized_that_day < 3:
                overworked_dates.append(datetime.fromisoformat(local_day).date())
        overworked_dates.sort()
        consecutive_overworked = any(
            (overworked_dates[index] - overworked_dates[index - 2]).days == 2
            for index in range(2, len(overworked_dates))
        )
        unsolvable = bool(
            self._scalar(
                "SELECT COUNT(*) FROM interviews WHERE mvp_run_id = ? "
                "AND completed_at IS NOT NULL AND solution_fit = 'UNSOLVABLE' "
                "AND completed_at <= ? AND recorded_at <= ?",
                run_id,
                extra=(cutoff, cutoff),
            )
        )
        loss_reasons = []
        if reviewed >= 200 and high_intent < 10:
            loss_reasons.append("LOW_HIGH_INTENT")
        if first_outreach >= 30 and valid_responses < 3:
            loss_reasons.append("LOW_VALID_RESPONSE")
        if first_outreach >= 40 and interviews == 0:
            loss_reasons.append("NO_INTERVIEW")
        if high_intent >= 20 and personalized_high_intent == 0:
            loss_reasons.append("NO_PERSONALIZED_CONTEXT")
        if consecutive_overworked:
            loss_reasons.append("THREE_OVER_90_MINUTE_DAYS")
        if unsolvable:
            loss_reasons.append("UNSOLVABLE_INTERVIEW")
        loss_stop = bool(loss_reasons)

        all_success = (
            unique_signals >= 300
            and reviewed >= 100
            and reviewed_ab >= 40
            and precision is not None and precision >= 0.5
            and first_outreach >= 30
            and valid_responses >= 5
            and interviews >= 2
            and quotes >= 1
            and time_complete
            and daily_time_within_limit
            and day8_12_gate
            and not incident
        )
        terminal = run["state"] == "CANCELLED" or instant >= due_at
        decision = conclusion_for(
            incident=incident,
            loss_stop=loss_stop,
            blocked_input=blocked_input,
            all_success_thresholds=all_success,
            terminal_eligible=terminal,
        )
        return MetricsSnapshot(
            run_id=run_id,
            unique_verifiable_signals=unique_signals,
            reviewed_signals=reviewed,
            first_outreach_subjects=first_outreach,
            valid_response_subjects=valid_responses,
            completed_interviews=interviews,
            verified_quotes=quotes,
            reviewed_ab=reviewed_ab,
            high_intent_ab=high_intent_ab,
            precision=precision,
            incident=incident,
            loss_stop=loss_stop,
            loss_stop_reasons=tuple(loss_reasons),
            blocked_input=blocked_input,
            time_complete=time_complete,
            daily_time_within_limit=daily_time_within_limit,
            day8_12_median_seconds=day8_12_median,
            all_success_thresholds=all_success,
            terminal_eligible=terminal,
            decision=decision,
            platform_breakdown=self._platform_breakdown(run_id, cutoff),
            industry_breakdown=self._industry_breakdown(run_id, cutoff),
            collection_breakdown=self._collection_breakdown(run_id, cutoff),
        )

    @staticmethod
    def _leaf_review_count() -> str:
        return """
            SELECT COUNT(*) FROM human_reviews review
            WHERE review.mvp_run_id = ? AND review.completed_at <= ?
              AND NOT EXISTS (
                SELECT 1 FROM human_reviews child
                WHERE child.supersedes_review_id = review.review_id
                  AND child.completed_at <= ?
              )
        """

    def _platform_breakdown(self, run_id: str, cutoff: str) -> dict[str, dict[str, int]]:
        platforms = [
            str(row[0])
            for row in self.connection.execute(
                """
                SELECT DISTINCT signal.platform
                FROM mvp_run_signals member
                JOIN signals signal ON signal.signal_id = member.signal_id
                WHERE member.mvp_run_id = ? AND member.added_at <= ?
                ORDER BY signal.platform
                """,
                (run_id, cutoff),
            ).fetchall()
        ]
        result: dict[str, dict[str, int]] = {}
        for platform in platforms:
            signals = self.connection.execute(
                """
                SELECT COUNT(DISTINCT member.signal_id)
                FROM mvp_run_signals member
                JOIN signals signal ON signal.signal_id = member.signal_id
                WHERE member.mvp_run_id = ? AND signal.platform = ?
                  AND member.added_at <= ?
                """,
                (run_id, platform, cutoff),
            ).fetchone()[0]
            reviewed = self.connection.execute(
                """
                SELECT COUNT(DISTINCT review.signal_id)
                FROM human_reviews review
                JOIN signals signal ON signal.signal_id = review.signal_id
                WHERE review.mvp_run_id = ? AND signal.platform = ?
                  AND review.completed_at <= ?
                  AND NOT EXISTS (
                    SELECT 1 FROM human_reviews child
                    WHERE child.supersedes_review_id = review.review_id
                      AND child.completed_at <= ?
                  )
                """,
                (run_id, platform, cutoff, cutoff),
            ).fetchone()[0]
            business = self.connection.execute(
                """
                SELECT
                  COUNT(DISTINCT outreach.subject_key),
                  COUNT(DISTINCT response.responder_subject_key),
                  COUNT(DISTINCT CASE WHEN interview.completed_at <= ?
                                            AND interview.recorded_at <= ?
                                      THEN response.responder_subject_key END),
                  COUNT(DISTINCT CASE
                    WHEN quote.verified_at <= ?
                     AND quote.agreed_to_receive_pricing_at <= ?
                     AND quote.recorded_at <= ?
                     AND (quote.interview_id IS NULL OR interview.recorded_at <= ?)
                    THEN response.responder_subject_key END)
                FROM outreach_actions outreach
                LEFT JOIN response_events response
                  ON response.outreach_action_id = outreach.outreach_action_id
                 AND response.mvp_run_id = outreach.mvp_run_id
                 AND response.response_type = 'VALID'
                 AND response.occurred_at <= ? AND response.verified_at <= ?
                 AND response.recorded_at <= ?
                 AND response.evidence_summary IS NOT NULL
                 AND length(trim(response.evidence_summary)) > 0
                LEFT JOIN interviews interview
                  ON interview.response_event_id = response.response_event_id
                 AND interview.mvp_run_id = response.mvp_run_id
                LEFT JOIN quote_opportunities quote
                  ON quote.mvp_run_id = response.mvp_run_id
                 AND quote.response_event_id = response.response_event_id
                    OR (
                      quote.mvp_run_id = response.mvp_run_id
                      AND quote.interview_id = interview.interview_id
                    )
                WHERE outreach.mvp_run_id = ? AND outreach.platform = ?
                  AND outreach.parent_outreach_action_id IS NULL
                  AND outreach.status = 'SENT_VERIFIED' AND outreach.sent_at <= ?
                  AND outreach.created_at <= ?
                """,
                (
                    cutoff, cutoff, cutoff, cutoff, cutoff, cutoff,
                    cutoff, cutoff, cutoff,
                    run_id, platform, cutoff, cutoff,
                ),
            ).fetchone()
            result[platform] = {
                "signals": int(signals),
                "reviewed": int(reviewed),
                "first_outreach": int(business[0]),
                "valid_responses": int(business[1]),
                "interviews": int(business[2]),
                "quotes": int(business[3]),
            }
        return result

    def _industry_breakdown(self, run_id: str, cutoff: str) -> dict[str, dict[str, int]]:
        industries = [
            str(row[0])
            for row in self.connection.execute(
                """
                SELECT DISTINCT coalesce(
                    json_extract(score.reason_json, '$.explicit_industry'), '未识别'
                )
                FROM score_presentations presentation
                JOIN score_runs score ON score.score_run_id = presentation.score_run_id
                WHERE presentation.mvp_run_id = ? AND presentation.presented_at <= ?
                ORDER BY 1
                """,
                (run_id, cutoff),
            ).fetchall()
        ]
        result: dict[str, dict[str, int]] = {}
        for industry in industries:
            row = self.connection.execute(
                """
                WITH scoped AS (
                  SELECT presentation.signal_id, score.score_run_id
                  FROM score_presentations presentation
                  JOIN score_runs score ON score.score_run_id = presentation.score_run_id
                  WHERE presentation.mvp_run_id = ? AND presentation.presented_at <= ?
                    AND coalesce(
                      json_extract(score.reason_json, '$.explicit_industry'), '未识别'
                    ) = ?
                ), leaf AS (
                  SELECT review.* FROM human_reviews review
                  JOIN scoped ON scoped.signal_id = review.signal_id
                  WHERE review.mvp_run_id = ? AND review.completed_at <= ?
                    AND NOT EXISTS (
                      SELECT 1 FROM human_reviews child
                      WHERE child.supersedes_review_id = review.review_id
                        AND child.completed_at <= ?
                    )
                )
                SELECT
                  COUNT(DISTINCT scoped.signal_id),
                  COUNT(DISTINCT leaf.signal_id),
                  COUNT(DISTINCT CASE WHEN leaf.label = 'HIGH_INTENT'
                                      THEN leaf.signal_id END),
                  COUNT(DISTINCT outreach.subject_key),
                  COUNT(DISTINCT response.responder_subject_key)
                FROM scoped
                LEFT JOIN leaf ON leaf.signal_id = scoped.signal_id
                LEFT JOIN outreach_actions outreach
                 ON outreach.mvp_run_id = ? AND outreach.signal_id = scoped.signal_id
                 AND outreach.parent_outreach_action_id IS NULL
                 AND outreach.status = 'SENT_VERIFIED' AND outreach.sent_at <= ?
                 AND outreach.created_at <= ?
                LEFT JOIN response_events response
                  ON response.mvp_run_id = outreach.mvp_run_id
                 AND response.outreach_action_id = outreach.outreach_action_id
                 AND response.response_type = 'VALID'
                 AND response.occurred_at <= ? AND response.verified_at <= ?
                 AND response.recorded_at <= ?
                 AND response.evidence_summary IS NOT NULL
                 AND length(trim(response.evidence_summary)) > 0
                """,
                (
                    run_id, cutoff, industry, run_id, cutoff, cutoff,
                    run_id, cutoff, cutoff, cutoff, cutoff, cutoff,
                ),
            ).fetchone()
            result[industry] = {
                "presented": int(row[0]),
                "reviewed": int(row[1]),
                "high_intent": int(row[2]),
                "first_outreach": int(row[3]),
                "valid_responses": int(row[4]),
            }
        return result

    def _collection_breakdown(self, run_id: str, cutoff: str) -> dict[str, dict[str, int]]:
        rows = self.connection.execute(
            """
            SELECT state, COUNT(*), coalesce(SUM(raw_count), 0),
                   coalesce(SUM(unique_count), 0)
            FROM collection_runs WHERE mvp_run_id = ?
              AND coalesce(finished_at, started_at) <= ? GROUP BY state
            """,
            (run_id, cutoff),
        ).fetchall()
        return {
            row[0]: {"runs": row[1], "raw": row[2], "unique": row[3]}
            for row in rows
        }

    def _scalar(self, statement: str, run_id: str, *, extra: tuple[object, ...] = ()) -> int:
        return int(self.connection.execute(statement, (run_id, *extra)).fetchone()[0])


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
