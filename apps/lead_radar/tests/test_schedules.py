from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from apps.lead_radar.server import create_server


WORKSPACE_PATH = "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI"


class ScheduledTaskApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.server = create_server("127.0.0.1", 0, str(Path(self.tempdir.name) / "schedule.sqlite3"))
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

    def test_schedule_persists_policy_and_records_blocked_due_run(self) -> None:
        status, created = self.request(
            "POST",
            f"{WORKSPACE_PATH}/schedules",
            {
                "objective": "持续寻找企业 AI 客服定制需求",
                "requested_limit": 10,
                "interval_minutes": 60,
                "max_credits_per_run": 100,
                "max_total_credits": 500,
                "min_new_results": 2,
                "failure_policy": "CONTINUE",
                "approval_policy": "DRAFT_ONLY",
                "start_at": "2026-09-22T00:00:00Z",
                "created_by": "qa",
            },
        )
        self.assertEqual(status, 201)
        schedule = created["schedule"]
        self.assertEqual(schedule["status"], "ACTIVE")
        self.assertEqual(schedule["failure_policy"], "CONTINUE")
        self.assertEqual(schedule["approval_policy"], "DRAFT_ONLY")
        self.assertEqual(created["execution"]["external_search_performed"], False)
        schedule_id = schedule["id"]

        status, triggered = self.request("POST", f"/api/v1/schedules/{schedule_id}/trigger", {"actor": "qa"})
        self.assertEqual(status, 200)
        self.assertEqual(triggered["run"]["status"], "BLOCKED_SOURCE")
        self.assertEqual(triggered["run"]["error_code"], "NO_SEARCH_CONNECTOR_READY")
        self.assertEqual(triggered["task"]["status"], "AWAITING_SOURCE")
        self.assertEqual(triggered["schedule"]["run_count"], 1)
        self.assertFalse(triggered["schedule"]["latest_run"]["status"] == "COMPLETED")

        status, repeated = self.request("POST", f"/api/v1/schedules/{schedule_id}/trigger", {"actor": "qa"})
        self.assertEqual(status, 200)
        self.assertEqual(repeated["status"], "SKIPPED")
        self.assertEqual(repeated["reason"], "not_due")

        status, listed = self.request("GET", f"{WORKSPACE_PATH}/schedules")
        self.assertEqual(status, 200)
        self.assertEqual(len(listed["items"]), 1)
        self.assertEqual(listed["items"][0]["run_count"], 1)

    def test_budget_gate_and_pause_resume_are_explicit(self) -> None:
        status, created = self.request(
            "POST",
            f"{WORKSPACE_PATH}/schedules",
            {
                "objective": "验证调度预算门禁",
                "interval_minutes": 5,
                "max_credits_per_run": 1,
                "failure_policy": "PAUSE",
                "start_at": "2026-09-22T00:00:00Z",
            },
        )
        self.assertEqual(status, 201)
        schedule_id = created["schedule"]["id"]
        status, triggered = self.request("POST", f"/api/v1/schedules/{schedule_id}/trigger", {})
        self.assertEqual(status, 200)
        self.assertEqual(triggered["run"]["status"], "BLOCKED_BUDGET")
        self.assertEqual(triggered["run"]["error_code"], "PER_RUN_BUDGET_EXCEEDED")
        self.assertEqual(triggered["schedule"]["status"], "PAUSED")

        status, paused = self.request("POST", f"/api/v1/schedules/{schedule_id}/trigger", {})
        self.assertEqual(status, 200)
        self.assertEqual(paused["status"], "SKIPPED")
        self.assertEqual(paused["reason"], "schedule_not_active")

        status, resumed = self.request("POST", f"/api/v1/schedules/{schedule_id}/resume", {"actor": "qa"})
        self.assertEqual(status, 200)
        self.assertEqual(resumed["schedule"]["status"], "ACTIVE")

    def test_invalid_schedule_never_accepts_credentials_or_unsafe_policy(self) -> None:
        status, rejected = self.request(
            "POST",
            f"{WORKSPACE_PATH}/schedules",
            {"objective": "不应接收密钥", "criteria": {"token": "secret"}},
        )
        self.assertEqual(status, 400)
        self.assertEqual(rejected["error"], "credential_fields_not_allowed")
        status, rejected = self.request(
            "POST",
            f"{WORKSPACE_PATH}/schedules",
            {"objective": "不应接受自动发送", "approval_policy": "AUTO_SEND"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(rejected["error"], "approval_policy_invalid")


if __name__ == "__main__":
    unittest.main()
