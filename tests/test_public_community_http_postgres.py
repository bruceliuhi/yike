"""Opt-in real socket HTTP/PG/client chain; only explicit NETWORK=1 reads V2EX.

Users, local dev login and key provisioning are controlled fixtures. Model calls
require a separate explicit opt-in; no outreach or production/Windows acceptance.
"""
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import threading
import time
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
import uvicorn

from pilot.auth import issue_token
from pilot.runtime import build_runtime_app
from pilot.store import PilotStore
from tests.test_candidate_review_http_postgres import local_provider
from tests.test_desktop_opportunity_http_postgres import _node_environment
from tests.test_confirmed_strategy_http_postgres import (
    databases, env, execution_databases, execution_env, raw_databases, raw_env, real_strategy_env,
)
from tests.test_execution_runtime_postgres import SECRET
from tests.test_research_strategies_postgres import prepare_body, confirm_body, configuration

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope='module', autouse=True)
def isolated_public_database_guard():
    # Run before the imported module-scoped migration/grant fixtures.
    urls = [os.environ.get(name) for name in (
        'YIKE_IDENTITY_TEST_DATABASE_URL', 'YIKE_IDENTITY_TEST_APP_DATABASE_URL')]
    if not all(urls):
        pytest.skip('dedicated public-flow PostgreSQL required')
    for value in urls:
        url = urlsplit(value)
        assert url.hostname == '127.0.0.1' and url.path == '/yike_public_flow', 'dedicated local public-flow database required'


def test_real_pg_prepare_confirm_get_preserves_qna_and_source_change_digest(real_strategy_env):
    env = real_strategy_env
    request = prepare_body(env, configuration=configuration(
        publicSource='v2ex-qna-v1', keywords=['企业软件'], exclusions=[]))
    qna_draft = env.strategies.prepare(env.claims, request)
    qna = env.strategies.confirm(env.claims, confirm_body(qna_draft))
    stored = env.strategies.get_strategy(env.claims, qna['strategy_version_id'])
    assert stored['snapshot']['configuration']['publicSource'] == 'v2ex-qna-v1'
    assert stored['configuration_sha256'] == qna['configuration_sha256']

    latest_draft = env.strategies.prepare(env.claims, request | {
        'request_id': str(uuid4()),
        'draft_revision': request['draft_revision'] + 1,
        'configuration': configuration(
            publicSource='v2ex-latest-v1', keywords=['企业软件'], exclusions=[]),
    })
    assert latest_draft['configuration_sha256'] != qna['configuration_sha256']
    assert latest_draft['snapshot']['configuration']['publicSource'] == 'v2ex-latest-v1'


