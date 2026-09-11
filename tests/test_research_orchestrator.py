"""Sequence policy tests; actual store idempotency is covered separately in PG."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from pilot.candidate_review_contract import CandidateReviewError
from pilot.execution_contract import ExecutionRuntimeError


def setup_sequence(count=2):
    from pilot.research_orchestrator import ResearchOrchestrator
    task, run, platform, profile, strategy = [str(uuid4()) for _ in range(5)]
    event = {"status": "SUCCEEDED"}
    receipt = {"task_id": task, "run_id": run, "accepted_count": count,
               "platform_run_id": platform, "items": []}
    details, views, requests, effects, reads = {}, {}, {}, [], []
    for index in range(count):
        candidate, version, observation = [str(uuid4()) for _ in range(3)]
        receipt['items'].append(dict(index=index, candidate_id=candidate, version_id=version,
                                     observation_id=observation, revision=1))
        details[candidate] = {"candidate": dict(candidate_id=candidate, revision=1,
            current_version={"version_id": version}, current_observation_id=observation,
            ambiguous=False, profile_version_id=profile, strategy_version_id=strategy, platform='PUBLIC_WEB'),
            "observations": {"items": [dict(observation_id=observation, task_id=task, run_id=run,
                platform_run_id=platform, execution_context={"kind": "research-resource-v1"})]}}
        views[candidate] = dict(id=candidate, revision=1, sourceVersionId=version,
            profileId=profile, profileVersion=2, strategyVersionId=strategy,
            currentBindingValid=True, status='PENDING_REVIEW')
    task_value = dict(task_id=task, run_id=run, profile_version_id=profile,
        strategy_version_id=strategy, status='PENDING', platform_runs=[{'platform': 'PUBLIC_WEB'}])

    def read(_claims, **kwargs):
        reads.append(kwargs['action_id'])
        value = deepcopy(receipt) | {'request_id': kwargs['action_id']}
        for detail in details.values():
            for obs in detail['observations']['items']:
                obs['request_id'] = kwargs['action_id']
                obs['execution_context'].update(action_id=kwargs['action_id'], task_id=task, run_id=run)
        return dict(event=deepcopy(event), receipt=value, replayed=len(reads)>1)

    def get_request(_claims, request_id):
        if request_id not in requests:
            raise CandidateReviewError('request_not_found', 404)
        return deepcopy(requests[request_id])

    def assess(_claims, payload, **origin):
        effects.append((deepcopy(payload), origin))
        result = dict(kind='assessment', requestId=payload['requestId'], candidateId=payload['candidateId'],
            assessment={'id': str(uuid4()), 'sendingAuthorized': False, 'effectiveDecision': 'REVIEW'})
        requests[payload['requestId']] = result
        return result

    runtime = SimpleNamespace(get_task=lambda *_: deepcopy(task_value))
    sources = SimpleNamespace(resources=SimpleNamespace(runtime=runtime), read_public=read)
    reviews = SimpleNamespace(get_request=get_request, assess_research=assess,
        get_candidate=lambda _, candidate: deepcopy(details[candidate]),
        list_candidates=lambda _, **kw: {'items': [deepcopy(views[item]) for item in kw['ids']]})
    orchestrator = ResearchOrchestrator(sources, reviews)
    return SimpleNamespace(orchestrator=orchestrator, sources=sources, reviews=reviews,
        task=task, run=run, task_value=task_value, details=details, views=views, event=event,
        receipt=receipt, requests=requests, effects=effects, reads=reads,
        execute=lambda: orchestrator.run(object(), task_id=task, run_id=run))


def test_sequence_uses_exact_receipt_and_recovery_does_not_assess_again():
    env = setup_sequence()
    first = env.execute()
    assert first['phase'] == 'ANALYZED'
    assert first['analyzed_originals'] == first['accepted_originals'] == 2
    assert first['sending_authorized'] is False
    assert len(env.effects) == 2
    for (payload, origin), item in zip(env.effects, env.receipt['items']):
        assert payload['profileVersion'] == 2
        assert payload['candidateId'] == item['candidate_id']
        assert origin == dict(task_id=env.task, run_id=env.run, observation_id=item['observation_id'])
        assert payload['action'] == 'ASSESS' and 'retryOf' not in payload
    assert env.execute() == first
    assert env.reads[0] == env.reads[1]
    assert len(env.effects) == 2


@pytest.mark.parametrize('state', ['ISSUED', 'UNKNOWN', 'FAILED'])
def test_incomplete_source_never_assesses(state):
    env = setup_sequence()
    env.event['status'] = state
    result = env.execute()
    assert result['phase'] == 'SOURCE_PENDING'
    assert result['analyzed_originals'] == 0 and not env.effects


def test_empty_source_is_not_a_successful_lead_search():
    result = setup_sequence(0).execute()
    assert result['phase'] == 'NO_ORIGINALS' and result['accepted_originals'] == 0


@pytest.mark.parametrize('change', ['ambiguous', 'version', 'observation', 'task'])
def test_changed_candidate_is_skipped_not_charged_to_another_observation(change):
    env = setup_sequence(1)
    detail = next(iter(env.details.values()))
    if change == 'ambiguous': detail['candidate']['ambiguous'] = True
    if change == 'version': detail['candidate']['current_version']['version_id'] = str(uuid4())
    if change == 'observation': detail['candidate']['current_observation_id'] = str(uuid4())
    if change == 'task': detail['observations']['items'][0]['task_id'] = str(uuid4())
    result = env.execute()
    assert result['phase'] == 'PARTIAL' and result['skipped_originals'] == 1
    assert not env.effects


@pytest.mark.parametrize('kind,status', [('pending','UNKNOWN'),('pending','PROCESSING'),('failure','FAILED')])
def test_uncertain_or_failed_review_stops_queue_and_is_not_retried(kind, status):
    env = setup_sequence()
    def pending(_claims, payload, **_origin):
        env.effects.append(payload)
        result = dict(kind=kind, status=status, requestId=payload['requestId'])
        env.requests[payload['requestId']] = result
        return result
    env.reviews.assess_research = pending
    assert env.execute()['phase'] == 'STOPPED'
    assert env.execute()['phase'] == 'STOPPED'
    assert len(env.effects) == 1


def test_limit_error_preserves_partial_results_and_session_error_does_not():
    env = setup_sequence()
    original = env.reviews.assess_research
    def limited(*args, **kwargs):
        if env.effects: raise ExecutionRuntimeError('resource_limit_exceeded',409)
        return original(*args, **kwargs)
    env.reviews.assess_research = limited
    result = env.execute()
    assert result['phase'] == 'STOPPED' and result['analyzed_originals'] == 1
    assert result['stop_code'] == 'resource_limit_exceeded'
    env.reviews.get_request = lambda *_: (_ for _ in ()).throw(CandidateReviewError('invalid_session',401))
    with pytest.raises(CandidateReviewError, match='invalid_session'): env.execute()


def test_other_run_and_platform_are_denied_before_read():
    env = setup_sequence()
    env.task_value['run_id'] = str(uuid4())
    with pytest.raises(ExecutionRuntimeError): env.execute()
    assert not env.reads
    env.task_value['run_id'] = env.run
    env.task_value['platform_runs'].append({'platform':'XIAOHONGSHU'})
    with pytest.raises(ExecutionRuntimeError): env.execute()
    assert not env.reads
