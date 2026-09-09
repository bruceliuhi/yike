import json
from uuid import uuid4

import pytest

from pilot.auth import TokenClaims
from pilot.execution_contract import ExecutionOperation, ExecutionRuntimeError
from pilot.execution_runtime import _hash, _operation, execution_signing_payload


def start_body(**changes):
    return dict(
        schema_version="execution-runtime-v1",
        request_id=str(uuid4()),
        operation="START",
        device_id=str(uuid4()),
        credential_version=1,
        profile_version_id="profile-1",
        strategy_version_id="strategy-1",
        configuration_sha256="a" * 64,
        targets=(
            dict(
                platform="PUBLIC_WEB",
                access_mode="PUBLIC_ANONYMOUS",
                connection_id=None,
                connection_version=None,
            ),
        ),
        task_id=None,
        platform_run_id=None,
        lease_id=None,
        execution_generation=None,
    ) | changes


def claims(*, session_digest="session-a"):
    return TokenClaims(user_id="用户-甲", expires_at=2_000_000_000, revocation_key=session_digest)


def test_signing_payload_is_utf8_canonical_and_preserves_operation_nulls():
    request = ExecutionOperation.model_validate(start_body())

    encoded = execution_signing_payload(tenant_id="租户-甲", claims=claims(), operation=request)
    decoded = json.loads(encoded)

    assert encoded == json.dumps(decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert "租户-甲" in encoded and "用户-甲" in encoded
    assert decoded["operation"] == request.model_dump(mode="json")
    assert decoded["operation"]["task_id"] is None
    assert decoded["operation"]["targets"][0]["connection_id"] is None


def test_input_key_order_does_not_change_payload_or_complete_request_digest():
    body = start_body()
    reordered = dict(reversed(tuple(body.items())))
    reordered["targets"] = (dict(reversed(tuple(body["targets"][0].items()))),)
    first = ExecutionOperation.model_validate(body)
    second = ExecutionOperation.model_validate(reordered)

    assert execution_signing_payload(tenant_id="tenant", claims=claims(), operation=first) == execution_signing_payload(
        tenant_id="tenant", claims=claims(), operation=second
    )
    assert _hash(first.model_dump(mode="json")) == _hash(second.model_dump(mode="json"))


def test_target_order_and_request_id_each_change_complete_request_digest():
    first_target = dict(
        platform="BILIBILI",
        access_mode="PLATFORM_ACCOUNT",
        connection_id=str(uuid4()),
        connection_version=1,
    )
    second_target = dict(
        platform="DOUYIN",
        access_mode="PLATFORM_ACCOUNT",
        connection_id=str(uuid4()),
        connection_version=1,
    )
    original = ExecutionOperation.model_validate(start_body(targets=(first_target, second_target)))
    reordered = ExecutionOperation.model_validate(start_body(
        request_id=original.request_id, targets=(second_target, first_target)
    ))
    new_request = ExecutionOperation.model_validate(start_body(
        request_id=str(uuid4()), targets=(first_target, second_target)
    ))

    digests = {
        _hash(operation.model_dump(mode="json"))
        for operation in (original, reordered, new_request)
    }
    assert len(digests) == 3


def test_changing_only_session_changes_only_session_bound_signing_bytes():
    request = ExecutionOperation.model_validate(start_body())
    first_encoded = execution_signing_payload(tenant_id="tenant", claims=claims(), operation=request)
    second_encoded = execution_signing_payload(
        tenant_id="tenant", claims=claims(session_digest="session-b"), operation=request
    )
    first, second = json.loads(first_encoded), json.loads(second_encoded)

    assert first_encoded != second_encoded
    assert first.pop("session_digest") == "session-a"
    assert second.pop("session_digest") == "session-b"
    assert first == second


@pytest.mark.parametrize(
    "forged",
    [
        lambda request: request.model_copy(update={"credential_version": True}),
        lambda request: request.model_copy(update={
            "targets": (request.targets[0].model_copy(update={"connection_version": True}),)
        }),
    ],
)
def test_forged_model_instances_cannot_replace_integer_credentials_with_booleans(forged):
    request = ExecutionOperation.model_validate(start_body())

    with pytest.raises(ExecutionRuntimeError) as caught:
        _operation(forged(request))

    assert caught.value.code == "invalid_request"
