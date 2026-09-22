from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

try:
    from .domain import now_iso, normalize
except ImportError:  # running server.py directly
    from domain import now_iso, normalize


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
    dedup_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
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
    created_at TEXT NOT NULL,
    UNIQUE(workspace_id, idempotency_key)
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

CREATE INDEX IF NOT EXISTS idx_tasks_workspace_created ON tasks(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_opportunities_workspace_updated ON opportunities(workspace_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities(status);
"""


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


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
                    "SELECT id, mode, status, requested_limit, candidate_count, verified_count, error_code, created_at, started_at, finished_at FROM task_runs WHERE task_id = ? ORDER BY created_at DESC",
                    (result["id"],),
                ).fetchall()
            result["plan"] = json.loads(plan_row["plan_json"]) if plan_row else None
            result["runs"] = [dict(run) for run in run_rows]
        return result

    def list_tasks(self, workspace_id: str) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.db.execute("SELECT * FROM tasks WHERE workspace_id = ? ORDER BY created_at DESC", (workspace_id,)).fetchall()
        return [self._task_dict(row) for row in rows]  # type: ignore[list-item]

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
                db.execute(
                    """INSERT INTO task_runs
                    (id, task_id, mode, status, requested_limit, error_code, idempotency_key, created_at, started_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (_id("run"), task_id, mode, run_status, row["requested_limit"], None if runnable else "NO_SEARCH_CONNECTOR_READY", run_key, now_iso(), now_iso() if runnable else None),
                )
                db.execute("UPDATE tasks SET status = ?, started_at = COALESCE(started_at, ?) WHERE id = ?", ("QUEUED" if runnable else "AWAITING_SOURCE", now_iso(), task_id))
                self._audit(db, row["workspace_id"], "task", task_id, "run_created", {"mode": mode, "status": run_status})
        return self.get_task(task_id)

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
        with self.tx() as db:
            existing = db.execute(
                "SELECT * FROM opportunities WHERE workspace_id = ? AND dedup_key = ?",
                (workspace_id, dedup_key),
            ).fetchone()
            if existing:
                db.execute("UPDATE opportunities SET updated_at = ? WHERE id = ?", (timestamp, existing["id"]))
                self._audit(db, workspace_id, "opportunity", existing["id"], "deduplicated", {"task_id": task_id})
                return self._opportunity_dict(existing), True
            db.execute(
                """INSERT INTO opportunities
                (id, workspace_id, task_id, status, title, author, published_at, intent_type,
                 industry_location, source_kind, source_url, snippet, evidence_level,
                 source_permission, score, dedup_key, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            self._audit(db, workspace_id, "opportunity", opportunity_id, "created", {"task_id": task_id, "status": status})
        return self.get_opportunity(opportunity_id), False  # type: ignore[return-value]

    def get_opportunity(self, opportunity_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.db.execute("SELECT * FROM opportunities WHERE id = ?", (opportunity_id,)).fetchone()
        return self._opportunity_dict(row)

    def append_evidence(
        self,
        opportunity_id: str,
        evidence_type: str,
        content: str,
        url: str,
        metadata: dict[str, Any],
        captured_at: str | None = None,
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
            db.execute("UPDATE opportunities SET updated_at = ? WHERE id = ?", (timestamp, opportunity_id))
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
            result["evidence"] = []
            for item in evidence:
                entry = dict(item)
                entry["metadata"] = json.loads(entry.pop("metadata_json") or "{}")
                result["evidence"].append(entry)
        return result

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

    def add_feedback(self, opportunity_id: str, label: str, note: str, actor: str) -> dict[str, Any] | None:
        with self.tx() as db:
            row = db.execute("SELECT workspace_id FROM opportunities WHERE id = ?", (opportunity_id,)).fetchone()
            if not row:
                return None
            status_map = {"VALID": "SEND_READY", "REVIEW": "REVIEW", "OBSERVE": "OBSERVE", "INVALID": "EXCLUDE", "DUPLICATE": "EXCLUDE"}
            next_status = status_map.get(label)
            if next_status:
                db.execute("UPDATE opportunities SET status = ?, updated_at = ? WHERE id = ?", (next_status, now_iso(), opportunity_id))
            feedback_id = _id("feedback")
            db.execute(
                "INSERT INTO feedback_events(id, opportunity_id, label, note, actor, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (feedback_id, opportunity_id, label, note, actor, now_iso()),
            )
            self._audit(db, row["workspace_id"], "opportunity", opportunity_id, "feedback", {"label": label, "actor": actor})
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
    ) -> None:
        with self.tx() as db:
            if idempotency_key:
                existing = db.execute(
                    "SELECT id FROM usage_ledger WHERE workspace_id = ? AND idempotency_key = ?",
                    (workspace_id, idempotency_key),
                ).fetchone()
                if existing:
                    return
            db.execute(
                "INSERT INTO usage_ledger(id, workspace_id, task_id, operation, units, credits, status, idempotency_key, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (_id("usage"), workspace_id, task_id, operation, units, credits, status, idempotency_key, now_iso()),
            )
            if task_id:
                db.execute("UPDATE tasks SET used_credits = used_credits + ? WHERE id = ?", (credits, task_id))

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

    @staticmethod
    def _audit(db: sqlite3.Connection, workspace_id: str, entity_type: str, entity_id: str, action: str, payload: dict[str, Any]) -> None:
        db.execute(
            "INSERT INTO audit_events(id, workspace_id, entity_type, entity_id, action, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_id("audit"), workspace_id, entity_type, entity_id, action, _json(payload), now_iso()),
        )
