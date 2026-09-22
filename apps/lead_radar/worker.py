"""Deployable scheduler and source worker for Lead Radar.

The worker is deliberately separate from the HTTP server. It can be run once
from a supervisor or kept alive with --loop. Every schedule trigger, source
result, failure and settlement is written through Store.
"""
from __future__ import annotations

import argparse
import json
import threading
from typing import Any

try:
    from .domain import evidence_status, now_iso
    from .planner import build_search_plan
    from .search_connector import AuthorizedSearchConnector, SearchConnectorError, result_digest
    from .storage import Store
    from .usage import UNIT as USAGE_UNIT, charge_for, source_metadata
except ImportError:
    from domain import evidence_status, now_iso
    from planner import build_search_plan
    from search_connector import AuthorizedSearchConnector, SearchConnectorError, result_digest
    from storage import Store
    from usage import UNIT as USAGE_UNIT, charge_for, source_metadata


WORKSPACE_ID = "ws_意客AI"


class WorkerError(RuntimeError):
    pass


def _record_source_usage(
    store: Store,
    workspace_id: str,
    task_id: str,
    outcome: str,
    idempotency_key: str,
    *,
    units: int = 1,
    **metadata: Any,
) -> dict[str, Any]:
    operation = "authorized_search_api"
    normalized_outcome = str(outcome).upper()
    credits = charge_for(operation, normalized_outcome, units)
    return store.record_usage(
        workspace_id,
        task_id,
        operation,
        units,
        credits,
        "COMPLETED" if normalized_outcome in {"SUCCESS", "DUPLICATE", "NO_RESULT"} else "FAILED",
        idempotency_key,
        source_id=operation,
        outcome=normalized_outcome,
        unit=USAGE_UNIT,
        metadata=source_metadata(operation, normalized_outcome, **metadata),
    )


