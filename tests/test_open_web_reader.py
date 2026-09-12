from __future__ import annotations

import hashlib
import io
import json
import socket
import ssl
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from pilot import open_web_reader_worker as worker
from pilot.open_web_reader import PublicReadError, normalize_public_url, read_public_page


class FakeSocket:
    def __init__(self, response: bytes):
        self.response = io.BytesIO(response)
        self.sent = b""

    def sendall(self, value: bytes):
        self.sent += value

    def makefile(self, mode: str):
        assert mode == "rb"
        return self.response

    def settimeout(self, value: float):
        assert value > 0

    def close(self):
        pass


def response(body: bytes, content_type="text/html; charset=utf-8", status="200 OK", extra=""):
    return (f"HTTP/1.1 {status}\r\nContent-Type: {content_type}\r\nContent-Length: {len(body)}\r\n{extra}\r\n".encode() + body)


def install_transport(monkeypatch, payload: bytes, addresses=("93.184.216.34",)):
    raw = FakeSocket(payload)
    seen = {}
    monkeypatch.setattr(worker.socket, "getaddrinfo", lambda *a, **k: [
        (socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443, 0, 0) if ":" in ip else (ip, 443))
        for ip in addresses
    ])
    monkeypatch.setattr(worker.socket, "create_connection", lambda address, timeout: seen.setdefault("address", address) and raw)

    class Context:
        def wrap_socket(self, sock, *, server_hostname):
            seen["server_hostname"] = server_hostname
            return sock

    monkeypatch.setattr(worker.ssl, "create_default_context", Context)
    return raw, seen


def test_html_extraction_hash_and_tls_hostname_with_pinned_ip(monkeypatch):
    body = b"<html><head><title> A title </title><script>bad()</script></head><body>Hello <b>world</b><div hidden>secret</div><p style='display:none'>nope</p></body></html>"
    raw, seen = install_transport(monkeypatch, response(body))
    result = worker.read_request({"url": "https://never-enumerated.example/path?q=1", "timeout_seconds": 3})
    assert result["url"] == "https://never-enumerated.example/path?q=1"
    assert result["title"] == "A title"
    assert result["text"] == "Hello world"
    assert result["content_sha256"] == hashlib.sha256(b"Hello world").hexdigest()
    assert result["read_scope"] == "PUBLIC_PAGE_TEXT"
    assert result["observed_at"].endswith("Z")
    assert seen == {"address": ("93.184.216.34", 443), "server_hostname": "never-enumerated.example"}
    assert raw.sent.startswith(b"GET /path?q=1 HTTP/1.1\r\nHost: never-enumerated.example\r\n")
    assert b"Cookie:" not in raw.sent and b"Authorization:" not in raw.sent


def test_plain_text(monkeypatch):
    install_transport(monkeypatch, response(b"plain\ntext", "text/plain"))
    assert worker.read_request({"url": "https://example.com/", "timeout_seconds": 2})["text"] == "plain\ntext"


@pytest.mark.parametrize("addresses", [("127.0.0.1",), ("93.184.216.34", "10.0.0.2")])
def test_rejects_private_or_mixed_dns(monkeypatch, addresses):
    install_transport(monkeypatch, response(b"ok", "text/plain"), addresses)
    with pytest.raises(worker.WorkerError) as error:
        worker.read_request({"url": "https://example.com/", "timeout_seconds": 2})
    assert error.value.code == "invalid_url"


def test_refuses_redirect(monkeypatch):
    install_transport(monkeypatch, response(b"", status="302 Found", extra="Location: https://example.org/\r\n"))
    with pytest.raises(worker.WorkerError) as error:
        worker.read_request({"url": "https://example.com/", "timeout_seconds": 2})
    assert error.value.code == "unavailable"


@pytest.mark.parametrize("payload", [
    response(b"x" * (worker.MAX_BODY_BYTES + 1), "text/plain"),
    response(("界" * (worker.MAX_TEXT_CHARS + 1)).encode(), "text/plain"),
])
def test_body_and_decoded_text_bounds(monkeypatch, payload):
    install_transport(monkeypatch, payload)
    with pytest.raises(worker.WorkerError) as error:
        worker.read_request({"url": "https://example.com/", "timeout_seconds": 2})
    assert error.value.code == "too_large"


@pytest.mark.parametrize("payload", [
    response(b"\xff", "text/plain; charset=utf-8"),
    response(b"hello", "text/plain; charset=latin-1"),
    response(b"%PDF", "application/pdf"),
])
def test_invalid_utf8_charset_and_content_are_unsupported(monkeypatch, payload):
    install_transport(monkeypatch, payload)
    with pytest.raises(worker.WorkerError) as error:
        worker.read_request({"url": "https://example.com/", "timeout_seconds": 2})
    assert error.value.code == "unsupported_content"


def test_parent_requires_aware_deadline():
    with pytest.raises(PublicReadError) as error:
        read_public_page("https://example.com/", deadline=datetime.now())
    assert error.value.code == "invalid_url"


def test_url_normalization_uses_candidate_idna_contract_and_ascii_request_target():
    assert normalize_public_url("https://faß.de:443/需求?q=公开#section") == (
        "https://xn--fa-hia.de/%E9%9C%80%E6%B1%82?q=%E5%85%AC%E5%BC%80"
    )


def test_parent_maps_worker_result_exactly(monkeypatch):
    expected = {"url": "https://example.com/", "title": None, "text": "ok", "observed_at": "2026-09-12T01:02:03Z", "content_sha256": hashlib.sha256(b"ok").hexdigest(), "read_scope": "PUBLIC_PAGE_TEXT"}

    class Process:
        returncode = 0
        def communicate(self, data, timeout):
            request = json.loads(data)
            assert request["url"] == expected["url"] and 0 < request["timeout_seconds"] <= 20
            return json.dumps({"ok": True, "result": expected}), ""

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: Process())
    assert read_public_page(expected["url"], deadline=datetime.now(timezone.utc) + timedelta(seconds=30)) == expected


def test_native_dns_timeout_kills_and_reaps_worker(monkeypatch):
    events = []

    class Process:
        returncode = None
        def communicate(self, data, timeout):
            events.append(("communicate", timeout))
            raise subprocess.TimeoutExpired("worker", timeout)
        def kill(self):
            events.append("kill")
        def wait(self, timeout=None):
            events.append("wait")
            self.returncode = -9

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: Process())
    with pytest.raises(PublicReadError) as error:
        read_public_page("https://example.com/", deadline=datetime.now(timezone.utc) + timedelta(seconds=1))
    assert error.value.code == "timeout"
    assert events[-2:] == ["kill", "wait"]
