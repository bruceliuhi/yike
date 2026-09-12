import json
import os
from pathlib import Path
import pytest
from tests.test_candidate_review_postgres import (BoundaryModel, databases, env,
    execution_databases, execution_env, raw_databases, raw_env)
from tests.test_confirmed_strategy_review_postgres import real_strategy_env
from tests.test_research_runtime_postgres import runtime_env, _runtime, _stable
from tests.test_research_source_plan import planned
from tests.test_research_strategies_postgres import prepare_body, confirm_body
from tests.test_research_candidates_postgres import topic
from tests.test_candidate_assessment_model import CONTENT


@pytest.mark.parametrize('kind', ['normal', 'empty', 'duplicate', 'failed', 'three', 'pending', 'knownfail'])
def test_plan_authenticated_http(runtime_env, kind):
    from fastapi.testclient import TestClient
    from pilot.auth import issue_token, verify_token_claims
    from pilot.web import build_app
    from pilot.research_runtime_config import public_research_policy, public_research_snapshot
    from tests.test_execution_runtime_postgres import SECRET, start
    from tests.test_research_quote_postgres import _request
    from tests.test_research_execution_postgres import services, signed_start
    env = runtime_env
    token = issue_token(env.claims.user_id, SECRET)
    env.claims = verify_token_claims(token, SECRET)
    config = planned()
    if kind == 'three': config['research']['sourcePlan']['sources'].append('v2ex-outsourcing-authors-v1')
    pending = env.strategies.prepare(env.claims, prepare_body(env, configuration=config, max_records=3))
    env.confirmed = env.strategies.confirm(env.claims, confirm_body(pending))
    env.snapshot = env.confirmed['snapshot']
    env.runtime.capability_check = public_research_policy
    quotes, service = services(env); quotes.research_capability = public_research_snapshot
    request = start(env)
    quote = quotes.quote(env.claims, _request(env, env.confirmed) | {'requestId': request.request_id})
    reads = []
    class Model(BoundaryModel):
        def assess_before(self, deadline, **kwargs): return self.assess(**kwargs)
    model = Model()
    def fetch(deadline):
        index = len(reads); reads.append(index)
        if kind == 'failed': raise TimeoutError('synthetic unknown source')
        if kind == 'empty' and index == 0: return []
        return [topic(2500 + (0 if kind == 'duplicate' else index * 10) + n,
            node={'name': ['qna','qna','outsourcing'][index]},
            title=CONTENT['title'], content=CONTENT['body']) for n in range(3)]
    runtime = _runtime(env, fetcher=fetch, model=model)
    http = TestClient(build_app(env.store, auth_secret=SECRET, research_execution=service,
        research_runtime=runtime), base_url='https://pilot.example')
    headers = {'Authorization': 'Bearer ' + token}
    cap = http.get('/api/ui/research-execution/capability?source_plan_version=1', headers=headers)
    assert cap.status_code == 200 and cap.json()['contractVersion'] == 3
    for query in ['source_plan_version=2','source_plan_version=1&source_catalog_version=1',
                  'source_plan_version=1&source_plan_version=1','unknown=1']:
        assert http.get('/api/ui/research-execution/capability?' + query, headers=headers).status_code == 422
    begun = http.post('/api/ui/research-execution/start', headers=headers, json={
        'request': request.model_dump(mode='json'), 'signature': signed_start(env, request),
        'authorization_token': quote['authorizationToken']})
    assert begun.status_code == 200, begun.json()
    execution = begun.json()['execution']; task, run = execution['task_id'], execution['run_id']
    path = '/api/ui/research-execution/tasks/' + task
    queued = http.get(path, headers=headers).json()
    assert queued['contractVersion'] == 3 and queued['acceptedOriginals'] is None
    if kind in ('pending', 'knownfail'):
        from pilot.research_source_catalog import source_plan_action, research_source
        resources = runtime.orchestrator.sources.resources
        scope = dict(task_id=task, run_id=run, action_id=source_plan_action(task, run, 'v2ex-latest-v1'))
        event = resources.begin(env.claims, **scope, resource='SOURCE_READ',
            input_sha256=research_source('v2ex-latest-v1').input_sha)['event']
        if kind == 'knownfail':
            resources.finish(env.claims, **scope, permit_id=event['permit_id'], status='FAILED')
        blocked = http.post(path+'/advance', headers=headers, json={'runId':run}).json()
        assert not blocked['canAdvance'] and blocked['acceptedOriginals'] is None
        assert blocked['sourceProgress'][0]['phase'] == ('PENDING' if kind == 'pending' else 'FAILED')
        assert blocked['sourceProgress'][1]['phase'] == 'NOT_STARTED'
        assert reads == [] and model.calls == 0
        return
    first = http.post(path+'/advance', headers=headers, json={'runId':run}).json()
    assert first['phase'] != 'COMPLETED' and first['acceptedOriginals'] is None
    assert model.calls == 0 and reads == [0]
    if kind == 'failed':
        assert not first['canAdvance']
        assert _stable(http.post(path+'/advance', headers=headers, json={'runId':run}).json()) == _stable(first)
        assert reads == [0]
        return
    assert first['canAdvance']
    assert first['phase'] == 'RUNNING'
    from uuid import uuid4
    from pilot.execution_contract import ExecutionRuntimeError
    from pilot.research_source_catalog import source_plan_action, research_source
    from pilot.research_public_reader import _public_topics
    from tests.test_research_candidates_postgres import canonical_result
    sources = runtime.orchestrator.sources
    with pytest.raises(ExecutionRuntimeError, match='request_conflict'):
        sources.read_public(env.claims, task_id=task, run_id=run, action_id=str(uuid4()),
            fetcher=lambda _: pytest.fail('unbound read'))
    action = source_plan_action(task, run, 'v2ex-outsourcing-authors-v1')
    if kind != 'three':
        with pytest.raises(ExecutionRuntimeError, match='request_conflict'):
            sources.read_public(env.claims, task_id=task, run_id=run, action_id=action,
                fetcher=lambda _: pytest.fail('unselected source'))
    event = sources.resources.get(env.claims, task_id=task, run_id=run,
        action_id=source_plan_action(task, run, 'v2ex-latest-v1'))
    value = _public_topics([], 'v2ex-qna-v1')
    with pytest.raises(ExecutionRuntimeError, match='request_conflict'):
        sources.commit_index(env.claims, event=event | {'input_sha256':research_source('v2ex-qna-v1').input_sha},
            result=value, output_sha256=canonical_result(value))
    second = http.post(path+'/advance', headers=headers, json={'runId':run}).json()
    assert model.calls == 0 and reads == [0,1]
    current = second
    for _ in range(5):
        if current['phase'] == 'COMPLETED': break
        current = http.post(path+'/advance', headers=headers, json={'runId':run}).json()
    assert current['phase'] == 'COMPLETED', current
    assert current['acceptedOriginals'] == (1 if kind == 'empty' else 3)
    assert current['analyzedOriginals'] + current['skippedOriginals'] == current['acceptedOriginals']
    if kind == 'duplicate': assert len(current['candidateIds']) == 2 and current['skippedOriginals'] == 1
    assert all(p['phase'] == 'SUCCEEDED' and p['acceptedOriginals'] <= p['recordLimit'] for p in current['sourceProgress'])
    recovered = _runtime(env, fetcher=lambda _: pytest.fail('no refetch'), model=model)
    assert _stable(recovered.advance(env.claims, task, run)) == _stable(current)
    if kind == 'normal' and (output := os.getenv('YIKE_SOURCE_PLAN_HTTP_OUTPUT')):
        Path(output).write_text(json.dumps({'capability':cap.json(), 'queued':queued,
            'afterFirstSource':first, 'afterAllSources':second, 'completed':current,
            'evidenceKind':'local_authenticated_http_restricted_postgresql_synthetic_source_and_model'}, ensure_ascii=False, indent=2))
