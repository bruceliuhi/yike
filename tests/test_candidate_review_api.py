"""HTTP boundary only; real storage/assessment is tested separately on PG."""
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from pilot.auth import issue_token
from pilot.candidate_ingestion import CandidateIngestionError
from pilot.web import build_app
from tests.test_ui_api import FakeStore

SECRET = "synthetic-review-http-secret"
LIMIT = 64 * 1024


class ReviewBoundary:
    def __init__(self, error=None):
        self.calls, self.error = [], error

    def _call(self, name, claims, **kwargs):
        self.calls.append((name, claims, kwargs))
        if self.error:
            raise self.error
        return {"boundary_operation": name}

    def review(self, claims, payload):
        return self._call("review", claims, payload=payload)

    def verify_source(self, claims, payload):
        return self._call("verify", claims, payload=payload)

    def list_candidates(self, claims, **kwargs):
        return self._call("list", claims, **kwargs)

    def get_request(self, claims, request_id):
        return self._call("request", claims, request_id=request_id)


def client_for(service=None, base_url="https://pilot.example"):
    return TestClient(build_app(FakeStore(), auth_secret=SECRET,
                                candidate_review=service), base_url=base_url)


def headers():
    return {"Authorization": "Bearer " + issue_token("user-1", SECRET)}


def binding():
    return dict(candidateId=str(uuid4()), candidateRevision=1,
                sourceVersionId=str(uuid4()), profileId=str(uuid4()),
                profileVersion=1, requestId="review:opaque.1")


def source_body():
    return binding() | dict(humanConfirmed=True, status="OPEN", openingMethod="DIRECT",
                            locator="原帖正文", excerpt="合成测试原文", contactMethod="COMMENT")


def test_review_default_is_unavailable_not_an_approved_candidate():
    client = client_for()
    for method, path, kwargs in [
        ("post", "/api/ui/candidate-reviews", {"json": binding() | {"action": "ASSESS"}}),
        ("post", "/api/ui/candidate-source-verifications", {"json": source_body()}),
        ("get", "/api/ui/candidates", {}),
        ("get", "/api/ui/candidate-review-requests/review:opaque.1", {}),
    ]:
        result = getattr(client, method)(path, headers=headers(), **kwargs)
        assert result.status_code == 501
        assert result.json()["detail"]["code"] == "capability_unavailable"
        assert result.headers["cache-control"] == "no-store"
    caps = client.get("/api/ui/capabilities").json()["capabilities"]
    assert caps["outreach"] == {"available": False}


def test_review_and_source_check_are_separate_authenticated_operations():
    service = ReviewBoundary()
    client = client_for(service)
    assessment = binding() | {"action": "ASSESS", "retryOf": "original:1"}
    # The service, not the transport, owns strict raw value validation.
    assessment["candidateRevision"] = True
    assert client.post("/api/ui/candidate-reviews", json=assessment, headers=headers()).status_code == 200
    assert service.calls[-1][2]["payload"] == assessment
    assert service.calls[-1][2]["payload"]["candidateRevision"] is True
    source = source_body()
    assert client.post("/api/ui/candidate-source-verifications", json=source, headers=headers()).status_code == 200
    assert service.calls[-1][0] == "verify"
    assert service.calls[-1][2]["payload"] == source
    assert all(call[1].user_id == "user-1" and call[1].revocation_key for call in service.calls)


def test_query_preserves_original_request_and_read_never_reexecutes():
    service = ReviewBoundary()
    client = client_for(service)
    candidate_id = str(uuid4())
    response = client.get("/api/ui/candidates", params={"ids": candidate_id,
        "reviewRequestId": "review:opaque.1", "page": 1, "pageSize": 1}, headers=headers())
    assert response.status_code == 200
    assert service.calls[-1][2] == dict(query=None, platform=None, status=None,
        ids=[candidate_id], review_request_id="review:opaque.1", page=1, page_size=1)
    assert client.get("/api/ui/candidate-review-requests/review:opaque.1", headers=headers()).status_code == 200
    assert service.calls[-1][2] == {"request_id": "review:opaque.1"}
    assert [call[0] for call in service.calls] == ["list", "request"]


