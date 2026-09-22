"""The operator landing page is server-derived and remains behind its session gate."""
import re
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from pilot.ops_store import OpsError
from pilot.ops_web import build_ops_app


class _OverviewStore:
    def __init__(self):
        self.token = None
        self.user_queries = []

    def session_valid(self, token):
        return token is not None and token == self.token

    def new_session(self):
        self.token = "A" * 43
        return self.token

    def logout(self, token):
        self.token = None

    def overview(self):
        return {"total": 12, "no_trial": 2, "revoked": 1, "pending": 4, "active": 3, "expired": 2}

    def users(self, *, offset=0, query='', state=''):
        if state not in ('', 'pending', 'active', 'expired', 'revoked', 'no_trial'):
            raise OpsError('invalid_user_state')
        self.user_queries.append((offset, query, state))
        return []

    def audit_events(self, *, offset=0, action='', result=''):
        self.audit_queries = getattr(self, 'audit_queries', [])
        self.audit_queries.append((offset, action, result))
        return [dict(created_at=datetime(2026, 9, 22, 1, 2, tzinfo=timezone.utc),
                     action='ISSUE', result='SUCCEEDED',
                     actor_hash='a' * 64, trial_id='trial-1', user_id='user-1', error_code=None)]


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


def test_ops_user_search_stays_server_side_and_survives_empty_results():
    store = _OverviewStore()
    client = TestClient(
        build_ops_app(store, password="synthetic-operator-password", origin="https://ops.example"),
        base_url="https://ops.example",
        follow_redirects=False,
    )
    headers = {"Origin": "https://ops.example"}
    client.post("/ops/login", data={"password": "synthetic-operator-password"}, headers=headers)
    response = client.get("/ops/users?q=星河%26项目")
    assert response.status_code == 200
    assert 'name="q"' in response.text and "星河&amp;项目" in response.text
    assert store.user_queries == [(0, "星河&项目", "")]


def test_ops_user_state_filter_is_server_side_and_preserved_in_form():
    store = _OverviewStore()
    client = TestClient(
        build_ops_app(store, password="synthetic-operator-password", origin="https://ops.example"),
        base_url="https://ops.example",
        follow_redirects=False,
    )
    headers = {"Origin": "https://ops.example"}
    client.post("/ops/login", data={"password": "synthetic-operator-password"}, headers=headers)
    response = client.get("/ops/users?q=星河&state=expired")
    assert response.status_code == 200
    assert 'id="user-state" name="state"' in response.text
    assert '<option value="expired" selected>已到期</option>' in response.text
    assert store.user_queries == [(0, "星河", "expired")]


def test_ops_invalid_user_state_fails_closed():
    store = _OverviewStore()
    client = TestClient(
        build_ops_app(store, password="synthetic-operator-password", origin="https://ops.example"),
        base_url="https://ops.example",
        follow_redirects=False,
    )
    headers = {"Origin": "https://ops.example"}
    client.post("/ops/login", data={"password": "synthetic-operator-password"}, headers=headers)
    response = client.get("/ops/users?state=unknown")
    assert response.status_code == 200
    assert "状态筛选无效" in response.text
    assert store.user_queries == []


def test_ops_audit_page_is_session_gated_and_filters_server_side():
    store = _OverviewStore()
    client = TestClient(
        build_ops_app(store, password="synthetic-operator-password", origin="https://ops.example"),
        base_url="https://ops.example",
        follow_redirects=False,
    )
    headers = {"Origin": "https://ops.example"}
    assert client.get("/ops/audit").status_code == 303
    client.post("/ops/login", data={"password": "synthetic-operator-password"}, headers=headers)
    response = client.get("/ops/audit?action=ISSUE&result=SUCCEEDED")
    assert response.status_code == 200
    assert "运营操作记录" in response.text
    assert "2026-09-22 09:02" in response.text
    assert "aaaaaaaaaaaa…" in response.text
    assert store.audit_queries == [(0, "ISSUE", "SUCCEEDED")]
