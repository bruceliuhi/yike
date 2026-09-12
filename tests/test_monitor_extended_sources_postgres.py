"""Declared monitor policies must reach the real reservation/START path."""
from uuid import uuid4

import pytest

from pilot import foreground_collection as policies
from pilot.execution_contract import ExecutionRuntimeError
from pilot.research_strategies import ResearchStrategyStore
from tests.test_monitor_runtime_postgres import (
    runtime_databases, runtime_env, runtime_pulse, force_due_window, sign_apply,
)
from tests.test_public_node_collection import configuration


def prepare_source(env, source, platform):
    if platform == 'PUBLIC_WEB':
        env.target = dict(platform=platform, access_mode='PUBLIC_ANONYMOUS',
            connection_id=None, connection_version=None)
    else:
        from pilot.store import PilotStore
        connection = PilotStore(env.database).connect_platform(env.user, platform,
            env.device, 'synthetic-monitor-zhihu', 'vault://synthetic-monitor-zhihu')
        with env.admin.connect() as db:
            version = db.execute("UPDATE pilot_platform_connections SET status='CONNECTED' "
                "WHERE connection_id=%s RETURNING connection_version", (connection['connection_id'],)).fetchone()[0]
        env.target = dict(platform=platform, access_mode='PLATFORM_ACCOUNT',
            connection_id=connection['connection_id'], connection_version=version)
    schedule = dict(kind='interval', times=[], interval=1, start='00:00', end='23:59',
        timezone='UTC', policyVersion=1)
    config = configuration(mode='monitor', schedule=schedule)
    if platform == 'PUBLIC_WEB':
        config['publicSource'] = source
    else:
        config.pop('publicSource')
    strategies = ResearchStrategyStore(env.database)
    prepared = strategies.prepare(env.claims, dict(schema_version='strategy-confirmation-v1',
        request_id=str(uuid4()), draft_id=str(uuid4()), draft_revision=1,
        profile_version_id=env.profile, configuration=config,
        platforms=[platform], max_records=10, max_runtime_seconds=600))
    env.strategy = strategies.confirm(env.claims, dict(schema_version='strategy-confirmation-v1',
        request_id=str(uuid4()), strategy_version_id=prepared['strategy_version_id'],
        configuration_sha256=prepared['configuration_sha256'], human_confirmed=True))
    env.plan = env.plans.create(env.claims, dict(schema_version='monitor-plans-v1',
        request_id=str(uuid4()), profile_version_id=env.profile,
        strategy_version_id=env.strategy['strategy_version_id'], human_confirmed=True))['plan']


@pytest.mark.parametrize('policy', [policies.four_platform_public_project_monitor_policy,
    policies.four_platform_public_bili_links_monitor_policy])
@pytest.mark.parametrize('platform,source', [('PUBLIC_WEB','v2ex-latest-v1'),
    ('PUBLIC_WEB','v2ex-qna-v1'), ('PUBLIC_WEB','v2ex-outsourcing-authors-v1'), ('ZHIHU',None)])
def test_declared_source_reaches_due_reservation_and_signed_start(runtime_env, policy, platform, source):
    env = runtime_env
    prepare_source(env, source, platform)
    env.execution.capability_check = policy
    support = env.monitor.support(env.claims)
    assert support['mode'] is not None
    if source:
        assert source in support['public_sources']
    pulse = runtime_pulse(env)
    first = env.monitor.pulse(env.claims, pulse)
    assert first['occurrence'] is None
    force_due_window(env)
    ready = env.monitor.pulse(env.claims, pulse)
    assert ready['state'] == 'READY'
    started = sign_apply(env, ready['occurrence']['start_request'])
    assert started['task_id']
    assert env.monitor.pulse(env.claims, pulse)['state'] == 'RUNNING'


def test_old_policy_does_not_gain_public_project_monitoring(runtime_env):
    env = runtime_env
    prepare_source(env, 'v2ex-outsourcing-authors-v1', 'PUBLIC_WEB')
    env.execution.capability_check = policies.four_platform_public_node_monitor_policy
    with pytest.raises(ExecutionRuntimeError, match='capability_unavailable'):
        env.monitor.pulse(env.claims, runtime_pulse(env))
