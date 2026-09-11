"""Trusted internal action runner; no client-supplied consumption endpoint."""
from datetime import UTC, datetime
import hashlib
import json

from pilot.execution_contract import ExecutionRuntimeError, canonical_uuid


def run_resource(store, claims, *, task_id, run_id, action_id, resource, input_sha256, action):
    if not callable(action):
        raise ExecutionRuntimeError('invalid_request', 422)
    binding = dict(task_id=task_id, run_id=run_id, action_id=action_id)
    admitted = store.begin(claims, **binding, resource=resource, input_sha256=input_sha256)
    event = admitted['event']
    if (type(admitted['created']) is not bool
            or any(event.get(key) != value for key, value in binding.items())
            or event.get('resource') != resource or event.get('input_sha256') != input_sha256):
        raise ExecutionRuntimeError('resource_unavailable', 503)
    if not admitted['created']:
        # A digest is not recoverable source content. Never repeat the effect
        # just because the caller lost the original result.
        return dict(event=event, result=None, replayed=True)
    status, digest, result = 'UNKNOWN', None, None
    try:
        canonical_uuid(event['permit_id'])
        deadline = datetime.fromisoformat(event['deadline_at'])
        if event['status'] != 'ISSUED' or deadline.tzinfo is None or deadline <= datetime.now(UTC):
            raise ValueError
        value = action(deadline)
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), allow_nan=False).encode('utf-8')
        if len(encoded) > 1_048_576 or datetime.now(UTC) >= deadline:
            raise ValueError
        result = json.loads(encoded)
        status, digest = 'SUCCEEDED', hashlib.sha256(encoded).hexdigest()
    except Exception:
        # Transport errors cannot establish that no remote work occurred.
        # The issued unit stays occupied; nothing here refunds or retries it.
        status, digest, result = 'UNKNOWN', None, None
    try:
        finished = store.finish(claims, **binding, permit_id=event['permit_id'],
                                status=status, output_sha256=digest)
    except Exception:
        raise ExecutionRuntimeError('resource_unavailable', 503) from None
    return dict(event=finished, result=result, replayed=False)
