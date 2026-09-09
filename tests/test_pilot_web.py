from fastapi.testclient import TestClient

import pytest

from pilot.auth import InvalidPilotToken, issue_token, verify_token
from pilot.web import build_app


class Store:
    def list_opportunities(self, user_id):
        assert user_id == "user-1"
        return [{"opportunity_id": "opp-1", "title": "展台搭建", "buyer": "采购负责人", "intent_status": "NEW", "source_status": "OPEN", "profile_status": "CONFIRMED", "summary": "秋季展会一体化搭建", "updated_at": "2026-09-08T10:00:00+00:00", "public_excerpt": "秋季展会寻团队"}]

    def get_opportunity(self, user_id, opportunity_id):
        assert (user_id, opportunity_id) == ("user-1", "opp-1")
        return {"opportunity_id": "opp-1", "title": "展台搭建 <script>alert(1)</script>", "buyer": "采购负责人", "summary": "需要方案与搭建", "contact_path": "原帖评论", "public_excerpt": "秋季展会寻搭建团队", "match_reason": "明确寻源且有具体场景", "action_signal": "正在比较服务商", "value_judgment": "项目型服务", "risk": "预算未公开", "reviewed_by": "reviewer-1", "reviewed_at": "2026-09-08T10:00:00+00:00", "source_platform": "xiaohongshu", "public_url": "https://example.invalid/source/one", "published_at": "2026-09-01T09:00:00+00:00", "draft_comment": "方便了解城市和面积吗？", "draft_dm": "看到你在找团队，项目还在评估吗？", "source_status": "OPEN", "profile_status": "CONFIRMED"}

    def record_followup(self, user_id, opportunity_id, status, note):
        assert (user_id, opportunity_id, status) == ("user-1", "opp-1", "REPLIED")
        return {"followup_id": "f-1"}

    def list_followups(self, user_id, opportunity_id):
        return []

    def list_all_followups(self, user_id):
        return []

    def list_failed_tasks(self, user_id):
        return []

    def set_source_status(self, user_id, opportunity_id, status):
        assert (user_id, opportunity_id, status) == ("user-1", "opp-1", "BLOCKED")


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
    opportunities_page = client.get("/opportunities", headers=headers).text
    assert "秋季展会一体化搭建" in opportunities_page
    assert "OPEN" in opportunities_page
    assert "2026-09-08T10:00:00+00:00" in opportunities_page
    assert "跟进反馈" in client.get("/followups", headers=headers).text
    detail = client.get("/opportunities/opp-1", headers=headers)
    assert "不自动发送" in detail.text
    assert "方便了解城市和面积吗？" in detail.text
    assert "原始证据" in detail.text
    assert "打开原文" in detail.text
    assert "秋季展会寻搭建团队" in detail.text
    assert "匹配理由" in detail.text
    assert "明确寻源且有具体场景" in detail.text
    source_response = client.post("/opportunities/opp-1/source-status", headers=headers, data={"status": "BLOCKED"}, follow_redirects=False)
    assert source_response.status_code == 303
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in detail.text
    response = client.post("/opportunities/opp-1/followups", headers=headers, data={"status": "REPLIED", "note": "对方回复，愿意沟通"}, follow_redirects=False)
    assert response.status_code == 303


def test_pilot_pages_load_local_styles_and_mobile_viewport():
    client = TestClient(build_app(Store(), auth_secret="test-secret"))
    headers = {"Authorization": "Bearer " + issue_token("user-1", "test-secret")}

    page = client.get("/profile", headers=headers)
    assert page.status_code == 200
    assert "<meta name='viewport' content='width=device-width,initial-scale=1'>" in page.text
    assert "<link rel='stylesheet' href='/static/styles.css'>" in page.text
    assert "<main" in page.text

    stylesheet = client.get("/static/styles.css")
    assert stylesheet.status_code == 200
    assert "@media (max-width: 760px)" in stylesheet.text


