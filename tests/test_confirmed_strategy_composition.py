"""Shared strategy registration boundaries; no real provider or platform calls."""
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from pilot.auth import issue_token, verify_token_claims
from pilot.db import PilotDatabase
from pilot.web import build_app
from tests.test_research_strategy_api import TransportStore, payload
from tests.test_ui_api import FakeStore


SECRET = "synthetic-shared-strategy-secret"
PREFIX = "/api/ui"
STRATEGY_PATHS = {
    "/api/ui/research-strategies/prepare",
    "/api/ui/research-strategies/confirm",
    "/api/ui/research-strategies/revoke",
    "/api/ui/research-strategy-operations/{request_id}",
    "/api/ui/research-strategies/{strategy_version_id}",
}
MIGRATION_SHA256 = "2f971d11f252ea525c0e29920c73f448007650a546a687d7cf17c13d9ac23ae3"


def headers(token):
    return {"Authorization": "Bearer " + token}


def test_shared_app_registers_published_strategy_migration_and_routes_once():
    strategy_entries = [entry for entry in PilotDatabase.migration_paths
                        if entry[0] == "v02-research-strategies"]
    assert len(strategy_entries) == 1
    version, path = strategy_entries[0]
    assert version == "v02-research-strategies"
    assert path.name == "114_v02_research_strategies.sql"
    assert path == Path(__file__).parents[1] / "migrations/114_v02_research_strategies.sql"
    assert sha256(path.read_bytes()).hexdigest() == MIGRATION_SHA256
    versions = [entry[0] for entry in PilotDatabase.migration_paths]
    assert versions.index("v02-research-strategies") > versions.index("v02-candidate-review")

    app = build_app(FakeStore(), auth_secret=SECRET, research_strategies=None)
    strategy_routes = [route.path for route in app.routes if route.path in STRATEGY_PATHS]
    assert set(strategy_routes) == STRATEGY_PATHS
    assert len(strategy_routes) == len(STRATEGY_PATHS)


def test_shared_app_keeps_strategy_service_optional_and_authenticates_first():
    client = TestClient(build_app(FakeStore(), auth_secret=SECRET, research_strategies=None),
                        base_url="https://pilot.example")
    valid = issue_token("user-1", SECRET)
    expired = issue_token("user-1", SECRET, ttl_seconds=1, now=1)
    cases = [
        ("POST", f"{PREFIX}/research-strategies/prepare", payload("prepare")),
        ("POST", f"{PREFIX}/research-strategies/confirm", payload("confirm")),
        ("POST", f"{PREFIX}/research-strategies/revoke", payload("revoke")),
        ("GET", f"{PREFIX}/research-strategy-operations/{uuid4()}", None),
        ("GET", f"{PREFIX}/research-strategies/{uuid4()}", None),
    ]
    for method, path, body in cases:
        assert client.request(method, path, json=body).status_code == 401
        assert client.request(method, path, json=body, headers=headers(expired)).status_code == 401
        unavailable = client.request(method, path, json=body, headers=headers(valid))
        assert unavailable.status_code == 501
        assert unavailable.json()["detail"]["code"] == "capability_unavailable"
    capabilities = client.get(f"{PREFIX}/capabilities").json()["capabilities"]
    assert capabilities["task_execution"] == {"available": False}
    assert set(capabilities) == {
        "pilot_token_session", "profiles", "opportunities", "manual_followups", "sms_login", "access_login",
        "platform_connections", "task_execution", "search_suggestions", "outreach", "replies",
    }


def test_shared_app_preserves_https_origin_and_exact_authenticated_claims():
    service = TransportStore()
    token = issue_token("user-1", SECRET)
    expected_claims = verify_token_claims(token, SECRET)
    body = payload("prepare")
    app = build_app(FakeStore(), auth_secret=SECRET, research_strategies=service)
    with TestClient(app, base_url="https://pilot.example") as client:
        forbidden = client.post(f"{PREFIX}/research-strategies/prepare", json=body,
                                headers=headers(token) | {"Origin": "https://foreign.example"})
        assert forbidden.status_code == 403
        response = client.post(f"{PREFIX}/research-strategies/prepare", json=body,
                               headers=headers(token))
    assert response.status_code == 200
    assert service.calls[0][1] == expected_claims
    assert service.calls[0][2].model_dump(mode="json") == body

    insecure = TestClient(build_app(FakeStore(), auth_secret=SECRET,
                                    research_strategies=TransportStore()),
                          base_url="http://pilot.example")
    assert insecure.post(f"{PREFIX}/research-strategies/prepare", json=body,
                         headers=headers(token)).status_code == 400
