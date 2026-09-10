"""Explicit-consent admission and bounded background execution for suggestions."""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import math
import threading
import time

from pydantic import BaseModel, ConfigDict, ValidationError

from pilot.search_suggestion_model import SearchSuggestionError
from pilot.search_suggestion_process import SearchSuggestionProcessUnavailable
from pilot.search_suggestions import SearchSuggestionRequest, SearchSuggestionStoreError


POLICY_VERSION = "profile-description-v1"


class SearchSuggestionServiceError(Exception):
    _STATUS = {"invalid_request": 422, "disclosure_mismatch": 409,
               "capability_unavailable": 501, "suggestion_busy": 503}

    def __init__(self, code):
        self.code = code if code in self._STATUS else "capability_unavailable"
        self.status = self._STATUS[self.code]
        super().__init__(self.code)


class Disclosure(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    accepted: bool
    profile_sha256: str
    model_provider: str
    model_name: str
    policy_version: str


class Submission(SearchSuggestionRequest):
    disclosure: Disclosure


class SearchSuggestionService:
    def __init__(self, store, model=None):
        self.store = store
        self.model = model
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="yike-search-suggestion")
        self._capacity = threading.BoundedSemaphore(4)
        self._condition = threading.Condition()
        self._accepting = True
        self._admitting = 0
        self._cleanup = 0
        self._jobs: dict[Future, tuple[object, str]] = {}

    @property
    def available(self):
        with self._condition:
            return bool(self._accepting and self.model is not None and getattr(self.model, "available", False))

    def _configured(self):
        if not self.available:
            raise SearchSuggestionServiceError("capability_unavailable")
        return self.model.provider, self.model.model

    def preview(self, claims, profile_version_id):
        provider, model = self._configured()
        return self.store.preview(claims, profile_version_id, provider=provider, model=model)

    def get_receipt(self, claims, request_id):
        return self.store.get_receipt(claims, request_id)

    def submit(self, claims, payload):
        try:
            submission = Submission.model_validate(payload)
        except ValidationError:
            raise SearchSuggestionServiceError("invalid_request") from None
        disclosure = submission.disclosure.model_dump()
        request = SearchSuggestionRequest.model_validate(submission.model_dump(exclude={"disclosure"}))
        replay = self.store.replay_receipt(claims, request, disclosure)
        if replay is not None:
            return replay
        if not disclosure["accepted"] or disclosure["policy_version"] != POLICY_VERSION:
            raise SearchSuggestionServiceError("disclosure_mismatch")
        provider = getattr(self.model, "provider", None)
        model_name = getattr(self.model, "model", None)
        if not self.available:
            error = SearchSuggestionServiceError("capability_unavailable")
            return self._reject(claims, request, disclosure, error.code, original=error)
        if disclosure["model_provider"] != provider or disclosure["model_name"] != model_name:
            error = SearchSuggestionServiceError("disclosure_mismatch")
            return self._reject(claims, request, disclosure, error.code, original=error)
        try:
            preview = self.store.preview(claims, submission.profile_version_id, provider=provider, model=model_name)
        except SearchSuggestionStoreError as error:
            if error.code == "profile_unavailable":
                return self._reject(claims, request, disclosure, error.code, original=error)
            raise
        if disclosure["profile_sha256"] != preview["profile_sha256"]:
            error = SearchSuggestionServiceError("disclosure_mismatch")
            return self._reject(claims, request, disclosure, error.code, original=error)
        rejection_reason = None
        with self._condition:
            if not self._accepting or not getattr(self.model, "available", False):
                rejection_reason = "capability_unavailable"
            elif not self._capacity.acquire(blocking=False):
                rejection_reason = "suggestion_busy"
            else:
                self._admitting += 1
        if rejection_reason is not None:
            error = SearchSuggestionServiceError(rejection_reason)
            return self._reject(claims, request, disclosure, rejection_reason, original=error)
        try:
            receipt, description = self.store.reserve(claims, request, provider=provider,
                model=model_name, disclosure=disclosure)
        except SearchSuggestionStoreError as error:
            self._capacity.release()
            with self._condition:
                self._admitting -= 1
                self._condition.notify_all()
            if error.code in {"profile_unavailable", "disclosure_mismatch", "suggestion_rate_limited",
                              "suggestion_quota_exceeded"}:
                return self._reject(claims, request, disclosure, error.code, original=error)
            raise
        except Exception:
            self._capacity.release()
            with self._condition:
                self._admitting -= 1
                self._condition.notify_all()
            raise
        if description is None:
            self._capacity.release()
            with self._condition:
                self._admitting -= 1
                self._condition.notify_all()
            return receipt
        try:
            future = self._executor.submit(self._execute, claims, request.request_id)
        except Exception:
            try:
                return self.store.finish(claims, request.request_id, error="dispatch_failed")
            finally:
                self._capacity.release()
                with self._condition:
                    self._admitting -= 1
                    self._condition.notify_all()
        with self._condition:
            self._jobs[future] = (claims, request.request_id)
            future.add_done_callback(self._done)
            self._admitting -= 1
            self._condition.notify_all()
        return receipt

    def _reject(self, claims, request, disclosure, reason, original=None):
        try:
            return self.store.reject(claims, request, disclosure, reason)
        except Exception:
            if original is not None:
                raise original
            raise SearchSuggestionServiceError(reason)

    def _cancel_finish(self, claims, request_id):
        try:
            self._finish_error(claims, request_id, "dispatch_failed")
        finally:
            with self._condition:
                self._cleanup -= 1
                self._condition.notify_all()

    def _execute(self, claims, request_id):
        try:
            description = self.store.prepare_dispatch(claims, request_id)
        except SearchSuggestionStoreError as error:
            try:
                self.store.finish(claims, request_id, error="dispatch_failed")
            except Exception:
                pass
            return
        try:
            content, usage = self.model.generate(description=description)
            self.store.finish(claims, request_id, content=content, usage=usage)
        except SearchSuggestionProcessUnavailable:
            self._finish_error(claims, request_id, "dispatch_failed")
        except SearchSuggestionError as error:
            self._finish_error(claims, request_id, error)
        except Exception:
            self._finish_error(claims, request_id, SearchSuggestionError("suggestion_result_unknown", 504))

    def _finish_error(self, claims, request_id, error):
        try:
            self.store.finish(claims, request_id, error=error)
        except Exception:
            pass

    def _done(self, future):
        with self._condition:
            self._jobs.pop(future, None)
            self._capacity.release()
            self._condition.notify_all()

    def close(self, timeout_seconds=5):
        if (type(timeout_seconds) not in (int, float) or not 0 <= timeout_seconds <= 10
                or not math.isfinite(timeout_seconds)):
            raise SearchSuggestionServiceError("invalid_request")
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            self._accepting = False
            jobs = list(self._jobs.items())
        for future, (claims, request_id) in jobs:
            if future.cancel():
                with self._condition:
                    self._cleanup += 1
                threading.Thread(target=self._cancel_finish, args=(claims, request_id),
                    name="yike-search-suggestion-cancel", daemon=True).start()
        remaining = max(0, deadline - time.monotonic())
        model_stopped = self.model is None or self.model.close(timeout_seconds=remaining)
        with self._condition:
            while self._jobs or self._admitting or self._cleanup:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
        self._executor.shutdown(wait=False, cancel_futures=False)
        return bool(model_stopped)
