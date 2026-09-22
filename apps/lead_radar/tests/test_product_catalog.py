from __future__ import annotations

import unittest

from apps.lead_radar.mcp_server import TOOL_DEFINITIONS
from apps.lead_radar.product_catalog import list_product_catalog


class ProductCatalogTest(unittest.TestCase):
    def test_catalog_describes_buyer_outcomes_and_external_boundaries(self) -> None:
        items = list_product_catalog("zh-CN")
        self.assertEqual(len(items), 6)
        self.assertTrue(all(item["buyer_value"] for item in items))
        self.assertTrue(all(item["inputs"] and item["outputs"] for item in items))
        self.assertTrue(any(item["status"] == "CATALOG_ONLY" for item in items))
        self.assertTrue(any(item["requires_external_proof"] for item in items))
        english = list_product_catalog("en-US")
        self.assertEqual(english[0]["name"], "Intent compiler and search plan")
        self.assertEqual(english[0]["language"], "en-US")

    def test_mcp_product_catalog_is_read_only(self) -> None:
        tool = next(item for item in TOOL_DEFINITIONS if item["name"] == "list_product_catalog")
        self.assertTrue(tool["readOnlyHint"])
        self.assertEqual(set(tool["inputSchema"]["properties"]), {"language"})
        self.assertFalse(tool["inputSchema"]["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
