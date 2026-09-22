from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from apps.lead_radar.mcp_server import TOOL_DEFINITIONS
from apps.lead_radar.server import create_server


WORKSPACE_PATH = "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI"


class BusinessApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.server = create_server("127.0.0.1", 0, str(Path(self.tempdir.name) / "business.sqlite3"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server.store.close()
        self.tempdir.cleanup()

    def request(self, method: str, path: str, payload: dict | None = None, headers: dict | None = None):
        connection = HTTPConnection(self.host, self.port)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        connection.request(
            method,
            path,
            body=body,
            headers={"Content-Type": "application/json; charset=utf-8", **(headers or {})},
        )
        response = connection.getresponse()
        result = json.loads(response.read().decode("utf-8"))
        request_id = response.getheader("X-Request-ID")
        connection.close()
        return response.status, result, request_id

    def test_named_business_api_is_idempotent_and_paginates_only_one_task(self) -> None:
        status, rejected, _ = self.request(
            "POST",
            "/api/v1/business/create_search_task",
            {"objective": "寻找企业 AI 客服项目", "token": "must-not-be-accepted"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(rejected["error"], "credential_fields_not_allowed")

        status, created, request_id = self.request(
            "POST",
            "/api/v1/business/create_search_task",
            {"objective": "寻找企业 AI 客服项目", "requested_limit": 10},
            {"Idempotency-Key": "business-task-1", "X-Request-ID": "qa-request-1"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(created["api_version"], "2026-09-23")
        self.assertEqual(created["request_id"], "qa-request-1")
        self.assertEqual(request_id, "qa-request-1")
        task_id = created["task"]["id"]

        status, duplicate, _ = self.request(
            "POST",
            "/api/v1/business/create_search_task",
            {"objective": "第二次请求不应产生新任务"},
            {"Idempotency-Key": "business-task-1"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(duplicate["task"]["id"], task_id)

        status, result, _ = self.request(
            "POST",
            f"/api/v1/tasks/{task_id}/opportunities",
            {
                "items": [
                    {
                        "title": "企业 AI 客服采购需求",
                        "source_url": "https://buyer.example/one",
                        "snippet": "公开页面提到正在评估企业 AI 客服定制开发。",
                        "entity_name": "示例企业",
                    },
                    {
                        "title": "企业知识库采购需求",
                        "source_url": "https://buyer.example/two",
                        "snippet": "公开页面提到需要寻找企业知识库落地团队。",
                        "entity_name": "示例企业",
                    },
                ]
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(result["created_count"], 2)

        status, page, _ = self.request(
            "GET",
            f"/api/v1/business/fetch_search_results/{task_id}?limit=1",
        )
        self.assertEqual(status, 200)
        self.assertEqual(page["pagination"], {"limit": 1, "offset": 0, "total": 2, "has_more": True, "next_offset": 1})
        self.assertEqual(len(page["items"]), 1)
        self.assertTrue(page["result_contract"]["evidence_reopen_required"])

        status, second_page, _ = self.request(
            "GET",
            f"/api/v1/business/fetch_search_results/{task_id}?limit=1&offset=1",
        )
        self.assertEqual(status, 200)
        self.assertEqual(second_page["pagination"]["has_more"], False)
        self.assertEqual(len(second_page["items"]), 1)

        status, task_status, _ = self.request("GET", f"/api/v1/business/get_search_status/{task_id}")
        self.assertEqual(status, 200)
        self.assertEqual(task_status["task_id"], task_id)
        self.assertEqual(task_status["status"], "PLANNED")
        self.assertFalse(task_status["external_actions"]["messages_sent"])

        entity_id = page["items"][0]["entities"][0]["id"]
        status, entity, _ = self.request("GET", f"/api/v1/business/enrich_entity/{entity_id}")
        self.assertEqual(status, 200)
        self.assertEqual(entity["enrichment"]["status"], "LOCAL_ONLY")
        self.assertFalse(entity["enrichment"]["external_lookup_performed"])
        self.assertEqual(len(entity["entity"]["opportunities"]), 2)

    def test_missing_business_resources_are_scoped_and_safe(self) -> None:
        status, body, request_id = self.request("GET", "/api/v1/business/get_search_status/task_missing")
        self.assertEqual(status, 404)
        self.assertEqual(body["error"], "task_not_found")
        self.assertTrue(request_id.startswith("req_"))
        status, body, _ = self.request("GET", "/api/v1/business/fetch_search_results/task_missing")
        self.assertEqual(status, 404)
        self.assertEqual(body["error"], "task_not_found")

    def test_calibration_evaluation_exposes_quality_metrics_and_blocks_fixtures(self) -> None:
        status, created, _ = self.request(
            "POST",
            "/api/v1/business/create_search_task",
            {"objective": "评测报告任务"},
        )
        self.assertEqual(status, 201)
        task_id = created["task"]["id"]
        status, added, _ = self.request(
            "POST",
            f"/api/v1/tasks/{task_id}/opportunities",
            {
                "title": "评测候选",
                "source_url": "https://evaluation.example/request",
                "snippet": "公开需求样本",
                "source_kind": "manual_public_evidence",
            },
        )
        self.assertEqual(status, 201)
        opportunity_id = added["items"][0]["id"]
        status, batch, _ = self.request(
            "POST",
            f"{WORKSPACE_PATH}/calibration-batches",
            {"name": "评测批次", "target_count": 1, "opportunity_ids": [opportunity_id]},
        )
        self.assertEqual(status, 201)
        status, report, _ = self.request(
            "GET",
            f"/api/v1/calibration-batches/{batch['id']}/evaluation",
        )
        self.assertEqual(status, 200)
        evaluation = report["evaluation"]
        self.assertTrue(evaluation["not_a_public_benchmark"])
        self.assertEqual(evaluation["metrics"]["evidence_completeness"]["rate"], 1.0)
        self.assertEqual(evaluation["metrics"]["cost"]["unit"], "SOUBEI")
        self.assertIn("sample_count_below_30", evaluation["quality_gate"]["blocking_reasons"])
        self.assertIn("no_approved_authorized_source_right", evaluation["quality_gate"]["blocking_reasons"])
        self.assertIn("rmb_cost", evaluation["unavailable_metrics"])


class McpContractTest(unittest.TestCase):
    def test_mcp_tools_have_no_credential_or_outreach_inputs(self) -> None:
        forbidden = {"cookie", "cookies", "password", "token", "api_key", "authorization", "send", "message"}
        for tool in TOOL_DEFINITIONS:
            properties = set(tool["inputSchema"]["properties"])
            self.assertFalse(properties & forbidden, tool["name"])
            self.assertNotIn("send", tool["name"])
            self.assertNotIn("message", tool["name"])
            self.assertTrue(tool["inputSchema"]["additionalProperties"] is False)


if __name__ == "__main__":
    unittest.main()
