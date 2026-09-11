"""Shared app registration checks; PostgreSQL semantics are tested separately."""
from fastapi.testclient import TestClient
from pilot.web import build_app
from test_ui_api import FakeStore


def test_normal_ui_mounts_three_authenticated_research_reads():
    store = FakeStore()
    client = TestClient(build_app(store, auth_secret='synthetic-research-secret', dev_login=True))
    assert client.get('/api/ui/opportunity-research').status_code == 401
    for path in ('timeline', 'similar'):
        response = client.post(f'/api/ui/opportunity-research/{path}', json={})
        assert response.status_code == 401
        assert response.headers['cache-control'] == 'no-store'
    assert store.calls == []
