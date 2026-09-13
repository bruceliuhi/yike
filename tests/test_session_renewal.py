"""Synthetic transport evidence: renewal keeps the original revocation family."""
import time

from fastapi.testclient import TestClient

from pilot.auth import issue_token, verify_token_claims
from pilot.web import build_app
from tests.test_ui_api import FakeStore


def test_sms_session_renews_without_escaping_logout():
    store = FakeStore()
    client = TestClient(build_app(store, auth_secret="test-secret"), base_url="https://pilot.example")
    original = issue_token("user-1", "test-secret", auth_source="sms", ttl_seconds=60)
    client.cookies.set("pilot_session", original)
    response = client.get("/api/ui/session")
    assert response.status_code == 200
    assert "Max-Age=2592000" in response.headers.get("set-cookie", "")
    renewed = response.cookies.get("pilot_session")
    old_claims = verify_token_claims(original, "test-secret")
    new_claims = verify_token_claims(renewed, "test-secret")
    assert new_claims.revocation_key == old_claims.revocation_key
    assert new_claims.expires_at >= int(time.time()) + 29 * 86400
    client.cookies.clear()
    client.cookies.set("pilot_session", original)
    assert client.delete("/api/ui/session").status_code == 200
    client.cookies.set("pilot_session", renewed)
    assert client.get("/api/ui/session").status_code == 401


def test_temporary_and_legacy_sessions_are_not_extended():
    for source in ("legacy", "temporary_access"):
        client = TestClient(build_app(FakeStore(), auth_secret="test-secret"), base_url="https://pilot.example")
        client.cookies.set("pilot_session", issue_token("user-1", "test-secret", auth_source=source))
        response = client.get("/api/ui/session")
        assert response.status_code == 200
        assert "set-cookie" not in response.headers
