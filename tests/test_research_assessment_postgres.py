"""Restricted-PG research candidates require a trusted MODEL_CALL permit."""
import copy
import time
from uuid import uuid4

import pytest

from pilot.candidate_ingestion import CandidateIngestionStore
from pilot.candidate_review import CandidateReviewStore
from pilot.candidate_review_contract import CandidateReviewError
from pilot.research_assessment import ResearchAssessmentRunner
from pilot.research_candidates import ResearchCandidateStore
from tests.test_candidate_assessment_model import CONTENT, assessment
from tests.test_candidate_review_postgres import review_payload
from tests.test_candidate_review_postgres import (databases, env, execution_databases,
    execution_env, raw_databases, raw_env)
from tests.test_confirmed_strategy_review_postgres import real_strategy_env
from tests.test_research_candidates_postgres import topic
from tests.test_research_resources_postgres import started, store as resource_store
from tests.test_execution_runtime_postgres import apply, operation


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


def _source(env):
    execution, _ = started(env)
    resources = resource_store(env)
    receipt = ResearchCandidateStore(resources).read_public(
        env.claims, task_id=execution["task_id"], run_id=execution["run_id"],
        action_id=str(uuid4()), fetcher=lambda _deadline: [topic(
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
