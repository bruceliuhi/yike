from __future__ import annotations

import math
import threading
import time

import pytest

from pilot.research_effects import EffectDispatchError, dispatch_effect


def test_legacy_dispatch_calls_perform_with_original_deadline_and_copies_result():
    deadline = time.monotonic() + 10
    source = {"nested": [1]}
    returned = {"value": source}
    result = dispatch_effect(None, kind="MODEL", payload={"input": []}, deadline=deadline,
                             perform=lambda effective: returned if effective == deadline else pytest.fail())
    result["value"]["nested"].append(2)
    assert source == {"nested": [1]}


def test_dispatcher_gets_copied_payload_and_can_shorten_deadline():
    original = {"query": "hello", "nested": [1]}
    host_deadline = time.monotonic() + 10
    seen = {}

    def dispatcher(kind, payload, deadline, perform):
        seen.update(kind=kind, payload=payload, deadline=deadline)
        payload["nested"].append(2)
        return perform(deadline - 1)

    result = dispatch_effect(dispatcher, kind="SEARCH", payload=original, deadline=host_deadline,
                             perform=lambda deadline: {"effective": deadline})
    assert original == {"query": "hello", "nested": [1]}
    assert seen["kind"] == "SEARCH" and seen["deadline"] == host_deadline
    assert result["effective"] == host_deadline - 1


@pytest.mark.parametrize("value", [None, [], "bad", 1, True])
def test_dispatcher_invalid_result_never_becomes_effect_result(value):
    with pytest.raises(EffectDispatchError, match="^effect_unavailable$"):
        dispatch_effect(lambda *_: value, kind="READ", payload={"url": "https://example.com/"},
                        deadline=time.monotonic() + 10, perform=lambda _: pytest.fail("must not run"))


@pytest.mark.parametrize("dispatcher", [False, 1, "callable"])
def test_non_callable_dispatcher_is_rejected_without_perform(dispatcher):
    with pytest.raises(EffectDispatchError, match="^effect_unavailable$"):
        dispatch_effect(dispatcher, kind="MODEL", payload={}, deadline=time.monotonic() + 10,
                        perform=lambda _: pytest.fail("must not run"))


@pytest.mark.parametrize("kind", ["", "model", "OTHER", None])
def test_invalid_kind_is_rejected_without_perform(kind):
    with pytest.raises(EffectDispatchError, match="^effect_unavailable$"):
        dispatch_effect(lambda *_: {}, kind=kind, payload={}, deadline=time.monotonic() + 10,
                        perform=lambda _: pytest.fail("must not run"))


@pytest.mark.parametrize("deadline", [True, math.nan, math.inf, -math.inf])
def test_invalid_host_deadline_is_rejected_without_dispatch_or_perform(deadline):
    with pytest.raises(EffectDispatchError, match="^effect_unavailable$"):
        dispatch_effect(lambda *_: pytest.fail("must not dispatch"), kind="MODEL", payload={},
                        deadline=deadline, perform=lambda _: pytest.fail("must not run"))


@pytest.mark.parametrize("effective", [True, math.nan, math.inf, -math.inf])
def test_invalid_effective_deadline_is_rejected_before_perform(effective):
    with pytest.raises(EffectDispatchError, match="^effect_unavailable$"):
        dispatch_effect(lambda _k, _p, _d, perform: perform(effective), kind="MODEL", payload={},
                        deadline=time.monotonic() + 10, perform=lambda _: pytest.fail("must not run"))


def test_past_or_extended_deadline_is_rejected_before_perform():
    for select in (lambda original: time.monotonic() - 1, lambda original: original + 0.001):
        calls = []
        host = time.monotonic() + 10
        with pytest.raises(EffectDispatchError, match="^effect_unavailable$"):
            dispatch_effect(lambda _k, _p, _d, perform: perform(select(host)), kind="MODEL", payload={},
                            deadline=host, perform=lambda value: calls.append(value) or {})
        assert calls == []


