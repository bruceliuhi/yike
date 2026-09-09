"""Actual desktop opportunity read through authenticated HTTP and restricted PG.

The source, model response, users, and session tokens are synthetic.  This test
does not contact a platform or model and does not send a message.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time

import pytest
import uvicorn

from pilot.auth import issue_token
from pilot.web import build_app
from tests.test_candidate_review_postgres import assessment
from tests.test_confirmed_strategy_review_postgres import (
    databases,
    env,
    execution_databases,
    execution_env,
    raw_databases,
    raw_env,
    real_review,
    real_strategy_env,
)
from tests.test_execution_runtime_postgres import SECRET
from tests.test_opportunity_evidence_postgres import include


ROOT = Path(__file__).parents[1]
DESKTOP = ROOT / "desktop"
DATABASE_ENV_NAMES = {
    "YIKE_RESEARCH_STRATEGY_TEST_DATABASE_URL",
    "YIKE_RESEARCH_STRATEGY_TEST_APP_DATABASE_URL",
    "YIKE_IDENTITY_TEST_DATABASE_URL",
    "YIKE_IDENTITY_TEST_APP_DATABASE_URL",
    "YIKE_PILOT_DATABASE_URL",
    "YIKE_PILOT_ADMIN_DATABASE_URL",
    "POSTGRES_PASSWORD",
}
SYSTEM_ENV_NAMES = (
    "SystemRoot",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "PATH",
    "TEMP",
    "TMP",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "PROCESSOR_IDENTIFIER",
)


def _node_environment() -> dict[str, str]:
    child = {
        name: value
        for name in SYSTEM_ENV_NAMES
        if (value := os.environ.get(name)) is not None
    }
    assert not DATABASE_ENV_NAMES.intersection(child)
    assert not any(
        "DATABASE" in name.upper() or name.upper().startswith("POSTGRES_")
        for name in child
    )
    return child


def test_actual_desktop_reads_fixed_comment_evidence_from_restricted_postgres(
    real_strategy_env,
):
    test_env = real_strategy_env
    review = real_review(test_env)

    def comment_assessment(**_kwargs):
        value = assessment()
        value["businessMatch"]["citations"][1] = {
            "field": "parent.title",
            "quote": "食品工厂扩产",
        }
        value["businessMatch"]["citations"].append(
            {"field": "parent.body", "quote": "父评论  原文"}
        )
        return value, None

    review.model.assess = comment_assessment
    parent = {
        "external_comment_id": "synthetic-parent-comment",
        "body": "父评论  原文",
        "author_public_id": "synthetic-parent-author",
        "published_at": None,
        "public_url": None,
    }
    *_, opportunity_id = include(
        test_env,
        service=review,
        kind="COMMENT",
        external_source_id="synthetic-owned-post",
        external_comment_id="synthetic-owned-comment",
        author_public_id=None,
        parent=parent,
    )
    # Fixture-only state setup: the application role intentionally has no
    # UPDATE grant on opportunities.  Keep the actual HTTP read on env.store.
    with test_env.admin.connect() as connection:
        changed = connection.execute(
            "UPDATE pilot_opportunities "
            "SET source_status='BLOCKED', updated_at=CURRENT_TIMESTAMP "
            "WHERE tenant_id=%s AND opportunity_id=%s",
            (test_env.tenant, opportunity_id),
        )
        assert changed.rowcount == 1
    stored = test_env.store.get_opportunity(test_env.users[0], opportunity_id)
    evidence = stored["source_evidence"]
    snapshot = evidence["snapshot"]
    assert stored["source_status"] == "BLOCKED"
    assert evidence["status"] == "CAPTURED"
    assert snapshot["source"]["kind"] == "COMMENT"
    assert snapshot["source"]["title"] is None
    assert snapshot["source"]["container_title"] == "食品工厂扩产"
    assert snapshot["source"]["author_public_id"] is None
    assert snapshot["source"]["parent"] == parent
    assert snapshot["assessment"]["citations"] == [
        {
            "dimension": "businessMatch",
            "field": "source.container_title",
            "quote": "食品工厂扩产",
        },
        {
            "dimension": "businessMatch",
            "field": "source.parent.body",
            "quote": "父评论  原文",
        },
        {
            "dimension": "intent",
            "field": "source.body",
            "quote": "采购输送设备",
        },
        {
            "dimension": "urgency",
            "field": "source.body",
            "quote": "月底前",
        },
    ]
    assert "unknowns" not in snapshot["assessment"]
    assert snapshot["verification"]["status_at_capture"] == "OPEN"

    app = build_app(test_env.store, auth_secret=SECRET, dev_login=True)
    routes = [
        route.path
        for route in app.routes
        if route.path == "/api/ui/opportunities/{opportunity_id}"
    ]
    assert routes == ["/api/ui/opportunities/{opportunity_id}"]

    node = os.environ.get("YIKE_EVIDENCE_LIVE_NODE_BINARY") or shutil.which("node")
    if not node:
        pytest.skip("Node 24 required for actual desktop evidence consumer")
    child_env = _node_environment()
    version = subprocess.run(
        [node, "--version"],
        env=child_env,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    assert version.stdout.strip().startswith("v24."), "Node 24 required"

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(64)
        server = uvicorn.Server(
            uvicorn.Config(app, log_level="critical", access_log=False, lifespan="off")
        )
        thread = threading.Thread(
            target=server.run, kwargs={"sockets": [listener]}, daemon=True
        )
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while (
                not server.started
                and thread.is_alive()
                and time.monotonic() < deadline
            ):
                time.sleep(0.02)
            assert server.started and thread.is_alive(), "isolated HTTP fixture failed to start"

            owner_token = issue_token(test_env.users[0], SECRET)
            stranger_token = issue_token(test_env.users[2], SECRET)
            child_env.update(
                YIKE_EVIDENCE_LIVE_BASE=(
                    f"http://127.0.0.1:{listener.getsockname()[1]}"
                ),
                YIKE_EVIDENCE_LIVE_TOKEN=owner_token,
                YIKE_EVIDENCE_LIVE_STRANGER_TOKEN=stranger_token,
                YIKE_EVIDENCE_LIVE_OPPORTUNITY_ID=opportunity_id,
                YIKE_EVIDENCE_LIVE_EXPECTED_JSON=json.dumps(
                    evidence,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
            assert not DATABASE_ENV_NAMES.intersection(child_env)
            assert not any(
                "DATABASE" in name.upper() or name.upper().startswith("POSTGRES_")
                for name in child_env
            )
            result = subprocess.run(
                [
                    node,
                    "node_modules/vitest/vitest.mjs",
                    "run",
                    "tests/integration/opportunity-evidence-live.test.ts",
                ],
                cwd=DESKTOP,
                env=child_env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=50,
            )
            output = result.stdout + result.stderr
            for synthetic_token in (owner_token, stranger_token):
                output = output.replace(synthetic_token, "[redacted]")
            assert result.returncode == 0, output
            assert "1 passed" in output and "skipped" not in output.lower(), output
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive(), "isolated HTTP fixture did not stop"
