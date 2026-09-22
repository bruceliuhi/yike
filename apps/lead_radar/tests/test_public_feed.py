from __future__ import annotations

import json
import tempfile
import threading
import unittest
from email.message import Message
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from apps.lead_radar.capture import CaptureError, fetch_public_feed
from apps.lead_radar.server import create_server


RSS_BODY = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>公开需求 Feed</title>
  <item><guid>one</guid><title>企业寻找 AI 客服团队</title><link>https://source.example/one</link><description><![CDATA[正在评估 <b>AI 客服</b> 定制开发。]]></description><pubDate>Tue, 22 Sep 2026 10:00:00 GMT</pubDate></item>
  <item><guid>two</guid><title>知识库采购讨论</title><link>/two</link><description>需要企业知识库落地团队。</description><pubDate>Tue, 23 Sep 2026 10:00:00 GMT</pubDate></item>
</channel></rss>""".encode("utf-8")


class FakeResponse:
    def __init__(self, body: bytes, content_type: str = "application/rss+xml") -> None:
        self._body = body
        self.headers = Message()
        self.headers["Content-Type"] = f"{content_type}; charset=utf-8"

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self) -> str:
        return "https://source.example/feed.xml"

    def read(self, _size: int = -1) -> bytes:
        return self._body


class FakeOpener:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    def open(self, _request, timeout: int):
        self.timeout = timeout
        return self.response


class PublicFeedCaptureTest(unittest.TestCase):
    def test_rss_parser_preserves_links_dates_and_hashes_without_original_xml(self) -> None:
        with patch("apps.lead_radar.capture.build_opener", return_value=FakeOpener(FakeResponse(RSS_BODY))), patch(
            "apps.lead_radar.capture.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 443))],
        ):
            feed = fetch_public_feed("https://source.example/feed.xml", 2)
        self.assertEqual(feed["feed_title"], "公开需求 Feed")
        self.assertEqual(len(feed["entries"]), 2)
        self.assertEqual(feed["entries"][0]["source_url"], "https://source.example/one")
        self.assertEqual(feed["entries"][1]["source_url"], "https://source.example/two")
        self.assertIn("AI 客服", feed["entries"][0]["snippet"])
        self.assertNotIn("<b>", feed["entries"][0]["snippet"])
        self.assertEqual(feed["entries"][0]["published_at"], "Tue, 22 Sep 2026 10:00:00 GMT")
        self.assertEqual(len(feed["feed_hash"]), 64)
        self.assertNotIn("body", feed)

    def test_parser_rejects_html_and_external_entity_declarations(self) -> None:
        with patch(
            "apps.lead_radar.capture.build_opener",
            return_value=FakeOpener(FakeResponse(b"<html>not a feed</html>", "text/html")),
        ), patch(
            "apps.lead_radar.capture.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 443))],
        ):
            with self.assertRaises(CaptureError) as error:
                fetch_public_feed("https://source.example/feed.xml")
            self.assertEqual(error.exception.code, "unsupported_feed_content_type")
        unsafe = b'<!DOCTYPE foo [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]><rss><channel /></rss>'
        with patch("apps.lead_radar.capture.build_opener", return_value=FakeOpener(FakeResponse(unsafe))), patch(
            "apps.lead_radar.capture.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 443))],
        ):
            with self.assertRaises(CaptureError) as error:
                fetch_public_feed("https://source.example/feed.xml")
            self.assertEqual(error.exception.code, "unsafe_xml")

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.server = create_server("127.0.0.1", 0, str(Path(self.tempdir.name) / "feed.sqlite3"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server.store.close()
        self.tempdir.cleanup()

    def request(self, method: str, path: str, payload: dict | None = None, headers: dict | None = None):
        connection = HTTPConnection(self.host, self.port)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        connection.request(method, path, body=body, headers={"Content-Type": "application/json; charset=utf-8", **(headers or {})})
        response = connection.getresponse()
        result = json.loads(response.read().decode("utf-8"))
        connection.close()
        return response.status, result

    def test_feed_endpoint_creates_review_candidates_and_deduplicates_retries(self) -> None:
        status, task = self.request(
            "POST",
            "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks",
            {"objective": "公开 Feed 需求采集"},
        )
        self.assertEqual(status, 201)
        feed = {
            "requested_url": "https://source.example/feed.xml",
            "final_url": "https://source.example/feed.xml",
            "feed_title": "公开需求 Feed",
            "feed_hash": "f" * 64,
            "byte_length": len(RSS_BODY),
            "content_type": "application/rss+xml",
            "charset": "utf-8",
            "captured_at": "2026-09-23T00:00:00+00:00",
            "entries": [
                {
                    "entry_id": "one",
                    "title": "企业寻找 AI 客服团队",
                    "source_url": "https://source.example/one",
                    "snippet": "正在评估 AI 客服定制开发。",
                    "published_at": "2026-09-22",
                    "content_hash": "1" * 64,
                },
                {
                    "entry_id": "two",
                    "title": "知识库采购讨论",
                    "source_url": "https://source.example/two",
                    "snippet": "需要企业知识库落地团队。",
                    "published_at": "2026-09-23",
                    "content_hash": "2" * 64,
                },
            ],
        }
        path = f"/api/v1/tasks/{task['id']}/capture-feed"
        with patch("apps.lead_radar.server.fetch_public_feed", return_value=feed):
            status, first = self.request("POST", path, {"url": feed["requested_url"], "limit": 2})
            self.assertEqual(status, 201)
            self.assertEqual(first["created_count"], 2)
            self.assertEqual(first["items"][0]["item"]["source_kind"], "public_feed_capture")
            self.assertEqual(first["items"][0]["item"]["decision"]["code"], "CAPTURED_FEED_NEEDS_REVIEW")
            self.assertEqual(first["items"][0]["item"]["evidence"][0]["metadata"]["feed_hash"], "f" * 64)
            status, second = self.request("POST", path, {"url": feed["requested_url"], "limit": 2})
        self.assertEqual(status, 201)
        self.assertEqual(second["created_count"], 0)
        self.assertEqual(second["deduplicated_count"], 2)
        status, dashboard = self.request("GET", "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/dashboard")
        self.assertEqual(status, 200)
        self.assertEqual(dashboard["opportunities"], 2)
        self.assertEqual(dashboard["credits_used"], 2)

    def test_feed_candidates_can_reopen_the_original_entry(self) -> None:
        _, task = self.request(
            "POST",
            "/api/v1/workspaces/ws_%E6%84%8F%E5%AE%A2AI/tasks",
            {"objective": "公开 Feed 重开"},
        )
        feed = {
            "requested_url": "https://source.example/feed.xml",
            "final_url": "https://source.example/feed.xml",
            "feed_title": "Feed",
            "feed_hash": "a" * 64,
            "byte_length": 10,
            "content_type": "application/rss+xml",
            "charset": "utf-8",
            "captured_at": "2026-09-23T00:00:00+00:00",
            "entries": [
                {"entry_id": "one", "title": "公开需求", "source_url": "https://source.example/one", "snippet": "AI 客服需求", "published_at": "2026-09-23", "content_hash": "1" * 64}
            ],
        }
        path = f"/api/v1/tasks/{task['id']}/capture-feed"
        with patch("apps.lead_radar.server.fetch_public_feed", return_value=feed):
            _, created = self.request("POST", path, {"url": feed["requested_url"]})
        opportunity_id = created["items"][0]["item"]["id"]
        capture = {
            "title": "公开需求",
            "snippet": "AI 客服需求",
            "content_hash": "1" * 64,
            "byte_length": 100,
            "requested_url": "https://source.example/one",
            "final_url": "https://source.example/one",
            "content_type": "text/html",
            "charset": "utf-8",
            "captured_at": "2026-09-23T00:00:01+00:00",
        }
        with patch("apps.lead_radar.server.fetch_public_page", return_value=capture):
            status, reopened = self.request(
                "POST",
                f"/api/v1/opportunities/{opportunity_id}/reopen",
                {},
                {"Idempotency-Key": "feed-reopen-1"},
            )
        self.assertEqual(status, 200)
        self.assertEqual(reopened["reopen"]["source_kind"], "public_feed_capture")
        self.assertTrue(reopened["reopen"]["matches_previous_snapshot"])
        self.assertEqual(len(reopened["opportunity"]["evidence"]), 2)


if __name__ == "__main__":
    unittest.main()
