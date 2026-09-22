from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from apps.lead_radar.server import create_server


WORKSPACE_PATH = "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI"


class PublicFeedCaptureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.server = create_server("127.0.0.1", 0, str(Path(self.tempdir.name) / "feed-capture.sqlite3"))
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

    def test_user_submitted_feed_is_captured_as_review_evidence_and_deduplicated(self) -> None:
        status, created = self.request("POST", f"{WORKSPACE_PATH}/tasks", {"objective": "公开 Feed 采集"})
        self.assertEqual(status, 201)
        task_id = created["id"]
        feed = {
            "requested_url": "https://feeds.example/public.xml",
            "final_url": "https://feeds.example/public.xml",
            "feed_title": "公开采购 Feed",
            "feed_hash": "feed-hash",
            "byte_length": 321,
            "content_type": "application/rss+xml",
            "charset": "utf-8",
            "captured_at": "2026-09-23T10:00:00+08:00",
            "entries": [
                {
                    "entry_id": "entry-1",
                    "title": "寻找企业 AI 客服团队",
                    "source_url": "https://buyer.example/request-1",
                    "snippet": "希望近期启动企业 AI 客服项目。",
                    "published_at": "2026-09-22T09:00:00+08:00",
                    "content_hash": "entry-hash",
                }
            ],
        }
        with patch("apps.lead_radar.server.fetch_public_feed", return_value=feed):
            status, first = self.request(
                "POST",
                f"/api/v1/tasks/{task_id}/capture-feed",
                {"url": feed["requested_url"], "limit": 20, "intent_type": "定制开发"},
            )
            self.assertEqual(status, 201)
            self.assertEqual(first["created_count"], 1)
            self.assertEqual(first["items"][0]["item"]["source_kind"], "public_feed_capture")
            self.assertEqual(first["items"][0]["item"]["source_permission"], "public_feed_user_supplied")
            self.assertEqual(first["items"][0]["item"]["status"], "REVIEW")

            status, second = self.request(
                "POST",
                f"/api/v1/tasks/{task_id}/capture-feed",
                {"url": feed["requested_url"], "limit": 20},
            )
            self.assertEqual(status, 201)
            self.assertEqual(second["created_count"], 0)
            self.assertEqual(second["deduplicated_count"], 1)

        status, usage = self.request("GET", f"{WORKSPACE_PATH}/usage")
        self.assertEqual(status, 200)
        rows = [row for row in usage["usage"]["by_operation"] if row["operation"] == "public_feed_capture"]
        self.assertEqual(rows[0]["credits"], 1)


if __name__ == "__main__":
    unittest.main()
