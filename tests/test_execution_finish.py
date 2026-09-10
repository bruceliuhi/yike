import json

import pytest
from pydantic import ValidationError

from pilot.execution_contract import ExecutionOperation, ExecutionRuntimeError
from tests.test_execution_contract import start_body


def finish_body(**changes):
    return start_body(operation='FINISH', profile_version_id=None, strategy_version_id=None,
                      configuration_sha256=None, targets=None, task_id='task-1',
                      platform_run_id='platform-1', lease_id='lease-1', execution_generation=1,
                      upload_request_id='upload:original.1') | changes


def test_finish_roundtrip():
    body = finish_body()
    assert ExecutionOperation.model_validate(body).model_dump(mode='json') == body


@pytest.mark.parametrize('field,value', [('upload_request_id', None), ('upload_request_id', ''),
    ('upload_request_id', 'bad/key'), ('upload_request_id', 'x'*129), ('execution_generation', True),
    ('lease_id', None), ('platform_run_id', None), ('task_id', None)])
def test_finish_requires_exact_binding(field, value):
    with pytest.raises((ValidationError, ExecutionRuntimeError)):
        ExecutionOperation.model_validate(finish_body(**{field: value}))


@pytest.mark.parametrize('action', ['START', 'CLAIM', 'RENEW', 'CANCEL'])
def test_old_operation_serialization_unchanged(action):
    body = start_body() if action == 'START' else finish_body(operation=action)
    body.pop('upload_request_id', None)
    if action == 'CLAIM': body.update(lease_id=None, execution_generation=None)
    if action == 'CANCEL': body.update(platform_run_id=None, lease_id=None, execution_generation=None)
    body = json.loads(json.dumps(body))
    model = ExecutionOperation.model_validate(body)
    assert model.model_dump(mode='json') == body
    assert model.model_dump(mode='json', exclude={'request_id'}) == {k:v for k,v in body.items() if k != 'request_id'}
    with pytest.raises((ValidationError, ExecutionRuntimeError)):
        ExecutionOperation.model_validate(body | {'upload_request_id':'unexpected'})
