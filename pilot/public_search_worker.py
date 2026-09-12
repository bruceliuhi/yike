"""Isolated stdlib-only Serper search worker."""
from __future__ import annotations

import http.client
import ipaddress
import json
import re
import ssl
import sys
from datetime import datetime, timezone
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit

ENDPOINT_HOST = "google.serper.dev"
MAX_BODY_BYTES = 1024 * 1024
MAX_INPUT_BYTES = 16 * 1024
_CODES = {"unavailable", "auth_failed", "rate_limited", "timeout", "too_large", "invalid_search_result"}
_CREDENTIAL_KEYS = {
    "apikey", "accesskey", "accesskeyid", "secretkey", "secretaccesskey",
    "clientsecret", "credential", "credentials", "authorization", "auth",
    "token", "accesstoken", "refreshtoken", "idtoken", "password", "passwd",
    "pwd", "cookie", "session", "sessionid", "signature", "sig",
}


class WorkerError(RuntimeError):
    def __init__(self, code: str):
        self.code = code if code in _CODES else "unavailable"
        super().__init__(self.code)


def _text(value, limit: int):
    if value is None:
        return None
    if type(value) is not str:
        raise WorkerError("invalid_search_result")
    normalized = " ".join(value.split())
    return normalized[:limit] or None


def _safe_url(value):
    if type(value) is not str or len(value) > 2048:
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme.lower() != "https" or parts.port not in (None, 443) or parts.username or parts.password:
            return None
        host = (parts.hostname or "").rstrip(".").lower().encode("idna").decode("ascii")
        if not host or host == "localhost" or host.endswith(".localhost"):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            pass
        for key, _value in parse_qsl(parts.query, keep_blank_values=True):
            token = re.sub(r"[^a-z0-9]", "", key.lower())
            if token in _CREDENTIAL_KEYS or token.startswith("x") and token[1:] in _CREDENTIAL_KEYS:
                return None
        authority = f"[{host}]" if ":" in host else host
        path = quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~")
        query = quote(parts.query, safe="=&?/:@!$'()*+,;%-._~")
        return urlunsplit(("https", authority, path, query, ""))
    except (UnicodeError, ValueError):
        return None


def _read_body(response) -> bytes:
    length = response.getheader("Content-Length")
    if length is not None:
        try:
            expected = int(length)
        except ValueError:
            raise WorkerError("unavailable") from None
        if expected < 0:
            raise WorkerError("unavailable")
        if expected > MAX_BODY_BYTES:
            raise WorkerError("too_large")
    else:
        expected = None
    try:
        body = response.read(MAX_BODY_BYTES + 1)
    except (OSError, http.client.HTTPException):
        raise WorkerError("unavailable") from None
    if len(body) > MAX_BODY_BYTES:
        raise WorkerError("too_large")
    if expected is not None and len(body) != expected:
        raise WorkerError("unavailable")
    return body


def search_request(request: dict) -> dict:
    try:
        query = request["query"]
        api_key = request["api_key"]
        timeout = float(request["timeout_seconds"])
        if type(query) is not str or type(api_key) is not str or not api_key or not 0 < timeout <= 20:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise WorkerError("unavailable") from None
    connection = None
    try:
        connection = http.client.HTTPSConnection(ENDPOINT_HOST, 443, timeout=timeout, context=ssl.create_default_context())
        payload = json.dumps({"q": query, "num": 10, "hl": "zh-cn"}, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")
        connection.request("POST", "/search", payload, {
            "Content-Type": "application/json", "Accept": "application/json",
            "X-API-KEY": api_key, "Connection": "close", "User-Agent": "YikePublicSearch/1",
        })
        response = connection.getresponse()
        if response.status in (401, 403):
            raise WorkerError("auth_failed")
        if response.status == 429:
            raise WorkerError("rate_limited")
        if response.status != 200:
            raise WorkerError("unavailable")
        body = _read_body(response)
        try:
            document = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise WorkerError("invalid_search_result") from None
    except WorkerError:
        raise
    except TimeoutError:
        raise WorkerError("timeout") from None
    except (OSError, ssl.SSLError, http.client.HTTPException):
        raise WorkerError("unavailable") from None
    finally:
        if connection is not None:
            connection.close()
    if type(document) is not dict or type(document.get("organic")) is not list:
        raise WorkerError("invalid_search_result")
    organic = document["organic"]
    results = []
    seen = set()
    for index, raw in enumerate(organic):
        if type(raw) is not dict:
            raise WorkerError("invalid_search_result")
        url = _safe_url(raw.get("link"))
        if url is None or url in seen:
            continue
        seen.add(url)
        if len(results) >= 10:
            continue
        position = raw.get("position")
        rank = position if type(position) is int and position > 0 else index + 1
        results.append({"url": url, "title": _text(raw.get("title"), 1000),
                        "snippet": _text(raw.get("snippet"), 2000),
                        "date_hint": _text(raw.get("date"), 200), "rank": rank})
    return {"query": query, "observed_at": datetime.now(timezone.utc).isoformat(),
            "read_scope": "SEARCH_RESULTS", "results": results,
            "omitted_count": len(organic) - len(results)}


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise WorkerError("unavailable")
        request = json.loads(raw.decode("utf-8"))
        if type(request) is not dict:
            raise WorkerError("unavailable")
        message = {"ok": True, "result": search_request(request)}
    except WorkerError as error:
        message = {"ok": False, "code": error.code}
    except Exception:
        message = {"ok": False, "code": "unavailable"}
    sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
