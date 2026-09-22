from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from apps.lead_radar.server import create_server


WORKSPACE_PATH = "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI"


class EvidenceProvenanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.server = create_server("127.0.0.1", 0, str(Path(self.tempdir.name) / "provenance.sqlite3"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server.store.close()
        self.tempdir.cleanup()

    def request(self, method: str, path: str, payload: dict | None = None):
        connection = HTTPConnection(self.host, self.port)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        connection.request(method, path, body=body, headers={"Content-Type": "application/json; charset=utf-8"})
        response = connection.getresponse()
        result = json.loads(response.read().decode("utf-8"))
        connection.close()
        return response.status, result

    def test_opportunity_detail_exposes_rights_reopen_and_counter_evidence(self) -> None:
        status, created = self.request(
            "POST",
            "/api/v1/business/create_search_task",
            {"objective": "证据权利详情测试"},
        )
        self.assertEqual(status, 201)
        task_id = created["task"]["id"]
        status, right = self.request(
            "POST",
            f"{WORKSPACE_PATH}/source-rights",
            {
                "source_id": "authorized_search_api",
                "provider": "Test Search",
                "source_family": "authorized_search",
                "access_method": "OFFICIAL_API",
                "status": "PENDING",
                "proof_ref": "proof-test-search",
                "allowed_operations": ["SEARCH", "REOPEN", "STORE_EXCERPT"],
                "allowed_fields": ["title", "url", "snippet", "published_at"],
                "retention_days": 30,
                "rate_limit_per_minute": 60,
                "store_original": False,
                "can_search": True,
                "can_write_back": False,
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(right["right"]["permission_status"], "PENDING")
        status, added = self.request(
            "POST",
            f"/api/v1/tasks/{task_id}/opportunities",
            {
                "title": "授权来源候选",
                "source_url": "https://authorized.example/request",
                "snippet": "企业公开表达 AI 客服采购需求。",
                "source_kind": "authorized_search_api",
                "source_permission": "authorized_search_api",
            },
        )
        self.assertEqual(status, 201)
        opportunity_id = added["items"][0]["id"]
        self.server.store.append_evidence(
            opportunity_id,
            "reopen_check",
            "原文重新打开，内容一致。",
            "https://authorized.example/request",
            {"matches_previous_snapshot": True, "content_hash": "same"},
        )
        self.server.store.append_evidence(
            opportunity_id,
            "counter_evidence",
            "页面未出现预算、时间或采购主体。",
            "https://authorized.example/request",
            {"reason": "missing_purchase_detail"},
        )
        status, opportunity = self.request("GET", f"/api/v1/opportunities/{opportunity_id}")
        self.assertEqual(status, 200)
        self.assertEqual(opportunity["data_use"]["permission_status"], "PENDING")
        self.assertEqual(opportunity["data_use"]["retention_days"], 30)
        self.assertEqual(opportunity["data_use"]["allowed_operations"], ["SEARCH", "REOPEN", "STORE_EXCERPT"])
        self.assertFalse(opportunity["data_use"]["can_write_back"])
        self.assertEqual(opportunity["evidence_audit"]["reopen_status"], "PASS")
        self.assertEqual(opportunity["evidence_audit"]["reopen_check_count"], 1)
        self.assertEqual(opportunity["evidence_audit"]["counter_evidence_count"], 1)


if __name__ == "__main__":
    unittest.main()
