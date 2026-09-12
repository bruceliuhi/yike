"""Restricted-PG research candidates require a trusted MODEL_CALL permit."""
import copy
import time
from uuid import uuid4
from types import SimpleNamespace

import pytest

from pilot.candidate_ingestion import CandidateIngestionStore
from pilot.candidate_review import CandidateReviewStore
from pilot.candidate_review_contract import CandidateReviewError
from pilot.execution_contract import ExecutionRuntimeError
from pilot.research_assessment import ResearchAssessmentRunner
from pilot.research_candidates import ResearchCandidateStore
from tests.test_candidate_assessment_model import CONTENT, assessment
from tests.test_candidate_review_postgres import (review_payload, material_reference_env,
    _attach_material_reference, _revoke_attached)
from tests.test_candidate_review_postgres import (databases, env, execution_databases,
    execution_env, raw_databases, raw_env)
from tests.test_confirmed_strategy_review_postgres import real_strategy_env
from tests.test_research_candidates_postgres import topic
from tests.test_research_resources_postgres import started, store as resource_store
from tests.test_execution_runtime_postgres import apply, operation


def test_revoke_during_permit_admission_never_discloses_to_model(real_strategy_env, material_reference_env):
    from pilot.auth import issue_token, verify_token_claims
    from tests.test_execution_runtime_postgres import SECRET
    from tests.test_research_strategies_postgres import prepare_body, confirm_body
    env = real_strategy_env
    material, source, ready = _attach_material_reference(env)
    pending = env.strategies.prepare(env.claims, prepare_body(env))
    env.confirmed = env.strategies.confirm(env.claims, confirm_body(pending))
    env.snapshot = env.confirmed['snapshot']
    resources, execution, binding, origin = _source(env)
    # A second authenticated session can revoke material while the first holds
    # task/profile locks. Only the network boundary is synthetic.
    other = SimpleNamespace(**(vars(env) | {'claims': verify_token_claims(
        issue_token(env.claims.user_id, SECRET), SECRET)}))
    model = BoundedModel()
    class RevokeAtAdmission(ResearchAssessmentRunner):
        def _admission(self, snapshot):
            original = super()._admission(snapshot)
            def admit(cursor, tenant, event):
                assert _revoke_attached(other, material, source, ready)['status'] == 'SUCCEEDED'
                return original(cursor, tenant, event)
            return admit
    service = _review(env, model, RevokeAtAdmission(resources))
    payload = review_payload(binding)
    with pytest.raises(CandidateReviewError):
        service.assess_research(env.claims, payload, **origin)
    assert model.calls == 0
    recovered = service.assess_research(env.claims, payload, **origin)
    assert recovered['kind'] != 'assessment' and model.calls == 0
    with env.admin.connect() as conn:
        events = conn.execute("SELECT status FROM pilot_research_resource_events WHERE tenant_id=%s "
            "AND task_id=%s AND resource='MODEL_CALL'", (env.tenant,execution['task_id'])).fetchall()
    assert events == [('UNKNOWN',)]


class BoundedModel:
    provider, model = "synthetic", "bounded-only"
    rule_version, rule_sha256 = "test-v1", "a" * 64
    industry_strategy_version = "industry-task-strategy-v1"

    def __init__(self):
        self.calls = 0

    def assess_before(self, deadline, **kwargs):
        assert deadline.tzinfo is not None
        self.calls += 1
        self.last_input = copy.deepcopy(kwargs)
        return assessment(), {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}


