"""Restricted PostgreSQL coverage snapshots; all source content is synthetic."""
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time
from uuid import uuid4

import pytest
import uvicorn

from pilot.auth import issue_token, verify_token_claims
from pilot.candidate_ingestion import CandidateIngestionStore
from pilot.execution_contract import ExecutionRuntimeError
from pilot.web import build_app
from tests.test_candidate_ingestion_postgres import payload, submit
from tests.test_confirmed_strategy_review_postgres import (
    databases, env, execution_databases, execution_env, raw_databases, raw_env,
    real_strategy_env,
)
from tests.test_execution_runtime_postgres import SECRET, apply, claimed, operation
from tests.test_desktop_opportunity_http_postgres import _node_environment


def query(env, task_id, **changes):
    value = {
        "contractVersion": 1,
        "requestId": str(uuid4()),
        "taskId": task_id,
        "profileId": env.profile,
        "profileVersion": env.profile_number,
        "expectedScope": {
            "userId": env.claims.user_id,
            "accountScopeId": env.tenant,
            "scopeVersion": 1,
        },
    }
    value.update(changes)
    return value


def test_real_signed_observations_are_counted_without_claiming_complete(real_strategy_env):
    from pilot.search_coverage import SearchCoverageService

    env = real_strategy_env
    begun, lease = claimed(env)
    ingestion = CandidateIngestionStore(env.db, env.runtime)
    batch = payload(env, begun, lease)
    original = batch["records"][0]
    batch["records"] = [original,
                        original | {"public_url": "https://example.com/independent", "body": "independent"}]
    submit(env, ingestion, batch)
    repeated = payload(env, begun, lease)
    repeated["records"][0].update(body="same source, later observation", observed_at="2026-01-01T00:00:01Z")
    submit(env, ingestion, repeated)
    apply(env, operation(env, "FINISH", begun, lease_id=lease["lease_id"],
                         execution_generation=lease["execution_generation"],
                         upload_request_id=repeated["request_id"]))

    before = {}
    with env.admin.connect() as connection:
        for table in ("pilot_collection_tasks", "pilot_candidate_observations"):
            before[table] = connection.execute(
                f"SELECT count(*) FROM {table} WHERE tenant_id=%s", (env.tenant,)
            ).fetchone()[0]
    result = SearchCoverageService(env.db).query(env.claims, query(env, begun["task_id"]))
    assert result["coverage"] == "PARTIAL" and result["screening"] == "UNKNOWN"
    assert result["profileId"] == query(env, begun["task_id"])["profileId"]
    assert result["profileVersion"] == env.profile_number
    assert result["configurationRevision"] == env.confirmed["draft_revision"]
    assert result["units"][0]["coverage"] == "PARTIAL"
    assert result["units"][0]["counts"] == {
        "requests": None, "rawContents": 3, "duplicates": 1,
        "independentSources": 2, "newCandidates": None,
        "confirmedOpportunities": None, "pendingReviews": None,
    }
    assert len(result["units"][0]["evidence"]) == 2
    assert result["usage"] is None and result["units"][0]["unchecked"]
    with env.admin.connect() as connection:
        assert before == {table: connection.execute(
            f"SELECT count(*) FROM {table} WHERE tenant_id=%s", (env.tenant,)
        ).fetchone()[0] for table in before}
    _run_node_http(env, begun["task_id"], raw=3, sources=2,
                   body="same source, later observation")


