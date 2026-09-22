from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from apps.lead_radar.presentation import localize_opportunity
from apps.lead_radar.server import create_server


class PresentationTest(unittest.TestCase):
    def test_localized_layer_preserves_original_evidence(self) -> None:
        item = {
            "status": "REVIEW",
            "source_kind": "public_feed_capture",
            "snippet": "正在寻找 AI 客服服务商。",
            "decision": {
                "code": "CAPTURED_FEED_NEEDS_REVIEW",
                "reason": "公开 Feed 条目待复核。",
                "qualification": {"band": "HIGH", "review_priority": "P1"},
            },
        }
        english = localize_opportunity(item, "en-US")
        self.assertEqual(english["snippet"], item["snippet"])
        self.assertEqual(english["presentation"]["status_label"], "Review")
        self.assertEqual(english["presentation"]["source_kind_label"], "Public RSS/Atom feed")
        self.assertEqual(english["presentation"]["qualification_band_label"], "High priority")
        self.assertTrue(english["presentation"]["source_evidence_is_original"])
        self.assertNotIn("presentation", item)
        with self.assertRaises(ValueError):
            localize_opportunity(item, "fr-FR")

    def test_http_opportunity_list_and_detail_accept_language(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            server = create_server("127.0.0.1", 0, str(Path(tempdir) / "presentation.sqlite3"))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address

                def request(method: str, path: str, payload: dict | None = None):
                    connection = HTTPConnection(host, port)
                    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
                    connection.request(method, path, body=body, headers={"Content-Type": "application/json"})
                    response = connection.getresponse()
                    value = json.loads(response.read().decode("utf-8"))
                    connection.close()
                    return response.status, value

                status, task = request("POST", "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks", {"objective": "Find enterprise AI customer service demand"})
                self.assertEqual(status, 201)
                status, created = request(
                    "POST",
                    f"/api/v1/tasks/{task['id']}/opportunities",
                    {"title": "AI customer service request", "source_url": "https://example.com/request", "snippet": "Looking for an implementation vendor."},
                )
                self.assertEqual(status, 201)
                opportunity_id = created["items"][0]["id"]
                status, listed = request("GET", "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/opportunities?language=en-US")
                self.assertEqual(status, 200)
                self.assertEqual(listed["language"], "en-US")
                self.assertEqual(listed["items"][0]["presentation"]["status_label"], "Review")
                status, detail = request("GET", f"/api/v1/opportunities/{opportunity_id}?language=en-US")
                self.assertEqual(status, 200)
                self.assertEqual(detail["presentation"]["language"], "en-US")
                status, rejected = request("GET", "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/opportunities?language=fr-FR")
                self.assertEqual(status, 400)
                self.assertEqual(rejected["message"], "language_not_supported")
            finally:
                server.shutdown()
                server.server_close()
                server.store.close()


if __name__ == "__main__":
    unittest.main()
