from datetime import UTC, datetime
import json
import sqlite3
from uuid import uuid4

from app.repository import Repository


_REVIEW_LABELS = frozenset(("HIGH_INTENT", "POSSIBLE", "NOT_LEAD", "UNVERIFIABLE"))


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _required(value: str, name: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


class Workflow:
    """Append-only human workflow facts; this class performs no outbound I/O."""

    def __init__(self, repository: Repository):
        self.repository = repository
        self.connection = repository.connection

    def present_score(self, run_id: str, signal_id: str, score_run_id: str) -> str:
        existing = self.connection.execute(
            """
            SELECT score_run_id FROM score_presentations
            WHERE mvp_run_id = ? AND signal_id = ?
            """,
            (run_id, signal_id),
        ).fetchone()
        if existing is not None:
            return str(existing["score_run_id"])
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO score_presentations (
                    presentation_id, mvp_run_id, signal_id, score_run_id, presented_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (str(uuid4()), run_id, signal_id, score_run_id, _now()),
            )
        return score_run_id

    def complete_review(
        self,
        *,
        run_id: str,
        signal_id: str,
        label: str,
        reason: str,
        note: str | None,
        started_at: str,
        completed_at: str,
        active_seconds: int,
        supersedes_review_id: str | None = None,
    ) -> str:
        if label not in _REVIEW_LABELS:
            raise ValueError("invalid human review label")
        reason = _required(reason, "review reason")
        started_at = _required(started_at, "review started_at")
        completed_at = _required(completed_at, "review completed_at")
        if active_seconds < 0:
            raise ValueError("active_seconds must be nonnegative")
        presentation = self.connection.execute(
            """
            SELECT score_run_id FROM score_presentations
            WHERE mvp_run_id = ? AND signal_id = ?
            """,
            (run_id, signal_id),
        ).fetchone()
        if presentation is None:
            raise ValueError("a successful score must be presented before review")
        review_id = str(uuid4())
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO human_reviews (
                    review_id, mvp_run_id, signal_id, presented_score_run_id,
                    label, reason, note, started_at, completed_at,
                    active_seconds, supersedes_review_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    run_id,
                    signal_id,
                    presentation["score_run_id"],
                    label,
                    reason,
                    note,
                    started_at,
                    completed_at,
                    active_seconds,
                    supersedes_review_id,
                ),
            )
        return review_id

    def create_draft(
        self,
        *,
        run_id: str,
        signal_id: str,
        body: str,
        created_at: str | None = None,
    ) -> str:
        body = _required(body, "draft body")
        if len(body) > 180:
            raise ValueError("draft body must not exceed 180 characters")
        draft_id = str(uuid4())
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO draft_runs (
                    draft_run_id, mvp_run_id, signal_id, provider, model,
                    prompt_version, body, status, created_at
                ) VALUES (?, ?, ?, 'manual', NULL, 'MANUAL_DRAFT_V1', ?, 'SUCCEEDED', ?)
                """,
                (draft_id, run_id, signal_id, body, created_at or _now()),
            )
        return draft_id

    def register_outreach(
        self,
        *,
        run_id: str,
        signal_id: str,
        review_id: str,
        draft_run_id: str,
        platform: str,
        subject_key: str,
        approved_text: str,
        sent_at: str,
        source_url: str,
        source_link_opened: bool,
        parent_outreach_action_id: str | None = None,
    ) -> str:
        if source_link_opened is not True:
            raise ValueError("source link must be opened and confirmed")
        if platform not in ("bili", "dy"):
            raise ValueError("invalid outreach platform")
        subject_key = _required(subject_key, "subject_key")
        approved_text = _required(approved_text, "approved_text")
        sent_at = _required(sent_at, "sent_at")
        source_url = _required(source_url, "source_url")
        review = self.connection.execute(
            """
            SELECT presented_score_run_id FROM human_reviews
            WHERE review_id = ? AND mvp_run_id = ? AND signal_id = ?
              AND completed_at IS NOT NULL
            """,
            (review_id, run_id, signal_id),
        ).fetchone()
        if review is None:
            raise ValueError("a completed review is required before outreach")
        draft = self.connection.execute(
            """
            SELECT 1 FROM draft_runs
            WHERE draft_run_id = ? AND mvp_run_id = ? AND signal_id = ?
              AND status = 'SUCCEEDED'
            """,
            (draft_run_id, run_id, signal_id),
        ).fetchone()
        signal = self.connection.execute(
            """
            SELECT signals.platform FROM mvp_run_signals
            JOIN signals ON signals.signal_id = mvp_run_signals.signal_id
            WHERE mvp_run_signals.mvp_run_id = ? AND mvp_run_signals.signal_id = ?
            """,
            (run_id, signal_id),
        ).fetchone()
        if draft is None:
            raise ValueError("a successful draft is required before outreach")
        if signal is None or signal["platform"] != platform:
            raise ValueError("outreach platform must match signal platform")
        outreach_id = str(uuid4())
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO outreach_actions (
                    outreach_action_id, mvp_run_id, signal_id, review_id,
                    score_run_id, draft_run_id, platform, subject_key,
                    approved_text, sent_at, source_url, evidence_summary,
                    source_link_opened, status, parent_outreach_action_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          'SOURCE_LINK_OPENED_CONFIRMED', 1, 'SENT_VERIFIED', ?, ?)
                """,
                (
                    outreach_id,
                    run_id,
                    signal_id,
                    review_id,
                    review["presented_score_run_id"],
                    draft_run_id,
                    platform,
                    subject_key,
                    approved_text,
                    sent_at,
                    source_url,
                    parent_outreach_action_id,
                    _now(),
                ),
            )
        return outreach_id

    def register_response(
        self,
        *,
        run_id: str,
        outreach_action_id: str,
        responder_subject_key: str,
        response_type: str,
        summary: str,
        occurred_at: str,
        verified_at: str,
    ) -> str:
        response_id = str(uuid4())
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO response_events (
                    response_event_id, mvp_run_id, outreach_action_id,
                    responder_subject_key, response_type, summary,
                    occurred_at, verified_at, evidence_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'MANUALLY_VERIFIED')
                """,
                (
                    response_id,
                    run_id,
                    outreach_action_id,
                    _required(responder_subject_key, "responder_subject_key"),
                    _required(response_type, "response_type"),
                    _required(summary, "response summary"),
                    _required(occurred_at, "occurred_at"),
                    _required(verified_at, "verified_at"),
                ),
            )
        return response_id

    def register_interview(
        self,
        *,
        run_id: str,
        response_event_id: str,
        scheduled_at: str,
        completed_at: str,
        summary: dict[str, object],
        next_step: str,
    ) -> str:
        if not summary:
            raise ValueError("interview summary is required")
        interview_id = str(uuid4())
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO interviews (
                    interview_id, mvp_run_id, response_event_id, scheduled_at,
                    completed_at, summary_json, next_step
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    interview_id,
                    run_id,
                    response_event_id,
                    _required(scheduled_at, "scheduled_at"),
                    _required(completed_at, "completed_at"),
                    json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    _required(next_step, "next_step"),
                ),
            )
        return interview_id

    def register_quote(
        self,
        *,
        run_id: str,
        response_event_id: str | None,
        interview_id: str | None,
        scope_summary: str,
        agreed_to_receive_pricing_at: str,
        verified_at: str,
    ) -> str:
        if response_event_id is None and interview_id is None:
            raise ValueError("quote requires a response or interview")
        if response_event_id is not None and interview_id is not None:
            linked = self.connection.execute(
                """
                SELECT 1 FROM interviews
                WHERE interview_id = ? AND mvp_run_id = ? AND response_event_id = ?
                """,
                (interview_id, run_id, response_event_id),
            ).fetchone()
            if linked is None:
                raise ValueError("quote response and interview must share causality")
        quote_id = str(uuid4())
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO quote_opportunities (
                    quote_opportunity_id, mvp_run_id, response_event_id,
                    interview_id, scope_summary, agreed_to_receive_pricing_at,
                    verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    quote_id,
                    run_id,
                    response_event_id,
                    interview_id,
                    _required(scope_summary, "scope_summary"),
                    _required(agreed_to_receive_pricing_at, "pricing agreement time"),
                    _required(verified_at, "verified_at"),
                ),
            )
        return quote_id
