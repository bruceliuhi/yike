from fastapi.testclient import TestClient

import pytest

from pilot.auth import InvalidPilotToken, issue_token, verify_token
from pilot.web import build_app


class Store:
    def list_opportunities(self, user_id):
        assert user_id == "user-1"
        return [{"opportunity_id": "opp-1", "title": "展台搭建", "buyer": "采购负责人", "intent_status": "NEW", "source_status": "OPEN", "public_excerpt": "秋季展会寻团队"}]

    def get_opportunity(self, user_id, opportunity_id):
        assert (user_id, opportunity_id) == ("user-1", "opp-1")
        return {"opportunity_id": "opp-1", "title": "展台搭建 <script>alert(1)</script>", "buyer": "采购负责人", "summary": "需要方案与搭建", "contact_path": "原帖评论", "draft_comment": "方便了解城市和面积吗？", "draft_dm": "看到你在找团队，项目还在评估吗？", "source_status": "OPEN"}

    def record_followup(self, user_id, opportunity_id, status, note):
        assert (user_id, opportunity_id, status) == ("user-1", "opp-1", "REPLIED")
        return {"followup_id": "f-1"}

    def list_followups(self, user_id, opportunity_id):
        return []

    def list_all_followups(self, user_id):
        return []


def test_pilot_token_rejects_tampering_and_expiry():
    token = issue_token("user-1", "secret", ttl_seconds=10, now=100)
    assert verify_token(token, "secret", now=105) == "user-1"
    with pytest.raises(InvalidPilotToken):
        verify_token(token[:-1] + "x", "secret", now=105)
    with pytest.raises(InvalidPilotToken):
        verify_token(token, "secret", now=111)


def test_pages_require_authenticated_user_and_render_evidence():
    client = TestClient(build_app(Store(), auth_secret="test-secret"))
    assert client.get("/opportunities").status_code == 401
    headers = {"Authorization": "Bearer " + issue_token("user-1", "test-secret")}
    assert "展台搭建" in client.get("/profile", headers=headers).text
    assert "展台搭建" in client.get("/opportunities", headers=headers).text
    assert "跟进反馈" in client.get("/followups", headers=headers).text
    detail = client.get("/opportunities/opp-1", headers=headers)
    assert "不自动发送" in detail.text
    assert "方便了解城市和面积吗？" in detail.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in detail.text
    response = client.post("/opportunities/opp-1/followups", headers=headers, data={"status": "REPLIED", "note": "对方回复，愿意沟通"}, follow_redirects=False)
    assert response.status_code == 303


def test_dev_session_bridge_is_disabled_by_default_and_sets_http_only_cookie():
    token = issue_token("user-1", "test-secret")
    disabled = TestClient(build_app(Store(), auth_secret="test-secret"))
    assert disabled.get("/__dev/session", params={"token": token}).status_code == 404
    enabled = TestClient(build_app(Store(), auth_secret="test-secret", dev_login=True))
    response = enabled.get("/__dev/session", params={"token": token}, follow_redirects=False)
    assert response.status_code == 303
    assert "httponly" in response.headers["set-cookie"].lower()
    assert enabled.get("/opportunities").status_code == 200


def test_health_and_readiness_are_public_and_readiness_checks_database():
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query):
            assert query == "SELECT 1"

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            return Cursor()

    class HealthStore(Store):
        database = type("Database", (), {"connect": lambda self: Connection()})()

    client = TestClient(build_app(HealthStore(), auth_secret="test-secret"))
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}

    class BrokenStore(Store):
        database = type("Database", (), {"connect": lambda self: (_ for _ in ()).throw(RuntimeError("db down"))})()

    broken = TestClient(build_app(BrokenStore(), auth_secret="test-secret"))
    assert broken.get("/readyz").status_code == 503
