from __future__ import annotations

import argparse
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

try:
    from .capture import CaptureError, fetch_public_page
    from .connectors import list_capabilities
    from .domain import compile_intent, evidence_status
    from .planner import build_search_plan
    from .storage import Store
except ImportError:  # running server.py directly
    from capture import CaptureError, fetch_public_page
    from connectors import list_capabilities
    from domain import compile_intent, evidence_status
    from planner import build_search_plan
    from storage import Store


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
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Idempotency-Key")
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

    def do_OPTIONS(self) -> None:
        self._send(204, b"")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path).rstrip("/") or "/"
        if path == "/":
            return self._serve_static("index.html")
        if path == "/api/health":
            return self._send(200, {"ok": True, "service": "lead-radar", "workspace_id": WORKSPACE_ID})
        if path == "/api/v1/sources/capabilities":
            return self._send(200, {"items": list_capabilities()})
        if path == f"/api/v1/workspaces/{WORKSPACE_ID}/dashboard":
            return self._send(200, self.store.dashboard(WORKSPACE_ID))
        if path == f"/api/v1/workspaces/{WORKSPACE_ID}/tasks":
            return self._send(200, {"items": self.store.list_tasks(WORKSPACE_ID)})
        if path == f"/api/v1/workspaces/{WORKSPACE_ID}/opportunities":
            status = parse_qs(parsed.query).get("status", [None])[0]
            return self._send(200, {"items": self.store.list_opportunities(WORKSPACE_ID, status)})
        if path == f"/api/v1/workspaces/{WORKSPACE_ID}/entities":
            return self._send(200, {"items": self.store.list_entities(WORKSPACE_ID)})
        if path.startswith("/api/v1/tasks/") and path.count("/") == 4:
            task = self.store.get_task(path.rsplit("/", 1)[-1])
            return self._send(200, task) if task else self._error(404, "task_not_found", "任务不存在")
        if path.startswith("/api/v1/tasks/") and path.endswith("/plan"):
            task = self.store.get_task(path.split("/")[-2])
            return self._send(200, task["plan"]) if task and task.get("plan") else self._error(404, "plan_not_found", "任务计划不存在")
        if path.startswith("/api/v1/opportunities/") and path.count("/") == 4:
            opportunity = self.store.get_opportunity(path.rsplit("/", 1)[-1])
            return self._send(200, opportunity) if opportunity else self._error(404, "opportunity_not_found", "机会不存在")
        if path.startswith("/api/v1/entities/") and path.count("/") == 4:
            entity = self.store.get_entity(path.rsplit("/", 1)[-1])
            return self._send(200, entity) if entity else self._error(404, "entity_not_found", "实体不存在")
        return self._error(404, "not_found", "接口不存在")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path).rstrip("/")
        try:
            payload = self._body()
            if path == f"/api/v1/workspaces/{WORKSPACE_ID}/profiles":
                return self._create_profile(payload)
            if path == f"/api/v1/workspaces/{WORKSPACE_ID}/tasks":
                return self._create_task(payload)
            if path.startswith("/api/v1/tasks/") and path.endswith("/capture-url"):
                return self._capture_url(path.split("/")[-2], payload)
            if path.startswith("/api/v1/tasks/") and path.endswith("/start"):
                return self._start_task(path.split("/")[-2], payload)
            if path.startswith("/api/v1/tasks/") and path.endswith("/opportunities"):
                return self._add_opportunities(path.split("/")[-2], payload)
            if path.startswith("/api/v1/opportunities/") and path.endswith("/feedback"):
                return self._feedback(path.split("/")[-2], payload)
            if path.startswith("/api/v1/opportunities/") and path.endswith("/reopen"):
                return self._reopen_evidence(path.split("/")[-2])
            if path.startswith("/api/v1/entities/") and path.endswith("/merge"):
                return self._merge_entity(path.split("/")[-2], payload)
            if path.startswith("/api/v1/entities/") and path.endswith("/split"):
                return self._split_entity(path.split("/")[-2], payload)
        except CaptureError as exc:
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

    def _create_profile(self, payload: dict[str, Any]) -> None:
        objective = str(payload.get("objective", "")).strip()
        if not objective:
            raise ValueError("objective_required")
        criteria = compile_intent(objective, payload.get("criteria"))
        profile = self.store.create_profile(WORKSPACE_ID, str(payload.get("name") or "自定义画像"), objective, criteria)
        self._send(201, profile)

    def _create_task(self, payload: dict[str, Any]) -> None:
        objective = str(payload.get("objective", "")).strip()
        if not objective:
            raise ValueError("objective_required")
        requested_limit = max(1, min(int(payload.get("requested_limit", 10)), 500))
        criteria = compile_intent(objective, payload.get("criteria"))
        plan = build_search_plan(criteria, requested_limit)
        idempotency_key = self.headers.get("Idempotency-Key") or payload.get("idempotency_key")
        task = self.store.create_task(
            WORKSPACE_ID,
            payload.get("profile_id"),
            objective,
            criteria,
            requested_limit,
            int(payload.get("estimated_credits", plan["cost_estimate"]["max_credits"])),
            idempotency_key,
            plan,
        )
        self._send(201, task)

    def _start_task(self, task_id: str, payload: dict[str, Any]) -> None:
        task = self.store.start_task(task_id, str(payload.get("mode", "quick")))
        if not task:
            return self._error(404, "task_not_found", "任务不存在")
        latest_run = task.get("runs", [None])[0]
        message = "任务已进入队列。" if latest_run and latest_run["status"] == "QUEUED" else "任务计划已生成，但当前没有通过生产门禁的自动搜索连接器。"
        self._send(200, {**task, "message": message})

    def _capture_url(self, task_id: str, payload: dict[str, Any]) -> None:
        task = self.store.get_task(task_id)
        if not task:
            return self._error(404, "task_not_found", "任务不存在")
        requested_url = str(payload.get("url", "")).strip()
        if not requested_url:
            raise ValueError("url_required")
        capture = fetch_public_page(requested_url)
        item = {
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
            },
        }
        status = evidence_status(item)
        opportunity, was_duplicate = self.store.add_opportunity(task_id, item, status)
        self.store.record_usage(
            WORKSPACE_ID,
            task_id,
            "public_url_capture",
            1,
            1,
            "COMPLETED",
            self.headers.get("Idempotency-Key"),
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
            for required in ("title", "source_url", "snippet"):
                if not str(item.get(required, "")).strip():
                    raise ValueError(f"{required}_required")
            if not str(item["source_url"]).startswith(("http://", "https://")):
                raise ValueError("source_url_must_be_http")
            status = evidence_status(item)
            if item.get("status") == "SEND_READY" and status != "SEND_READY":
                raise ValueError("send_ready_requires_verified_allowed_evidence")
            opportunity, was_duplicate = self.store.add_opportunity(task_id, item, status)
            self.store.record_usage(WORKSPACE_ID, task_id, "evidence_ingest", 1, 0, "COMPLETED")
            created.append(opportunity)  # type: ignore[arg-type]
            deduplicated += int(was_duplicate)
        self._send(201, {"items": created, "created_count": len(created) - deduplicated, "deduplicated_count": deduplicated})

    def _feedback(self, opportunity_id: str, payload: dict[str, Any]) -> None:
        label = str(payload.get("label", "")).upper()
        if label not in {"VALID", "REVIEW", "OBSERVE", "INVALID", "DUPLICATE"}:
            raise ValueError("invalid_feedback_label")
        opportunity = self.store.add_feedback(opportunity_id, label, str(payload.get("note", "")), str(payload.get("actor", "operator")))
        if not opportunity:
            return self._error(404, "opportunity_not_found", "机会不存在")
        self._send(200, opportunity)

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

    def _reopen_evidence(self, opportunity_id: str) -> None:
        opportunity = self.store.get_opportunity(opportunity_id)
        if not opportunity:
            return self._error(404, "opportunity_not_found", "机会不存在")
        if opportunity.get("source_kind") != "public_url_capture":
            raise ValueError("reopen_supported_for_public_url_capture_only")
        capture = fetch_public_page(opportunity["source_url"])
        previous_hashes = [
            evidence.get("metadata", {}).get("content_hash")
            for evidence in opportunity.get("evidence", [])
            if evidence.get("metadata", {}).get("content_hash")
        ]
        matches_previous = bool(previous_hashes) and capture["content_hash"] == previous_hashes[-1]
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
            },
            capture["captured_at"],
        )
        self.store.record_usage(
            WORKSPACE_ID,
            opportunity.get("task_id"),
            "public_url_reopen",
            1,
            1,
            "COMPLETED",
            self.headers.get("Idempotency-Key"),
        )
        self._send(
            200,
            {
                "opportunity": updated,
                "reopen": {
                    "matches_previous_snapshot": matches_previous,
                    "content_hash": capture["content_hash"],
                    "captured_at": capture["captured_at"],
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
