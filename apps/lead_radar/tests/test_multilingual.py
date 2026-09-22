from __future__ import annotations

import unittest

from apps.lead_radar.domain import compile_intent
from apps.lead_radar.planner import build_search_plan


class MultilingualPlanTest(unittest.TestCase):
    def test_english_objective_compiles_to_english_queries(self) -> None:
        criteria = compile_intent(
            "Find an enterprise looking for AI customer service implementation",
            {"language": "en-US"},
        )
        self.assertEqual(criteria["language"], "en-US")
        self.assertIn("ai customer service", [term.lower() for term in criteria["solution_terms"]])
        self.assertTrue(any("implementation" in term.lower() for term in criteria["purchase_terms"]))
        plan = build_search_plan(criteria, 10)
        self.assertEqual(plan["language"], "en-US")
        queries = [query for strategy in plan["strategies"] for query in strategy["queries"]]
        self.assertTrue(queries)
        self.assertTrue(any("-tutorial" in query for query in queries))
        self.assertFalse(any("-教程" in query for query in queries))

    def test_language_is_detected_for_chinese_and_rejects_unknown_values(self) -> None:
        self.assertEqual(compile_intent("寻找企业 AI 客服采购需求")["language"], "zh-CN")
        with self.assertRaisesRegex(ValueError, "language_not_supported"):
            compile_intent("Find an AI vendor", {"language": "fr-FR"})


if __name__ == "__main__":
    unittest.main()
