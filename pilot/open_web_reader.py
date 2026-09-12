"""Bounded parent process for anonymous public HTTPS page reads."""
from __future__ import annotations

import json
import hashlib
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

from pilot.candidate_contract import _normalize_host, _validate_url

_MAX_SECONDS = 20.0
_WORKER = Path(__file__).with_name("open_web_reader_worker.py")
_CODES = {"invalid_url", "unavailable", "unsupported_content", "too_large", "timeout"}
_RESULT_KEYS = {"url", "title", "text", "observed_at", "content_sha256", "read_scope"}
_UTC_TIME = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


class PublicReadError(RuntimeError):
    def __init__(self, code: str):
        self.code = code if code in _CODES else "unavailable"
        super().__init__(self.code)


def normalize_public_url(url: str) -> str:
    """Validate and normalize an anonymous HTTPS/default-443 URL."""
    try:
        _validate_url(url, "PUBLIC_WEB")
        parts = urlsplit(url)
        if parts.scheme.lower() != "https" or parts.port not in (None, 443):
            raise ValueError
        host = _normalize_host(parts.hostname or "")
        if not host:
            raise ValueError
        authority = f"[{host}]" if ":" in host else host
        path = quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~")
        query = quote(parts.query, safe="=&?/:@!$'()*+,;%-._~")
        normalized = urlunsplit(("https", authority, path, query, ""))
        _validate_url(normalized, "PUBLIC_WEB")
        return normalized
    except (ValueError, UnicodeError):
        raise PublicReadError("invalid_url") from None


def read_public_page(url: str, *, deadline: datetime) -> dict:
    """Read one public page before an aware caller-provided deadline."""
    if not isinstance(deadline, datetime) or deadline.tzinfo is None or deadline.utcoffset() is None:
        raise PublicReadError("invalid_url")
    normalized = normalize_public_url(url)
    remaining = (deadline.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds()
    if remaining <= 0:
        raise PublicReadError("timeout")
    timeout = min(_MAX_SECONDS, remaining)
    try:
        process = subprocess.Popen(
            [sys.executable, "-I", str(_WORKER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            env={},
        )
    except OSError:
        raise PublicReadError("unavailable") from None
    try:
        stdout, _stderr = process.communicate(
            json.dumps({"url": normalized, "timeout_seconds": timeout}, separators=(",", ":")),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise PublicReadError("timeout") from None
    except BaseException as error:
        if process.returncode is None:
            process.kill()
            process.wait()
        if isinstance(error, OSError):
            raise PublicReadError("unavailable") from None
        raise
    if process.returncode != 0 or len(stdout.encode("utf-8")) > 300_000:
        raise PublicReadError("unavailable")
    try:
        message = json.loads(stdout)
        if message.get("ok") is not True:
            raise PublicReadError(message.get("code", "unavailable"))
        result = message["result"]
        if type(result) is not dict or set(result) != _RESULT_KEYS:
            raise ValueError
        text = result["text"]
        title = result["title"]
        observed_at = result["observed_at"]
        if (result["url"] != normalized or type(text) is not str or len(text) > 60_000
                or not (title is None or type(title) is str and len(title) <= 1000)
                or result["read_scope"] != "PUBLIC_PAGE_TEXT"
                or type(observed_at) is not str or not _UTC_TIME.fullmatch(observed_at)):
            raise ValueError
        datetime.strptime(observed_at, "%Y-%m-%dT%H:%M:%SZ")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if result["content_sha256"] != digest:
            raise ValueError
        return result
    except PublicReadError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise PublicReadError("unavailable") from None
