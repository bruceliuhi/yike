"""Actual authenticated device recovery on dedicated PG; no platform session or send."""
from pathlib import Path
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from nacl.signing import SigningKey

from pilot.auth import issue_token
from pilot.web import build_app
from tests.test_device_credentials_postgres import databases, env as device_env, SECRET
from tests.test_device_keys import encoded


@pytest.fixture
def env(device_env):
    grant = Path(__file__).parents[1] / "deploy/grant_device_registration.sql"
    if grant.exists():
        with device_env.database.connect() as connection:
            role = connection.execute("SELECT current_user").fetchone()[0]
        with device_env.admin.connect() as connection:
            connection.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
            connection.execute(grant.read_text())
    try:
        yield device_env
    finally:
        with device_env.admin.connect() as connection:
            if connection.execute("SELECT to_regclass('pilot_device_registrations')").fetchone()[0]:
                connection.execute("DELETE FROM pilot_device_registrations WHERE tenant_id=ANY(%s)",
                                   (device_env.tenants,))


def client_for(env):
    client = TestClient(build_app(env.store, auth_secret=SECRET), base_url="https://pilot.example")
    client.headers["Authorization"] = "Bearer " + env.token
    return client


def test_http_registration_original_request_recovers_exact_device(env):
    value = {"request_id": str(uuid4()), "device_label": "  合成客户电脑  "}
    with client_for(env) as client:
        response = client.post("/api/ui/device-registrations", json=value)
        assert response.status_code == 201, response.text
        receipt = response.json()
        assert set(receipt) == {"request_id", "device_id", "device_label", "registered_at", "state"}
        assert receipt["request_id"] == value["request_id"]
        assert receipt["device_label"] == "合成客户电脑"
        assert receipt["state"] == "SUCCEEDED"
        assert response.headers["cache-control"] == "no-store"
        assert client.post("/api/ui/device-registrations", json=value).json() == receipt
    with client_for(env) as client:
        recovered = client.get("/api/ui/device-registration-requests/" + value["request_id"])
        assert recovered.status_code == 200, recovered.text
        assert recovered.json() == receipt
        current = client.get("/api/ui/devices/" + receipt["device_id"] + "/identity")
        assert current.status_code == 200, current.text
        assert current.json() == {"device_id": receipt["device_id"], "device_status": "ACTIVE",
                                  "credential_version": 0, "public_key": None}
        conflict = client.post("/api/ui/device-registrations", json=value | {"device_label": "不同电脑"})
        assert conflict.status_code == 409, conflict.text
        assert conflict.json()["detail"]["code"] == "request_conflict"
    with env.database.connect() as connection:
        assert connection.execute("SELECT rolsuper,rolbypassrls,rolcreaterole FROM pg_roles WHERE rolname=current_user").fetchone() == (False, False, False)
        assert connection.execute("SELECT row_security_active('pilot_device_registrations')").fetchone() == (True,)
    with env.admin.connect() as connection:
        assert connection.execute("SELECT count(*) FROM pilot_device_registrations WHERE tenant_id=%s AND owner_user_id=%s",
                                  (env.tenants[0], env.users[0])).fetchone() == (1,)
        # The shared fixture owns one pre-existing legacy device plus this one.
        assert connection.execute("SELECT count(*) FROM pilot_devices WHERE tenant_id=%s AND owner_user_id=%s",
                                  (env.tenants[0], env.users[0])).fetchone() == (2,)


def key_operation(client, device_id, key, *, operation="BIND", version=0, previous=None):
    public = None if operation == "PROVE" else encoded(key.verify_key.encode())
    path = f"/api/ui/devices/{device_id}/key-challenges"
    response = client.post(path, json={"request_id": str(uuid4()), "operation": operation,
        "expected_credential_version": version, "public_key": public})
    assert response.status_code == 200, response.text
    item = response.json()
    message = item["signing_payload"].encode()
    proof = {"signature": encoded(key.sign(message).signature)}
    if previous is not None:
        proof["previous_signature"] = encoded(previous.sign(message).signature)
    completed = client.post(path + "/" + item["challenge_id"] + "/complete", json=proof)
    assert completed.status_code == 200, completed.text
    assert completed.json()["state"] == "SUCCEEDED"
    return completed.json()


