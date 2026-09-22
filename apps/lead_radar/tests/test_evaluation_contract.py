from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from apps.lead_radar.evaluation_contract import get_evaluation_contract, validate_evaluation_manifest
from apps.lead_radar.mcp_server import TOOL_DEFINITIONS
from apps.lead_radar.server import create_server


class EvaluationContractTest(unittest.TestCase):
    @staticmethod
    def manifest() -> dict:
        sample = {
            "sample_id": "sample-001",
            "industry": "制造业",
            "source_family": "authorized_search",
            "source_url": "https://buyer.example/request-1",
            "source_permission": "authorized_search_api",
            "source_proof_ref": "proof-001",
            "published_at": "2026-09-23T08:00:00Z",
            "snippet": "正在评估企业 AI 客服定制开发团队。",
            "system_predicted_label": "VALID",
            "gold_label": "VALID",
            "reviewer": "qa",
            "review_note": "原文明确表达采购评估动作。",
            "reopen_required": True,
            "reopen_verified": True,
            "evidence_fingerprint": "sha256:sample-001",
        }
        second = dict(sample)
        second.update({"sample_id": "sample-002", "source_url": "https://buyer.example/request-2", "industry": "零售"})
        return {
            "dataset": {
                "dataset_id": "qa-dataset",
                "dataset_version": "2026-09-23.1",
                "license_or_rights_ref": "rights-001",
                "label_policy_version": "gold-v1",
                "rights_approval_verified": True,
                "external_actions_sent": 0,
            },
            "samples": [sample, second],
        }

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

    def test_manifest_validator_separates_schema_validity_from_release_gates(self) -> None:
        report = validate_evaluation_manifest(self.manifest())
        self.assertTrue(report["schema_valid"])
        self.assertFalse(report["benchmark_claim_allowed"])
        self.assertEqual(report["summary"]["sample_count"], 2)
        self.assertEqual(report["summary"]["accuracy"], 1.0)
        self.assertEqual(report["summary"]["reopen_rate"], 1.0)
        self.assertEqual(report["summary"]["rights_reference_ratio"], 1.0)
        self.assertIn("sample_count_below_30", report["quality_gate"]["blocking_reasons"])
        self.assertNotIn("manifest_invalid", report["quality_gate"]["blocking_reasons"])

    def test_manifest_validator_rejects_prohibited_fields_bad_urls_and_duplicates(self) -> None:
        manifest = self.manifest()
        manifest["dataset"]["external_actions_sent"] = 1
        manifest["samples"][0]["phone"] = "13800000000"
        manifest["samples"][0]["source_url"] = "http://not-https.example/request"
        manifest["samples"][1]["sample_id"] = manifest["samples"][0]["sample_id"]
        report = validate_evaluation_manifest(manifest)
        codes = {error["code"] for error in report["errors"]}
        self.assertFalse(report["schema_valid"])
        self.assertIn("prohibited_field", codes)
        self.assertIn("https_url_required", codes)
        self.assertIn("duplicate_sample_id", codes)
        self.assertIn("external_actions_sent", report["quality_gate"]["blocking_reasons"])
        self.assertIn("manifest_invalid", report["quality_gate"]["blocking_reasons"])

    def test_manifest_validator_is_available_over_http_and_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            server = create_server("127.0.0.1", 0, str(Path(tempdir) / "validation.sqlite3"))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                connection = HTTPConnection(host, port)
                body = json.dumps(self.manifest(), ensure_ascii=False).encode("utf-8")
                connection.request("POST", "/api/v1/evaluation-contract/validate", body=body, headers={"Content-Type": "application/json"})
                response = connection.getresponse()
                payload = json.loads(response.read().decode("utf-8"))
                connection.close()
                self.assertEqual(response.status, 200)
                self.assertTrue(payload["schema_valid"])
                self.assertIn("sample_count_below_30", payload["quality_gate"]["blocking_reasons"])
            finally:
                server.shutdown()
                server.server_close()
                server.store.close()

        tool = next(item for item in TOOL_DEFINITIONS if item["name"] == "validate_evaluation_manifest")
        self.assertTrue(tool["readOnlyHint"])
        self.assertEqual(tool["inputSchema"]["required"], ["manifest"])
        self.assertFalse(tool["inputSchema"]["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
