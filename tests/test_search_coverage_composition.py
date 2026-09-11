"""Only verifies ordinary app route registration, not database semantics."""
from fastapi.testclient import TestClient
from pilot.web import build_app
from test_ui_api import FakeStore


def test_normal_app_mounts_authenticated_coverage_read():
    store = FakeStore()
    client = TestClient(build_app(store, auth_secret="synthetic-coverage-secret", dev_login=True))
    response = client.post("/api/ui/search-coverage", json={})
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert store.calls == []
