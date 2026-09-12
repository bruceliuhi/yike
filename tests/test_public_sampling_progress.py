"""Committed public sampling rounds; all records in this module are synthetic."""
import json
import os
import socket
import ssl
import threading
import time
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
import httpx
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
from nacl.signing import SigningKey
from psycopg import sql
from pydantic import ValidationError

from pilot.auth import TokenClaims, issue_token, verify_token_claims
from pilot.candidate_ingestion import CandidateIngestionStore
from pilot.db import PilotDatabase
from pilot.device_credentials import DeviceCredentialStore
from pilot.execution_contract import ExecutionOperation, ExecutionRuntimeError
from pilot.execution_runtime import ExecutionRuntime, execution_signing_payload
from pilot.foreground_collection import configured_collection_policy
from pilot.monitor_plans import MonitorPlanStore
from pilot.monitor_runtime import MonitorRuntime
from pilot.public_sampling_progress import committed_public_sampling_round
from pilot.research_strategies import ResearchStrategyStore
from pilot.store import PilotStore
from pilot.web import build_app
from tests.test_execution_api import RuntimeFixture, SECRET, auth_headers, client_for, operation_payload
from tests.test_candidate_ingestion_postgres import payload, submit
from tests.test_device_credentials_postgres import RoleDatabase, bind
from tests.test_device_keys import encoded
from tests.test_monitor_runtime_postgres import force_due_window, runtime_pulse
from tests.test_research_strategies_postgres import confirm_body, configuration, prepare_body
from tests.test_ui_api import FakeStore


