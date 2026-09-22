from __future__ import annotations

import argparse
import json
import mimetypes
import os
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

try:
    from .business_api import (
        BusinessApiError,
        create_search_task,
        enrich_entity,
        fetch_search_results,
        get_search_status,
    )
    from .capture import CaptureError, fetch_public_page
    from .connectors import list_capabilities
    from .domain import compile_intent, evidence_status
    from .feed_api import get_feed_event, list_feed, review_feed_event
    from .index_connector import IndexResultError, normalize_index_results
    from .planner import build_search_plan
    from .proofs import SourceProofError, normalize_source_proof
    from .search_connector import AuthorizedSearchConnector, SearchConnectorError
    from .schedule_api import control_schedule, create_schedule, get_schedule, list_schedules, trigger_schedule
    from .source_policy import classify_public_url
    from .storage import Store
    from .usage import UNIT as USAGE_UNIT, charge_for, source_metadata
except ImportError:  # running server.py directly
    from business_api import BusinessApiError, create_search_task, enrich_entity, fetch_search_results, get_search_status
    from capture import CaptureError, fetch_public_page
    from connectors import list_capabilities
    from domain import compile_intent, evidence_status
    from feed_api import get_feed_event, list_feed, review_feed_event
    from index_connector import IndexResultError, normalize_index_results
    from planner import build_search_plan
    from proofs import SourceProofError, normalize_source_proof
    from search_connector import AuthorizedSearchConnector, SearchConnectorError
    from schedule_api import control_schedule, create_schedule, get_schedule, list_schedules, trigger_schedule
    from source_policy import classify_public_url
    from storage import Store
    from usage import UNIT as USAGE_UNIT, charge_for, source_metadata


ROOT = Path(__file__).resolve().parent
WORKSPACE_ID = "ws_意客AI"


