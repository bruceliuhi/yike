"""Synthetic multi-round observations through real restricted PG; no live platform."""
from datetime import datetime, UTC
import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from nacl.signing import SigningKey
from psycopg import sql

from pilot.auth import issue_token, verify_token_claims
from pilot.candidate_ingestion import CandidateIngestionStore
from pilot.db import PilotDatabase
from pilot.device_credentials import DeviceCredentialStore
from pilot.execution_runtime import ExecutionRuntime
from pilot.execution_contract import ExecutionRuntimeError
from pilot.foreground_collection import configured_collection_policy
from pilot.monitor_plans import MonitorPlanStore
from pilot.monitor_runtime import MonitorRuntime
from pilot.research_strategies import ResearchStrategyStore
from pilot.store import PilotStore
from tests.test_candidate_ingestion_postgres import payload, submit
from tests.test_device_credentials_postgres import RoleDatabase, bind
from tests.test_monitor_runtime_postgres import begin_and_claim, runtime_pulse, sign_apply
from tests.test_research_strategies_postgres import prepare_body, confirm_body, configuration

ROOT = Path(__file__).parents[1]


@pytest.fixture
def public_monitor_env():
    value = os.environ.get('YIKE_PUBLIC_MONITOR_TEST_DATABASE_URL')
    if not value:
        pytest.skip('dedicated public-monitor PostgreSQL required')
    url = urlsplit(value)
    assert url.hostname == '127.0.0.1' and url.path == '/yike_public_monitor'
    admin = PilotDatabase(value)
    admin.migrate()
    role = 'public_monitor_' + uuid4().hex
    with admin.connect() as conn:
        conn.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE')
                     .format(sql.Identifier(role)))
        conn.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
        for line in (ROOT / 'deploy/grant_runtime.sql').read_text().splitlines():
            if line.startswith('\\ir '):
                conn.execute((ROOT / 'deploy' / line.split()[1]).read_text())
    db = RoleDatabase(admin, role)
    provisioner = PilotStore(admin)
    tenant = provisioner.provision_tenant('synthetic-public-monitor')
    user = provisioner.provision_user(tenant, f'{uuid4()}@example.invalid')
    claims = verify_token_claims(issue_token(user, 'synthetic-public-monitor'), 'synthetic-public-monitor')
    store = PilotStore(db)
    device = store.register_device(user, 'synthetic-public-monitor')['device_id']
    key = SigningKey.generate()
    bind(SimpleNamespace(service=DeviceCredentialStore(db), claims=claims, device=device), key)
    profile = provisioner.save_profile(user, {'description': '我们承接企业软件项目。'})['version_id']
    provisioner.confirm_profile(user, profile)
    env = SimpleNamespace(admin=admin, db=db, tenant=tenant, claims=claims, device=device, key=key, profile=profile)
    strategies = ResearchStrategyStore(db)
    schedule = dict(kind='interval', times=[], interval=1, start='00:00', end='23:59', timezone='UTC', policyVersion=1)
    prepared = strategies.prepare(claims, prepare_body(env, configuration=configuration(
        mode='monitor', schedule=schedule, publicSource='v2ex-qna-v1', keywords=['企业软件'], exclusions=[])))
    confirmed = strategies.confirm(claims, confirm_body(prepared))
    env.snapshot = confirmed['snapshot']
    env.plans = MonitorPlanStore(db, strategy_resolver=strategies.resolve)
    env.plan = env.plans.create(claims, dict(schema_version='monitor-plans-v1', request_id=str(uuid4()),
        profile_version_id=profile, strategy_version_id=confirmed['strategy_version_id'], human_confirmed=True))['plan']
    env.execution = ExecutionRuntime(db, strategy_resolver=strategies.resolve,
        capability_check=configured_collection_policy({'YIKE_PILOT_COLLECTION_MODE': 'four-platform-public-node-monitor-v1'}))
    env.monitor = MonitorRuntime(db, env.execution)
    env.execution.monitor_runtime = env.monitor
    env.target = dict(platform='PUBLIC_WEB', access_mode='PUBLIC_ANONYMOUS', connection_id=None, connection_version=None)
    try:
        yield env
    finally:
        # Audit rows remain in this disposable database; never weaken immutability.
        with admin.connect() as conn:
            conn.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
            conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


