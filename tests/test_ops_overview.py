"""The operator landing page is server-derived and remains behind its session gate."""
import re

from fastapi.testclient import TestClient

from pilot.ops_web import build_ops_app


class _OverviewStore:
    def __init__(self):
        self.token = None

    def session_valid(self, token):
        return token is not None and token == self.token

    def new_session(self):
        self.token = "A" * 43
        return self.token

    def logout(self, token):
        self.token = None

    def overview(self):
        return {"total": 12, "no_trial": 2, "revoked": 1, "pending": 4, "active": 3, "expired": 2}


def test_ops_home_shows_server_derived_trial_summary():
    store = _OverviewStore()
    client = TestClient(
        build_ops_app(store, password="synthetic-operator-password", origin="https://ops.example"),
        base_url="https://ops.example",
        follow_redirects=False,
    )
    headers = {"Origin": "https://ops.example"}
    assert client.get("/ops").status_code == 303
    assert client.post("/ops/login", data={"password": "synthetic-operator-password"}, headers=headers).status_code == 303
    response = client.get("/ops")
    assert response.status_code == 200
    assert "运营概览" in response.text
    assert re.search(r">12<.*>客户总数<", response.text, re.S)
    assert ">4<" in response.text and ">待激活试用<" in response.text
    assert "/ops/users" in response.text and "/ops/trials" in response.text
