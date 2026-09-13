"""Mission-owned, bounded dispatch of reads for URLs discovered by that mission."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math
import threading
import time

from pilot.open_web_reader import (
    PublicPageReader, PublicReadError, normalize_public_url, valid_page_evidence,
)
from pilot.research_effects import dispatch_effect
from pilot.research_effect_contract import is_known_read_failure

_FAILURE_CODES = {"invalid_url", "unavailable", "unsupported_content", "too_large", "timeout",
                  "not_found", "unsupported_media_type", "access_restricted", "rate_limited", "connection_unavailable",
                  "invalid_read_result", "deadline_exceeded", "read_limit_reached", "closed"}


def _failure(code, replayed=False):
    return {
        "status": "FAILED",
        "code": code if code in _FAILURE_CODES else "unavailable",
        "replayed": replayed,
    }


class PublicReadSession:
    def __init__(self, *, max_reads, deadline, allowed_url, effect_dispatcher, reader=None):
        if type(max_reads) is not int or not 1 <= max_reads <= 100:
            raise ValueError("invalid_max_reads")
        if (type(deadline) not in (int, float) or not math.isfinite(deadline)
                or deadline-time.monotonic() > 1800):
            raise ValueError("invalid_deadline")
        if not callable(allowed_url) or not callable(effect_dispatcher):
            raise ValueError("invalid_read_configuration")
        reader = PublicPageReader() if reader is None else reader
        if not callable(getattr(reader,"read",None)) or not callable(getattr(reader,"close",None)):
            raise ValueError("invalid_reader")
        self._max_reads, self._deadline = max_reads, float(deadline)
        self._allowed_url, self._dispatcher, self._reader = allowed_url, effect_dispatcher, reader
        self._lock = threading.Lock()
        self._operation_lock = threading.Lock()
        self._cache = {}
        self._discovered_links = set()
        self._used = 0
        self._closed = False

    def read(self, url, *, deadline):
        try:
            normalized = normalize_public_url(url)
        except PublicReadError:
            return _failure("invalid_url")
        try:
            allowed = self._allowed_url(normalized) is True
        except Exception:
            allowed = False
        with self._lock:
            allowed = allowed or normalized in self._discovered_links
        if not allowed:
            return _failure("invalid_url")
        with self._operation_lock:
            with self._lock:
                now = time.monotonic()
                if self._closed:
                    return _failure("closed")
                if now >= self._deadline:
                    return _failure("deadline_exceeded")
                if (type(deadline) not in (int, float) or not math.isfinite(deadline)
                        or deadline <= now):
                    return _failure("deadline_exceeded")
                if normalized in self._cache:
                    result = deepcopy(self._cache[normalized])
                    result["replayed"] = True
                    return result
                if self._used >= self._max_reads:
                    return _failure("read_limit_reached")
                self._used += 1
                self._cache[normalized] = _failure("unavailable")
                effective = min(self._deadline, float(deadline), now+20.0)
            hard_read_error = None
            try:
                def perform(action_deadline):
                    nonlocal hard_read_error
                    try:
                        evidence = self._reader.read(
                            normalized,
                            deadline=datetime.now(timezone.utc) + timedelta(
                                seconds=max(0, action_deadline-time.monotonic())))
                        if not valid_page_evidence(evidence, normalized):
                            raise PublicReadError("invalid_read_result")
                        # Persist the same validated result the MCP caller sees.
                        # The durable READ contract is an envelope, not a bare page.
                        return {"status": "READ", "evidence": evidence,
                                "review_status": "UNREVIEWED", "replayed": False}
                    except PublicReadError as error:
                        failure = _failure(error.code)
                        if is_known_read_failure("READ", {"url": normalized}, failure):
                            return failure
                        # Keep a concrete hard-error diagnostic across the closed durable
                        # dispatcher; never use this path to turn a lost known-result ACK
                        # into a continuable response.
                        hard_read_error = failure["code"]
                        return {"_read_error": error.code}

                raw = dispatch_effect(
                    self._dispatcher, kind="READ", payload={"url": normalized},
                    deadline=effective, perform=perform)
                with self._lock:
                    closed = self._closed
                if closed:
                    result = _failure("closed")
                elif time.monotonic() >= self._deadline:
                    result = _failure("deadline_exceeded")
                elif type(raw) is dict and set(raw) == {"_read_error"}:
                    result = _failure(raw["_read_error"])
                elif is_known_read_failure("READ", {"url": normalized}, raw):
                    result = deepcopy(raw)
                elif (type(raw) is not dict
                      or set(raw) != {"status", "evidence", "review_status", "replayed"}
                      or raw["status"] != "READ" or raw["review_status"] != "UNREVIEWED"
                      or type(raw["replayed"]) is not bool
                      or not valid_page_evidence(raw["evidence"], normalized)):
                    result = _failure("invalid_read_result")
                else:
                    result = deepcopy(raw)
            except PublicReadError as error:
                result = _failure(error.code)
            except Exception:
                result = _failure(hard_read_error or "unavailable")
            with self._lock:
                self._cache[normalized] = deepcopy(result)
                if not self._closed and result.get("status") == "READ":
                    self._discovered_links.update(result["evidence"].get("links", []))
            return deepcopy(result)

    def close(self):
        with self._lock:
            self._closed = True
        self._reader.close()