def test_http_registration_bind_prove_rotate_and_revoke_separate_history_from_current(env):
    body = {"request_id": str(uuid4()), "device_label": "合成设备完整身份链"}
    old_key, new_key = SigningKey.generate(), SigningKey.generate()
    with client_for(env) as client:
        registered = client.post("/api/ui/device-registrations", json=body)
        assert registered.status_code == 201, registered.text
        receipt = registered.json()
        device = receipt["device_id"]
        identity_path = f"/api/ui/devices/{device}/identity"
        receipt_path = "/api/ui/device-registration-requests/" + body["request_id"]
        assert key_operation(client, device, old_key)["credential_version"] == 1
        assert key_operation(client, device, old_key, operation="PROVE", version=1)["credential_version"] == 1
        assert client.get(identity_path).json() == {"device_id": device, "device_status": "ACTIVE",
            "credential_version": 1, "public_key": encoded(old_key.verify_key.encode())}
        assert key_operation(client, device, new_key, operation="ROTATE", version=1,
                             previous=old_key)["credential_version"] == 2
        current = client.get(identity_path)
        assert current.status_code == 200, current.text
        assert current.json() == {"device_id": device, "device_status": "ACTIVE",
            "credential_version": 2, "public_key": encoded(new_key.verify_key.encode())}
        assert client.get(receipt_path).json() == receipt
        assert client.post("/api/ui/device-registrations", json=body).json() == receipt
        revoked = client.post(f"/api/ui/devices/{device}/revoke")
        assert revoked.status_code == 200, revoked.text
        assert client.get(identity_path).json() == current.json() | {"device_status": "REVOKED"}
        assert client.get(receipt_path).json() == receipt
        assert client.post("/api/ui/device-registrations", json=body).json() == receipt
        new_proof = client.post(f"/api/ui/devices/{device}/key-challenges", json={
            "request_id": str(uuid4()), "operation": "PROVE", "expected_credential_version": 2,
            "public_key": None})
        assert new_proof.status_code == 404
        for private in (encoded(old_key.encode()), encoded(new_key.encode()), env.token):
            assert private not in registered.text + current.text


@pytest.mark.parametrize("user_index", [1, 2])
def test_http_registration_owner_scope_and_same_request_id_in_other_owner(env, user_index):
    body = {"request_id": str(uuid4()), "device_label": "相同标签不是身份"}
    with client_for(env) as client:
        original = client.post("/api/ui/device-registrations", json=body)
        assert original.status_code == 201, original.text
        receipt = original.json()
        foreign = {"Authorization": "Bearer " + issue_token(env.users[user_index], SECRET)}
        for path in ("/api/ui/device-registration-requests/" + body["request_id"],
                     "/api/ui/devices/" + receipt["device_id"] + "/identity"):
            response = client.get(path, headers=foreign)
            assert response.status_code == 404, response.text
            assert receipt["device_id"] not in response.text
        separate = client.post("/api/ui/device-registrations", json=body, headers=foreign)
        assert separate.status_code == 201, separate.text
        assert separate.json()["device_id"] != receipt["device_id"]
        assert client.get("/api/ui/device-registration-requests/" + body["request_id"]).json() == receipt


def test_http_registration_logout_then_new_session_can_recover(env):
    body = {"request_id": str(uuid4()), "device_label": "重新登录核对"}
    with client_for(env) as client:
        response = client.post("/api/ui/device-registrations", json=body)
        assert response.status_code == 201, response.text
        receipt = response.json()
        path = "/api/ui/device-registration-requests/" + body["request_id"]
        assert client.delete("/api/ui/session").status_code == 200
        assert client.get(path).status_code == 401
        assert client.get("/api/ui/devices/" + receipt["device_id"] + "/identity").status_code == 401
        assert client.post("/api/ui/device-registrations", json=body).status_code == 401
        new_session = {"Authorization": "Bearer " + issue_token(env.users[0], SECRET)}
        assert client.get(path, headers=new_session).json() == receipt


