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
from datetime import datetime, timezone, timedelta, date
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

MAX_BODY_BYTES = 1024 * 1024
MAX_TEXT_CHARS = 60_000
MAX_HEADER_BYTES = 64 * 1024
MAX_TITLE_CHARS = 1000
_HIDDEN_TAGS = {"script", "style", "noscript", "template", "svg", "canvas"}
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
_HEAD_ELEMENTS = {"base", "basefont", "bgsound", "link", "meta", "title", "noframes", "script", "noscript", "style", "template"}


def _metadata_text(value, limit):
    if (type(value) is not str or not 1 <= len(value) <= limit or value != value.strip().strip('\ufeff')
            or any(ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
        raise ValueError("invalid page metadata")
    return value


def _publication_claim(raw, declaration):
    raw = _metadata_text(raw, 128)
    if declaration not in {"article:published_time", "datepublished"}:
        raise ValueError("invalid publication declaration")
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw):
        value, precision = date.fromisoformat(raw).isoformat(), "DATE"
    else:
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}(?:Z|[+-][0-9]{2}:[0-9]{2})?", raw) is None:
            raise ValueError("invalid publication time")
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            value, precision = parsed.isoformat(timespec="seconds"), "LOCAL_SECOND"
        else:
            offset = raw[-6:] if not raw.endswith("Z") else "+00:00"
            if int(offset[-2:]) > 59 or int(offset[1:3]) > 14 or int(offset[1:3]) == 14 and int(offset[-2:]):
                raise ValueError("invalid publication offset")
            try:
                value = parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            except OverflowError:
                raise ValueError("publication outside supported calendar") from None
            precision = "SECOND"
    return {"raw": raw, "declaration": declaration, "value": value, "precision": precision}


def validate_page_metadata(value, *, observed_at=None):
    """Validate retained publisher declarations without inferring identity/timezone."""
    if (type(value) is not dict or set(value) != {"schema_version", "publication", "author"}
            or value["schema_version"] != "public-page-metadata-v1"):
        raise ValueError("invalid page metadata")
    publication, author = value["publication"], value["author"]
    if publication is None and author is None:
        raise ValueError("empty page metadata")
    if publication is not None:
        if (type(publication) is not dict or set(publication) != {"raw", "declaration", "value", "precision"}
                or _publication_claim(publication["raw"], publication["declaration"]) != publication):
            raise ValueError("inconsistent publication claim")
        if observed_at is not None:
            observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
            if observed.tzinfo is None:
                raise ValueError("missing observation timezone")
            observed = observed.astimezone(timezone.utc)
            # Unknown timezone must stay unknown. +14 is only the latest possible
            # local wall-clock bound, never an assigned publication timezone.
            maximum_local = (observed + timedelta(hours=14)).replace(tzinfo=None)
            if publication["precision"] == "DATE":
                future = date.fromisoformat(publication["value"]) > maximum_local.date()
            elif publication["precision"] == "LOCAL_SECOND":
                future = datetime.fromisoformat(publication["value"]) > maximum_local
            else:
                future = datetime.fromisoformat(publication["value"].replace("Z", "+00:00")) > observed
            if future:
                raise ValueError("future publication declaration")
    if author is not None:
        if (type(author) is not dict or set(author) != {"raw", "declaration", "value"}
                or author["declaration"] != "author" or _metadata_text(author["raw"], 256) != author["value"]):
            raise ValueError("inconsistent author declaration")
    return value


