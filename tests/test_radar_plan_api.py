"""Pure HTTP boundaries with explicit session doubles; no production/source proof."""
from copy import deepcopy
from unittest.mock import Mock

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient

from pilot.auth import TokenClaims
from pilot.radar_plan_api import register_radar_plan_api
from pilot.sessions import SessionIdentity


REQUEST_ID = "11111111-1111-4111-8111-111111111111"
TENANT_ID = "22222222-2222-4222-8222-222222222222"
PAYLOAD = {
    "contractVersion": 1, "requestId": REQUEST_ID,
    "querySeeds": ["展台搭建"], "intentSignals": ["询价"],
    "exclusions": ["招聘"], "region": "深圳", "demandTypes": ["INQUIRY"],
}


def session(user="test-user", tenant=TENANT_ID):
    return SessionIdentity(user, tenant, TokenClaims(user, 253402300799, "test-only-revocation-key"))


def client(*, sessions=None, guard=None):
    app = FastAPI()
    router = APIRouter(prefix="/api/ui")
    identity = Mock(side_effect=sessions) if sessions is not None else Mock(return_value=session())
    https = guard or Mock()
    register_radar_plan_api(router, identity, https)
    app.include_router(router)
    return TestClient(app), identity, https


def test_preview_binds_response_to_authenticated_customer_and_rechecks_session():
    http, identity, https = client()
    payload = deepcopy(PAYLOAD)
    response = http.post("/api/ui/research-plan/preview", json=payload)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    result = response.json()
    assert {key: result[key] for key in ("contractVersion", "requestId", "userId", "accountScope")} == {
        "contractVersion": 1, "requestId": REQUEST_ID, "userId": "test-user",
        "accountScope": {"id": TENANT_ID, "version": 1},
    }
    assert set(result) == {"contractVersion", "requestId", "userId", "accountScope", "plan"}
    assert [group["id"] for group in result["plan"]["strategies"]] == ["quick", "condition", "broad"]
    assert result["plan"]["queries"]
    assert len(result["plan"]["queries"]) <= 24
    assert identity.call_count == https.call_count == 2
    assert payload == PAYLOAD


@pytest.mark.parametrize("next_session", [session("another-user"), session(tenant="33333333-3333-4333-8333-333333333333")])
def test_changed_identity_during_planning_is_not_returned(next_session):
    http, _, _ = client(sessions=[session(), next_session])
    response = http.post("/api/ui/research-plan/preview", json=PAYLOAD)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "identity_conflict"
    assert "plan" not in response.json()
    assert response.headers["cache-control"] == "no-store"


def test_revoked_session_during_planning_cannot_receive_the_late_response():
    denied = HTTPException(401, detail={"code": "session_revoked"})
    http, identity, _ = client(sessions=[session(), denied])
    response = http.post("/api/ui/research-plan/preview", json=PAYLOAD)
    assert response.status_code == 401
    assert identity.call_count == 2
    assert "plan" not in response.json()


def test_invalid_session_and_https_guard_reject_before_planning(monkeypatch):
    compiler = Mock(side_effect=AssertionError("must not plan"))
    monkeypatch.setattr("pilot.radar_plan_api.build_search_directions", compiler)
    invalid = SessionIdentity("test-user", TENANT_ID, None)
    http, _, _ = client(sessions=[invalid])
    assert http.post("/api/ui/research-plan/preview", json=PAYLOAD).status_code == 401
    http, identity, _ = client(guard=Mock(side_effect=HTTPException(403)))
    assert http.post("/api/ui/research-plan/preview", json=PAYLOAD).status_code == 403
    identity.assert_not_called()
    compiler.assert_not_called()


@pytest.mark.parametrize("patch", [
    {"contractVersion": True}, {"contractVersion": 2}, {"requestId": "not-a-uuid"},
    {"querySeeds": []}, {"querySeeds": "采购"}, {"querySeeds": ["x"] * 21},
    {"querySeeds": ["x" * 161]}, {"intentSignals": ["x"] * 21},
    {"exclusions": ["x"] * 26}, {"exclusions": None}, {"region": "地" * 81},
    {"demandTypes": ["INQUIRY", "INQUIRY"]}, {"demandTypes": ["UNKNOWN"]},
    {"querySeeds": ["x\u0001"]}, {"querySeeds": ["x\u200b"]},
    {"querySeeds": ["api_key=private"]}, {"tenant_id": "other"},
])
def test_invalid_or_over_limit_input_is_rejected(patch):
    http, _, _ = client()
    response = http.post("/api/ui/research-plan/preview", json=PAYLOAD | patch)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_request"
    assert response.headers["cache-control"] == "no-store"


def test_exact_json_route_rejects_query_injection_duplicates_and_large_bodies():
    http, _, _ = client()
    path = "/api/ui/research-plan/preview"
    assert http.get(path).status_code == 405
    assert http.post(path + "/other", json=PAYLOAD).status_code == 404
    assert http.post(path + "?tenant_id=other", json=PAYLOAD).status_code == 422
    assert http.post(path, content="{}", headers={"content-type": "text/plain"}).status_code == 415
    headers = {"content-type": "application/json"}
    assert http.post(path, content='{"contractVersion":1,"contractVersion":1}', headers=headers).status_code == 422
    assert http.post(path, content='{"contractVersion":NaN}', headers=headers).status_code == 422
    assert http.post(path, content=b"x" * (32 * 1024 + 1), headers=headers).status_code == 413


def test_missing_required_fields_are_not_silently_defaulted():
    http, _, _ = client()
    for field in PAYLOAD:
        payload = {key: value for key, value in PAYLOAD.items() if key != field}
        assert http.post("/api/ui/research-plan/preview", json=payload).status_code == 422
