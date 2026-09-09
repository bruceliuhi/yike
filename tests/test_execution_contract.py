import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pilot.auth import issue_token, verify_token_claims
from pilot.execution_contract import ExecutionOperation, ExecutionRuntimeError, ExecutionTarget
from pilot.execution_runtime import ExecutionRuntime, execution_signing_payload


def start_body(**changes):
    return dict(schema_version='execution-runtime-v1', request_id=str(uuid4()),
                operation='START', device_id=str(uuid4()), credential_version=1,
                profile_version_id='profile-1', strategy_version_id='strategy-1',
                configuration_sha256='a' * 64, targets=(dict(platform='PUBLIC_WEB',
                access_mode='PUBLIC_ANONYMOUS', connection_id=None, connection_version=None),),
                task_id=None, platform_run_id=None, lease_id=None, execution_generation=None) | changes


def test_strict_frozen_operation_and_order():
    value = ExecutionOperation.model_validate(start_body())
    assert value.operation == 'START'
    with pytest.raises(ValidationError):
        value.operation = 'CANCEL'
    with pytest.raises((ValidationError, ExecutionRuntimeError)):
        ExecutionOperation.model_validate(value.model_copy(update={'credential_version': True}))


def test_http_json_arrays_are_frozen_and_revalidated():
    body = json.loads(json.dumps(start_body()))
    value = ExecutionOperation.model_validate(body)
    assert isinstance(value.targets, tuple)
    assert value.model_dump(mode='json') == body
    with pytest.raises((ValidationError, ExecutionRuntimeError)):
        ExecutionOperation.model_validate(value.model_copy(update={'targets': (
            value.targets[0].model_copy(update={'platform': 'INVALID'}),)}))


@pytest.mark.parametrize('changes', [
    {'credential_version': True}, {'credential_version': '1'}, {'extra': 'secret'},
    {'request_id': 'AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA'}, {'device_id': 'device'},
    {'task_id': 'not-applicable'}, {'configuration_sha256': 'A' * 64}, {'targets': ()},
    {'targets': (dict(platform='DOUYIN', access_mode='PUBLIC_ANONYMOUS', connection_id=None),)},
    {'targets': (dict(platform='BILIBILI', access_mode='PLATFORM_ACCOUNT', connection_id='connection', connection_version=1),)},
])
def test_rejects_malformed_start(changes):
    with pytest.raises((ValidationError, ExecutionRuntimeError)):
        ExecutionOperation.model_validate(start_body(**changes))


def test_targets_unique_and_request_order_preserved():
    first = dict(platform='BILIBILI', access_mode='PLATFORM_ACCOUNT', connection_id=str(uuid4()), connection_version=1)
    second = dict(platform='DOUYIN', access_mode='PLATFORM_ACCOUNT', connection_id=str(uuid4()), connection_version=1)
    value = ExecutionOperation.model_validate(start_body(targets=(first, second)))
    assert [t.platform for t in value.targets] == ['BILIBILI', 'DOUYIN']
    with pytest.raises((ValidationError, ExecutionRuntimeError)):
        ExecutionOperation.model_validate(start_body(targets=(first, first)))


@pytest.mark.parametrize('action', ['CLAIM', 'RENEW', 'CANCEL'])
def test_non_start_shape(action):
    body = start_body(operation=action, profile_version_id=None, strategy_version_id=None,
                      configuration_sha256=None, targets=None, task_id='task-1',
                      platform_run_id=None if action == 'CANCEL' else 'platform-run-1',
                      lease_id='lease-1' if action == 'RENEW' else None,
                      execution_generation=1 if action == 'RENEW' else None)
    assert ExecutionOperation.model_validate(body).operation == action
    with pytest.raises((ValidationError, ExecutionRuntimeError)):
        ExecutionOperation.model_validate(body | {'profile_version_id': 'extra'})


def test_signing_canonical_and_session_bound():
    claims = verify_token_claims(issue_token('user', 'synthetic-key'), 'synthetic-key')
    request = ExecutionOperation.model_validate(start_body())
    encoded = execution_signing_payload(tenant_id='tenant', claims=claims, operation=request)
    payload = json.loads(encoded)
    assert encoded == json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    assert payload == dict(protocol='yike-execution-operation-v1', tenant_id='tenant',
                           user_id='user', session_digest=claims.revocation_key,
                           operation=request.model_dump(mode='json'))


def test_missing_strategy_has_stable_capability_status():
    runtime = ExecutionRuntime(None)
    with pytest.raises(ExecutionRuntimeError) as error:
        runtime._strategy(None, None, None, 'profile', 'strategy', 'a'*64, ())
    assert error.value.code == 'capability_unavailable'
    assert error.value.status == 501