def execute_task_once(
    store: Store,
    workspace_id: str,
    task_id: str,
    *,
    mode: str = "quick",
    actor: str = "scheduler-worker",
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute one already-triggered task through the authorized connector."""

    task = store.get_task(task_id)
    if not task or task.get("workspace_id") != workspace_id:
        raise WorkerError("task_not_found")
    connector = AuthorizedSearchConnector()
    capability = connector.preflight()
    plan = task.get("plan") or {}
    if capability.get("status") != "READY" or "authorized_search_api" not in plan.get("runnable_sources", []):
        return {"status": "BLOCKED_SOURCE", "error_code": "NO_SEARCH_CONNECTOR_READY", "capability": capability, "task": task}

    task = store.start_task(task_id, mode)
    if not task:
        raise WorkerError("task_not_found")
    run = task.get("runs", [None])[0]
    if not run:
        raise WorkerError("run_not_created")
    if run.get("status") == "QUEUED":
        task = store.begin_task_run(task_id, run["id"], actor)
        run = (task or {}).get("runs", [None])[0]
    if not run or run.get("status") != "RUNNING":
        return {"status": run.get("status") if run else "RUN_NOT_READY", "task": task, "run": run}

    run_id = str(run["id"])
    request_id = request_id or f"worker-{run_id}"
    try:
        results = connector.search(
            plan,
            mode,
            request_id=request_id,
            idempotency_key=f"search:{run_id}:authorized_search_api",
        )
        created_count = 0
        deduplicated_count = 0
        for position, item in enumerate(results, start=1):
            metadata = dict(item.get("evidence_metadata") or {})
            metadata.update({"run_id": run_id, "connector_proof": capability.get("proof")})
            item["evidence_metadata"] = metadata
            opportunity, was_duplicate = store.add_opportunity(task_id, item, evidence_status(item))
            created_count += int(not was_duplicate)
            deduplicated_count += int(was_duplicate)
            _record_source_usage(
                store,
                workspace_id,
                task_id,
                "DUPLICATE" if was_duplicate else "SUCCESS",
                f"search:{run_id}:authorized_search_api:{position}:{item.get('source_url', '')}",
                source_position=position,
                source_url=item.get("source_url"),
            )
        if not results:
            _record_source_usage(
                store,
                workspace_id,
                task_id,
                "NO_RESULT",
                f"search:{run_id}:authorized_search_api:no-result",
                units=0,
            )
        completed = store.complete_task_run(
            task_id,
            run_id,
            len(results),
            sum(1 for item in results if evidence_status(item) == "SEND_READY"),
            actor,
        )
        schedule = store.settle_scheduled_task_run(task_id, len(results), created_count)
        return {
            "status": "COMPLETED",
            "task": completed,
            "run_id": run_id,
            "created_count": created_count,
            "deduplicated_count": deduplicated_count,
            "candidate_count": len(results),
            "result_digest": result_digest(results),
            "schedule": schedule,
        }
    except SearchConnectorError as exc:
        _record_source_usage(
            store,
            workspace_id,
            task_id,
            "FAILED",
            f"search:{run_id}:authorized_search_api:failed",
            units=0,
            error_code=exc.code,
        )
        failed = store.fail_task_run(task_id, run_id, exc.code, exc.message, actor)
        schedule = store.settle_scheduled_task_run(task_id, 0, 0, error_code=exc.code, message=exc.message)
        return {"status": "FAILED", "error_code": exc.code, "message": exc.message, "retryable": exc.retryable, "task": failed, "run_id": run_id, "schedule": schedule}
    except Exception:
        _record_source_usage(
            store,
            workspace_id,
            task_id,
            "FAILED",
            f"search:{run_id}:authorized_search_api:failed",
            units=0,
            error_code="connector_internal_error",
        )
        failed = store.fail_task_run(task_id, run_id, "connector_internal_error", "来源连接器执行失败。", actor)
        schedule = store.settle_scheduled_task_run(task_id, 0, 0, error_code="connector_internal_error", message="来源连接器执行失败。")
        return {"status": "FAILED", "error_code": "connector_internal_error", "message": "来源连接器执行失败。", "task": failed, "run_id": run_id, "schedule": schedule}


def run_due_once(
    store: Store,
    workspace_id: str = WORKSPACE_ID,
    *,
    due_at: str | None = None,
    actor: str = "scheduler-worker",
    execute: bool = True,
) -> dict[str, Any]:
    """Claim and process all schedule occurrences due at the supplied time."""

    checked_at = str(due_at or now_iso()).strip()
    schedules = store.list_due_scheduled_tasks(workspace_id, checked_at)
    items: list[dict[str, Any]] = []
    for schedule in schedules:
        plan = build_search_plan(schedule["criteria"], int(schedule["requested_limit"]))
        triggered = store.trigger_scheduled_task(schedule["id"], workspace_id, plan, actor=actor, scheduled_for=checked_at)
        if not triggered:
            continue
        item: dict[str, Any] = {"schedule_id": schedule["id"], "trigger": triggered}
        run = triggered.get("run") or {}
        task = triggered.get("task") or {}
        if execute and run.get("status") == "QUEUED" and task.get("id"):
            item["execution"] = execute_task_once(
                store,
                workspace_id,
                task["id"],
                actor=actor,
                request_id=f"schedule-{schedule['id']}-{checked_at}",
            )
        items.append(item)
    return {"checked_at": checked_at, "due_count": len(schedules), "processed_count": len(items), "items": items}


def run_loop(
    store: Store,
    workspace_id: str = WORKSPACE_ID,
    *,
    interval_seconds: int = 30,
    actor: str = "scheduler-worker",
    stop_event: threading.Event | None = None,
) -> None:
    stop_event = stop_event or threading.Event()
    while not stop_event.is_set():
        run_due_once(store, workspace_id, actor=actor)
        stop_event.wait(max(1, int(interval_seconds)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Lead Radar durable schedule and source worker")
    parser.add_argument("--db", default="apps/lead_radar/lead_radar.sqlite3")
    parser.add_argument("--workspace", default=WORKSPACE_ID)
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    store = Store(args.db)
    try:
        if args.once:
            print(json.dumps(run_due_once(store, args.workspace), ensure_ascii=False))
        else:
            run_loop(store, args.workspace, interval_seconds=args.interval)
    finally:
        store.close()


if __name__ == "__main__":
    main()
