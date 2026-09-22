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

    def test_opportunity_csv_export_preserves_evidence_fields_and_workspace_scope(self) -> None:
        status, created, _ = self.request(
            "POST",
            "/api/v1/business/create_search_task",
            {"objective": "CSV 导出任务"},
        )
        self.assertEqual(status, 201)
        task_id = created["task"]["id"]
        status, added, _ = self.request(
            "POST",
            f"/api/v1/tasks/{task_id}/opportunities",
            {
                "title": "导出候选",
                "author": "公开作者",
                "source_url": "https://export.example/request",
                "snippet": "需要 AI 客服定制方案",
                "intent_type": "AI 客服",
                "source_kind": "manual_public_evidence",
                "source_permission": "public_url_user_supplied",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(added["items"][0]["status"], "REVIEW")
        connection = HTTPConnection(self.host, self.port)
        connection.request(
            "GET",
            f"{WORKSPACE_PATH}/opportunities/export.csv?status=REVIEW",
            headers={"Accept": "text/csv"},
        )
        response = connection.getresponse()
        csv_body = response.read().decode("utf-8-sig")
        export_count = response.getheader("X-Export-Count")
        content_disposition = response.getheader("Content-Disposition")
        content_type = response.getheader("Content-Type")
        connection.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(export_count, "1")
        self.assertIn("attachment", content_disposition or "")
        self.assertIn("text/csv", content_type or "")
        self.assertIn("source_url", csv_body)
        self.assertIn("https://export.example/request", csv_body)
        self.assertIn("需要 AI 客服定制方案", csv_body)
        self.assertNotIn("phone", csv_body.lower())

    def test_task_templates_are_localized_and_compile_into_audited_tasks(self) -> None:
        status, zh, _ = self.request("GET", "/api/v1/task-templates?language=zh-CN")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(zh["items"]), 7)
        self.assertTrue(any(item["id"] == "ai_customer_service" for item in zh["items"]))
        status, en, _ = self.request("GET", "/api/v1/task-templates?language=en-US")
        self.assertEqual(status, 200)
        self.assertEqual(en["language"], "en-US")
        self.assertTrue(any(item["title"] == "AI customer service demand" for item in en["items"]))
        status, created, _ = self.request(
            "POST",
            "/api/v1/business/create_search_task",
            {"template_id": "ai_customer_service"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(created["task"]["criteria"]["template_id"], "ai_customer_service")
        self.assertIn("AI 客服", created["task"]["objective"])
        status, rejected, _ = self.request(
            "POST",
            "/api/v1/business/create_search_task",
            {"template_id": "does_not_exist"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(rejected["error"], "task_template_not_found")

    def test_research_brief_is_evidence_bound_and_never_claims_external_enrichment(self) -> None:
        status, created, _ = self.request(
            "POST",
            "/api/v1/business/create_search_task",
            {"objective": "研究简报任务"},
        )
        self.assertEqual(status, 201)
        task_id = created["task"]["id"]
        status, added, _ = self.request(
            "POST",
            f"/api/v1/tasks/{task_id}/opportunities",
            {
                "title": "研究简报候选",
                "source_url": "https://brief.example/request",
                "snippet": "企业公开表达需要 AI 客服定制开发。",
                "intent_type": "AI 客服",
                "source_kind": "manual_public_evidence",
            },
        )
        self.assertEqual(status, 201)
        status, brief, _ = self.request(
            "GET",
            f"/api/v1/business/research_brief/{task_id}",
        )
        self.assertEqual(status, 200)
        self.assertEqual(brief["brief"]["candidate_count"], 1)
        self.assertEqual(brief["brief"]["status_counts"]["REVIEW"], 1)
        self.assertTrue(brief["provenance"]["evidence_bound"])
        self.assertFalse(brief["provenance"]["external_lookup_performed"])
        self.assertFalse(brief["provenance"]["external_actions_sent"])
        self.assertIn("人工打开原文", brief["brief"]["next_actions"][0])


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
