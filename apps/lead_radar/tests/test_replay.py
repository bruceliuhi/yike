from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from apps.lead_radar.server import create_server


class ReplayApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.server = create_server("127.0.0.1", 0, str(Path(self.tempdir.name) / "replay.sqlite3"))
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

    def test_replay_contains_the_full_human_review_boundary(self) -> None:
        workspace = "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI"
        status, task = self.request("POST", f"{workspace}/tasks", {"objective": "寻找企业 AI 客服采购需求"})
        self.assertEqual(status, 201)
        task_id = task["id"]
        status, added = self.request(
            "POST",
            f"/api/v1/tasks/{task_id}/opportunities",
            {
                "title": "企业 AI 客服采购需求",
                "source_url": "https://buyer.example/request",
                "snippet": "企业正在寻找 AI 客服定制开发团队。",
                "source_kind": "manual_public_evidence",
                "source_permission": "allowed",
                "evidence_level": "VERIFIED",
                "manual_override": {
                    "status": "SEND_READY",
                    "actor": "qa",
                    "reason": "人工打开原文并确认采购意向",
                    "confirmed": True,
                },
            },
        )
        self.assertEqual(status, 201)
        opportunity_id = added["items"][0]["id"]
        status, drafts = self.request("POST", f"/api/v1/opportunities/{opportunity_id}/action-drafts", {"channels": ["EMAIL"], "actor": "qa"})
        self.assertEqual(status, 200)
        self.assertEqual(drafts["count"], 1)
        status, feedback = self.request("POST", f"/api/v1/opportunities/{opportunity_id}/feedback", {"label": "DEFERRED", "note": "等待预算确认", "actor": "qa"})
        self.assertEqual(status, 200)

        status, replay = self.request("GET", f"/api/v1/tasks/{task_id}/replay")
        self.assertEqual(status, 200)
        self.assertEqual(replay["task_id"], task_id)
        body = replay["replay"]
        self.assertEqual(body["task"]["objective"], "寻找企业 AI 客服采购需求")
        self.assertTrue(body["task"]["plan"]["strategies"])
        self.assertEqual(len(body["candidates"]), 1)
        self.assertTrue(body["candidates"][0]["evidence"])
        self.assertEqual(body["candidates"][0]["feedback_events"][0]["label"], "DEFERRED")
        self.assertEqual(body["action_drafts"][0]["status"], "CANCELLED")
        self.assertTrue(body["audit_events"])
        self.assertTrue(body["timeline"])
        self.assertTrue(replay["explainability"]["evidence_reopen_required"])
        self.assertFalse(replay["explainability"]["external_actions_sent"])

    def test_replay_is_workspace_scoped(self) -> None:
        status, body = self.request("GET", "/api/v1/tasks/task_missing/replay")
        self.assertEqual(status, 404)
        self.assertEqual(body["error"], "task_not_found")


if __name__ == "__main__":
    unittest.main()
