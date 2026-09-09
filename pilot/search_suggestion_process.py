"""Own at most two one-shot model workers, including their actual I/O exit.

No database or authorization lives here. Normal shutdown is bounded; a parent
hard crash is not covered by this local lifecycle fence. Killing our worker
cannot establish that the remote provider cancelled processing or charges.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from pilot.search_suggestion_model import (
    OpenAICompatibleSearchSuggestionModel, SearchSuggestionError,
    _ERROR_STATUS, _json_object, _usage, _validate_description, validate_suggestion,
)


class SearchSuggestionProcessUnavailable(Exception):
    """No worker was created for this attempt; not a retry recommendation."""
    code = "dispatch_failed"

    def __init__(self):
        super().__init__(self.code)


@dataclass(eq=False)
class _Work:
    process: subprocess.Popen | None = field(default=None, repr=False)
    io: threading.Thread | None = field(default=None, repr=False)
    done: threading.Event = field(default_factory=threading.Event, repr=False)
    output: bytes | None = field(default=None, repr=False)
    io_failed: bool = False


def _communicate(work: _Work, payload: bytes) -> None:
    # Windows may block writing stdin before communicate's timeout applies.
    # This thread owns all pipes; the caller independently supervises the PID.
    try:
        work.output, _ = work.process.communicate(payload)
    except Exception:
        work.io_failed = True
    finally:
        work.done.set()


def _cleanup(work: _Work) -> bool:
    """One cleanup budget for TERM, KILL, wait, and the pipe owner's exit."""
    deadline = time.monotonic() + 3.0
    process = work.process
    if process is None:
        return True
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=min(0.5, max(0, deadline - time.monotonic())))
            except subprocess.TimeoutExpired:
                process.kill()
        process.wait(timeout=max(0, deadline - time.monotonic()))
    except (OSError, subprocess.TimeoutExpired):
        return False
    if work.io is not None and work.io.ident is not None:
        work.io.join(timeout=max(0, deadline - time.monotonic()))
        if work.io.is_alive():
            return False
    try:
        # Only after its sole I/O owner has ended (or never started). Pipe-close
        # errors are also stop-unconfirmed, not public OS exception messages.
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        return process.poll() is not None
    except OSError:
        return False


def _worker_environment() -> dict[str, str]:
    # Python executable/package paths are absolute. Never inherit model, DB,
    # proxy, PYTHONPATH, or other caller-supplied configuration into the child.
    needed = {"systemroot", "windir", "temp", "tmp"} if os.name == "nt" else set()
    return {name: value for name, value in os.environ.items() if name.lower() in needed}


class ProcessSearchSuggestionModel:
    provider = "openai-compatible"

    def __init__(self, *, base_url: str, api_key: str, model: str,
                 timeout_seconds: float = 30, total_timeout_seconds: float = 30):
        adapter = OpenAICompatibleSearchSuggestionModel(base_url, api_key, model, timeout_seconds)
        if (type(total_timeout_seconds) not in (int, float)
                or not 0 < total_timeout_seconds <= 60 or not math.isfinite(total_timeout_seconds)):
            raise SearchSuggestionError("invalid_suggestion_configuration", 500)
        self.model = adapter.model
        self._configuration = dict(base_url=adapter.base_url, api_key=adapter.api_key,
                                   model=adapter.model, timeout_seconds=adapter.timeout_seconds)
        self._total_timeout = total_timeout_seconds
        self._condition = threading.Condition()
        self._active: set[_Work] = set()
        self._closed = False
        self._poisoned = False

    @property
    def available(self) -> bool:
        with self._condition:
            return not self._closed and not self._poisoned

    def close(self, timeout_seconds: float = 5) -> bool:
        """Stop admission and wait once for all owners. False is not stopped."""
        if (type(timeout_seconds) not in (int, float) or not 0 <= timeout_seconds <= 10
                or not math.isfinite(timeout_seconds)):
            raise SearchSuggestionError("invalid_suggestion_configuration", 500)
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            self._closed = True
            self._condition.notify_all()
            while self._active:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(timeout=remaining)
            return True

    def _dispatch(self, work: _Work, payload: bytes, deadline: float) -> None:
        # Claim stdin dispatch against close/deadline immediately before I/O.
        # Never hold this lock for pipe writes, which may block on Windows.
        with self._condition:
            allowed = not self._closed and time.monotonic() < deadline
        if allowed:
            _communicate(work, payload)
        else:
            work.done.set()

    def generate(self, *, description: str):
        _validate_description(description)
        payload = json.dumps(dict(configuration=self._configuration, description=description),
                             ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        work = _Work()
        deadline = time.monotonic() + self._total_timeout
        with self._condition:
            if self._closed or self._poisoned or len(self._active) >= 2:
                raise SearchSuggestionProcessUnavailable()
            # STARTING counts too: close cannot pass while Popen has not returned.
            self._active.add(work)
        result = None
        error_code, error_status = "suggestion_result_unknown", 504
        try:
            worker = Path(__file__).resolve().with_name("search_suggestion_worker.py")
            work.process = subprocess.Popen(
                [sys.executable, "-I", "-X", "utf8", str(worker)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env=_worker_environment(), shell=False, close_fds=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            work.io = threading.Thread(target=self._dispatch, args=(work, payload, deadline),
                                       name="yike-search-model-io", daemon=True)
            work.io.start()
            while True:
                with self._condition:
                    if self._closed or time.monotonic() >= deadline:
                        break
                if work.done.wait(timeout=min(0.05, max(0, deadline - time.monotonic()))):
                    if not work.io_failed and work.process.returncode == 0:
                        if type(work.output) is bytes and len(work.output) <= 65536:
                            try:
                                reply = _json_object(work.output.decode("utf-8"))
                                if set(reply) == {"content", "usage"}:
                                    result = (validate_suggestion(reply["content"], description=description),
                                              _usage(reply["usage"]))
                                elif set(reply) == {"error"} and reply["error"] in _ERROR_STATUS:
                                    error_code = reply["error"]
                                    error_status = _ERROR_STATUS[error_code]
                                else:
                                    error_code, error_status = "invalid_suggestion_result", 502
                            except (ValueError, UnicodeError, SearchSuggestionError, TypeError, RecursionError):
                                error_code, error_status = "invalid_suggestion_result", 502
                        else:
                            error_code, error_status = "invalid_suggestion_result", 502
                    break
        except Exception:
            # Neither provider data nor an OS exception enters the public error.
            result = None
        finally:
            confirmed = _cleanup(work)
            with self._condition:
                if confirmed:
                    self._active.remove(work)
                else:
                    self._poisoned = True  # Keep handle and capacity occupied.
                if self._closed or not confirmed or time.monotonic() >= deadline:
                    result = None
                    error_code, error_status = "suggestion_result_unknown", 504
                self._condition.notify_all()
                # This is the successful-result/close linearization point.
        if result is not None:
            return result
        if work.process is None:
            raise SearchSuggestionProcessUnavailable()
        raise SearchSuggestionError(error_code, error_status)
