from __future__ import annotations

import hashlib
import html
import ipaddress
import re
import socket
import xml.etree.ElementTree as ET
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
MAX_FEED_ENTRIES = 50


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


def _xml_local_name(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1].lower()


def _xml_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    value = " ".join("".join(element.itertext()).split())
    return html.unescape(value).strip()


def _feed_link(element: ET.Element, base_url: str) -> str:
    link = ""
    for child in list(element):
        if _xml_local_name(child.tag) != "link":
            continue
        href = str(child.attrib.get("href") or "").strip()
        rel = str(child.attrib.get("rel") or "alternate").strip().lower()
        candidate = href or _xml_text(child)
        if candidate and rel in {"alternate", ""}:
            link = candidate
            break
        if not link and candidate:
            link = candidate
    if not link:
        return ""
    resolved = urljoin(base_url, link)
    try:
        return _assert_public_url(resolved)
    except CaptureError:
        return ""


def _feed_entry(element: ET.Element, feed_url: str) -> dict[str, Any] | None:
    values: dict[str, str] = {}
    for child in list(element):
        name = _xml_local_name(child.tag)
        if name in {"title", "description", "summary", "content", "published", "updated", "pubdate", "id", "guid"}:
            values.setdefault(name, _xml_text(child))
    title = values.get("title", "").strip()[:240]
    link = _feed_link(element, feed_url)
    if not title or not link:
        return None
    snippet = (values.get("description") or values.get("summary") or values.get("content") or title).strip()
    snippet = re.sub(r"<[^>]+>", " ", html.unescape(snippet))
    snippet = " ".join(snippet.split())[:700]
    entry_id = values.get("guid") or values.get("id") or link
    digest = hashlib.sha256(f"{entry_id}|{title}|{link}|{snippet}".encode("utf-8")).hexdigest()
    return {
        "entry_id": entry_id[:500],
        "title": title,
        "source_url": link,
        "snippet": snippet or title,
        "published_at": (values.get("published") or values.get("pubdate") or values.get("updated") or "")[:120] or None,
        "content_hash": digest,
    }


def fetch_public_feed(url: str, limit: int = MAX_FEED_ENTRIES) -> dict[str, Any]:
    """Fetch a user-submitted public RSS/Atom feed without authentication."""

    requested_url = _assert_public_url(url)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_FEED_ENTRIES:
        raise CaptureError("feed_limit_invalid", f"Feed 条目上限必须是 1 到 {MAX_FEED_ENTRIES}。")
    request = Request(
        requested_url,
        headers={
            "User-Agent": "LeadRadar/0.1 (+controlled-public-feed-capture)",
            "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml;q=0.9",
        },
    )
    opener = build_opener(_SafeRedirectHandler())
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            final_url = _assert_public_url(response.geturl())
            content_type = response.headers.get_content_type().lower()
            if content_type not in {"application/rss+xml", "application/atom+xml", "application/xml", "text/xml"}:
                raise CaptureError("unsupported_feed_content_type", "目标 URL 不是 RSS/Atom/XML Feed")
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise CaptureError("feed_too_large", "Feed 超过 1 MB 采集上限")
            charset = response.headers.get_content_charset() or "utf-8"
    except CaptureError:
        raise
    except TimeoutError as exc:
        raise CaptureError("feed_timeout", "Feed 打开超时") from exc
    except OSError as exc:
        raise CaptureError("feed_fetch_failed", "Feed 无法打开") from exc

    upper_body = body.upper()
    if b"<!DOCTYPE" in upper_body or b"<!ENTITY" in upper_body:
        raise CaptureError("unsafe_xml", "Feed 包含不允许的 XML 外部实体声明")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise CaptureError("invalid_feed_xml", "Feed 不是可解析的 RSS/Atom XML") from exc
    root_name = _xml_local_name(root.tag)
    if root_name == "rss":
        channel = next((child for child in list(root) if _xml_local_name(child.tag) == "channel"), root)
        feed_title = next((_xml_text(child) for child in list(channel) if _xml_local_name(child.tag) == "title"), "")
        source_elements = [child for child in list(channel) if _xml_local_name(child.tag) == "item"]
    elif root_name == "feed":
        feed_title = next((_xml_text(child) for child in list(root) if _xml_local_name(child.tag) == "title"), "")
        source_elements = [child for child in list(root) if _xml_local_name(child.tag) == "entry"]
    else:
        raise CaptureError("unsupported_feed_root", "Feed 根节点必须是 RSS channel 或 Atom feed")
    entries = [item for item in (_feed_entry(element, final_url) for element in source_elements[:MAX_FEED_ENTRIES]) if item][:limit]
    if not entries:
        raise CaptureError("empty_feed", "Feed 没有包含可公开重开的有效条目")
    return {
        "requested_url": requested_url,
        "final_url": final_url,
        "feed_title": feed_title[:240] or urlparse(final_url).hostname or "公开 Feed",
        "entries": entries,
        "feed_hash": hashlib.sha256(body).hexdigest(),
        "byte_length": len(body),
        "content_type": content_type,
        "charset": charset,
        "captured_at": now_iso(),
    }
