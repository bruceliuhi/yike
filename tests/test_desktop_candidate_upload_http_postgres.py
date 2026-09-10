"""Product Node candidate signer/transport -> real socket HTTP -> restricted PG.

Synthetic bound device/source/lease and record only; not real platform or UI proof.
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
from pilot.candidate_ingestion import CandidateIngestionStore
from pilot.web import build_app
from tests.test_desktop_opportunity_http_postgres import _node_environment
from tests.test_confirmed_strategy_http_postgres import (
    databases, env, execution_databases, execution_env, raw_databases, raw_env, real_strategy_env,
)
from tests.test_candidate_submission_signing_http_postgres import batch_for, client_for, facts
from tests.test_execution_runtime_postgres import SECRET

ROOT = Path(__file__).parents[1]


def test_desktop_candidate_upload_and_original_receipt(real_strategy_env):
    env = real_strategy_env
    node = os.environ.get('YIKE_DEVICE_LIVE_NODE_BINARY') or shutil.which('node')
    if not node:
        pytest.skip('Node 24 required')
    with client_for(env) as fixture_client:
        batch, begun = batch_for(fixture_client, env)
    batch['request_id'] = 'win-original:batch.1'
    batch['records'][0]['body'] = '  原文证据 e\u0301😀\n保留空白与换行\t  '
    child_env = _node_environment()
    tokens = [issue_token(env.claims.user_id, SECRET), issue_token(env.claims.user_id, SECRET)]
    seed = env.key.encode().hex()  # Disposable fixture key only.
    app = build_app(env.store, auth_secret=SECRET, dev_login=True,
        execution_runtime=env.runtime, research_strategies=env.strategies,
        candidate_ingestion=CandidateIngestionStore(env.db, env.runtime))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(64)
        server = uvicorn.Server(uvicorn.Config(app, log_level='critical', access_log=False, lifespan='off'))
        thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert server.started and thread.is_alive()
            child_env.update(YIKE_CANDIDATE_UPLOAD_LIVE_BASE=f'http://127.0.0.1:{listener.getsockname()[1]}',
                YIKE_CANDIDATE_UPLOAD_LIVE_USER=env.claims.user_id, YIKE_CANDIDATE_UPLOAD_LIVE_SEED=seed,
                YIKE_CANDIDATE_UPLOAD_LIVE_TOKEN=tokens[0], YIKE_CANDIDATE_UPLOAD_LIVE_NEXT_TOKEN=tokens[1],
                YIKE_CANDIDATE_UPLOAD_LIVE_BATCH=json.dumps(batch, ensure_ascii=False))
            assert not any('DATABASE' in key.upper() or key.upper().startswith('POSTGRES_') for key in child_env)
            child = subprocess.run([node, 'node_modules/vitest/vitest.mjs', 'run',
                'tests/integration/candidate-upload-live.test.ts', '--maxWorkers=1'],
                cwd=ROOT / 'desktop', env=child_env, capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=50)
            output = child.stdout + child.stderr
            for private in tokens + [seed]:
                output = output.replace(private, '[redacted]')
            assert child.returncode == 0, output
            assert '1 passed' in output and 'skipped' not in output.lower(), output
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive()
    counts, _, _ = facts(env)
    assert all(count == 1 for count in counts.values()), counts
    assert env.runtime.get_task(env.claims, begun['task_id'])['records_used'] == 1
    with env.admin.connect() as connection:
        assert connection.execute("SELECT content->>'body' FROM pilot_candidate_versions WHERE tenant_id=%s",
            (env.tenant,)).fetchall() == [(batch['records'][0]['body'],)]
