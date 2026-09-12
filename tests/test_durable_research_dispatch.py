from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from pilot.durable_research_dispatch import DurableResearchDispatcher
from pilot.research_effects import EffectDispatchError
from pilot.research_effect_contract import effect_input
from tests.test_research_effect_contract import binding


class Journal:
    def __init__(self):
        self.events = []
        self.entries = []
        self.last_entry = None

    def begin(self, claims, **kwargs):
        self.events.append(("begin", kwargs.copy()))
        if self.entries:
            return self.entries.pop(0)
        payload, digest = effect_input(kwargs["kind"], kwargs["payload"], kwargs["context_binding"])
        entry = kwargs | {"payload": payload, "input_sha256": digest,
                          "action_id": str(uuid4()), "permit_id": str(uuid4()),
                          "deadline_at": (datetime.now(timezone.utc) + timedelta(seconds=20)).isoformat(),
                          "status": "ISSUED", "result": None, "output_sha256": None}
        self.last_entry = entry
        return {"created": True, "entry": entry}

    def finish(self, claims, **kwargs):
        self.events.append(("finish", kwargs.copy()))
        return kwargs | {"task_id": TASK, "run_id": RUN, "sequence": kwargs["sequence"],
                         "generation": 3, "coordinator_owner": OWNER,
                         "kind": self.events[-2][1]["kind"], "payload": self.events[-2][1]["payload"],
                         "context_binding": BINDING,
                         "input_sha256": effect_input(self.events[-2][1]["kind"], self.events[-2][1]["payload"], BINDING)[1],
                         "action_id": self.last_entry["action_id"], "deadline_at": self.last_entry["deadline_at"],
                         "output_sha256": hashlib.sha256(__import__('json').dumps(kwargs.get("result"), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest() if kwargs.get("result") is not None else None}


TASK, RUN, OWNER = str(uuid4()), str(uuid4()), str(uuid4())
BINDING = binding()


def dispatcher(journal):
    return DurableResearchDispatcher(journal, object(), task_id=TASK, run_id=RUN,
        generation=3, coordinator_owner=OWNER, context_binding=BINDING)


def search_result(query="buyer"):
    return {"status": "SEARCHED", "query": query, "observed_at": datetime.now(timezone.utc).isoformat(),
            "read_scope": "SEARCH_RESULTS", "results": [], "omitted_count": 0, "replayed": False}


def test_created_effect_performs_then_finishes_before_returning():
    journal = Journal(); calls = []
    expected = search_result()
    result = dispatcher(journal)("SEARCH", {"query": "buyer"}, time.monotonic()+10,
                                 lambda deadline: calls.append(deadline) or expected)
    assert result == expected
    assert [event[0] for event in journal.events] == ["begin", "finish"]
    assert calls and journal.events[1][1]["status"] == "SUCCEEDED"
    assert journal.events[0][1]["sequence"] == 1


def test_known_failure_finishes_failed_then_allows_different_effect():
    journal = Journal(); use = dispatcher(journal)
    result = {"status": "FAILED", "code": "not_found", "replayed": False}
    assert use("READ", {"url": "https://example.com/"}, time.monotonic()+10, lambda _: result) == result
    assert journal.events[-1][1]["status"] == "FAILED"
    assert use("SEARCH", {"query": "buyer"}, time.monotonic()+10, lambda _: search_result())["status"] == "SEARCHED"


@pytest.mark.parametrize("mode", ["lost", "substituted", "status"])
def test_known_failure_ack_uncertainty_closes_without_second_finish(mode):
    journal = Journal(); original = journal.finish; use = dispatcher(journal)
    def finish(*args, **kwargs):
        acknowledged = original(*args, **kwargs)
        if mode == "lost":
            raise RuntimeError("lost ack")
        if mode == "status":
            acknowledged["status"] = "SUCCEEDED"
        else:
            from pilot.research_effect_contract import canonical_effect_sha256
            acknowledged["result"] = acknowledged["result"] | {"code": "too_large"}
            acknowledged["output_sha256"] = canonical_effect_sha256(acknowledged["result"])
        return acknowledged
    journal.finish = finish
    with pytest.raises(EffectDispatchError):
        use("READ", {"url": "https://example.com/"}, time.monotonic()+10,
            lambda _: {"status": "FAILED", "code": "not_found", "replayed": False})
    assert len([e for e in journal.events if e[0] == "finish"]) == 1
    with pytest.raises(EffectDispatchError):
        use("SEARCH", {"query": "buyer"}, time.monotonic()+10, lambda _: pytest.fail("no subsequent I/O"))


def test_dispatch_is_serial_and_sequence_increases():
    journal = Journal(); gate = threading.Event(); entered = threading.Event(); order = []
    use = dispatcher(journal)
    def first(_): entered.set(); gate.wait(1); order.append(1); return search_result("one")
    threads = [threading.Thread(target=lambda: use("SEARCH", {"query": "one"}, time.monotonic()+10, first)),
               threading.Thread(target=lambda: use("SEARCH", {"query": "two"}, time.monotonic()+10, lambda _: order.append(2) or search_result("two")))]
    threads[0].start(); assert entered.wait(1); threads[1].start(); time.sleep(.02); assert order == []
    gate.set(); [thread.join(1) for thread in threads]
    assert order == [1, 2]
    assert [event[1]["sequence"] for event in journal.events if event[0] == "begin"] == [1, 2]


def test_begin_denial_and_nonreplayable_status_never_perform_and_close_dispatcher():
    for response in [None, {"created": False, "entry": {"status": "ISSUED"}}]:
        journal = Journal()
        if response is None:
            journal.begin = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("secret"))
        else:
            journal.entries.append(response)
        use = dispatcher(journal)
        with pytest.raises(EffectDispatchError, match="^effect_unavailable$"):
            use("SEARCH", {"query": "buyer"}, time.monotonic()+10, lambda _: pytest.fail())
        with pytest.raises(EffectDispatchError, match="^effect_unavailable$"):
            use("SEARCH", {"query": "next"}, time.monotonic()+10, lambda _: pytest.fail())


def test_transport_or_validation_failure_finishes_unknown_once_and_closes():
    for perform in [lambda _: (_ for _ in ()).throw(RuntimeError("secret")), lambda _: {"bad": True}]:
        journal = Journal(); use = dispatcher(journal)
        with pytest.raises(EffectDispatchError, match="^effect_unavailable$"):
            use("SEARCH", {"query": "buyer"}, time.monotonic()+10, perform)
        finishes = [event for event in journal.events if event[0] == "finish"]
        assert len(finishes) == 1 and finishes[0][1]["status"] == "UNKNOWN" and "result" not in finishes[0][1]


def test_result_after_effective_deadline_is_unknown():
    journal = Journal(); use = dispatcher(journal)
    with pytest.raises(EffectDispatchError, match="^effect_unavailable$"):
        use("SEARCH", {"query": "buyer"}, time.monotonic()+.01,
            lambda _deadline: time.sleep(.02) or search_result())
    assert journal.events[-1][0] == "finish"
    assert journal.events[-1][1]["status"] == "UNKNOWN"


def test_finish_failure_has_no_fallback_finish():
    journal = Journal()
    def finish(*_args, **kwargs): journal.events.append(("finish", kwargs)); raise RuntimeError("lost ack")
    journal.finish = finish
    with pytest.raises(EffectDispatchError, match="^effect_unavailable$"):
        dispatcher(journal)("SEARCH", {"query": "buyer"}, time.monotonic()+10, lambda _: search_result())
    assert len([x for x in journal.events if x[0] == "finish"]) == 1


def test_success_finish_rejects_valid_acknowledgement_for_a_different_result():
    journal = Journal()
    actual = search_result()
    substituted = actual | {"omitted_count": 2}
    original_finish = journal.finish

    def finish(*args, **kwargs):
        acknowledged = original_finish(*args, **kwargs)
        acknowledged["result"] = substituted
        acknowledged["output_sha256"] = hashlib.sha256(__import__('json').dumps(
            substituted, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False).encode()).hexdigest()
        return acknowledged

    journal.finish = finish
    with pytest.raises(EffectDispatchError, match="^effect_unavailable$"):
        dispatcher(journal)("SEARCH", {"query": "buyer"}, time.monotonic()+10,
                            lambda _: actual)
    assert len([x for x in journal.events if x[0] == "finish"]) == 1


def test_success_finish_cannot_mutate_submitted_result_into_a_different_acknowledgement():
    journal = Journal()
    actual = search_result()
    original_finish = journal.finish

    def finish(*args, **kwargs):
        kwargs["result"]["omitted_count"] = 2
        return original_finish(*args, **kwargs)

    journal.finish = finish
    with pytest.raises(EffectDispatchError, match="^effect_unavailable$"):
        dispatcher(journal)("SEARCH", {"query": "buyer"}, time.monotonic()+10,
                            lambda _: actual)
    assert len([x for x in journal.events if x[0] == "finish"]) == 1


def test_success_replay_is_validated_without_perform_or_finish():
    journal = Journal(); result = search_result()
    payload = {"query": "buyer"}; _, digest = effect_input("SEARCH", payload, BINDING)
    entry = {"task_id": TASK, "run_id": RUN, "sequence": 1, "generation": 3,
             "coordinator_owner": OWNER, "kind": "SEARCH", "payload": payload,
             "input_sha256": digest, "context_binding": BINDING, "action_id": str(uuid4()),
             "permit_id": str(uuid4()), "deadline_at": (datetime.now(timezone.utc)+timedelta(seconds=10)).isoformat(),
             "status": "SUCCEEDED", "result": result,
             "output_sha256": hashlib.sha256(__import__('json').dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()}
    journal.entries.append({"created": False, "entry": entry})
    assert dispatcher(journal)("SEARCH", payload, time.monotonic()+10, lambda _: pytest.fail()) == result
    assert [x[0] for x in journal.events] == ["begin"]


@pytest.mark.parametrize("deadline", [True, float("nan"), -1.0])
def test_invalid_or_expired_deadline_fails_before_begin(deadline):
    journal = Journal()
    with pytest.raises(EffectDispatchError, match="^effect_unavailable$"):
        dispatcher(journal)("SEARCH", {"query": "buyer"}, deadline, lambda _: pytest.fail())
    assert journal.events == []
