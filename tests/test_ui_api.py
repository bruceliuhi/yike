"""UI transport contracts with an isolated store double, not PostgreSQL proof."""
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from pilot.auth import issue_token
from pilot.web import build_app


class FakeDatabase:
    def __init__(self, store):
        self.store = store
        self.executions = []

    @contextmanager
    def connect(self):
        yield self

    @contextmanager
    def cursor(self):
        database = self

        class Cursor:
            tenant = None
            description = [SimpleNamespace(name=name) for name in ("profile_id", "version_id", "version", "payload", "status")]

            def execute(self, query, params):
                database.executions.append((query, params))
                if query.startswith("SELECT set_config"):
                    self.tenant = params[0]
                else:
                    assert "WHERE tenant_id=%s" in query
                    assert params == (self.tenant,)

            def fetchall(self):
                profile = database.store.profiles.get(self.tenant)
                return [] if profile is None else [tuple(profile[key.name] for key in self.description)]

        yield Cursor()


class FakeStore:
    """Only synthetic fixtures; no platform, collection, or sending actions."""

    def __init__(self):
        self.database = FakeDatabase(self)
        self.profiles = {
            "tenant-1": {"profile_id": "profile-1", "version_id": "version-1", "version": 1, "payload": {"description": "测试业务"}, "status": "DRAFT"},
            "tenant-2": {"profile_id": "profile-2", "version_id": "version-2", "version": 1, "payload": {"description": "另一个租户"}, "status": "DRAFT"},
        }
        self.calls = []
        self.history = []

    def _tenant_for_user(self, user_id):
        if user_id not in {"user-1", "user-2"}:
            raise PermissionError("unprovisioned sensitive details")
        return "tenant-" + user_id[-1]

    def save_profile(self, user_id, payload):
        self.calls.append(("save_profile", user_id, payload))
        profile = self.profiles[self._tenant_for_user(user_id)]
        profile["payload"] = payload
        return {key: profile[key] for key in ("profile_id", "version_id", "version", "status")}

    def confirm_profile(self, user_id, version_id):
        profile = self.profiles[self._tenant_for_user(user_id)]
        if profile["version_id"] != version_id:
            raise KeyError("wrong tenant")
        if profile["status"] == "REVOKED":
            raise ValueError("revoked")
        self.calls.append(("confirm_profile", user_id, version_id))
        profile["status"] = "CONFIRMED"

    def get_profile_version(self, user_id, version_id):
        profile = self.profiles[self._tenant_for_user(user_id)]
        if profile["version_id"] != version_id:
            raise KeyError("wrong tenant")
        return {key: profile[key] for key in ("version_id", "version", "payload", "status")}

    def list_opportunities(self, user_id):
        self.calls.append(("list_opportunities", user_id))
        if user_id == "user-2":
            return []
        return [{"opportunity_id": "opp-1", "title": "测试机会", "intent_status": "NEW", "source_status": "UNVERIFIED", "updated_at": datetime(2026, 9, 9, tzinfo=UTC)}]

    def get_opportunity(self, user_id, opportunity_id):
        if (user_id, opportunity_id) != ("user-1", "opp-1"):
            raise KeyError("wrong tenant")
        return {"opportunity_id": "opp-1", "public_excerpt": None, "source_platform": "test_fixture", "public_url": "https://example.invalid/test-only", "source_status": "UNVERIFIED", "draft_comment": "测试草稿", "draft_dm": "测试草稿"}

    def list_followups(self, user_id, opportunity_id):
        self.get_opportunity(user_id, opportunity_id)
        return self.history

    def list_all_followups(self, user_id):
        return self.history if user_id == "user-1" else []

    def record_followup(self, user_id, opportunity_id, status, note):
        self.get_opportunity(user_id, opportunity_id)
        self.calls.append(("record_followup", user_id, opportunity_id, status, note))
        self.history.append({"followup_id": "followup-1", "opportunity_id": opportunity_id, "status": status, "note": note, "created_at": datetime(2026, 9, 9, tzinfo=UTC)})
        return {"followup_id": "followup-1"}


@pytest.fixture
def setup():
    store = FakeStore()
    client = TestClient(build_app(store, auth_secret="test-secret"), base_url="https://pilot.example")
    headers = {"Authorization": "Bearer " + issue_token("user-1", "test-secret")}
    return store, client, headers


