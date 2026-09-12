from copy import deepcopy
from uuid import uuid4
import pytest
from pydantic import ValidationError
from pilot.research_strategy_contract import ResearchStrategyConfiguration, PrepareStrategyRequest
from tests.test_research_strategies_postgres import configuration


def planned():
    return configuration() | {'publicSource': 'v2ex-latest-v1', 'research': {
        'version': 1, 'demandTypes': ['INQUIRY'], 'maxSoubei': 10,
        'limits': {'sources': 3, 'minutes': 10, 'modelCalls': 10},
        'stopAtAnyLimit': True, 'evidenceOrder': 'SOURCE_MATCH_CONTEXT',
        'sourcePlan': {'version': 1, 'sources': ['v2ex-latest-v1', 'v2ex-qna-v1']}}}


def test_plan_roundtrip_and_legacy_bytes():
    value = planned()
    assert ResearchStrategyConfiguration.model_validate(value).model_dump(mode='json') == value
    del value['research']['sourcePlan']
    assert ResearchStrategyConfiguration.model_validate(value).model_dump(mode='json') == value


@pytest.mark.parametrize('plan', [None, {'version': True, 'sources': ['v2ex-latest-v1','v2ex-qna-v1']},
    {'version': 1, 'sources': ['v2ex-latest-v1']}, {'version': 1, 'sources': ['v2ex-latest-v1']*2},
    {'version': 1, 'sources': ['v2ex-latest-v1','unknown']},
    {'version': 1, 'sources': ['v2ex-latest-v1','v2ex-qna-v1'], 'extra': 1}])
def test_invalid_plan(plan):
    value = planned(); value['research']['sourcePlan'] = plan
    with pytest.raises(ValidationError): ResearchStrategyConfiguration.model_validate(value)


@pytest.mark.parametrize('field,value', [('publicSource','v2ex-qna-v1'), ('source','links'), ('mode','monitor')])
def test_plan_configuration_relations(field, value):
    with pytest.raises(ValidationError): ResearchStrategyConfiguration.model_validate(planned() | {field:value})


@pytest.mark.parametrize('platforms,records', [(['PUBLIC_WEB','BILIBILI'], 3), (['PUBLIC_WEB'],1), (['PUBLIC_WEB'],101)])
def test_plan_scope_budget(platforms, records):
    with pytest.raises(ValidationError):
        PrepareStrategyRequest.model_validate(dict(request_id=str(uuid4()), draft_id=str(uuid4()),
            draft_revision=1, profile_version_id=str(uuid4()), configuration=planned(),
            platforms=platforms, max_records=records, max_runtime_seconds=600))


def test_plan_snapshot_rechecks_budget_and_fixed_actions():
    from pilot.research_runtime_config import public_research_snapshot
    from pilot.research_source_catalog import source_plan_action, source_record_limits, source_for_action
    from pilot.execution_contract import ExecutionRuntimeError
    from uuid import UUID, uuid5
    snapshot = dict(configuration=planned(), platforms=['PUBLIC_WEB'], max_records=3)
    assert public_research_snapshot(snapshot)
    assert source_record_limits(snapshot) == (2, 1)
    for total in [None, True, 1, 101]:
        assert not public_research_snapshot(snapshot | {'max_records':total})
    bad = deepcopy(snapshot); bad['configuration']['research']['limits']['sources'] = 1
    assert not public_research_snapshot(bad)
    task, run = str(uuid4()), str(uuid4())
    action = source_plan_action(task, run, 'v2ex-qna-v1')
    assert action == str(uuid5(UUID(run), 'research-source-plan-v1:' + task + ':v2ex-qna-v1'))
    assert source_for_action(snapshot, task, run, action).source_id == 'v2ex-qna-v1'
    with pytest.raises(ExecutionRuntimeError): source_for_action(snapshot, task, run, str(uuid4()))