def test_pilot_pages_set_baseline_security_headers():
    client = TestClient(build_app(Store(), auth_secret="test-secret"))
    headers = {"Authorization": "Bearer " + issue_token("user-1", "test-secret")}

    response = client.get("/profile", headers=headers)

    assert response.headers["content-security-policy"] == (
        "default-src 'self'; style-src 'self'; script-src 'self'; "
        "base-uri 'none'; object-src 'none'; frame-src 'none'; "
        "frame-ancestors 'none'; form-action 'self'"
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["cache-control"] == "no-store"


def test_unhandled_errors_keep_baseline_security_headers():
    class BrokenStore(Store):
        def list_opportunities(self, user_id):
            raise RuntimeError("unexpected database failure")

    client = TestClient(build_app(BrokenStore(), auth_secret="test-secret"), raise_server_exceptions=False)
    headers = {"Authorization": "Bearer " + issue_token("user-1", "test-secret")}

    response = client.get("/opportunities", headers=headers)

    assert response.status_code == 500
    assert response.headers["content-security-policy"].startswith("default-src 'self'")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"


def test_authenticated_user_without_tenant_is_rejected_without_server_error():
    class UnknownUserStore(Store):
        def list_opportunities(self, user_id):
            raise PermissionError("authenticated pilot user is not mapped to a tenant")

    client = TestClient(build_app(UnknownUserStore(), auth_secret="test-secret"))
    headers = {"Authorization": "Bearer " + issue_token("unknown-user", "test-secret")}
    assert client.get("/opportunities", headers=headers).status_code == 403


def test_dev_session_bridge_is_disabled_by_default_and_sets_http_only_cookie(caplog):
    token = issue_token("user-1", "test-secret")
    disabled = TestClient(build_app(Store(), auth_secret="test-secret"))
    assert disabled.get("/__dev/session", params={"token": token}).status_code == 404
    enabled = TestClient(build_app(Store(), auth_secret="test-secret", dev_login=True))
    with caplog.at_level("INFO", logger="yike.pilot.access"):
        response = enabled.get("/__dev/session", params={"token": token}, follow_redirects=False)
        opportunities_response = enabled.get("/opportunities")
    assert response.status_code == 303
    assert "httponly" in response.headers["set-cookie"].lower()
    assert opportunities_response.status_code == 200
    assert all("token=" not in record.getMessage() for record in caplog.records)


def test_secure_session_exchange_uses_post_and_https_cookie():
    token = issue_token("user-1", "test-secret")
    client = TestClient(build_app(Store(), auth_secret="test-secret"), base_url="https://testserver")
    response = client.post("/session", data={"token": token}, follow_redirects=False)
    assert response.status_code == 303
    assert "secure" in response.headers["set-cookie"].lower()
    assert "token=" not in response.headers["location"]
    assert client.get("/opportunities").status_code == 200


def test_secure_session_exchange_rejects_plain_http_in_production():
    token = issue_token("user-1", "test-secret")
    client = TestClient(build_app(Store(), auth_secret="test-secret"))
    assert client.post("/session", data={"token": token}, follow_redirects=False).status_code == 400
    assert client.post("/session", data={"token": token}, headers={"x-forwarded-proto": "https"}, follow_redirects=False).status_code == 400


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


@pytest.mark.parametrize(
    ("status", "warning"),
    [
        ("EXPIRED", "来源已过期"),
        ("BLOCKED", "来源暂时受阻"),
        ("UNVERIFIED", "来源尚未核验"),
    ],
)
def test_source_status_warning_is_visible(status, warning):
    class StatusStore(Store):
        def get_opportunity(self, user_id, opportunity_id):
            row = super().get_opportunity(user_id, opportunity_id)
            row["source_status"] = status
            return row

    client = TestClient(build_app(StatusStore(), auth_secret="test-secret"))
    headers = {"Authorization": "Bearer " + issue_token("user-1", "test-secret")}
    assert warning in client.get("/opportunities/opp-1", headers=headers).text


def test_changed_profile_warning_is_visible():
    class StaleStore(Store):
        def get_opportunity(self, user_id, opportunity_id):
            row = super().get_opportunity(user_id, opportunity_id)
            row["profile_status"] = "REVOKED"
            return row

    client = TestClient(build_app(StaleStore(), auth_secret="test-secret"))
    headers = {"Authorization": "Bearer " + issue_token("user-1", "test-secret")}
    assert "业务画像已更新" in client.get("/opportunities/opp-1", headers=headers).text


def test_failed_research_task_is_visible_on_opportunities_page():
    class FailedStore(Store):
        def list_failed_tasks(self, user_id):
            return [{"task_id": "task-1", "task_key": "research:failed", "status": "FAILED"}]

    client = TestClient(build_app(FailedStore(), auth_secret="test-secret"))
    headers = {"Authorization": "Bearer " + issue_token("user-1", "test-secret")}
    assert "后台研究任务失败" in client.get("/opportunities", headers=headers).text


def test_invalid_form_values_and_missing_opportunity_fail_closed():
    class MissingStore(Store):
        def get_opportunity(self, user_id, opportunity_id):
            raise KeyError("missing")

    client = TestClient(build_app(MissingStore(), auth_secret="test-secret"))
    headers = {"Authorization": "Bearer " + issue_token("user-1", "test-secret")}
    assert client.get("/opportunities/missing", headers=headers).status_code == 404

    client = TestClient(build_app(Store(), auth_secret="test-secret"))
    assert client.post("/opportunities/opp-1/source-status", headers=headers, data={"status": "INVALID"}).status_code == 400
    assert client.post("/opportunities/opp-1/followups", headers=headers, data={"status": "INVALID", "note": ""}).status_code == 400


def test_profile_rejects_blank_description():
    class ProfileStore(Store):
        def save_profile(self, user_id, payload):
            raise AssertionError("blank profile must be rejected before persistence")

    client = TestClient(build_app(ProfileStore(), auth_secret="test-secret"))
    headers = {"Authorization": "Bearer " + issue_token("user-1", "test-secret")}
    assert client.post("/profile", headers=headers, data={"payload": "  \n  "}).status_code == 400


def test_profile_rejects_oversized_description():
    class ProfileStore(Store):
        def save_profile(self, user_id, payload):
            raise AssertionError("oversized profile must be rejected before persistence")

    client = TestClient(build_app(ProfileStore(), auth_secret="test-secret"))
    headers = {"Authorization": "Bearer " + issue_token("user-1", "test-secret")}
    assert client.post("/profile", headers=headers, data={"payload": "x" * 8001}).status_code == 413


def test_profile_confirmation_missing_version_fails_closed():
    class MissingProfileStore(Store):
        def confirm_profile(self, user_id, version_id):
            raise KeyError("missing")

    client = TestClient(build_app(MissingProfileStore(), auth_secret="test-secret"))
    headers = {"Authorization": "Bearer " + issue_token("user-1", "test-secret")}
    assert client.post("/profile/missing/confirm", headers=headers, follow_redirects=False).status_code == 404


def test_revoked_profile_version_cannot_be_reused():
    class RevokedProfileStore(Store):
        def save_profile(self, user_id, payload):
            return {"profile_id": "profile-1", "version_id": "version-1", "version": 1, "status": "REVOKED"}

    client = TestClient(build_app(RevokedProfileStore(), auth_secret="test-secret"))
    headers = {"Authorization": "Bearer " + issue_token("user-1", "test-secret")}
    response = client.post("/profile", headers=headers, data={"payload": "展台设计搭建"})
    assert response.status_code == 409
