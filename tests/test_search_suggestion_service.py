from dataclasses import dataclass
import re
import threading
from uuid import uuid4

import pytest

from pilot.search_suggestion_model import SearchSuggestionError


@dataclass
class Claims:
    user_id: str = "user"


class FakeModel:
    provider = "openai-compatible"
    model = "synthetic-v1"

    def __init__(self, gate=None):
        self.gate = gate
        self.calls = 0
        self.closed = False

    @property
    def available(self):
        return not self.closed

    def generate(self, *, description):
        self.calls += 1
        if self.gate:
            self.gate.wait(2)
        return ({"keywords": ["采购"], "exclusions": [], "rationale": "依据业务介绍。",
                 "evidence": [description[:2]], "unknowns": []}, None)

    def close(self, timeout_seconds=5):
        self.closed = True
        return True


class FakeStore:
    def __init__(self):
        self.rows = {}
        self.finishes = []
        self.description = "设备定制"
        self.sha = "a" * 64
        self.rejects = []

    def preview(self, claims, profile_version_id, *, provider, model):
        return {"profile_version_id": profile_version_id, "profile_sha256": self.sha,
                "description": self.description, "model_provider": provider,
                "model_name": model, "disclosure_policy_version": "profile-description-v1"}

    def reserve(self, claims, request, *, provider, model, disclosure=None):
        old = self.rows.get(request.request_id)
        fingerprint = (request.model_dump(), disclosure)
        if old:
            if old[0] != fingerprint:
                from pilot.search_suggestions import SearchSuggestionStoreError
                raise SearchSuggestionStoreError("request_conflict")
            return old[1], None
        receipt = {"request_id": request.request_id, "state": "PENDING",
                   "disclosure_policy_version": disclosure["policy_version"]}
        self.rows[request.request_id] = (fingerprint, receipt)
        return receipt, self.description

    def get_receipt(self, claims, request_id):
        return self.rows[request_id][1]

    def replay_receipt(self, claims, request, disclosure):
        old = self.rows.get(request.request_id)
        if not old:
            return None
        if old[0] != (request.model_dump(), disclosure):
            from pilot.search_suggestions import SearchSuggestionStoreError
            raise SearchSuggestionStoreError("request_conflict")
        return old[1]

    def reject(self, claims, request, disclosure, reason):
        if (disclosure.get("accepted") is not True
                or not re.fullmatch(r"[a-f0-9]{64}", disclosure.get("profile_sha256", ""))
                or disclosure.get("policy_version") != "profile-description-v1"):
            from pilot.search_suggestions import SearchSuggestionStoreError
            raise SearchSuggestionStoreError("invalid_request")
        self.rejects.append(reason)
        receipt = {"request_id": request.request_id, "state": "NOT_SUBMITTED",
                   "error_code": reason}
        self.rows[request.request_id] = ((request.model_dump(), disclosure), receipt)
        return receipt

    def prepare_dispatch(self, claims, request_id):
        return self.description

    def finish(self, claims, request_id, **outcome):
        self.finishes.append((request_id, outcome))
        receipt = dict(self.rows[request_id][1])
        if outcome.get("error"):
            error = outcome["error"]
            receipt.update(state="UNKNOWN" if getattr(error, "code", error) == "suggestion_result_unknown" else "FAILED")
        else:
            receipt.update(state="SUCCEEDED", result=outcome["content"])
        self.rows[request_id] = (self.rows[request_id][0], receipt)
        return receipt


def payload(preview, request_id=None):
    return {"request_id": request_id or str(uuid4()), "draft_id": str(uuid4()),
            "profile_version_id": preview["profile_version_id"], "draft_revision": 1,
            "disclosure": {"accepted": True, "profile_sha256": preview["profile_sha256"],
                "model_provider": preview["model_provider"], "model_name": preview["model_name"],
                "policy_version": preview["disclosure_policy_version"]}}


def test_preview_does_not_call_model_and_submit_replays_original():
    from pilot.search_suggestion_service import SearchSuggestionService
    store, model = FakeStore(), FakeModel()
    service = SearchSuggestionService(store, model)
    preview = service.preview(Claims(), str(uuid4()))
    assert model.calls == 0 and preview["description"] == store.description
    body = payload(preview)
    first = service.submit(Claims(), body)
    second = service.submit(Claims(), body)
    assert first["request_id"] == second["request_id"] and model.calls <= 1
    service.close()


