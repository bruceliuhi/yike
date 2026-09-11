from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import json
from uuid import uuid4

import pytest

from pilot.execution_contract import ExecutionRuntimeError
from pilot.research_resource_runner import run_resource


class MemoryEvents:
    """Only runner behavior; database authority is covered by restricted PG tests."""
    def __init__(self):
        self.event = None
        self.fail_begin = False
        self.fail_finish = False
        self.deadline = datetime.now(UTC) + timedelta(seconds=15)

    def begin(self, claims, **request):
        if self.fail_begin:
            raise ExecutionRuntimeError('resource_limit_exceeded')
        if self.event is not None:
            return {'created': False, 'event': deepcopy(self.event)}
        self.event = {'schema_version': 'research-resource-v1', 'reservation_id': str(uuid4()),
            'task_id': request['task_id'], 'run_id': request['run_id'], 'action_id': request['action_id'],
            'permit_id': str(uuid4()), 'research_generation': 1, 'resource': request['resource'],
            'input_sha256': request['input_sha256'], 'status': 'ISSUED', 'output_sha256': None,
            'issued_at': datetime.now(UTC).isoformat(), 'deadline_at': self.deadline.isoformat(), 'finished_at': None}
        return {'created': True, 'event': deepcopy(self.event)}

    def finish(self, claims, **request):
        if self.fail_finish:
            raise RuntimeError('sentinel-private-storage-details')
        assert request['permit_id'] == self.event['permit_id']
        assert all(request[key] == self.event[key] for key in ('task_id', 'run_id', 'action_id'))
        self.event.update(status=request['status'], output_sha256=request.get('output_sha256'),
            finished_at=datetime.now(UTC).isoformat())
        return deepcopy(self.event)


def kwargs():
    return {'task_id': str(uuid4()), 'run_id': str(uuid4()), 'action_id': str(uuid4()),
        'resource': 'SOURCE_READ', 'input_sha256': 'a' * 64}


def test_actual_action_requires_permit_and_finishes_with_canonical_result_digest():
    store, request = MemoryEvents(), kwargs()
    result = {'body': '公开内容', 'count': 1}
    def action(deadline):
        assert store.event['status'] == 'ISSUED'
        assert deadline == store.deadline
        return result
    outcome = run_resource(store, 'synthetic-claims', **request, action=action)
    digest = hashlib.sha256(json.dumps(result, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    assert outcome == {'event': store.event, 'result': result, 'replayed': False}
    assert store.event['status'] == 'SUCCEEDED'
    assert store.event['output_sha256'] == digest


def test_denied_permit_does_not_invoke_action():
    store, called = MemoryEvents(), []
    store.fail_begin = True
    with pytest.raises(ExecutionRuntimeError, match='resource_limit_exceeded'):
        run_resource(store, None, **kwargs(), action=lambda _: called.append(True))
    assert called == []
    assert store.event is None


@pytest.mark.parametrize('state', ['ISSUED', 'SUCCEEDED', 'UNKNOWN'])
def test_recovery_returns_only_existing_event_without_refetch(state):
    store, request, called = MemoryEvents(), kwargs(), []
    store.begin(None, **request)
    store.event['status'] = state
    outcome = run_resource(store, None, **request, action=lambda _: called.append(True))
    assert outcome == {'event': store.event, 'result': None, 'replayed': True}
    assert called == []


def test_exception_is_unknown_with_no_secret_and_no_automatic_retry():
    store, request, called = MemoryEvents(), kwargs(), []
    def action(_):
        called.append(True)
        raise RuntimeError('sentinel-private-action')
    outcome = run_resource(store, None, **request, action=action)
    assert outcome['event']['status'] == 'UNKNOWN'
    assert outcome['event']['output_sha256'] is None
    assert 'sentinel' not in str(outcome)
    assert run_resource(store, None, **request, action=action)['replayed'] is True
    assert called == [True]


@pytest.mark.parametrize('value', [float('nan'), {'large': 'x' * 1_048_576}, {'opaque': object()}])
def test_unusable_action_result_cannot_be_reported_success(value):
    result = run_resource(MemoryEvents(), None, **kwargs(), action=lambda _: value)
    assert result['event']['status'] == 'UNKNOWN'
    assert result['result'] is None


def test_failed_outcome_write_keeps_issued_and_does_not_return_success():
    store = MemoryEvents()
    store.fail_finish = True
    with pytest.raises(ExecutionRuntimeError, match='resource_unavailable') as failure:
        run_resource(store, None, **kwargs(), action=lambda _: {'ok': True})
    assert 'sentinel' not in str(failure.value)
    assert store.event['status'] == 'ISSUED'


def test_expired_permit_does_not_begin_network_action():
    store, called = MemoryEvents(), []
    store.deadline = datetime.now(UTC) - timedelta(seconds=1)
    outcome = run_resource(store, None, **kwargs(), action=lambda _: called.append(True))
    assert called == []
    assert outcome['event']['status'] == 'UNKNOWN'


def test_success_completion_receives_canonical_result_instead_of_normal_finish():
    store, request, completed = MemoryEvents(), kwargs(), []
    store.fail_finish = True
    value = {'source': '原文'}
    def complete(event, result, digest):
        assert event == store.event and event['status'] == 'ISSUED'
        assert result == value and result is not value
        assert digest == hashlib.sha256(json.dumps(value, ensure_ascii=False,
            sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        completed.append(result)
        store.event.update(status='SUCCEEDED', output_sha256=digest,
                           finished_at=datetime.now(UTC).isoformat())
        return deepcopy(store.event)
    outcome = run_resource(store, None, **request, action=lambda _: value, on_success=complete)
    assert outcome['event']['status'] == 'SUCCEEDED'
    assert completed == [value]
    assert run_resource(store, None, **request, action=lambda _: pytest.fail('refetched'),
                        on_success=complete)['replayed'] is True
    assert completed == [value]


def test_failure_does_not_call_success_completion():
    def fail(_):
        raise ValueError('source_failed')
    outcome = run_resource(MemoryEvents(), None, **kwargs(), action=fail,
        on_success=lambda *_: pytest.fail('failed source was committed'))
    assert outcome['event']['status'] == 'UNKNOWN'


def test_completion_failure_leaves_original_issued_without_fallback_finish():
    store = MemoryEvents()
    def fail(*_):
        raise ValueError('sentinel-private-commit')
    with pytest.raises(ExecutionRuntimeError, match='resource_unavailable'):
        run_resource(store, None, **kwargs(), action=lambda _: {'ok': True}, on_success=fail)
    assert store.event['status'] == 'ISSUED'


def test_invalid_completion_is_rejected_before_admission():
    store = MemoryEvents()
    with pytest.raises(ExecutionRuntimeError, match='invalid_request'):
        run_resource(store, None, **kwargs(), action=lambda _: None, on_success=True)
    assert store.event is None
