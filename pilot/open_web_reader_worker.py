"""Single-request stdlib worker for a DNS-pinned public HTTPS read."""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import re
import socket
import ssl
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit

MAX_BODY_BYTES = 1024 * 1024
MAX_TEXT_CHARS = 60_000
MAX_HEADER_BYTES = 64 * 1024
MAX_TITLE_CHARS = 1000
_HIDDEN_TAGS = {"script", "style", "noscript", "template", "svg", "canvas"}
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class WorkerError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return bool(address.is_global and not address.is_multicast and not address.is_reserved
                and not address.is_loopback and not address.is_link_local
                and not address.is_unspecified and not getattr(address, "is_site_local", False))


class _VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden_depth = 0
        self.title_depth = 0
        self.stack: list[tuple[str, bool, bool]] = []
        self.text_parts: list[str] = []
        self.title_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = {key.lower(): (value or "").lower() for key, value in attrs}
        style = values.get("style", "").replace(" ", "")
        tag = tag.lower()
        hidden = (tag in _HIDDEN_TAGS or "hidden" in values
                  or values.get("aria-hidden") == "true"
                  or "display:none" in style or "visibility:hidden" in style)
        title = tag == "title"
        if hidden:
            self.hidden_depth += 1
        if title:
            self.title_depth += 1
        if tag not in _VOID_TAGS:
            self.stack.append((tag, hidden, title))

    def handle_startendtag(self, tag, attrs):
        return

    def handle_endtag(self, tag):
        tag = tag.lower()
        if not self.stack or self.stack[-1][0] != tag:
            return
        _tag, hidden, title = self.stack.pop()
        if title:
            self.title_depth -= 1
        if hidden:
            self.hidden_depth -= 1

    def handle_data(self, data):
        if self.title_depth:
            self.title_parts.append(data)
        elif not self.hidden_depth:
            self.text_parts.append(data)


def _read_body(response: http.client.HTTPResponse) -> bytes:
    length = response.getheader("Content-Length")
    if length is not None:
        try:
            if int(length) > MAX_BODY_BYTES:
                raise WorkerError("too_large")
        except ValueError:
            raise WorkerError("unavailable") from None
    body = response.read(MAX_BODY_BYTES + 1)
    if len(body) > MAX_BODY_BYTES:
        raise WorkerError("too_large")
    return body


def _decode(body: bytes, content_type: str) -> tuple[str, str | None]:
    media_type, *parameters = content_type.split(";")
    media_type = media_type.strip().lower()
    if media_type not in {"text/html", "text/plain"}:
        raise WorkerError("unsupported_content")
    charset = "utf-8"
    for parameter in parameters:
        key, separator, value = parameter.partition("=")
        if separator and key.strip().lower() == "charset":
            charset = value.strip().strip('"').lower()
    if charset not in {"utf-8", "utf8", "us-ascii", "ascii"}:
        raise WorkerError("unsupported_content")
    try:
        decoded = body.decode("ascii" if charset in {"us-ascii", "ascii"} else "utf-8", errors="strict")
    except UnicodeDecodeError:
        raise WorkerError("unsupported_content") from None
    if media_type == "text/plain":
        text, title = decoded, None
    else:
        parser = _VisibleHTML()
        try:
            parser.feed(decoded)
            parser.close()
        except Exception:
            raise WorkerError("unsupported_content") from None
        text = " ".join(" ".join(parser.text_parts).split())
        title_value = " ".join(" ".join(parser.title_parts).split())
        title = title_value[:MAX_TITLE_CHARS] or None
    if len(text) > MAX_TEXT_CHARS:
        raise WorkerError("too_large")
    return text, title


def read_request(request: dict) -> dict:
    try:
        url = request["url"]
        timeout = float(request["timeout_seconds"])
        parts = urlsplit(url)
        host = parts.hostname or ""
        if parts.scheme != "https" or parts.port not in (None, 443) or not host or not 0 < timeout <= 20:
            raise WorkerError("invalid_url")
    except (KeyError, TypeError, ValueError):
        raise WorkerError("invalid_url") from None
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    except (OSError, socket.gaierror):
        raise WorkerError("unavailable") from None
    addresses = []
    for family, socktype, proto, _canonname, sockaddr in records:
        address = sockaddr[0]
        if not _public_address(address):
            raise WorkerError("invalid_url")
        item = (family, socktype, proto, address)
        if item not in addresses:
            addresses.append(item)
    if not addresses:
        raise WorkerError("unavailable")
    family, _socktype, _proto, address = addresses[0]
    target = next(sockaddr for record_family, _kind, _protocol, _name, sockaddr in records
                  if record_family == family and sockaddr[0] == address)
    raw = tls = None
    try:
        raw = socket.socket(family, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        raw.settimeout(timeout)
        raw.connect(target)
        tls = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        authority = f"[{host}]" if ":" in host else host
        request_bytes = (f"GET {path} HTTP/1.1\r\nHost: {authority}\r\n"
                         "Accept: text/html, text/plain\r\nConnection: close\r\n"
                         "User-Agent: YikePublicReader/1\r\n\r\n").encode("ascii")
        tls.sendall(request_bytes)
        response = http.client.HTTPResponse(tls, method="GET")
        response.begin()
        if response.status != 200:
            raise WorkerError("unavailable")
        if response.getheader("Content-Encoding") not in (None, "identity"):
            raise WorkerError("unsupported_content")
        body = _read_body(response)
        text, title = _decode(body, response.getheader("Content-Type") or "")
    except WorkerError:
        raise
    except (OSError, ssl.SSLError, http.client.HTTPException, UnicodeError):
        raise WorkerError("unavailable") from None
    finally:
        if tls is not None:
            tls.close()
        elif raw is not None:
            raw.close()
    observed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"url": url, "title": title, "text": text, "observed_at": observed_at,
            "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "read_scope": "PUBLIC_PAGE_TEXT"}


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(16_385)
        if len(raw) > 16_384:
            raise WorkerError("invalid_url")
        request = json.loads(raw.decode("utf-8"))
        if type(request) is not dict:
            raise WorkerError("invalid_url")
        message = {"ok": True, "result": read_request(request)}
    except WorkerError as error:
        message = {"ok": False, "code": error.code}
    except Exception:
        message = {"ok": False, "code": "unavailable"}
    sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
