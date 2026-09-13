"""Unprivileged identity contract shared by the service and broker client."""
import hashlib
import json
from uuid import UUID

# Includes the broker's 2s CLI wait + three 2s Docker checks + thread cleanup.
STREAM_READ_TIMEOUT = 12
STREAM_JOIN_TIMEOUT = STREAM_READ_TIMEOUT + 1


def task_key(identity):
    try:
        if type(identity) is not dict or set(identity) != {'tenant_id', 'task_id', 'run_id', 'generation'}:
            raise ValueError()
        for field in ('tenant_id', 'task_id', 'run_id'):
            if type(identity[field]) is not str or str(UUID(identity[field])) != identity[field]:
                raise ValueError()
        if type(identity['generation']) is not int or not 1 <= identity['generation'] <= 2**31-1:
            raise ValueError()
        return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    except (ValueError, TypeError, AttributeError):
        raise ValueError('invalid_task_identity') from None
