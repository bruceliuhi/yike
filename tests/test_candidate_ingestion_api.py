"""HTTP boundary tests only; persistence/signatures need the real PG suite."""
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from pilot.auth import issue_token
from pilot.candidate_contract import CandidateContractError
from pilot.execution_contract import ExecutionRuntimeError
from pilot.web import build_app
from tests.test_ui_api import FakeStore

SECRET = "synthetic-candidate-transport-secret"
SIGNATURE = "A" * 86
LIMIT = 4 * 1024 * 1024


class StoreBoundary:
    """Observe transport arguments; never used as evidence of ingestion."""
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def _result(self, operation, claims, **kwargs):
        self.calls.append((operation, claims, kwargs))
        if self.error:
            raise self.error
        return {"boundary_operation": operation}

    def ingest(self, claims, payload, signature):
        return self._result("ingest", claims, payload=payload, signature=signature)

    def get_receipt(self, claims, platform_run_id, request_id):
        return self._result("receipt", claims, platform_run_id=platform_run_id, request_id=request_id)

    def list_candidates(self, claims, **kwargs):
        return self._result("list", claims, **kwargs)

    def get_candidate(self, claims, candidate_id):
        return self._result("detail", claims, candidate_id=candidate_id)


def client_for(service=None, base_url="https://pilot.example"):
    return TestClient(build_app(FakeStore(), auth_secret=SECRET,
                                candidate_ingestion=service), base_url=base_url)


def headers():
    return {"Authorization": "Bearer " + issue_token("user-1", SECRET)}


def envelope():
    # Intentionally not a full DTO: the service owns raw strict validation.
    return {"batch": {"request_id": "batch:opaque.1", "records": [],
                      "execution": {"credential_version": True}}, "signature": SIGNATURE}


def paths():
    return ["/api/ui/candidate-batches/" + str(uuid4()) + "/batch:opaque.1",
            "/api/ui/raw-candidates", "/api/ui/raw-candidates/" + str(uuid4())]


def test_absent_ingestion_is_explicitly_unavailable_not_a_working_collector():
    client = client_for()
    results = [client.post("/api/ui/candidate-batches", json=envelope(), headers=headers())]
    results += [client.get(path, headers=headers()) for path in paths()]
    for result in results:
        assert result.status_code == 501
        assert result.json()["detail"]["code"] == "capability_unavailable"
        assert result.headers["cache-control"] == "no-store"
    assert client.get("/api/ui/capabilities").json()["capabilities"]["task_execution"] == {"available": False}


def test_upload_preserves_original_raw_types_and_routes_authenticate_all_reads():
    service = StoreBoundary()
    client = client_for(service)
    raw = envelope()
    response = client.post("/api/ui/candidate-batches", json=raw, headers=headers())
    assert response.status_code == 200
    call = service.calls[0]
    assert call[0] == "ingest" and call[1].user_id == "user-1"
    assert call[1].revocation_key
    assert call[2] == {"payload": raw["batch"], "signature": SIGNATURE}
    assert call[2]["payload"]["execution"]["credential_version"] is True
    lookups = paths()
    for path in lookups:
        assert client.get(path, headers=headers()).status_code == 200
    assert [call[0] for call in service.calls] == ["ingest", "receipt", "list", "detail"]
    assert service.calls[1][2]["request_id"] == "batch:opaque.1"
    assert service.calls[2][2] == {"task_id": None, "platform": None, "page": 1, "page_size": 20}
    task = str(uuid4())
    result = client.get("/api/ui/raw-candidates", params={"task_id": task, "platform": "BILIBILI", "page": 2, "page_size": 100}, headers=headers())
    assert result.status_code == 200
    assert service.calls[-1][2] == {"task_id": task, "platform": "BILIBILI", "page": 2, "page_size": 100}


@pytest.mark.parametrize("change", ["extra", "array", "string", "missing", "signature", "sig_padding", "null"])
def test_invalid_envelope_rejected_without_echo_or_service_call(change, caplog):
    service = StoreBoundary()
    body = envelope()
    if change == "extra": body["token"] = "synthetic-private-value"
    elif change == "array": body["batch"] = []
    elif change == "string": body["batch"] = "synthetic-private-value"
    elif change == "missing": del body["batch"]
    elif change == "signature": body["signature"] = "synthetic-private-value"
    elif change == "sig_padding": body["signature"] = SIGNATURE + "=="
    else: body = None
    result = client_for(service).post("/api/ui/candidate-batches", content=json.dumps(body), headers=headers() | {"Content-Type": "application/json"})
    assert result.status_code == 422
    assert result.json()["detail"]["code"] == "invalid_request"
    assert "synthetic-private-value" not in result.text + caplog.text
    assert SIGNATURE not in result.text + caplog.text
    assert not service.calls


