from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import sqlite3
from typing import Callable
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.repository import Repository


_REVIEW_LABELS = frozenset(("HIGH_INTENT", "POSSIBLE", "NOT_LEAD", "UNVERIFIABLE"))
_ACTIVITY_KINDS = frozenset(("REVIEW", "DRAFT"))
_EVENTS = frozenset(
    ("START", "PAUSE_HIDDEN", "PAUSE_IDLE", "RESUME", "COMPLETE", "CANCEL")
)
_INTERVIEW_KEYS = frozenset(
    (
        "customer_source_and_sales_process",
        "weekly_lead_volume_and_loss_point",
        "most_manual_step",
        "current_tools",
        "minimum_agent_scenario_and_decision_process",
    )
)
_INCIDENT_TYPES = frozenset(
    (
        "PLATFORM_PENALTY", "UNAUTHORIZED_COLLECTION", "MIS_SEND",
        "DUPLICATE_HARASSMENT", "SENSITIVE_LEAK", "UNAUTHORIZED_DATA", "BYPASS",
    )
)


def _system_now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _required(value: str, name: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _operator_timestamp(value: str, name: str) -> str:
    raw = _required(value, name)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be a valid date and time") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    return _timestamp(parsed)


@dataclass(frozen=True)
class ActivityResult:
    activity_session_id: str
    state: str
    active_seconds: int | None


@dataclass(frozen=True)
class ActivitySession:
    activity_session_id: str
    state: str


class Workflow:
    """Append-only operator facts. It never performs outbound platform I/O."""

    def __init__(
        self, repository: Repository, *, now: Callable[[], datetime] | None = None
    ):
        self.repository = repository
        self.connection = repository.connection
        self._now = now or _system_now

    def _timestamp(self) -> str:
        return _timestamp(self._now())

    def _require_active_run(self, run_id: str) -> None:
        row = self.connection.execute(
            "SELECT state, day14_due_at FROM mvp_runs WHERE mvp_run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown mvp run: {run_id}")
        if row["state"] != "ACTIVE":
            raise ValueError("operator facts require an ACTIVE mvp run")
        if _parse(self._timestamp()) > _parse(str(row["day14_due_at"])):
            raise ValueError("operator facts are closed after the Day 14 cutoff")

    def start_activity(self, run_id: str, signal_id: str, activity_kind: str) -> str:
        self._require_active_run(run_id)
        if activity_kind not in _ACTIVITY_KINDS:
            raise ValueError("activity kind must be REVIEW or DRAFT")
        existing = self.connection.execute(
            """
            SELECT activity_session_id FROM activity_sessions
            WHERE mvp_run_id = ? AND signal_id = ? AND activity_kind = ?
              AND state IN ('OPEN', 'PAUSED')
            """,
            (run_id, signal_id, activity_kind),
        ).fetchone()
        if existing is not None:
            return str(existing["activity_session_id"])
        session_id = str(uuid4())
        now = self._timestamp()
        try:
            with self.connection:
                self.connection.execute(
                    """
                    INSERT INTO activity_sessions (
                        activity_session_id, mvp_run_id, signal_id,
                        activity_kind, state, started_at
                    ) VALUES (?, ?, ?, ?, 'OPEN', ?)
                    """,
                    (session_id, run_id, signal_id, activity_kind, now),
                )
                self.connection.execute(
                    """
                    INSERT INTO activity_events (
                        activity_event_id, activity_session_id, mvp_run_id,
                        signal_id, activity_kind, sequence_no, event_kind, received_at
                    ) VALUES (?, ?, ?, ?, ?, 1, 'START', ?)
                    """,
                    (str(uuid4()), session_id, run_id, signal_id, activity_kind, now),
                )
        except sqlite3.IntegrityError as error:
            if "one_open_activity_per_subject" in str(error):
                raise ValueError("an open activity session already exists") from error
            raise
        return session_id

    def activity_session(self, session_id: str) -> ActivitySession:
        row = self.connection.execute(
            "SELECT state FROM activity_sessions WHERE activity_session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown activity session: {session_id}")
        return ActivitySession(session_id, str(row["state"]))

    def record_activity(self, session_id: str, event_kind: str) -> ActivityResult:
        if event_kind not in _EVENTS or event_kind == "START":
            raise ValueError("invalid activity event")
        session = self.connection.execute(
            "SELECT * FROM activity_sessions WHERE activity_session_id = ?",
            (session_id,),
        ).fetchone()
        if session is None:
            raise KeyError(f"unknown activity session: {session_id}")
        self._require_active_run(str(session["mvp_run_id"]))
        state = str(session["state"])
        allowed = {
            "OPEN": {"PAUSE_HIDDEN", "PAUSE_IDLE", "COMPLETE", "CANCEL"},
            "PAUSED": {"RESUME", "CANCEL"},
        }
        if event_kind not in allowed.get(state, set()):
            raise ValueError("invalid activity transition")
        now = self._timestamp()
        latest = self.connection.execute(
            """
            SELECT sequence_no, received_at FROM activity_events
            WHERE activity_session_id = ? ORDER BY sequence_no DESC LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        if latest is None or _parse(now) < _parse(str(latest["received_at"])):
            raise ValueError("activity server clock moved backwards")
        next_state = {
            "PAUSE_HIDDEN": "PAUSED",
            "PAUSE_IDLE": "PAUSED",
            "RESUME": "OPEN",
            "COMPLETE": "COMPLETED",
            "CANCEL": "CANCELLED",
        }[event_kind]
        sequence = int(latest["sequence_no"]) + 1
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO activity_events (
                    activity_event_id, activity_session_id, mvp_run_id,
                    signal_id, activity_kind, sequence_no, event_kind, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()), session_id, session["mvp_run_id"],
                    session["signal_id"], session["activity_kind"], sequence,
                    event_kind, now,
                ),
            )
            active_seconds = None
            completed_at = None
            if next_state in ("COMPLETED", "CANCELLED"):
                completed_at = now
                active_seconds = self._active_seconds(session_id)
            self.connection.execute(
                """
                UPDATE activity_sessions
                SET state = ?, completed_at = ?, active_seconds = ?
                WHERE activity_session_id = ?
                """,
                (next_state, completed_at, active_seconds, session_id),
            )
        return ActivityResult(session_id, next_state, active_seconds)

    def _active_seconds(self, session_id: str) -> int:
        rows = self.connection.execute(
            """
            SELECT event_kind, received_at FROM activity_events
            WHERE activity_session_id = ? ORDER BY sequence_no
            """,
            (session_id,),
        ).fetchall()
        active_from: datetime | None = None
        active = timedelta()
        for row in rows:
            kind = str(row["event_kind"])
            received = _parse(str(row["received_at"]))
            if kind in ("START", "RESUME"):
                active_from = received
            elif kind in ("PAUSE_HIDDEN", "PAUSE_IDLE", "COMPLETE", "CANCEL"):
                if active_from is not None:
                    interval = received - active_from
                    if kind == "PAUSE_IDLE":
                        interval = max(interval - timedelta(seconds=60), timedelta())
                    active += interval
                    active_from = None
        return max(0, int(active.total_seconds()))

    def present_score(self, run_id: str, signal_id: str, score_run_id: str) -> str:
        self._require_active_run(run_id)
        existing = self.connection.execute(
            "SELECT score_run_id FROM score_presentations "
            "WHERE mvp_run_id = ? AND signal_id = ?",
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
                (str(uuid4()), run_id, signal_id, score_run_id, self._timestamp()),
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
        activity_session_id: str,
        supersedes_review_id: str | None = None,
    ) -> str:
        self._require_active_run(run_id)
        if label not in _REVIEW_LABELS:
            raise ValueError("invalid human review label")
        reason = _required(reason, "review reason")
        presentation = self.connection.execute(
            "SELECT score_run_id FROM score_presentations "
            "WHERE mvp_run_id = ? AND signal_id = ?",
            (run_id, signal_id),
        ).fetchone()
        if presentation is None:
            raise ValueError("a successful score must be presented before review")
        session = self.connection.execute(
            """
            SELECT * FROM activity_sessions
            WHERE activity_session_id = ? AND mvp_run_id = ? AND signal_id = ?
              AND activity_kind = 'REVIEW' AND state = 'COMPLETED'
            """,
            (activity_session_id, run_id, signal_id),
        ).fetchone()
        if session is None:
            raise ValueError("a completed REVIEW activity session is required")
        current = self.connection.execute(
            """
            SELECT review.review_id FROM human_reviews review
            WHERE review.mvp_run_id = ? AND review.signal_id = ?
              AND NOT EXISTS (
                  SELECT 1 FROM human_reviews child
                  WHERE child.supersedes_review_id = review.review_id
              )
            """,
            (run_id, signal_id),
        ).fetchone()
        if current is None and supersedes_review_id is not None:
            raise ValueError("first review cannot supersede another review")
        if current is not None and supersedes_review_id != current["review_id"]:
            raise ValueError("revision must supersede the current review")
        review_id = str(uuid4())
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO human_reviews (
                    review_id, mvp_run_id, signal_id, presented_score_run_id,
                    label, reason, note, activity_session_id, started_at,
                    completed_at, active_seconds, supersedes_review_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id, run_id, signal_id, presentation["score_run_id"],
                    label, reason, note, activity_session_id, session["started_at"],
                    session["completed_at"], session["active_seconds"],
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
        activity_session_id: str,
    ) -> str:
        self._require_active_run(run_id)
        body = _required(body, "draft body")
        if len(body) > 180:
            raise ValueError("draft body must not exceed 180 characters")
        session = self.connection.execute(
            """
            SELECT 1 FROM activity_sessions
            WHERE activity_session_id = ? AND mvp_run_id = ? AND signal_id = ?
              AND activity_kind = 'DRAFT' AND state = 'COMPLETED'
            """,
            (activity_session_id, run_id, signal_id),
        ).fetchone()
        if session is None:
            raise ValueError("a completed DRAFT activity session is required")
        draft_id = str(uuid4())
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO draft_runs (
                    draft_run_id, mvp_run_id, signal_id, provider, model,
                    prompt_version, draft_kind, body, status,
                    activity_session_id, created_at
                ) VALUES (?, ?, ?, 'human', NULL, 'HUMAN_DRAFT_V1',
                          'HUMAN_EDITED', ?, 'SUCCEEDED', ?, ?)
                """,
                (draft_id, run_id, signal_id, body, activity_session_id, self._timestamp()),
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
        context_evidence: str,
        sent_at: str,
        source_url: str,
        source_link_opened: bool,
        parent_outreach_action_id: str | None = None,
    ) -> str:
        self._require_active_run(run_id)
        if source_link_opened is not True:
            raise ValueError("source link must be opened and confirmed")
        if platform not in ("bili", "dy"):
            raise ValueError("invalid outreach platform")
        approved_text = _required(approved_text, "approved_text")
        context_evidence = _required(context_evidence, "context_evidence")
        if context_evidence not in approved_text:
            raise ValueError("context evidence must occur verbatim in approved text")
        if context_evidence not in self.repository.get_signal_source_text(run_id, signal_id):
            raise ValueError("context evidence must occur verbatim in source text")
        review = self.connection.execute(
            """
            SELECT presented_score_run_id FROM human_reviews current
            WHERE review_id = ? AND mvp_run_id = ? AND signal_id = ?
              AND completed_at IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM human_reviews child
                WHERE child.supersedes_review_id = current.review_id
              )
            """,
            (review_id, run_id, signal_id),
        ).fetchone()
        if review is None:
            raise ValueError("outreach review must be the current leaf review")
        draft = self.connection.execute(
            """
            SELECT 1 FROM draft_runs
            WHERE draft_run_id = ? AND mvp_run_id = ? AND signal_id = ?
              AND status = 'SUCCEEDED' AND draft_kind = 'HUMAN_EDITED'
            """,
            (draft_run_id, run_id, signal_id),
        ).fetchone()
        signal = self.connection.execute(
            """
            SELECT signals.platform, signals.author_public_id FROM mvp_run_signals
            JOIN signals ON signals.signal_id = mvp_run_signals.signal_id
            WHERE mvp_run_signals.mvp_run_id = ? AND mvp_run_signals.signal_id = ?
            """,
            (run_id, signal_id),
        ).fetchone()
        if draft is None:
            raise ValueError("a human-edited completed draft is required before outreach")
        if signal is None or signal["platform"] != platform:
            raise ValueError("outreach platform must match signal platform")
        expected_subject = f"{signal['platform']}:{signal['author_public_id']}"
        if _required(subject_key, "subject_key") != expected_subject:
            raise ValueError("outreach subject must match the signal author")
        subject_key = expected_subject
        parent = None
        if parent_outreach_action_id is not None:
            parent = self.connection.execute(
                """
                SELECT sent_at FROM outreach_actions
                WHERE outreach_action_id = ? AND mvp_run_id = ? AND signal_id = ?
                  AND platform = ? AND subject_key = ?
                  AND parent_outreach_action_id IS NULL
                """,
                (
                    parent_outreach_action_id, run_id, signal_id,
                    platform, subject_key,
                ),
            ).fetchone()
            if parent is None:
                raise ValueError("follow-up parent must be the matching first contact")
        sent_timestamp = _operator_timestamp(sent_at, "sent_at")
        if parent is not None and sent_timestamp < str(parent["sent_at"]):
            raise ValueError("follow-up sent_at must follow the first contact")
        ready_at = self.connection.execute(
            """
            SELECT review.completed_at, draft.created_at
            FROM human_reviews review
            JOIN draft_runs draft ON draft.draft_run_id = ?
            WHERE review.review_id = ?
            """,
            (draft_run_id, review_id),
        ).fetchone()
        if ready_at is None or sent_timestamp < max(str(ready_at[0]), str(ready_at[1])):
            raise ValueError("outreach sent_at must follow review and draft completion")
        outreach_id = str(uuid4())
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO outreach_actions (
                    outreach_action_id, mvp_run_id, signal_id, review_id,
                    score_run_id, draft_run_id, platform, subject_key,
                    approved_text, sent_at, source_url, context_evidence,
                    evidence_summary, source_link_opened, status,
                    parent_outreach_action_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1,
                          'SENT_VERIFIED', ?, ?)
                """,
                (
                    outreach_id, run_id, signal_id, review_id,
                    review["presented_score_run_id"], draft_run_id, platform,
                    subject_key, approved_text, sent_timestamp,
                    _required(source_url, "source_url"), context_evidence,
                    context_evidence, parent_outreach_action_id, self._timestamp(),
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
        evidence_summary: str | None,
    ) -> str:
        self._require_active_run(run_id)
        if response_type not in ("VALID", "INVALID"):
            raise ValueError("response_type must be VALID or INVALID")
        outreach = self.connection.execute(
            """
            SELECT subject_key, status FROM outreach_actions
            WHERE outreach_action_id = ? AND mvp_run_id = ?
            """,
            (outreach_action_id, run_id),
        ).fetchone()
        if outreach is None:
            raise ValueError("response requires an outreach fact")
        if _required(responder_subject_key, "responder_subject_key") != outreach["subject_key"]:
            raise ValueError("response subject must match outreach")
        if response_type == "VALID" and outreach["status"] != "SENT_VERIFIED":
            raise ValueError("valid response requires verified sent outreach")
        if response_type == "VALID":
            evidence_summary = _required(evidence_summary or "", "response evidence")
        elif evidence_summary is not None:
            evidence_summary = evidence_summary.strip() or None
        occurred_timestamp = _operator_timestamp(occurred_at, "occurred_at")
        verified_timestamp = _operator_timestamp(verified_at, "verified_at")
        sent_at = self.connection.execute(
            "SELECT sent_at FROM outreach_actions WHERE outreach_action_id = ?",
            (outreach_action_id,),
        ).fetchone()[0]
        if occurred_timestamp < sent_at or verified_timestamp < occurred_timestamp:
            raise ValueError("response time must follow the sent outreach")
        response_id = str(uuid4())
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO response_events (
                    response_event_id, mvp_run_id, outreach_action_id,
                    responder_subject_key, response_type, summary, occurred_at,
                    verified_at, evidence_summary, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    response_id, run_id, outreach_action_id,
                    outreach["subject_key"],
                    response_type, _required(summary, "response summary"),
                    occurred_timestamp, verified_timestamp, evidence_summary,
                    self._timestamp(),
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
        solution_fit: str,
        next_step: str,
    ) -> str:
        self._require_active_run(run_id)
        if set(summary) != _INTERVIEW_KEYS or any(
            not isinstance(summary[key], str) or not str(summary[key]).strip()
            for key in _INTERVIEW_KEYS
        ):
            raise ValueError("interview summary requires exactly five nonblank answers")
        if solution_fit not in ("SOLVABLE", "UNSOLVABLE", "UNKNOWN"):
            raise ValueError("invalid solution_fit")
        if not self.connection.execute(
            "SELECT 1 FROM response_events WHERE response_event_id = ? "
            "AND mvp_run_id = ? AND response_type = 'VALID'",
            (response_event_id, run_id),
        ).fetchone():
            raise ValueError("interview requires a verified VALID response")
        scheduled_timestamp = _operator_timestamp(scheduled_at, "scheduled_at")
        completed_timestamp = _operator_timestamp(completed_at, "completed_at")
        response_verified_at = self.connection.execute(
            "SELECT verified_at FROM response_events WHERE response_event_id = ?",
            (response_event_id,),
        ).fetchone()[0]
        if scheduled_timestamp > completed_timestamp or completed_timestamp < response_verified_at:
            raise ValueError("interview time must follow the verified response")
        interview_id = str(uuid4())
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO interviews (
                    interview_id, mvp_run_id, response_event_id, scheduled_at,
                    completed_at, summary_json, solution_fit, next_step, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    interview_id, run_id, response_event_id,
                    scheduled_timestamp, completed_timestamp,
                    json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    solution_fit, _required(next_step, "next_step"), self._timestamp(),
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
        self._require_active_run(run_id)
        if response_event_id is None and interview_id is None:
            raise ValueError("quote requires a response or interview")
        linked = self.connection.execute(
            """
            SELECT response.response_event_id
            FROM response_events response
            LEFT JOIN interviews interview
              ON interview.interview_id = ? AND interview.mvp_run_id = ?
            WHERE response.mvp_run_id = ?
              AND response.response_event_id = coalesce(?, interview.response_event_id)
              AND response.response_type = 'VALID'
              AND (? IS NULL OR ? IS NULL OR interview.response_event_id = ?)
            """,
            (
                interview_id, run_id, run_id, response_event_id,
                response_event_id, interview_id, response_event_id,
            ),
        ).fetchone()
        if linked is None:
            raise ValueError("quote requires a verified VALID response chain")
        agreement_timestamp = _operator_timestamp(
            agreed_to_receive_pricing_at, "pricing agreement time"
        )
        verified_timestamp = _operator_timestamp(verified_at, "verified_at")
        parent_time = self.connection.execute(
            """
            SELECT max(response.verified_at, coalesce(interview.completed_at, response.verified_at))
            FROM response_events response
            LEFT JOIN interviews interview ON interview.interview_id = ?
            WHERE response.response_event_id = ?
            """,
            (interview_id, linked["response_event_id"]),
        ).fetchone()[0]
        if agreement_timestamp < parent_time or verified_timestamp < agreement_timestamp:
            raise ValueError("quote time must follow the verified business chain")
        quote_id = str(uuid4())
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO quote_opportunities (
                    quote_opportunity_id, mvp_run_id, response_event_id,
                    interview_id, scope_summary, agreed_to_receive_pricing_at,
                    verified_at, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    quote_id, run_id, response_event_id, interview_id,
                    _required(scope_summary, "scope_summary"),
                    agreement_timestamp, verified_timestamp, self._timestamp(),
                ),
            )
        return quote_id

    def register_incident(
        self, *, run_id: str, event_type: str, platform: str | None, summary: str
    ) -> str:
        self._require_active_run(run_id)
        if event_type not in _INCIDENT_TYPES:
            raise ValueError("invalid incident type")
        if platform not in (None, "bili", "dy"):
            raise ValueError("invalid incident platform")
        incident_id = str(uuid4())
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO risk_events (
                    risk_event_id, mvp_run_id, event_type, severity, platform,
                    summary, verified_at, forces_stop
                ) VALUES (?, ?, ?, 'CONFIRMED', ?, ?, ?, 1)
                """,
                (
                    incident_id, run_id, event_type, platform,
                    _required(summary, "incident summary"), self._timestamp(),
                ),
            )
        return incident_id