def test_legacy_operation_serialization_and_signing_bytes_are_unchanged():
    body = operation_payload("CLAIM")
    operation = ExecutionOperation.model_validate(body)
    claims = TokenClaims(user_id="user", expires_at=2_000_000_000, revocation_key="a" * 64)

    assert operation.model_dump(mode="json") == body
    assert execution_signing_payload(tenant_id="tenant", claims=claims, operation=operation) == json.dumps(
        {
            "operation": body,
            "protocol": "yike-execution-operation-v1",
            "session_digest": "a" * 64,
            "tenant_id": "tenant",
            "user_id": "user",
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def test_sampling_version_one_is_serialized_only_for_claim():
    body = operation_payload("CLAIM") | {"public_sampling_version": 1}

    assert ExecutionOperation.model_validate(body).model_dump(mode="json") == body


@pytest.mark.parametrize("value", [None, True, 2, 0, "1"])
def test_sampling_version_rejects_null_bool_and_non_one_values(value):
    with pytest.raises((ValidationError, ExecutionRuntimeError)):
        ExecutionOperation.model_validate(operation_payload("CLAIM") | {"public_sampling_version": value})


@pytest.mark.parametrize("operation", ["START", "RENEW", "CANCEL"])
def test_sampling_version_is_rejected_outside_claim(operation):
    with pytest.raises((ValidationError, ExecutionRuntimeError)):
        ExecutionOperation.model_validate(operation_payload(operation) | {"public_sampling_version": 1})


class _SupportRuntime(RuntimeFixture):
    def __init__(self, policy):
        super().__init__()
        self.capability_check = policy
        cursor = SimpleNamespace()
        self.database = SimpleNamespace(connect=lambda: nullcontext(
            SimpleNamespace(cursor=lambda: nullcontext(cursor))))

    def _active(self, cursor, claims):
        self.calls.append(("active", claims))


def _support_client(mode="four-platform-public-project-monitor-v1"):
    runtime = _SupportRuntime(configured_collection_policy({"YIKE_PILOT_COLLECTION_MODE": mode}))
    return client_for(runtime), runtime


def test_support_preserves_legacy_shape_and_negotiates_only_exact_query():
    client, _ = _support_client()
    legacy = {
        "schema_version": "foreground-collection-support-v1",
        "mode": "four-platform-foreground-v1",
        "public_source": "v2ex-latest-v1",
        "public_sources": ["v2ex-latest-v1", "v2ex-qna-v1", "v2ex-outsourcing-authors-v1"],
        "public_monitor": True,
    }

    assert client.get("/api/ui/execution-support", headers=auth_headers()).json() == legacy
    assert client.get(
        "/api/ui/execution-support?sampling_version=1", headers=auth_headers()
    ).json() == legacy | {"public_sampling": "committed-round-v1"}


@pytest.mark.parametrize("query", ["sampling_version=2", "sampling_version=1&sampling_version=1", "extra=1"])
def test_support_rejects_non_exact_queries_after_authentication(query):
    client, runtime = _support_client()

    response = client.get(f"/api/ui/execution-support?{query}", headers=auth_headers())

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_request"
    assert runtime.calls and runtime.calls[0][0] == "active"


def test_support_query_requires_auth_and_does_not_advertise_without_public_monitor():
    client, _ = _support_client("four-platform-foreground-v1")

    assert client.get("/api/ui/execution-support?sampling_version=1").status_code == 401
    assert client.get(
        "/api/ui/execution-support?sampling_version=1", headers=auth_headers()
    ).json() == {
        "schema_version": "foreground-collection-support-v1",
        "mode": "four-platform-foreground-v1",
    }


def test_progress_helper_rejects_native_platform_without_querying():
    with pytest.raises(ExecutionRuntimeError, match="capability_unavailable"):
        committed_public_sampling_round(
            None, tenant_id="tenant", owner_user_id="user", task={},
            platform={"platform": "BILIBILI", "access_mode": "PLATFORM_ACCOUNT"},
        )


def test_progress_helper_rejects_non_monitor_snapshot():
    class Cursor:
        def execute(self, statement, params):
            self.statement, self.params = statement, params

        @staticmethod
        def fetchone():
            return str(uuid4()), {"configuration": {
                "mode": "once", "publicSource": "v2ex-qna-v1",
            }}

    cursor = Cursor()
    with pytest.raises(ExecutionRuntimeError, match="capability_unavailable"):
        committed_public_sampling_round(
            cursor, tenant_id="tenant", owner_user_id="user",
            task={"task_id": "task"},
            platform={"platform": "PUBLIC_WEB", "access_mode": "PUBLIC_ANONYMOUS",
                      "run_id": "run", "platform_run_id": "platform-run"},
        )


@pytest.fixture(scope="module")
def sampling_databases():
    value = os.environ.get("YIKE_PUBLIC_SAMPLING_TEST_DATABASE_URL")
    if not value:
        pytest.skip("dedicated public-sampling PostgreSQL required")
    url = urlsplit(value)
    assert url.hostname == "127.0.0.1" and url.path == "/yike_public_sampling_task1"
    admin = PilotDatabase(value)
    admin.migrate()
    role = "public_sampling_" + uuid4().hex
    root = Path(__file__).parents[1]
    with admin.connect() as connection:
        connection.execute(sql.SQL(
            "CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
        ).format(sql.Identifier(role)))
        connection.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
        for line in (root / "deploy/grant_runtime.sql").read_text().splitlines():
            if line.startswith("\\ir "):
                connection.execute((root / "deploy" / line.split()[1]).read_text())
    yield admin, RoleDatabase(admin, role)
    with admin.connect() as connection:
        connection.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
        connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def _sampling_env(databases, *, tenant=None, user=None, profile=None, label="main"):
    admin, database = databases
    provisioner = PilotStore(admin)
    tenant = tenant or provisioner.provision_tenant("synthetic-public-sampling-" + label)
    user = user or provisioner.provision_user(tenant, f"{uuid4()}@example.invalid")
    token = issue_token(user, "synthetic-public-sampling")
    claims = verify_token_claims(token, "synthetic-public-sampling")
    store = PilotStore(database)
    device = store.register_device(user, "synthetic-public-sampling")["device_id"]
    key = SigningKey.generate()
    bind(SimpleNamespace(service=DeviceCredentialStore(database), claims=claims, device=device), key)
    if profile is None:
        profile = provisioner.save_profile(user, {"description": "合成公开来源抽样"})["version_id"]
        provisioner.confirm_profile(user, profile)
    seed = SimpleNamespace(profile=profile)
    schedule = {
        "kind": "interval", "times": [], "interval": 1, "start": "00:00", "end": "23:59",
        "timezone": "UTC", "policyVersion": 1,
    }
    strategies = ResearchStrategyStore(database)
    prepared = strategies.prepare(claims, prepare_body(seed, configuration=configuration(
        name="抽样-" + label, mode="monitor", schedule=schedule,
        publicSource="v2ex-qna-v1", keywords=["企业软件"], exclusions=[])))
    confirmed = strategies.confirm(claims, confirm_body(prepared))
    plans = MonitorPlanStore(database, strategy_resolver=strategies.resolve)
    plan = plans.create(claims, {
        "schema_version": "monitor-plans-v1", "request_id": str(uuid4()),
        "profile_version_id": profile, "strategy_version_id": confirmed["strategy_version_id"],
        "human_confirmed": True,
    })["plan"]
    execution = ExecutionRuntime(
        database,
        strategy_resolver=strategies.resolve,
        capability_check=configured_collection_policy({
            "YIKE_PILOT_COLLECTION_MODE": "four-platform-public-node-monitor-v1"
        }),
    )
    monitor = MonitorRuntime(database, execution)
    execution.monitor_runtime = monitor
    return SimpleNamespace(
        admin=admin, db=database, store=store, tenant=tenant, user=user, token=token,
        claims=claims, device=device, key=key, profile=profile, snapshot=confirmed["snapshot"],
        plan=plan, execution=execution, monitor=monitor,
        target={"platform": "PUBLIC_WEB", "access_mode": "PUBLIC_ANONYMOUS",
                "connection_id": None, "connection_version": None},
    )


def _sign_apply(env, body):
    operation = ExecutionOperation.model_validate(body)
    signature = encoded(env.key.sign(execution_signing_payload(
        tenant_id=env.tenant, claims=env.claims, operation=operation
    ).encode()).signature)
    return env.execution.apply(env.claims, operation, signature)


def _begin_sampling_claim(env, session, *, client=None):
    env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    force_due_window(env)
    ready = env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    begun = _sign_apply(env, ready["occurrence"]["start_request"])
    request = {
        "schema_version": "execution-runtime-v1", "request_id": str(uuid4()), "operation": "CLAIM",
        "device_id": env.device, "credential_version": 1, "profile_version_id": None,
        "strategy_version_id": None, "configuration_sha256": None, "targets": None,
        "task_id": begun["task_id"], "platform_run_id": begun["platform_runs"][0]["platform_run_id"],
        "lease_id": None, "execution_generation": None, "public_sampling_version": 1,
    }
    if client is None:
        return begun, request, _sign_apply(env, request)
    operation = ExecutionOperation.model_validate(request)
    signature = encoded(env.key.sign(execution_signing_payload(
        tenant_id=env.tenant, claims=env.claims, operation=operation
    ).encode()).signature)
    response = client.post("/api/ui/execution-operations", json={"request": request, "signature": signature})
    assert response.status_code == 200, response.text
    return begun, request, response.json()


@contextmanager
def _authenticated_https_client(env, tmp_path):
    cert, private_key = tmp_path / "cert.pem", tmp_path / "key.pem"
    tls_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.now(UTC)
    tls_cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                .public_key(tls_key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
                .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip_address("127.0.0.1"))]), False)
                .sign(tls_key, hashes.SHA256()))
    private_key.write_bytes(tls_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    cert.write_bytes(tls_cert.public_bytes(serialization.Encoding.PEM))
    app = build_app(
        env.store, auth_secret="synthetic-public-sampling", execution_runtime=env.execution,
        candidate_ingestion=CandidateIngestionStore(env.db, env.execution),
    )
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(32)
        base_url = f"https://127.0.0.1:{listener.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(
            app, log_level="critical", access_log=False, lifespan="off",
            ssl_certfile=str(cert), ssl_keyfile=str(private_key),
        ))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert server.started
            with httpx.Client(
                base_url=base_url, verify=ssl.create_default_context(cafile=str(cert)), trust_env=False,
                timeout=10, headers={"Authorization": "Bearer " + env.token, "Origin": base_url},
            ) as client:
                yield client
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive()


