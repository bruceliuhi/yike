from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from apps.lead_radar.evaluation_contract import get_evaluation_contract
from apps.lead_radar.server import create_server


class EvaluationContractTest(unittest.TestCase):
    def test_contract_is_explicitly_not_a_benchmark_claim(self) -> None:
        contract = get_evaluation_contract()
        self.assertEqual(contract["contract_version"], "lead-radar-evaluation-v1")
        self.assertEqual(contract["status"], "CONTRACT_READY")
        self.assertFalse(contract["benchmark_claim_allowed"])
        self.assertTrue(contract["requires_real_authorized_samples"])
        self.assertEqual(contract["quality_gates"]["minimum_sample_count"], 30)
        self.assertIn("license_or_rights_ref", {field["name"] for field in contract["dataset_fields"]})
        self.assertIn("source_permission", {field["name"] for field in contract["sample_fields"]})

    def test_contract_localizes_descriptions_without_leaking_schema_objects(self) -> None:
        zh = get_evaluation_contract("zh-CN")
        en = get_evaluation_contract("en-US")
        self.assertNotEqual(zh["name"], en["name"])
        self.assertNotEqual(zh["sample_fields"][0]["description"], en["sample_fields"][0]["description"])
        zh["sample_fields"][0]["name"] = "mutated"
        self.assertEqual(get_evaluation_contract()["sample_fields"][0]["name"], "sample_id")
        with self.assertRaises(ValueError):
            get_evaluation_contract("fr-FR")

    def test_contract_is_available_from_the_lead_radar_api(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            server = create_server("127.0.0.1", 0, str(Path(tempdir) / "evaluation.sqlite3"))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                connection = HTTPConnection(host, port)
                connection.request("GET", "/api/v1/evaluation-contract?language=en-US")
                response = connection.getresponse()
                payload = json.loads(response.read().decode("utf-8"))
                connection.close()
                self.assertEqual(response.status, 200)
                self.assertEqual(payload["language"], "en-US")
                self.assertFalse(payload["benchmark_claim_allowed"])
            finally:
                server.shutdown()
                server.server_close()
                server.store.close()


if __name__ == "__main__":
    unittest.main()