@pytest.mark.parametrize("path,body", [
    ("candidate-reviews", {"action": "APPROVED"}),
    ("candidate-reviews", {"action": "ASSESS", "reviewer": "someone"}),
    ("candidate-reviews", {"action": "INCLUDE", "reviewedAt": "today"}),
    ("candidate-source-verifications", {"reviewer": "someone"}),
    ("candidate-source-verifications", {"token": "synthetic-sensitive-canary"}),
])
def test_unknown_or_forged_fields_never_reach_service(path, body, caplog):
    service = ReviewBoundary()
    result = client_for(service).post("/api/ui/" + path, json=body, headers=headers())
    assert result.status_code == 422
    assert "synthetic-sensitive-canary" not in result.text + caplog.text
    assert not service.calls


@pytest.mark.parametrize("raw", [b"{broken", b"\xff", b"[]", b"null",
    b'{"action":"ASSESS","action":"INCLUDE"}', b'{"action":"ASSESS","candidateRevision":NaN}',
    b'{"action":"ASSESS","candidateRevision":1e309}', b'{"action":"ASSESS","reason":"\\ud800"}',
    ("[" * 1200).encode()])
def test_ambiguous_or_invalid_json_is_safe(raw):
    service = ReviewBoundary()
    result = client_for(service).post("/api/ui/candidate-reviews", content=raw,
        headers=headers() | {"Content-Type": "application/json"})
    assert result.status_code == 422
    assert not service.calls


def test_body_limit_counts_actual_bytes_and_requires_json():
    service = ReviewBoundary()
    client = client_for(service)
    response = client.post("/api/ui/candidate-reviews", content=json.dumps(binding()),
        headers=headers() | {"Content-Type": "text/plain"})
    assert response.status_code == 415
    for declared in ("1", str(LIMIT * 3)):
        response = client.post("/api/ui/candidate-reviews", content=iter([b" " * LIMIT, b" "]),
            headers=headers() | {"Content-Type": "application/json", "Content-Length": declared})
        assert response.status_code == 413
    assert not service.calls


@pytest.mark.parametrize("query", ["page=0", "pageSize=101", "page=true", "ids=bad",
    "page=1&page=2", "status=APPROVED", "platform=xhs", "ignored=secret",
    "reviewRequestId=req", "query=" + "a" * 201, "page=1.0"])
def test_invalid_query_rejected(query):
    service = ReviewBoundary()
    assert client_for(service).get("/api/ui/candidates?" + query, headers=headers()).status_code == 422
    assert not service.calls


def test_auth_https_origin_and_revoked_session_cover_all_operations():
    service = ReviewBoundary()
    client = client_for(service)
    paths = ["/api/ui/candidates", "/api/ui/candidate-review-requests/req"]
    for path in paths:
        assert client.get(path).status_code == 401
    body = binding() | {"action": "ASSESS"}
    assert client.post("/api/ui/candidate-reviews", json=body).status_code == 401
    assert client.post("/api/ui/candidate-source-verifications", json=source_body()).status_code == 401
    assert client_for(service, "http://pilot.example").post("/api/ui/candidate-reviews", json=body, headers=headers()).status_code == 400
    assert client.post("/api/ui/candidate-reviews", json=body, headers=headers() | {"Origin": "https://other.example"}).status_code == 403
    auth = headers()
    assert client.delete("/api/ui/session", headers=auth).status_code == 200
    for path in paths:
        assert client.get(path, headers=auth).status_code == 401
    assert client.post("/api/ui/candidate-reviews", json=body, headers=auth).status_code == 401
    assert not service.calls


@pytest.mark.parametrize("error,code,status", [
    (CandidateIngestionError("request_conflict", 409), "request_conflict", 409),
    (RuntimeError("synthetic-sensitive-canary"), "internal_error", 500),
])
def test_service_error_is_not_retried_or_downgraded_to_safe_failure(error, code, status, caplog):
    service = ReviewBoundary(error)
    response = client_for(service).post("/api/ui/candidate-reviews",
        json=binding() | {"action": "ASSESS"}, headers=headers())
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert len(service.calls) == 1
    assert "synthetic-sensitive-canary" not in response.text + caplog.text
