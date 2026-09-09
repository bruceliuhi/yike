"""Synthetic transport boundaries; real restricted-PG integration is separate."""
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from pilot.auth import issue_token
from pilot.web import build_app
from tests.test_ui_api import FakeStore


SECRET = "synthetic-execution-transport-secret"
SIGNATURE = "A" * 86


def start_payload():
    return {
        "schema_version": "execution-runtime-v1",
        "request_id": str(uuid4()),
        "device_id": str(uuid4()),
        "credential_version": 1,
        "operation": "START",
        "profile_version_id": str(uuid4()),
        "strategy_version_id": str(uuid4()),
        "configuration_sha256": "a" * 64,
        "targets": [{"platform": "PUBLIC_WEB", "access_mode": "PUBLIC_ANONYMOUS",
                     "connection_id": None, "connection_version": None}],
        "task_id": None, "platform_run_id": None, "lease_id": None,
        "execution_generation": None,
    }


def operation_payload(operation):
    payload = start_payload()
    if operation == "START":
        return payload
    payload.update(
        operation=operation,
        profile_version_id=None,
        strategy_version_id=None,
        configuration_sha256=None,
        targets=None,
        task_id="task-1",
        platform_run_id=None if operation == "CANCEL" else "platform-run-1",
        lease_id="lease-1" if operation == "RENEW" else None,
        execution_generation=1 if operation == "RENEW" else None,
    )
    return payload


def auth_headers():
    return {"Authorization": "Bearer " + issue_token("user-1", SECRET)}


def envelope():
    return {"request": start_payload(), "signature": SIGNATURE}


class RuntimeFixture:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def apply(self, claims, request, signature):
        self.calls.append(("apply", claims, request, signature))
        if self.error:
            raise self.error
        return {"request_id": request.request_id, "status": "PENDING"}

    def prepare_signing_payload(self, claims, request):
        self.calls.append(("prepare", claims, request))
        if self.error:
            raise self.error
        return {
            "signing_payload": "synthetic-signing-payload",
            "request_id": request.request_id,
            "device_id": request.device_id,
            "credential_version": request.credential_version,
            "request_sha256": "b" * 64,
        }

    def get_receipt(self, claims, request_id):
        self.calls.append(("receipt", claims, request_id))
        if self.error:
            raise self.error
        return {"request_id": request_id, "status": "PENDING"}

    def get_task(self, claims, task_id):
        self.calls.append(("task", claims, task_id))
        if self.error:
            raise self.error
        return {"task_id": task_id, "status": "PENDING"}


def client_for(runtime, base_url="https://pilot.example"):
    return TestClient(build_app(FakeStore(), auth_secret=SECRET,
                               execution_runtime=runtime), base_url=base_url)


def test_absent_runtime_has_explicit_unavailable_routes_and_no_execution_claim():
    client = TestClient(build_app(FakeStore(), auth_secret=SECRET),
                        base_url="https://pilot.example")
    for method, path, payload in [
        ("POST", "/api/ui/execution-signing-payload", {"request": start_payload()}),
        ("POST", "/api/ui/execution-operations", envelope()),
        ("GET", "/api/ui/execution-operations/" + str(uuid4()), None),
        ("GET", "/api/ui/execution-tasks/" + str(uuid4()), None),
    ]:
        response = client.request(method, path, json=payload, headers=auth_headers())
        assert response.status_code == 501
        assert response.json()["detail"]["code"] == "capability_unavailable"
        assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/ui/capabilities").json()["capabilities"]["task_execution"] == {"available": False}


