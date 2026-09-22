from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apps.lead_radar import worker
from apps.lead_radar.domain import compile_intent
from apps.lead_radar.storage import Store


WORKSPACE_ID = "ws_意客AI"


class WorkerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.tempdir.name) / "worker.sqlite3"))

    def tearDown(self) -> None:
        self.store.close()
        self.tempdir.cleanup()

    def schedule(self, criteria: dict | None = None):
        return self.store.create_scheduled_task(
            WORKSPACE_ID,
            "持续寻找企业 AI 客服采购需求",
            criteria or compile_intent("企业 AI 客服采购"),
            5,
            60,
            100,
            500,
            0,
            "CONTINUE",
            "MANUAL_REVIEW",
            "2026-09-22T00:00:00+00:00",
            "qa",
        )

    def test_due_blocked_schedule_is_claimed_once_and_explains_source_gate(self) -> None:
        schedule = self.schedule()
        result = worker.run_due_once(self.store, due_at="2026-09-23T00:00:00+00:00", execute=True)
        self.assertEqual(result["due_count"], 1)
        self.assertEqual(result["processed_count"], 1)
        execution = result["items"][0]["trigger"]
        self.assertEqual(execution["run"]["status"], "BLOCKED_SOURCE")
        self.assertEqual(execution["run"]["error_code"], "NO_SEARCH_CONNECTOR_READY")
        self.assertIsNotNone(execution["task"])

        repeated = worker.run_due_once(self.store, due_at="2026-09-23T00:00:00+00:00", execute=True)
        self.assertEqual(repeated["due_count"], 0)
        self.assertEqual(self.store.get_scheduled_task(schedule["id"], WORKSPACE_ID)["run_count"], 1)

    def test_ready_schedule_executes_and_settles_source_results(self) -> None:
        ready_plan = {
            "planner_version": "test-worker",
            "requested_limit": 2,
            "runnable_sources": ["authorized_search_api"],
            "blocked_sources": [],
            "cost_estimate": {"max_credits": 2},
            "strategies": [{"id": "quick", "queries": ["企业 AI 客服采购"]}],
            "hard_filters": {},
            "output_contract": ["title", "source_url", "snippet"],
        }

        class FakeConnector:
            def preflight(self):
                return {"status": "READY", "proof": {"reference": "proof-test"}}

            def search(self, plan, mode, *, request_id=None, idempotency_key=None):
                return [{
                    "title": "企业 AI 客服采购需求",
                    "source_url": "https://buyer.example/ai-service",
                    "snippet": "公开页面表示正在寻找企业 AI 客服定制开发团队。",
                    "source_kind": "authorized_search_api",
                    "source_permission": "authorized_api",
                    "evidence_level": "PROVIDER_ATTESTED",
                    "evidence_metadata": {"provider": "test"},
                }]

        original_plan = worker.build_search_plan
        original_connector = worker.AuthorizedSearchConnector
        worker.build_search_plan = lambda criteria, requested_limit: ready_plan
        worker.AuthorizedSearchConnector = FakeConnector
        try:
            schedule = self.schedule({"sources": ["authorized_search_api"]})
            result = worker.run_due_once(self.store, due_at="2026-09-23T00:00:00+00:00", execute=True)
        finally:
            worker.build_search_plan = original_plan
            worker.AuthorizedSearchConnector = original_connector

        execution = result["items"][0]["execution"]
        self.assertEqual(execution["status"], "COMPLETED")
        self.assertEqual(execution["created_count"], 1)
        settled = self.store.get_scheduled_task(schedule["id"], WORKSPACE_ID)
        self.assertEqual(settled["latest_run"]["status"], "COMPLETED")
        self.assertEqual(settled["latest_run"]["new_result_count"], 1)
        self.assertEqual(len(self.store.list_opportunities(WORKSPACE_ID)), 1)
        usage = self.store.get_usage_by_idempotency_key(WORKSPACE_ID, "search:" + execution["run_id"] + ":authorized_search_api:1:https://buyer.example/ai-service")
        self.assertEqual(usage["outcome"], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