def _upload_and_close(env, begun, lease, *, empty=False, finish=False):
    value = payload(env, begun, lease)
    if empty:
        value["records"] = []
    receipt = submit(env, CandidateIngestionStore(env.db, env.execution), value)
    assert submit(env, CandidateIngestionStore(env.db, env.execution), value) == receipt
    if finish:
        _sign_apply(env, {
            "schema_version": "execution-runtime-v1", "request_id": str(uuid4()), "operation": "FINISH",
            "device_id": env.device, "credential_version": 1, "profile_version_id": None,
            "strategy_version_id": None, "configuration_sha256": None, "targets": None,
            "task_id": begun["task_id"], "platform_run_id": lease["platform_run_id"],
            "lease_id": lease["lease_id"], "execution_generation": lease["execution_generation"],
            "upload_request_id": value["request_id"],
        })
    else:
        with env.admin.connect() as connection:
            for table in ("pilot_collection_tasks", "pilot_collection_runs", "pilot_collection_platform_runs"):
                connection.execute(
                    f"UPDATE {table} SET status='CANCELED' WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s",
                    (env.tenant, env.user, begun["task_id"]),
                )
    env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=str(uuid4())))
    return receipt


def test_real_pg_round_counts_distinct_committed_batches_and_isolates_owner_and_plan(
        sampling_databases, tmp_path):
    env = _sampling_env(sampling_databases)
    session = str(uuid4())
    with _authenticated_https_client(env, tmp_path) as client:
        assert client.get("/api/ui/execution-support?sampling_version=1").json()["public_sampling"] == \
            "committed-round-v1"
        begun0, request0, lease0 = _begin_sampling_claim(env, session, client=client)
    assert lease0["public_sampling"] == {
        "schema_version": "public-sampling-round-v1", "plan_id": env.plan["plan_id"],
        "source_id": "v2ex-qna-v1", "round": 0,
    }
    assert _sign_apply(env, request0) == lease0
    _upload_and_close(env, begun0, lease0)
    assert _sign_apply(env, request0) == lease0  # Commit cannot rewrite the persisted CLAIM round.

    other_owner = _sampling_env(sampling_databases, tenant=env.tenant, label="other-owner")
    other_begun, _, other_lease = _begin_sampling_claim(other_owner, str(uuid4()))
    _upload_and_close(other_owner, other_begun, other_lease)
    other_plan = _sampling_env(
        sampling_databases, tenant=env.tenant, user=env.user, profile=env.profile, label="other-plan"
    )
    other_begun, _, other_lease = _begin_sampling_claim(other_plan, str(uuid4()))
    _upload_and_close(other_plan, other_begun, other_lease)

    begun1, _, lease1 = _begin_sampling_claim(env, session)
    assert lease1["public_sampling"]["round"] == 1
    _upload_and_close(env, begun1, lease1, empty=True, finish=True)

    begun2, request2, lease2 = _begin_sampling_claim(env, session)
    assert lease2["public_sampling"]["round"] == 2
    assert _sign_apply(env, request2) == lease2
    with env.admin.connect() as connection:
        for table in ("pilot_collection_tasks", "pilot_collection_runs", "pilot_collection_platform_runs"):
            connection.execute(
                f"UPDATE {table} SET status='CANCELED' WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s",
                (env.tenant, env.user, begun2["task_id"]),
            )
    env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=str(uuid4())))
    _, _, lease3 = _begin_sampling_claim(env, session)
    assert lease3["public_sampling"]["round"] == 2  # A terminated run without a batch does not advance.
    with env.admin.connect() as connection:
        assert connection.execute(
            "SELECT count(*) FROM pilot_candidate_batches WHERE tenant_id=%s AND owner_user_id=%s",
            (env.tenant, env.user),
        ).fetchone() == (3,)  # Two own-plan batches plus the isolated other-plan batch.

    artifact = os.environ.get("YIKE_PUBLIC_SAMPLING_HTTP_ARTIFACT")
    if artifact:
        Path(artifact).write_text(json.dumps(
            {"request": request0, "response": lease0}, ensure_ascii=False, indent=2, sort_keys=True
        ) + "\n")
