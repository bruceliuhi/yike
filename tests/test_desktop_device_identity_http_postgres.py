"""Actual Node journal/vault/coordinator -> socket HTTP -> restricted PostgreSQL.

Users and the Node protection adapter are synthetic. No external platform,
Windows safeStorage, normal renderer assembly, sending, or production proof.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time

import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
import uvicorn

from pilot.auth import issue_token
from pilot.db import PilotDatabase
from pilot.web import build_app
from tests.test_desktop_opportunity_http_postgres import _node_environment
from tests.test_device_credentials_postgres import env as device_env, SECRET
from tests.test_device_registration_http_postgres import env

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def databases():
    admin_url = os.environ.get("YIKE_IDENTITY_TEST_DATABASE_URL")
    app_url = os.environ.get("YIKE_IDENTITY_TEST_APP_DATABASE_URL")
    if not admin_url or not app_url:
        pytest.skip("dedicated identity PostgreSQL required")
    admin, app = PilotDatabase(admin_url), PilotDatabase(app_url)
    admin.migrate()
    parts = conninfo_to_dict(app_url)
    role = parts["user"]
    with admin.connect() as connection:
        assert not connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone(), "fresh app role required"
        connection.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {}").format(
            sql.Identifier(role), sql.Literal(parts["password"])))
        connection.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
        connection.execute((ROOT / "deploy/grant_device_credentials.sql").read_text())
    with app.connect() as connection:
        assert connection.execute("SELECT rolsuper,rolbypassrls,rolcreaterole FROM pg_roles WHERE rolname=current_user").fetchone() == (False, False, False)
        assert connection.execute("SELECT row_security_active('pilot_devices')").fetchone() == (True,)
    return admin, app


def test_actual_device_coordinator_recovers_registration_and_proof(env):
    node = os.environ.get("YIKE_DEVICE_LIVE_NODE_BINARY") or shutil.which("node")
    if not node:
        pytest.skip("Node 24 required")
    child_env = _node_environment()
    version = subprocess.run([node, "--version"], env=child_env, capture_output=True, text=True, timeout=10, check=True)
    assert version.stdout.strip().startswith("v24."), "Node 24 required"
    tokens = (issue_token(env.users[0], SECRET), issue_token(env.users[0], SECRET), issue_token(env.users[1], SECRET))
    app = build_app(env.store, auth_secret=SECRET, dev_login=True)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(64)
        server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False, lifespan="off"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert server.started and thread.is_alive(), "isolated device HTTP server failed to start"
            child_env.update(YIKE_DEVICE_LIVE_BASE=f"http://127.0.0.1:{listener.getsockname()[1]}",
                YIKE_DEVICE_LIVE_USER=env.users[0], YIKE_DEVICE_LIVE_TOKEN=tokens[0],
                YIKE_DEVICE_LIVE_NEXT_TOKEN=tokens[1], YIKE_DEVICE_LIVE_PEER_TOKEN=tokens[2])
            assert not any("DATABASE" in key.upper() or key.upper().startswith("POSTGRES_") or "SECRET" in key.upper() for key in child_env)
            try:
                child = subprocess.run([node, "node_modules/vitest/vitest.mjs", "run",
                    "tests/integration/device-identity-live.test.ts", "--pool=threads", "--maxWorkers=1", "--no-file-parallelism"],
                    cwd=ROOT / "desktop", env=child_env, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=50)
            except subprocess.TimeoutExpired:
                pytest.fail("device HTTP Node child timed out", pytrace=False)
            output = child.stdout + child.stderr
            for token in tokens:
                output = output.replace(token, "[redacted]")
            assert child.returncode == 0, output
            assert "1 passed" in output and "skipped" not in output.lower(), output
            records = [line.split("DEVICE_LIVE_RESULT:", 1)[1] for line in output.splitlines() if "DEVICE_LIVE_RESULT:" in line]
            assert len(records) == 1, output
            result = json.loads(records[0])
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive(), "isolated device HTTP server failed to stop"
    with env.admin.connect() as connection:
        assert connection.execute("SELECT count(*) FROM pilot_device_registrations WHERE tenant_id=%s AND owner_user_id=%s",
            (env.tenants[0], env.users[0])).fetchone() == (1,)
        registered = connection.execute("SELECT device_id,device_label FROM pilot_device_registrations WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s",
            (env.tenants[0], env.users[0], result["registrationId"])).fetchone()
        assert registered == (result["deviceId"], "合成 Windows 客户端")
        assert connection.execute("SELECT count(*) FROM pilot_devices WHERE tenant_id=%s AND owner_user_id=%s",
            (env.tenants[0], env.users[0])).fetchone() == (2,)  # one legacy fixture device, one registered by Node
        assert connection.execute("SELECT status FROM pilot_devices WHERE tenant_id=%s AND device_id=%s",
            (env.tenants[0], result["deviceId"])).fetchone() == ("REVOKED",)
        proofs = connection.execute("SELECT request_id,operation,state,result_version,session_digest FROM pilot_device_key_requests WHERE tenant_id=%s AND device_id=%s ORDER BY operation",
            (env.tenants[0], result["deviceId"])).fetchall()
        assert [row[:4] for row in proofs] == [(result["bindRequestId"], "BIND", "SUCCEEDED", 1), (result["proveRequestId"], "PROVE", "SUCCEEDED", 1)]
        assert proofs[0][4] != proofs[1][4]
        key, version = connection.execute("SELECT public_key,credential_version FROM pilot_device_credentials WHERE tenant_id=%s AND device_id=%s",
            (env.tenants[0], result["deviceId"])).fetchone()
        assert version == 1
        assert hashlib.sha256(key.encode()).hexdigest() == result["publicKeyHash"]
