"""Ordinary Node client + real HTTP + restricted PG. Synthetic source, no sends."""
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

from pilot.auth import issue_token
from pilot.contact_drafts import ContactDraftStore
from pilot.web import build_app
from tests.test_confirmed_strategy_review_postgres import (
    databases, env, execution_databases, execution_env, raw_databases, raw_env,
    real_strategy_env,
)
from tests.test_desktop_opportunity_http_postgres import _node_environment
from tests.test_execution_runtime_postgres import SECRET
from tests.test_opportunity_evidence_postgres import include


def test_ordinary_client_restores_saved_versions_and_original_requests(real_strategy_env, request):
    env = real_strategy_env
    root = Path(__file__).parents[1]
    with env.db.connect() as conn:
        role = conn.execute('SELECT current_user').fetchone()[0]
    with env.admin.connect() as conn:
        conn.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
        conn.execute((root / 'deploy/grant_contact_drafts.sql').read_text())
    review, _, _, _, decision, _, opportunity_id = include(env)
    def cleanup_synthetic_drafts():
        # Only tear down this test's synthetic rows, after all acceptance. The
        # live application path above/below retains RLS and immutable triggers.
        with env.admin.connect() as conn:
            conn.execute('ALTER TABLE pilot_contact_drafts DISABLE TRIGGER contact_draft_immutable')
            conn.execute('DELETE FROM pilot_contact_drafts WHERE tenant_id=%s AND opportunity_id=%s',
                         (env.tenant, opportunity_id))
            conn.execute('ALTER TABLE pilot_contact_drafts ENABLE TRIGGER contact_draft_immutable')
    request.addfinalizer(cleanup_synthetic_drafts)
    with env.admin.connect() as conn:
        facts = conn.execute('SELECT o.profile_version_id,o.source_status,o.intent_status,p.status,s.health '
            'FROM pilot_opportunities o JOIN business_profile_versions p ON p.profile_version_id=o.profile_version_id '
            'JOIN pilot_sources s ON s.source_id=o.source_id WHERE o.opportunity_id=%s', (opportunity_id,)).fetchone()
        assert facts == (env.profile, 'OPEN', 'NEW', 'CONFIRMED', 'OPEN'), facts
    app = build_app(env.store, auth_secret=SECRET, dev_login=True,
                    contact_drafts=ContactDraftStore(env.db))
    node = os.environ.get('YIKE_DEVICE_LIVE_NODE_BINARY') or shutil.which('node')
    if not node:
        pytest.skip('Node 24 needed for actual client')
    child_env = _node_environment()
    token, other_token = [issue_token(user, SECRET) for user in env.users[:2]]
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0)); listener.listen(64)
        server = uvicorn.Server(uvicorn.Config(app, log_level='critical', access_log=False, lifespan='off'))
        thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert server.started and thread.is_alive()
            child_env.update(YIKE_DRAFT_LIVE_BASE=f'http://127.0.0.1:{listener.getsockname()[1]}',
                YIKE_DRAFT_LIVE_TOKEN=token, YIKE_DRAFT_LIVE_OTHER_TOKEN=other_token,
                YIKE_DRAFT_LIVE_OPPORTUNITY=opportunity_id)
            result = subprocess.run([node, 'node_modules/vitest/vitest.mjs', 'run',
                'tests/integration/contact-drafts-live.test.ts', '--maxWorkers=1'],
                cwd=root / 'desktop', env=child_env, capture_output=True, text=True, timeout=50)
            output = (result.stdout + result.stderr).replace(token, '[redacted]').replace(other_token, '[redacted]')
            assert result.returncode == 0, output
            assert '1 passed' in output and 'skipped' not in output.lower(), output
            with env.db.connect() as conn:
                conn.execute("SELECT set_config('yike.tenant_id',%s,true)", (env.tenant,))
                conn.execute("SELECT set_config('yike.user_id',%s,true)", (env.claims.user_id,))
                # No extra row from the lost response or the stale editor.
                rows = conn.execute('SELECT count(*) FROM pilot_contact_drafts WHERE tenant_id=%s AND opportunity_id=%s',
                                    (env.tenant, opportunity_id)).fetchone()[0]
                assert rows == 2
            # A repeat human inclusion is not permission to revive a source
            # explicitly closed since the original captured version.
            with env.admin.connect() as conn:
                conn.execute("UPDATE pilot_opportunities SET source_status='BLOCKED' WHERE opportunity_id=%s", (opportunity_id,))
                conn.execute("UPDATE pilot_sources SET health='BLOCKED' WHERE source_id=(SELECT source_id FROM pilot_opportunities WHERE opportunity_id=%s)", (opportunity_id,))
            repeated = review.review(env.claims, {**decision, 'requestId': str(uuid4())})
            assert repeated['receipt']['outcome'] == 'ALREADY_IMPORTED'
            with env.admin.connect() as conn:
                assert conn.execute('SELECT o.source_status,s.health FROM pilot_opportunities o JOIN pilot_sources s ON o.source_id=s.source_id WHERE o.opportunity_id=%s',
                                    (opportunity_id,)).fetchone() == ('BLOCKED', 'BLOCKED')
        finally:
            server.should_exit = True; thread.join(timeout=10)
            assert not thread.is_alive()