def _source(env, *, identity=17):
    execution, _ = started(env)
    resources = resource_store(env)
    receipt = ResearchCandidateStore(resources).read_public(
        env.claims, task_id=execution["task_id"], run_id=execution["run_id"],
        action_id=str(uuid4()), fetcher=lambda _deadline: [topic(identity=identity,
            title=CONTENT["title"], content=CONTENT["body"], created=1_700_000_000)]
    )["receipt"]
    item = receipt["items"][0]
    detail = CandidateIngestionStore(env.db).get_candidate(env.claims, item["candidate_id"])["candidate"]
    binding = dict(candidateId=item["candidate_id"], candidateRevision=detail["revision"],
        sourceVersionId=item["version_id"], profileId=env.profile,
        profileVersion=env.profile_number)
    origin = dict(task_id=execution["task_id"], run_id=execution["run_id"],
                  observation_id=item["observation_id"])
    return resources, execution, binding, origin


def _review(env, model, research_assessment=None):
    return CandidateReviewStore(env.db, model=model, strategy_resolver=env.strategies.resolve,
        strategy_snapshot_reader=env.strategies.read_snapshot,
        research_assessment=research_assessment)


def test_research_assessment_denies_before_candidate_quota_without_adapter(real_strategy_env):
    env = real_strategy_env
    _, _, binding, origin = _source(env)
    with env.admin.connect() as connection:
        before = connection.execute("SELECT count(*) FROM pilot_candidate_call_quota").fetchone()[0]
    with pytest.raises(CandidateReviewError, match="capability_unavailable"):
        _review(env, BoundedModel()).assess_research(
            env.claims, review_payload(binding), **origin)
    with env.admin.connect() as connection:
        after = connection.execute("SELECT count(*) FROM pilot_candidate_call_quota").fetchone()[0]
    assert after == before


def test_confirmed_research_assessment_spends_one_model_permit_and_replays(real_strategy_env):
    env = real_strategy_env
    resources, _, binding, origin = _source(env)
    model = BoundedModel()
    service = _review(env, model, ResearchAssessmentRunner(resources))
    request = review_payload(binding)
    first = service.assess_research(env.claims, request, **origin)
    assert first["kind"] == "assessment" and first["assessment"]["effectiveDecision"] == "REVIEW"
    assert model.calls == 1
    assert service.assess_research(env.claims, request, **origin) == first
    assert model.calls == 1
    with env.admin.connect() as connection:
        events = connection.execute("SELECT resource,status,count(*) FROM pilot_research_resource_events "
            "WHERE tenant_id=%s GROUP BY resource,status", (env.tenant,)).fetchall()
    assert ("MODEL_CALL", "SUCCEEDED", 1) in events


def test_replay_rejects_different_internal_origin(real_strategy_env):
    env = real_strategy_env
    resources, _, binding, origin = _source(env)
    service = _review(env, BoundedModel(), ResearchAssessmentRunner(resources))
    request = review_payload(binding)
    service.assess_research(env.claims, request, **origin)
    with pytest.raises(CandidateReviewError, match="candidate_conflict"):
        service.assess_research(env.claims, request, **(origin | {"observation_id": str(uuid4())}))


def test_unsupported_bounded_model_denies_before_candidate_quota(real_strategy_env):
    env = real_strategy_env
    resources, _, binding, origin = _source(env)
    with env.admin.connect() as connection:
        before = connection.execute("SELECT count(*) FROM pilot_candidate_call_quota").fetchone()[0]
    model = BoundedModel()
    model.assess_before = None
    with pytest.raises(CandidateReviewError, match="assessment_unavailable"):
        _review(env, model, ResearchAssessmentRunner(resources)).assess_research(
            env.claims, review_payload(binding), **origin)
    with env.admin.connect() as connection:
        assert connection.execute("SELECT count(*) FROM pilot_candidate_call_quota").fetchone()[0] == before


