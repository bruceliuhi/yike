from dataclasses import dataclass
from datetime import UTC, datetime
import sqlite3


def conclusion_for(
    *,
    incident: bool = False,
    loss_stop: bool = False,
    blocked_input: bool = False,
    all_success_thresholds: bool = False,
    terminal_eligible: bool = False,
) -> str:
    """Return the first matching governed conclusion branch."""
    if incident:
        return "STOP_DISCOVERY"
    if loss_stop:
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
    blocked_input: bool
    all_success_thresholds: bool
    terminal_eligible: bool
    decision: str


class MetricsEngine:
    """Compute experiment metrics from persisted SQLite facts only."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def calculate(
        self, run_id: str, *, now: datetime | None = None
    ) -> MetricsSnapshot:
        run = self.connection.execute(
            "SELECT state, day14_due_at FROM mvp_runs WHERE mvp_run_id = ?", (run_id,)
        ).fetchone()
        if run is None:
            raise KeyError(f"unknown mvp run: {run_id}")

        unique_signals = self._scalar(
            """
            SELECT COUNT(*) FROM mvp_run_signals m
            JOIN signals s ON s.signal_id = m.signal_id
            WHERE m.mvp_run_id = ? AND s.verifiable = 1
            """,
            run_id,
        )
        reviewed = self._scalar(
            """
            SELECT COUNT(DISTINCT review.signal_id)
            FROM human_reviews review
            WHERE review.mvp_run_id = ?
              AND NOT EXISTS (
                SELECT 1 FROM human_reviews child
                WHERE child.mvp_run_id = review.mvp_run_id
                  AND child.signal_id = review.signal_id
                  AND child.supersedes_review_id = review.review_id
              )
            """,
            run_id,
        )
        first_outreach = self._scalar(
            """
            SELECT COUNT(DISTINCT platform || ':' || subject_key)
            FROM outreach_actions
            WHERE mvp_run_id = ? AND parent_outreach_action_id IS NULL
              AND status = 'SENT_VERIFIED'
            """,
            run_id,
        )
        valid_responses = self._scalar(
            """
            SELECT COUNT(DISTINCT responder_subject_key)
            FROM response_events
            WHERE mvp_run_id = ? AND response_type = 'VALID'
              AND verified_at IS NOT NULL AND evidence_summary IS NOT NULL
            """,
            run_id,
        )
        interviews = self._scalar(
            """
            SELECT COUNT(DISTINCT re.responder_subject_key)
            FROM interviews i
            JOIN response_events re
              ON re.response_event_id = i.response_event_id
             AND re.mvp_run_id = i.mvp_run_id
            WHERE i.mvp_run_id = ? AND i.completed_at IS NOT NULL
            """,
            run_id,
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
             AND response.response_event_id = COALESCE(
                   quote.response_event_id, interview.response_event_id
                 )
            WHERE quote.mvp_run_id = ? AND quote.verified_at IS NOT NULL
              AND quote.agreed_to_receive_pricing_at IS NOT NULL
            """,
            run_id,
        )
        reviewed_ab, high_intent_ab = self.connection.execute(
            """
            SELECT
              COUNT(DISTINCT sp.signal_id),
              COUNT(DISTINCT CASE WHEN hr.label = 'HIGH_INTENT' THEN sp.signal_id END)
            FROM score_presentations sp
            JOIN score_runs sr
              ON sr.score_run_id = sp.score_run_id
             AND sr.mvp_run_id = sp.mvp_run_id
             AND sr.signal_id = sp.signal_id
            JOIN human_reviews hr
              ON hr.presented_score_run_id = sp.score_run_id
             AND hr.mvp_run_id = sp.mvp_run_id
             AND hr.signal_id = sp.signal_id
            WHERE sp.mvp_run_id = ? AND sr.grade IN ('A', 'B')
              AND NOT EXISTS (
                SELECT 1 FROM human_reviews child
                WHERE child.mvp_run_id = hr.mvp_run_id
                  AND child.signal_id = hr.signal_id
                  AND child.supersedes_review_id = hr.review_id
              )
            """,
            (run_id,),
        ).fetchone()
        precision = high_intent_ab / reviewed_ab if reviewed_ab else None
        incident = bool(
            self._scalar(
                "SELECT COUNT(*) FROM risk_events WHERE mvp_run_id = ? AND forces_stop = 1",
                run_id,
            )
        )
        collection_blocked = bool(
            self._scalar(
                """
                SELECT COUNT(*) FROM collection_runs
                WHERE mvp_run_id = ? AND state = 'BLOCKED_INPUT'
                """,
                run_id,
            )
        )
        model_blocked = bool(
            self._scalar(
                """
                SELECT COUNT(*)
                FROM score_runs blocked
                WHERE blocked.mvp_run_id = ?
                  AND blocked.status = 'FAILED'
                  AND blocked.error_code IN (
                    'MODEL_NOT_CONFIGURED', 'MODEL_UNAVAILABLE'
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM score_runs newer
                    WHERE newer.mvp_run_id = blocked.mvp_run_id
                      AND newer.signal_id = blocked.signal_id
                      AND (
                        newer.created_at > blocked.created_at
                        OR (
                          newer.created_at = blocked.created_at
                          AND newer.rowid > blocked.rowid
                        )
                      )
                  )
                """,
                run_id,
            )
        )
        blocked_input = collection_blocked or model_blocked
        high_intent = self._scalar(
            """
            SELECT COUNT(DISTINCT review.signal_id) FROM human_reviews review
            WHERE review.mvp_run_id = ? AND review.label = 'HIGH_INTENT'
              AND NOT EXISTS (
                SELECT 1 FROM human_reviews child
                WHERE child.mvp_run_id = review.mvp_run_id
                  AND child.signal_id = review.signal_id
                  AND child.supersedes_review_id = review.review_id
              )
            """,
            run_id,
        )
        loss_stop = (
            (reviewed >= 200 and high_intent < 10)
            or (first_outreach >= 30 and valid_responses < 3)
            or (first_outreach >= 40 and interviews == 0)
        )

        # V3 has no governed activity-session or personalized-context facts. Those
        # success gates therefore fail closed until facts exist in a later schema.
        all_success = False
        instant = now or datetime.now(UTC)
        due_at = datetime.fromisoformat(str(run["day14_due_at"]).replace("Z", "+00:00"))
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
            blocked_input=blocked_input,
            all_success_thresholds=all_success,
            terminal_eligible=terminal,
            decision=decision,
        )

    def _scalar(self, statement: str, run_id: str) -> int:
        return int(self.connection.execute(statement, (run_id,)).fetchone()[0])
