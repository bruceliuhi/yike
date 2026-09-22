from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from apps.lead_radar.server import create_server


WORKSPACE_PATH = "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI"


class FeedApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.server = create_server("127.0.0.1", 0, str(Path(self.tempdir.name) / "feed.sqlite3"))
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

    def test_feed_is_evidence_bound_filterable_reviewable_and_change_aware(self) -> None:
        status, task = self.request(
            "POST",
            f"{WORKSPACE_PATH}/tasks",
            {"objective": "验证采购需求 Feed"},
        )
        self.assertEqual(status, 201)
        task_id = task["id"]
        path = f"/api/v1/tasks/{task_id}/opportunities"
        items = [
            {
                "title": "企业 AI 客服采购",
                "source_url": "https://feed.example/purchase",
                "snippet": "正在寻找企业 AI 客服定制团队。",
                "feed_event_type": "PURCHASE_DEMAND",
            },
            {
                "title": "招聘 AI 工程师",
                "source_url": "https://feed.example/hiring",
                "snippet": "招聘负责企业智能体落地的工程师。",
                "feed_event_type": "HIRING",
            },
            {
                "title": "AI 平台项目招标公告",
                "source_url": "https://feed.example/tender",
                "snippet": "公开招标建设企业 AI 平台。",
                "feed_event_type": "TENDER",
            },
        ]
        status, created = self.request("POST", path, {"items": items})
        self.assertEqual(status, 201)
        self.assertEqual(created["created_count"], 3)

        status, feed = self.request("GET", f"{WORKSPACE_PATH}/feed?limit=2")
        self.assertEqual(status, 200)
        self.assertEqual(feed["pagination"]["total"], 3)
        self.assertEqual(len(feed["items"]), 2)
        self.assertTrue(all(item["source_url"].startswith("https://feed.example/") for item in feed["items"]))
        self.assertTrue(all(item["content_hash"] for item in feed["items"]))
        self.assertTrue(feed["contract"]["evidence_bound"])

        status, hiring = self.request("GET", f"{WORKSPACE_PATH}/feed?event_type=HIRING")
        self.assertEqual(status, 200)
        self.assertEqual(hiring["pagination"]["total"], 1)
        event_id = hiring["items"][0]["id"]
        status, reviewed = self.request(
            "POST",
            f"/api/v1/feed-events/{event_id}/review",
            {"status": "REVIEWED", "actor": "qa", "note": "人工核对来源"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(reviewed["event"]["status"], "REVIEWED")
        status, reviewed_feed = self.request("GET", f"{WORKSPACE_PATH}/feed?status=REVIEWED")
        self.assertEqual(status, 200)
        self.assertEqual(reviewed_feed["pagination"]["total"], 1)

        # Same opportunity URL/title with changed evidence creates a new Feed event
        # without manufacturing a second opportunity.
        status, duplicate = self.request(
            "POST",
            path,
            {
                **items[0],
                "snippet": "页面更新：正在寻找可交付的企业 AI 客服实施团队。",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(duplicate["created_count"], 0)
        status, purchase_feed = self.request("GET", f"{WORKSPACE_PATH}/feed?event_type=PURCHASE_DEMAND")
        self.assertEqual(status, 200)
        self.assertEqual(purchase_feed["pagination"]["total"], 2)

        opportunity_id = duplicate["items"][0]["id"]
        self.server.store.append_evidence(
            opportunity_id,
            "reopen_check",
            "官网正文已发生变化。",
            "https://feed.example/purchase",
            {"matches_previous_snapshot": False, "content_hash": "changed-content"},
        )
        status, website_changes = self.request("GET", f"{WORKSPACE_PATH}/feed?event_type=WEBSITE_CHANGE")
        self.assertEqual(status, 200)
        self.assertEqual(website_changes["pagination"]["total"], 1)

    def test_feed_rejects_unsupported_event_and_review_status(self) -> None:
        status, task = self.request("POST", f"{WORKSPACE_PATH}/tasks", {"objective": "Feed 安全边界"})
        self.assertEqual(status, 201)
        status, rejected = self.request(
            "POST",
            f"/api/v1/tasks/{task['id']}/opportunities",
            {
                "title": "未知事件",
                "source_url": "https://feed.example/unknown",
                "snippet": "有来源的事件摘要。",
                "feed_event_type": "AUTO_SEND",
            },
        )
        self.assertEqual(status, 400)
        self.assertEqual(rejected["error"], "invalid_request")
        status, missing = self.request("GET", f"/api/v1/feed-events/event_missing")
        self.assertEqual(status, 404)
        self.assertEqual(missing["error"], "feed_event_not_found")


if __name__ == "__main__":
    unittest.main()
