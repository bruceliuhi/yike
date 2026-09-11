from types import SimpleNamespace
from uuid import uuid4

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
import psycopg

from pilot.auth import TokenClaims
from pilot.research_quote import ResearchQuoteError


def body():
    return {"contractVersion": 1, "requestId": str(uuid4()), "userId": "u",
        "accountScopeId": "t", "accountScopeVersion": 1, "draftId": "draft", "revision": 1,
        "configurationHash": "a" * 64, "maxSoubei": 10, "strategyBinding": {
            "strategyVersionId": str(uuid4()), "profileVersionId": str(uuid4()),
            "configurationSha256": "b" * 64}}


class Service:
    def __init__(self): self.calls = []
    def quote(self, claims, value):
        self.calls.append((claims, value))
        return value | {"ok": True}


def client(service=... , authenticated=True):
    from pilot.research_quote_api import register_research_quote_api
    app, router = FastAPI(), APIRouter(prefix="/api/ui")
    def identity(_request):
        return SimpleNamespace(claims=TokenClaims("u", 253402300799, "a" * 64) if authenticated else None)
    register_research_quote_api(router, None if service is ... else service, identity,
        lambda request: None)
    app.include_router(router)
    return TestClient(app)


def test_quote_api_strict_json_and_no_store():
    service = Service()
    response = client(service).post("/api/ui/research-usage/quote", json=body())
    assert response.status_code == 200 and response.json()["ok"] is True
    assert response.headers["cache-control"] == "no-store"
    raw = '{"contractVersion":1,"contractVersion":1}'
    assert client(service).post("/api/ui/research-usage/quote", content=raw,
        headers={"content-type": "application/json"}).status_code == 422


def test_quote_api_authenticates_before_unavailable_service():
    assert client(None, authenticated=False).post("/api/ui/research-usage/quote", json=body()).status_code == 401
    response = client(None).post("/api/ui/research-usage/quote", json=body())
    assert response.status_code == 501
    assert response.json()["detail"]["code"] == "capability_unavailable"
    assert client(Service()).post("/api/ui/research-usage/quote?extra=1", json=body()).status_code == 422


def test_quote_api_enforces_https_hook_and_body_limit():
    from pilot.research_quote_api import register_research_quote_api
    app, router, service = FastAPI(), APIRouter(prefix="/api/ui"), Service()
    def https(_request): raise HTTPException(400, detail={"code": "https_required"})
    register_research_quote_api(router, service,
        lambda _: SimpleNamespace(claims=TokenClaims("u", 253402300799, "a" * 64)), https)
    app.include_router(router)
    assert TestClient(app).post("/api/ui/research-usage/quote", json=body()).status_code == 400
    response = client(service).post("/api/ui/research-usage/quote", content=b"{" + b" " * 32768,
        headers={"content-type": "application/json"})
    assert response.status_code == 413


def test_quote_api_maps_service_error_without_echoing_body():
    class Broken:
        def quote(self, *_): raise ResearchQuoteError("strategy_conflict", 409)
    response = client(Broken()).post("/api/ui/research-usage/quote", json=body())
    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "strategy_conflict"}}
    assert response.headers["cache-control"] == "no-store"


def test_quote_api_rejects_non_token_claims_and_sanitizes_unknown_service_error():
    from pilot.research_quote_api import register_research_quote_api
    app, router = FastAPI(), APIRouter(prefix="/api/ui")
    register_research_quote_api(router, Service(), lambda _: SimpleNamespace(claims=object()), lambda _: None)
    app.include_router(router)
    assert TestClient(app).post("/api/ui/research-usage/quote", json=body()).status_code == 401
    class Broken:
        def quote(self, *_): raise ResearchQuoteError("private_detail", 418)
    response = client(Broken()).post("/api/ui/research-usage/quote", json=body())
    assert (response.status_code, response.json()) == (503, {"detail": {"code": "quote_unavailable"}})


def test_quote_api_maps_only_identity_database_failure_without_private_detail():
    from pilot.research_quote_api import register_research_quote_api
    for service in (Service(), None):
        app, router = FastAPI(), APIRouter(prefix="/api/ui")
        def database_failure(_request):
            raise psycopg.OperationalError("private-postgresql-dsn")
        register_research_quote_api(router, service, database_failure, lambda _: None)
        app.include_router(router)
        response = TestClient(app).post("/api/ui/research-usage/quote", json=body())
        assert response.status_code == 503
        assert response.json() == {"detail": {"code": "quote_unavailable"}}
        assert response.headers["cache-control"] == "no-store"
        assert "private-postgresql-dsn" not in response.text


def test_quote_api_preserves_identity_http_rejections():
    from pilot.research_quote_api import register_research_quote_api
    for status in (401, 403):
        app, router = FastAPI(), APIRouter(prefix="/api/ui")
        def rejected(_request, status=status):
            raise HTTPException(status, detail={"code": "identity_rejected"},
                headers={"Cache-Control": "no-store"})
        register_research_quote_api(router, Service(), rejected, lambda _: None)
        app.include_router(router)
        response = TestClient(app).post("/api/ui/research-usage/quote", json=body())
        assert response.status_code == status
        assert response.json() == {"detail": {"code": "identity_rejected"}}
