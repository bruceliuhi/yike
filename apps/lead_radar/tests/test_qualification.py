from __future__ import annotations

from datetime import datetime, timezone
import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest

from apps.lead_radar.qualification import VERSION, score_opportunity
from apps.lead_radar.server import create_server


class QualificationScoreTest(unittest.TestCase):
    NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)

    def test_positive_candidate_is_ranked_from_visible_signals(self) -> None:
        result = score_opportunity(
            {
                "title": "企业 AI 客服采购需求",
                "intent_type": "定制开发",
                "snippet": "正在寻找服务商，计划近期落地 AI 客服并评估预算。",
                "source_url": "https://buyer.example/request",
                "published_at": "2026-09-20T08:00:00Z",
                "evidence_level": "CAPTURED",
            },
            {"time_window_days": 30},
            now=self.NOW,
        )
        self.assertEqual(result["version"], VERSION)
        self.assertGreaterEqual(result["score"], 70)
        self.assertEqual(result["band"], "HIGH")
        self.assertFalse(result["permission_granted"])
        self.assertIn("ai客服", result["components"]["solution"]["matched_terms"])
        self.assertIn("采购", result["components"]["purchase"]["matched_terms"])

    def test_excluded_content_is_penalized_and_stays_low(self) -> None:
        result = score_opportunity(
            {
                "title": "AI 客服教程与招聘信息",
                "snippet": "课程分享和招聘广告，不是采购需求。",
                "source_url": "https://example.com/tutorial",
                "published_at": "2026-01-01T08:00:00Z",
            },
            {"time_window_days": 30},
            now=self.NOW,
        )
        self.assertLess(result["score"], 45)
        self.assertGreaterEqual(result["components"]["exclusion_penalty"]["points"], 30)
        self.assertEqual(result["band"], "LOW")


class QualificationPersistenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.server = create_server("127.0.0.1", 0, str(Path(self.tempdir.name) / "qualification.sqlite3"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server.store.close()
        self.tempdir.cleanup()

    def request(self, method: str, path: str, payload: dict) -> tuple[int, dict]:
        connection = HTTPConnection(self.host, self.port)
        connection.request(
            method,
            path,
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        result = json.loads(response.read().decode("utf-8"))
        connection.close()
        return response.status, result

    def test_ingested_opportunity_persists_explainable_score(self) -> None:
        status, task = self.request("POST", "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks", {"objective": "寻找企业 AI 客服定制开发采购需求"})
        self.assertEqual(status, 201)
        status, result = self.request(
            "POST",
            f"/api/v1/tasks/{task['id']}/opportunities",
            {
                "title": "企业 AI 客服采购",
                "source_url": "https://buyer.example/ai-support",
                "snippet": "企业正在寻找服务商，计划近期定制开发并落地 AI 客服。",
                "published_at": "2026-09-22T08:00:00Z",
                "evidence_level": "CAPTURED",
            },
        )
        self.assertEqual(status, 201)
        opportunity = result["items"][0]
        self.assertGreater(opportunity["score"], 0)
        self.assertEqual(opportunity["decision"]["qualification"]["version"], VERSION)
        self.assertFalse(opportunity["decision"]["qualification"]["permission_granted"])
        self.assertEqual(opportunity["background"]["status"], "LOCAL_EVIDENCE_ONLY")
        self.assertFalse(opportunity["background"]["external_lookup_performed"])
        self.assertEqual(opportunity["background"]["linked_opportunity_count"], 1)


if __name__ == "__main__":
    unittest.main()
