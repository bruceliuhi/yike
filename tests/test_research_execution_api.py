from types import SimpleNamespace
from uuid import uuid4

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
import psycopg
import pytest

from pilot.auth import TokenClaims, issue_token
from pilot.execution_contract import ExecutionRuntimeError
from pilot.web import build_app
from tests.test_execution_api import SIGNATURE, start_payload
from tests.test_ui_api import FakeStore


SECRET = "research-execution-http-secret"


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


def web_client(service=None, base_url="https://pilot.example"):
    return TestClient(build_app(FakeStore(), auth_secret=SECRET,
        research_execution=service), base_url=base_url)


def auth_headers(token=None):
    return {"Authorization": "Bearer " + (token or issue_token("user-1", SECRET))}


def test_actual_web_registration_enforces_session_https_and_origin_before_service():
    service = Service()
    path = "/api/ui/research-execution/start"
    assert web_client(service).post(path, json=envelope()).status_code == 401
    assert web_client(None).post(path, json=envelope()).status_code == 401
    assert web_client(service).post(path, json=envelope(),
        headers=auth_headers("invalid-token")).status_code == 401
    assert web_client(service, "http://pilot.example").post(path, json=envelope(),
        headers=auth_headers()).status_code == 400
    response = web_client(service).post(path, json=envelope(), headers=auth_headers() |
        {"Origin": "https://foreign.example"})
    assert response.status_code == 403
    assert "private-quote-token" not in response.text
    assert not service.calls


@pytest.mark.parametrize("token", [None, 7, [], {"secret": "private-quote-token"}])
def test_actual_web_rejects_invalid_token_types_and_media_type_without_echo(token):
    service = Service()
    response = web_client(service).post("/api/ui/research-execution/start",
        json=envelope(authorization_token=token), headers=auth_headers())
    assert response.status_code == 422
    assert "private-quote-token" not in response.text
    response = web_client(service).post("/api/ui/research-execution/start",
        content="private-quote-token", headers=auth_headers() | {"content-type": "text/plain"})
    assert response.status_code == 415
    assert "private-quote-token" not in response.text
    assert not service.calls


def test_actual_web_maps_identity_and_storage_failures_to_secret_free_503(monkeypatch):
    import pilot.ui_api as ui_api
    sentinel = "private-postgresql-dsn-private-quote-token"
    def identity_failure(*_):
        raise psycopg.OperationalError(sentinel)
    monkeypatch.setattr(ui_api, "authenticate_session", identity_failure)
    for method, path, body in (
        ("POST", "/api/ui/research-execution/start", envelope()),
        ("GET", "/api/ui/research-execution/operations/" + str(uuid4()), None),
    ):
        response = web_client(Service()).request(method, path, json=body, headers=auth_headers())
        assert response.status_code == 503
        assert response.json() == {"detail": {"code": "capability_unavailable"}}
        assert response.headers["cache-control"] == "no-store"
        assert sentinel not in response.text


def test_actual_web_maps_start_and_receipt_errors_without_secret_echo():
    class Broken(Service):
        def start(self, *_):
            raise ExecutionRuntimeError("research_unavailable", 503)
        def get_receipt(self, *_):
            raise ExecutionRuntimeError("research_unavailable", 503)
    client = web_client(Broken())
    for method, path, body in (
        ("POST", "/api/ui/research-execution/start", envelope()),
        ("GET", "/api/ui/research-execution/operations/" + str(uuid4()), None),
    ):
        response = client.request(method, path, json=body, headers=auth_headers())
        assert response.status_code == 503
        assert response.json() == {"detail": {"code": "research_unavailable"}}
        assert response.headers["cache-control"] == "no-store"
        assert "private-quote-token" not in response.text
