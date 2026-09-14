"""STOP contract and cancellation state regression tests."""
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from pilot.execution_contract import ExecutionOperation, ExecutionRuntimeError
from pilot.execution_runtime import ExecutionRuntime
from tests.test_execution_finish import finish_body


def stop_body(**changes):
    body = finish_body(operation='STOP', device_id='00000000-0000-4000-8000-000000000001')
    body.pop('upload_request_id')
    return body | changes


def test_stop_roundtrip_has_no_upload():
    body = stop_body()
    assert ExecutionOperation.model_validate(body).model_dump(mode='json') == body


@pytest.mark.parametrize('field,value', [
    ('task_id', None), ('platform_run_id', None), ('lease_id', None),
    ('execution_generation', None), ('execution_generation', True),
    ('execution_generation', 0), ('credential_version', 0),
    ('upload_request_id', 'unexpected'), ('upload_request_id', None), ('native_progress_version', 1),
    ('public_sampling_version', 1), ('targets', []),
])
def test_stop_requires_exact_binding(field, value):
    with pytest.raises((ExecutionRuntimeError, ValidationError)):
        ExecutionOperation.model_validate(stop_body(**{field: value}))


class Cursor:
    def __init__(self):
        self.writes = []

    def execute(self, sql, params):
        self.writes.append((sql, params))


def state(monkeypatch, statuses):
    runtime = ExecutionRuntime(None)
    task = dict(task_id='task-1', device_id=stop_body()['device_id'],
                status='CANCELLING', configuration_snapshot={})
    run = dict(run_id='run-1', status='CANCELLING')
    platforms = [dict(platform_run_id=f'platform-{i+1}', status=status,
                      execution_generation=generation, lease_id='lease-1', credential_version=1)
                 for i, (status, generation) in enumerate(statuses)]
    monkeypatch.setattr(runtime, '_peek_task', lambda *args: task)
    monkeypatch.setattr(runtime, '_locks', lambda *args: (task, run, platforms))
    monkeypatch.setattr(runtime, '_research_row', lambda *args, **kwargs: None)
    def forbidden(*args, **kwargs):
        pytest.fail('STOP must not require live execution authority')
    monkeypatch.setattr(runtime, '_versions', forbidden)
    monkeypatch.setattr(runtime, '_live', forbidden)
    return runtime, task, run, platforms


@pytest.mark.parametrize('other,expected', [('CANCELLING', 'CANCELLING'), ('CANCELED', 'CANCELED'), ('SUCCEEDED', 'CANCELED')])
def test_stop_only_acknowledges_bound_platform_and_aggregates(monkeypatch, other, expected):
    runtime, _, _, _ = state(monkeypatch, [('CANCELLING', 1), (other, 1)])
    cursor = Cursor()
    receipt = runtime._mutate(cursor, SimpleNamespace(user_id='user'), 'tenant',
                              ExecutionOperation.model_validate(stop_body()))
    assert receipt == dict(task_id='task-1', run_id='run-1', platform_run_id='platform-1',
                          lease_id='lease-1', execution_generation=1, status=expected,
                          stop_confirmed=expected == 'CANCELED')
    assert len(cursor.writes) == 3
    assert cursor.writes[0][1][-1] == 'platform-1'


def test_cancel_preserves_acknowledged_platform(monkeypatch):
    runtime, _, _, _ = state(monkeypatch, [('CANCELED', 1), ('SUCCEEDED', 1)])
    request = ExecutionOperation.model_validate(stop_body(operation='CANCEL', platform_run_id=None,
                                                          lease_id=None, execution_generation=None))
    assert runtime._mutate(Cursor(), SimpleNamespace(user_id='user'), 'tenant', request)['status'] == 'CANCELED'
