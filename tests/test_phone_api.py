"""Synthetic transport checks; PostgreSQL/real SMS are separate evidence."""
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from pilot.web import build_app
from pilot.phone_auth import PhoneAuthError
from tests.test_ui_api import FakeStore


PHONE = "19900000001"
CODE = "123456"


class PhoneFixture:
    def __init__(self, eligible=True):
        self.eligible = eligible
        self.calls = []

    def reserve(self, phone, peer):
        self.calls.append(("reserve", phone, peer))
        return SimpleNamespace(challenge_id="synthetic-challenge", code=CODE,
                               eligible=self.eligible)

    def settle(self, phone, challenge_id, state):
        self.calls.append(("settle", phone, challenge_id, state))

    def consume(self, phone, code):
        self.calls.append(("consume", phone, code))
        return "user-1"


class SenderFixture:
    def __init__(self, result=True, error=False):
        self.result, self.error, self.calls = result, error, []

    def send_code(self, phone, code):
        self.calls.append((phone, code))
        if self.error:
            raise RuntimeError("synthetic-sensitive-provider-error")
        return self.result


def client_for(phone=None, sender=None, url="https://pilot.example"):
    return TestClient(build_app(FakeStore(), auth_secret="test-secret",
                               phone_auth=phone, sms_sender=sender), base_url=url)


def test_default_routes_are_explicitly_unavailable_not_fake_success():
    client = TestClient(build_app(FakeStore(), auth_secret="test-secret"),
                        base_url="https://pilot.example")
    for path, payload in [("sms-code", {"phone": PHONE}),
                          ("sms-session", {"phone": PHONE, "code": CODE})]:
        response = client.post("/api/ui/auth/" + path, json=payload)
        assert response.status_code == 501
        assert response.json()["detail"]["code"] == "capability_unavailable"
        assert "set-cookie" not in response.headers
    assert client.get("/api/ui/capabilities").json()["capabilities"]["sms_login"] == {"available": False}


@pytest.mark.parametrize("eligible,result,error,state", [
    (True, True, False, "ACCEPTED"),
    (True, False, False, "REJECTED"),
    (True, True, True, "UNKNOWN"),
    (False, True, False, "REJECTED"),
])
def test_code_request_has_uniform_response_without_delivery_claim(eligible, result, error, state, caplog):
    auth, sender = PhoneFixture(eligible), SenderFixture(result, error)
    client = client_for(auth, sender)
    response = client.post("/api/ui/auth/sms-code", json={"phone": PHONE})
    assert response.status_code == 200
    assert response.json() == {"retry_after": 60}
    assert auth.calls == [("reserve", PHONE, "testclient"),
                          ("settle", PHONE, "synthetic-challenge", state)]
    assert sender.calls == ([(PHONE, CODE)] if eligible else [])
    assert "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "no-store"
    for sensitive in [PHONE, CODE, "synthetic-sensitive-provider-error"]:
        assert sensitive not in caplog.text
        assert sensitive not in response.text


def test_phone_login_sets_only_http_only_cookie_and_existing_session_can_logout():
    auth, sender = PhoneFixture(), SenderFixture()
    client = client_for(auth, sender)
    response = client.post("/api/ui/auth/sms-session", json={"phone": PHONE, "code": CODE})
    assert response.status_code == 200
    assert response.json() == {"authenticated": True, "user_id": "user-1"}
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
    assert auth.calls == [("consume", PHONE, CODE)]
    assert not sender.calls
    assert client.get("/api/ui/session").json()["user_id"] == "user-1"
    old_cookie = client.cookies.get("pilot_session")
    assert client.delete("/api/ui/session").status_code == 200
    client.cookies.set("pilot_session", old_cookie)
    assert client.get("/api/ui/session").status_code == 401


@pytest.mark.parametrize("path,payload", [
    ("sms-code", {"phone": PHONE, "tenant_id": "other"}),
    ("sms-code", {"phone": 19900000001}),
    ("sms-code", {"phone": PHONE + "\n"}),
    ("sms-code", {"phone": "１９９０００００００１"}),
    ("sms-session", {"phone": PHONE, "code": CODE, "user_id": "other"}),
    ("sms-session", {"phone": PHONE, "code": 123456}),
    ("sms-session", {"phone": PHONE, "code": "１２３４５６"}),
    ("sms-session", {"phone": PHONE, "code": CODE, "trial_code": "x" * 129}),
])
def test_strict_request_body_cannot_override_identity(path, payload):
    auth = PhoneFixture()
    client = client_for(auth, SenderFixture())
    response = client.post("/api/ui/auth/" + path, json=payload)
    assert response.status_code == 422
    assert not auth.calls
    assert PHONE not in response.text and CODE not in response.text


@pytest.mark.parametrize("path,payload", [
    ("sms-code", {"phone": PHONE}),
    ("sms-session", {"phone": PHONE, "code": CODE}),
])
def test_phone_routes_preserve_https_and_origin(path, payload):
    auth = PhoneFixture()
    response = client_for(auth, SenderFixture(), "http://pilot.example").post(
        "/api/ui/auth/" + path, json=payload)
    assert response.status_code == 400
    response = client_for(auth, SenderFixture()).post(
        "/api/ui/auth/" + path, json=payload, headers={"Origin": "https://other.example"})
    assert response.status_code == 403
    assert not auth.calls


def test_trial_code_is_not_silently_accepted_or_consumed():
    auth = PhoneFixture()
    response = client_for(auth, SenderFixture()).post("/api/ui/auth/sms-session",
        json={"phone": PHONE, "code": CODE, "trial_code": "synthetic-invitation"})
    assert response.status_code == 501
    assert not auth.calls
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize("code,status", [("phone_auth_failed", 401), ("auth_rate_limited", 429)])
def test_auth_failures_do_not_issue_cookie_or_expose_provider_values(code, status):
    class DeniedPhone(PhoneFixture):
        def consume(self, phone, otp):
            raise PhoneAuthError(code)

        def reserve(self, phone, peer):
            raise PhoneAuthError(code)

    sender = SenderFixture()
    client = client_for(DeniedPhone(), sender)
    for path, payload in [("sms-code", {"phone": PHONE}),
                          ("sms-session", {"phone": PHONE, "code": CODE})]:
        response = client.post("/api/ui/auth/" + path, json=payload)
        assert response.status_code == status
        assert "set-cookie" not in response.headers
        assert PHONE not in response.text and CODE not in response.text
    assert not sender.calls


def test_missing_either_dependency_keeps_sms_unavailable():
    for auth, sender in [(PhoneFixture(), None), (None, SenderFixture())]:
        client = client_for(auth, sender)
        assert client.post("/api/ui/auth/sms-code", json={"phone": PHONE}).status_code == 501
        assert client.get("/api/ui/capabilities").json()["capabilities"]["sms_login"] == {"available": False}


def test_authenticated_result_does_not_accept_an_unprovisioned_user():
    class UnknownUser(PhoneFixture):
        def consume(self, phone, code):
            return "not-provisioned"

    response = client_for(UnknownUser(), SenderFixture()).post(
        "/api/ui/auth/sms-session", json={"phone": PHONE, "code": CODE})
    assert response.status_code == 403
    assert "set-cookie" not in response.headers
