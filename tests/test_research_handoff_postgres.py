"""Two-candidate closeout on restricted PG; all sources and models synthetic."""
import time

from pilot.research_effects import dispatch_effect
from tests.test_candidate_review_postgres import (
    databases, env, execution_databases, execution_env, raw_databases, raw_env,
)
from tests.test_customer_research_context_postgres import context_env, real_strategy_env
from tests.test_dynamic_research_runtime import (
    dynamic_env, mission_completed, read_result, service, wait_terminal,
)
from tests.test_research_effect_contract import model_payload, model_result


def test_two_candidates_finish_after_research_spends_entire_allocated_model_budget(dynamic_env):
    env = dynamic_env
    research_calls = []

    def mission(_description, **kwargs):
        dispatcher = kwargs['effect_dispatcher']
        deadline = time.monotonic() + 20
        for index in range(kwargs['max_requests']):
            payload = model_payload()
            payload['input'][0]['content'] = f'synthetic research step {index}'
            dispatch_effect(dispatcher, kind='MODEL', payload=payload,
                            deadline=deadline, perform=lambda _: model_result())
            research_calls.append(index)
        pages = []
        for suffix in ('a', 'b'):
            value = read_result()
            value['evidence']['url'] = 'https://example.com/buyer-' + suffix
            dispatch_effect(dispatcher, kind='READ',
                            payload={'url': value['evidence']['url']}, deadline=deadline,
                            perform=lambda _, value=value: value)
            pages.append(value['evidence'])
        return mission_completed(kwargs, pages)

    runtime = service(env, mission)
    task_id, run_id = env.execution['task_id'], env.execution['run_id']
    try:
        runtime.advance(env.claims, task_id, run_id)
        result = wait_terminal(runtime, env, timeout=20)
        assert result['phase'] == 'COMPLETED', result
        assert result['acceptedOriginals'] == result['analyzedOriginals'] == 2
        assert len(result['candidateIds']) == 2
        assert result['discovery']['unpublishedOriginals'] == 0
        assert env.reviews.model.calls == 2
        used = result['usage']['modelCalls']['issued']
        assert used == len(research_calls) + 2
        assert used <= 10  # dynamic_start's confirmed total; no extra budget.
        assert result['usage']['modelCalls']['succeeded'] == used
        assert result['usage']['modelCalls']['unknown'] == 0
        assert runtime.advance(env.claims, task_id, run_id)['phase'] == 'COMPLETED'
        assert env.reviews.model.calls == 2
        assert runtime.status(env.claims, task_id)['usage']['modelCalls']['issued'] == used
    finally:
        runtime.shutdown(timeout_seconds=2)
