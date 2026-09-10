"""Production desktop client -> socket HTTP -> restricted PostgreSQL review.

Only platform records and model output are synthetic. No external platform,
model, sending, production deployment, or customer-acceptance proof is claimed.
The Node child receives loopback credentials only, never database credentials.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
from pilot.opportunity_evidence import evidence_digest
from pilot.store import PilotStore
from pilot.web import build_app
from tests.test_candidate_assessment_model import CONTENT, DESCRIPTION
from tests.test_candidate_ingestion_postgres import service as raw_service
from tests.test_candidate_review_postgres import assessment, seed
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
from tests.test_desktop_opportunity_http_postgres import _node_environment
from tests.test_execution_runtime_postgres import SECRET


DESKTOP = Path(__file__).parents[1] / "desktop"
RESULT_PREFIX = "CANDIDATE_LIVE_RESULT:"
PARENT = {
    "external_comment_id": "synthetic-parent-comment",
    "body": "父评论  原文",
    "author_public_id": "synthetic-parent-author",
    "published_at": None,
    "public_url": None,
}
COMMENT = {
    "kind": "COMMENT",
    "external_source_id": "synthetic-owned-post",
    "external_comment_id": "synthetic-owned-comment",
    "author_public_id": "synthetic-comment-author",
    "parent": PARENT,
}


def _redacted_output(output: str | bytes | None, tokens: tuple[str, ...]) -> str:
    if isinstance(output, bytes):
        output = output.decode("utf-8", errors="replace")
    for token in tokens:
        output = (output or "").replace(token, "[redacted]")
    return output or ""


def _run_client(node, child_env, *, mode, tokens, expected=None):
    child = child_env | {"YIKE_CANDIDATE_LIVE_MODE": mode}
    if expected is not None:
        child["YIKE_CANDIDATE_LIVE_EXPECTED_JSON"] = json.dumps(
            expected, ensure_ascii=False, separators=(",", ":")
        )
    assert not any(
        "DATABASE" in name.upper()
        or name.upper().startswith("POSTGRES_")
        or "SECRET" in name.upper()
        for name in child
    )
    try:
        result = subprocess.run(
            [
                node,
                "node_modules/vitest/vitest.mjs",
                "run",
                "tests/integration/candidate-review-live.test.ts",
                # One process: subprocess.run kills it and all its threads on
                # timeout; no forked Vitest process can outlive this fixture.
                "--pool=threads",
                "--maxWorkers=1",
                "--no-file-parallelism",
            ],
            cwd=DESKTOP,
            env=child,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=50,
        )
    except subprocess.TimeoutExpired as error:
        output = _redacted_output(error.stdout, tokens) + _redacted_output(
            error.stderr, tokens
        )
        pytest.fail("candidate desktop HTTP child timed out\n" + output, pytrace=False)
    output = _redacted_output(result.stdout + result.stderr, tokens)
    assert result.returncode == 0, output
    assert "1 passed" in output and "skipped" not in output.lower(), output
    # Parse only redacted output so diagnostics cannot reintroduce a token.
    records = [
        line.split(RESULT_PREFIX, 1)[1]
        for line in output.splitlines()
        if RESULT_PREFIX in line
    ]
    assert len(records) == 1, output
    return json.loads(records[0])


def _assert_database_result(test_env, result, *, imported, times):
    with test_env.admin.connect() as connection:
        for table, expected in (
            ("pilot_opportunities", 1 if imported else 0),
            ("pilot_candidate_reviews", 2 if imported else 0),
            ("pilot_candidate_assessments", 1),
            ("pilot_candidate_source_verifications", 1),
        ):
            assert connection.execute(
                f"SELECT count(*) FROM {table} WHERE tenant_id=%s",
                (test_env.tenant,),
            ).fetchone()[0] == expected
        if imported:
            original = connection.execute(
                "SELECT verification_id, result FROM pilot_candidate_reviews "
                "WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s",
                (test_env.tenant, test_env.users[0], result["decisionRequestId"]),
            ).fetchone()
            assert original is not None
            assert str(original[0]) == result["sourceVerificationId"]
            receipt = original[1]["receipt"]
            assert receipt["review"]["sourceVerificationId"] == result["sourceVerificationId"]
            assert receipt["opportunityId"] == result["opportunityId"]
            assert receipt["outcome"] == "IMPORTED"
    if not imported:
        return
    opportunity = test_env.store.get_opportunity(
        test_env.users[0], result["opportunityId"]
    )
    evidence = opportunity["source_evidence"]
    assert evidence["status"] == "CAPTURED"
    snapshot = evidence["snapshot"]
    assert evidence["snapshot_sha256"] == evidence_digest(snapshot)
    assert snapshot["source"]["version_id"] == result["rawVersionId"]
    assert snapshot["source"]["kind"] == "COMMENT"
    assert snapshot["source"]["title"] is None
    assert snapshot["source"]["container_title"] == CONTENT["title"]
    assert snapshot["source"]["body"] == CONTENT["body"]
    assert snapshot["source"]["author_public_id"] == COMMENT["author_public_id"]
    assert snapshot["source"]["parent"] == PARENT
    published_at = datetime.fromisoformat(snapshot["source"]["published_at"].replace("Z", "+00:00"))
    observed_at = datetime.fromisoformat(snapshot["observation"]["observed_at"].replace("Z", "+00:00"))
    received_at = datetime.fromisoformat(snapshot["observation"]["received_at"].replace("Z", "+00:00"))
    assert published_at == datetime.fromisoformat(times["publishedAt"].replace("Z", "+00:00"))
    assert observed_at == datetime.fromisoformat(times["observedAt"].replace("Z", "+00:00"))
    assert published_at < observed_at < received_at
    with test_env.admin.connect() as connection:
        raw_observation = connection.execute(
            "SELECT o.observation_id, o.observed_at, o.received_at, "
            "p.current_observation_id, v.content->>'published_at' "
            "FROM pilot_candidate_observations o "
            "JOIN pilot_candidate_projections p USING (tenant_id, owner_user_id, candidate_id) "
            "JOIN pilot_candidate_versions v ON v.tenant_id=o.tenant_id "
            "AND v.owner_user_id=o.owner_user_id AND v.source_id=o.source_id AND v.version_id=o.version_id "
            "WHERE o.tenant_id=%s AND o.owner_user_id=%s AND o.candidate_id=%s "
            "AND o.version_id=%s AND o.observation_id=%s",
            (test_env.tenant, test_env.users[0], result["binding"]["candidateId"],
             result["rawVersionId"], snapshot["observation"]["id"]),
        ).fetchone()
    assert raw_observation is not None
    assert str(raw_observation[0]) == str(raw_observation[3]) == snapshot["observation"]["id"]
    assert raw_observation[1] == observed_at
    assert raw_observation[2] == received_at
    assert datetime.fromisoformat(raw_observation[4].replace("Z", "+00:00")) == published_at
    assert snapshot["assessment"]["id"] == result["assessmentId"]
    assert snapshot["assessment"]["profile_version_id"] == test_env.profile
    assert snapshot["assessment"]["citations"] == [
        {
            "dimension": "businessMatch",
            "field": "source.container_title",
            "quote": CONTENT["title"],
        },
        {
            "dimension": "businessMatch",
            "field": "source.parent.body",
            "quote": PARENT["body"],
        },
        {"dimension": "intent", "field": "source.body", "quote": "采购输送设备"},
        {"dimension": "urgency", "field": "source.body", "quote": "月底前"},
    ]
    assert snapshot["verification"]["status_at_capture"] == "OPEN"
    assert snapshot["verification"]["contact_method"] == "COMMENT"


@pytest.mark.parametrize("case", ["flow", "source-change", "profile-change"])
def test_actual_desktop_candidate_review_http_postgres(real_strategy_env, case):
    test_env = real_strategy_env
    review = real_review(test_env)
    model_calls = []

    def comment_assessment(*, description, content):
        # Synthetic model boundary only; real validation, binding, quota and
        # assessment persistence still run in CandidateReviewStore.
        model_calls.append((description, content))
        value = assessment()
        value["businessMatch"]["citations"][1] = {
            "field": "parent.title", "quote": CONTENT["title"]
        }
        value["businessMatch"]["citations"].append(
            {"field": "parent.body", "quote": PARENT["body"]}
        )
        return value, None

    review.model.assess = comment_assessment
    now = datetime.now(UTC)
    times = {
        "publishedAt": (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "observedAt": (now - timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    binding = seed(
        test_env, **COMMENT, observed_at=times["observedAt"], published_at=times["publishedAt"]
    ) | {"profileVersion": test_env.profile_number}
    with test_env.db.connect() as connection:
        assert connection.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user"
        ).fetchone() == (False, False)
        assert connection.execute(
            "SELECT row_security_active('pilot_candidate_reviews'::regclass)"
        ).fetchone()[0]

    app = build_app(
        test_env.store,
        auth_secret=SECRET,
        dev_login=True,  # Isolated loopback HTTP fixture; bearer auth remains on.
        candidate_review=review,
        candidate_ingestion=raw_service(test_env),
        execution_runtime=test_env.runtime,
        research_strategies=test_env.strategies,
    )
    node = os.environ.get("YIKE_CANDIDATE_LIVE_NODE_BINARY") or shutil.which("node")
    if not node:
        pytest.skip("Node 24 required for actual desktop candidate review")
    child_env = _node_environment()
    version = subprocess.run(
        [node, "--version"], env=child_env, capture_output=True, text=True,
        timeout=10, check=True,
    )
    assert version.stdout.strip().startswith("v24."), "Node 24 required"
    tokens = tuple(issue_token(user, SECRET) for user in test_env.users)
    child_env.update(
        YIKE_CANDIDATE_LIVE_TOKEN=tokens[0],
        YIKE_CANDIDATE_LIVE_PEER_TOKEN=tokens[1],
        YIKE_CANDIDATE_LIVE_STRANGER_TOKEN=tokens[2],
        YIKE_CANDIDATE_LIVE_BINDING_JSON=json.dumps(binding),
        YIKE_CANDIDATE_LIVE_TIMES_JSON=json.dumps(times),
    )
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(64)
        child_env["YIKE_CANDIDATE_LIVE_BASE"] = (
            f"http://127.0.0.1:{listener.getsockname()[1]}"
        )
        server = uvicorn.Server(
            uvicorn.Config(app, log_level="critical", access_log=False, lifespan="off")
        )
        thread = threading.Thread(
            target=server.run, kwargs={"sockets": [listener]}, daemon=True
        )
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert server.started and thread.is_alive(), "isolated HTTP fixture failed to start"
            result = _run_client(
                node, child_env, mode="flow" if case == "flow" else "prepare", tokens=tokens
            )
            assert result["binding"] == binding
            assert result["rawVersionId"] == binding["sourceVersionId"]
            if case != "flow":
                _assert_database_result(test_env, result, imported=False, times=times)
                if case == "source-change":
                    # Real signed ingestion produces a new current version of
                    # the same candidate; never mutate immutable raw tables.
                    changed = seed(
                        test_env, **COMMENT,
                        body=CONTENT["body"] + "  本人补充：下周再核对。",
                        published_at=times["publishedAt"],
                        observed_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    )
                    assert changed["candidateId"] == binding["candidateId"]
                    assert changed["sourceVersionId"] != binding["sourceVersionId"]
                    assert changed["candidateRevision"] > binding["candidateRevision"]
                else:
                    provisioner = PilotStore(test_env.admin)
                    replacement = provisioner.save_profile(
                        test_env.users[0], {"description": DESCRIPTION + " 新版业务范围。"}
                    )
                    provisioner.confirm_profile(test_env.users[0], replacement["version_id"])
                    assert replacement["version_id"] != binding["profileId"]
                _run_client(node, child_env, mode="stale", tokens=tokens, expected=result)
            _assert_database_result(test_env, result, imported=case == "flow", times=times)
            assert len(model_calls) == 1
            assert model_calls[0][0] == DESCRIPTION
            assert model_calls[0][1]["body"] == CONTENT["body"]
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive(), "isolated HTTP fixture did not stop"
