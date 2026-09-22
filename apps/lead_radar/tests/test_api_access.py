from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from apps.lead_radar.server import create_server


WORKSPACE_PATH = "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI"


class ApiAccessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.server = create_server("127.0.0.1", 0, str(Path(self.tempdir.name) / "api-access.sqlite3"), require_api_key=True)
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
        connection.request(method, path, body=body, headers={"Content-Type": "application/json; charset=utf-8", **(headers or {})})
        response = connection.getresponse()
        result = json.loads(response.read().decode("utf-8"))
        request_id = response.getheader("X-Request-ID")
        connection.close()
        return response.status, result, request_id

    def create_key(self) -> tuple[str, str]:
        status, body, _ = self.request("POST", f"{WORKSPACE_PATH}/api-keys", {"label": "qa integration", "created_by": "qa"})
        self.assertEqual(status, 201)
        secret = body["api_key"]["secret"]
        key_id = body["api_key"]["id"]
        self.assertTrue(secret.startswith("lr_live_"))
        return secret, key_id

    def test_key_is_one_time_secret_and_business_actions_are_metered(self) -> None:
        secret, key_id = self.create_key()
        status, listed, _ = self.request("GET", f"{WORKSPACE_PATH}/api-keys")
        self.assertEqual(status, 200)
        self.assertEqual(listed["items"][0]["id"], key_id)
        self.assertNotIn("secret", listed["items"][0])
        status, denied, _ = self.request("POST", "/api/v1/business/create_search_task", {"objective": "企业 AI 客服"})
        self.assertEqual(status, 401)
        self.assertEqual(denied["error"], "api_key_required")

        headers = {"X-API-Key": secret, "Idempotency-Key": "api-key-task-1", "X-Request-ID": "api-request-1"}
        status, created, request_id = self.request("POST", "/api/v1/business/create_search_task", {"objective": "企业 AI 客服"}, headers)
        self.assertEqual(status, 201)
        self.assertEqual(request_id, "api-request-1")
        task_id = created["task"]["id"]
        status, replay, _ = self.request("POST", "/api/v1/business/create_search_task", {"objective": "其他目标"}, {**headers, "X-Request-ID": "api-request-2"})
        self.assertEqual(status, 201)
        self.assertEqual(replay["task"]["id"], task_id)

        status, usage, _ = self.request("GET", f"{WORKSPACE_PATH}/usage")
        self.assertEqual(status, 200)
        self.assertEqual(usage["usage"]["used_credits"], 1)
        self.assertEqual(usage["usage"]["api_requests"], 3)
        self.assertTrue(any(row["operation"] == "api_action:create_search_task" and row["credits"] == 1 for row in usage["usage"]["by_operation"]))

        status, revoked, _ = self.request("POST", f"/api/v1/api-keys/{key_id}/revoke", {"actor": "qa"})
        self.assertEqual(status, 200)
        status, denied, _ = self.request("GET", f"/api/v1/business/get_search_status/{task_id}", headers={"X-API-Key": secret})
        self.assertEqual(status, 401)
        self.assertEqual(denied["error"], "api_key_invalid")

    def test_hard_quota_blocks_before_a_billable_action(self) -> None:
        secret, _ = self.create_key()
        status, quota, _ = self.request("POST", f"{WORKSPACE_PATH}/quota", {"included_credits": 0, "hard_limit": True, "actor": "qa"})
        self.assertEqual(status, 200)
        self.assertEqual(quota["usage"]["remaining_credits"], 0)
        status, blocked, _ = self.request("POST", "/api/v1/business/create_search_task", {"objective": "额度测试"}, {"X-API-Key": secret})
        self.assertEqual(status, 429)
        self.assertEqual(blocked["error"], "quota_exceeded")


if __name__ == "__main__":
    unittest.main()
