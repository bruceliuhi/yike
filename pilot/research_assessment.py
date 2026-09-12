"""Trusted bridge from persisted research evidence to one bounded model effect."""
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import logging
import time
from uuid import NAMESPACE_URL, uuid5

from pilot.candidate_assessment_model import AssessmentModelError, validate_assessment
from pilot.execution_contract import ExecutionRuntimeError
from pilot.research_resource_runner import run_resource
from pilot.research_resources import _event

_LOGGER = logging.getLogger(__name__)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


class ResearchAssessmentRunner:
    def __init__(self, resources):
        self.resources = resources

    @staticmethod
    def _admission(snapshot):
        research = snapshot["research"]
        binding = snapshot["binding"]

        def admit(cursor, tenant, event):
            cursor.execute("""SELECT p.revision,p.version_id,p.current_observation_id,p.ambiguous,b.task_id,b.run_id,
                    b.request_id,b.execution_context,e.status,e.resource,e.permit_id,e.reservation_id,
                    e.input_sha256,e.output_sha256
                FROM pilot_candidate_projections p
                JOIN pilot_candidate_observations o ON o.tenant_id=p.tenant_id
                    AND o.owner_user_id=p.owner_user_id AND o.observation_id=p.current_observation_id
                JOIN pilot_candidate_batches b ON b.tenant_id=o.tenant_id
                    AND b.owner_user_id=o.owner_user_id AND b.platform_run_id=o.platform_run_id
                    AND b.request_id=o.request_id
                JOIN pilot_research_resource_events e ON e.tenant_id=b.tenant_id
                    AND e.owner_user_id=b.owner_user_id AND e.task_id=b.task_id
                    AND e.run_id=b.run_id AND e.action_id=b.request_id
                WHERE p.tenant_id=%s AND p.owner_user_id=%s AND p.candidate_id=%s
                FOR UPDATE OF p""", (tenant, research["ownerUserId"], binding["candidateId"]))
            row = cursor.fetchone()
            if row is None:
                return False
            (revision, version, observation, ambiguous, task, run, source_action, context,
             status, resource, permit, reservation, source_input, output) = row
            captured_context = research["context"]
            return (revision == binding["candidateRevision"]
                and str(version) == binding["sourceVersionId"]
                and str(observation) == research["observationId"]
                and ambiguous is False
                and str(task) == research["taskId"] and str(run) == research["runId"]
                and context == captured_context
                and type(context) is dict and context.get("kind") == "research-resource-v1"
                and context.get("action_id") == str(source_action)
                and context.get("permit_id") == str(permit)
                and context.get("reservation_id") == str(reservation)
                and context.get("input_sha256") == source_input
                and context.get("output_sha256") == output
                and resource == "SOURCE_READ" and status == "SUCCEEDED"
                and event["task_id"] == research["taskId"] and event["run_id"] == research["runId"])
        return admit

    def assess(self, claims, request, snapshot, model, *, review_deadline,
               before_dispatch, _admission=None, **kwargs):
        if (not callable(getattr(model, "assess_before", None))
                or not callable(before_dispatch)):
            raise AssessmentModelError("invalid_assessment_configuration", 500)
        research = snapshot["research"]
        action_id = str(uuid5(NAMESPACE_URL, "yike:research-assessment:" + ":".join((
            research["taskId"], research["runId"], request.requestId))))
        material = {key: snapshot[key] for key in (
            "research", "binding", "description", "content", "strategy", "model")}
        material["modelInput"] = kwargs
        digest = hashlib.sha256(_json(material).encode()).hexdigest()
        observed_error = None
        started = time.monotonic()

        def invoke(deadline):
            nonlocal observed_error
            effective_deadline = min(deadline, review_deadline)
            # The permit transaction is committed. Recheck disclosure
            # qualification immediately before the external effect without
            # keeping any database transaction open across the model call.
            before_dispatch()
            if _admission is not None:
                with self.resources.runtime.database.connect() as connection, \
                        connection.cursor() as cursor:
                    tenant = self.resources.runtime._active(cursor, claims)
                    row = self.resources._select(
                        cursor, tenant, claims.user_id, research["taskId"],
                        research["runId"], action_id
                    )
                    current = _event(row) if row is not None else None
                    if (current is None or current["status"] != "ISSUED"
                            or _admission(cursor, tenant, current) is not True):
                        raise ExecutionRuntimeError("request_conflict", 409)
                    # Host admission may lock coordinator and all durable
                    # effects. Lock and re-read this permit afterwards to keep
                    # that global order and close the unlocked-read race.
                    row = self.resources._select(
                        cursor, tenant, claims.user_id, research["taskId"],
                        research["runId"], action_id, lock=True
                    )
                    if row is None or _event(row)["status"] != "ISSUED":
                        raise ExecutionRuntimeError("request_conflict", 409)
                    self.resources.runtime._active(cursor, claims)
            try:
                usage = None
                value, usage = model.assess_before(effective_deadline, **kwargs)
                value = value.model_dump() if hasattr(value, "model_dump") else value
                grounded = validate_assessment(value, description=snapshot["description"],
                                               content=snapshot["content"]).model_dump()
            except AssessmentModelError as error:
                # Revalidate even typed adapter errors; never log exception text.
                observed_error = AssessmentModelError(error.code, error.status,
                    usage=error.usage, diagnostic=getattr(error, 'diagnostic', None))
                if observed_error.usage is None and usage is not None:
                    observed_error = AssessmentModelError(error.code, error.status,
                        usage=usage, diagnostic=observed_error.diagnostic)
                raise
            return {"assessment": grounded, "usage": usage}

        snapshot_admission = self._admission(snapshot)
        def admission(cursor, tenant, event):
            return snapshot_admission(cursor, tenant, event) and (
                _admission is None or _admission(cursor, tenant, event))

        result = run_resource(self.resources, claims, task_id=research["taskId"],
            run_id=research["runId"], action_id=action_id, resource="MODEL_CALL",
            input_sha256=digest, action=invoke, _admission=admission)
        if result["event"]["status"] != "SUCCEEDED" or result["result"] is None:
            if observed_error is not None:
                _LOGGER.warning(_json({
                    'event': 'research_assessment_failure',
                    'task_id': research['taskId'], 'run_id': research['runId'],
                    'request_id': request.requestId, 'action_id': action_id,
                    'model_error': observed_error.code,
                    'diagnostic': observed_error.diagnostic,
                    'elapsed_ms': max(0, int((time.monotonic()-started)*1000)),
                    'usage_reported': observed_error.usage is not None,
                }))
            # The resource remains UNKNOWN and occupied. Measured usage is not
            # a success receipt, and is not permission to retry or refund.
            raise AssessmentModelError("assessment_result_unknown", 504,
                usage=observed_error.usage if observed_error is not None else None,
                diagnostic=observed_error.diagnostic if observed_error is not None else None)
        return result["result"]["assessment"], result["result"]["usage"]
