from __future__ import annotations

import hashlib
import html
import ipaddress
import re
import socket
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

try:
    from .domain import now_iso
except ImportError:  # running server.py directly
    from domain import now_iso


MAX_BYTES = 1_000_000
TIMEOUT_SECONDS = 8


class CaptureError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _assert_public_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise CaptureError("invalid_url", "只允许 http 或 https URL")
    if parsed.username or parsed.password:
        raise CaptureError("credentials_in_url", "URL 不允许携带用户名或密码")
    if parsed.port not in {None, 80, 443}:
        raise CaptureError("port_not_allowed", "只允许标准 HTTP/HTTPS 端口")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise CaptureError("dns_failed", "域名无法解析") from exc
    for address in {item[4][0] for item in addresses}:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise CaptureError("private_address_rejected", "为防止 SSRF，不访问内网或保留地址")
    return value.strip()


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Request | None:
        safe_url = _assert_public_url(urljoin(req.full_url, newurl))
        return super().redirect_request(req, fp, code, msg, headers, safe_url)


class _DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._title_depth = 0
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered == "title":
            self._title_depth += 1
        if lowered in {"script", "style", "noscript", "svg", "template"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == "title" and self._title_depth:
            self._title_depth -= 1
        if lowered in {"script", "style", "noscript", "svg", "template"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        clean = re.sub(r"\s+", " ", html.unescape(data)).strip()
        if not clean:
            return
        if self._title_depth:
            self.title_parts.append(clean)
        self.text_parts.append(clean)


def extract_document(body: bytes, charset: str = "utf-8") -> dict[str, Any]:
    try:
        decoded = body.decode(charset, errors="replace")
    except LookupError:
        decoded = body.decode("utf-8", errors="replace")
    parser = _DocumentParser()
    parser.feed(decoded)
    title = " ".join(parser.title_parts).strip()
    text = " ".join(parser.text_parts).strip()
    return {
        "title": title[:240],
        "snippet": text[:700],
        "content_hash": hashlib.sha256(body).hexdigest(),
        "byte_length": len(body),
    }


def fetch_public_page(url: str) -> dict[str, Any]:
    requested_url = _assert_public_url(url)
    request = Request(
        requested_url,
        headers={
            "User-Agent": "LeadRadar/0.1 (+controlled-public-evidence-capture)",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
        },
    )
    opener = build_opener(_SafeRedirectHandler())
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            final_url = _assert_public_url(response.geturl())
            content_type = response.headers.get_content_type().lower()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise CaptureError("unsupported_content_type", "目标 URL 不是 HTML 页面")
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise CaptureError("page_too_large", "页面超过 1 MB 采集上限")
            charset = response.headers.get_content_charset() or "utf-8"
    except CaptureError:
        raise
    except TimeoutError as exc:
        raise CaptureError("fetch_timeout", "页面打开超时") from exc
    except OSError as exc:
        raise CaptureError("fetch_failed", "页面无法打开") from exc

    document = extract_document(body, charset)
    if not document["snippet"]:
        raise CaptureError("empty_document", "页面没有可提取的正文片段")
    return {
        **document,
        "requested_url": requested_url,
        "final_url": final_url,
        "content_type": content_type,
        "charset": charset,
        "captured_at": now_iso(),
    }

