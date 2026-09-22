from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from typing import Any, Iterator
from urllib.parse import urlparse

try:
    from .domain import evidence_decision, now_iso, normalize
except ImportError:  # running server.py directly
    from domain import evidence_decision, now_iso, normalize


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    name TEXT NOT NULL,
    objective TEXT NOT NULL,
    criteria_json TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    profile_id TEXT REFERENCES profiles(id),
    objective TEXT NOT NULL,
    criteria_json TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_limit INTEGER NOT NULL DEFAULT 10,
    estimated_credits INTEGER NOT NULL DEFAULT 0,
    used_credits INTEGER NOT NULL DEFAULT 0,
    idempotency_key TEXT UNIQUE,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS task_plans (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL UNIQUE REFERENCES tasks(id),
    planner_version TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_runs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_limit INTEGER NOT NULL,
    candidate_count INTEGER NOT NULL DEFAULT 0,
    verified_count INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    idempotency_key TEXT UNIQUE,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS task_run_events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES task_runs(id),
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    objective TEXT NOT NULL,
    criteria_json TEXT NOT NULL,
    requested_limit INTEGER NOT NULL,
    interval_minutes INTEGER NOT NULL,
    max_credits_per_run INTEGER NOT NULL,
    max_total_credits INTEGER,
    min_new_results INTEGER NOT NULL DEFAULT 0,
    failure_policy TEXT NOT NULL,
    approval_policy TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    next_run_at TEXT NOT NULL,
    last_run_at TEXT,
    run_count INTEGER NOT NULL DEFAULT 0,
    total_credits INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scheduled_task_runs (
    id TEXT PRIMARY KEY,
    schedule_id TEXT NOT NULL REFERENCES scheduled_tasks(id),
    task_id TEXT REFERENCES tasks(id),
    status TEXT NOT NULL,
    scheduled_for TEXT NOT NULL,
    candidate_count INTEGER NOT NULL DEFAULT 0,
    new_result_count INTEGER NOT NULL DEFAULT 0,
    credits_used INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    message TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS opportunities (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    task_id TEXT NOT NULL REFERENCES tasks(id),
    status TEXT NOT NULL,
    title TEXT NOT NULL,
    author TEXT,
    published_at TEXT,
    intent_type TEXT,
    industry_location TEXT,
    source_kind TEXT NOT NULL,
    source_url TEXT NOT NULL,
    snippet TEXT NOT NULL,
    evidence_level TEXT NOT NULL DEFAULT 'UNVERIFIED',
    source_permission TEXT NOT NULL DEFAULT 'unknown',
    score REAL NOT NULL DEFAULT 0,
    decision_json TEXT NOT NULL DEFAULT '{}',
    dedup_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(workspace_id, dedup_key)
);

CREATE TABLE IF NOT EXISTS feed_events (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    task_id TEXT REFERENCES tasks(id),
    opportunity_id TEXT REFERENCES opportunities(id),
    event_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'NEW',
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    source_url TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    published_at TEXT,
    observed_at TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    review_note TEXT,
    reviewed_by TEXT,
    reviewed_at TEXT,
    dedup_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(workspace_id, dedup_key)
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
    evidence_type TEXT NOT NULL,
    content TEXT NOT NULL,
    url TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    captured_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    entity_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    website_host TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL,
    resolution_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(workspace_id, entity_type, canonical_name, website_host)
);

CREATE TABLE IF NOT EXISTS opportunity_entities (
    id TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
    entity_id TEXT NOT NULL REFERENCES entities(id),
    relation TEXT NOT NULL,
    confidence REAL NOT NULL,
    resolution_reason TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(opportunity_id, entity_id)
);

CREATE TABLE IF NOT EXISTS feedback_events (
    id TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
    label TEXT NOT NULL,
    note TEXT,
    actor TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_ledger (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    task_id TEXT REFERENCES tasks(id),
    operation TEXT NOT NULL,
    units INTEGER NOT NULL,
    credits INTEGER NOT NULL,
    status TEXT NOT NULL,
    idempotency_key TEXT,
    source_id TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT 'CHARGED',
    unit TEXT NOT NULL DEFAULT 'SOUBEI',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(workspace_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS source_proofs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    proof_ref TEXT NOT NULL,
    provider TEXT NOT NULL,
    source_family TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    checks_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    revoked_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(workspace_id, proof_ref)
);

CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calibration_batches (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    name TEXT NOT NULL,
    target_count INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    created_at TEXT NOT NULL,
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS calibration_items (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES calibration_batches(id),
    opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
    predicted_label TEXT NOT NULL,
    gold_label TEXT,
    reviewer TEXT,
    note TEXT,
    reviewed_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(batch_id, opportunity_id)
);

CREATE TABLE IF NOT EXISTS action_drafts (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
    channel TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT',
    subject TEXT,
    body TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL DEFAULT '[]',
    idempotency_key TEXT UNIQUE,
    created_by TEXT NOT NULL,
    approved_by TEXT,
    approved_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_workspace_created ON tasks(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_opportunities_workspace_updated ON opportunities(workspace_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities(status);
CREATE INDEX IF NOT EXISTS idx_feed_events_workspace_observed ON feed_events(workspace_id, observed_at DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feed_events_type_status ON feed_events(workspace_id, event_type, status, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_entities_workspace ON entities(workspace_id, entity_type, canonical_name);
CREATE INDEX IF NOT EXISTS idx_entities_host ON entities(workspace_id, website_host);
CREATE INDEX IF NOT EXISTS idx_opportunity_entities_entity ON opportunity_entities(entity_id);
CREATE INDEX IF NOT EXISTS idx_task_run_events_run_created ON task_run_events(run_id, created_at);
CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_workspace_status ON scheduled_tasks(workspace_id, status, next_run_at);
CREATE INDEX IF NOT EXISTS idx_scheduled_task_runs_schedule_created ON scheduled_task_runs(schedule_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scheduled_task_runs_task ON scheduled_task_runs(task_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_calibration_batches_workspace_created ON calibration_batches(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_calibration_items_batch_created ON calibration_items(batch_id, created_at);
CREATE INDEX IF NOT EXISTS idx_action_drafts_opportunity_created ON action_drafts(opportunity_id, created_at DESC);
"""


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


PLATFORM_HOSTS = {
    "xiaohongshu.com",
    "www.xiaohongshu.com",
    "xhslink.com",
    "douyin.com",
    "www.douyin.com",
    "tiktok.com",
    "www.tiktok.com",
    "weibo.com",
    "www.weibo.com",
    "bilibili.com",
    "www.bilibili.com",
    "zhihu.com",
    "www.zhihu.com",
}

CALIBRATION_LABELS = {"VALID", "INVALID", "DUPLICATE", "OBSERVE", "NEEDS_EVIDENCE"}
ACTION_CHANNELS = {"PUBLIC_REPLY", "EMAIL", "FEISHU_TASK", "CRM_TASK"}
ACTION_CHANNEL_ORDER = ["PUBLIC_REPLY", "EMAIL", "FEISHU_TASK", "CRM_TASK"]
CALIBRATION_NAME_MAX = 120
CALIBRATION_REVIEWER_MAX = 120
CALIBRATION_NOTE_MAX = 4000
FEED_EVENT_TYPES = {"PURCHASE_DEMAND", "HIRING", "TENDER", "WEBSITE_CHANGE", "COMPETITOR_CHANGE"}
FEED_EVENT_STATUSES = {"NEW", "REVIEWED", "DISMISSED"}


def predicted_calibration_label(status: str) -> str:
    return {
        "SEND_READY": "VALID",
        "EXCLUDE": "INVALID",
        "OBSERVE": "OBSERVE",
        "REVIEW": "NEEDS_EVIDENCE",
    }.get(status, "NEEDS_EVIDENCE")


def normalize_entity_name(value: Any) -> str:
    value = normalize(str(value or ""))
    return " ".join(value.split())


def normalize_host(value: Any) -> str:
    raw = str(value or "").strip().lower().rstrip(".")
    if not raw:
        return ""
    if "://" in raw:
        raw = urlparse(raw).hostname or ""
    if raw.startswith("www."):
        raw = raw[4:]
    return raw


def source_host(value: Any) -> str:
    return normalize_host(urlparse(str(value or "")).hostname)


def is_platform_host(host: str) -> bool:
    host = normalize_host(host)
    return host in PLATFORM_HOSTS or any(host.endswith("." + suffix) for suffix in PLATFORM_HOSTS)


class Store:
    def __init__(self, path: str = "lead_radar.sqlite3") -> None:
        self.path = path
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.lock:
            self.db.executescript(SCHEMA)
            columns = {row["name"] for row in self.db.execute("PRAGMA table_info(evidence)").fetchall()}
            if "metadata_json" not in columns:
                self.db.execute("ALTER TABLE evidence ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'")
            opportunity_columns = {row["name"] for row in self.db.execute("PRAGMA table_info(opportunities)").fetchall()}
            if "decision_json" not in opportunity_columns:
                self.db.execute("ALTER TABLE opportunities ADD COLUMN decision_json TEXT NOT NULL DEFAULT '{}'")
            proof_columns = {row["name"] for row in self.db.execute("PRAGMA table_info(source_proofs)").fetchall()}
            if "status" not in proof_columns:
                self.db.execute("ALTER TABLE source_proofs ADD COLUMN status TEXT NOT NULL DEFAULT 'ACTIVE'")
            if "revoked_at" not in proof_columns:
                self.db.execute("ALTER TABLE source_proofs ADD COLUMN revoked_at TEXT")
            usage_columns = {row["name"] for row in self.db.execute("PRAGMA table_info(usage_ledger)").fetchall()}
            if "source_id" not in usage_columns:
                self.db.execute("ALTER TABLE usage_ledger ADD COLUMN source_id TEXT NOT NULL DEFAULT ''")
            if "outcome" not in usage_columns:
                self.db.execute("ALTER TABLE usage_ledger ADD COLUMN outcome TEXT NOT NULL DEFAULT 'CHARGED'")
            if "unit" not in usage_columns:
                self.db.execute("ALTER TABLE usage_ledger ADD COLUMN unit TEXT NOT NULL DEFAULT 'SOUBEI'")
            if "metadata_json" not in usage_columns:
                self.db.execute("ALTER TABLE usage_ledger ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'")
            self.db.execute(
                "INSERT OR IGNORE INTO workspaces(id, name, created_at) VALUES (?, ?, ?)",
                ("ws_意客AI", "意客 AI 商机雷达", now_iso()),
            )
            self.db.commit()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self.lock:
            try:
                yield self.db
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise

    def close(self) -> None:
        with self.lock:
            self.db.close()

    def create_profile(self, workspace_id: str, name: str, objective: str, criteria: dict[str, Any]) -> dict[str, Any]:
        profile_id = _id("profile")
        created_at = now_iso()
        with self.tx() as db:
            db.execute(
                "INSERT INTO profiles(id, workspace_id, name, objective, criteria_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (profile_id, workspace_id, name, objective, _json(criteria), created_at),
            )
            self._audit(db, workspace_id, "profile", profile_id, "created", {"name": name})
        return self.get_profile(profile_id)  # type: ignore[return-value]

    def get_profile(self, profile_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        result = _decode(row)
        if result:
            result["criteria"] = json.loads(result.pop("criteria_json"))
        return result

    def create_task(
        self,
        workspace_id: str,
        profile_id: str | None,
        objective: str,
        criteria: dict[str, Any],
        requested_limit: int,
        estimated_credits: int,
        idempotency_key: str | None,
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        if idempotency_key:
            with self.lock:
                existing = self.db.execute("SELECT * FROM tasks WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
            if existing:
                return self._task_dict(existing)
        task_id = _id("task")
        created_at = now_iso()
        with self.tx() as db:
            db.execute(
                """INSERT INTO tasks
                (id, workspace_id, profile_id, objective, criteria_json, status, requested_limit,
                 estimated_credits, idempotency_key, created_at)
                VALUES (?, ?, ?, ?, ?, 'PLANNED', ?, ?, ?, ?)""",
                (task_id, workspace_id, profile_id, objective, _json(criteria), requested_limit, estimated_credits, idempotency_key, created_at),
            )
            db.execute(
                "INSERT INTO task_plans(id, task_id, planner_version, plan_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (_id("plan"), task_id, plan["planner_version"], _json(plan), created_at),
            )
            self._audit(db, workspace_id, "task", task_id, "created", {"objective": objective})
            self._audit(db, workspace_id, "task", task_id, "plan_generated", {"planner_version": plan["planner_version"]})
        return self.get_task(task_id)  # type: ignore[return-value]

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._task_dict(row)

    def _task_dict(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        result = _decode(row)
        if result:
            result["criteria"] = json.loads(result.pop("criteria_json"))
            with self.lock:
                plan_row = self.db.execute("SELECT plan_json FROM task_plans WHERE task_id = ?", (result["id"],)).fetchone()
                run_rows = self.db.execute(
                    "SELECT id, mode, status, requested_limit, candidate_count, verified_count, error_code, created_at, started_at, finished_at FROM task_runs WHERE task_id = ? ORDER BY created_at DESC, rowid DESC",
                    (result["id"],),
                ).fetchall()
                run_event_rows = self.db.execute(
                    "SELECT run_id, id, event_type, status, message, payload_json, created_at FROM task_run_events WHERE run_id IN (SELECT id FROM task_runs WHERE task_id = ?) ORDER BY created_at",
                    (result["id"],),
                ).fetchall()
            result["plan"] = json.loads(plan_row["plan_json"]) if plan_row else None
            events_by_run: dict[str, list[dict[str, Any]]] = {}
            for event in run_event_rows:
                entry = dict(event)
                entry["payload"] = json.loads(entry.pop("payload_json") or "{}")
                events_by_run.setdefault(entry.pop("run_id"), []).append(entry)
            result["runs"] = []
            for run in run_rows:
                run_dict = dict(run)
                run_dict["events"] = events_by_run.get(run_dict["id"], [])
                result["runs"].append(run_dict)
        return result

    def list_tasks(self, workspace_id: str) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.db.execute("SELECT * FROM tasks WHERE workspace_id = ? ORDER BY created_at DESC", (workspace_id,)).fetchall()
        return [self._task_dict(row) for row in rows]  # type: ignore[list-item]

    def create_scheduled_task(
        self,
        workspace_id: str,
        objective: str,
        criteria: dict[str, Any],
        requested_limit: int,
        interval_minutes: int,
        max_credits_per_run: int,
        max_total_credits: int | None,
        min_new_results: int,
        failure_policy: str,
        approval_policy: str,
        next_run_at: str,
        created_by: str,
    ) -> dict[str, Any] | None:
        schedule_id = _id("schedule")
        timestamp = now_iso()
        with self.tx() as db:
            workspace = db.execute("SELECT id FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
            if not workspace:
                return None
            db.execute(
                """INSERT INTO scheduled_tasks
                   (id, workspace_id, objective, criteria_json, requested_limit,
                    interval_minutes, max_credits_per_run, max_total_credits,
                    min_new_results, failure_policy, approval_policy, status,
                    next_run_at, created_by, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?)""",
                (
                    schedule_id,
                    workspace_id,
                    objective,
                    _json(criteria),
                    requested_limit,
                    interval_minutes,
                    max_credits_per_run,
                    max_total_credits,
                    min_new_results,
                    failure_policy,
                    approval_policy,
                    next_run_at,
                    created_by,
                    timestamp,
                    timestamp,
                ),
            )
            self._audit(
                db,
                workspace_id,
                "scheduled_task",
                schedule_id,
                "created",
                {
                    "interval_minutes": interval_minutes,
                    "max_credits_per_run": max_credits_per_run,
                    "max_total_credits": max_total_credits,
                    "min_new_results": min_new_results,
                    "failure_policy": failure_policy,
                    "approval_policy": approval_policy,
                },
            )
        return self.get_scheduled_task(schedule_id, workspace_id)

    @staticmethod
    def _scheduled_task_run_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return _decode(row)

    def _scheduled_task_dict(self, row: sqlite3.Row | None, include_runs: bool = True) -> dict[str, Any] | None:
        result = _decode(row)
        if not result:
            return None
        result["criteria"] = json.loads(result.pop("criteria_json") or "{}")
        if include_runs:
            with self.lock:
                run_rows = self.db.execute(
                    """SELECT id, schedule_id, task_id, status, scheduled_for,
                              candidate_count, new_result_count, credits_used,
                              error_code, message, idempotency_key, created_at,
                              started_at, finished_at
                       FROM scheduled_task_runs
                       WHERE schedule_id = ?
                       ORDER BY created_at DESC, rowid DESC
                       LIMIT 50""",
                    (result["id"],),
                ).fetchall()
            result["runs"] = [self._scheduled_task_run_dict(item) for item in run_rows]
            result["latest_run"] = result["runs"][0] if result["runs"] else None
        return result

    def get_scheduled_task(self, schedule_id: str, workspace_id: str | None = None) -> dict[str, Any] | None:
        query = "SELECT * FROM scheduled_tasks WHERE id = ?"
        params: list[Any] = [schedule_id]
        if workspace_id is not None:
            query += " AND workspace_id = ?"
            params.append(workspace_id)
        with self.lock:
            row = self.db.execute(query, params).fetchone()
        return self._scheduled_task_dict(row)

    def list_scheduled_tasks(self, workspace_id: str) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.db.execute(
                "SELECT * FROM scheduled_tasks WHERE workspace_id = ? ORDER BY status, next_run_at, created_at DESC",
                (workspace_id,),
            ).fetchall()
        return [self._scheduled_task_dict(row, include_runs=False) for row in rows]  # type: ignore[list-item]

    def control_scheduled_task(self, schedule_id: str, workspace_id: str, action: str, actor: str = "operator") -> dict[str, Any] | None:
        if action not in {"pause", "resume"}:
            raise ValueError("invalid_schedule_action")
        actor = str(actor or "operator").strip() or "operator"
        with self.tx() as db:
            row = db.execute(
                "SELECT * FROM scheduled_tasks WHERE id = ? AND workspace_id = ?",
                (schedule_id, workspace_id),
            ).fetchone()
            if not row:
                return None
            current = row["status"]
            if action == "pause":
                if current == "PAUSED":
                    return self._scheduled_task_dict(row)
                if current in {"EXHAUSTED", "ARCHIVED"}:
                    raise ValueError("schedule_not_pauseable")
                next_status = "PAUSED"
            else:
                if current == "ACTIVE":
                    return self._scheduled_task_dict(row)
                if current in {"EXHAUSTED", "ARCHIVED"}:
                    raise ValueError("schedule_not_resumable")
                next_status = "ACTIVE"
            timestamp = now_iso()
            db.execute(
                "UPDATE scheduled_tasks SET status = ?, next_run_at = CASE WHEN ? = 'ACTIVE' AND next_run_at < ? THEN ? ELSE next_run_at END, updated_at = ? WHERE id = ?",
                (next_status, next_status, timestamp, timestamp, timestamp, schedule_id),
            )
            self._audit(
                db,
                workspace_id,
                "scheduled_task",
                schedule_id,
                action,
                {"actor": actor, "from_status": current, "to_status": next_status},
            )
        return self.get_scheduled_task(schedule_id, workspace_id)

    def trigger_scheduled_task(
        self,
        schedule_id: str,
        workspace_id: str,
        plan: dict[str, Any],
        actor: str = "scheduler",
        scheduled_for: str | None = None,
    ) -> dict[str, Any] | None:
        """Reserve one due schedule occurrence without pretending to run a source.

        A runnable plan becomes a QUEUED schedule run and a PLANNED task for the
        existing worker. A blocked plan still gets a durable BLOCKED_SOURCE run,
        so the monitor can explain why it did not search.
        """

        actor = str(actor or "scheduler").strip() or "scheduler"
        occurrence = str(scheduled_for or now_iso()).strip()
        with self.tx() as db:
            schedule = db.execute(
                "SELECT * FROM scheduled_tasks WHERE id = ? AND workspace_id = ?",
                (schedule_id, workspace_id),
            ).fetchone()
            if not schedule:
                return None
            if schedule["status"] != "ACTIVE":
                return {"status": "SKIPPED", "reason": "schedule_not_active", "schedule": self._scheduled_task_dict(schedule)}
            if str(schedule["next_run_at"]) > occurrence:
                return {"status": "SKIPPED", "reason": "not_due", "schedule": self._scheduled_task_dict(schedule)}

            quoted_max = (plan.get("cost_estimate") or {}).get("max_credits")
            if quoted_max is None:
                run_status = "BLOCKED_BUDGET"
                error_code = "UNKNOWN_SOURCE_QUOTE"
                message = "计划包含尚未登记计量规则的来源，调度不会在预算未知时执行。"
                task_id = None
            elif int(quoted_max) > int(schedule["max_credits_per_run"]):
                run_status = "BLOCKED_BUDGET"
                error_code = "PER_RUN_BUDGET_EXCEEDED"
                message = "计划的最高估算超过调度单次预算上限。"
                task_id = None
            elif schedule["max_total_credits"] is not None and int(schedule["total_credits"]) + int(quoted_max) > int(schedule["max_total_credits"]):
                run_status = "BLOCKED_BUDGET"
                error_code = "TOTAL_BUDGET_EXCEEDED"
                message = "计划的最高估算会超过调度总预算上限。"
                task_id = None
            else:
                task_id = _id("task")
                timestamp = now_iso()
                runnable = bool(plan.get("runnable_sources"))
                task_status = "PLANNED" if runnable else "AWAITING_SOURCE"
                db.execute(
                    """INSERT INTO tasks
                       (id, workspace_id, profile_id, objective, criteria_json,
                        status, requested_limit, estimated_credits, idempotency_key,
                        created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        task_id,
                        workspace_id,
                        None,
                        schedule["objective"],
                        schedule["criteria_json"],
                        task_status,
                        schedule["requested_limit"],
                        int(quoted_max),
                        f"schedule:{schedule_id}:{occurrence}",
                        timestamp,
                    ),
                )
                db.execute(
                    "INSERT INTO task_plans(id, task_id, planner_version, plan_json, created_at) VALUES (?, ?, ?, ?, ?)",
                    (_id("plan"), task_id, plan["planner_version"], _json(plan), timestamp),
                )
                if runnable:
                    run_status = "QUEUED"
                    error_code = None
                    message = "调度已生成任务，等待来源 worker 执行。"
                else:
                    run_status = "BLOCKED_SOURCE"
                    error_code = "NO_SEARCH_CONNECTOR_READY"
                    message = "调度已记录，但当前没有通过生产门禁的自动搜索来源。"

            run_id = _id("schedule_run")
            db.execute(
                """INSERT INTO scheduled_task_runs
                   (id, schedule_id, task_id, status, scheduled_for,
                    error_code, message, idempotency_key, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    schedule_id,
                    task_id,
                    run_status,
                    occurrence,
                    error_code,
                    message,
                    f"schedule-run:{schedule_id}:{occurrence}",
                    now_iso(),
                ),
            )
            next_run = now_iso()
            from datetime import datetime, timedelta, timezone

            try:
                base = datetime.fromisoformat(occurrence.replace("Z", "+00:00"))
                if base.tzinfo is None:
                    base = base.replace(tzinfo=timezone.utc)
                next_run = (base + timedelta(minutes=int(schedule["interval_minutes"]))).isoformat(timespec="seconds")
            except (TypeError, ValueError):
                next_run = now_iso()
            next_status = schedule["status"]
            if run_status in {"BLOCKED_SOURCE", "BLOCKED_BUDGET"} and schedule["failure_policy"] == "PAUSE":
                next_status = "PAUSED"
            db.execute(
                """UPDATE scheduled_tasks
                   SET status = ?, next_run_at = ?, last_run_at = ?,
                       run_count = run_count + 1, updated_at = ?
                   WHERE id = ?""",
                (next_status, next_run, occurrence, now_iso(), schedule_id),
            )
            self._audit(
                db,
                workspace_id,
                "scheduled_task",
                schedule_id,
                "triggered",
                {
                    "run_id": run_id,
                    "task_id": task_id,
                    "status": run_status,
                    "actor": actor,
                    "scheduled_for": occurrence,
                    "next_run_at": next_run,
                    "error_code": error_code,
                },
            )
        return {
            "run": self.get_scheduled_task_run(run_id, workspace_id),
            "task": self.get_task(task_id) if task_id else None,
            "schedule": self.get_scheduled_task(schedule_id, workspace_id),
        }

    def get_scheduled_task_run(self, run_id: str, workspace_id: str | None = None) -> dict[str, Any] | None:
        query = """SELECT r.* FROM scheduled_task_runs r
                   JOIN scheduled_tasks s ON s.id = r.schedule_id
                   WHERE r.id = ?"""
        params: list[Any] = [run_id]
        if workspace_id is not None:
            query += " AND s.workspace_id = ?"
            params.append(workspace_id)
        with self.lock:
            row = self.db.execute(query, params).fetchone()
        return self._scheduled_task_run_dict(row)

    def settle_scheduled_task_run(
        self,
        task_id: str,
        candidate_count: int,
        new_result_count: int,
        *,
        error_code: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any] | None:
        """Settle the schedule occurrence after the existing source worker finishes."""

        with self.tx() as db:
            run = db.execute(
                """SELECT r.*, s.workspace_id, s.failure_policy, s.approval_policy,
                          s.min_new_results, s.max_total_credits, s.total_credits,
                          s.id AS schedule_id
                   FROM scheduled_task_runs r
                   JOIN scheduled_tasks s ON s.id = r.schedule_id
                   WHERE r.task_id = ? AND r.status IN ('QUEUED', 'RUNNING')
                   ORDER BY r.created_at DESC, r.rowid DESC LIMIT 1""",
                (task_id,),
            ).fetchone()
            if not run:
                return None
            credits = int(
                db.execute("SELECT COALESCE(SUM(credits), 0) FROM usage_ledger WHERE task_id = ?", (task_id,)).fetchone()[0]
            )
            if error_code:
                next_status = "FAILED"
                next_message = message or "调度任务执行失败。"
            elif int(new_result_count) < int(run["min_new_results"]):
                next_status = "COMPLETED_BELOW_THRESHOLD"
                next_message = message or "调度任务完成，但新增结果低于阈值。"
            else:
                next_status = "COMPLETED"
                next_message = message or "调度任务完成并达到结果阈值。"
            timestamp = now_iso()
            db.execute(
                """UPDATE scheduled_task_runs
                   SET status = ?, candidate_count = ?, new_result_count = ?,
                       credits_used = ?, error_code = ?, message = ?,
                       finished_at = ?
                   WHERE id = ?""",
                (
                    next_status,
                    max(0, int(candidate_count)),
                    max(0, int(new_result_count)),
                    credits,
                    error_code,
                    next_message,
                    timestamp,
                    run["id"],
                ),
            )
            total_credits = int(run["total_credits"]) + credits
            schedule_status = "ACTIVE"
            if error_code and run["failure_policy"] == "PAUSE":
                schedule_status = "PAUSED"
            elif run["max_total_credits"] is not None and total_credits >= int(run["max_total_credits"]):
                schedule_status = "EXHAUSTED"
            db.execute(
                "UPDATE scheduled_tasks SET total_credits = ?, status = ?, updated_at = ? WHERE id = ?",
                (total_credits, schedule_status, timestamp, run["schedule_id"]),
            )
            self._audit(
                db,
                run["workspace_id"],
                "scheduled_task",
                run["schedule_id"],
                "settled",
                {
                    "run_id": run["id"],
                    "task_id": task_id,
                    "status": next_status,
                    "candidate_count": int(candidate_count),
                    "new_result_count": int(new_result_count),
                    "credits_used": credits,
                    "error_code": error_code,
                },
            )
            schedule_id = run["schedule_id"]
            workspace_id = run["workspace_id"]
        return self.get_scheduled_task(schedule_id, workspace_id)

    def start_task(self, task_id: str, mode: str = "quick") -> dict[str, Any] | None:
        if mode not in {"quick", "condition", "broad"}:
            raise ValueError("invalid_run_mode")
        with self.tx() as db:
            row = db.execute("SELECT workspace_id, requested_limit FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                return None
            plan_row = db.execute("SELECT plan_json FROM task_plans WHERE task_id = ?", (task_id,)).fetchone()
            plan = json.loads(plan_row["plan_json"]) if plan_row else {}
            run_key = f"{task_id}:{mode}:{plan.get('planner_version', 'unknown')}"
            existing = db.execute("SELECT id FROM task_runs WHERE idempotency_key = ?", (run_key,)).fetchone()
            if not existing:
                runnable = bool(plan.get("runnable_sources"))
                run_status = "QUEUED" if runnable else "BLOCKED_REQUIRES_SOURCE"
                timestamp = now_iso()
                run_id = _id("run")
                db.execute(
                    """INSERT INTO task_runs
                    (id, task_id, mode, status, requested_limit, error_code, idempotency_key, created_at, started_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (run_id, task_id, mode, run_status, row["requested_limit"], None if runnable else "NO_SEARCH_CONNECTOR_READY", run_key, timestamp, timestamp if runnable else None),
                )
                db.execute("UPDATE tasks SET status = ?, started_at = COALESCE(started_at, ?) WHERE id = ?", ("QUEUED" if runnable else "AWAITING_SOURCE", timestamp, task_id))
                self._run_event(
                    db,
                    run_id,
                    "created",
                    run_status,
                    "任务已创建运行实例。" if runnable else "任务被来源生产门禁阻塞。",
                    {"mode": mode, "blocked_sources": plan.get("blocked_sources", [])},
                )
                self._audit(db, row["workspace_id"], "task", task_id, "run_created", {"mode": mode, "status": run_status})
        return self.get_task(task_id)

    def control_task_run(self, task_id: str, run_id: str, action: str, actor: str = "operator") -> dict[str, Any] | None:
        transitions = {
            "pause": ({"QUEUED", "RUNNING"}, "PAUSED", "任务已暂停。"),
            "resume": ({"PAUSED"}, "QUEUED", "任务已恢复并重新排队。"),
            "cancel": ({"QUEUED", "RUNNING", "PAUSED", "BLOCKED_REQUIRES_SOURCE"}, "CANCELLED", "任务已取消。"),
        }
        if action not in transitions:
            raise ValueError("invalid_run_action")
        allowed, next_status, message = transitions[action]
        with self.tx() as db:
            row = db.execute(
                """SELECT r.*, t.workspace_id FROM task_runs r
                   JOIN tasks t ON t.id = r.task_id
                   WHERE r.id = ? AND r.task_id = ?""",
                (run_id, task_id),
            ).fetchone()
            if not row:
                return None
            current = row["status"]
            if current == next_status:
                return self.get_task(task_id)
            if current not in allowed:
                raise ValueError(f"run_action_not_allowed:{action}:{current}")
            timestamp = now_iso()
            finished_at = timestamp if next_status in {"CANCELLED"} else None
            started_at = timestamp if next_status == "RUNNING" else row["started_at"]
            db.execute(
                "UPDATE task_runs SET status = ?, started_at = ?, finished_at = ? WHERE id = ?",
                (next_status, started_at, finished_at, run_id),
            )
            task_status = "CANCELLED" if next_status == "CANCELLED" else next_status
            db.execute("UPDATE tasks SET status = ?, finished_at = ? WHERE id = ?", (task_status, finished_at, task_id))
            self._run_event(db, run_id, action, next_status, message, {"actor": actor, "from_status": current})
            self._audit(db, row["workspace_id"], "task_run", run_id, action, {"task_id": task_id, "actor": actor, "from_status": current, "to_status": next_status})
        return self.get_task(task_id)

    def retry_task_run(self, task_id: str, run_id: str, actor: str = "operator") -> dict[str, Any] | None:
        with self.tx() as db:
            row = db.execute(
                """SELECT r.*, t.workspace_id, t.requested_limit FROM task_runs r
                   JOIN tasks t ON t.id = r.task_id
                   WHERE r.id = ? AND r.task_id = ?""",
                (run_id, task_id),
            ).fetchone()
            if not row:
                return None
            if row["status"] not in {"FAILED", "CANCELLED", "BLOCKED_REQUIRES_SOURCE"}:
                raise ValueError(f"retry_not_allowed:{row['status']}")
            plan_row = db.execute("SELECT plan_json FROM task_plans WHERE task_id = ?", (task_id,)).fetchone()
            plan = json.loads(plan_row["plan_json"]) if plan_row else {}
            runnable = bool(plan.get("runnable_sources"))
            next_status = "QUEUED" if runnable else "BLOCKED_REQUIRES_SOURCE"
            timestamp = now_iso()
            new_run_id = _id("run")
            retry_key = f"{task_id}:{row['mode']}:{plan.get('planner_version', 'unknown')}:retry:{new_run_id}"
            db.execute(
                """INSERT INTO task_runs
                   (id, task_id, mode, status, requested_limit, error_code, idempotency_key, created_at, started_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (new_run_id, task_id, row["mode"], next_status, row["requested_limit"], None if runnable else "NO_SEARCH_CONNECTOR_READY", retry_key, timestamp, timestamp if runnable else None),
            )
            db.execute("UPDATE tasks SET status = ?, finished_at = NULL, started_at = COALESCE(started_at, ?) WHERE id = ?", ("QUEUED" if runnable else "AWAITING_SOURCE", timestamp, task_id))
            self._run_event(db, new_run_id, "retry_created", next_status, "已从上一运行实例重试。" if runnable else "重试仍被来源生产门禁阻塞。", {"actor": actor, "previous_run_id": run_id, "blocked_sources": plan.get("blocked_sources", [])})
            self._audit(db, row["workspace_id"], "task_run", new_run_id, "retry_created", {"task_id": task_id, "actor": actor, "previous_run_id": run_id, "status": next_status})
        return self.get_task(task_id)

    def begin_task_run(self, task_id: str, run_id: str, actor: str = "worker") -> dict[str, Any] | None:
        with self.tx() as db:
            row = db.execute(
                """SELECT r.*, t.workspace_id FROM task_runs r
                   JOIN tasks t ON t.id = r.task_id
                   WHERE r.id = ? AND r.task_id = ?""",
                (run_id, task_id),
            ).fetchone()
            if not row:
                return None
            if row["status"] == "RUNNING":
                return self.get_task(task_id)
            if row["status"] != "QUEUED":
                raise ValueError(f"run_start_not_allowed:{row['status']}")
            timestamp = now_iso()
            db.execute("UPDATE task_runs SET status = 'RUNNING', started_at = COALESCE(started_at, ?) WHERE id = ?", (timestamp, run_id))
            db.execute("UPDATE tasks SET status = 'RUNNING', started_at = COALESCE(started_at, ?), finished_at = NULL WHERE id = ?", (timestamp, task_id))
            self._run_event(db, run_id, "started", "RUNNING", "来源连接器开始执行。", {"actor": actor})
            self._audit(db, row["workspace_id"], "task_run", run_id, "started", {"task_id": task_id, "actor": actor})
        return self.get_task(task_id)

    def complete_task_run(self, task_id: str, run_id: str, candidate_count: int, verified_count: int, actor: str = "worker") -> dict[str, Any] | None:
        with self.tx() as db:
            row = db.execute(
                """SELECT r.*, t.workspace_id FROM task_runs r
                   JOIN tasks t ON t.id = r.task_id
                   WHERE r.id = ? AND r.task_id = ?""",
                (run_id, task_id),
            ).fetchone()
            if not row:
                return None
            if row["status"] == "COMPLETED":
                return self.get_task(task_id)
            if row["status"] != "RUNNING":
                raise ValueError(f"run_complete_not_allowed:{row['status']}")
            timestamp = now_iso()
            db.execute(
                "UPDATE task_runs SET status = 'COMPLETED', candidate_count = ?, verified_count = ?, finished_at = ? WHERE id = ?",
                (candidate_count, verified_count, timestamp, run_id),
            )
            db.execute("UPDATE tasks SET status = 'COMPLETED', finished_at = ? WHERE id = ?", (timestamp, task_id))
            self._run_event(db, run_id, "completed", "COMPLETED", "来源连接器执行完成。", {"actor": actor, "candidate_count": candidate_count, "verified_count": verified_count})
            self._audit(db, row["workspace_id"], "task_run", run_id, "completed", {"task_id": task_id, "actor": actor, "candidate_count": candidate_count, "verified_count": verified_count})
        return self.get_task(task_id)

    def fail_task_run(self, task_id: str, run_id: str, error_code: str, message: str, actor: str = "worker") -> dict[str, Any] | None:
        with self.tx() as db:
            row = db.execute(
                """SELECT r.*, t.workspace_id FROM task_runs r
                   JOIN tasks t ON t.id = r.task_id
                   WHERE r.id = ? AND r.task_id = ?""",
                (run_id, task_id),
            ).fetchone()
            if not row:
                return None
            if row["status"] == "FAILED":
                return self.get_task(task_id)
            if row["status"] != "RUNNING":
                raise ValueError(f"run_fail_not_allowed:{row['status']}")
            timestamp = now_iso()
            db.execute("UPDATE task_runs SET status = 'FAILED', error_code = ?, finished_at = ? WHERE id = ?", (error_code, timestamp, run_id))
            db.execute("UPDATE tasks SET status = 'FAILED', finished_at = ? WHERE id = ?", (timestamp, task_id))
            self._run_event(db, run_id, "failed", "FAILED", message, {"actor": actor, "error_code": error_code})
            self._audit(db, row["workspace_id"], "task_run", run_id, "failed", {"task_id": task_id, "actor": actor, "error_code": error_code})
        return self.get_task(task_id)

    def _run_events(self, run_id: str) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.db.execute(
                "SELECT id, event_type, status, message, payload_json, created_at FROM task_run_events WHERE run_id = ? ORDER BY created_at, rowid",
                (run_id,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            entry = dict(row)
            entry["payload"] = json.loads(entry.pop("payload_json") or "{}")
            result.append(entry)
        return result

    def get_task_run_events(self, task_id: str, run_id: str) -> list[dict[str, Any]] | None:
        with self.lock:
            owned = self.db.execute("SELECT id FROM task_runs WHERE id = ? AND task_id = ?", (run_id, task_id)).fetchone()
        if not owned:
            return None
        return self._run_events(run_id)

    @staticmethod
    def _run_event(db: sqlite3.Connection, run_id: str, event_type: str, status: str, message: str, payload: dict[str, Any]) -> None:
        db.execute(
            "INSERT INTO task_run_events(id, run_id, event_type, status, message, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_id("run_event"), run_id, event_type, status, message, _json(payload), now_iso()),
        )

    @staticmethod
    def _feed_event_type(item: dict[str, Any], override: str | None = None) -> str:
        explicit = override or item.get("feed_event_type") or item.get("event_type")
        if explicit:
            normalized = str(explicit).strip().upper()
            if normalized not in FEED_EVENT_TYPES:
                raise ValueError("feed_event_type_invalid")
            return normalized
        text = " ".join(str(item.get(field) or "") for field in ("title", "intent_type", "snippet"))
        if any(term in text for term in ("招聘", "招募", "岗位", "人才")):
            return "HIRING"
        if any(term in text for term in ("招标", "投标", "公告", "标书")):
            return "TENDER"
        return "PURCHASE_DEMAND"

    @staticmethod
    def _feed_event_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        result = _decode(row)
        if not result:
            return None
        try:
            result["payload"] = json.loads(result.pop("payload_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            result["payload"] = {}
            result.pop("payload_json", None)
        return result

    def _record_feed_event(
        self,
        db: sqlite3.Connection,
        workspace_id: str,
        task_id: str | None,
        opportunity_id: str | None,
        item: dict[str, Any],
        *,
        event_type: str | None = None,
        observed_at: str | None = None,
    ) -> dict[str, Any]:
        normalized_type = self._feed_event_type(item, event_type)
        title = str(item.get("title") or "公开来源事件").strip()[:500]
        summary = str(item.get("snippet") or item.get("summary") or "").strip()[:4000]
        source_url = str(item.get("source_url") or item.get("url") or "").strip()
        if not title or not summary or not source_url:
            raise ValueError("feed_event_evidence_required")
        metadata = item.get("evidence_metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        content_hash = str(
            metadata.get("content_hash")
            or item.get("content_hash")
            or hashlib.sha256(f"{title}|{summary}".encode("utf-8")).hexdigest()
        ).strip()
        if len(content_hash) > 128:
            content_hash = hashlib.sha256(content_hash.encode("utf-8")).hexdigest()
        dedup_key = hashlib.sha256(
            f"{workspace_id}|{normalized_type}|{source_url}|{content_hash}".encode("utf-8")
        ).hexdigest()
        provenance = metadata.get("source_provenance") if isinstance(metadata.get("source_provenance"), dict) else {}
        payload = {
            "source_kind": item.get("source_kind"),
            "evidence_level": item.get("evidence_level", "UNVERIFIED"),
            "source_permission": item.get("source_permission", "unknown"),
            "platform": provenance.get("platform"),
            "change_type": item.get("change_type"),
            "content_hash": content_hash,
        }
        timestamp = now_iso()
        db.execute(
            """INSERT OR IGNORE INTO feed_events
               (id, workspace_id, task_id, opportunity_id, event_type, status,
                title, summary, source_url, content_hash, published_at,
                observed_at, payload_json, dedup_key, created_at)
               VALUES (?, ?, ?, ?, ?, 'NEW', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _id("feed"),
                workspace_id,
                task_id,
                opportunity_id,
                normalized_type,
                title,
                summary,
                source_url,
                content_hash,
                item.get("published_at"),
                str(observed_at or item.get("observed_at") or item.get("captured_at") or timestamp),
                _json(payload),
                dedup_key,
                timestamp,
            ),
        )
        row = db.execute("SELECT * FROM feed_events WHERE workspace_id = ? AND dedup_key = ?", (workspace_id, dedup_key)).fetchone()
        return self._feed_event_dict(row)  # type: ignore[return-value]

    def get_feed_event(self, event_id: str, workspace_id: str | None = None) -> dict[str, Any] | None:
        query = "SELECT * FROM feed_events WHERE id = ?"
        params: list[Any] = [event_id]
        if workspace_id is not None:
            query += " AND workspace_id = ?"
            params.append(workspace_id)
        with self.lock:
            row = self.db.execute(query, params).fetchone()
        return self._feed_event_dict(row)

    def list_feed_events(
        self,
        workspace_id: str,
        *,
        event_type: str | None = None,
        status: str | None = None,
        since: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        if event_type is not None:
            event_type = str(event_type).strip().upper()
            if event_type not in FEED_EVENT_TYPES:
                raise ValueError("feed_event_type_invalid")
        if status is not None:
            status = str(status).strip().upper()
            if status not in FEED_EVENT_STATUSES:
                raise ValueError("feed_event_status_invalid")
        bounded_limit = max(1, min(int(limit), 100))
        bounded_offset = max(0, int(offset))
        clauses = ["workspace_id = ?"]
        params: list[Any] = [workspace_id]
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if since:
            clauses.append("observed_at >= ?")
            params.append(str(since))
        where = " AND ".join(clauses)
        with self.lock:
            total = int(self.db.execute(f"SELECT COUNT(*) FROM feed_events WHERE {where}", params).fetchone()[0])
            rows = self.db.execute(
                f"SELECT * FROM feed_events WHERE {where} ORDER BY observed_at DESC, created_at DESC, rowid DESC LIMIT ? OFFSET ?",
                (*params, bounded_limit, bounded_offset),
            ).fetchall()
        items = [self._feed_event_dict(row) for row in rows]
        next_offset = bounded_offset + bounded_limit if bounded_offset + bounded_limit < total else None
        return {
            "items": items,
            "pagination": {
                "limit": bounded_limit,
                "offset": bounded_offset,
                "total": total,
                "has_more": next_offset is not None,
                "next_offset": next_offset,
            },
        }

    def review_feed_event(
        self,
        event_id: str,
        workspace_id: str,
        status: str,
        actor: str = "operator",
        note: str = "",
    ) -> dict[str, Any] | None:
        status = str(status or "").strip().upper()
        if status not in FEED_EVENT_STATUSES - {"NEW"}:
            raise ValueError("feed_review_status_invalid")
        actor = str(actor or "operator").strip() or "operator"
        note = str(note or "").strip()[:1000]
        with self.tx() as db:
            row = db.execute(
                "SELECT * FROM feed_events WHERE id = ? AND workspace_id = ?",
                (event_id, workspace_id),
            ).fetchone()
            if not row:
                return None
            timestamp = now_iso()
            db.execute(
                "UPDATE feed_events SET status = ?, review_note = ?, reviewed_by = ?, reviewed_at = ? WHERE id = ?",
                (status, note, actor, timestamp, event_id),
            )
            self._audit(db, workspace_id, "feed_event", event_id, "reviewed", {"status": status, "actor": actor, "note": note})
        return self.get_feed_event(event_id, workspace_id)

    def add_opportunity(self, task_id: str, item: dict[str, Any], status: str) -> tuple[dict[str, Any], bool]:
        with self.lock:
            task = self.db.execute("SELECT workspace_id FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            raise KeyError("task_not_found")
        workspace_id = task["workspace_id"]
        dedup_input = f"{workspace_id}|{normalize(item['source_url'])}|{normalize(item['title'])}"
        dedup_key = hashlib.sha256(dedup_input.encode("utf-8")).hexdigest()
        opportunity_id = _id("opp")
        timestamp = now_iso()
        # `status` is the persisted workflow state chosen by the caller.  It must
        # not be fed back as an operator override: REVIEW is the normal state for
        # newly captured evidence, and the decision code should still explain why
        # that evidence needs review (for example CAPTURED_PAGE_NEEDS_REVIEW).
        decision = item.get("decision") or evidence_decision(item)
        with self.tx() as db:
            existing = db.execute(
                "SELECT * FROM opportunities WHERE workspace_id = ? AND dedup_key = ?",
                (workspace_id, dedup_key),
            ).fetchone()
            if existing:
                db.execute("UPDATE opportunities SET updated_at = ? WHERE id = ?", (timestamp, existing["id"]))
                self._record_feed_event(db, workspace_id, task_id, existing["id"], item)
                self._audit(db, workspace_id, "opportunity", existing["id"], "deduplicated", {"task_id": task_id})
                return self._opportunity_dict(existing), True
            db.execute(
                """INSERT INTO opportunities
                (id, workspace_id, task_id, status, title, author, published_at, intent_type,
                 industry_location, source_kind, source_url, snippet, evidence_level,
                 source_permission, score, decision_json, dedup_key, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    opportunity_id,
                    workspace_id,
                    task_id,
                    status,
                    item["title"],
                    item.get("author"),
                    item.get("published_at"),
                    item.get("intent_type"),
                    item.get("industry_location"),
                    item.get("source_kind", "manual_public_evidence"),
                    item["source_url"],
                    item["snippet"],
                    item.get("evidence_level", "UNVERIFIED"),
                    item.get("source_permission", "unknown"),
                    float(item.get("score", 0)),
                    _json(decision),
                    dedup_key,
                    timestamp,
                    timestamp,
                ),
            )
            evidence_id = _id("evidence")
            db.execute(
                "INSERT INTO evidence(id, opportunity_id, evidence_type, content, url, metadata_json, captured_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    evidence_id,
                    opportunity_id,
                    item.get("evidence_type", "original_snippet"),
                    item["snippet"],
                    item["source_url"],
                    _json(item.get("evidence_metadata", {})),
                    item.get("captured_at", timestamp),
                    timestamp,
                ),
            )
            self._resolve_opportunity_entities(db, workspace_id, opportunity_id, item)
            self._record_feed_event(db, workspace_id, task_id, opportunity_id, item)
            audit_payload = {"task_id": task_id, "status": status}
            manual_override = item.get("_manual_override")
            if isinstance(manual_override, dict):
                audit_payload["manual_override"] = dict(manual_override)
            self._audit(db, workspace_id, "opportunity", opportunity_id, "created", audit_payload)
        return self.get_opportunity(opportunity_id), False  # type: ignore[return-value]

    def get_opportunity(self, opportunity_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.db.execute("SELECT * FROM opportunities WHERE id = ?", (opportunity_id,)).fetchone()
        return self._opportunity_dict(row)

    @staticmethod
    def _action_draft_content(channel: str, opportunity: sqlite3.Row) -> tuple[str | None, str]:
        title = str(opportunity["title"] or "公开需求")
        intent = str(opportunity["intent_type"] or "相关需求")
        snippet = str(opportunity["snippet"] or "").strip()
        excerpt = snippet[:240] + ("…" if len(snippet) > 240 else "")
        source_url = str(opportunity["source_url"])
        if channel == "PUBLIC_REPLY":
            return None, (
                f"你好，我看到你在公开页面提到{intent}，想进一步了解具体场景。"
                f"如果这个需求仍在评估，我可以先提供一个针对性的落地思路，再根据预算和时间安排下一步。"
                f"参考原文：{source_url}"
            )
        if channel == "EMAIL":
            return f"关于{title}的 AI 需求沟通", (
                f"您好，我看到贵方公开提到{intent}。\n\n"
                f"原文摘要：{excerpt}\n\n"
                "我们可以先用一次短沟通确认目标、现有系统和交付边界，再判断是否适合进入方案评估。\n\n"
                f"参考来源：{source_url}"
            )
        task_prefix = "飞书任务" if channel == "FEISHU_TASK" else "CRM 任务"
        return f"{task_prefix}：复核 {title}", (
            f"复核对象：{title}\n"
            f"需求类型：{intent}\n"
            f"原文摘要：{excerpt}\n"
            f"来源：{source_url}\n\n"
            "下一步：人工确认联系人、业务关系和触达方式后再执行。"
        )

    @staticmethod
    def _action_draft_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        result = _decode(row)
        if not result:
            return None
        result["evidence_ids"] = json.loads(result.pop("evidence_ids_json") or "[]")
        return result

    def create_action_drafts(
        self,
        opportunity_id: str,
        channels: list[str],
        actor: str = "operator",
        request_key: str | None = None,
    ) -> list[dict[str, Any]] | None:
        normalized_channels: list[str] = []
        for channel in channels:
            value = str(channel or "").strip().upper()
            if value not in ACTION_CHANNELS:
                raise ValueError("invalid_action_channel")
            if value not in normalized_channels:
                normalized_channels.append(value)
        if not normalized_channels:
            raise ValueError("action_channels_required")
        actor = str(actor or "operator").strip() or "operator"
        with self.tx() as db:
            opportunity = db.execute("SELECT * FROM opportunities WHERE id = ?", (opportunity_id,)).fetchone()
            if not opportunity:
                return None
            if opportunity["status"] != "SEND_READY":
                raise ValueError("opportunity_not_send_ready")
            evidence_ids = [row["id"] for row in db.execute("SELECT id FROM evidence WHERE opportunity_id = ? ORDER BY created_at", (opportunity_id,)).fetchall()]
            timestamp = now_iso()
            for channel in normalized_channels:
                idempotency_key = f"{request_key}:{channel}" if request_key else None
                existing = None
                if idempotency_key:
                    existing = db.execute("SELECT id FROM action_drafts WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
                else:
                    existing = db.execute(
                        """SELECT id FROM action_drafts
                           WHERE opportunity_id = ? AND channel = ? AND status IN ('DRAFT', 'APPROVED')
                           ORDER BY created_at DESC LIMIT 1""",
                        (opportunity_id, channel),
                    ).fetchone()
                if existing:
                    continue
                subject, body = self._action_draft_content(channel, opportunity)
                draft_id = _id("action")
                db.execute(
                    """INSERT INTO action_drafts
                       (id, workspace_id, opportunity_id, channel, status, subject, body,
                        evidence_ids_json, idempotency_key, created_by, created_at, updated_at)
                       VALUES (?, ?, ?, ?, 'DRAFT', ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        draft_id,
                        opportunity["workspace_id"],
                        opportunity_id,
                        channel,
                        subject,
                        body,
                        _json(evidence_ids),
                        idempotency_key,
                        actor,
                        timestamp,
                        timestamp,
                    ),
                )
                self._audit(
                    db,
                    opportunity["workspace_id"],
                    "opportunity",
                    opportunity_id,
                    "action_draft_created",
                    {"draft_id": draft_id, "channel": channel, "actor": actor, "evidence_ids": evidence_ids},
                )
        return self.list_action_drafts(opportunity_id)

    def list_action_drafts(self, opportunity_id: str, workspace_id: str | None = None) -> list[dict[str, Any]]:
        with self.lock:
            query = "SELECT * FROM action_drafts WHERE opportunity_id = ?"
            params: list[Any] = [opportunity_id]
            if workspace_id is not None:
                query += " AND workspace_id = ?"
                params.append(workspace_id)
            query += " ORDER BY created_at DESC, rowid DESC"
            rows = self.db.execute(query, params).fetchall()
        return [self._action_draft_dict(row) for row in rows]  # type: ignore[list-item]

    def get_action_draft(self, draft_id: str, workspace_id: str | None = None) -> dict[str, Any] | None:
        with self.lock:
            query = "SELECT * FROM action_drafts WHERE id = ?"
            params: list[Any] = [draft_id]
            if workspace_id is not None:
                query += " AND workspace_id = ?"
                params.append(workspace_id)
            row = self.db.execute(query, params).fetchone()
        return self._action_draft_dict(row)

    def approve_action_draft(self, draft_id: str, actor: str = "operator", confirm: bool = False) -> dict[str, Any] | None:
        if confirm is not True:
            raise ValueError("explicit_confirmation_required")
        actor = str(actor or "operator").strip() or "operator"
        with self.tx() as db:
            row = db.execute(
                """SELECT d.*, o.status AS opportunity_status
                   FROM action_drafts d JOIN opportunities o ON o.id = d.opportunity_id
                   WHERE d.id = ?""",
                (draft_id,),
            ).fetchone()
            if not row:
                return None
            if row["status"] == "APPROVED":
                return self._action_draft_dict(row)
            if row["status"] != "DRAFT":
                raise ValueError("action_draft_not_approvable")
            if row["opportunity_status"] != "SEND_READY":
                raise ValueError("opportunity_not_send_ready")
            timestamp = now_iso()
            db.execute(
                "UPDATE action_drafts SET status = 'APPROVED', approved_by = ?, approved_at = ?, updated_at = ? WHERE id = ?",
                (actor, timestamp, timestamp, draft_id),
            )
            self._audit(
                db,
                row["workspace_id"],
                "opportunity",
                row["opportunity_id"],
                "action_draft_approved",
                {"draft_id": draft_id, "channel": row["channel"], "actor": actor, "sent": False},
            )
        return self.get_action_draft(draft_id)

    def cancel_action_draft(self, draft_id: str, actor: str = "operator") -> dict[str, Any] | None:
        actor = str(actor or "operator").strip() or "operator"
        with self.tx() as db:
            row = db.execute("SELECT * FROM action_drafts WHERE id = ?", (draft_id,)).fetchone()
            if not row:
                return None
            if row["status"] == "CANCELLED":
                return self._action_draft_dict(row)
            if row["status"] not in {"DRAFT", "APPROVED"}:
                raise ValueError("action_draft_not_cancellable")
            timestamp = now_iso()
            db.execute("UPDATE action_drafts SET status = 'CANCELLED', updated_at = ? WHERE id = ?", (timestamp, draft_id))
            self._audit(
                db,
                row["workspace_id"],
                "opportunity",
                row["opportunity_id"],
                "action_draft_cancelled",
                {"draft_id": draft_id, "channel": row["channel"], "actor": actor},
            )
        return self.get_action_draft(draft_id)

    def list_entities(self, workspace_id: str) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.db.execute(
                """SELECT e.*, COUNT(DISTINCT oe.opportunity_id) AS opportunity_count
                   FROM entities e
                   LEFT JOIN opportunity_entities oe ON oe.entity_id = e.id
                   WHERE e.workspace_id = ?
                   GROUP BY e.id
                   ORDER BY opportunity_count DESC, e.updated_at DESC""",
                (workspace_id,),
            ).fetchall()
        return [self._entity_dict(row, include_opportunities=False) for row in rows]

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.db.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
        return self._entity_dict(row)

    def merge_entities(self, source_id: str, target_id: str, actor: str, reason: str) -> dict[str, Any] | None:
        if source_id == target_id:
            raise ValueError("merge_target_must_differ")
        reason = str(reason or "人工确认同一实体").strip()
        with self.tx() as db:
            source = db.execute("SELECT * FROM entities WHERE id = ?", (source_id,)).fetchone()
            target = db.execute("SELECT * FROM entities WHERE id = ?", (target_id,)).fetchone()
            if not source or not target:
                return None
            if source["workspace_id"] != target["workspace_id"]:
                raise ValueError("entities_must_share_workspace")
            if source["entity_type"] != target["entity_type"]:
                raise ValueError("entity_types_must_match")
            links = db.execute(
                "SELECT * FROM opportunity_entities WHERE entity_id = ? ORDER BY created_at",
                (source_id,),
            ).fetchall()
            moved = 0
            skipped = 0
            timestamp = now_iso()
            for link in links:
                existing = db.execute(
                    "SELECT id FROM opportunity_entities WHERE opportunity_id = ? AND entity_id = ?",
                    (link["opportunity_id"], target_id),
                ).fetchone()
                if existing:
                    skipped += 1
                    continue
                db.execute(
                    """INSERT INTO opportunity_entities
                       (id, opportunity_id, entity_id, relation, confidence, resolution_reason, evidence_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        _id("opp_entity"),
                        link["opportunity_id"],
                        target_id,
                        link["relation"],
                        max(float(link["confidence"]), 0.99),
                        f"人工合并：{reason}",
                        _json({"merged_from": source_id, "original_evidence": json.loads(link["evidence_json"] or "{}")}),
                        timestamp,
                    ),
                )
                moved += 1
            db.execute("DELETE FROM opportunity_entities WHERE entity_id = ?", (source_id,))
            db.execute("DELETE FROM entities WHERE id = ?", (source_id,))
            self._audit(
                db,
                target["workspace_id"],
                "entity",
                target_id,
                "merged",
                {"source_id": source_id, "actor": actor, "reason": reason, "moved": moved, "skipped": skipped},
            )
        return self.get_entity(target_id)

    def split_entity(
        self,
        entity_id: str,
        opportunity_id: str,
        new_name: str,
        website_host: str,
        actor: str,
        reason: str,
    ) -> dict[str, Any] | None:
        new_name = normalize_entity_name(new_name)
        if not new_name:
            raise ValueError("new_entity_name_required")
        website_host = normalize_host(website_host)
        reason = str(reason or "人工确认该机会属于另一个实体").strip()
        with self.tx() as db:
            source = db.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
            opportunity = db.execute(
                "SELECT id, workspace_id FROM opportunities WHERE id = ?", (opportunity_id,)
            ).fetchone()
            link = db.execute(
                "SELECT id FROM opportunity_entities WHERE entity_id = ? AND opportunity_id = ?",
                (entity_id, opportunity_id),
            ).fetchone()
            if not source or not opportunity or not link:
                return None
            if source["workspace_id"] != opportunity["workspace_id"]:
                raise ValueError("entities_must_share_workspace")
            timestamp = now_iso()
            target = db.execute(
                """SELECT * FROM entities
                   WHERE workspace_id = ? AND entity_type = ? AND canonical_name = ? AND website_host = ?""",
                (source["workspace_id"], source["entity_type"], new_name, website_host),
            ).fetchone()
            if target is None:
                target_id = _id("entity")
                db.execute(
                    """INSERT INTO entities
                       (id, workspace_id, entity_type, canonical_name, website_host, confidence, resolution_status, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (target_id, source["workspace_id"], source["entity_type"], new_name, website_host, 1.0, "MANUAL_SPLIT", timestamp, timestamp),
                )
            else:
                target_id = target["id"]
                db.execute("UPDATE entities SET confidence = MAX(confidence, 1.0), updated_at = ? WHERE id = ?", (timestamp, target_id))
            db.execute("DELETE FROM opportunity_entities WHERE id = ?", (link["id"],))
            db.execute(
                """INSERT OR REPLACE INTO opportunity_entities
                   (id, opportunity_id, entity_id, relation, confidence, resolution_reason, evidence_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    _id("opp_entity"),
                    opportunity_id,
                    target_id,
                    "about",
                    1.0,
                    f"人工拆分：{reason}",
                    _json({"split_from": entity_id, "source_opportunity": opportunity_id}),
                    timestamp,
                ),
            )
            self._audit(
                db,
                source["workspace_id"],
                "entity",
                target_id,
                "split",
                {"source_id": entity_id, "opportunity_id": opportunity_id, "actor": actor, "reason": reason},
            )
        return self.get_entity(target_id)

    def _entity_dict(self, row: sqlite3.Row | None, include_opportunities: bool = True) -> dict[str, Any] | None:
        result = _decode(row)
        if not result:
            return None
        if include_opportunities:
            with self.lock:
                opportunities = self.db.execute(
                    """SELECT o.id, o.title, o.status, o.source_url, oe.confidence,
                              oe.resolution_reason
                       FROM opportunity_entities oe
                       JOIN opportunities o ON o.id = oe.opportunity_id
                       WHERE oe.entity_id = ?
                       ORDER BY o.updated_at DESC""",
                    (result["id"],),
                ).fetchall()
            result["opportunities"] = [dict(item) for item in opportunities]
        return result

    def append_evidence(
        self,
        opportunity_id: str,
        evidence_type: str,
        content: str,
        url: str,
        metadata: dict[str, Any],
        captured_at: str | None = None,
        decision: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with self.tx() as db:
            row = db.execute("SELECT workspace_id FROM opportunities WHERE id = ?", (opportunity_id,)).fetchone()
            if not row:
                return None
            timestamp = now_iso()
            db.execute(
                "INSERT INTO evidence(id, opportunity_id, evidence_type, content, url, metadata_json, captured_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (_id("evidence"), opportunity_id, evidence_type, content, url, _json(metadata), captured_at or timestamp, timestamp),
            )
            if decision is None:
                db.execute("UPDATE opportunities SET updated_at = ? WHERE id = ?", (timestamp, opportunity_id))
            else:
                db.execute(
                    "UPDATE opportunities SET decision_json = ?, updated_at = ? WHERE id = ?",
                    (_json(decision), timestamp, opportunity_id),
                )
            if evidence_type == "reopen_check" and metadata.get("matches_previous_snapshot") is False:
                opportunity = db.execute(
                    "SELECT task_id, title, published_at, source_kind, source_permission, evidence_level FROM opportunities WHERE id = ?",
                    (opportunity_id,),
                ).fetchone()
                if opportunity:
                    self._record_feed_event(
                        db,
                        row["workspace_id"],
                        opportunity["task_id"],
                        opportunity_id,
                        {
                            "title": opportunity["title"],
                            "snippet": content,
                            "source_url": url,
                            "published_at": opportunity["published_at"],
                            "source_kind": opportunity["source_kind"],
                            "source_permission": opportunity["source_permission"],
                            "evidence_level": opportunity["evidence_level"],
                            "change_type": "CONTENT_CHANGED",
                            "evidence_metadata": metadata,
                        },
                        event_type="WEBSITE_CHANGE",
                        observed_at=captured_at or timestamp,
                    )
            self._audit(db, row["workspace_id"], "opportunity", opportunity_id, "evidence_appended", {"evidence_type": evidence_type, **metadata})
        return self.get_opportunity(opportunity_id)

    def _opportunity_dict(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        result = _decode(row)
        if result:
            with self.lock:
                evidence = self.db.execute(
                    "SELECT id, evidence_type, content, url, metadata_json, captured_at, created_at FROM evidence WHERE opportunity_id = ? ORDER BY created_at",
                    (result["id"],),
                ).fetchall()
                entities = self.db.execute(
                    """SELECT e.id, e.entity_type, e.canonical_name, e.website_host,
                              e.confidence AS entity_confidence, e.resolution_status,
                              oe.relation, oe.confidence, oe.resolution_reason, oe.evidence_json
                       FROM opportunity_entities oe
                       JOIN entities e ON e.id = oe.entity_id
                       WHERE oe.opportunity_id = ?
                       ORDER BY oe.created_at""",
                    (result["id"],),
                ).fetchall()
                feedback_events = self.db.execute(
                    """SELECT id, label, note, actor, created_at
                       FROM feedback_events
                       WHERE opportunity_id = ?
                       ORDER BY created_at, rowid""",
                    (result["id"],),
                ).fetchall()
                audit_events = self.db.execute(
                    """SELECT id, action, payload_json, created_at
                       FROM audit_events
                       WHERE workspace_id = ? AND entity_type = 'opportunity' AND entity_id = ?
                       ORDER BY created_at, rowid""",
                    (result["workspace_id"], result["id"]),
                ).fetchall()
                action_drafts = self.db.execute(
                    "SELECT * FROM action_drafts WHERE opportunity_id = ? ORDER BY created_at DESC, rowid DESC",
                    (result["id"],),
                ).fetchall()
                feed_events = self.db.execute(
                    "SELECT * FROM feed_events WHERE opportunity_id = ? ORDER BY observed_at DESC, created_at DESC, rowid DESC",
                    (result["id"],),
                ).fetchall()
            result["evidence"] = []
            result["decision"] = json.loads(result.pop("decision_json") or "{}")
            for item in evidence:
                entry = dict(item)
                entry["metadata"] = json.loads(entry.pop("metadata_json") or "{}")
                result["evidence"].append(entry)
            result["entities"] = []
            for item in entities:
                entry = dict(item)
                entry["confidence"] = entry.pop("confidence")
                entry["entity_confidence"] = entry.pop("entity_confidence")
                entry["evidence"] = json.loads(entry.pop("evidence_json") or "{}")
                result["entities"].append(entry)
            result["feedback_events"] = [dict(item) for item in feedback_events]
            result["audit_events"] = []
            for item in audit_events:
                entry = dict(item)
                entry["payload"] = json.loads(entry.pop("payload_json") or "{}")
                result["audit_events"].append(entry)
            result["action_drafts"] = [self._action_draft_dict(item) for item in action_drafts]
            result["feed_events"] = [self._feed_event_dict(item) for item in feed_events]
        return result

    def _resolve_opportunity_entities(
        self,
        db: sqlite3.Connection,
        workspace_id: str,
        opportunity_id: str,
        item: dict[str, Any],
    ) -> None:
        """Link an opportunity only when the identity signal is strong enough.

        A title or author alone never creates an organization. An explicit entity name
        may be reused across social sources, while a real website host is part of the
        identity key so same-name organizations on different sites stay separate.
        """

        explicit_name = normalize_entity_name(item.get("entity_name") or item.get("company_name"))
        explicit_type = normalize_entity_name(item.get("entity_type")) or "organization"
        host = source_host(item.get("source_url"))
        website_host = "" if is_platform_host(host) else host
        if not explicit_name and not website_host:
            return

        if explicit_name:
            canonical_name = explicit_name
            confidence = 0.78 if website_host else 0.72
            resolution_status = "EXPLICIT_NAME_AND_HOST" if website_host else "EXPLICIT_NAME"
            reason = "用户或导入记录提供实体名称" + ("，且来源 URL 提供官网主机" if website_host else "")
        else:
            canonical_name = website_host
            explicit_type = "organization"
            confidence = 0.9
            resolution_status = "HOST_MATCH"
            reason = "来源 URL 的公网主机作为保守实体标识"

        existing = db.execute(
            """SELECT * FROM entities
               WHERE workspace_id = ? AND entity_type = ? AND canonical_name = ? AND website_host = ?""",
            (workspace_id, explicit_type, canonical_name, website_host),
        ).fetchone()
        timestamp = now_iso()
        if existing:
            entity_id = existing["id"]
            db.execute(
                "UPDATE entities SET confidence = MAX(confidence, ?), updated_at = ? WHERE id = ?",
                (confidence, timestamp, entity_id),
            )
        else:
            entity_id = _id("entity")
            db.execute(
                """INSERT INTO entities
                   (id, workspace_id, entity_type, canonical_name, website_host,
                    confidence, resolution_status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entity_id, workspace_id, explicit_type, canonical_name, website_host, confidence, resolution_status, timestamp, timestamp),
            )
        db.execute(
            """INSERT OR IGNORE INTO opportunity_entities
               (id, opportunity_id, entity_id, relation, confidence, resolution_reason, evidence_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _id("opp_entity"),
                opportunity_id,
                entity_id,
                "about",
                confidence,
                reason,
                _json({"source_url": item.get("source_url"), "host": host, "explicit_name": bool(explicit_name)}),
                timestamp,
            ),
        )

    def list_opportunities(self, workspace_id: str, status: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM opportunities WHERE workspace_id = ?"
        params: list[Any] = [workspace_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY score DESC, updated_at DESC"
        with self.lock:
            rows = self.db.execute(query, params).fetchall()
        return [self._opportunity_dict(row) for row in rows]  # type: ignore[list-item]

    def create_calibration_batch(
        self,
        workspace_id: str,
        name: str,
        target_count: int = 30,
        opportunity_ids: list[str] | None = None,
    ) -> dict[str, Any] | None:
        name = str(name or "真实候选校准").strip()
        if not name:
            raise ValueError("calibration_name_required")
        if isinstance(target_count, bool) or not isinstance(target_count, int) or target_count < 1 or target_count > 500:
            raise ValueError("calibration_target_count_out_of_range")
        if len(name) > CALIBRATION_NAME_MAX:
            raise ValueError("calibration_name_too_long")
        with self.tx() as db:
            workspace = db.execute("SELECT id FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
            if not workspace:
                return None
            if opportunity_ids is None:
                rows = db.execute(
                    """SELECT * FROM opportunities
                       WHERE workspace_id = ?
                       ORDER BY CASE status
                           WHEN 'REVIEW' THEN 0
                           WHEN 'OBSERVE' THEN 1
                           WHEN 'SEND_READY' THEN 2
                           WHEN 'EXCLUDE' THEN 3
                           ELSE 4 END,
                           updated_at DESC, rowid DESC
                       LIMIT ?""",
                    (workspace_id, target_count),
                ).fetchall()
            else:
                if any(not isinstance(item, str) for item in opportunity_ids):
                    raise ValueError("calibration_opportunity_ids_must_be_strings")
                ids = [item.strip() for item in opportunity_ids if item.strip()]
                if len(ids) != len(set(ids)):
                    raise ValueError("calibration_opportunity_ids_must_be_unique")
                if len(ids) > target_count:
                    raise ValueError("calibration_items_exceed_target_count")
                if ids:
                    placeholders = ",".join("?" for _ in ids)
                    selected = db.execute(
                        f"SELECT * FROM opportunities WHERE workspace_id = ? AND id IN ({placeholders})",
                        (workspace_id, *ids),
                    ).fetchall()
                    by_id = {row["id"]: row for row in selected}
                    if len(by_id) != len(ids):
                        raise ValueError("calibration_opportunity_not_in_workspace")
                    rows = [by_id[item_id] for item_id in ids]
                else:
                    rows = []

            batch_id = _id("calibration")
            timestamp = now_iso()
            db.execute(
                """INSERT INTO calibration_batches
                   (id, workspace_id, name, target_count, status, created_at)
                   VALUES (?, ?, ?, ?, 'OPEN', ?)""",
                (batch_id, workspace_id, name, target_count, timestamp),
            )
            for row in rows:
                db.execute(
                    """INSERT INTO calibration_items
                       (id, batch_id, opportunity_id, predicted_label, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (_id("calibration_item"), batch_id, row["id"], predicted_calibration_label(row["status"]), timestamp),
                )
            self._audit(
                db,
                workspace_id,
                "calibration_batch",
                batch_id,
                "created",
                {"name": name, "target_count": target_count, "item_count": len(rows)},
            )
        return self.get_calibration_batch(batch_id, workspace_id)

    @staticmethod
    def _calibration_metrics(db: sqlite3.Connection, batch_id: str) -> dict[str, Any]:
        rows = db.execute(
            """SELECT ci.predicted_label, ci.gold_label, o.source_kind,
                      EXISTS(SELECT 1 FROM evidence e
                             WHERE e.opportunity_id = o.id AND e.evidence_type = 'reopen_check') AS reopened
               FROM calibration_items ci
               JOIN opportunities o ON o.id = ci.opportunity_id
               WHERE ci.batch_id = ?""",
            (batch_id,),
        ).fetchall()
        item_count = len(rows)
        reviewed = [row for row in rows if row["gold_label"]]
        agreement_count = sum(1 for row in reviewed if row["predicted_label"] == row["gold_label"])
        false_positive_count = sum(
            1 for row in reviewed if row["predicted_label"] == "VALID" and row["gold_label"] != "VALID"
        )
        false_negative_count = sum(
            1 for row in reviewed if row["predicted_label"] != "VALID" and row["gold_label"] == "VALID"
        )
        reopenable_sources = {"public_url_capture", "search_index_snippet", "authorized_search_api"}
        reopen_eligible_count = sum(1 for row in rows if row["source_kind"] in reopenable_sources)
        reopened_count = sum(
            1 for row in rows if row["source_kind"] in reopenable_sources and bool(row["reopened"])
        )
        return {
            "item_count": item_count,
            "reviewed_count": len(reviewed),
            "unreviewed_count": item_count - len(reviewed),
            "agreement_count": agreement_count,
            "accuracy": round(agreement_count / len(reviewed), 4) if reviewed else None,
            "false_positive_count": false_positive_count,
            "false_negative_count": false_negative_count,
            "reopen_eligible_count": reopen_eligible_count,
            "reopened_count": reopened_count,
            "reopen_rate": round(reopened_count / reopen_eligible_count, 4) if reopen_eligible_count else None,
        }

    @classmethod
    def _calibration_summary(cls, db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["metrics"] = cls._calibration_metrics(db, result["id"])
        result["coverage"] = round(
            result["metrics"]["item_count"] / result["target_count"], 4
        ) if result["target_count"] else 0
        return result

    @staticmethod
    def _calibration_item(db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["decision"] = json.loads(result.pop("decision_json") or "{}")
        result["reopened"] = bool(result["reopened"])
        return result

    def list_calibration_batches(self, workspace_id: str) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.db.execute(
                "SELECT * FROM calibration_batches WHERE workspace_id = ? ORDER BY created_at DESC, rowid DESC",
                (workspace_id,),
            ).fetchall()
            return [self._calibration_summary(self.db, row) for row in rows]

    def get_calibration_batch(self, batch_id: str, workspace_id: str | None = None) -> dict[str, Any] | None:
        with self.lock:
            query = "SELECT * FROM calibration_batches WHERE id = ?"
            params: list[Any] = [batch_id]
            if workspace_id is not None:
                query += " AND workspace_id = ?"
                params.append(workspace_id)
            batch = self.db.execute(query, params).fetchone()
            if not batch:
                return None
            item_rows = self.db.execute(
                """SELECT ci.id, ci.batch_id, ci.opportunity_id, ci.predicted_label, ci.gold_label,
                          ci.reviewer, ci.note, ci.reviewed_at, ci.created_at,
                          o.title, o.author, o.published_at, o.intent_type, o.status,
                          o.source_kind, o.source_url, o.snippet, o.decision_json,
                          (SELECT COUNT(*) FROM evidence e WHERE e.opportunity_id = o.id) AS evidence_count,
                          EXISTS(SELECT 1 FROM evidence e
                                 WHERE e.opportunity_id = o.id AND e.evidence_type = 'reopen_check') AS reopened
                   FROM calibration_items ci
                   JOIN opportunities o ON o.id = ci.opportunity_id
                   WHERE ci.batch_id = ?
                   ORDER BY ci.created_at, ci.rowid""",
                (batch_id,),
            ).fetchall()
            result = self._calibration_summary(self.db, batch)
            result["items"] = [self._calibration_item(self.db, row) for row in item_rows]
            return result

    def review_calibration_item(
        self,
        batch_id: str,
        item_id: str,
        gold_label: str,
        reviewer: str = "operator",
        note: str = "",
        apply_feedback: bool = True,
    ) -> dict[str, Any] | None:
        if not isinstance(gold_label, str):
            raise ValueError("gold_label_must_be_string")
        if not isinstance(reviewer, str) or not isinstance(note, str):
            raise ValueError("reviewer_and_note_must_be_string")
        if not isinstance(apply_feedback, bool):
            raise ValueError("apply_feedback_must_be_boolean")
        gold_label = gold_label.strip().upper()
        if gold_label not in CALIBRATION_LABELS:
            raise ValueError("invalid_calibration_gold_label")
        reviewer = reviewer.strip() or "operator"
        note = note.strip()
        if len(reviewer) > CALIBRATION_REVIEWER_MAX:
            raise ValueError("calibration_reviewer_too_long")
        if len(note) > CALIBRATION_NOTE_MAX:
            raise ValueError("calibration_note_too_long")
        status_map = {
            "VALID": "SEND_READY",
            "INVALID": "EXCLUDE",
            "DUPLICATE": "EXCLUDE",
            "OBSERVE": "OBSERVE",
            "NEEDS_EVIDENCE": "REVIEW",
        }
        with self.tx() as db:
            row = db.execute(
                """SELECT ci.*, cb.workspace_id, o.status AS opportunity_status
                   FROM calibration_items ci
                   JOIN calibration_batches cb ON cb.id = ci.batch_id
                   JOIN opportunities o ON o.id = ci.opportunity_id
                   WHERE ci.id = ? AND ci.batch_id = ?""",
                (item_id, batch_id),
            ).fetchone()
            if not row:
                return None
            timestamp = now_iso()
            db.execute(
                """UPDATE calibration_items
                   SET gold_label = ?, reviewer = ?, note = ?, reviewed_at = ?
                   WHERE id = ? AND batch_id = ?""",
                (gold_label, reviewer, note, timestamp, item_id, batch_id),
            )
            if apply_feedback:
                next_status = status_map[gold_label]
                db.execute(
                    "UPDATE opportunities SET status = ?, updated_at = ? WHERE id = ?",
                    (next_status, timestamp, row["opportunity_id"]),
                )
                db.execute(
                    "INSERT INTO feedback_events(id, opportunity_id, label, note, actor, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (_id("feedback"), row["opportunity_id"], gold_label, note or f"校准批次 {batch_id}", reviewer, timestamp),
                )
            self._audit(
                db,
                row["workspace_id"],
                "calibration_item",
                item_id,
                "reviewed",
                {
                    "batch_id": batch_id,
                    "opportunity_id": row["opportunity_id"],
                    "gold_label": gold_label,
                    "reviewer": reviewer,
                    "apply_feedback": apply_feedback,
                },
            )
            workspace_id = row["workspace_id"]
        return self.get_calibration_batch(batch_id, workspace_id)

    def add_feedback(self, opportunity_id: str, label: str, note: str, actor: str) -> dict[str, Any] | None:
        with self.tx() as db:
            row = db.execute("SELECT workspace_id, status FROM opportunities WHERE id = ?", (opportunity_id,)).fetchone()
            if not row:
                return None
            if row["status"] == "DO_NOT_CONTACT" and label != "UNSUBSCRIBED":
                raise ValueError("do_not_contact_locked")
            status_map = {
                "VALID": "SEND_READY",
                "REVIEW": "REVIEW",
                "OBSERVE": "OBSERVE",
                "INVALID": "EXCLUDE",
                "DUPLICATE": "DUPLICATE",
                "CONTACTED": "CONTACTED",
                "DEFERRED": "DEFERRED",
                "HANDOFF": "HANDOFF",
                "UNSUBSCRIBED": "DO_NOT_CONTACT",
            }
            next_status = status_map.get(label)
            previous_status = row["status"]
            cancelled_drafts = 0
            if next_status:
                db.execute("UPDATE opportunities SET status = ?, updated_at = ? WHERE id = ?", (next_status, now_iso(), opportunity_id))
            if label in {"CONTACTED", "DEFERRED", "HANDOFF", "UNSUBSCRIBED", "INVALID", "DUPLICATE"}:
                cancelled_drafts = int(
                    db.execute(
                        "SELECT COUNT(*) FROM action_drafts WHERE opportunity_id = ? AND status IN ('DRAFT', 'APPROVED')",
                        (opportunity_id,),
                    ).fetchone()[0]
                )
                if cancelled_drafts:
                    db.execute(
                        "UPDATE action_drafts SET status = 'CANCELLED', updated_at = ? WHERE opportunity_id = ? AND status IN ('DRAFT', 'APPROVED')",
                        (now_iso(), opportunity_id),
                    )
            feedback_id = _id("feedback")
            db.execute(
                "INSERT INTO feedback_events(id, opportunity_id, label, note, actor, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (feedback_id, opportunity_id, label, note, actor, now_iso()),
            )
            self._audit(
                db,
                row["workspace_id"],
                "opportunity",
                opportunity_id,
                "feedback",
                {
                    "label": label,
                    "actor": actor,
                    "previous_status": previous_status,
                    "next_status": next_status,
                    "cancelled_draft_count": cancelled_drafts,
                },
            )
        return self.get_opportunity(opportunity_id)

    def record_usage(
        self,
        workspace_id: str,
        task_id: str | None,
        operation: str,
        units: int,
        credits: int,
        status: str,
        idempotency_key: str | None = None,
        *,
        source_id: str | None = None,
        outcome: str | None = None,
        unit: str = "SOUBEI",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record one immutable usage fact and return whether it was inserted.

        Existing callers may continue using the legacy positional arguments.
        Source-aware callers should provide ``source_id`` and ``outcome`` so
        successful, duplicate, empty and failed attempts remain distinguishable
        in the same audit ledger.  An idempotency replay returns the original
        row and never updates task totals a second time.
        """
        units = max(0, int(units))
        credits = max(0, int(credits))
        normalized_source = str(source_id or "").strip()
        normalized_outcome = str(outcome or ("CHARGED" if credits else "UNBILLED")).upper()
        normalized_unit = str(unit or "SOUBEI").strip().upper() or "SOUBEI"
        details = dict(metadata or {})
        with self.tx() as db:
            if idempotency_key:
                existing = db.execute(
                    "SELECT * FROM usage_ledger WHERE workspace_id = ? AND idempotency_key = ?",
                    (workspace_id, idempotency_key),
                ).fetchone()
                if existing:
                    return {"created": False, "entry": self._usage_dict(existing)}
            usage_id = _id("usage")
            created_at = now_iso()
            db.execute(
                """INSERT INTO usage_ledger
                   (id, workspace_id, task_id, operation, units, credits, status,
                    idempotency_key, source_id, outcome, unit, metadata_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    usage_id,
                    workspace_id,
                    task_id,
                    operation,
                    units,
                    credits,
                    status,
                    idempotency_key,
                    normalized_source,
                    normalized_outcome,
                    normalized_unit,
                    _json(details),
                    created_at,
                ),
            )
            if task_id:
                db.execute("UPDATE tasks SET used_credits = used_credits + ? WHERE id = ?", (credits, task_id))
            self._audit(
                db,
                workspace_id,
                "usage",
                usage_id,
                "recorded",
                {
                    "task_id": task_id,
                    "operation": operation,
                    "source_id": normalized_source,
                    "outcome": normalized_outcome,
                    "units": units,
                    "credits": credits,
                    "unit": normalized_unit,
                    "idempotency_key": idempotency_key,
                    **details,
                },
            )
            row = db.execute("SELECT * FROM usage_ledger WHERE id = ?", (usage_id,)).fetchone()
        return {"created": True, "entry": self._usage_dict(row)}

    @staticmethod
    def _usage_dict(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        try:
            result["metadata"] = json.loads(result.pop("metadata_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            result["metadata"] = {}
            result.pop("metadata_json", None)
        return result

    def get_usage_by_idempotency_key(self, workspace_id: str, idempotency_key: str, operation: str | None = None) -> dict[str, Any] | None:
        query = "SELECT * FROM usage_ledger WHERE workspace_id = ? AND idempotency_key = ?"
        params: list[Any] = [workspace_id, idempotency_key]
        if operation is not None:
            query += " AND operation = ?"
            params.append(operation)
        with self.lock:
            row = self.db.execute(query, params).fetchone()
        return self._usage_dict(row)

    def save_source_proof(self, workspace_id: str, proof: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Register a proof binding without storing the raw external artifact."""

        with self.tx() as db:
            workspace = db.execute("SELECT id FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
            if not workspace:
                raise KeyError("workspace_not_found")
            existing = db.execute(
                "SELECT * FROM source_proofs WHERE workspace_id = ? AND proof_ref = ?",
                (workspace_id, proof["proof_ref"]),
            ).fetchone()
            if existing:
                existing_values = dict(existing)
                if any(existing_values[key] != proof[key] for key in ("provider", "source_family", "endpoint", "artifact_sha256", "checked_at")):
                    raise ValueError("source_proof_ref_conflict")
                if json.loads(existing_values["checks_json"] or "{}") != proof["checks"]:
                    raise ValueError("source_proof_ref_conflict")
                return self._source_proof_dict(existing), False  # type: ignore[return-value]
            proof_id = _id("proof")
            timestamp = now_iso()
            db.execute(
                """INSERT INTO source_proofs
                   (id, workspace_id, proof_ref, provider, source_family, endpoint,
                    artifact_sha256, checked_at, checks_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    proof_id,
                    workspace_id,
                    proof["proof_ref"],
                    proof["provider"],
                    proof["source_family"],
                    proof["endpoint"],
                    proof["artifact_sha256"],
                    proof["checked_at"],
                    _json(proof["checks"]),
                    timestamp,
                ),
            )
            self._audit(
                db,
                workspace_id,
                "source_proof",
                proof_id,
                "registered",
                {
                    "proof_ref": proof["proof_ref"],
                    "provider": proof["provider"],
                    "source_family": proof["source_family"],
                    "endpoint": proof["endpoint"],
                    "artifact_sha256": proof["artifact_sha256"],
                    "checked_at": proof["checked_at"],
                    "checks": proof["checks"],
                },
            )
            row = db.execute("SELECT * FROM source_proofs WHERE id = ?", (proof_id,)).fetchone()
        return self._source_proof_dict(row), True  # type: ignore[return-value]

    @staticmethod
    def _source_proof_dict(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        result["checks"] = json.loads(result.pop("checks_json") or "{}")
        return result

    def get_source_proof(self, workspace_id: str, proof_ref: str, provider: str | None = None) -> dict[str, Any] | None:
        query = "SELECT * FROM source_proofs WHERE workspace_id = ? AND proof_ref = ? AND status = 'ACTIVE'"
        params: list[Any] = [workspace_id, proof_ref]
        if provider is not None:
            query += " AND provider = ?"
            params.append(provider)
        with self.lock:
            row = self.db.execute(query, params).fetchone()
        return self._source_proof_dict(row)

    def list_source_proofs(self, workspace_id: str) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.db.execute(
                "SELECT * FROM source_proofs WHERE workspace_id = ? ORDER BY created_at DESC, rowid DESC",
                (workspace_id,),
            ).fetchall()
        return [self._source_proof_dict(row) for row in rows]  # type: ignore[list-item]

    def revoke_source_proof(self, workspace_id: str, proof_ref: str, actor: str = "operator") -> dict[str, Any] | None:
        with self.tx() as db:
            row = db.execute(
                "SELECT * FROM source_proofs WHERE workspace_id = ? AND proof_ref = ?",
                (workspace_id, proof_ref),
            ).fetchone()
            if not row:
                return None
            if row["status"] == "REVOKED":
                return self._source_proof_dict(row)
            revoked_at = now_iso()
            db.execute(
                "UPDATE source_proofs SET status = 'REVOKED', revoked_at = ? WHERE id = ?",
                (revoked_at, row["id"]),
            )
            self._audit(
                db,
                workspace_id,
                "source_proof",
                row["id"],
                "revoked",
                {"proof_ref": proof_ref, "actor": str(actor or "operator").strip() or "operator", "revoked_at": revoked_at},
            )
            updated = db.execute("SELECT * FROM source_proofs WHERE id = ?", (row["id"],)).fetchone()
        return self._source_proof_dict(updated)

    def dashboard(self, workspace_id: str) -> dict[str, Any]:
        with self.lock:
            def count(query: str, params: tuple[Any, ...] = ()) -> int:
                return int(self.db.execute(query, params).fetchone()[0])

            return {
                "workspace": dict(self.db.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()),
                "tasks": count("SELECT COUNT(*) FROM tasks WHERE workspace_id = ?", (workspace_id,)),
                "running_tasks": count("SELECT COUNT(*) FROM tasks WHERE workspace_id = ? AND status IN ('QUEUED', 'RUNNING')", (workspace_id,)),
                "awaiting_source": count("SELECT COUNT(*) FROM tasks WHERE workspace_id = ? AND status = 'AWAITING_SOURCE'", (workspace_id,)),
                "opportunities": count("SELECT COUNT(*) FROM opportunities WHERE workspace_id = ?", (workspace_id,)),
                "review": count("SELECT COUNT(*) FROM opportunities WHERE workspace_id = ? AND status = 'REVIEW'", (workspace_id,)),
                "send_ready": count("SELECT COUNT(*) FROM opportunities WHERE workspace_id = ? AND status = 'SEND_READY'", (workspace_id,)),
                "observed": count("SELECT COUNT(*) FROM opportunities WHERE workspace_id = ? AND status = 'OBSERVE'", (workspace_id,)),
                "excluded": count("SELECT COUNT(*) FROM opportunities WHERE workspace_id = ? AND status = 'EXCLUDE'", (workspace_id,)),
                "credits_used": int(self.db.execute("SELECT COALESCE(SUM(credits), 0) FROM usage_ledger WHERE workspace_id = ?", (workspace_id,)).fetchone()[0]),
            }

    def audit_usage(self, workspace_id: str, limit: int = 100) -> dict[str, Any]:
        """Return a read-only audit trail and usage ledger for one workspace."""
        try:
            bounded_limit = max(1, min(int(limit), 200))
        except (TypeError, ValueError):
            bounded_limit = 100
        with self.lock:
            audit_rows = self.db.execute(
                """SELECT id, entity_type, entity_id, action, payload_json, created_at
                   FROM audit_events
                   WHERE workspace_id = ?
                   ORDER BY created_at DESC, rowid DESC
                   LIMIT ?""",
                (workspace_id, bounded_limit),
            ).fetchall()
            usage_rows = self.db.execute(
                """SELECT id, task_id, operation, units, credits, status,
                          idempotency_key, source_id, outcome, unit, metadata_json, created_at
                   FROM usage_ledger
                   WHERE workspace_id = ?
                   ORDER BY created_at DESC, rowid DESC
                   LIMIT ?""",
                (workspace_id, bounded_limit),
            ).fetchall()
            credits_used = int(self.db.execute(
                "SELECT COALESCE(SUM(credits), 0) FROM usage_ledger WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchone()[0])
        audits: list[dict[str, Any]] = []
        for row in audit_rows:
            entry = dict(row)
            try:
                entry["payload"] = json.loads(entry.pop("payload_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                entry["payload"] = {}
                entry.pop("payload_json", None)
            audits.append(entry)
        usage: list[dict[str, Any]] = []
        for row in usage_rows:
            entry = self._usage_dict(row)
            if entry is not None:
                usage.append(entry)
        return {
            "workspace_id": workspace_id,
            "credits_used": credits_used,
            "events": audits,
            "usage": usage,
        }

    @staticmethod
    def _audit(db: sqlite3.Connection, workspace_id: str, entity_type: str, entity_id: str, action: str, payload: dict[str, Any]) -> None:
        db.execute(
            "INSERT INTO audit_events(id, workspace_id, entity_type, entity_id, action, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_id("audit"), workspace_id, entity_type, entity_id, action, _json(payload), now_iso()),
        )