def test_session_checks_signed_and_provisioned_identity_and_logs_out(setup):
    _, client, _ = setup
    assert client.get("/api/ui/session").status_code == 401
    invalid = client.post("/api/ui/session", json={"token": "private-invalid-token"})
    assert invalid.status_code == 401
    assert "private-invalid-token" not in invalid.text
    unknown = client.post("/api/ui/session", json={"token": issue_token("unknown", "test-secret")})
    assert unknown.status_code == 403
    assert "set-cookie" not in unknown.headers
    token = issue_token("user-1", "test-secret")
    login = client.post("/api/ui/session", json={"token": token})
    assert login.json() == {"authenticated": True, "user_id": "user-1"}
    cookie = login.headers["set-cookie"].lower()
    assert all(item in cookie for item in ("httponly", "secure", "samesite=strict", "max-age=3600"))
    assert token not in login.text
    assert client.get("/api/ui/session").json() == login.json()
    expired = issue_token("user-1", "test-secret", ttl_seconds=1, now=1)
    assert client.get("/api/ui/session", headers={"Authorization": "Bearer " + expired}).status_code == 401
    assert client.delete("/api/ui/session").json() == {"authenticated": False}
    assert client.get("/api/ui/session").status_code == 401


def test_session_requires_https_without_enabling_dev_token_bridge():
    client = TestClient(build_app(FakeStore(), auth_secret="test-secret"))
    token = issue_token("user-1", "test-secret")
    assert client.post("/api/ui/session", json={"token": token}).status_code == 400
    assert client.delete("/api/ui/session").status_code == 400
    assert client.get("/__dev/session", params={"token": token}).status_code == 404


@pytest.mark.parametrize("origin", ["https://attacker.example", "null", "file://", "https://pilot.example:444", "https://pilot.example/bad"])
def test_json_mutations_keep_existing_origin_boundary(setup, origin):
    store, client, headers = setup
    headers["Origin"] = origin
    response = client.post("/api/ui/profiles", headers=headers, json={"description": "测试"})
    assert response.status_code == 403
    assert store.calls == []
    assert response.headers["x-content-type-options"] == "nosniff"


def test_profiles_are_scoped_by_authenticated_identity_and_keep_store_shape(setup):
    store, client, headers = setup
    listed = client.get("/api/ui/profiles?tenantId=tenant-2", headers=headers)
    assert listed.json() == {"items": [store.profiles["tenant-1"]]}
    assert store.database.executions[-1][1] == ("tenant-1",)
    headers["Origin"] = "https://pilot.example"
    result = client.post("/api/ui/profiles", headers=headers, json={"description": "展台设计搭建"})
    assert result.json() == {"profile_id": "profile-1", "version_id": "version-1", "version": 1, "status": "DRAFT"}
    assert store.calls[-1] == ("save_profile", "user-1", {"description": "展台设计搭建"})
    confirmed = client.post("/api/ui/profiles/version-1/confirm", headers=headers)
    assert confirmed.json() == {"version_id": "version-1", "version": 1, "payload": {"description": "展台设计搭建"}, "status": "CONFIRMED"}
    assert store.calls[-1] == ("confirm_profile", "user-1", "version-1")
    assert "RUNNING" not in confirmed.text
    assert client.post("/api/ui/profiles/version-2/confirm", headers=headers).status_code == 404


@pytest.mark.parametrize("body", [{"description": " "}, {"description": "a" * 8001}, {"description": 123}, {"description": "valid", "tenantId": "tenant-2"}, {"description": "valid", "user_id": "user-2"}])
def test_profile_input_is_strict_and_never_echoes_rejected_fields(setup, body):
    store, client, headers = setup
    response = client.post("/api/ui/profiles", headers=headers, json=body)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_request"
    assert store.calls == []
    assert "tenant-2" not in response.text


def test_revoked_profiles_do_not_become_saved_or_confirmed(setup):
    store, client, headers = setup
    store.profiles["tenant-1"]["status"] = "REVOKED"
    assert client.post("/api/ui/profiles", headers=headers, json={"description": "测试"}).status_code == 409
    assert client.post("/api/ui/profiles/version-1/confirm", headers=headers).status_code == 400


