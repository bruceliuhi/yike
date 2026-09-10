"""Actual three-platform desktop -> loopback HTTP -> restricted PG; source data is synthetic."""
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
from pilot.foreground_collection import configured_collection_policy
from pilot.web import build_app
from tests.test_desktop_opportunity_http_postgres import _node_environment
from tests.test_confirmed_strategy_http_postgres import (
    databases, env, execution_databases, execution_env, raw_databases, raw_env, real_strategy_env,
)
from tests.test_execution_runtime_postgres import SECRET, start
from tests.test_research_strategies_postgres import configuration, confirm_body, prepare_body

ROOT = Path(__file__).parents[1]


def test_actual_three_platform_recovery_and_resume_over_http_postgres(real_strategy_env):
    env = real_strategy_env
    node = os.environ.get('YIKE_DEVICE_LIVE_NODE_BINARY') or shutil.which('node')
    if not node:
        pytest.skip('Node 24 required')
    prepared = env.strategies.prepare(env.claims, prepare_body(env,
        configuration=configuration(keywords=['设计'], exclusions=[]),
        platforms=['XIAOHONGSHU', 'DOUYIN', 'BILIBILI'], max_records=10))
    env.confirmed = env.strategies.confirm(env.claims, confirm_body(prepared))
    env.snapshot = env.confirmed['snapshot']
    env.runtime.capability_check = configured_collection_policy({'YIKE_PILOT_COLLECTION_MODE': 'three-platform-foreground-v1'})
    request = start(env, targets=[dict(platform=platform, access_mode='PLATFORM_ACCOUNT',
        connection_id=str(uuid4()), connection_version=2) for platform in ('XIAOHONGSHU', 'DOUYIN', 'BILIBILI')]).model_dump(mode='json')
    for key in ('targets',):
        request.pop(key)
    accounts = {'XIAOHONGSHU':'66c01234abcdef0123456789', 'DOUYIN':'studio_2026', 'BILIBILI':'123456789'}
    now = datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
    urls = {'XIAOHONGSHU':'https://www.xiaohongshu.com/explore/66c01234abcdef0123456789',
            'DOUYIN':'https://www.douyin.com/video/7512345678901234567',
            'BILIBILI':'https://www.bilibili.com/video/BV1synthetic'}
    records = {platform:[dict(kind='COMMENT', external_source_id=f'synthetic-{platform.lower()}',
        external_comment_id=f'synthetic-comment-{platform.lower()}', public_url=urls[platform], title=None,
        author_public_id=None, body=f'  {platform} 合成原文 e\u0301😀\n保持不变\t  ', published_at=None,
        observed_at=now, parent=None, collector_version='synthetic-source-v1',
        normalizer_version='normalizer-v1', query='设计')] for platform in accounts}
    records['DOUYIN'].append(records['DOUYIN'][0] | {
        'external_comment_id': 'synthetic-comment-douyin-second',
        'body': '  DOUYIN 第二条合成原文，预算内保持不变  ',
    })
    token, seed = issue_token(env.claims.user_id, SECRET), env.key.encode().hex()
    app = build_app(env.store, auth_secret=SECRET, dev_login=True, execution_runtime=env.runtime,
        research_strategies=env.strategies, candidate_ingestion=CandidateIngestionStore(env.db, env.runtime))
    child_env = _node_environment()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0)); listener.listen(64)
        server = uvicorn.Server(uvicorn.Config(app, log_level='critical', access_log=False, lifespan='off'))
        thread = threading.Thread(target=server.run, kwargs={'sockets':[listener]}, daemon=True); thread.start()
        try:
            deadline=time.monotonic()+10
            while not server.started and thread.is_alive() and time.monotonic()<deadline: time.sleep(.02)
            assert server.started and thread.is_alive()
            child_env.update(YIKE_MULTIPLATFORM_LIVE_BASE=f'http://127.0.0.1:{listener.getsockname()[1]}',
                YIKE_MULTIPLATFORM_LIVE_USER=env.claims.user_id, YIKE_MULTIPLATFORM_LIVE_TOKEN=token,
                YIKE_MULTIPLATFORM_LIVE_SEED=seed, YIKE_MULTIPLATFORM_LIVE_START=json.dumps(request),
                YIKE_MULTIPLATFORM_LIVE_ACCOUNTS=json.dumps(accounts),
                YIKE_MULTIPLATFORM_LIVE_RECORDS=json.dumps(records, ensure_ascii=False))
            assert not any('DATABASE' in key.upper() or key.upper().startswith('POSTGRES_') for key in child_env)
            child=subprocess.run([node,'node_modules/vitest/vitest.mjs','run',
                'tests/integration/foreground-collection-multiplatform-live.test.ts','--maxWorkers=1'],
                cwd=ROOT/'desktop',env=child_env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
            output=child.stdout+child.stderr
            for private in (token,seed): output=output.replace(private,'[redacted]')
            assert child.returncode==0,output
            assert '1 passed' in output and 'skipped' not in output.lower(),output
        finally:
            server.should_exit=True;thread.join(timeout=10);assert not thread.is_alive()
    with env.admin.connect() as connection:
        task=connection.execute('SELECT task_id,status,max_records FROM pilot_collection_tasks WHERE tenant_id=%s',(env.tenant,)).fetchone()
        assert task[1:] == ('SUCCEEDED',10)
        runs=connection.execute('SELECT platform,status,records_used FROM pilot_collection_platform_runs WHERE tenant_id=%s ORDER BY target_order',(env.tenant,)).fetchall()
        assert runs == [('XIAOHONGSHU','SUCCEEDED',1),('DOUYIN','SUCCEEDED',2),('BILIBILI','SUCCEEDED',1)]
        assert connection.execute('SELECT count(*) FROM pilot_candidate_batches WHERE tenant_id=%s',(env.tenant,)).fetchone()[0] == 3
        assert connection.execute('SELECT count(*) FROM pilot_candidate_observations WHERE tenant_id=%s',(env.tenant,)).fetchone()[0] == 4
        persisted = connection.execute('''
            SELECT s.platform,s.kind,s.external_source_id,s.external_comment_id,
                   v.content->>'public_url',v.content->>'title',v.content->>'author_public_id',
                   v.content->>'body',v.content->>'published_at',v.content->'parent',
                   to_char(o.observed_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                   o.query,o.collector_version,o.normalizer_version
            FROM pilot_candidate_observations o
            JOIN pilot_candidate_sources s USING(tenant_id,owner_user_id,source_id)
            JOIN pilot_candidate_versions v USING(tenant_id,owner_user_id,source_id,version_id)
            WHERE o.tenant_id=%s AND o.owner_user_id=%s
            ORDER BY s.platform,s.external_comment_id
        ''',(env.tenant,env.claims.user_id)).fetchall()
        expected = sorted((platform, record['kind'], record['external_source_id'],
            record['external_comment_id'], record['public_url'], record['title'],
            record['author_public_id'], record['body'], record['published_at'],
            record['parent'], record['observed_at'], record['query'],
            record['collector_version'], record['normalizer_version'])
            for platform, platform_records in records.items() for record in platform_records)
        assert persisted == expected
        operations=connection.execute('SELECT operation,count(*) FROM pilot_execution_operations WHERE tenant_id=%s GROUP BY operation',(env.tenant,)).fetchall()
        assert sorted(operations) == [('CLAIM',3),('FINISH',3),('START',1)]
