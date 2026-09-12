"""Bounded parent session for anonymous public search discovery."""
from __future__ import annotations

import json
import math
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from pilot.public_search_worker import _safe_url

_WORKER = Path(__file__).with_name("public_search_worker.py")
_MAX_OUTPUT_BYTES = 1024 * 1024
_FAILURE_CODES = {"invalid_query", "unavailable", "auth_failed", "rate_limited", "timeout",
                  "too_large", "invalid_search_result", "search_limit_reached",
                  "deadline_exceeded", "closed"}
_SEARCH_KEYS = {"status", "query", "observed_at", "read_scope", "results", "omitted_count", "replayed"}
_ITEM_KEYS = {"url", "title", "snippet", "date_hint", "rank"}


def normalize_query(query: str) -> str:
    try:
        if type(query) is not str or any(
                (ord(character) < 32 and not character.isspace()) or 127 <= ord(character) <= 159
                for character in query):
            raise ValueError
        normalized = " ".join(query.split())
        if not 1 <= len(normalized) <= 512:
            raise ValueError
        return normalized
    except (TypeError, ValueError):
        raise ValueError("invalid_query") from None


def valid_search_result(value: dict, query: str) -> bool:
    if type(value) is not dict or type(value.get("replayed")) is not bool:
        return False
    if value.get("status") == "FAILED":
        return set(value) == {"status", "code", "replayed"} and value.get("code") in _FAILURE_CODES
    if set(value) != _SEARCH_KEYS or value.get("status") != "SEARCHED" or value.get("query") != query:
        return False
    if value.get("read_scope") != "SEARCH_RESULTS" or type(value.get("omitted_count")) is not int or value["omitted_count"] < 0:
        return False
    try:
        observed = datetime.fromisoformat(value["observed_at"])
        if observed.tzinfo is None or observed.utcoffset() is None:
            return False
    except (TypeError, ValueError):
        return False
    results = value.get("results")
    if type(results) is not list or len(results) > 10:
        return False
    urls = set()
    for item in results:
        if type(item) is not dict or set(item) != _ITEM_KEYS:
            return False
        url = item.get("url")
        if type(url) is not str or _safe_url(url) != url or url in urls:
            return False
        urls.add(url)
        for key, limit in (("title", 1000), ("snippet", 2000), ("date_hint", 200)):
            text = item.get(key)
            if text is not None and (type(text) is not str or not text or len(text) > limit):
                return False
        if type(item.get("rank")) is not int or item["rank"] <= 0:
            return False
    return True


def _failure(code: str, replayed: bool = False) -> dict:
    return {"status": "FAILED", "code": code if code in _FAILURE_CODES else "unavailable", "replayed": replayed}


def _stop(process: subprocess.Popen) -> None:
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


class PublicSearchSession:
    def __init__(self, *, api_key: str, max_searches: int, deadline: float):
        if type(api_key) is not str or not api_key or len(api_key) > 8192 or any(ord(c) < 32 or ord(c) == 127 for c in api_key):
            raise ValueError("invalid_api_key")
        if type(max_searches) is not int or not 1 <= max_searches <= 10:
            raise ValueError("invalid_max_searches")
        if type(deadline) not in (int, float) or not math.isfinite(deadline) or deadline - time.monotonic() > 1800:
            raise ValueError("invalid_deadline")
        self._api_key = api_key
        self._max_searches = max_searches
        self._deadline = float(deadline)
        self._condition = threading.Condition()
        self._active_lock = threading.Lock()
        self._active: set[subprocess.Popen] = set()
        self._cache: dict[str, dict] = {}
        self._inflight: set[str] = set()
        self._attempts = 0
        self._closed = False

    def search(self, query: str) -> dict:
        try:
            normalized = normalize_query(query)
        except ValueError:
            return _failure("invalid_query")
        with self._condition:
            while normalized in self._inflight:
                self._condition.wait()
            if normalized in self._cache:
                return self._cache[normalized] | {"replayed": True}
            if self._closed:
                return _failure("closed")
            if time.monotonic() >= self._deadline:
                return _failure("deadline_exceeded")
            if self._attempts >= self._max_searches:
                return _failure("search_limit_reached")
            self._attempts += 1
            self._inflight.add(normalized)
        result = self._run(normalized)
        with self._condition:
            self._cache[normalized] = result
            self._inflight.remove(normalized)
            self._condition.notify_all()
        return result

    def _run(self, query: str) -> dict:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            return _failure("deadline_exceeded")
        timeout = min(20.0, remaining)
        process = None
        try:
            with self._active_lock:
                if self._closed:
                    return _failure("closed")
                process = subprocess.Popen([sys.executable, "-I", str(_WORKER)], stdin=subprocess.PIPE,
                                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                           text=True, env={})
                self._active.add(process)
            payload = json.dumps({"query": query, "api_key": self._api_key, "timeout_seconds": timeout},
                                 ensure_ascii=False, separators=(",", ":"))
            stdout, _stderr = process.communicate(payload, timeout=timeout)
            if len(stdout.encode("utf-8")) > _MAX_OUTPUT_BYTES:
                return _failure("too_large")
            message = json.loads(stdout)
            if type(message) is not dict or set(message) not in ({"ok", "result"}, {"ok", "code"}):
                return _failure("invalid_search_result")
            if message.get("ok") is False:
                return _failure(message.get("code"))
            candidate = {"status": "SEARCHED", **message.get("result", {}), "replayed": False}
            return candidate if valid_search_result(candidate, query) else _failure("invalid_search_result")
        except subprocess.TimeoutExpired:
            if process is not None:
                _stop(process)
            return _failure("timeout")
        except (AttributeError, OSError, TypeError, ValueError, json.JSONDecodeError):
            return _failure("unavailable")
        finally:
            if process is not None:
                with self._active_lock:
                    self._active.discard(process)

    def close(self):
        with self._active_lock:
            self._closed = True
            processes = tuple(self._active)
        for process in processes:
            _stop(process)
        with self._condition:
            self._condition.notify_all()
