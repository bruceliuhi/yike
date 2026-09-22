from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from apps.lead_radar.capture import CaptureError, extract_document
from apps.lead_radar.server import create_server
from apps.lead_radar.search_connector import SearchConnectorError


ROOT = Path(__file__).resolve().parents[3]


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


class LeadRadarApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.server = create_server("127.0.0.1", 0, str(Path(self.tempdir.name) / "test.sqlite3"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server.store.close()
        self.tempdir.cleanup()

    def request(self, method: str, path: str, payload: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
        connection = HTTPConnection(self.host, self.port)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        connection.request(method, path, body=body, headers={"Content-Type": "application/json; charset=utf-8", **(headers or {})})
        response = connection.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        connection.close()
        return response.status, data

    def register_source_proof(self, proof_ref: str, provider: str = "licensed-search-index") -> tuple[int, dict]:
        return self.request(
            "POST",
            "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/source-proofs",
            {
                "proof_ref": proof_ref,
                "provider": provider,
                "source_family": "authorized_search_index",
                "endpoint": "https://search.example/proof/" + proof_ref,
                "artifact_sha256": "a" * 64,
                "checked_at": "2026-09-22T00:00:00Z",
                "checks": {
                    "terms_and_robots": True,
                    "rate_limit": True,
                    "published_at": True,
                    "url_reopen": True,
                    "save_boundary": True,
                    "retry_idempotency": True,
                },
            },
        )

    def test_source_proof_registration_is_validated_and_idempotent(self) -> None:
        status, created = self.register_source_proof("proof-registry-001")
        self.assertEqual(status, 201)
        self.assertTrue(created["created"])
        self.assertEqual(created["proof"]["proof_ref"], "proof-registry-001")

        status, duplicate = self.register_source_proof("proof-registry-001")
        self.assertEqual(status, 200)
        self.assertFalse(duplicate["created"])
        self.assertEqual(created["proof"]["id"], duplicate["proof"]["id"])

        status, conflict = self.register_source_proof("proof-registry-001", "other-provider")
        self.assertEqual(status, 400)
        self.assertEqual(conflict["error"], "invalid_request")

        malformed = {
            "proof_ref": "proof-invalid",
            "provider": "licensed-search-index",
            "source_family": "authorized_search_index",
            "endpoint": "http://search.example/proof",
            "artifact_sha256": "not-a-sha",
            "checked_at": "2026-09-22T00:00:00Z",
            "checks": {},
        }
        status, rejected = self.request(
            "POST",
            "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/source-proofs",
            malformed,
        )
        self.assertEqual(status, 400)
        self.assertEqual(rejected["error"], "endpoint_invalid")

        status, listed = self.request("GET", "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/source-proofs")
        self.assertEqual(status, 200)
        self.assertEqual(len(listed["items"]), 1)

    def test_index_import_requires_registered_source_proof(self) -> None:
        _, task = self.request(
            "POST",
            "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks",
            {"objective": "验证来源证明绑定"},
        )
        payload = {
            "provider": "licensed-search-index",
            "query": "AI 客服",
            "proof_ref": "proof-unregistered",
            "retrieved_at": "2026-09-22T12:00:00Z",
            "items": [{
                "position": 1,
                "title": "企业 AI 客服需求",
                "source_url": "https://example.com/request",
                "snippet": "公开需求摘要",
            }],
        }
        status, rejected = self.request("POST", f"/api/v1/tasks/{task['id']}/index-results", payload)
        self.assertEqual(status, 400)
        self.assertEqual(rejected["error"], "proof_not_registered")

    def test_task_idempotency_and_evidence_feedback_loop(self) -> None:
        path = "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks"
        request_headers = {"Idempotency-Key": "same-task-request"}
        status, task = self.request("POST", path, {"objective": "寻找企业 AI 客服定制需求", "requested_limit": 10}, request_headers)
        self.assertEqual(status, 201)
        self.assertIsNotNone(task["plan"])
        self.assertEqual([strategy["id"] for strategy in task["plan"]["strategies"]], ["quick", "condition", "broad"])
        self.assertGreater(task["estimated_credits"], 0)
        status, duplicate = self.request("POST", path, {"objective": "这个请求不能产生第二个任务"}, request_headers)
        self.assertEqual(status, 201)
        self.assertEqual(task["id"], duplicate["id"])

        task_path = f"/api/v1/tasks/{task['id']}/opportunities"
        status, rejected = self.request("POST", task_path, {"title": "缺少原文片段", "source_url": "https://example.com/a"})
        self.assertEqual(status, 400)
        self.assertEqual(rejected["error"], "invalid_request")

        status, created = self.request("POST", task_path, {"title": "企业寻找 AI 客服开发团队", "author": "公开账号", "source_url": "https://example.com/a", "snippet": "希望寻找团队定制企业 AI 客服并尽快落地。", "intent_type": "定制 / 开发", "source_permission": "allowed", "evidence_level": "VERIFIED"})
        self.assertEqual(status, 201)
        self.assertEqual(created["created_count"], 1)
        opportunity_id = created["items"][0]["id"]
        self.assertEqual(created["items"][0]["status"], "SEND_READY")
        self.assertEqual(created["items"][0]["decision"]["code"], "VERIFIED_ALLOWED_EVIDENCE")

        status, feedback = self.request("POST", f"/api/v1/opportunities/{opportunity_id}/feedback", {"label": "INVALID", "note": "人工复核后排除"})
        self.assertEqual(status, 200)
        self.assertEqual(feedback["status"], "EXCLUDE")
        status, detail = self.request("GET", f"/api/v1/opportunities/{opportunity_id}")
        self.assertEqual(status, 200)
        self.assertEqual(detail["evidence"][0]["content"], "希望寻找团队定制企业 AI 客服并尽快落地。")
        self.assertEqual(detail["feedback_events"][-1]["note"], "人工复核后排除")
        self.assertEqual(detail["audit_events"][-1]["payload"]["label"], "INVALID")
        self.assertEqual(feedback["feedback_events"][-1]["label"], "INVALID")
        self.assertEqual(feedback["audit_events"][-1]["action"], "feedback")

        status, started = self.request("POST", f"/api/v1/tasks/{task['id']}/start", {"mode": "quick"})
        self.assertEqual(status, 200)
        self.assertEqual(started["runs"][0]["status"], "BLOCKED_REQUIRES_SOURCE")
        self.assertEqual(started["runs"][0]["error_code"], "NO_SEARCH_CONNECTOR_READY")
        self.assertEqual(started["runs"][0]["events"][0]["event_type"], "created")
        run_id = started["runs"][0]["id"]
        status, run_events = self.request("GET", f"/api/v1/tasks/{task['id']}/runs/{run_id}/events")
        self.assertEqual(status, 200)
        self.assertEqual(run_events["events"][0]["status"], "BLOCKED_REQUIRES_SOURCE")
        status, plan = self.request("GET", f"/api/v1/tasks/{task['id']}/plan")
        self.assertEqual(status, 200)
        self.assertEqual(plan["cost_estimate"]["unit"], "credits")

        status, dashboard = self.request("GET", "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/dashboard")
        self.assertEqual(status, 200)
        self.assertEqual(dashboard["opportunities"], 1)
        self.assertEqual(dashboard["excluded"], 1)
        self.assertEqual(dashboard["running_tasks"], 0)
        self.assertEqual(dashboard["awaiting_source"], 1)

        status, audit = self.request("GET", "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/audit?limit=20")
        self.assertEqual(status, 200)
        self.assertEqual(audit["workspace_id"], "ws_意客AI")
        self.assertGreater(len(audit["events"]), 0)
        self.assertIsInstance(audit["usage"], list)
        self.assertIn("credits_used", audit)

    def test_task_run_cancel_retry_and_event_history(self) -> None:
        _, task = self.request("POST", "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks", {"objective": "验证运行控制"})
        status, started = self.request("POST", f"/api/v1/tasks/{task['id']}/start", {"mode": "quick"})
        self.assertEqual(status, 200)
        run_id = started["runs"][0]["id"]

        status, cancelled = self.request("POST", f"/api/v1/tasks/{task['id']}/runs/{run_id}/cancel", {"actor": "qa"})
        self.assertEqual(status, 200)
        self.assertEqual(cancelled["run"]["status"], "CANCELLED")
        self.assertEqual(cancelled["run"]["events"][-1]["event_type"], "cancel")
        status, retried = self.request("POST", f"/api/v1/tasks/{task['id']}/runs/{run_id}/retry", {"actor": "qa"})
        self.assertEqual(status, 200)
        self.assertEqual(retried["run"]["status"], "BLOCKED_REQUIRES_SOURCE")
        self.assertEqual(retried["run"]["events"][0]["event_type"], "retry_created")
        self.assertEqual(len(retried["runs"]), 2)

    def test_action_drafts_bind_evidence_and_require_explicit_approval(self) -> None:
        _, task = self.request(
            "POST",
            "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks",
            {"objective": "生成 AI 客服需求的人工跟进草稿"},
        )
        _, created = self.request(
            "POST",
            f"/api/v1/tasks/{task['id']}/opportunities",
            {
                "title": "企业寻找 AI 客服开发团队",
                "source_url": "https://buyer.example/request/1",
                "snippet": "公开页面明确提到正在评估 AI 客服定制开发。",
                "intent_type": "定制 / 开发",
                "source_permission": "allowed",
                "evidence_level": "VERIFIED",
            },
        )
        opportunity_id = created["items"][0]["id"]
        draft_path = f"/api/v1/opportunities/{opportunity_id}/action-drafts"
        headers = {"Idempotency-Key": "draft-request-1"}
        status, first = self.request("POST", draft_path, {"channels": ["PUBLIC_REPLY", "EMAIL"]}, headers)
        self.assertEqual(status, 200)
        self.assertEqual(first["count"], 2)
        self.assertEqual({item["channel"] for item in first["items"]}, {"PUBLIC_REPLY", "EMAIL"})
        self.assertTrue(all(item["status"] == "DRAFT" for item in first["items"]))
        self.assertTrue(all(item["evidence_ids"] for item in first["items"]))
        status, duplicate = self.request("POST", draft_path, {"channels": ["PUBLIC_REPLY", "EMAIL"]}, headers)
        self.assertEqual(status, 200)
        self.assertEqual(duplicate["count"], 2)
        self.assertEqual(len(duplicate["items"]), 2)
        self.assertEqual(len({item["id"] for item in duplicate["items"]}), 2)

        public_reply = next(item for item in first["items"] if item["channel"] == "PUBLIC_REPLY")
        status, rejected = self.request("POST", f"/api/v1/action-drafts/{public_reply['id']}/approve", {"confirm": False})
        self.assertEqual(status, 400)
        self.assertEqual(rejected["error"], "invalid_request")
        status, approved = self.request("POST", f"/api/v1/action-drafts/{public_reply['id']}/approve", {"confirm": True, "actor": "qa"})
        self.assertEqual(status, 200)
        self.assertEqual(approved["draft"]["status"], "APPROVED")
        status, detail = self.request("GET", f"/api/v1/opportunities/{opportunity_id}")
        self.assertEqual(status, 200)
        self.assertEqual(detail["audit_events"][-1]["action"], "action_draft_approved")
        self.assertFalse(detail["audit_events"][-1]["payload"]["sent"])

        email = next(item for item in first["items"] if item["channel"] == "EMAIL")
        status, cancelled = self.request("POST", f"/api/v1/action-drafts/{email['id']}/cancel", {"actor": "qa"})
        self.assertEqual(status, 200)
        self.assertEqual(cancelled["draft"]["status"], "CANCELLED")

    def test_search_index_import_is_proof_bound_review_only_and_idempotent(self) -> None:
        _, task = self.request(
            "POST",
            "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks",
            {"objective": "从公开索引发现三平台 AI 需求"},
        )
        payload = {
            "provider": "licensed-search-index",
            "query": "site:xiaohongshu.com AI 客服 定制",
            "proof_ref": "proof-index-20260923-001",
            "retrieved_at": "2026-09-22T12:00:00Z",
            "items": [
                {
                    "position": 1,
                    "title": "企业寻找 AI 客服团队",
                    "source_url": "https://www.xiaohongshu.com/explore/index-1",
                    "snippet": "正在评估企业 AI 客服定制开发。",
                },
                {
                    "position": 2,
                    "title": "企业寻找 AI 客服团队",
                    "source_url": "https://www.xiaohongshu.com/explore/index-1",
                    "snippet": "重复索引结果。",
                },
                {
                    "position": 3,
                    "title": "抖音公开需求摘要",
                    "source_url": "https://www.douyin.com/video/index-2",
                    "snippet": "想找团队落地企业知识库。",
                },
            ],
        }
        path = f"/api/v1/tasks/{task['id']}/index-results"
        status, blocked = self.request("POST", path, payload)
        self.assertEqual(status, 400)
        self.assertEqual(blocked["error"], "proof_not_registered")

        proof_path = "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/source-proofs"
        proof_payload = {
            "proof_ref": payload["proof_ref"],
            "provider": payload["provider"],
            "source_family": "social_platform",
            "endpoint": "https://provider.example/search",
            "artifact_sha256": "a" * 64,
            "checked_at": "2026-09-22T11:00:00Z",
            "checks": {
                "terms_and_robots": True,
                "rate_limit": True,
                "published_at": True,
                "url_reopen": True,
                "save_boundary": True,
                "retry_idempotency": True,
            },
        }
        status, registered = self.request("POST", proof_path, proof_payload)
        self.assertEqual(status, 201)
        self.assertTrue(registered["created"])
        status, repeated = self.request("POST", proof_path, proof_payload)
        self.assertEqual(status, 200)
        self.assertFalse(repeated["created"])
        status, conflict = self.request(
            "POST",
            proof_path,
            {**proof_payload, "artifact_sha256": "b" * 64},
        )
        self.assertEqual(status, 400)
        self.assertEqual(conflict["error"], "invalid_request")
        self.assertIn("source_proof_ref_conflict", conflict["message"])
        status, proofs = self.request("GET", proof_path)
        self.assertEqual(status, 200)
        self.assertEqual(proofs["items"][0]["artifact_sha256"], "a" * 64)

        status, first = self.request("POST", path, payload)
        self.assertEqual(status, 201)
        self.assertEqual(first["created_count"], 2)
        self.assertEqual(first["deduplicated_count"], 0)
        self.assertTrue(first["source"]["reopen_required"])
        self.assertEqual(first["source"]["proof_registry_status"], "REGISTERED")
        self.assertEqual({item["item"]["status"] for item in first["items"]}, {"REVIEW"})
        by_platform = {
            item["item"]["evidence"][0]["metadata"]["source_provenance"]["platform"]
            for item in first["items"]
        }
        self.assertEqual(by_platform, {"xiaohongshu", "douyin"})
        self.assertTrue(all(item["item"]["evidence"][0]["metadata"]["reopen_required"] for item in first["items"]))
        self.assertTrue(all(item["item"]["evidence"][0]["metadata"]["proof_registry_status"] == "REGISTERED" for item in first["items"]))

        status, retry = self.request("POST", path, payload)
        self.assertEqual(status, 201)
        self.assertEqual(retry["created_count"], 0)
        self.assertEqual(retry["deduplicated_count"], 2)
        _, dashboard = self.request("GET", "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/dashboard")
        self.assertEqual(dashboard["opportunities"], 2)
        self.assertEqual(dashboard["credits_used"], 2)

        status, invalid = self.request(
            "POST",
            path,
            {**payload, "proof_ref": "", "retrieved_at": "2026-09-22T12:00:00Z"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(invalid["error"], "proof_ref_required")

        status, future = self.request(
            "POST",
            path,
            {**payload, "proof_ref": "proof-future", "retrieved_at": "2999-01-01T00:00:00Z"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(future["error"], "retrieved_at_in_future")

        status, invalid_position = self.request(
            "POST",
            path,
            {**payload, "proof_ref": "proof-position", "items": [{**payload["items"][0], "position": "zero"}]},
        )
        self.assertEqual(status, 400)
        self.assertEqual(invalid_position["error"], "position_invalid")

    def test_search_index_candidate_reopens_original_url_and_stays_review(self) -> None:
        _, task = self.request(
            "POST",
            "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks",
            {"objective": "重开索引候选原文"},
        )
        index_payload = {
            "provider": "licensed-search-index",
            "query": "site:bilibili.com AI 客服 采购",
            "proof_ref": "proof-reopen-001",
            "retrieved_at": "2026-09-22T12:00:00Z",
            "items": [{
                "position": 1,
                "title": "企业 AI 客服评估",
                "source_url": "https://www.bilibili.com/video/reopen-1",
                "snippet": "索引摘要：企业正在评估 AI 客服解决方案。",
            }],
        }
        proof_payload = {
            "proof_ref": "proof-reopen-001",
            "provider": "licensed-search-index",
            "source_family": "social_platform",
            "endpoint": "https://provider.example/search",
            "artifact_sha256": "c" * 64,
            "checked_at": "2026-09-22T11:00:00Z",
            "checks": {
                "terms_and_robots": True,
                "rate_limit": True,
                "published_at": True,
                "url_reopen": True,
                "save_boundary": True,
                "retry_idempotency": True,
            },
        }
        status, registered = self.request(
            "POST",
            "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/source-proofs",
            proof_payload,
        )
        self.assertEqual(status, 201)
        self.assertTrue(registered["created"])
        status, indexed = self.request("POST", f"/api/v1/tasks/{task['id']}/index-results", index_payload)
        self.assertEqual(status, 201)
        opportunity_id = indexed["items"][0]["item"]["id"]
        capture = {
            "title": "企业 AI 客服评估原文",
            "snippet": "原文页面：企业正在评估 AI 客服解决方案并寻找落地团队。",
            "content_hash": "b" * 64,
            "byte_length": 2048,
            "requested_url": index_payload["items"][0]["source_url"],
            "final_url": index_payload["items"][0]["source_url"],
            "content_type": "text/html",
            "charset": "utf-8",
            "captured_at": "2026-09-23T00:00:00+00:00",
        }
        with patch("apps.lead_radar.server.fetch_public_page", return_value=capture):
            status, reopened = self.request(
                "POST",
                f"/api/v1/opportunities/{opportunity_id}/reopen",
                {},
                {"Idempotency-Key": "index-reopen-001"},
            )
        self.assertEqual(status, 200)
        self.assertEqual(reopened["reopen"]["source_kind"], "search_index_snippet")
        self.assertFalse(reopened["reopen"]["reopen_required"])
        self.assertTrue(reopened["reopen"]["keeps_review"])
        self.assertEqual(reopened["opportunity"]["status"], "REVIEW")
        self.assertEqual(reopened["opportunity"]["decision"]["code"], "REOPENED_SOURCE_NEEDS_REVIEW")
        self.assertEqual(reopened["opportunity"]["evidence"][-1]["evidence_type"], "reopen_check")
        metadata = reopened["opportunity"]["evidence"][-1]["metadata"]
        self.assertEqual(metadata["reopen_from_source_kind"], "search_index_snippet")
        self.assertEqual(metadata["proof_ref"], "proof-reopen-001")
        self.assertEqual(metadata["content_hash"], "b" * 64)

    def test_duplicate_evidence_is_recorded_without_double_counting(self) -> None:
        _, task = self.request("POST", "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks", {"objective": "寻找 AI 知识库项目"})
        item = {"title": "企业知识库需求", "source_url": "https://example.com/knowledge", "snippet": "需要内部知识库问答系统。"}
        path = f"/api/v1/tasks/{task['id']}/opportunities"
        _, first = self.request("POST", path, item)
        _, second = self.request("POST", path, item)
        self.assertEqual(first["created_count"], 1)
        self.assertEqual(second["deduplicated_count"], 1)
        _, dashboard = self.request("GET", "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/dashboard")
        self.assertEqual(dashboard["opportunities"], 1)
        self.assertEqual(dashboard["credits_used"], 0)

    def test_controlled_public_url_capture_creates_review_evidence(self) -> None:
        _, task = self.request("POST", "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks", {"objective": "验证公开网页证据"})
        capture = {
            "title": "公开页面标题",
            "snippet": "页面正文中出现了企业寻找 AI 客服定制团队的需求描述。",
            "content_hash": "a" * 64,
            "byte_length": 1234,
            "requested_url": "https://example.com/request",
            "final_url": "https://example.com/request",
            "content_type": "text/html",
            "charset": "utf-8",
            "captured_at": "2026-09-22T00:00:00+00:00",
        }
        with patch("apps.lead_radar.server.fetch_public_page", return_value=capture):
            status, result = self.request("POST", f"/api/v1/tasks/{task['id']}/capture-url", {"url": capture["requested_url"], "intent_type": "定制开发"}, {"Idempotency-Key": "capture-001"})
        self.assertEqual(status, 201)
        self.assertTrue(result["created"])
        self.assertEqual(result["item"]["status"], "REVIEW")
        self.assertEqual(result["item"]["source_kind"], "public_url_capture")
        self.assertEqual(result["item"]["decision"]["code"], "CAPTURED_PAGE_NEEDS_REVIEW")
        self.assertEqual(result["item"]["evidence"][0]["metadata"]["content_hash"], "a" * 64)
        self.assertEqual(result["item"]["evidence"][0]["metadata"]["source_provenance"]["platform"], "web")
        with patch("apps.lead_radar.server.fetch_public_page", return_value=capture):
            status, reopened = self.request("POST", f"/api/v1/opportunities/{result['item']['id']}/reopen", {}, {"Idempotency-Key": "reopen-001"})
        self.assertEqual(status, 200)
        self.assertTrue(reopened["reopen"]["matches_previous_snapshot"])
        self.assertEqual(len(reopened["opportunity"]["evidence"]), 2)
        self.assertEqual(reopened["opportunity"]["evidence"][-1]["evidence_type"], "reopen_check")
        _, dashboard = self.request("GET", "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/dashboard")
        self.assertEqual(dashboard["credits_used"], 2)

    def test_html_capture_excludes_script_content(self) -> None:
        document = extract_document("<html><title>需求页</title><script>secret-noise</script><p>需要企业 AI 客服。</p></html>".encode("utf-8"))
        self.assertEqual(document["title"], "需求页")
        self.assertIn("需要企业 AI 客服", document["snippet"])
        self.assertNotIn("secret-noise", document["snippet"])

    def test_conservative_entity_resolution_links_same_host_and_keeps_different_hosts_separate(self) -> None:
        _, task = self.request("POST", "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks", {"objective": "寻找 AI 定制开发需求"})
        path = f"/api/v1/tasks/{task['id']}/opportunities"
        common = {
            "entity_name": "星河科技",
            "title": "企业 AI 客服采购讨论",
            "snippet": "明确寻找 AI 客服定制开发团队。",
            "source_permission": "allowed",
            "evidence_level": "VERIFIED",
        }
        _, first = self.request("POST", path, {**common, "source_url": "https://xinghe.example/brief-a"})
        _, second = self.request("POST", path, {**common, "title": "星河科技知识库需求", "source_url": "https://xinghe.example/brief-b"})
        _, different_host = self.request("POST", path, {**common, "source_url": "https://xinghe-ai.example/brief-c"})

        first_entity = first["items"][0]["entities"][0]
        second_entity = second["items"][0]["entities"][0]
        different_entity = different_host["items"][0]["entities"][0]
        self.assertEqual(first_entity["id"], second_entity["id"])
        self.assertEqual(first_entity["canonical_name"], "星河科技")
        self.assertEqual(first_entity["website_host"], "xinghe.example")
        self.assertEqual(first_entity["resolution_status"], "EXPLICIT_NAME_AND_HOST")
        self.assertNotEqual(first_entity["id"], different_entity["id"])
        self.assertEqual(different_entity["website_host"], "xinghe-ai.example")

    def test_title_or_social_account_alone_does_not_create_organization(self) -> None:
        _, task = self.request("POST", "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks", {"objective": "寻找公开 AI 需求"})
        path = f"/api/v1/tasks/{task['id']}/opportunities"
        _, result = self.request(
            "POST",
            path,
            {
                "title": "某账号发布 AI 客服需求",
                "author": "某账号",
                "source_url": "https://www.xiaohongshu.com/explore/abc",
                "snippet": "想了解企业 AI 客服定制开发方案。",
            },
        )
        self.assertEqual(result["items"][0]["entities"], [])

    def test_manual_entity_merge_and_split_keep_opportunity_links_auditable(self) -> None:
        _, task = self.request("POST", "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks", {"objective": "寻找企业 AI 项目"})
        path = f"/api/v1/tasks/{task['id']}/opportunities"
        base = {"title": "AI 项目线索", "snippet": "寻找 AI 定制开发团队。", "source_permission": "allowed", "evidence_level": "VERIFIED"}
        _, left = self.request("POST", path, {**base, "entity_name": "甲公司", "source_url": "https://jia.example/a"})
        _, right = self.request("POST", path, {**base, "title": "AI 项目线索 2", "entity_name": "乙公司", "source_url": "https://yi.example/b"})
        left_id = left["items"][0]["entities"][0]["id"]
        right_id = right["items"][0]["entities"][0]["id"]
        right_opportunity_id = right["items"][0]["id"]

        status, merged = self.request(
            "POST",
            f"/api/v1/entities/{right_id}/merge",
            {"target_entity_id": left_id, "reason": "人工核对官网和工商名称一致", "actor": "qa"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(merged["id"], left_id)
        self.assertEqual(len(merged["opportunities"]), 2)

        status, split = self.request(
            "POST",
            f"/api/v1/entities/{left_id}/split",
            {"opportunity_id": right_opportunity_id, "entity_name": "乙公司（拆分后）", "website_host": "yi.example", "reason": "复核发现属于另一家公司", "actor": "qa"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(split["canonical_name"], "乙公司（拆分后）")
        self.assertEqual(split["opportunities"][0]["id"], right_opportunity_id)

        status, entity_detail = self.request("GET", f"/api/v1/entities/{left_id}")
        self.assertEqual(status, 200)
        self.assertEqual(len(entity_detail["opportunities"]), 1)
        status, entities = self.request("GET", "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/entities")
        self.assertEqual(status, 200)
        self.assertEqual(len(entities["items"]), 2)

    def test_batch_public_url_capture_is_partial_and_idempotently_billed(self) -> None:
        _, task = self.request("POST", "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks", {"objective": "批量导入公开需求"})

        def fake_capture(url: str) -> dict:
            if "bad" in url:
                raise CaptureError("fetch_failed", "测试页面不可用")
            return {
                "title": "批量公开需求",
                "snippet": "需要企业 AI 客服定制开发团队。",
                "content_hash": "b" * 64,
                "byte_length": 256,
                "requested_url": url,
                "final_url": url,
                "content_type": "text/html",
                "charset": "utf-8",
                "captured_at": "2026-09-22T00:00:00+00:00",
            }

        path = f"/api/v1/tasks/{task['id']}/capture-urls"
        with patch("apps.lead_radar.server.fetch_public_page", side_effect=fake_capture):
            status, first = self.request("POST", path, {"items": [{"url": "https://batch.example/one", "entity_name": "批量企业"}, {"url": "https://bad.example/two"}]})
            status, second = self.request("POST", path, {"urls": ["https://batch.example/one"]})
        self.assertEqual(status, 200)
        self.assertEqual(first["created_count"], 1)
        self.assertEqual(first["failed_count"], 1)
        self.assertEqual(first["errors"][0]["error"], "fetch_failed")
        self.assertEqual(second["items"][0]["created"], False)
        _, dashboard = self.request("GET", "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/dashboard")
        self.assertEqual(dashboard["opportunities"], 1)
        self.assertEqual(dashboard["credits_used"], 1)

    def test_authorized_search_connector_executes_only_after_proof_gate(self) -> None:
        result_item = {
            "title": "授权搜索返回的 AI 客服需求",
            "source_url": "https://buyer.example/request/1",
            "snippet": "企业正在寻找 AI 客服定制开发团队。",
            "entity_name": "买方科技",
            "id": "provider-result-1",
        }
        with patch.dict(
            os.environ,
            {**PROOF_ENV,
                "LEAD_RADAR_SEARCH_ENDPOINT": "https://search.example/api/search",
                "LEAD_RADAR_SEARCH_TOKEN": "test-token",
                "LEAD_RADAR_SEARCH_REOPEN_PROOF": "true",
            },
        ), patch("apps.lead_radar.server.AuthorizedSearchConnector.search", return_value=[{
            "title": result_item["title"],
            "source_url": result_item["source_url"],
            "snippet": result_item["snippet"],
            "entity_name": result_item["entity_name"],
            "source_kind": "authorized_search_api",
            "evidence_level": "PROVIDER_ATTESTED",
            "source_permission": "authorized_api",
            "evidence_type": "authorized_search_result",
            "evidence_metadata": {"provider": "test", "provider_result_id": result_item["id"]},
        }]):
            status, task = self.request(
                "POST",
                "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks",
                {"objective": "授权搜索 AI 客服需求", "criteria": {"sources": ["authorized_search_api"]}},
            )
            self.assertEqual(status, 201)
            self.assertEqual(task["plan"]["execution"]["status"], "READY")
            status, executed = self.request("POST", f"/api/v1/tasks/{task['id']}/execute", {"mode": "quick"})
        self.assertEqual(status, 200)
        self.assertEqual(executed["created_count"], 1)
        self.assertEqual(executed["candidate_count"], 1)
        self.assertEqual(executed["task"]["runs"][0]["status"], "COMPLETED")
        self.assertEqual(executed["task"]["runs"][0]["events"][-1]["event_type"], "completed")
        self.assertEqual(executed["task"]["runs"][0]["events"][1]["event_type"], "started")
        self.assertEqual(executed["task"]["status"], "COMPLETED")

    def test_authorized_search_execution_failure_is_recorded_and_retryable(self) -> None:
        with patch.dict(
            os.environ,
            {**PROOF_ENV,
                "LEAD_RADAR_SEARCH_ENDPOINT": "https://search.example/api/search",
                "LEAD_RADAR_SEARCH_TOKEN": "test-token",
                "LEAD_RADAR_SEARCH_REOPEN_PROOF": "true",
            },
        ), patch("apps.lead_radar.server.AuthorizedSearchConnector.search", side_effect=SearchConnectorError("provider_unavailable", "测试服务不可用", retryable=True)):
            _, task = self.request(
                "POST",
                "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks",
                {"objective": "授权搜索失败重试", "criteria": {"sources": ["authorized_search_api"]}},
            )
            status, failed = self.request("POST", f"/api/v1/tasks/{task['id']}/execute", {"mode": "quick"})
        self.assertEqual(status, 502)
        self.assertEqual(failed["error"], "provider_unavailable")
        self.assertEqual(failed["task"]["runs"][0]["status"], "FAILED")
        self.assertEqual(failed["task"]["runs"][0]["events"][-1]["event_type"], "failed")

    def test_calibration_batch_freezes_predictions_and_computes_quality_metrics(self) -> None:
        _, task = self.request(
            "POST",
            "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks",
            {"objective": "校准真实 AI 需求候选"},
        )
        path = f"/api/v1/tasks/{task['id']}/opportunities"
        _, valid = self.request(
            "POST",
            path,
            {
                "title": "误报候选",
                "source_url": "https://calibration.example/false-positive",
                "snippet": "这是一条经过授权但人工判定无效的样本。",
                "source_permission": "allowed",
                "evidence_level": "VERIFIED",
            },
        )
        _, unverified = self.request(
            "POST",
            path,
            {
                "title": "漏报候选",
                "source_url": "https://calibration.example/false-negative",
                "snippet": "这是一条未经系统确认但人工判定有效的样本。",
            },
        )
        _, captured = self.request(
            "POST",
            path,
            {
                "title": "公开页面候选",
                "source_url": "https://calibration.example/captured",
                "snippet": "公开页面候选，等待复核。",
                "source_kind": "public_url_capture",
                "source_permission": "public_url_user_supplied",
                "evidence_level": "CAPTURED",
            },
        )
        valid_id = valid["items"][0]["id"]
        unverified_id = unverified["items"][0]["id"]
        captured_id = captured["items"][0]["id"]
        self.server.store.append_evidence(
            captured_id,
            "reopen_check",
            "重开核验快照",
            "https://calibration.example/captured",
            {"matches_previous_snapshot": True},
        )

        status, created = self.request(
            "POST",
            "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/calibration-batches",
            {"name": "首批真实候选校准", "target_count": 3, "opportunity_ids": [valid_id, unverified_id, captured_id]},
        )
        self.assertEqual(status, 201)
        self.assertEqual(created["metrics"]["item_count"], 3)
        self.assertEqual(created["metrics"]["reviewed_count"], 0)
        self.assertEqual(created["coverage"], 1.0)
        self.assertEqual([item["predicted_label"] for item in created["items"]], ["VALID", "NEEDS_EVIDENCE", "NEEDS_EVIDENCE"])
        self.assertEqual(created["metrics"]["reopen_rate"], 1.0)

        for item_id, label in zip(
            [item["id"] for item in created["items"]],
            ["INVALID", "VALID", "NEEDS_EVIDENCE"],
        ):
            status, reviewed = self.request(
                "POST",
                f"/api/v1/calibration-batches/{created['id']}/items/{item_id}/review",
                {"gold_label": label, "reviewer": "qa", "note": "校准记录"},
            )
            self.assertEqual(status, 200)

        self.assertEqual(reviewed["metrics"]["reviewed_count"], 3)
        self.assertEqual(reviewed["metrics"]["agreement_count"], 1)
        self.assertEqual(reviewed["metrics"]["accuracy"], 0.3333)
        self.assertEqual(reviewed["metrics"]["false_positive_count"], 1)
        self.assertEqual(reviewed["metrics"]["false_negative_count"], 1)
        self.assertEqual(reviewed["metrics"]["reopen_rate"], 1.0)
        self.assertEqual(reviewed["items"][0]["gold_label"], "INVALID")

        status, batches = self.request(
            "GET",
            "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/calibration-batches",
        )
        self.assertEqual(status, 200)
        self.assertEqual(batches["items"][0]["metrics"]["false_positive_count"], 1)
        self.assertEqual(self.server.store.get_opportunity(valid_id)["status"], "EXCLUDE")
        self.assertEqual(self.server.store.get_opportunity(unverified_id)["status"], "SEND_READY")

    def test_calibration_contract_rejects_ambiguous_inputs(self) -> None:
        _, task = self.request(
            "POST",
            "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks",
            {"objective": "校准输入校验"},
        )
        _, opportunity = self.request(
            "POST",
            f"/api/v1/tasks/{task['id']}/opportunities",
            {
                "title": "校准输入样本",
                "source_url": "https://calibration.example/validation",
                "snippet": "公开需求样本。",
            },
        )
        opportunity_id = opportunity["items"][0]["id"]
        batch_path = "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/calibration-batches"

        status, result = self.request("POST", batch_path, {"target_count": 0})
        self.assertEqual(status, 400)
        self.assertIn("out_of_range", result["message"])
        status, result = self.request("POST", batch_path, {"target_count": 1, "opportunity_ids": [opportunity_id, opportunity_id]})
        self.assertEqual(status, 400)
        self.assertIn("must_be_unique", result["message"])
        status, batch = self.request("POST", batch_path, {"target_count": 1, "opportunity_ids": [opportunity_id]})
        self.assertEqual(status, 201)
        item_id = batch["items"][0]["id"]
        review_path = f"/api/v1/calibration-batches/{batch['id']}/items/{item_id}/review"

        status, result = self.request("POST", review_path, {"gold_label": "NOT_A_LABEL"})
        self.assertEqual(status, 400)
        self.assertIn("invalid_calibration_gold_label", result["message"])
        status, result = self.request("POST", review_path, {"gold_label": "VALID", "apply_feedback": "false"})
        self.assertEqual(status, 400)
        self.assertIn("apply_feedback_must_be_boolean", result["message"])

    def test_action_drafts_are_evidence_bound_idempotent_and_never_sent(self) -> None:
        _, task = self.request(
            "POST",
            "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks",
            {"objective": "生成 AI 客服商机动作草案"},
        )
        path = f"/api/v1/tasks/{task['id']}/opportunities"
        _, created = self.request(
            "POST",
            path,
            {
                "title": "动作草案候选",
                "source_url": "https://action.example/request",
                "snippet": "企业公开表达需要 AI 客服定制开发团队。",
                "intent_type": "定制开发",
                "source_permission": "allowed",
                "evidence_level": "VERIFIED",
            },
        )
        opportunity_id = created["items"][0]["id"]
        draft_path = f"/api/v1/opportunities/{opportunity_id}/action-drafts"
        status, drafts = self.request(
            "POST",
            draft_path,
            {"channels": ["PUBLIC_REPLY", "EMAIL", "FEISHU_TASK", "CRM_TASK"], "actor": "qa"},
            {"Idempotency-Key": "action-draft-request-1"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(drafts["count"], 4)
        self.assertTrue(all(item["status"] == "DRAFT" for item in drafts["items"]))
        self.assertTrue(all(item["evidence_ids"] for item in drafts["items"]))
        self.assertTrue(all("尚未发送" not in item["body"] for item in drafts["items"]))

        status, retry = self.request(
            "POST",
            draft_path,
            {"channels": ["PUBLIC_REPLY", "EMAIL", "FEISHU_TASK", "CRM_TASK"], "actor": "qa"},
            {"Idempotency-Key": "action-draft-request-1"},
        )
        self.assertEqual(status, 200)
        self.assertEqual({item["id"] for item in retry["items"]}, {item["id"] for item in drafts["items"]})

        draft_id = drafts["items"][0]["id"]
        status, rejected = self.request("POST", f"/api/v1/action-drafts/{draft_id}/approve", {"confirm": False})
        self.assertEqual(status, 400)
        self.assertIn("explicit_confirmation_required", rejected["message"])
        status, approved = self.request("POST", f"/api/v1/action-drafts/{draft_id}/approve", {"confirm": True, "actor": "qa"})
        self.assertEqual(status, 200)
        self.assertEqual(approved["draft"]["status"], "APPROVED")
        self.assertFalse(approved["sent"])
        self.assertIn("尚未发送", approved["message"])

        status, listed = self.request("GET", draft_path)
        self.assertEqual(status, 200)
        self.assertEqual({item["status"] for item in listed["items"]}, {"DRAFT", "APPROVED"})
        status, detail = self.request("GET", f"/api/v1/opportunities/{opportunity_id}")
        self.assertEqual(status, 200)
        self.assertEqual(len(detail["action_drafts"]), 4)
        self.assertEqual(detail["audit_events"][-1]["action"], "action_draft_approved")

        _, review_only = self.request(
            "POST",
            path,
            {"title": "尚未就绪", "source_url": "https://action.example/review", "snippet": "只有公开片段。"},
        )
        status, blocked = self.request(
            "POST",
            f"/api/v1/opportunities/{review_only['items'][0]['id']}/action-drafts",
            {"channels": ["EMAIL"]},
        )
        self.assertEqual(status, 400)
        self.assertIn("opportunity_not_send_ready", blocked["message"])


if __name__ == "__main__":
    unittest.main()