@pytest.mark.parametrize("change", ["accepted", "profile_sha256", "policy_version"])
def test_submit_requires_exact_server_preview_disclosure(change):
    from pilot.search_suggestion_service import SearchSuggestionService, SearchSuggestionServiceError
    service = SearchSuggestionService(FakeStore(), FakeModel())
    preview = service.preview(Claims(), str(uuid4()))
    body = payload(preview)
    body["disclosure"][change] = False if change == "accepted" else "changed"
    with pytest.raises(SearchSuggestionServiceError, match="disclosure_mismatch"):
        service.submit(Claims(), body)
    service.close()


@pytest.mark.parametrize("change", ["model_provider", "model_name"])
def test_submit_records_canonical_configuration_mismatch(change):
    from pilot.search_suggestion_service import SearchSuggestionService
    store = FakeStore()
    service = SearchSuggestionService(store, FakeModel())
    body = payload(service.preview(Claims(), str(uuid4())))
    body["disclosure"][change] = "changed"
    receipt = service.submit(Claims(), body)
    assert receipt["state"] == "NOT_SUBMITTED" and receipt["error_code"] == "disclosure_mismatch"
    service.close()


def test_unconfigured_service_still_reads_receipts_but_never_generates():
    from pilot.search_suggestion_service import SearchSuggestionService, SearchSuggestionServiceError
    store = FakeStore()
    service = SearchSuggestionService(store)
    store.rows["known"] = (None, {"request_id": "known", "state": "SUCCEEDED"})
    assert not service.available
    assert service.get_receipt(Claims(), "known")["state"] == "SUCCEEDED"
    with pytest.raises(SearchSuggestionServiceError, match="capability_unavailable"):
        service.preview(Claims(), str(uuid4()))


def test_submit_persists_valid_unavailable_request_without_generating():
    from pilot.search_suggestion_service import SearchSuggestionService
    store, model = FakeStore(), FakeModel()
    preview = store.preview(Claims(), str(uuid4()), provider=model.provider, model=model.model)
    body = payload(preview)
    model.closed = True
    receipt = SearchSuggestionService(store, model).submit(Claims(), body)
    assert receipt["state"] == "NOT_SUBMITTED"
    assert receipt["error_code"] == "capability_unavailable"
    assert store.rejects == ["capability_unavailable"] and model.calls == 0


def test_busy_request_is_recoverable_and_never_reserved():
    from pilot.search_suggestion_service import SearchSuggestionService
    store, model = FakeStore(), FakeModel()
    service = SearchSuggestionService(store, model)
    preview = service.preview(Claims(), str(uuid4()))
    assert service._capacity.acquire(blocking=False)
    assert service._capacity.acquire(blocking=False)
    assert service._capacity.acquire(blocking=False)
    assert service._capacity.acquire(blocking=False)
    receipt = service.submit(Claims(), payload(preview))
    assert receipt["state"] == "NOT_SUBMITTED"
    assert store.rejects == ["suggestion_busy"] and model.calls == 0


def test_close_rejects_admission_and_marks_cancelled_queue_dispatch_failed():
    from pilot.search_suggestion_service import SearchSuggestionService, SearchSuggestionServiceError
    gate = threading.Event()
    service = SearchSuggestionService(FakeStore(), FakeModel(gate))
    previews = [service.preview(Claims(), str(uuid4())) for _ in range(4)]
    bodies = [payload(item) for item in previews]
    for body in bodies:
        service.submit(Claims(), body)
    assert service.close(timeout_seconds=0) is False
    rejected = service.submit(Claims(), payload(previews[0]))
    assert rejected["state"] == "NOT_SUBMITTED" and rejected["error_code"] == "capability_unavailable"
    gate.set()
    service.close(timeout_seconds=2)
    assert any(getattr(outcome.get("error"), "code", outcome.get("error")) == "dispatch_failed"
               for _, outcome in service.store.finishes)