def test_same_content_new_observation_uses_review_cache_without_model_permit(real_strategy_env):
    env = real_strategy_env
    resources, execution, binding, first_origin = _source(env)
    model = BoundedModel()
    service = _review(env, model, ResearchAssessmentRunner(resources))
    first = service.assess_research(env.claims, review_payload(binding), **first_origin)
    # The public reader records whole seconds; cross one tick so this identical
    # content becomes the authoritative current observation.
    time.sleep(1.05)
    second_receipt = ResearchCandidateStore(resources).read_public(
        env.claims, task_id=execution["task_id"], run_id=execution["run_id"],
        action_id=str(uuid4()), fetcher=lambda _deadline: [topic(
            title=CONTENT["title"], content=CONTENT["body"], created=1_700_000_000)]
    )["receipt"]
    second_origin = first_origin | {"observation_id": second_receipt["items"][0]["observation_id"]}
    second = service.assess_research(env.claims, review_payload(binding), **second_origin)
    assert second["assessment"]["id"] == first["assessment"]["id"]
    assert model.calls == 1
    with env.admin.connect() as connection:
        assert connection.execute("SELECT count(*) FROM pilot_research_resource_events WHERE tenant_id=%s "
            "AND resource='MODEL_CALL'", (env.tenant,)).fetchone()[0] == 1


def test_current_source_race_fails_admission_without_calling_model(real_strategy_env):
    env = real_strategy_env
    resources, _, binding, origin = _source(env)
    model = BoundedModel()

    class RacingRunner(ResearchAssessmentRunner):
        def assess(self, claims, request, snapshot, bounded_model, **kwargs):
            with env.admin.connect() as connection:
                connection.execute("UPDATE pilot_candidate_projections SET ambiguous=true "
                    "WHERE tenant_id=%s AND owner_user_id=%s AND candidate_id=%s",
                    (env.tenant, env.claims.user_id, binding["candidateId"]))
            return super().assess(claims, request, snapshot, bounded_model, **kwargs)

    with pytest.raises(CandidateReviewError, match="candidate_conflict"):
        _review(env, model, RacingRunner(resources)).assess_research(
            env.claims, review_payload(binding), **origin)
    assert model.calls == 0
    with env.admin.connect() as connection:
        assert connection.execute("SELECT count(*) FROM pilot_research_resource_events WHERE tenant_id=%s "
            "AND resource='MODEL_CALL'", (env.tenant,)).fetchone()[0] == 0


@pytest.mark.parametrize("blocked", ["cancelled", "model_limit"])
def test_resource_block_never_invokes_model(real_strategy_env, blocked):
    env = real_strategy_env
    resources, execution, binding, origin = _source(env)
    if blocked == "cancelled":
        apply(env, operation(env, "CANCEL", execution))
    else:
        for _ in range(10):
            resources.begin(env.claims, task_id=execution["task_id"], run_id=execution["run_id"],
                action_id=str(uuid4()), resource="MODEL_CALL", input_sha256="b" * 64)
    model = BoundedModel()
    result = _review(env, model, ResearchAssessmentRunner(resources)).assess_research(
        env.claims, review_payload(binding), **origin)
    assert result["status"] == "UNKNOWN" and model.calls == 0


def test_host_admission_is_rechecked_after_permit_before_model_dispatch(real_strategy_env):
    env = real_strategy_env
    resources, execution, binding, origin = _source(env, identity=uuid4().int % 1_000_000_000)
    model = BoundedModel()
    model.model = "bounded-predispatch-" + str(uuid4())
    admissions = []

    def admission(_cursor, _tenant, event):
        admissions.append(event.get("status", "PRE_ISSUE"))
        if len(admissions) == 2:
            raise ExecutionRuntimeError("runtime_shutdown", 503)
        return True

    result = _review(env, model, ResearchAssessmentRunner(resources)).assess_research(
        env.claims, review_payload(binding), **origin, _admission=admission
    )
    assert result["status"] == "UNKNOWN"
    assert admissions == ["PRE_ISSUE", "ISSUED"]
    assert model.calls == 0
    with env.admin.connect() as connection:
        assert connection.execute(
            "SELECT status FROM pilot_research_resource_events WHERE tenant_id=%s "
            "AND task_id=%s AND resource='MODEL_CALL'",
            (env.tenant, execution["task_id"]),
        ).fetchall() == [("UNKNOWN",)]
