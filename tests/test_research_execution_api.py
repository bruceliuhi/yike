from types import SimpleNamespace
from uuid import uuid4

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from pilot.auth import TokenClaims
from tests.test_execution_api import SIGNATURE, start_payload


class Service:
    def __init__(self):
        self.calls = []

    def start(self, claims, request, signature, token):
        self.calls.append((claims, request, signature, token))
        return {"schema_version": "research-execution-v1", "execution": {}, "reservation": {}}

    def get_receipt(self, claims, request_id):
        self.calls.append((claims, request_id))
        return {"schema_version": "research-execution-v1", "execution": {}, "reservation": {}}


def client(service=...):
    from pilot.research_execution_api import register_research_execution_api
    app, router = FastAPI(), APIRouter(prefix="/api/ui")
    register_research_execution_api(
        router, None if service is ... else service,
        lambda _: SimpleNamespace(claims=TokenClaims("u", 253402300799, "a" * 64)),
        lambda _: None,
    )
    app.include_router(router)
    return TestClient(app)


def envelope(**changes):
    value = {"request": start_payload(), "signature": SIGNATURE,
             "authorization_token": "private-quote-token"}
    value.update(changes)
    return value


def test_start_and_history_routes_are_strict_and_secret_free():
    service = Service()
    response = client(service).post("/api/ui/research-execution/start", json=envelope())
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "private-quote-token" not in response.text
    assert service.calls[0][3] == "private-quote-token"
    request_id = str(uuid4())
    recovered = client(service).get("/api/ui/research-execution/operations/" + request_id)
    assert recovered.status_code == 200
    assert service.calls[-1][1] == request_id


def test_start_rejects_non_start_unknown_fields_query_and_large_body():
    service = Service()
    for body in (
        envelope(extra=True),
        envelope(request=start_payload() | {"operation": "CANCEL", "profile_version_id": None,
            "strategy_version_id": None, "configuration_sha256": None, "targets": None,
            "task_id": str(uuid4())}),
    ):
        response = client(service).post("/api/ui/research-execution/start", json=body)
        assert response.status_code == 422
        assert "private-quote-token" not in response.text
    assert client(service).post("/api/ui/research-execution/start?x=1", json=envelope()).status_code == 422
    response = client(service).post("/api/ui/research-execution/start", content=b"{" + b" " * 32768,
        headers={"content-type": "application/json"})
    assert response.status_code == 413


def test_unavailable_is_authenticated_before_501_and_never_echoes_secret():
    response = client(None).post("/api/ui/research-execution/start", json=envelope())
    assert response.status_code == 501
    assert response.json() == {"detail": {"code": "capability_unavailable"}}
    assert "private-quote-token" not in response.text
