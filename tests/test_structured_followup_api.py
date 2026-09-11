from types import SimpleNamespace
from uuid import uuid4

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from pilot.auth import TokenClaims
from pilot.followup_api import register_followup_api


def _client(service):
    app = FastAPI()
    router = APIRouter(prefix="/api/ui")
    claims = TokenClaims(str(uuid4()), 4_000_000_000, "rev")
    register_followup_api(router, service, lambda _: SimpleNamespace(claims=claims), lambda _: None)
    app.include_router(router)
    return TestClient(app)


def test_routes_are_no_store_and_keep_the_exact_binding():
    binding = {"opportunityId": str(uuid4()), "profileVersionId": str(uuid4()),
               "action": "create", "targetId": "", "targetRevision": 0,
               "requestId": str(uuid4())}
    seen = []
    service = SimpleNamespace(
        list=lambda claims: {"records": [], "members": [], "legacyRecords": []},
        replies=lambda claims, opportunity_id=None: [],
        mutate=lambda claims, raw: seen.append(raw) or {"binding": raw["binding"], "status": "UNKNOWN"},
        operation=lambda claims, raw: {"binding": raw, "status": "PENDING"},
    )
    client = _client(service)
    values = {"status": "CONTACTED", "note": "已电话联系", "occurredAt": None,
              "nextStep": "发送资料", "nextFollowupAt": None, "ownerId": str(uuid4())}
    response = client.post("/api/ui/followup-workspace/mutate", json={"binding": binding, "values": values})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert seen == [{"binding": binding, "values": values}]


def test_api_rejects_duplicate_json_keys_and_legacy_create():
    service = SimpleNamespace(list=lambda *_: {}, replies=lambda *_: [], mutate=lambda *_: {}, operation=lambda *_: {})
    client = _client(service)
    duplicate = '{"binding":{"opportunityId":"%s"},"binding":{}}' % uuid4()
    assert client.post("/api/ui/followup-workspace/mutate", content=duplicate,
                       headers={"content-type": "application/json"}).status_code == 422
    binding = {"opportunityId": str(uuid4()), "profileVersionId": str(uuid4()),
               "action": "legacy-create", "targetId": "", "targetRevision": 0,
               "requestId": str(uuid4())}
    assert client.post("/api/ui/followup-workspace/mutate", json={"binding": binding}).status_code == 422


def test_missing_service_is_501():
    assert _client(None).get("/api/ui/followup-workspace").status_code == 501
