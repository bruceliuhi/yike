from types import SimpleNamespace
from uuid import uuid4

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient


class Service:
    available = True
    def preview(self, claims, profile): return {"profile_version_id": profile}
    def submit(self, claims, payload): return {"request_id": payload["request_id"], "state": "PENDING"}
    def get_receipt(self, claims, request): return {"request_id": request, "state": "PENDING"}


def client(service=Service()):
    from pilot.auth import TokenClaims
    from pilot.search_suggestion_api import register_search_suggestion_api
    app, router = FastAPI(), APIRouter()
    claims = TokenClaims(user_id="user", expires_at=4102444800, revocation_key="a" * 64)
    register_search_suggestion_api(router, service, lambda request: SimpleNamespace(claims=claims), lambda request: None)
    app.include_router(router)
    return TestClient(app)


def test_api_strict_body_query_and_no_store():
    c = client()
    profile, request, draft = str(uuid4()), str(uuid4()), str(uuid4())
    response = c.get(f"/search-suggestions/preview?profileVersionId={profile}")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    raw = (f'{{"request_id":"{request}","request_id":"{request}","draft_id":"{draft}",'
           f'"profile_version_id":"{profile}","draft_revision":1,"disclosure":{{}}}}')
    assert c.post("/search-suggestions", content=raw, headers={"content-type": "application/json"}).status_code == 422
    assert c.get(f"/search-suggestions/{request}?extra=1").status_code == 422


def test_api_unconfigured_is_501():
    assert client(None).get(f"/search-suggestions/{uuid4()}").status_code == 501