@pytest.mark.parametrize("body", [b"{broken", b'\xff', b'{"batch":{},"batch":{},"signature":"x"}', b'{"batch":{"value":NaN},"signature":"x"}', ("[" * 1200).encode()])
def test_non_json_ambiguous_or_deep_json_rejected_safely(body):
    service = StoreBoundary()
    result = client_for(service).post("/api/ui/candidate-batches", content=body, headers=headers() | {"Content-Type": "application/json"})
    assert result.status_code == 422
    assert not service.calls


def test_transport_limit_counts_stream_bytes_without_trusting_declared_length():
    service = StoreBoundary()
    client = client_for(service)
    for declared in (None, "1", str(LIMIT + 1)):
        request_headers = headers() | {"Content-Type": "application/json"}
        if declared is not None: request_headers["Content-Length"] = declared
        result = client.post("/api/ui/candidate-batches", content=iter([b" " * (LIMIT // 2)] * 3), headers=request_headers)
        assert result.status_code == 413
        assert result.json()["detail"]["code"] == "request_too_large"
        assert result.headers["cache-control"] == "no-store"
    assert not service.calls


def test_content_type_must_be_json():
    service = StoreBoundary()
    result = client_for(service).post("/api/ui/candidate-batches", content=json.dumps(envelope()), headers=headers() | {"Content-Type": "text/plain"})
    assert result.status_code == 415
    assert not service.calls


def test_auth_https_origin_and_revocation_gate_before_ingestion():
    service = StoreBoundary()
    client = client_for(service)
    assert client.post("/api/ui/candidate-batches", json=envelope()).status_code == 401
    for path in paths(): assert client.get(path).status_code == 401
    assert client_for(service, "http://pilot.example").post("/api/ui/candidate-batches", json=envelope(), headers=headers()).status_code == 400
    assert client.post("/api/ui/candidate-batches", json=envelope(), headers=headers() | {"Origin": "https://foreign.example"}).status_code == 403
    auth = headers()
    assert client.delete("/api/ui/session", headers=auth).status_code == 200
    assert client.post("/api/ui/candidate-batches", json=envelope(), headers=auth).status_code == 401
    for path in paths(): assert client.get(path, headers=auth).status_code == 401
    assert not service.calls


@pytest.mark.parametrize("query", [{"page": 0}, {"page_size": 101}, {"page": "true"}, {"task_id": "bad"}, {"platform": "xhs"}, {"unknown": "secret"}, {"page": "1.0"}])
def test_invalid_filters_are_not_silently_ignored(query):
    service = StoreBoundary()
    response = client_for(service).get("/api/ui/raw-candidates", params=query, headers=headers())
    assert response.status_code == 422
    assert not service.calls


def test_duplicate_query_parameters_are_rejected():
    service = StoreBoundary()
    response = client_for(service).get("/api/ui/raw-candidates?page=1&page=2", headers=headers())
    assert response.status_code == 422
    assert not service.calls


def test_ingestion_domain_error_is_mapped_without_implicit_retry():
    from pilot.candidate_ingestion import CandidateIngestionError
    service = StoreBoundary(CandidateIngestionError("request_conflict", 409))
    response = client_for(service).post("/api/ui/candidate-batches", json=envelope(), headers=headers())
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "request_conflict"
    assert len(service.calls) == 1


def test_invalid_lookup_identifiers_do_not_reach_service():
    service = StoreBoundary()
    client = client_for(service)
    for path in ["/api/ui/candidate-batches/bad/req", "/api/ui/candidate-batches/" + str(uuid4()) + "/bad%20id", "/api/ui/raw-candidates/bad"]:
        assert client.get(path, headers=headers()).status_code == 422
    assert not service.calls


@pytest.mark.parametrize("error,code,status", [
    (CandidateContractError("INVALID_BATCH"), "INVALID_BATCH", 422),
    (ExecutionRuntimeError("lease_expired", 409), "lease_expired", 409),
    (ExecutionRuntimeError("invalid_session", 401), "invalid_session", 401),
    (RuntimeError("synthetic-private-value"), "internal_error", 500),
])
def test_errors_remain_sanitized_and_preserve_unknown_outcome(error, code, status, caplog):
    service = StoreBoundary(error)
    response = client_for(service).post("/api/ui/candidate-batches", json=envelope(), headers=headers())
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert "synthetic-private-value" not in response.text + caplog.text
    assert response.headers["cache-control"] == "no-store"
    assert len(service.calls) == 1  # no implicit HTTP retry
