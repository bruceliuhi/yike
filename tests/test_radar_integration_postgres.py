"""Same-session preview and signed task use one planner and existing PG records.

Disposable database and synthetic profile only; no external search/model call.
"""
import json
from uuid import uuid4

from tests.test_customer_research_context_postgres import (
    databases, env, execution_databases, execution_env, raw_databases, raw_env,
    real_strategy_env, context_env, dynamic_start, load,
)
from tests.test_pilot_runtime_http_postgres import ordinary_client


def test_customer_preview_matches_signed_runtime_without_a_second_task_or_charge(monkeypatch, context_env):
    env = context_env
    execution = dynamic_start(env)
    compiled = load(env, execution)
    context = json.loads(compiled['context_json'])
    configuration = env.snapshot['configuration']
    payload = dict(contractVersion=1, requestId=str(uuid4()),
        querySeeds=context['query_seeds'], intentSignals=[], exclusions=context['exclusions'], region='',
        demandTypes=configuration['research']['demandTypes'])
    with env.admin.connect() as connection:
        before_tasks = connection.execute('SELECT count(*) FROM pilot_collection_tasks').fetchone()[0]
        before_usage = connection.execute('SELECT count(*) FROM pilot_research_resource_events').fetchone()[0]
    with ordinary_client(monkeypatch, env) as client:
        response = client.post('/api/ui/research-plan/preview', json=payload)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['accountScope']['id'] == env.tenant
        assert result['userId'] == env.claims.user_id
        assert result['plan']['queries'] == compiled['query_portfolio']
        assert response.headers['cache-control'] == 'no-store'
        assert client.post('/api/ui/research-plan/preview', json=payload | {'tenantId': 'foreign'}).status_code == 422
        client.headers.pop('Authorization')
        assert client.post('/api/ui/research-plan/preview', json=payload).status_code == 401
    with env.admin.connect() as connection:
        assert connection.execute('SELECT count(*) FROM pilot_collection_tasks').fetchone()[0] == before_tasks
        assert connection.execute('SELECT count(*) FROM pilot_research_resource_events').fetchone()[0] == before_usage
