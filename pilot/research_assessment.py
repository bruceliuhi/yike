"""Trusted bridge from persisted research evidence to one bounded model effect."""
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from uuid import NAMESPACE_URL, uuid5

from pilot.candidate_assessment_model import AssessmentModelError, validate_assessment
from pilot.execution_contract import ExecutionRuntimeError
from pilot.research_resource_runner import run_resource


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

        def invoke(deadline):
            effective_deadline = min(deadline, review_deadline)
            # The permit transaction is committed. Recheck disclosure
            # qualification immediately before the external effect without
            # keeping any database transaction open across the model call.
            before_dispatch()
            value, usage = model.assess_before(effective_deadline, **kwargs)
            value = value.model_dump() if hasattr(value, "model_dump") else value
            grounded = validate_assessment(value, description=snapshot["description"],
                                           content=snapshot["content"]).model_dump()
            return {"assessment": grounded, "usage": usage}

        snapshot_admission = self._admission(snapshot)
        def admission(cursor, tenant, event):
            return snapshot_admission(cursor, tenant, event) and (
                _admission is None or _admission(cursor, tenant, event))

        result = run_resource(self.resources, claims, task_id=research["taskId"],
            run_id=research["runId"], action_id=action_id, resource="MODEL_CALL",
            input_sha256=digest, action=invoke, _admission=admission)
        if result["event"]["status"] != "SUCCEEDED" or result["result"] is None:
            raise AssessmentModelError("assessment_result_unknown", 504)
        return result["result"]["assessment"], result["result"]["usage"]
