from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from apps.lead_radar.connector_contract import get_connector_contract, validate_connector_manifest
from apps.lead_radar.mcp_server import TOOL_DEFINITIONS
from apps.lead_radar.server import create_server


class ConnectorContractTest(unittest.TestCase):
    @staticmethod
    def search_manifest() -> dict:
        checks = (
            "permission_scope_verified", "url_reopen_verified", "published_at_verified",
            "rate_limit_observed", "save_boundary_verified", "retry_idempotency_verified",
        )
        return {
            "connector_id": "search-provider-v1",
            "connector_kind": "search",
            "provider": "authorized-provider",
            "endpoint": "https://search.example/v1/query",
            "access_method": "official_api",
            "permission_scope_ref": "scope-review-001",
            "proof_artifact_ref": "artifact-001",
            "proof_artifact_sha256": "a" * 64,
            "verified_at": "2020-01-01T00:00:00Z",
            "allowed_fields": ["title", "source_url", "snippet", "published_at"],
            "reopen_sample_count": 3,
            "published_at_sample_count": 3,
            "checks": {name: True for name in checks},
        }

    def test_contract_localizes_and_declares_two_connector_kinds(self) -> None:
        zh = get_connector_contract("zh-CN")
        en = get_connector_contract("en-US")
        self.assertEqual(zh["contract_version"], "lead-radar-connector-v1")
        self.assertNotEqual(zh["name"], en["name"])
        self.assertEqual(set(zh["checks"]), {"search", "writeback"})
        self.assertFalse(zh["ready_claim_allowed"])

    def test_search_manifest_can_pass_without_exposing_credentials(self) -> None:
        report = validate_connector_manifest(self.search_manifest())
        self.assertTrue(report["schema_valid"])
        self.assertTrue(report["ready_claim_allowed"])
        self.assertEqual(report["quality_gate"]["status"], "READY")
        self.assertNotIn("secret", json.dumps(report, ensure_ascii=False).lower())

    def test_manifest_blocks_missing_proof_and_contact_fields(self) -> None:
        manifest = self.search_manifest()
        manifest["allowed_fields"].append("email")
        manifest["checks"]["url_reopen_verified"] = False
        manifest["proof_artifact_sha256"] = "bad"
        report = validate_connector_manifest(manifest)
        codes = {item["code"] for item in report["errors"]}
        self.assertFalse(report["schema_valid"])
        self.assertFalse(report["ready_claim_allowed"])
        self.assertIn("prohibited_field", codes)
        self.assertIn("sha256_required", codes)
        self.assertIn("url_reopen_verified", report["quality_gate"]["blocking_reasons"])

    def test_manifest_rejects_secret_bearing_or_ambiguous_endpoint(self) -> None:
        manifest = self.search_manifest()
        manifest["endpoint"] = "https://user:secret@example.test/query?token=leak"
        manifest["unexpected"] = "ignored"
        report = validate_connector_manifest(manifest)
        self.assertFalse(report["ready_claim_allowed"])
        self.assertIn("unknown_field", {item["code"] for item in report["errors"]})
        self.assertIn("https_url_required", {item["code"] for item in report["errors"]})

    def test_writeback_requires_readback_rollback_and_idempotency(self) -> None:
        manifest = self.search_manifest()
        manifest.update({
            "connector_id": "crm-v1",
            "connector_kind": "writeback",
            "access_method": "oauth",
            "idempotency_key_field": "lead_radar_event_id",
            "checks": {
                "permission_scope_verified": True,
                "field_allowlist_verified": True,
                "retry_idempotency_verified": True,
                "writeback_readback_verified": True,
                "rollback_verified": True,
            },
        })
        manifest.pop("reopen_sample_count")
        manifest.pop("published_at_sample_count")
        report = validate_connector_manifest(manifest)
        self.assertTrue(report["ready_claim_allowed"])
        self.assertEqual(report["summary"]["endpoint_host"], "search.example")

    def test_contract_is_available_over_http_and_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            server = create_server("127.0.0.1", 0, str(Path(tempdir) / "connector.sqlite3"))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                connection = HTTPConnection(host, port)
                connection.request("GET", "/api/v1/connector-contract?language=en-US")
                response = connection.getresponse()
                payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(response.status, 200)
                self.assertEqual(payload["language"], "en-US")
                body = json.dumps(self.search_manifest()).encode("utf-8")
                connection.request("POST", "/api/v1/connector-contract/validate", body=body, headers={"Content-Type": "application/json"})
                response = connection.getresponse()
                validated = json.loads(response.read().decode("utf-8"))
                connection.close()
                self.assertEqual(response.status, 200)
                self.assertTrue(validated["ready_claim_allowed"])
            finally:
                server.shutdown()
                server.server_close()
                server.store.close()

        definitions = {item["name"]: item for item in TOOL_DEFINITIONS}
        self.assertTrue(definitions["get_connector_contract"]["readOnlyHint"])
        self.assertTrue(definitions["validate_connector_manifest"]["readOnlyHint"])
        self.assertEqual(definitions["validate_connector_manifest"]["inputSchema"]["required"], ["manifest"])


if __name__ == "__main__":
    unittest.main()
