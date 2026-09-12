"""Serial, fail-closed dispatcher backed by a durable research journal."""
from __future__ import annotations

import copy
import math
import threading
import time
from datetime import datetime, timezone
from typing import Any

from pilot.execution_contract import ExecutionRuntimeError, canonical_uuid
from pilot.research_effect_contract import (
    canonical_effect_sha256, effect_input, effect_result, known_read_failure,
    is_known_read_failure,
)
from pilot.research_effects import EffectDispatchError


class _AdmissionLimitReached(EffectDispatchError):
    """Trusted journal rejected before issuing a permit; no effect occurred."""


class DurableResearchDispatcher:
    def __init__(self, journal, claims, *, task_id, run_id, generation,
                 coordinator_owner, context_binding):
        try:
            if not callable(getattr(journal, "begin", None)) or not callable(getattr(journal, "finish", None)):
                raise ValueError
            self._task_id = canonical_uuid(task_id)
            self._run_id = canonical_uuid(run_id)
            self._owner = canonical_uuid(coordinator_owner)
            if type(generation) is not int or not 1 <= generation <= 2147483647:
                raise ValueError
            # Validate the exact binding without inventing a placeholder effect.
            effect_input("SEARCH", {"query": "binding-validation"}, context_binding)
            self._binding = context_binding.copy()
            self._generation = generation
            self._journal = journal
            self._claims = claims
            self._lock = threading.Lock()
            self._sequence = 0
            self._closed = False
        except BaseException:
            raise EffectDispatchError() from None

    def _fail(self):
        self._closed = True
        raise EffectDispatchError()

    def _entry(self, entry: Any, *, sequence: int, kind: str, payload: dict,
               digest: str, require_result: bool = False) -> dict:
        try:
            required = {"task_id", "run_id", "sequence", "generation", "coordinator_owner",
                        "kind", "payload", "input_sha256", "context_binding", "action_id",
                        "permit_id", "deadline_at", "status", "result", "output_sha256"}
            if type(entry) is not dict or not required <= set(entry):
                self._fail()
            if any((entry["task_id"] != self._task_id, entry["run_id"] != self._run_id,
                    entry["sequence"] != sequence, entry["generation"] != self._generation,
                    entry["coordinator_owner"] != self._owner, entry["kind"] != kind,
                    entry["payload"] != payload, entry["input_sha256"] != digest,
                    entry["context_binding"] != self._binding)):
                self._fail()
            canonical_uuid(entry["action_id"]); canonical_uuid(entry["permit_id"])
            parsed = datetime.fromisoformat(entry["deadline_at"].replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                self._fail()
            if require_result:
                if entry["status"] == "FAILED":
                    validated = known_read_failure(kind, payload, entry["result"])
                elif entry["status"] == "SUCCEEDED":
                    validated = effect_result(kind, payload, entry["result"])
                else:
                    self._fail()
                if entry["output_sha256"] != canonical_effect_sha256(validated):
                    self._fail()
            return entry
        except EffectDispatchError:
            raise
        except BaseException:
            self._fail()

    def __call__(self, kind, payload, deadline, perform) -> dict:
        with self._lock:
            began = None
            try:
                if self._closed or not callable(perform) or type(deadline) not in (int, float) \
                        or not math.isfinite(deadline) or deadline <= time.monotonic():
                    self._fail()
                clean, digest = effect_input(kind, payload, self._binding)
                self._sequence += 1
                sequence = self._sequence
                try:
                    began = self._journal.begin(
                        self._claims, task_id=self._task_id, run_id=self._run_id,
                        sequence=sequence, generation=self._generation,
                        coordinator_owner=self._owner, context_binding=self._binding,
                        kind=kind, payload=clean)
                except ExecutionRuntimeError as error:
                    if error.code != "resource_limit_exceeded":
                        raise
                    # ResourceStore raises this before inserting either record.
                    # Reuse the unissued sequence; other resources still require
                    # fresh authority/limit checks. Never recover I/O/ACK errors.
                    self._sequence -= 1
                    raise _AdmissionLimitReached() from None
                if type(began) is not dict or set(began) != {"created", "entry"} \
                        or type(began["created"]) is not bool:
                    self._fail()
                entry = self._entry(began["entry"], sequence=sequence, kind=kind,
                                    payload=clean, digest=digest)
                if not began["created"]:
                    if entry["status"] not in ("SUCCEEDED", "FAILED"):
                        self._fail()
                    return copy.deepcopy(self._entry(
                        entry, sequence=sequence, kind=kind, payload=clean,
                        digest=digest, require_result=True)["result"])
                if entry["status"] != "ISSUED" or entry["result"] is not None or entry["output_sha256"] is not None:
                    self._fail()
                wall_remaining = (datetime.fromisoformat(entry["deadline_at"].replace("Z", "+00:00"))
                                  .astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds()
                effective = min(float(deadline), time.monotonic() + wall_remaining)
                if wall_remaining <= 0 or effective <= time.monotonic():
                    self._fail()
                try:
                    raw = perform(effective)
                    negative = is_known_read_failure(kind, clean, raw)
                    result = known_read_failure(kind, clean, raw) if negative else effect_result(kind, clean, raw)
                    if time.monotonic() >= effective or time.monotonic() >= float(deadline):
                        raise EffectDispatchError()
                except BaseException:
                    try:
                        self._journal.finish(self._claims, task_id=self._task_id,
                            run_id=self._run_id, sequence=sequence, permit_id=entry["permit_id"],
                            status="UNKNOWN")
                    except BaseException:
                        pass
                    self._fail()
                expected_result = copy.deepcopy(result)
                result_digest = canonical_effect_sha256(expected_result)
                status = "FAILED" if negative else "SUCCEEDED"
                finished = self._journal.finish(self._claims, task_id=self._task_id,
                    run_id=self._run_id, sequence=sequence, permit_id=entry["permit_id"],
                    status=status, result=copy.deepcopy(expected_result))
                checked = self._entry(finished, sequence=sequence, kind=kind, payload=clean,
                                      digest=digest, require_result=True)
                if checked["status"] != status or checked["permit_id"] != entry["permit_id"] \
                        or checked["action_id"] != entry["action_id"] \
                        or checked["output_sha256"] != result_digest \
                        or checked["result"] != expected_result:
                    self._fail()
                return copy.deepcopy(checked["result"])
            except _AdmissionLimitReached:
                raise
            except EffectDispatchError:
                self._closed = True
                raise
            except BaseException:
                self._closed = True
                raise EffectDispatchError() from None
