"""Real foreground controller -> socket HTTP -> restricted PG, synthetic source only."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import uvicorn

from pilot.auth import issue_token
from pilot.candidate_ingestion import CandidateIngestionStore
from pilot.connection_versions import ConnectionOperation, ConnectionOperationStore
from pilot.foreground_collection import configured_collection_policy
from pilot.web import build_app
from tests.test_desktop_opportunity_http_postgres import _node_environment
from tests.test_confirmed_strategy_http_postgres import (
    databases, env, execution_databases, execution_env, raw_databases, raw_env, real_strategy_env,
)
from tests.test_execution_runtime_postgres import SECRET, start
from tests.test_research_strategies_postgres import prepare_body, confirm_body, configuration

ROOT = Path(__file__).parents[1]


def test_desktop_foreground_original_upload_finish(real_strategy_env):
    env = real_strategy_env
    node = os.environ.get('YIKE_DEVICE_LIVE_NODE_BINARY') or shutil.which('node')
    if not node: pytest.skip('Node 24 required')
    # Persist and confirm a genuine strategy version; do not patch its resolver or policy.
    prepared = env.strategies.prepare(env.claims, prepare_body(env,
        configuration=configuration(keywords=['设计'], exclusions=[]), platforms=['XIAOHONGSHU'], max_records=1))
    env.confirmed = env.strategies.confirm(env.claims, confirm_body(prepared))
    env.snapshot = env.confirmed['snapshot']
    env.runtime.capability_check = configured_collection_policy({'YIKE_PILOT_COLLECTION_MODE': 'xhs-foreground-v1'})
    connections = ConnectionOperationStore(env.db)
    account = '66c01234abcdef0123456789'
    registered = connections.apply(env.claims, ConnectionOperation(request_id=str(uuid4()), action='REGISTER',
        device_id=env.device, connection_id=None, expected_connection_version=0,
        platform='XIAOHONGSHU', account_public_id=account, session_ref='vault://synthetic-foreground'))
    verified = connections.apply(env.claims, ConnectionOperation(request_id=str(uuid4()), action='VERIFY',
        device_id=env.device, connection_id=registered['connection_id'], expected_connection_version=1,
        platform='XIAOHONGSHU', account_public_id=account, session_ref='vault://synthetic-foreground'))
    request = start(env, targets=[dict(platform='XIAOHONGSHU', access_mode='PLATFORM_ACCOUNT',
        connection_id=registered['connection_id'], connection_version=verified['connection_version'])]).model_dump(mode='json')
    records = [dict(kind='COMMENT', external_source_id=account, external_comment_id='66c11234abcdef0123456789',
        public_url='https://www.xiaohongshu.com/explore/' + account, title=None, author_public_id=None,
        body='  原文证据 e\u0301😀\n保留空白与换行\t  ', published_at=None,
        observed_at=datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ'), parent=None,
        collector_version='synthetic-source-v1', normalizer_version='normalizer-v1', query='设计')]
    token, seed = issue_token(env.claims.user_id, SECRET), env.key.encode().hex()
    app = build_app(env.store, auth_secret=SECRET, dev_login=True, execution_runtime=env.runtime,
        research_strategies=env.strategies, candidate_ingestion=CandidateIngestionStore(env.db, env.runtime))
    child_env = _node_environment()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0)); listener.listen(64)
        server = uvicorn.Server(uvicorn.Config(app, log_level='critical', access_log=False, lifespan='off'))
        thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True); thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline: time.sleep(0.02)
            assert server.started and thread.is_alive()
            child_env.update(YIKE_FOREGROUND_LIVE_BASE=f'http://127.0.0.1:{listener.getsockname()[1]}',
                YIKE_FOREGROUND_LIVE_USER=env.claims.user_id, YIKE_FOREGROUND_LIVE_TOKEN=token,
                YIKE_FOREGROUND_LIVE_SEED=seed, YIKE_FOREGROUND_LIVE_START=json.dumps(request),
                YIKE_FOREGROUND_LIVE_RECORDS=json.dumps(records, ensure_ascii=False))
            assert not any('DATABASE' in key.upper() or key.upper().startswith('POSTGRES_') for key in child_env)
            child = subprocess.run([node, 'node_modules/vitest/vitest.mjs', 'run',
                'tests/integration/foreground-collection-live.test.ts', '--maxWorkers=1'],
                cwd=ROOT / 'desktop', env=child_env, capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=50)
            output = child.stdout + child.stderr
            for private in (token, seed): output = output.replace(private, '[redacted]')
            assert child.returncode == 0, output
            assert '1 passed' in output and 'skipped' not in output.lower(), output
        finally:
            server.should_exit = True; thread.join(timeout=10)
            assert not thread.is_alive()
    with env.admin.connect() as connection:
        assert connection.execute("SELECT content->>'body' FROM pilot_candidate_versions WHERE tenant_id=%s", (env.tenant,)).fetchall() == [(records[0]['body'],)]
        tasks = connection.execute('SELECT task_id FROM pilot_collection_tasks WHERE tenant_id=%s', (env.tenant,)).fetchall()
        assert len(tasks) == 1
        assert connection.execute('SELECT count(*) FROM pilot_candidate_batches WHERE tenant_id=%s', (env.tenant,)).fetchone()[0] == 1
        assert connection.execute('SELECT count(*) FROM pilot_candidate_observations WHERE tenant_id=%s', (env.tenant,)).fetchone()[0] == 1
        operations = connection.execute('SELECT operation FROM pilot_execution_operations WHERE tenant_id=%s', (env.tenant,)).fetchall()
        assert sorted(row[0] for row in operations) == ['CLAIM', 'FINISH', 'START']
    current = env.runtime.get_task(env.claims, str(tasks[0][0]))
    assert current['status'] == 'SUCCEEDED' and current['stop_confirmed'] is True and current['records_used'] == 1