class LeadRadarHandler(BaseHTTPRequestHandler):
    server_version = "LeadRadar/0.1"

    @property
    def store(self) -> Store:
        return self.server.store  # type: ignore[attr-defined]

    def _send(self, status: int, payload: Any, content_type: str = "application/json; charset=utf-8") -> None:
        if isinstance(payload, (dict, list)):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        elif isinstance(payload, str):
            body = payload.encode("utf-8")
        else:
            body = bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Request-ID", getattr(self, "request_id", ""))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Idempotency-Key, X-Request-ID")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, code: str, message: str) -> None:
        self._send(status, {"error": code, "message": message})

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("body_must_be_json") from exc
        if not isinstance(value, dict):
            raise ValueError("body_must_be_object")
        return value

    @staticmethod
    def _normalize_manual_override(item: dict[str, Any]) -> dict[str, Any]:
        """Require an explicit, attributable human promotion to SEND_READY."""

        raw = item.get("manual_override")
        if not isinstance(raw, dict):
            raise ValueError("manual_override_required")
        if raw.get("status") != "SEND_READY":
            raise ValueError("manual_override_status_invalid")
        if raw.get("confirmed") is not True:
            raise ValueError("manual_override_confirmation_required")
        actor = str(raw.get("actor", "")).strip()
        reason = str(raw.get("reason", "")).strip()
        if not actor:
            raise ValueError("manual_override_actor_required")
        if len(actor) > 120:
            raise ValueError("manual_override_actor_too_long")
        if not reason:
            raise ValueError("manual_override_reason_required")
        if len(reason) > 500:
            raise ValueError("manual_override_reason_too_long")
        return {
            "status": "SEND_READY",
            "actor": actor,
            "reason": reason,
            "confirmed": True,
        }

    def _record_source_usage(
        self,
        task_id: str | None,
        operation: str,
        outcome: str,
        idempotency_key: str | None,
        *,
        units: int = 1,
        **metadata: Any,
    ) -> dict[str, Any]:
        """Write one source-result billing fact with the shared SOUBEI rule."""

        normalized_outcome = str(outcome or "").upper()
        credits = charge_for(operation, normalized_outcome, units)
        return self.store.record_usage(
            WORKSPACE_ID,
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

    def do_OPTIONS(self) -> None:
        self.request_id = self._request_id()
        self._send(204, b"")

    def do_GET(self) -> None:
        self.request_id = self._request_id()
        parsed = urlparse(self.path)
        path = unquote(parsed.path).rstrip("/") or "/"
        if path == "/":
            return self._serve_static("index.html")
        if path == "/api/health":
            return self._send(200, {"ok": True, "service": "lead-radar", "workspace_id": WORKSPACE_ID})
        if path == "/api/v1/sources/capabilities":
            return self._send(200, {"items": list_capabilities()})
        if path.startswith("/api/v1/business/get_search_status/"):
            try:
                return self._send(200, get_search_status(self.store, WORKSPACE_ID, path.rsplit("/", 1)[-1]))
            except BusinessApiError as exc:
                return self._error(exc.status, exc.code, exc.message)
        if path.startswith("/api/v1/business/fetch_search_results/"):
            query = parse_qs(parsed.query)
            try:
                return self._send(
                    200,
                    fetch_search_results(
                        self.store,
                        WORKSPACE_ID,
                        path.rsplit("/", 1)[-1],
                        limit=query.get("limit", [20])[0],
                        offset=query.get("offset", [0])[0],
                        status=query.get("status", [None])[0],
                    ),
                )
            except BusinessApiError as exc:
                return self._error(exc.status, exc.code, exc.message)
        if path.startswith("/api/v1/business/enrich_entity/"):
            try:
                return self._send(200, enrich_entity(self.store, WORKSPACE_ID, path.rsplit("/", 1)[-1]))
            except BusinessApiError as exc:
                return self._error(exc.status, exc.code, exc.message)
        if path == f"/api/v1/workspaces/{WORKSPACE_ID}/schedules":
            return self._send(200, list_schedules(self.store, WORKSPACE_ID))
        if path == f"/api/v1/workspaces/{WORKSPACE_ID}/feed":
            query = parse_qs(parsed.query)
            try:
                return self._send(
                    200,
                    list_feed(
                        self.store,
                        WORKSPACE_ID,
                        event_type=query.get("event_type", [None])[0],
                        status=query.get("status", [None])[0],
                        since=query.get("since", [None])[0],
                        limit=query.get("limit", [50])[0],
                        offset=query.get("offset", [0])[0],
                    ),
                )
            except BusinessApiError as exc:
                return self._error(exc.status, exc.code, exc.message)
        if path.startswith("/api/v1/feed-events/") and path.count("/") == 4:
            try:
                return self._send(200, get_feed_event(self.store, WORKSPACE_ID, path.rsplit("/", 1)[-1]))
            except BusinessApiError as exc:
                return self._error(exc.status, exc.code, exc.message)
        if path.startswith("/api/v1/schedules/") and path.count("/") == 4:
            try:
                return self._send(200, get_schedule(self.store, WORKSPACE_ID, path.rsplit("/", 1)[-1]))
            except BusinessApiError as exc:
                return self._error(exc.status, exc.code, exc.message)
        if path == f"/api/v1/workspaces/{WORKSPACE_ID}/dashboard":
            return self._send(200, self.store.dashboard(WORKSPACE_ID))
        if path == f"/api/v1/workspaces/{WORKSPACE_ID}/audit":
            limit = parse_qs(parsed.query).get("limit", ["100"])[0]
            return self._send(200, self.store.audit_usage(WORKSPACE_ID, limit))
        if path == f"/api/v1/workspaces/{WORKSPACE_ID}/source-proofs":
            return self._send(200, {"items": self.store.list_source_proofs(WORKSPACE_ID)})
        if path == f"/api/v1/workspaces/{WORKSPACE_ID}/tasks":
            return self._send(200, {"items": self.store.list_tasks(WORKSPACE_ID)})
        if path == f"/api/v1/workspaces/{WORKSPACE_ID}/opportunities":
            status = parse_qs(parsed.query).get("status", [None])[0]
            return self._send(200, {"items": self.store.list_opportunities(WORKSPACE_ID, status)})
        if path == f"/api/v1/workspaces/{WORKSPACE_ID}/entities":
            return self._send(200, {"items": self.store.list_entities(WORKSPACE_ID)})
        if path == f"/api/v1/workspaces/{WORKSPACE_ID}/calibration-batches":
            return self._send(200, {"items": self.store.list_calibration_batches(WORKSPACE_ID)})
        if path.startswith("/api/v1/tasks/") and path.count("/") == 4:
            task = self.store.get_task(path.rsplit("/", 1)[-1])
            return self._send(200, task) if task else self._error(404, "task_not_found", "任务不存在")
        if path.startswith("/api/v1/tasks/") and path.endswith("/plan"):
            task = self.store.get_task(path.split("/")[-2])
            return self._send(200, task["plan"]) if task and task.get("plan") else self._error(404, "plan_not_found", "任务计划不存在")
        if path.startswith("/api/v1/tasks/") and path.endswith("/events"):
            parts = path.split("/")
            task_id, run_id = parts[-4], parts[-2]
            events = self.store.get_task_run_events(task_id, run_id)
            return self._send(200, {"run_id": run_id, "events": events}) if events is not None else self._error(404, "run_not_found", "运行实例不存在")
        if path.startswith("/api/v1/opportunities/") and path.count("/") == 4:
            opportunity = self.store.get_opportunity(path.rsplit("/", 1)[-1])
            return self._send(200, opportunity) if opportunity else self._error(404, "opportunity_not_found", "机会不存在")
        if path.startswith("/api/v1/opportunities/") and path.endswith("/action-drafts"):
            opportunity_id = path.split("/")[-2]
            opportunity = self.store.get_opportunity(opportunity_id)
            if not opportunity or opportunity.get("workspace_id") != WORKSPACE_ID:
                return self._error(404, "opportunity_not_found", "机会不存在")
            return self._send(200, {"items": self.store.list_action_drafts(opportunity_id, WORKSPACE_ID)})
        if path.startswith("/api/v1/entities/") and path.count("/") == 4:
            entity = self.store.get_entity(path.rsplit("/", 1)[-1])
            return self._send(200, entity) if entity else self._error(404, "entity_not_found", "实体不存在")
        if path.startswith("/api/v1/calibration-batches/") and path.count("/") == 4:
            batch = self.store.get_calibration_batch(path.rsplit("/", 1)[-1], WORKSPACE_ID)
            return self._send(200, batch) if batch else self._error(404, "calibration_batch_not_found", "校准批次不存在")
        return self._error(404, "not_found", "接口不存在")

    def do_POST(self) -> None:
        self.request_id = self._request_id()
        parsed = urlparse(self.path)
        path = unquote(parsed.path).rstrip("/")
        try:
            payload = self._body()
            if path == "/api/v1/business/create_search_task":
                result = create_search_task(self.store, WORKSPACE_ID, payload, self.headers.get("Idempotency-Key"))
                result["request_id"] = self.request_id
                return self._send(201, result)
            if path == f"/api/v1/workspaces/{WORKSPACE_ID}/schedules":
                return self._send(201, create_schedule(self.store, WORKSPACE_ID, payload))
            if path.startswith("/api/v1/schedules/") and path.endswith("/trigger"):
                return self._send(200, trigger_schedule(self.store, WORKSPACE_ID, path.split("/")[-2], payload.get("actor", "scheduler"), payload.get("scheduled_for")))
            if path.startswith("/api/v1/schedules/") and path.endswith("/pause"):
                return self._send(200, control_schedule(self.store, WORKSPACE_ID, path.split("/")[-2], "pause", payload.get("actor", "operator")))
            if path.startswith("/api/v1/schedules/") and path.endswith("/resume"):
                return self._send(200, control_schedule(self.store, WORKSPACE_ID, path.split("/")[-2], "resume", payload.get("actor", "operator")))
            if path.startswith("/api/v1/feed-events/") and path.endswith("/review"):
                return self._send(200, review_feed_event(self.store, WORKSPACE_ID, path.split("/")[-2], payload))
            if path == f"/api/v1/workspaces/{WORKSPACE_ID}/profiles":
                return self._create_profile(payload)
            if path == f"/api/v1/workspaces/{WORKSPACE_ID}/source-proofs/revoke":
                return self._revoke_source_proof(payload)
            if path == f"/api/v1/workspaces/{WORKSPACE_ID}/source-proofs":
                return self._register_source_proof(payload)
            if path == f"/api/v1/workspaces/{WORKSPACE_ID}/tasks":
                return self._create_task(payload)
            if path == f"/api/v1/workspaces/{WORKSPACE_ID}/calibration-batches":
                return self._create_calibration_batch(payload)
            if path.startswith("/api/v1/tasks/") and path.endswith("/capture-url"):
                return self._capture_url(path.split("/")[-2], payload)
            if path.startswith("/api/v1/tasks/") and path.endswith("/capture-urls"):
                return self._capture_urls(path.split("/")[-2], payload)
            if path.startswith("/api/v1/tasks/") and path.endswith("/index-results"):
                return self._ingest_index_results(path.split("/")[-2], payload)
            if path.startswith("/api/v1/tasks/") and path.endswith("/start"):
                return self._start_task(path.split("/")[-2], payload)
            if path.startswith("/api/v1/tasks/") and path.endswith("/execute"):
                return self._execute_task(path.split("/")[-2], payload)
            if path.startswith("/api/v1/tasks/") and path.split("/")[-1] in {"pause", "resume", "cancel", "retry"}:
                parts = path.split("/")
                return self._control_run(parts[-4], parts[-2], parts[-1], payload)
            if path.startswith("/api/v1/tasks/") and path.endswith("/opportunities"):
                return self._add_opportunities(path.split("/")[-2], payload)
            if path.startswith("/api/v1/opportunities/") and path.endswith("/feedback"):
                return self._feedback(path.split("/")[-2], payload)
            if path.startswith("/api/v1/opportunities/") and path.endswith("/action-drafts"):
                return self._create_action_drafts(path.split("/")[-2], payload)
            if path.startswith("/api/v1/action-drafts/") and path.endswith("/approve"):
                return self._approve_action_draft(path.split("/")[-2], payload)
            if path.startswith("/api/v1/action-drafts/") and path.endswith("/cancel"):
                return self._cancel_action_draft(path.split("/")[-2], payload)
            if path.startswith("/api/v1/opportunities/") and path.endswith("/reopen"):
                return self._reopen_evidence(path.split("/")[-2])
            if path.startswith("/api/v1/entities/") and path.endswith("/merge"):
                return self._merge_entity(path.split("/")[-2], payload)
            if path.startswith("/api/v1/entities/") and path.endswith("/split"):
                return self._split_entity(path.split("/")[-2], payload)
            if path.startswith("/api/v1/calibration-batches/") and path.endswith("/review"):
                parts = path.split("/")
                return self._review_calibration_item(parts[-4], parts[-2], payload)
        except BusinessApiError as exc:
            return self._error(exc.status, exc.code, exc.message)
        except CaptureError as exc:
            return self._error(400, exc.code, exc.message)
        except IndexResultError as exc:
            return self._error(400, exc.code, exc.message)
        except SourceProofError as exc:
            return self._error(400, exc.code, exc.message)
        except ValueError as exc:
            return self._error(400, "invalid_request", str(exc))
        except KeyError as exc:
            return self._error(404, str(exc).strip("'"), "关联对象不存在")
        except Exception as exc:  # keep the API response safe while preserving local traceback in development
            if os.environ.get("LEAD_RADAR_DEBUG"):
                raise
            return self._error(500, "internal_error", str(exc))
        return self._error(404, "not_found", "接口不存在")

    def _request_id(self) -> str:
        supplied = self.headers.get("X-Request-ID", "").strip()
        if supplied and len(supplied) <= 100 and all(character.isalnum() or character in {"-", "_", "."} for character in supplied):
            return supplied
        return f"req_{uuid.uuid4().hex}"

    def _create_profile(self, payload: dict[str, Any]) -> None:
        objective = str(payload.get("objective", "")).strip()
        if not objective:
            raise ValueError("objective_required")
        criteria = compile_intent(objective, payload.get("criteria"))
        profile = self.store.create_profile(WORKSPACE_ID, str(payload.get("name") or "自定义画像"), objective, criteria)
        self._send(201, profile)

    def _register_source_proof(self, payload: dict[str, Any]) -> None:
        proof = normalize_source_proof(payload)
        registered, created = self.store.save_source_proof(WORKSPACE_ID, proof)
        self._send(201 if created else 200, {"proof": registered, "created": created})

    def _revoke_source_proof(self, payload: dict[str, Any]) -> None:
        proof_ref = str(payload.get("proof_ref") or "").strip()
        if not proof_ref:
            raise ValueError("proof_ref_required")
        revoked = self.store.revoke_source_proof(WORKSPACE_ID, proof_ref, str(payload.get("actor", "operator")))
        if not revoked:
            return self._error(404, "source_proof_not_found", "来源证明不存在")
        self._send(200, {"proof": revoked, "message": "来源证明已撤销，后续索引导入将被阻断。"})

    def _create_task(self, payload: dict[str, Any]) -> None:
        objective = str(payload.get("objective", "")).strip()
        if not objective:
            raise ValueError("objective_required")
        requested_limit = max(1, min(int(payload.get("requested_limit", 10)), 500))
        criteria = compile_intent(objective, payload.get("criteria"))
        plan = build_search_plan(criteria, requested_limit)
        idempotency_key = self.headers.get("Idempotency-Key") or payload.get("idempotency_key")
        quoted_max = plan["cost_estimate"].get("max_credits")
        requested_estimate = payload.get("estimated_credits", quoted_max)
        estimated_credits = 0 if requested_estimate is None else int(requested_estimate)
        task = self.store.create_task(
            WORKSPACE_ID,
            payload.get("profile_id"),
            objective,
            criteria,
            requested_limit,
            estimated_credits,
            idempotency_key,
            plan,
        )
        self._send(201, task)

    def _create_calibration_batch(self, payload: dict[str, Any]) -> None:
        name = str(payload.get("name") or "真实候选校准").strip()
        target_count = int(payload.get("target_count", 30))
        opportunity_ids = payload.get("opportunity_ids")
        if opportunity_ids is not None and not isinstance(opportunity_ids, list):
            raise ValueError("opportunity_ids_must_be_array")
        batch = self.store.create_calibration_batch(WORKSPACE_ID, name, target_count, opportunity_ids)
        if not batch:
            return self._error(404, "workspace_not_found", "工作区不存在")
        self._send(201, batch)

    def _start_task(self, task_id: str, payload: dict[str, Any]) -> None:
        task = self.store.start_task(task_id, str(payload.get("mode", "quick")))
        if not task:
            return self._error(404, "task_not_found", "任务不存在")
        latest_run = task.get("runs", [None])[0]
        message = "任务已进入队列。" if latest_run and latest_run["status"] == "QUEUED" else "任务计划已生成，但当前没有通过生产门禁的自动搜索连接器。"
        self._send(200, {**task, "message": message})

    def _execute_task(self, task_id: str, payload: dict[str, Any]) -> None:
        task = self.store.get_task(task_id)
        if not task:
            return self._error(404, "task_not_found", "任务不存在")
        mode = str(payload.get("mode", "quick"))
        connector = AuthorizedSearchConnector()
        capability = connector.preflight()
        plan = task.get("plan") or {}
        if capability.get("status") != "READY" or "authorized_search_api" not in plan.get("runnable_sources", []):
            return self._send(
                409,
                {
                    "error": "source_not_ready",
                    "message": "当前任务没有通过授权搜索 API 的生产门禁。",
                    "capability": capability,
                    "task": task,
                },
            )
        task = self.store.start_task(task_id, mode)
        if not task:
            return self._error(404, "task_not_found", "任务不存在")
        run = task.get("runs", [None])[0]
        if not run or run.get("status") != "QUEUED":
            return self._send(409, {"error": "run_not_ready", "message": "任务运行实例当前不能执行。", "task": task, "run": run})
        run_id = run["id"]
        self.store.begin_task_run(task_id, run_id)
        try:
            results = connector.search(plan, mode)
            created_count = 0
            deduplicated_count = 0
            for position, item in enumerate(results, start=1):
                metadata = dict(item.get("evidence_metadata") or {})
                metadata["run_id"] = run_id
                item["evidence_metadata"] = metadata
                opportunity, was_duplicate = self.store.add_opportunity(task_id, item, evidence_status(item))
                created_count += int(not was_duplicate)
                deduplicated_count += int(was_duplicate)
                self._record_source_usage(
                    task_id,
                    "authorized_search_api",
                    "DUPLICATE" if was_duplicate else "SUCCESS",
                    f"search:{run_id}:authorized_search_api:{position}:{item.get('source_url', '')}",
                    source_position=position,
                    source_url=item.get("source_url"),
                )
            if not results:
                self._record_source_usage(
                    task_id,
                    "authorized_search_api",
                    "NO_RESULT",
                    f"search:{run_id}:authorized_search_api:no-result",
                    units=0,
                )
            completed = self.store.complete_task_run(task_id, run_id, len(results), sum(1 for item in results if evidence_status(item) == "SEND_READY"))
            schedule = self.store.settle_scheduled_task_run(task_id, len(results), created_count)
            self._send(200, {"task": completed, "run_id": run_id, "created_count": created_count, "deduplicated_count": deduplicated_count, "candidate_count": len(results), "schedule": schedule})
        except SearchConnectorError as exc:
            self._record_source_usage(
                task_id,
                "authorized_search_api",
                "FAILED",
                f"search:{run_id}:authorized_search_api:failed",
                units=0,
                error_code=exc.code,
            )
            failed = self.store.fail_task_run(task_id, run_id, exc.code, exc.message)
            schedule = self.store.settle_scheduled_task_run(task_id, 0, 0, error_code=exc.code, message=exc.message)
            self._send(502, {"error": exc.code, "message": exc.message, "retryable": exc.retryable, "task": failed, "run_id": run_id, "schedule": schedule})
        except Exception as exc:
            self._record_source_usage(
                task_id,
                "authorized_search_api",
                "FAILED",
                f"search:{run_id}:authorized_search_api:failed",
                units=0,
                error_code="connector_internal_error",
            )
            failed = self.store.fail_task_run(task_id, run_id, "connector_internal_error", str(exc))
            schedule = self.store.settle_scheduled_task_run(task_id, 0, 0, error_code="connector_internal_error", message="来源连接器执行失败。")
            if os.environ.get("LEAD_RADAR_DEBUG"):
                raise
            self._send(500, {"error": "connector_internal_error", "message": "来源连接器执行失败。", "task": failed, "run_id": run_id, "schedule": schedule})

    def _control_run(self, task_id: str, run_id: str, action: str, payload: dict[str, Any]) -> None:
        actor = str(payload.get("actor", "operator"))
        task = self.store.retry_task_run(task_id, run_id, actor) if action == "retry" else self.store.control_task_run(task_id, run_id, action, actor)
        if not task:
            return self._error(404, "run_not_found", "运行实例不存在")
        latest_run = task.get("runs", [None])[0]
        self._send(200, {**task, "message": f"运行实例已执行：{action}", "run": latest_run})

    @staticmethod
    def _build_captured_item(payload: dict[str, Any], capture: dict[str, Any]) -> dict[str, Any]:
        source = classify_public_url(capture["final_url"])
        return {
            "title": str(payload.get("title") or capture["title"] or urlparse(capture["final_url"]).hostname or "公开网页"),
            "author": payload.get("author"),
            "entity_name": payload.get("entity_name") or payload.get("company_name"),
            "entity_type": payload.get("entity_type", "organization"),
            "published_at": payload.get("published_at"),
            "intent_type": payload.get("intent_type"),
            "industry_location": payload.get("industry_location"),
            "source_kind": "public_url_capture",
            "source_url": capture["final_url"],
            "snippet": capture["snippet"],
            "evidence_level": "CAPTURED",
            "source_permission": "public_url_user_supplied",
            "evidence_type": "captured_page_excerpt",
            "captured_at": capture["captured_at"],
            "evidence_metadata": {
                "requested_url": capture["requested_url"],
                "final_url": capture["final_url"],
                "content_hash": capture["content_hash"],
                "byte_length": capture["byte_length"],
                "content_type": capture["content_type"],
                "charset": capture["charset"],
                "capture_method": "controlled_public_url_capture",
                "source_provenance": source,
            },
        }

    def _capture_url(self, task_id: str, payload: dict[str, Any]) -> None:
        task = self.store.get_task(task_id)
        if not task:
            return self._error(404, "task_not_found", "任务不存在")
        requested_url = str(payload.get("url", "")).strip()
        if not requested_url:
            raise ValueError("url_required")
        try:
            capture = fetch_public_page(requested_url)
        except CaptureError as exc:
            self._record_source_usage(
                task_id,
                "public_url_capture",
                "FAILED",
                f"public-url:{task_id}:{requested_url}:failed",
                units=0,
                requested_url=requested_url,
                error_code=exc.code,
            )
            raise
        item = self._build_captured_item(payload, capture)
        status = evidence_status(item)
        opportunity, was_duplicate = self.store.add_opportunity(task_id, item, status)
        usage = self._record_source_usage(
            task_id,
            "public_url_capture",
            "DUPLICATE" if was_duplicate else "SUCCESS",
            f"public-url:{task_id}:{requested_url}",
            source_url=capture["final_url"],
        )
        self._send(
            201,
            {
                "item": opportunity,
                "created": not was_duplicate,
                "capture": {
                    "title": capture["title"],
                    "requested_url": capture["requested_url"],
                    "final_url": capture["final_url"],
                    "content_hash": capture["content_hash"],
                    "captured_at": capture["captured_at"],
                },
                "usage": usage["entry"],
            },
        )

    def _capture_urls(self, task_id: str, payload: dict[str, Any]) -> None:
        task = self.store.get_task(task_id)
        if not task:
            return self._error(404, "task_not_found", "任务不存在")
        raw_items = payload.get("items")
        if raw_items is None and isinstance(payload.get("urls"), list):
            raw_items = [{"url": value} for value in payload["urls"]]
        if not isinstance(raw_items, list) or not raw_items:
            raise ValueError("items_required")
        if len(raw_items) > 50:
            raise ValueError("items_limit_exceeded")
        items: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for index, raw_item in enumerate(raw_items):
            if isinstance(raw_item, str):
                raw_item = {"url": raw_item}
            if not isinstance(raw_item, dict):
                errors.append({"index": index, "error": "item_must_be_object"})
                self._record_source_usage(
                    task_id,
                    "public_url_batch_capture",
                    "FAILED",
                    f"public-url:{task_id}:index:{index}:invalid",
                    units=0,
                    item_index=index,
                    error_code="item_must_be_object",
                )
                continue
            requested_url = str(raw_item.get("url", "")).strip()
            if not requested_url:
                errors.append({"index": index, "error": "url_required"})
                self._record_source_usage(
                    task_id,
                    "public_url_batch_capture",
                    "FAILED",
                    f"public-url:{task_id}:index:{index}:missing-url",
                    units=0,
                    item_index=index,
                    error_code="url_required",
                )
                continue
            try:
                capture = fetch_public_page(requested_url)
                item = self._build_captured_item(raw_item, capture)
                opportunity, was_duplicate = self.store.add_opportunity(task_id, item, evidence_status(item))
                usage = self._record_source_usage(
                    task_id,
                    "public_url_batch_capture",
                    "DUPLICATE" if was_duplicate else "SUCCESS",
                    f"public-url:{task_id}:index:{index}:{requested_url}",
                    requested_url=requested_url,
                    item_index=index,
                )
                items.append({
                    "item": opportunity,
                    "created": not was_duplicate,
                    "capture": {"requested_url": capture["requested_url"], "final_url": capture["final_url"], "content_hash": capture["content_hash"]},
                    "usage": usage["entry"],
                })
            except CaptureError as exc:
                self._record_source_usage(
                    task_id,
                    "public_url_batch_capture",
                    "FAILED",
                    f"public-url:{task_id}:{requested_url}:failed",
                    units=0,
                    requested_url=requested_url,
                    error_code=exc.code,
                )
                errors.append({"index": index, "url": requested_url, "error": exc.code, "message": exc.message})
        self._send(200, {"items": items, "errors": errors, "created_count": sum(int(item["created"]) for item in items), "failed_count": len(errors)})

    def _ingest_index_results(self, task_id: str, payload: dict[str, Any]) -> None:
        task = self.store.get_task(task_id)
        if not task:
            return self._error(404, "task_not_found", "任务不存在")
        context, normalized = normalize_index_results(payload)
        proof = self.store.get_source_proof(WORKSPACE_ID, context["proof_ref"], context["provider"])
        if not proof:
            raise IndexResultError("proof_not_registered", "索引结果的 proof_ref/provider 尚未在当前工作区登记来源证明。")
        if context["result_status"] == "NO_MATCHES":
            run_key = "index-run:{}:{}:{}:{}".format(
                task_id,
                context["provider"],
                context["query"],
                context["retrieved_at"],
            )
            self._record_source_usage(
                task_id,
                "search_index_import",
                "NO_RESULT",
                run_key,
                units=0,
                provider=context["provider"],
                proof_ref=context["proof_ref"],
                query=context["query"],
            )
            self._send(
                201,
                {
                    "items": [],
                    "created_count": 0,
                    "deduplicated_count": 0,
                    "source": {
                        **context,
                        "reopen_required": False,
                        "proof_registry_status": "REGISTERED",
                        "proof_artifact_sha256": proof["artifact_sha256"],
                    },
                    "message": "已完成公开索引搜索，本次没有返回合格候选。",
                },
            )
            return
        items: list[dict[str, Any]] = []
        deduplicated = 0
        for item in normalized:
            item["evidence_metadata"].update(
                {
                    "proof_registry_status": "REGISTERED",
                    "proof_artifact_sha256": proof["artifact_sha256"],
                    "proof_checked_at": proof["checked_at"],
                    "proof_endpoint": proof["endpoint"],
                    "proof_checks": proof["checks"],
                }
            )
            opportunity, was_duplicate = self.store.add_opportunity(task_id, item, evidence_status(item))
            idempotency_key = "index:{}:{}:{}:{}".format(
                task_id,
                context["provider"],
                context["retrieved_at"],
                item["source_url"],
            )
            usage = self._record_source_usage(
                task_id,
                "search_index_import",
                "DUPLICATE" if was_duplicate else "SUCCESS",
                idempotency_key,
                source_url=item["source_url"],
                provider=context["provider"],
                proof_ref=context["proof_ref"],
            )
            items.append({"item": opportunity, "created": not was_duplicate, "usage": usage["entry"]})
            deduplicated += int(was_duplicate)
        self._send(
            201,
            {
                "items": items,
                "created_count": len(items) - deduplicated,
                "deduplicated_count": deduplicated,
                "source": {
                    **context,
                    "reopen_required": True,
                    "proof_registry_status": "REGISTERED",
                    "proof_artifact_sha256": proof["artifact_sha256"],
                },
            },
        )

    def _add_opportunities(self, task_id: str, payload: dict[str, Any]) -> None:
        task = self.store.get_task(task_id)
        if not task:
            return self._error(404, "task_not_found", "任务不存在")
        raw_items = payload.get("items")
        if raw_items is None:
            raw_items = [payload]
        if not isinstance(raw_items, list) or not raw_items:
            raise ValueError("items_required")
        if len(raw_items) > 100:
            raise ValueError("items_limit_exceeded")
        created: list[dict[str, Any]] = []
        deduplicated = 0
        for item in raw_items:
            if not isinstance(item, dict):
                raise ValueError("item_must_be_object")
            item = dict(item)
            # This private field is server-generated below; callers cannot
            # smuggle an already-normalized override into the audit trail.
            item.pop("_manual_override", None)
            for required in ("title", "source_url", "snippet"):
                if not str(item.get(required, "")).strip():
                    raise ValueError(f"{required}_required")
            if not str(item["source_url"]).startswith(("http://", "https://")):
                raise ValueError("source_url_must_be_http")
            status = evidence_status(item)
            if item.get("status") == "SEND_READY" and status != "SEND_READY":
                raise ValueError("send_ready_requires_verified_allowed_evidence")
            if status == "SEND_READY":
                override = self._normalize_manual_override(item)
                item["_manual_override"] = override
                evidence_metadata = dict(item.get("evidence_metadata") or {})
                evidence_metadata["manual_override"] = override
                item["evidence_metadata"] = evidence_metadata
            elif item.get("manual_override") is not None:
                raise ValueError("manual_override_requires_verified_allowed_evidence")
            opportunity, was_duplicate = self.store.add_opportunity(task_id, item, status)
            self.store.record_usage(WORKSPACE_ID, task_id, "evidence_ingest", 1, 0, "COMPLETED")
            created.append(opportunity)  # type: ignore[arg-type]
            deduplicated += int(was_duplicate)
        self._send(201, {"items": created, "created_count": len(created) - deduplicated, "deduplicated_count": deduplicated})

    def _feedback(self, opportunity_id: str, payload: dict[str, Any]) -> None:
        label = str(payload.get("label", "")).upper()
        if label not in {
            "VALID",
            "REVIEW",
            "OBSERVE",
            "INVALID",
            "DUPLICATE",
            "CONTACTED",
            "DEFERRED",
            "HANDOFF",
            "UNSUBSCRIBED",
        }:
            raise ValueError("invalid_feedback_label")
        note = str(payload.get("note", "")).strip()
        if label == "UNSUBSCRIBED" and not note:
            raise ValueError("unsubscribe_reason_required")
        opportunity = self.store.add_feedback(opportunity_id, label, note, str(payload.get("actor", "operator")))
        if not opportunity:
            return self._error(404, "opportunity_not_found", "机会不存在")
        self._send(200, opportunity)

    def _create_action_drafts(self, opportunity_id: str, payload: dict[str, Any]) -> None:
        opportunity = self.store.get_opportunity(opportunity_id)
        if not opportunity or opportunity.get("workspace_id") != WORKSPACE_ID:
            return self._error(404, "opportunity_not_found", "机会不存在")
        channels = payload.get("channels", ["PUBLIC_REPLY", "EMAIL", "FEISHU_TASK", "CRM_TASK"])
        if not isinstance(channels, list):
            raise ValueError("action_channels_must_be_array")
        request_key = self.headers.get("Idempotency-Key") or payload.get("idempotency_key")
        if request_key is not None and not isinstance(request_key, str):
            raise ValueError("idempotency_key_must_be_string")
        drafts = self.store.create_action_drafts(
            opportunity_id,
            channels,
            str(payload.get("actor", "operator")),
            request_key,
        )
        if drafts is None:
            return self._error(404, "opportunity_not_found", "机会不存在")
        self._send(200, {"items": drafts, "count": len(drafts), "message": "动作草案已生成，尚未发送。"})

    def _approve_action_draft(self, draft_id: str, payload: dict[str, Any]) -> None:
        draft = self.store.get_action_draft(draft_id, WORKSPACE_ID)
        if not draft:
            return self._error(404, "action_draft_not_found", "动作草案不存在")
        confirm = payload.get("confirm")
        if not isinstance(confirm, bool):
            raise ValueError("confirm_must_be_boolean")
        approved = self.store.approve_action_draft(draft_id, str(payload.get("actor", "operator")), confirm)
        if not approved:
            return self._error(404, "action_draft_not_found", "动作草案不存在")
        self._send(200, {"draft": approved, "sent": False, "message": "草案已人工批准，但系统尚未发送。"})

    def _cancel_action_draft(self, draft_id: str, payload: dict[str, Any]) -> None:
        draft = self.store.get_action_draft(draft_id, WORKSPACE_ID)
        if not draft:
            return self._error(404, "action_draft_not_found", "动作草案不存在")
        cancelled = self.store.cancel_action_draft(draft_id, str(payload.get("actor", "operator")))
        if not cancelled:
            return self._error(404, "action_draft_not_found", "动作草案不存在")
        self._send(200, {"draft": cancelled, "message": "草案已取消，未发送。"})

    def _merge_entity(self, source_id: str, payload: dict[str, Any]) -> None:
        target_id = str(payload.get("target_entity_id", "")).strip()
        if not target_id:
            raise ValueError("target_entity_id_required")
        entity = self.store.merge_entities(source_id, target_id, str(payload.get("actor", "operator")), str(payload.get("reason", "")))
        if not entity:
            return self._error(404, "entity_not_found", "实体不存在或关联不完整")
        self._send(200, entity)

    def _split_entity(self, entity_id: str, payload: dict[str, Any]) -> None:
        opportunity_id = str(payload.get("opportunity_id", "")).strip()
        new_name = str(payload.get("entity_name") or payload.get("new_name") or "").strip()
        if not opportunity_id:
            raise ValueError("opportunity_id_required")
        if not new_name:
            raise ValueError("entity_name_required")
        entity = self.store.split_entity(
            entity_id,
            opportunity_id,
            new_name,
            str(payload.get("website_host", "")),
            str(payload.get("actor", "operator")),
            str(payload.get("reason", "")),
        )
        if not entity:
            return self._error(404, "entity_not_found", "实体或机会关联不存在")
        self._send(200, entity)

    def _review_calibration_item(self, batch_id: str, item_id: str, payload: dict[str, Any]) -> None:
        batch = self.store.get_calibration_batch(batch_id, WORKSPACE_ID)
        if not batch:
            return self._error(404, "calibration_batch_not_found", "校准批次不存在")
        gold_label = payload.get("gold_label")
        if not isinstance(gold_label, str):
            raise ValueError("gold_label_must_be_string")
        reviewer = payload.get("reviewer", "operator")
        note = payload.get("note", "")
        apply_feedback = payload.get("apply_feedback", True)
        if not isinstance(reviewer, str) or not isinstance(note, str):
            raise ValueError("reviewer_and_note_must_be_string")
        if not isinstance(apply_feedback, bool):
            raise ValueError("apply_feedback_must_be_boolean")
        result = self.store.review_calibration_item(
            batch_id,
            item_id,
            gold_label,
            reviewer,
            note,
            apply_feedback,
        )
        if not result:
            return self._error(404, "calibration_item_not_found", "校准样本不存在")
        self._send(200, result)

    def _reopen_evidence(self, opportunity_id: str) -> None:
        opportunity = self.store.get_opportunity(opportunity_id)
        if not opportunity:
            return self._error(404, "opportunity_not_found", "机会不存在")
        source_kind = opportunity.get("source_kind")
        if source_kind not in {"public_url_capture", "search_index_snippet", "authorized_search_api"}:
            raise ValueError("reopen_supported_for_public_or_index_sources_only")
        request_key = self.headers.get("Idempotency-Key")
        if not request_key:
            raise ValueError("idempotency_key_required")
        ledger_key = f"public-url-reopen:{opportunity_id}:{request_key}" if request_key else None
        if ledger_key:
            previous = self.store.get_usage_by_idempotency_key(WORKSPACE_ID, ledger_key, "public_url_reopen")
            if previous:
                latest = self.store.get_opportunity(opportunity_id)
                previous_reopen = next(
                    (item for item in reversed(latest.get("evidence", [])) if item.get("evidence_type") == "reopen_check"),
                    {},
                ) if latest else {}
                previous_metadata = previous_reopen.get("metadata") or {}
                return self._send(
                    200,
                    {
                        "opportunity": latest,
                        "reopen": {
                            "matches_previous_snapshot": bool(previous_metadata.get("matches_previous_snapshot")),
                            "content_hash": previous_metadata.get("content_hash"),
                            "captured_at": previous_reopen.get("captured_at"),
                            "source_kind": source_kind,
                            "reopen_required": False,
                            "keeps_review": True,
                            "replayed": True,
                        },
                    },
                )
        capture = fetch_public_page(opportunity["source_url"])
        previous_hashes = [
            evidence.get("metadata", {}).get("content_hash")
            for evidence in opportunity.get("evidence", [])
            if evidence.get("metadata", {}).get("content_hash")
        ]
        matches_previous = bool(previous_hashes) and capture["content_hash"] == previous_hashes[-1]
        original_evidence = (opportunity.get("evidence") or [{}])[0]
        original_metadata = original_evidence.get("metadata") or {}
        reopen_decision = {
            "status": opportunity.get("status", "REVIEW"),
            "code": "REOPENED_SOURCE_NEEDS_REVIEW",
            "reason": "原始 URL 已成功重开并追加当前页面快照，但页面相关性、发布时间和来源使用权仍需人工确认。",
            "missing_fields": [],
            "next_action": "人工核对重开页面与索引摘要是否一致，再决定有效、观察或排除。",
        }
        updated = self.store.append_evidence(
            opportunity_id,
            "reopen_check",
            capture["snippet"],
            capture["final_url"],
            {
                "requested_url": capture["requested_url"],
                "final_url": capture["final_url"],
                "content_hash": capture["content_hash"],
                "byte_length": capture["byte_length"],
                "content_type": capture["content_type"],
                "charset": capture["charset"],
                "capture_method": "controlled_public_url_reopen",
                "matches_previous_snapshot": matches_previous,
                "reopen_from_source_kind": source_kind,
                "original_evidence_type": original_evidence.get("evidence_type"),
                "original_source_provenance": original_metadata.get("source_provenance"),
                "proof_ref": original_metadata.get("proof_ref"),
                "provider": original_metadata.get("provider"),
                "source_provenance": classify_public_url(capture["final_url"]),
            },
            capture["captured_at"],
            reopen_decision,
        )
        self._record_source_usage(
            opportunity.get("task_id"),
            "public_url_reopen",
            "SUCCESS",
            ledger_key,
            source_url=capture["final_url"],
            opportunity_id=opportunity_id,
        )
        self._send(
            200,
            {
                "opportunity": updated,
                "reopen": {
                    "matches_previous_snapshot": matches_previous,
                    "content_hash": capture["content_hash"],
                    "captured_at": capture["captured_at"],
                    "source_kind": source_kind,
                    "reopen_required": False,
                    "keeps_review": True,
                    "replayed": False,
                },
            },
        )

    def _serve_static(self, filename: str) -> None:
        target = (ROOT / "web" / filename).resolve()
        if ROOT not in target.parents:
            return self._error(403, "forbidden", "禁止访问")
        if not target.exists():
            return self._error(404, "not_found", "页面不存在")
        body = target.read_bytes()
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self._send(200, body, f"{content_type}; charset=utf-8" if content_type.startswith("text/") else content_type)

    def log_message(self, format: str, *args: Any) -> None:
        if os.environ.get("LEAD_RADAR_ACCESS_LOG"):
            super().log_message(format, *args)


def create_server(host: str = "127.0.0.1", port: int = 8780, db_path: str = "lead_radar.sqlite3") -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), LeadRadarHandler)
    server.store = Store(db_path)  # type: ignore[attr-defined]
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="意客 AI Lead Radar local workspace")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8780)
    parser.add_argument("--db", default=str(ROOT / "lead_radar.sqlite3"))
    args = parser.parse_args()
    server = create_server(args.host, args.port, args.db)
    print(f"Lead Radar running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.store.close()  # type: ignore[attr-defined]
        server.server_close()


if __name__ == "__main__":
    main()