@pytest.mark.parametrize(('selected_source', 'expected_collector'), [
    ('v2ex-latest-v1', 'v2ex-latest-v1'),
    ('v2ex-qna-v1', 'v2ex-qna-v1'),
    ('v2ex-outsourcing-authors-v1', 'v2ex-outsourcing-authors-v1'),
])
def test_public_community_client_through_ordinary_runtime(
        real_strategy_env, selected_source, expected_collector, request):
    env = real_strategy_env
    network = os.environ.get('YIKE_PUBLIC_COMMUNITY_NETWORK') == '1'
    assess_mode = os.environ.get('YIKE_PUBLIC_COMMUNITY_ASSESSMENT', '')
    assert assess_mode in ('', 'fixture', 'network'), 'invalid assessment check mode'
    model_environment = {}
    provider = None
    target = ''
    if assess_mode:
        assert selected_source == 'v2ex-outsourcing-authors-v1', 'select only the author-source test'
        assert network == (assess_mode == 'network'), 'source and model modes must match'
        if network:
            target = os.environ.get('YIKE_PUBLIC_COMMUNITY_ASSESS_SOURCE_ID', '')
            assert re.fullmatch(r'[1-9][0-9]{0,15}', target), 'explicit source ID required'
            for suffix in ('BASE_URL', 'API_KEY', 'MODEL'):
                name = 'YIKE_PILOT_ASSESSMENT_' + suffix
                assert os.environ.get(name, '').strip(), 'complete model configuration required'
                model_environment[name] = os.environ[name]
        else:
            target = '987654321'
            provider = request.getfixturevalue('local_provider')
            provider.delay_seconds = 13  # Exceeds the old desktop 12-second timeout.
            for dimension in ('businessMatch', 'intent', 'urgency'):
                provider.result[dimension]['citations'] = [{'field': 'body', 'quote': '需要 AI 的企业服务'}]
            model_environment = {
                'YIKE_PILOT_ASSESSMENT_BASE_URL': provider.model.base_url,
                'YIKE_PILOT_ASSESSMENT_API_KEY': 'synthetic-test-only',
                'YIKE_PILOT_ASSESSMENT_MODEL': provider.model.model,
            }
        provisioner = PilotStore(env.admin)
        profile = provisioner.save_profile(env.claims.user_id, {'description':
            '我们提供AI应用、业务系统以及配套前端页面开发；具体作品需另行核实，不承诺尚未验证的UI审美案例。'})
        provisioner.confirm_profile(env.claims.user_id, profile['version_id'])
        env.profile = profile['version_id']
    node = os.environ.get('YIKE_DEVICE_LIVE_NODE_BINARY') or shutil.which('node')
    if not node:
        pytest.fail('Node 24 required for requested integration check')
    # Full normal runtime, actual policy/resolver and production grant manifest.
    # The fixture connection assumes a restricted role, never forwarded to Node.
    with env.db.connect() as conn:
        role = conn.execute('SELECT current_user').fetchone()[0]
        assert conn.execute('SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone() == (False,)
    with env.admin.connect() as conn:
        conn.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
        manifest = (ROOT / 'deploy/grant_runtime.sql').read_text()
        for line in manifest.splitlines():
            if line.startswith('\\ir '):
                conn.execute((ROOT / 'deploy' / line.split()[1]).read_text())
    prepare = prepare_body(env, configuration=configuration(publicSource=selected_source,
        keywords=['AI', '的'], exclusions=[]), platforms=['PUBLIC_WEB'],
        max_records=3 if selected_source == 'v2ex-outsourcing-authors-v1' else 100)
    token, seed = issue_token(env.claims.user_id, SECRET), env.key.encode().hex()
    app = build_runtime_app(env.db, auth_secret=SECRET, dev_login=True,
        environment={'YIKE_PILOT_COLLECTION_MODE': ('four-platform-public-project-monitor-v1'
            if selected_source == 'v2ex-outsourcing-authors-v1' else 'four-platform-public-node-monitor-v1'),
            **model_environment})
    child_env = _node_environment()
    child_env['NO_COLOR'] = '1'
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0)); listener.listen(64)
        base = f'http://127.0.0.1:{listener.getsockname()[1]}'
        server = uvicorn.Server(uvicorn.Config(app, log_level='critical', access_log=False, lifespan='off'))
        thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert server.started and thread.is_alive()
            child_env.update(YIKE_PUBLIC_LIVE_BASE=base, YIKE_PUBLIC_LIVE_USER=env.claims.user_id,
                YIKE_PUBLIC_LIVE_TOKEN=token, YIKE_PUBLIC_LIVE_SEED=seed, YIKE_PUBLIC_LIVE_DEVICE=env.device,
                YIKE_PUBLIC_LIVE_PROFILE=env.profile, YIKE_PUBLIC_LIVE_PREPARE=json.dumps(prepare),
                YIKE_PUBLIC_LIVE_SOURCE=selected_source,
                YIKE_PUBLIC_LIVE_ASSESS_SOURCE_ID=target,
                YIKE_PUBLIC_LIVE_NETWORK='1' if network else '0')
            assert not any('DATABASE' in key.upper() or key.upper().startswith('POSTGRES_') for key in child_env)
            child = subprocess.run([node, 'node_modules/vitest/vitest.mjs', 'run',
                'tests/integration/public-community-live.test.ts', '--maxWorkers=1'],
                cwd=ROOT / 'desktop', env=child_env, capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=150 if assess_mode else 90)
            output = re.sub(r'\x1b\[[0-9;]*m', '', child.stdout + child.stderr)
            for private in (token, seed):
                output = output.replace(private, '[redacted]')
            # Source bodies are not printed by the child, even on assertions.
            assert child.returncode == 0, output
            assert '1 passed' in output and 'skipped' not in output.lower(), output
            markers = [line.split('PUBLIC_COMMUNITY_RESULT ', 1)[1] for line in output.splitlines()
                       if 'PUBLIC_COMMUNITY_RESULT ' in line]
            assert len(markers) == 1, 'missing bounded client result'
            result = json.loads(markers[0])
            assert result['mode'] == ('network' if network else 'fixture')
            assert result['sourceId'] == selected_source
            assert result['collectorVersion'] == expected_collector
            assert 1 <= result['records'] <= 100
            expected_tasks = 1 if network else 2
            assert result['tasks'] == expected_tasks
            assert result['sourceReads'] == expected_tasks
            assert result['replyReads'] == (result['records'] * expected_tasks
                if selected_source == 'v2ex-outsourcing-authors-v1' else 0)
            if assess_mode:
                assert result['assessment']['sourceId'] == target
                assert result['assessment']['assessRequests'] == 1
                if provider is not None:
                    assert len(provider.requests) == 1
            # Ordinary read API must keep candidates private to their owner.
            for user in (env.users[1], env.users[2]):
                request = Request(base + '/api/ui/candidates', headers={
                    'Authorization': 'Bearer ' + issue_token(user, SECRET)})
                with urlopen(request, timeout=5) as response:
                    assert json.load(response)['total'] == 0
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive()
    with env.admin.connect() as conn:
        count, tasks = result['records'], result['tasks']
        for table in ('pilot_candidate_sources', 'pilot_candidate_versions'):
            assert conn.execute(f'SELECT count(*) FROM {table} WHERE tenant_id=%s', (env.tenant,)).fetchone()[0] == count
        assert conn.execute('SELECT count(*) FROM pilot_candidate_observations WHERE tenant_id=%s',
                            (env.tenant,)).fetchone()[0] == count * tasks
        assert conn.execute('SELECT count(*) FROM pilot_candidate_batches WHERE tenant_id=%s',
                            (env.tenant,)).fetchone()[0] == tasks
        assert conn.execute('SELECT status,records_used FROM pilot_collection_platform_runs WHERE task_id=%s',
                            (result['taskId'],)).fetchone() == ('SUCCEEDED', count)
        operations = conn.execute('SELECT operation FROM pilot_execution_operations WHERE tenant_id=%s', (env.tenant,)).fetchall()
        assert sorted(row[0] for row in operations) == sorted(['CLAIM', 'FINISH', 'START'] * tasks)
        assert conn.execute('SELECT count(*) FROM pilot_platform_connections WHERE tenant_id=%s', (env.tenant,)).fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM pilot_opportunities WHERE tenant_id=%s', (env.tenant,)).fetchone()[0] == 0
        for table in ('pilot_candidate_reviews', 'pilot_candidate_source_verifications'):
            assert conn.execute(f'SELECT count(*) FROM {table} WHERE tenant_id=%s', (env.tenant,)).fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM pilot_candidate_assessments WHERE tenant_id=%s',
                            (env.tenant,)).fetchone()[0] == (1 if assess_mode else 0)
        assert conn.execute("SELECT bool_and(collector_version=%s) FROM pilot_candidate_observations WHERE tenant_id=%s",
                            (expected_collector, env.tenant)).fetchone()[0] is True
    current = env.runtime.get_task(env.claims, result['taskId'])
    assert current['status'] == 'SUCCEEDED' and current['stop_confirmed'] is True and current['records_used'] == count
    print('PUBLIC_COMMUNITY_CHECK ' + json.dumps(result, sort_keys=True))
