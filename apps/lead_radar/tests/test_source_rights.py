from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from apps.lead_radar.server import create_server


WORKSPACE_PATH = "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI"


class SourceRightsApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.server = create_server("127.0.0.1", 0, str(Path(self.tempdir.name) / "rights.sqlite3"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server.store.close()
        self.tempdir.cleanup()

    def request(self, method: str, path: str, payload: dict | None = None):
        connection = HTTPConnection(self.host, self.port)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        connection.request(method, path, body=body, headers={"Content-Type": "application/json; charset=utf-8"})
        response = connection.getresponse()
        result = json.loads(response.read().decode("utf-8"))
        connection.close()
        return response.status, result

    def proof_payload(self) -> dict:
        return {
            "proof_ref": "rights-proof-001",
            "provider": "authorized-search-api",
            "source_family": "authorized_search",
            "endpoint": "https://search.example/proof/rights-proof-001",
            "artifact_sha256": "b" * 64,
            "checked_at": "2026-09-22T00:00:00Z",
            "checks": {
                "terms_and_robots": True,
                "rate_limit": True,
                "published_at": True,
                "url_reopen": True,
                "save_boundary": True,
                "retry_idempotency": True,
            },
        }

    def right_payload(self) -> dict:
        return {
            "source_id": "authorized_search_api",
            "provider": "authorized-search-api",
            "source_family": "authorized_search",
            "access_method": "OFFICIAL_API",
            "terms_url": "https://search.example/terms",
            "privacy_url": "https://search.example/privacy",
            "allowed_operations": ["SEARCH", "REOPEN", "STORE_EXCERPT"],
            "allowed_fields": ["title", "source_url", "snippet", "published_at"],
            "can_search": True,
            "can_write_back": False,
            "store_original": False,
            "retention_days": 30,
            "rate_limit_per_minute": 60,
            "notes": "仅保存候选摘要和可重开 URL。",
        }

    def test_rights_require_active_proof_before_approval_and_can_be_suspended(self) -> None:
        status, created = self.request("POST", f"{WORKSPACE_PATH}/source-rights", self.right_payload())
        self.assertEqual(status, 201)
        right_id = created["right"]["id"]
        self.assertEqual(created["right"]["permission_status"], "PENDING")
        self.assertEqual(created["right"]["retention_days"], 30)

        status, rejected = self.request("POST", f"/api/v1/source-rights/{right_id}/approve", {"proof_ref": "missing-proof", "actor": "qa"})
        self.assertEqual(status, 400)
        self.assertEqual(rejected["error"], "invalid_request")

        status, proof = self.request("POST", f"{WORKSPACE_PATH}/source-proofs", self.proof_payload())
        self.assertEqual(status, 201)
        status, approved = self.request("POST", f"/api/v1/source-rights/{right_id}/approve", {"proof_ref": "rights-proof-001", "actor": "qa"})
        self.assertEqual(status, 200)
        self.assertEqual(approved["right"]["permission_status"], "APPROVED")
        self.assertEqual(approved["right"]["proof_ref"], proof["proof"]["proof_ref"])
        self.assertIsNotNone(self.server.store.get_approved_source_right("ws_意客AI", "authorized_search_api"))

        status, suspended = self.request("POST", f"/api/v1/source-rights/{right_id}/suspend", {"actor": "qa", "reason": "合同审查需要重新确认。"})
        self.assertEqual(status, 200)
        self.assertEqual(suspended["right"]["permission_status"], "SUSPENDED")
        self.assertIsNone(self.server.store.get_approved_source_right("ws_意客AI", "authorized_search_api"))

    def test_rights_reject_unsafe_urls_and_permission_mismatch(self) -> None:
        invalid = {**self.right_payload(), "terms_url": "http://search.example/terms"}
        status, rejected = self.request("POST", f"{WORKSPACE_PATH}/source-rights", invalid)
        self.assertEqual(status, 400)
        self.assertEqual(rejected["error"], "terms_url_invalid")
        invalid = {**self.right_payload(), "source_id": "another", "store_original": True}
        status, rejected = self.request("POST", f"{WORKSPACE_PATH}/source-rights", invalid)
        self.assertEqual(status, 400)
        self.assertEqual(rejected["error"], "store_original_operation_required")


if __name__ == "__main__":
    unittest.main()