def _page_metadata(claims, observed_at):
    if len(claims) > 16:
        return None
    result = {"schema_version": "public-page-metadata-v1", "publication": None, "author": None}
    for field in ("publication", "author"):
        values, invalid = [], False
        for declaration, raw in claims:
            if (declaration == "author") != (field == "author"):
                continue
            try:
                claim = ({"raw": _metadata_text(raw, 256), "declaration": "author", "value": raw}
                         if field == "author" else _publication_claim(raw, declaration))
                checked = result | {field: claim}
                validate_page_metadata(checked, observed_at=observed_at)
                if claim not in values:
                    values.append(claim)
            except (ValueError, TypeError, OverflowError):
                invalid = True
        if not invalid and len(values) == 1:
            result[field] = values[0]
    return result if result["publication"] is not None or result["author"] is not None else None


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
        self.links: list[str] = []
        self.metadata_claims: list[tuple[str, str]] = []
        self.metadata_head_closed = False

    def handle_starttag(self, tag, attrs):
        values = {key.lower(): (value or "").lower() for key, value in attrs}
        style = values.get("style", "").replace(" ", "")
        tag = tag.lower()
        # HTMLParser does not perform the browser's implicit head/body closure.
        # Retain declarations only while the first explicit head is unambiguous.
        if not self.hidden_depth and not self.title_depth:
            if tag not in _HEAD_ELEMENTS | {"html", "head"} or (
                    tag == "head" and any(item[0] == "head" for item in self.stack)):
                self.metadata_head_closed = True
        hidden = (tag in _HIDDEN_TAGS or "hidden" in values
                  or values.get("aria-hidden") == "true"
                  or "display:none" in style or "visibility:hidden" in style)
        title = tag == "title"
        if (tag == "meta" and not hidden and not self.hidden_depth and not self.title_depth
                and not self.metadata_head_closed and self.stack and self.stack[-1][0] == "head"
                and not any(item[0] == "body" for item in self.stack)):
            attrs_raw = dict(attrs)
            declaration = values.get("property") or values.get("name")
            raw = attrs_raw.get("content")
            declarations = {value.lower() for key, value in attrs if key in {"property", "name"}
                            and type(value) is str and value.lower() in {"article:published_time", "datepublished", "author"}}
            ambiguous = (len(declarations) > 1 or any(
                sum(key == field for key, _value in attrs) > 1 for field in ("property", "name", "content")))
            if ambiguous:
                # Poison every implicated declaration instead of choosing first
                # or last duplicate attribute differently from a browser.
                for declared in sorted(declarations):
                    if len(self.metadata_claims) <= 16:
                        self.metadata_claims.append((declared, ""))
            elif declaration in {"article:published_time", "datepublished", "author"}:
                # Bounded, and a conflicting/oversized declaration is not silently
                # discarded in favour of whichever declaration happened to be first.
                if len(self.metadata_claims) <= 16:
                    self.metadata_claims.append((declaration, raw.strip() if type(raw) is str else ""))
        if tag == "a" and not hidden and not self.hidden_depth and not self.title_depth:
            href = dict(attrs).get("href")
            if (type(href) is str and href.strip() and len(href) <= 2048
                    and len(self.links) < 50 and href not in self.links):
                self.links.append(href)
        if tag in _VOID_TAGS:
            return
        self.stack.append((tag, hidden, title))
        self.hidden_depth += int(hidden)
        self.title_depth += int(title)

    def handle_startendtag(self, tag, attrs):
        # In HTML, the self-closing marker has no effect on non-void elements.
        # Treat e.g. <script/> as open until its matching end tag.
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"head", "body", "html"}:
            self.metadata_head_closed = True
        matching = next((index for index in range(len(self.stack) - 1, -1, -1)
                         if self.stack[index][0] == tag), None)
        if matching is None:
            return
        # Closing an ancestor also closes omitted descendants conservatively.
        for _tag, hidden, title in self.stack[matching:]:
            self.hidden_depth -= int(hidden)
            self.title_depth -= int(title)
        del self.stack[matching:]

    def handle_data(self, data):
        if data.strip() and not self.title_depth and not self.hidden_depth:
            self.metadata_head_closed = True
        if self.title_depth:
            self.title_parts.append(data)
        elif not self.hidden_depth:
            self.text_parts.append(data)


def _read_body(response: http.client.HTTPResponse) -> bytes:
    length = response.getheader("Content-Length")
    expected = None
    if length is not None:
        try:
            expected = int(length)
            if expected < 0:
                raise ValueError
            if expected > MAX_BODY_BYTES:
                raise WorkerError("too_large")
        except ValueError:
            raise WorkerError("unavailable") from None
    try:
        body = response.read(MAX_BODY_BYTES + 1)
    except http.client.IncompleteRead:
        raise WorkerError("unavailable") from None
    if len(body) > MAX_BODY_BYTES:
        raise WorkerError("too_large")
    if expected is not None and len(body) != expected:
        raise WorkerError("unavailable")
    return body


def _decode(body: bytes, content_type: str, *, links=None, metadata_claims=None) -> tuple[str, str | None]:
    media_type, *parameters = content_type.split(";")
    media_type = media_type.strip().lower()
    # A missing/malformed type is not a confirmed unsupported format.
    if re.fullmatch(r"[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*", media_type) is None:
        raise WorkerError("unsupported_content")
    if media_type not in {"text/html", "text/plain"}:
        raise WorkerError("unsupported_media_type")
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
        if links is not None:
            links.extend(parser.links)
        if metadata_claims is not None:
            metadata_claims.extend(parser.metadata_claims)
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
        # Leave room for a determinate failure receipt before the parent's total
        # deadline. No HTTP request has been sent at this narrow failure point.
        raw.settimeout(min(5.0, timeout / 2))
        try:
            raw.connect(target)
        except OSError:
            raise WorkerError("connection_unavailable") from None
        raw.settimeout(timeout)
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
        if response.status in (404, 410):
            raise WorkerError("not_found")
        if response.status in (401, 403):
            raise WorkerError("access_restricted")
        if response.status == 429:
            raise WorkerError("rate_limited")
        if response.status != 200:
            raise WorkerError("unavailable")
        if response.getheader("Content-Encoding") not in (None, "identity"):
            raise WorkerError("unsupported_content")
        body = _read_body(response)
        links, metadata_claims = [], []
        text, title = _decode(body, response.getheader("Content-Type") or "", links=links, metadata_claims=metadata_claims)
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
    resolved_links = []
    for href in links:
        try:
            resolved_links.append(urljoin(url, href))
        except ValueError:
            continue
    result = {"url": url, "title": title, "text": text, "observed_at": observed_at,
            "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "read_scope": "PUBLIC_PAGE_TEXT", "links": resolved_links}
    metadata = _page_metadata(metadata_claims, observed_at)
    if metadata is not None:
        result["page_metadata"] = metadata
    return result


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