def test_http_legacy_device_route_remains_compatible_and_null_owner_is_not_claimed(env):
    with client_for(env) as client:
        response = client.post("/api/ui/devices", json={"device_label": "旧登记兼容"})
        assert response.status_code == 201, response.text
        assert set(response.json()) == {"device_id", "device_label", "status"}
        device = response.json()["device_id"]
        with env.admin.connect() as connection:
            connection.execute("UPDATE pilot_devices SET owner_user_id=NULL WHERE device_id=%s", (device,))
        assert client.get("/api/ui/devices/" + device + "/identity").status_code == 404
        unknown = client.get("/api/ui/device-registration-requests/" + str(uuid4()))
        assert unknown.status_code == 404
        assert unknown.json()["detail"]["code"] == "request_not_found"
        with env.admin.connect() as connection:
            assert connection.execute("SELECT owner_user_id FROM pilot_devices WHERE device_id=%s", (device,)).fetchone() == (None,)


@pytest.mark.parametrize("change", [
    {"request_id": "NOT-A-UUID"}, {"request_id": 42}, {"device_label": True}, {"device_label": None},
    {"device_label": "   "}, {"device_label": "x" * 129}, {"device_label": "bad\x00label"},
    {"owner_user_id": "synthetic-must-not-echo"}, {"device_label": "\ud800"},
])
def test_http_registration_invalid_fields_are_bounded_sanitized(env, change, caplog):
    body = {"request_id": str(uuid4()), "device_label": "有效合成标签"} | change
    with client_for(env) as client:
        response = client.post("/api/ui/device-registrations", content=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"})
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["code"] == "invalid_request"
        assert response.headers["cache-control"] == "no-store"
        assert "synthetic-must-not-echo" not in response.text + caplog.text
        assert env.token not in response.text + caplog.text


@pytest.mark.parametrize("content, content_type, status", [
    (b'{"device_label":"synthetic-must-not-echo","device_label":"two"}', "application/json", 422),
    (b'{"device_label":1e999}', "application/json", 422),
    (b'{"device_label":"\xff"}', "application/json", 422),
    (b'[]', "application/json", 422),
    (b'{}', "text/plain", 415),
    (b' ' * 4097, "application/json", 413),
])
def test_http_registration_strict_wire_format(env, content, content_type, status, caplog):
    with client_for(env) as client:
        response = client.post("/api/ui/device-registrations", content=content,
                               headers={"Content-Type": content_type})
        assert response.status_code == status, response.text
        assert response.headers["cache-control"] == "no-store"
        assert "synthetic-must-not-echo" not in response.text + caplog.text


def test_http_registration_requires_auth_https_and_same_origin(env):
    body = {"request_id": str(uuid4()), "device_label": "访问保护"}
    app = build_app(env.store, auth_secret=SECRET)
    with TestClient(app, base_url="https://pilot.example") as client:
        assert client.post("/api/ui/device-registrations", json=body).status_code == 401
        assert client.get("/api/ui/device-registration-requests/" + body["request_id"]).status_code == 401
        assert client.get("/api/ui/devices/" + env.device + "/identity").status_code == 401
        headers = {"Authorization": "Bearer " + env.token, "Origin": "https://foreign.invalid"}
        assert client.post("/api/ui/device-registrations", json=body, headers=headers).status_code == 403
    with TestClient(app, base_url="http://pilot.example") as client:
        response = client.post("/api/ui/device-registrations", json=body,
                               headers={"Authorization": "Bearer " + env.token})
        assert response.status_code == 400, response.text
