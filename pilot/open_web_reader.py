"""Bounded parent process for anonymous public HTTPS page reads."""
from __future__ import annotations

import json
import hashlib
import re
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit

from pilot.candidate_contract import _normalize_host, _validate_url

_MAX_SECONDS = 20.0
_WORKER = Path(__file__).with_name("open_web_reader_worker.py")
_CODES = {"invalid_url", "unavailable", "unsupported_content", "too_large", "timeout"}
_RESULT_KEYS = {"url", "title", "text", "observed_at", "content_sha256", "read_scope"}
_UTC_TIME = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_CREDENTIAL_QUERY_KEYS = {
    "apikey", "accesskey", "accesskeyid", "secretkey", "secretaccesskey",
    "clientsecret", "credential", "credentials", "authorization", "auth",
    "token", "accesstoken", "refreshtoken", "idtoken", "password", "passwd",
    "pwd", "cookie", "session", "sessionid", "signature", "sig",
}
_ACTIVE_LOCK = threading.Lock()
_ACTIVE_PROCESSES: set[subprocess.Popen] = set()
_READS_STOPPED = False


class PublicReadError(RuntimeError):
    def __init__(self, code: str):
        self.code = code if code in _CODES else "unavailable"
        super().__init__(self.code)


def _stop_process(process: subprocess.Popen) -> None:
    if process.returncode is not None:
        return
    try:
        process.kill()
    except OSError:
        pass
    try:
        process.wait()
    except OSError:
        pass


def cancel_active_reads() -> None:
    """Terminate and reap reader workers owned by this process."""
    global _READS_STOPPED
    with _ACTIVE_LOCK:
        _READS_STOPPED = True
        processes = tuple(_ACTIVE_PROCESSES)
    for process in processes:
        _stop_process(process)


@dataclass
class _ReadScope:
    lock: threading.Lock = field(default_factory=threading.Lock)
    active: set[subprocess.Popen] = field(default_factory=set)
    stopped: bool = False


def valid_page_evidence(value, url: str) -> bool:
    """Validate exact, internally consistent public-page evidence."""
    try:
        if type(value) is not dict or set(value) != _RESULT_KEYS:
            return False
        observed = datetime.fromisoformat(value["observed_at"])
        text, title = value["text"], value["title"]
        return (
            value["url"] == url
            and value["read_scope"] == "PUBLIC_PAGE_TEXT"
            and type(text) is str and 1 <= len(text) <= 60_000 and bool(text.strip())
            and (title is None or type(title) is str and len(title) <= 1000)
            and observed.tzinfo is not None
            and observed <= datetime.now(timezone.utc)
            and value["content_sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
        )
    except (KeyError, ValueError, TypeError, UnicodeError):
        return False


def normalize_public_url(url: str) -> str:
    """Validate and normalize an anonymous HTTPS/default-443 URL."""
    try:
        _validate_url(url, "PUBLIC_WEB")
        parts = urlsplit(url)
        if parts.scheme.lower() != "https" or parts.port not in (None, 443):
            raise ValueError
        for key, _value in parse_qsl(parts.query, keep_blank_values=True):
            normalized_key = re.sub(r"[^a-z0-9]", "", key.lower())
            if (normalized_key in _CREDENTIAL_QUERY_KEYS
                    or normalized_key.startswith("x") and normalized_key[1:] in _CREDENTIAL_QUERY_KEYS):
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


def _read_public_page(url: str, *, deadline: datetime, lock, active, stopped) -> dict:
    """Read one public page before an aware caller-provided deadline."""
    if not isinstance(deadline, datetime) or deadline.tzinfo is None or deadline.utcoffset() is None:
        raise PublicReadError("invalid_url")
    normalized = normalize_public_url(url)
    remaining = (deadline.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds()
    if remaining <= 0:
        raise PublicReadError("timeout")
    timeout = min(_MAX_SECONDS, remaining)
    # Spawning and registration share one short critical section. It contains
    # no DNS/network/worker I/O, so cancellation cannot miss an OS child.
    with lock:
        if stopped():
            raise PublicReadError("timeout")
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
        active.add(process)
    try:
        stdout, _stderr = process.communicate(
            json.dumps({"url": normalized, "timeout_seconds": timeout}, separators=(",", ":")),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        _stop_process(process)
        raise PublicReadError("timeout") from None
    except BaseException as error:
        _stop_process(process)
        if isinstance(error, OSError):
            raise PublicReadError("unavailable") from None
        raise
    finally:
        with lock:
            active.discard(process)
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


def read_public_page(url: str, *, deadline: datetime) -> dict:
    """Read using the legacy process-global cancellation scope."""
    return _read_public_page(
        url, deadline=deadline, lock=_ACTIVE_LOCK, active=_ACTIVE_PROCESSES,
        stopped=lambda: _READS_STOPPED,
    )


class PublicPageReader:
    """A page reader whose workers and cancellation are mission-owned."""
    def __init__(self):
        self._scope = _ReadScope()

    def read(self, url: str, *, deadline: datetime) -> dict:
        scope = self._scope
        return _read_public_page(
            url, deadline=deadline, lock=scope.lock, active=scope.active,
            stopped=lambda: scope.stopped,
        )

    def close(self) -> None:
        scope = self._scope
        with scope.lock:
            scope.stopped = True
            processes = tuple(scope.active)
        for process in processes:
            _stop_process(process)