def test_public_monitor_three_rounds_preserve_versions_observations_and_idempotency(public_monitor_env):
    env = public_monitor_env
    store = CandidateIngestionStore(env.db, env.execution)
    session = str(uuid4())
    current_policy = env.execution.capability_check
    env.execution.capability_check = configured_collection_policy(
        {'YIKE_PILOT_COLLECTION_MODE': 'four-platform-public-sampling-monitor-v1'})
    with pytest.raises(ExecutionRuntimeError, match='capability_unavailable'):
        env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    env.execution.capability_check = current_policy
    candidates, versions, tasks = [], [], []
    for source_values in ((('a', '企业软件需求一'),),
                          (('a', '企业软件需求一更新'), ('b', '企业软件需求二')),
                          (('a', '企业软件需求一更新'), ('b', '企业软件需求二'))):
        # Test-only due-window advance; production clock/schedule are not patched.
        begun, claim, lease = begin_and_claim(env, session)
        tasks.append(begun['task_id'])
        batch = payload(env, begun, lease)
        template = batch['records'][0]
        observed = datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
        batch['records'] = [template | dict(external_source_id=key, public_url=f'https://example.invalid/{key}',
            body=body, published_at='2026-01-01T00:00:00Z', observed_at=observed,
            collector_version='synthetic-v2ex-monitor-v1') for key, body in source_values]
        receipt = submit(env, store, batch)
        assert submit(env, store, batch) == receipt  # Lost receipt must not add another observation.
        candidates.append([item['candidate_id'] for item in receipt['items']])
        versions.append([item['version_id'] for item in receipt['items']])
        finish = dict(schema_version='execution-runtime-v1', request_id=str(uuid4()), operation='FINISH',
            device_id=env.device, credential_version=1, task_id=begun['task_id'],
            platform_run_id=lease['platform_run_id'], lease_id=lease['lease_id'],
            execution_generation=lease['execution_generation'], upload_request_id=batch['request_id'])
        done = sign_apply(env, finish)
        assert sign_apply(env, finish) == done
        assert env.execution.get_task(env.claims, begun['task_id'])['status'] == 'SUCCEEDED'
        assert env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))['state'] == 'WAITING'
    assert len(set(tasks)) == 3
    assert candidates[0][0] == candidates[1][0] == candidates[2][0]
    assert candidates[1][1] == candidates[2][1]
    assert versions[0][0] != versions[1][0]
    assert versions[1] == versions[2]
    with env.admin.connect() as conn:
        for table, expected in [('pilot_candidate_sources', 2), ('pilot_candidate_versions', 3),
                                ('pilot_candidate_observations', 5), ('pilot_candidate_batches', 3),
                                ('pilot_platform_connections', 0), ('pilot_opportunities', 0)]:
            assert conn.execute(f'SELECT count(*) FROM {table} WHERE tenant_id=%s', (env.tenant,)).fetchone() == (expected,)
    detail = store.get_candidate(env.claims, candidates[2][0])
    assert detail['candidate']['current_version']['body'] == '企业软件需求一更新'
    assert detail['candidate']['current_version']['published_at'].startswith('2026-01-01T00:00:00')
    assert detail['observations']['total'] == 3


def test_public_author_context_round_trips_and_creates_content_version(public_monitor_env):
    env = public_monitor_env
    store = CandidateIngestionStore(env.db, env.execution)
    begun, _, lease = begin_and_claim(env, str(uuid4()))
    versions = []
    candidate_id = None
    for request_index, update in enumerate(("项目已结束", "项目已结束，请勿再联系"), start=1):
        value = payload(env, begun, lease)
        value['request_id'] = f'author-context-{request_index}'
        value['records'][0].update(kind='PAGE', external_source_id='1232232',
            public_url='https://www.v2ex.com/t/1232232', author_public_id='author-1',
            body='合成项目主帖', published_at='2025-12-31T00:00:00Z',
            observed_at=f'2026-01-0{request_index}T00:00:00Z',
            normalizer_version='v2ex-author-page-v1',
            source_context={'schema_version':'v2ex-author-context-v1', 'replies_expected':None,
                'replies_read':1, 'replies_complete':False, 'supplements_read':False,
                'author_replies':[{'id':'18012619', 'body':update,
                    'published_at':'2025-12-31T01:00:00Z'}]})
        receipt = submit(env, store, value)
        candidate_id = receipt['items'][0]['candidate_id']
        versions.append(receipt['items'][0]['version_id'])
    assert versions[0] != versions[1]
    detail = store.get_candidate(env.claims, candidate_id)
    current = detail['candidate']['current_version']
    assert set(current) == {'public_url','title','author_public_id','body','published_at','parent',
                            'source_context','version_id','content_version'}
    assert current['title'] is None and current['parent'] is None
    assert current['source_context']['replies_expected'] is None
    assert current['source_context']['author_replies'][0]['body'].endswith('请勿再联系')
    historical = detail['observations']['items'][1]['content']
    assert set(historical) == {'public_url','title','author_public_id','body','published_at','parent','source_context'}
    assert historical['title'] is None and historical['parent'] is None
    assert historical['source_context']['replies_expected'] is None
    assert historical['source_context']['author_replies'][0]['body'] == '项目已结束'
