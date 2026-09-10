"""Real HTTP/limited-role PG authentication with a synthetic SMS sink only."""
from fastapi.testclient import TestClient

from pilot.phone_auth import PhoneAuthStore
from pilot.store import PilotStore
from pilot.web import build_app
from tests.test_phone_auth_postgres import env, age  # shared dedicated-DB fixture


def test_phone_to_cookie_to_logout_with_real_database(env):
    admin, app, _, auth, user = env

    class SyntheticSink:
        def __init__(self):
            self.calls = []

        def send_code(self, phone, code):
            # The provider must not be called inside the reservation lock/TX.
            with admin.connect() as connection:
                assert connection.execute("SELECT pg_try_advisory_xact_lock(10901, 0)").fetchone()[0]
            self.calls.append((phone, code))
            return True

    sink = SyntheticSink()
    store = PilotStore(app)
    client = TestClient(build_app(store, auth_secret="synthetic-http-session-secret",
                                 phone_auth=auth, sms_sender=sink), base_url="https://pilot.example")
    phone = "13800000000"
    assert client.post("/api/ui/auth/sms-code", json={"phone": phone}).json() == {"retry_after": 60}
    assert len(sink.calls) == 1
    code = sink.calls[0][1]
    bad = "000000" if code != "000000" else "999999"
    for _ in range(5):
        response = client.post("/api/ui/auth/sms-session", json={"phone": phone, "code": bad})
        assert response.status_code == 401
    assert client.post("/api/ui/auth/sms-session", json={"phone": phone, "code": code}).status_code == 401
    assert client.get("/api/ui/session").status_code == 401

    age(admin)
    assert client.post("/api/ui/auth/sms-code", json={"phone": phone}).status_code == 200
    # Recreate app/service objects: state is in PostgreSQL, not a worker dict.
    client = TestClient(build_app(store, auth_secret="synthetic-http-session-secret",
        phone_auth=PhoneAuthStore(app, b"x" * 32), sms_sender=sink), base_url="https://pilot.example")
    response = client.post("/api/ui/auth/sms-session", json={"phone": phone, "code": sink.calls[1][1]})
    assert response.json() == {"authenticated": True, "user_id": user,
                               "account_scope": {"id": str(store._tenant_for_user(user)), "version": 1}}
    assert client.get("/api/ui/session").json()["user_id"] == user
    assert client.get("/api/ui/profiles").status_code == 200
    old_cookie = client.cookies.get("pilot_session")
    assert client.delete("/api/ui/session").status_code == 200
    client.cookies.set("pilot_session", old_cookie)
    assert client.get("/api/ui/session").status_code == 401
    assert client.post("/api/ui/auth/sms-session", json={"phone": phone, "code": sink.calls[1][1]}).status_code == 401
    assert len(sink.calls) == 2