def test_duplicate_perform_is_refused_even_after_first_failure():
    calls = []

    def dispatcher(_kind, _payload, deadline, perform):
        with pytest.raises(EffectDispatchError, match="^effect_unavailable$"):
            perform(deadline - 1)
        return perform(deadline - 1)

    with pytest.raises(EffectDispatchError, match="^effect_unavailable$"):
        dispatch_effect(dispatcher, kind="MODEL", payload={}, deadline=time.monotonic() + 10,
                        perform=lambda deadline: calls.append(deadline) or (_ for _ in ()).throw(RuntimeError("secret")))
    assert len(calls) == 1


def test_dispatcher_denial_or_exception_does_not_run_perform_or_echo_secret():
    for dispatcher in (lambda *_: (_ for _ in ()).throw(RuntimeError("private-secret")), lambda *_: None):
        with pytest.raises(EffectDispatchError) as error:
            dispatch_effect(dispatcher, kind="SEARCH", payload={}, deadline=time.monotonic() + 10,
                            perform=lambda _: pytest.fail("must not run"))
        assert str(error.value) == "effect_unavailable" and "private" not in repr(error.value)


def test_deadline_elapsed_while_dispatcher_queues_prevents_io():
    entered = threading.Event()
    release = threading.Event()
    performed = []

    def dispatcher(_kind, _payload, deadline, perform):
        entered.set()
        release.wait(1)
        return perform(deadline)

    failure = []
    thread = threading.Thread(target=lambda: _capture(
        failure, lambda: dispatch_effect(dispatcher, kind="READ", payload={},
                                         deadline=time.monotonic() + .03,
                                         perform=lambda _: performed.append(True) or {})))
    thread.start()
    assert entered.wait(1)
    time.sleep(.04)
    release.set()
    thread.join(1)
    assert performed == [] and len(failure) == 1 and str(failure[0]) == "effect_unavailable"


def test_saved_perform_is_invalid_after_dispatcher_returns():
    saved = []
    performed = []

    def dispatcher(_kind, _payload, _deadline, perform):
        saved.append(perform)
        return {"replayed": True}

    assert dispatch_effect(dispatcher, kind="READ", payload={}, deadline=time.monotonic() + 10,
                           perform=lambda _: performed.append(True) or {}) == {"replayed": True}
    with pytest.raises(EffectDispatchError, match="^effect_unavailable$"):
        saved[0](time.monotonic() + 1)
    assert performed == []


def test_effective_deadline_elapsed_during_action_rejects_result():
    with pytest.raises(EffectDispatchError, match="^effect_unavailable$"):
        dispatch_effect(lambda _k, _p, _deadline, perform: perform(time.monotonic() + .02),
                        kind="MODEL", payload={}, deadline=time.monotonic() + 1,
                        perform=lambda _: time.sleep(.03) or {"late": True})


def _capture(target, action):
    try:
        action()
    except Exception as error:
        target.append(error)


@pytest.mark.parametrize("payload", [
    [],
    {"bad": float("nan")},
    {"bad": {1: "non-string key"}},
    {"too_large": "x" * (2 * 1024 * 1024)},
])
def test_payload_must_be_bounded_plain_finite_json(payload):
    with pytest.raises(EffectDispatchError, match="^effect_unavailable$"):
        dispatch_effect(lambda *_: pytest.fail("must not dispatch"), kind="MODEL", payload=payload,
                        deadline=time.monotonic() + 10, perform=lambda _: pytest.fail("must not run"))


@pytest.mark.parametrize("result", [
    {"bad": float("nan")},
    {"bad": {1: "non-string key"}},
    {"too_large": "x" * (2 * 1024 * 1024)},
])
def test_result_must_be_bounded_plain_finite_json(result):
    with pytest.raises(EffectDispatchError, match="^effect_unavailable$"):
        dispatch_effect(lambda *_: result, kind="MODEL", payload={}, deadline=time.monotonic() + 10,
                        perform=lambda _: pytest.fail("trusted replay does not perform"))
