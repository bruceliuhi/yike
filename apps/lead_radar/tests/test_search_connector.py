from __future__ import annotations

import json
import os
import unittest
from unittest.mock import Mock, patch

from apps.lead_radar.search_connector import AuthorizedSearchConnector, capability


PROOF_ENV = {
    "LEAD_RADAR_SEARCH_PROOF_REF": "qa-search-proof-001",
    "LEAD_RADAR_SEARCH_PROOF_SHA256": "0" * 64,
    "LEAD_RADAR_SEARCH_PROOF_CHECKED_AT": "2026-09-22T00:00:00Z",
    "LEAD_RADAR_SEARCH_PROOF_ENDPOINT": "search.example",
    "LEAD_RADAR_SEARCH_PROOF_PROVIDER": "authorized-search-api",
    "LEAD_RADAR_SEARCH_PROOF_CHECKS": json.dumps({
        "url_reopen": True, "published_at": True, "save_boundary": True, "retry_idempotency": True,
    }),
}


class AuthorizedSearchConnectorTest(unittest.TestCase):
    def test_capability_requires_reopen_proof_before_ready(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LEAD_RADAR_SEARCH_ENDPOINT": "https://search.example/api/search",
                "LEAD_RADAR_SEARCH_TOKEN": "token",
                "LEAD_RADAR_SEARCH_REOPEN_PROOF": "false",
            },
        ):
            self.assertEqual(capability()["status"], "REQUIRES_PROOF")
        with patch.dict(
            os.environ,
            {**PROOF_ENV,
                "LEAD_RADAR_SEARCH_ENDPOINT": "https://search.example/api/search",
                "LEAD_RADAR_SEARCH_TOKEN": "token",
                "LEAD_RADAR_SEARCH_REOPEN_PROOF": "true",
            },
        ):
            self.assertEqual(capability()["status"], "READY")

    def test_search_validates_and_deduplicates_provider_results(self) -> None:
        response = Mock()
        response.read.return_value = json.dumps(
            {
                "items": [
                    {"id": "1", "title": "需求一", "source_url": "https://buyer.example/a", "snippet": "需要 AI 团队。"},
                    {"id": "1-duplicate", "title": "需求一", "source_url": "https://buyer.example/a", "snippet": "重复结果。"},
                    {"id": "2", "title": "需求二", "source_url": "https://buyer.example/b", "snippet": "需要知识库。"},
                ]
            },
            ensure_ascii=False,
        ).encode("utf-8")
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        plan = {"requested_limit": 10, "strategies": [{"id": "quick", "queries": ["AI 客服 采购"]}], "hard_filters": {}}
        with patch.dict(
            os.environ,
            {**PROOF_ENV,
                "LEAD_RADAR_SEARCH_ENDPOINT": "https://search.example/api/search",
                "LEAD_RADAR_SEARCH_TOKEN": "token",
                "LEAD_RADAR_SEARCH_REOPEN_PROOF": "true",
            },
        ), patch("apps.lead_radar.search_connector.urlopen", return_value=context):
            items = AuthorizedSearchConnector().search(plan)
        self.assertEqual([item["title"] for item in items], ["需求一", "需求二"])
        self.assertEqual(items[0]["source_kind"], "authorized_search_api")
        self.assertEqual(items[0]["source_permission"], "authorized_api")


if __name__ == "__main__":
    unittest.main()