def test_opportunities_encode_dates_preserve_missing_fields_and_deny_other_tenant(setup):
    _, client, headers = setup
    response = client.get("/api/ui/opportunities", headers=headers)
    item = response.json()["items"][0]
    assert item["updated_at"] == "2026-09-09T00:00:00+00:00"
    assert "source_platform" not in item
    detail = client.get("/api/ui/opportunities/opp-1", headers=headers)
    assert detail.json()["opportunity"]["public_excerpt"] is None
    assert detail.json()["followups"] == []
    other = {"Authorization": "Bearer " + issue_token("user-2", "test-secret")}
    assert client.get("/api/ui/opportunities", headers=other).json() == {"items": []}
    assert client.get("/api/ui/opportunities/opp-1", headers=other).status_code == 404
    assert client.get("/api/ui/opportunities/no-such-id", headers=headers).status_code == 404


@pytest.mark.parametrize("status", ["CONTACTED", "REPLIED", "MEETING", "QUOTED", "LOST", "WON"])
def test_followups_only_record_explicit_manual_facts(setup, status):
    store, client, headers = setup
    body = {"opportunity_id": "opp-1", "status": status, "note": "测试中人工录入的事实"}
    response = client.post("/api/ui/followups", headers=headers, json=body)
    assert response.status_code == 201
    assert response.json() == {"followup_id": "followup-1"}
    assert store.calls[-1] == ("record_followup", "user-1", "opp-1", status, body["note"])
    assert client.get("/api/ui/followups", headers=headers).json()["items"][0]["status"] == status


@pytest.mark.parametrize("override", [{"status": "SENT"}, {"status": "NOT_CONTACTED"}, {"note": " "}, {"note": "x" * 8001}, {"tenantId": "tenant-2"}, {"user_id": "user-2"}])
def test_invalid_followups_do_not_write(setup, override):
    store, client, headers = setup
    body = {"opportunity_id": "opp-1", "status": "CONTACTED", "note": "测试"} | override
    assert client.post("/api/ui/followups", headers=headers, json=body).status_code == 422
    assert store.history == []


def test_followup_to_other_tenant_is_not_found(setup):
    store, client, _ = setup
    headers = {"Authorization": "Bearer " + issue_token("user-2", "test-secret")}
    response = client.post("/api/ui/followups", headers=headers, json={"opportunity_id": "opp-1", "status": "CONTACTED", "note": "测试"})
    assert response.status_code == 404
    assert store.history == []


def test_missing_capabilities_never_report_execution_success(setup):
    store, client, headers = setup
    capabilities = client.get("/api/ui/capabilities").json()["capabilities"]
    assert capabilities["profiles"] == {"available": True}
    assert capabilities["platform_connections"] == {"available": True}
    for capability in ("sms_login", "task_execution", "search_suggestions", "outreach", "replies"):
        assert capabilities[capability] == {"available": False}
        response = client.post(f"/api/ui/capabilities/{capability}", headers=headers)
        assert response.status_code == 501
        assert response.json()["detail"]["code"] == "capability_unavailable"
    assert client.post("/api/ui/capabilities/profiles", headers=headers).status_code == 404
    assert client.post("/api/ui/capabilities/unknown", headers=headers).status_code == 404
    assert store.calls == []


@pytest.mark.parametrize("method,path,body", [("get", "/api/ui/profiles", None), ("post", "/api/ui/profiles", {"description": "测试"}), ("post", "/api/ui/profiles/version-1/confirm", None), ("get", "/api/ui/opportunities", None), ("get", "/api/ui/opportunities/opp-1", None), ("get", "/api/ui/followups", None), ("post", "/api/ui/followups", {"opportunity_id": "opp-1", "status": "CONTACTED", "note": "测试"}), ("post", "/api/ui/capabilities/outreach", None)])
def test_all_customer_data_routes_require_authentication(setup, method, path, body):
    store, client, _ = setup
    response = client.request(method, path, json=body)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"
    assert store.calls == []


def test_json_errors_are_generic_and_responses_are_not_cached(setup):
    store, client, headers = setup

    def broken(user_id):
        raise RuntimeError("postgresql://admin:private@private-database/private")

    store.list_opportunities = broken
    error = client.get("/api/ui/opportunities", headers=headers)
    assert error.status_code == 500
    assert error.json()["detail"]["code"] == "internal_error"
    assert "private" not in error.text
    for response in (error, client.get("/api/ui/capabilities"), client.get("/api/ui/session"), client.get("/api/ui/session", headers=headers)):
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
