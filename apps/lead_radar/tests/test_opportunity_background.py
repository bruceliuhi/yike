from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from apps.lead_radar.server import create_server


class OpportunityBackgroundTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.server = create_server("127.0.0.1", 0, str(Path(self.tempdir.name) / "background.sqlite3"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server.store.close()
        self.tempdir.cleanup()

    def request(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        connection = HTTPConnection(self.host, self.port)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        connection.request(method, path, body=body, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        result = json.loads(response.read().decode("utf-8"))
        connection.close()
        return response.status, result

    def test_detail_exposes_local_evidence_background_without_contact_data(self) -> None:
        _, task = self.request("POST", "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks", {"objective": "寻找企业 AI 需求"})
        path = f"/api/v1/tasks/{task['id']}/opportunities"
        base = {
            "entity_name": "星河科技",
            "title": "企业 AI 客服采购需求",
            "snippet": "正在寻找服务商并评估预算。",
            "source_permission": "unknown",
            "evidence_level": "CAPTURED",
        }
        _, first = self.request("POST", path, {**base, "source_url": "https://xinghe.example/one"})
        _, second = self.request("POST", path, {**base, "title": "知识库项目变化", "source_url": "https://xinghe.example/two"})
        self.assertNotEqual(first["items"][0]["id"], second["items"][0]["id"])
        status, detail = self.request("GET", f"/api/v1/opportunities/{first['items'][0]['id']}")
        self.assertEqual(status, 200)
        background = detail["background"]
        self.assertEqual(background["status"], "LOCAL_EVIDENCE_ONLY")
        self.assertEqual(background["entity_name"], "星河科技")
        self.assertEqual(background["linked_opportunity_count"], 2)
        self.assertEqual(background["known_source_hosts"], ["xinghe.example"])
        self.assertFalse(background["external_lookup_performed"])
        self.assertFalse(background["contact_data_returned"])
        self.assertNotIn("phone", background)
        self.assertNotIn("email", background)

    def test_unresolved_detail_explains_next_step_without_inventing_background(self) -> None:
        _, task = self.request("POST", "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks", {"objective": "寻找公开 AI 需求"})
        status, created = self.request(
            "POST",
            f"/api/v1/tasks/{task['id']}/opportunities",
            {"title": "某账号需求", "source_url": "https://www.xiaohongshu.com/explore/abc", "snippet": "需要 AI 客服方案。"},
        )
        self.assertEqual(status, 201)
        status, detail = self.request("GET", f"/api/v1/opportunities/{created['items'][0]['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(detail["background"]["status"], "ENTITY_UNRESOLVED")
        self.assertEqual(detail["background"]["known_signals"], [])


if __name__ == "__main__":
    unittest.main()
