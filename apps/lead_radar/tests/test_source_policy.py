from __future__ import annotations

import unittest

from apps.lead_radar.connectors import list_capabilities
from apps.lead_radar.domain import compile_intent
from apps.lead_radar.planner import build_search_plan
from apps.lead_radar.source_policy import classify_public_url, source_capability_metadata


class PublicSourcePolicyTest(unittest.TestCase):
    def test_classifies_social_urls_without_granting_crawl_permission(self) -> None:
        cases = {
            "https://www.xiaohongshu.com/explore/abc": "xiaohongshu",
            "https://v.douyin.com/abc": "douyin",
            "https://www.bilibili.com/video/BVabc": "bilibili",
            "https://b23.tv/abc": "bilibili",
            "https://buyer.example/request": "web",
        }
        for url, expected_platform in cases.items():
            with self.subTest(url=url):
                result = classify_public_url(url)
                self.assertEqual(result["platform"], expected_platform)
                self.assertFalse(result["end_user_login_required"])
                self.assertEqual(result["automated_search_status"], "REQUIRES_PROOF")
                if expected_platform != "web":
                    self.assertTrue(result["server_authorization_required"])

    def test_capabilities_expose_three_public_platforms_and_login_boundary(self) -> None:
        capabilities = {item["id"]: item for item in list_capabilities()}
        for source_id, platform in (
            ("xiaohongshu_public", "xiaohongshu"),
            ("douyin_public", "douyin"),
            ("bilibili_public", "bilibili"),
        ):
            with self.subTest(source_id=source_id):
                item = capabilities[source_id]
                self.assertEqual(item["status"], "REQUIRES_PROOF")
                self.assertFalse(item["can_search"])
                self.assertFalse(item["end_user_login_required"])
                self.assertTrue(item["server_authorization_required"])
                self.assertEqual(item["platform"], platform)
                self.assertIn("url_reopen", item["proof_gates"])

    def test_default_plan_lists_all_three_public_platforms_but_stays_blocked(self) -> None:
        criteria = compile_intent("寻找企业 AI 客服定制需求")
        plan = build_search_plan(criteria, 10)
        source_ids = plan["coverage"]["source_ids"]
        self.assertEqual(
            source_ids,
            ["public_web", "xiaohongshu_public", "douyin_public", "bilibili_public"],
        )
        self.assertEqual(plan["execution"]["status"], "BLOCKED_REQUIRES_SOURCE")
        self.assertFalse(plan["execution"]["can_start"])

    def test_policy_contract_rejects_unknown_platform(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown_public_source_platform"):
            source_capability_metadata("unknown")


if __name__ == "__main__":
    unittest.main()
