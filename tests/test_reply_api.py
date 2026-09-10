from types import SimpleNamespace
from uuid import uuid4

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from pilot.auth import TokenClaims
from pilot.reply_api import register_reply_api


def _event():
    ids = {name: str(uuid4()) for name in ("tenant_id", "user_id", "opportunity_id", "source_id", "outreach_request_id", "profile_version_id", "event_id")}
    return {"schema_version": "reply-event-v1", "kind": "PLATFORM_REPLY", "state": "ACTIVE", **ids,
            "platform": "XIAOHONGSHU", "channel": "dm", "external_reply_id": "r1",
            "sender_public_id": "author", "body": "请问费用？", "received_at": "2026-09-10T02:00:00Z",
            "observed_at": "2026-09-10T02:01:00Z", "read_state": "UNREAD", "read_at": None}


def _client(service):
    app = FastAPI()
    router = APIRouter(prefix="/api/ui")
    claims = TokenClaims(str(uuid4()), 4_000_000_000, "rev")
    register_reply_api(router, service, lambda request: SimpleNamespace(claims=claims), lambda request: None)
    app.include_router(router)
    return TestClient(app)


def test_record_reply_parses_event_and_returns_service_result():
    seen = []
    service = SimpleNamespace(record=lambda claims, event: seen.append(event) or {"event_id": event.event_id},
                              list_for_opportunity=lambda claims, opportunity_id: [])
    client = _client(service)
    payload = _event()
    response = client.post("/api/ui/replies", json=payload)
    assert response.status_code == 200
    assert response.json()["event_id"] == payload["event_id"]
    assert len(seen) == 1


def test_record_reply_rejects_invalid_payload_without_calling_service():
    called = []
    service = SimpleNamespace(record=lambda *args: called.append(args), list_for_opportunity=lambda *args: [])
    client = _client(service)
    response = client.post("/api/ui/replies", json={"kind": "PLATFORM_REPLY"})
    assert response.status_code == 422
    assert called == []