def test_signing_preparation_route_uses_authenticated_claims():
    runtime = RuntimeFixture()
    body = {"request": start_payload()}
    response = client_for(runtime).post(
        "/api/ui/execution-signing-payload", json=body, headers=auth_headers()
    )

    assert response.status_code == 200
    assert response.json() == {
        "signing_payload": "synthetic-signing-payload",
        "request_id": body["request"]["request_id"],
        "device_id": body["request"]["device_id"],
        "credential_version": 1,
        "request_sha256": "b" * 64,
    }
    call = runtime.calls[0]
    assert call[0] == "prepare"
    assert call[1].user_id == "user-1"
    assert call[1].revocation_key and call[1].expires_at
    assert call[2].model_dump(mode="json") == body["request"]
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("operation", ["START", "CLAIM", "RENEW", "CANCEL"])
def test_signing_preparation_route_accepts_each_operation_without_claiming_execution(operation):
    runtime = RuntimeFixture()
    request = operation_payload(operation)

    response = client_for(runtime).post(
        "/api/ui/execution-signing-payload",
        json={"request": request},
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["request_id"] == request["request_id"]
    assert [(call[0], call[2].operation) for call in runtime.calls] == [("prepare", operation)]


def test_fixed_routes_forward_authenticated_claims_and_validated_operation():
    runtime = RuntimeFixture()
    client = client_for(runtime)
    body = envelope()
    response = client.post("/api/ui/execution-operations", json=body, headers=auth_headers())
    assert response.status_code == 200
    assert response.json() == {"request_id": body["request"]["request_id"], "status": "PENDING"}
    call = runtime.calls[0]
    assert call[0] == "apply" and call[1].user_id == "user-1"
    assert call[1].revocation_key and call[1].expires_at
    assert call[2].model_dump(mode="json") == body["request"]
    assert call[3] == SIGNATURE
    rid, tid = body["request"]["request_id"], str(uuid4())
    assert client.get("/api/ui/execution-operations/" + rid, headers=auth_headers()).json()["request_id"] == rid
    assert client.get("/api/ui/execution-tasks/" + tid, headers=auth_headers()).json()["task_id"] == tid
    assert [call[0] for call in runtime.calls] == ["apply", "receipt", "task"]
    assert all(call[1].user_id == "user-1" for call in runtime.calls)
    assert client.get("/api/ui/capabilities").json()["capabilities"]["task_execution"] == {"available": False}


@pytest.mark.parametrize("change", ["tenant", "budget", "signature", "secret", "body_type"])
def test_invalid_envelopes_never_reach_runtime_or_echo_input(change):
    runtime = RuntimeFixture()
    client = client_for(runtime)
    body = envelope()
    if change == "tenant":
        body["request"]["tenant_id"] = "synthetic-private-value"
    elif change == "budget":
        body["request"]["max_records"] = 999999
    elif change == "signature":
        body["signature"] = "synthetic-private-value"
    elif change == "secret":
        body["token"] = "synthetic-private-value"
    else:
        body["request"] = "synthetic-private-value"
    response = client.post("/api/ui/execution-operations", json=body, headers=auth_headers())
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_request"
    assert "synthetic-private-value" not in response.text
    assert SIGNATURE not in response.text
    assert not runtime.calls


def test_auth_https_origin_and_revocation_gate_before_execution():
    runtime = RuntimeFixture()
    client = client_for(runtime)
    body = envelope()
    assert client.post("/api/ui/execution-operations", json=body).status_code == 401
    assert client.get("/api/ui/execution-tasks/" + str(uuid4())).status_code == 401
    assert client_for(runtime, "http://pilot.example").post(
        "/api/ui/execution-operations", json=body, headers=auth_headers()).status_code == 400
    assert client.post("/api/ui/execution-operations", json=body,
                       headers=auth_headers() | {"Origin": "https://foreign.example"}).status_code == 403
    token = issue_token("user-1", SECRET)
    headers = {"Authorization": "Bearer " + token}
    assert client.delete("/api/ui/session", headers=headers).status_code == 200
    assert client.post("/api/ui/execution-operations", json=body, headers=headers).status_code == 401
    assert not runtime.calls


def test_auth_https_origin_and_revocation_gate_before_signing_preparation():
    runtime = RuntimeFixture()
    client = client_for(runtime)
    body = {"request": start_payload()}
    path = "/api/ui/execution-signing-payload"

    assert client.post(path, json=body).status_code == 401
    assert client_for(runtime, "http://pilot.example").post(
        path, json=body, headers=auth_headers()
    ).status_code == 400
    assert client.post(
        path, json=body, headers=auth_headers() | {"Origin": "https://foreign.example"}
    ).status_code == 403
    token = issue_token("user-1", SECRET)
    headers = {"Authorization": "Bearer " + token}
    assert client.delete("/api/ui/session", headers=headers).status_code == 200
    assert client.post(path, json=body, headers=headers).status_code == 401
    assert not runtime.calls


@pytest.mark.parametrize(
    "change",
    [
        "request_tenant",
        "outer_tenant",
        "outer_user",
        "outer_session",
        "outer_token",
        "outer_signature",
        "outer_extra",
        "boolean_credential",
        "bad_shape",
    ],
)
def test_invalid_signing_preparation_envelopes_never_reach_runtime_or_echo_input(change):
    runtime = RuntimeFixture()
    body = {"request": start_payload()}
    private = "synthetic-private-value"
    if change == "request_tenant":
        body["request"]["tenant_id"] = private
    elif change == "outer_tenant":
        body["tenant_id"] = private
    elif change == "outer_user":
        body["user_id"] = private
    elif change == "outer_session":
        body["session_digest"] = private
    elif change == "outer_token":
        body["token"] = private
    elif change == "outer_signature":
        body["signature"] = private
    elif change == "outer_extra":
        body["extra"] = private
    elif change == "boolean_credential":
        body["request"]["credential_version"] = True
    else:
        body["request"] = private

    response = client_for(runtime).post(
        "/api/ui/execution-signing-payload", json=body, headers=auth_headers()
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_request"
    assert private not in response.text
    assert not runtime.calls


def test_signing_preparation_domain_error_stays_stable_and_payload_free(caplog):
    from pilot.execution_contract import ExecutionRuntimeError

    runtime = RuntimeFixture(ExecutionRuntimeError("credential_conflict"))
    response = client_for(runtime).post(
        "/api/ui/execution-signing-payload",
        json={"request": start_payload()},
        headers=auth_headers(),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "credential_conflict"
    assert response.headers["cache-control"] == "no-store"
    assert "synthetic-signing-payload" not in response.text + caplog.text


def test_unexpected_signing_preparation_failure_is_safe_unknown(caplog):
    runtime = RuntimeFixture(RuntimeError("synthetic-private-value"))
    response = client_for(runtime).post(
        "/api/ui/execution-signing-payload",
        json={"request": start_payload()},
        headers=auth_headers(),
    )

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "internal_error"
    assert "synthetic-private-value" not in response.text + caplog.text
    assert len(runtime.calls) == 1


@pytest.mark.parametrize("code,status", [("request_conflict", 409), ("request_not_found", 404),
                                        ("invalid_session", 401), ("capability_unavailable", 501)])
def test_domain_errors_stay_stable_and_do_not_expose_payload(code, status, caplog):
    from pilot.execution_contract import ExecutionRuntimeError
    runtime = RuntimeFixture(ExecutionRuntimeError(code, status))
    response = client_for(runtime).post("/api/ui/execution-operations", json=envelope(), headers=auth_headers())
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert response.headers["cache-control"] == "no-store"
    assert SIGNATURE not in response.text + caplog.text


def test_unexpected_failure_is_safe_unknown_not_a_success_or_retry(caplog):
    runtime = RuntimeFixture(RuntimeError("synthetic-private-value"))
    response = client_for(runtime).post("/api/ui/execution-operations", json=envelope(), headers=auth_headers())
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "internal_error"
    assert "synthetic-private-value" not in response.text + caplog.text
    assert len(runtime.calls) == 1


def test_invalid_lookup_ids_do_not_reach_runtime():
    runtime = RuntimeFixture()
    client = client_for(runtime)
    for path in ("/api/ui/execution-operations/not-a-uuid", "/api/ui/execution-tasks/not-a-uuid"):
        response = client.get(path, headers=auth_headers())
        assert response.status_code == 422
    assert not runtime.calls