def test_empty_running_scope_is_unknown_and_bindings_fail_closed(real_strategy_env):
    from pilot.search_coverage import SearchCoverageError, SearchCoverageService

    env = real_strategy_env
    begun, _ = claimed(env)
    service = SearchCoverageService(env.db)
    result = service.query(env.claims, query(env, begun["task_id"]))
    assert result["coverage"] == "RUNNING"
    assert result["units"][0]["screening"] == "UNKNOWN"
    assert result["units"][0]["counts"]["rawContents"] == 0
    cases = [
        query(env, begun["task_id"], profileVersion=env.profile_number + 1),
        query(env, begun["task_id"], contractVersion=True),
        query(env, begun["task_id"], requestId="not-a-canonical-uuid"),
        query(env, begun["task_id"], expectedScope={"userId": env.users[1], "accountScopeId": env.tenant, "scopeVersion": 1}),
        query(env, str(uuid4())),
    ]
    for request in cases:
        with pytest.raises(SearchCoverageError):
            service.query(env.claims, request)
    other = verify_token_claims(issue_token(env.users[1], SECRET), SECRET)
    with pytest.raises(SearchCoverageError, match="task_not_found"):
        service.query(other, query(env, begun["task_id"], expectedScope={
            "userId": env.users[1], "accountScopeId": env.tenant, "scopeVersion": 1}))


def test_feed_uses_historical_profile_number(real_strategy_env):
    env = real_strategy_env
    begun, _ = claimed(env)
    item = env.runtime.get_task_feed_item(env.claims, begun["task_id"])
    assert item["profile_version"] == env.profile_number


def test_deadline_only_marks_a_still_running_direction_as_expired():
    from pilot.search_coverage import SearchCoverageService

    now = datetime.now(UTC)
    task = {"generated_at": now, "deadline_at": now - timedelta(seconds=1),
            "configuration_snapshot": {"configuration": {"keywords": ["synthetic"]}}}
    base = {"platform_run_id": str(uuid4()), "platform": "PUBLIC_WEB",
            "raw_contents": 1, "independent_sources": 1, "evidence": []}
    assert SearchCoverageService._unit(SearchCoverageService, task, base | {"status": "RUNNING"})["stopReason"] == "LIMIT_REACHED"
    assert SearchCoverageService._unit(SearchCoverageService, task, base | {"status": "SUCCEEDED"})["stopReason"] == "UNKNOWN"
    assert SearchCoverageService._unit(SearchCoverageService, task, base | {"status": "CANCELED"})["stopReason"] == "CANCELED"


def _run_node_http(env, task_id, *, raw, sources, body):
    node = os.environ.get("YIKE_DEVICE_LIVE_NODE_BINARY") or shutil.which("node")
    if not node:
        pytest.skip("Node 24 required for coverage live contract")
    child_env = _node_environment()
    version = subprocess.run([node, "--version"], env=child_env, capture_output=True,
                             text=True, timeout=10, check=True)
    assert version.stdout.strip().startswith("v24.")
    token = issue_token(env.claims.user_id, SECRET)
    app = build_app(env.store, auth_secret=SECRET, dev_login=True,
                    execution_runtime=env.runtime, research_strategies=env.strategies)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0)); listener.listen(64)
        server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False, lifespan="off"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert server.started and thread.is_alive()
            child_env.update(YIKE_COVERAGE_LIVE_BASE=f"http://127.0.0.1:{listener.getsockname()[1]}",
                YIKE_COVERAGE_LIVE_USER=env.claims.user_id, YIKE_COVERAGE_LIVE_TOKEN=token,
                YIKE_COVERAGE_LIVE_TASK=task_id, YIKE_COVERAGE_LIVE_RAW=str(raw),
                YIKE_COVERAGE_LIVE_SOURCES=str(sources), YIKE_COVERAGE_LIVE_BODY=body)
            assert not any("DATABASE" in key.upper() or key.upper().startswith("POSTGRES_") for key in child_env)
            child = subprocess.run([node, "node_modules/vitest/vitest.mjs", "run",
                "tests/integration/search-coverage-live.test.ts", "--maxWorkers=1"],
                cwd=Path(__file__).parents[1] / "desktop", env=child_env,
                capture_output=True, text=True, timeout=50)
            output = (child.stdout + child.stderr).replace(token, "[redacted]")
            assert child.returncode == 0, output
            assert "1 passed" in output and "skipped" not in output.lower(), output
        finally:
            server.should_exit = True; thread.join(timeout=10)
            assert not thread.is_alive()
