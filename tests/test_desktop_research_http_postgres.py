"""Native signed research execution through socket HTTP and restricted PostgreSQL.

The key, login token, source response, and model response are disposable fixtures.
"""
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
from tests.test_candidate_review_postgres import (
    databases, env, execution_databases, execution_env, raw_databases, raw_env,
)
from tests.test_confirmed_strategy_review_postgres import real_strategy_env
from tests.test_desktop_opportunity_http_postgres import _node_environment
from tests.test_execution_runtime_postgres import SECRET, start
from tests.test_research_quote_postgres import _confirmed_research, _request
from tests.test_research_runtime_postgres import runtime_env
from tests.test_research_strategies_postgres import confirm_body, prepare_body

ROOT = Path(__file__).parents[1]


def test_native_research_start_advance_status_and_recovery(runtime_env, monkeypatch):
    import pilot.runtime as runtime_module
    from pilot.candidate_assessment_model import OpenAICompatibleCandidateAssessmentModel
    from pilot.research_orchestrator import ResearchOrchestrator
    from tests.test_candidate_assessment_model import CONTENT
    from tests.test_candidate_review_postgres import BoundaryModel
    from tests.test_research_candidates_postgres import topic

    test_env = runtime_env
    _, _, _, _, _, legacy = _confirmed_research(test_env)
    pending = test_env.strategies.prepare(test_env.claims, prepare_body(
        test_env, configuration=legacy["snapshot"]["configuration"] | {
            "publicSource": "v2ex-latest-v1"}))
    confirmed = test_env.strategies.confirm(test_env.claims, confirm_body(pending))
    test_env.confirmed, test_env.snapshot = confirmed, confirmed["snapshot"]
    operation = start(test_env)

    class SyntheticModel(OpenAICompatibleCandidateAssessmentModel):
        calls = 0
        def assess_before(self, _deadline, **kwargs):
            self.calls += 1
            return BoundaryModel().assess(**kwargs)

    model = SyntheticModel("https://example.invalid/v1", "synthetic-key", "synthetic-model")
    monkeypatch.setattr(runtime_module, "_assessment_model", lambda _environment: model)
    monkeypatch.setattr(runtime_module, "ResearchOrchestrator", lambda sources, reviews:
        ResearchOrchestrator(sources, reviews, fetcher=lambda _deadline: [topic(
            906, title=CONTENT["title"], content=CONTENT["body"])]))
    configuration = {
        "YIKE_PILOT_RESEARCH_MODE": "public-v2ex-v1",
        "YIKE_PILOT_RESEARCH_RULE_VERSION": "synthetic-live-rule-v1",
        "YIKE_PILOT_RESEARCH_SOURCE_MILLI": "100",
        "YIKE_PILOT_RESEARCH_MINUTE_MILLI": "200",
        "YIKE_PILOT_RESEARCH_MODEL_CALL_MILLI": "300",
    }
    secret = SECRET + "-desktop-research-live"
    token = issue_token(test_env.claims.user_id, secret)
    app = runtime_module.build_runtime_app(test_env.db, auth_secret=secret,
        dev_login=True, environment=configuration)
    node = os.environ.get("YIKE_DEVICE_LIVE_NODE_BINARY") or shutil.which("node")
    if not node:
        pytest.skip("Node 24 required")
    child_env = _node_environment()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0)); listener.listen(64)
        server = uvicorn.Server(uvicorn.Config(app, log_level="critical",
            access_log=False, lifespan="off"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(.02)
            assert server.started and thread.is_alive()
            child_env.update(
                YIKE_RESEARCH_LIVE_BASE=f"http://127.0.0.1:{listener.getsockname()[1]}",
                YIKE_RESEARCH_LIVE_USER=test_env.claims.user_id,
                YIKE_RESEARCH_LIVE_TOKEN=token,
                YIKE_RESEARCH_LIVE_SEED=test_env.key.encode().hex(),
                YIKE_RESEARCH_LIVE_START=json.dumps(operation.model_dump(mode="json")),
                YIKE_RESEARCH_LIVE_QUOTE=json.dumps(_request(test_env, confirmed) | {
                    "requestId": operation.request_id}),
                YIKE_RESEARCH_LIVE_BINDING=json.dumps({"limits":
                    confirmed["snapshot"]["configuration"]["research"]["limits"]}),
            )
            assert not any("DATABASE" in key.upper() or key.upper().startswith("POSTGRES_")
                for key in child_env)
            child = subprocess.run([node, "node_modules/vitest/vitest.mjs", "run",
                "tests/integration/research-execution-live.test.ts", "--maxWorkers=1"],
                cwd=ROOT / "desktop", env=child_env, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=50)
            output = child.stdout + child.stderr
            for private in (token, test_env.key.encode().hex()):
                output = output.replace(private, "[redacted]")
            assert child.returncode == 0, output
            assert "1 passed" in output and "skipped" not in output.lower(), output
        finally:
            server.should_exit = True; thread.join(timeout=10)
            assert not thread.is_alive()
    assert model.calls == 1
