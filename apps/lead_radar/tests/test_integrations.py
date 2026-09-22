import unittest

from apps.lead_radar.integrations import list_integrations


class IntegrationCatalogTests(unittest.TestCase):
    def test_catalog_is_explicit_and_does_not_claim_ready(self):
        items = list_integrations()
        self.assertGreaterEqual(len(items), 4)
        self.assertTrue(all(item["status"] in {"REQUIRES_AUTH", "REQUIRES_PROOF"} for item in items))
        self.assertTrue(all(item["configured"] is False for item in items))
        for item in items:
            self.assertNotIn("secret", item)
            self.assertNotIn("password", item)
            self.assertTrue(item["allowed_fields"])
            self.assertTrue(item["blocked_fields"])
            self.assertTrue(item["evidence_required"])

    def test_catalog_supports_only_declared_languages(self):
        zh = list_integrations("zh-CN")
        en = list_integrations("en-US")
        self.assertEqual(len(zh), len(en))
        self.assertEqual(zh[0]["language"], "zh-CN")
        self.assertEqual(en[0]["language"], "en-US")
        self.assertNotEqual(zh[0]["name"], en[0]["name"])
        with self.assertRaises(ValueError):
            list_integrations("fr-FR")


if __name__ == "__main__":
    unittest.main()
