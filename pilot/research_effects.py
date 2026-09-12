"""Host-controlled admission for bounded research side effects."""

from __future__ import annotations

import copy
import json
import math
import threading
import time
from typing import Any


_MAX_JSON_BYTES = 2 * 1024 * 1024
_KINDS = {"MODEL", "SEARCH", "READ"}


class EffectDispatchError(RuntimeError):
    """Fixed failure raised when a research effect cannot be admitted."""

    def __init__(self):
        super().__init__("effect_unavailable")


def _plain_json(value: Any) -> bool:
    value_type = type(value)
    if value is None or value_type in (str, bool, int):
        return True
    if value_type is float:
        return math.isfinite(value)
    if value_type is list:
        return all(_plain_json(item) for item in value)
    if value_type is dict:
        return all(type(key) is str and _plain_json(item) for key, item in value.items())
    return False


def _copy_bounded_json(value: Any) -> Any:
    try:
        if not _plain_json(value):
            raise ValueError
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")
        if len(encoded) > _MAX_JSON_BYTES:
            raise ValueError
        return copy.deepcopy(value)
    except (RecursionError, TypeError, UnicodeError, ValueError):
        raise EffectDispatchError() from None


def _valid_deadline(value: Any, *, original: float | None = None) -> bool:
    return (type(value) in (int, float) and math.isfinite(value)
            and value > time.monotonic()
            and (original is None or value <= original))


def dispatch_effect(dispatcher, *, kind, payload, deadline, perform):
    """Dispatch one bounded effect or accept a trusted persisted replay."""
    try:
        if kind not in _KINDS or not callable(perform) or not _valid_deadline(deadline):
            raise EffectDispatchError()
        clean_payload = _copy_bounded_json(payload)
        host_deadline = float(deadline)
        if dispatcher is None:
            result = perform(host_deadline)
        else:
            if not callable(dispatcher):
                raise EffectDispatchError()
            once_lock = threading.Lock()
            invoked = False

            def guarded_perform(effective_deadline: float) -> dict:
                nonlocal invoked
                with once_lock:
                    if invoked:
                        raise EffectDispatchError()
                    invoked = True
                if not _valid_deadline(effective_deadline, original=host_deadline):
                    raise EffectDispatchError()
                return perform(float(effective_deadline))

            result = dispatcher(kind, clean_payload, host_deadline, guarded_perform)
        if time.monotonic() >= host_deadline:
            raise EffectDispatchError()
        if type(result) is not dict:
            raise EffectDispatchError()
        return _copy_bounded_json(result)
    except EffectDispatchError:
        raise
    except BaseException:
        raise EffectDispatchError() from None
