from __future__ import annotations

import unittest

from apps.lead_radar.planner import build_search_plan


class SearchPlanExecutionContractTest(unittest.TestCase):
    def test_plan_exposes_truthful_blocked_state_when_sources_are_not_ready(self) -> None:
        plan = build_search_plan(
            {
                "solution_terms": ["AI 客服"],
                "purchase_terms": ["采购"],
                "business_terms": ["企业"],
                "sources": ["xiaohongshu_public", "xiaohongshu_public", "unknown_source"],
            },
            10,
        )

        self.assertEqual(plan["planner_version"], "2026.09.23.1")
        self.assertEqual(plan["execution"]["status"], "BLOCKED_REQUIRES_SOURCE")
        self.assertFalse(plan["execution"]["can_start"])
        self.assertEqual(plan["execution"]["runnable_sources"], [])
        self.assertEqual(plan["coverage"]["requested_source_count"], 2)
        self.assertEqual(plan["coverage"]["blocked_source_count"], 2)
        self.assertIn("受控公开 URL", plan["execution"]["summary"])

    def test_plan_marks_execution_ready_only_for_a_search_capable_source(self) -> None:
        plan = build_search_plan(
            {
                "solution_terms": ["AI 客服"],
                "purchase_terms": ["采购"],
                "business_terms": ["企业"],
                "sources": ["manual_public_evidence", "ready_test_source"],
            },
            5,
        )

        # The current catalog contains no READY search connector. This assertion makes
        # the contract explicit and prevents a display-only source from being treated as executable.
        self.assertEqual(plan["execution"]["status"], "BLOCKED_REQUIRES_SOURCE")
        self.assertFalse(plan["execution"]["can_start"])
        self.assertEqual(plan["coverage"]["runnable_source_count"], 0)
        self.assertEqual(plan["coverage"]["source_ids"], ["manual_public_evidence", "ready_test_source"])


if __name__ == "__main__":
    unittest.main()
