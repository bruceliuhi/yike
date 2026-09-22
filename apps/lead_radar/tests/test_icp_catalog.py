from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from apps.lead_radar.icp_catalog import get_icp_profile, list_icp_profiles
from apps.lead_radar.mcp_server import TOOL_DEFINITIONS
from apps.lead_radar.server import create_server


class IcpCatalogTest(unittest.TestCase):
    def test_profile_is_versioned_and_explicit_about_gates(self) -> None:
        profiles = list_icp_profiles()
        self.assertEqual([item["id"] for item in profiles], ["ai_solution_buyer_v1"])
        profile = profiles[0]
        self.assertEqual(profile["status"], "READY_LOCAL")
        self.assertTrue(profile["requires_external_source_proof"])
        self.assertTrue(profile["qualification_policy"]["required_human_review"])
        self.assertEqual(profile["pilot_acceptance"][0], "30 条真实候选人工校准")
        self.assertEqual(get_icp_profile("ai_solution_buyer_v1", "en-US")["language"], "en-US")
        with self.assertRaises(ValueError):
            list_icp_profiles("fr-FR")

    def test_icp_catalog_is_available_over_http_and_mcp(self) -> None:
        names = {item["name"] for item in TOOL_DEFINITIONS}
        self.assertIn("list_icp_profiles", names)
        with tempfile.TemporaryDirectory() as tempdir:
            server = create_server("127.0.0.1", 0, str(Path(tempdir) / "icp.sqlite3"))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                connection = HTTPConnection(host, port)
                connection.request("GET", "/api/v1/icp-profiles?language=en-US")
                response = connection.getresponse()
                payload = json.loads(response.read().decode("utf-8"))
                connection.close()
                self.assertEqual(response.status, 200)
                self.assertEqual(payload["language"], "en-US")
                self.assertEqual(payload["items"][0]["name"], "AI solution buyer")
            finally:
                server.shutdown()
                server.server_close()
                server.store.close()


if __name__ == "__main__":
    unittest.main()
