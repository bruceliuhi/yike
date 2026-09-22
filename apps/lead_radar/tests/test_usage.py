from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from apps.lead_radar.capture import CaptureError
from apps.lead_radar.planner import build_search_plan
from apps.lead_radar.server import create_server
from apps.lead_radar.usage import charge_for, cost_estimate


WORKSPACE_PATH = "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI"


class UsageRuleTest(unittest.TestCase):
    def test_source_result_rule_charges_only_new_results(self) -> None:
        self.assertEqual(charge_for("search_index_import", "SUCCESS"), 1)
        self.assertEqual(charge_for("search_index_import", "DUPLICATE"), 0)
        self.assertEqual(charge_for("search_index_import", "NO_RESULT", 0), 0)
        self.assertEqual(charge_for("search_index_import", "FAILED", 0), 0)
        with self.assertRaisesRegex(ValueError, "usage_operation_invalid"):
            charge_for("unregistered_source", "SUCCESS")
        with self.assertRaisesRegex(ValueError, "usage_outcome_invalid"):
            charge_for("search_index_import", "UNKNOWN")

    def test_plan_quote_is_explicitly_soubei_and_does_not_reserve(self) -> None:
        quote = cost_estimate("xiaohongshu_public", 10)
        self.assertEqual(quote["unit"], "SOUBEI")
        self.assertEqual(quote["display_unit"], "搜贝")
        self.assertEqual(quote["maximum_credits"], 10)
        self.assertEqual(quote["settlement"], "NOT_STARTED")
        unavailable = cost_estimate("unregistered_source", 10)
        self.assertIsNone(unavailable["maximum_credits"])
        self.assertEqual(unavailable["settlement"], "UNKNOWN")
        plan = build_search_plan({"sources": ["unregistered_source"]}, 5)
        self.assertIsNone(plan["cost_estimate"]["max_credits"])
        self.assertEqual(plan["cost_estimate"]["settlement"], "UNKNOWN")


class SourceUsageApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.server = create_server("127.0.0.1", 0, str(Path(self.tempdir.name) / "usage.sqlite3"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server.store.close()
        self.tempdir.cleanup()

    def request(self, method: str, path: str, payload: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
        connection = HTTPConnection(self.host, self.port)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        connection.request(
            method,
            path,
            body=body,
            headers={"Content-Type": "application/json; charset=utf-8", **(headers or {})},
        )
        response = connection.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        connection.close()
        return response.status, data

    def _task(self) -> dict:
        status, task = self.request("POST", WORKSPACE_PATH + "/tasks", {"objective": "验证来源结果计费"})
        self.assertEqual(status, 201)
        return task

    def _proof(self, proof_ref: str = "usage-proof") -> None:
        status, _ = self.request(
            "POST",
            WORKSPACE_PATH + "/source-proofs",
            {
                "proof_ref": proof_ref,
                "provider": "licensed-search-index",
                "source_family": "authorized_search_index",
                "endpoint": "https://provider.example/search",
                "artifact_sha256": "a" * 64,
                "checked_at": "2026-09-22T00:00:00Z",
                "checks": {
                    "terms_and_robots": True,
                    "rate_limit": True,
                    "published_at": True,
                    "url_reopen": True,
                    "save_boundary": True,
                    "retry_idempotency": True,
                },
            },
        )
        self.assertEqual(status, 201)

    def _audit_usage(self) -> list[dict]:
        status, audit = self.request("GET", WORKSPACE_PATH + "/audit?limit=100")
        self.assertEqual(status, 200)
        return audit["usage"]

    def test_index_import_records_success_and_duplicate_without_double_charge(self) -> None:
        task = self._task()
        self._proof()
        payload = {
            "provider": "licensed-search-index",
            "query": "AI 客服采购",
            "proof_ref": "usage-proof",
            "retrieved_at": "2026-09-22T12:00:00Z",
            "items": [{
                "title": "企业寻找 AI 客服团队",
                "source_url": "https://buyer.example/request/usage-1",
                "snippet": "正在评估 AI 客服解决方案。",
            }],
        }
        path = f"/api/v1/tasks/{task['id']}/index-results"
        self.assertEqual(self.request("POST", path, payload)[0], 201)
        repeated_payload = {**payload, "retrieved_at": "2026-09-22T13:00:00Z"}
        self.assertEqual(self.request("POST", path, repeated_payload)[0], 201)
        usage = [item for item in self._audit_usage() if item["operation"] == "search_index_import"]
        self.assertEqual([item["outcome"] for item in usage], ["DUPLICATE", "SUCCESS"])
        self.assertEqual(sum(item["credits"] for item in usage), 1)
        self.assertTrue(all(item["unit"] == "SOUBEI" for item in usage))
        self.assertEqual(self.request("GET", WORKSPACE_PATH + "/dashboard")[1]["credits_used"], 1)

    def test_unregistered_source_stays_unknown_without_fake_task_quote(self) -> None:
        status, task = self.request(
            "POST",
            WORKSPACE_PATH + "/tasks",
            {"objective": "未知来源不应虚构费用", "criteria": {"sources": ["unregistered_source"]}},
        )
        self.assertEqual(status, 201)
        self.assertEqual(task["estimated_credits"], 0)
        self.assertEqual(task["plan"]["cost_estimate"]["settlement"], "UNKNOWN")

    def test_batch_capture_records_success_duplicate_and_failure(self) -> None:
        task = self._task()
        capture = {
            "title": "采购需求",
            "snippet": "正在寻找 AI 客服团队。",
            "content_hash": "b" * 64,
            "byte_length": 512,
            "requested_url": "https://buyer.example/request/usage-2",
            "final_url": "https://buyer.example/request/usage-2",
            "content_type": "text/html",
            "charset": "utf-8",
            "captured_at": "2026-09-22T00:00:00+00:00",
        }
        with patch(
            "apps.lead_radar.server.fetch_public_page",
            side_effect=[capture, capture, CaptureError("timeout", "来源超时")],
        ):
            status, result = self.request(
                "POST",
                f"/api/v1/tasks/{task['id']}/capture-urls",
                {"urls": [capture["requested_url"], capture["requested_url"], "https://buyer.example/request/usage-3"]},
            )
        self.assertEqual(status, 200)
        self.assertEqual(result["created_count"], 1)
        self.assertEqual(result["failed_count"], 1)
        usage = [item for item in self._audit_usage() if item["operation"] == "public_url_batch_capture"]
        self.assertEqual({item["outcome"] for item in usage}, {"SUCCESS", "DUPLICATE", "FAILED"})
        self.assertEqual(sum(item["credits"] for item in usage), 1)
        self.assertEqual(self.request("GET", WORKSPACE_PATH + "/dashboard")[1]["credits_used"], 1)
