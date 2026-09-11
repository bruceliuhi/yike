"""Regression coverage for coordinator fencing at resource admission."""
import pytest

from tests.test_research_runtime_postgres import (
    _runtime,
    databases,
    env,
    execution_databases,
    execution_env,
    raw_databases,
    raw_env,
    real_strategy_env,
    runtime_env,
    started,
)


def test_lost_coordinator_is_fenced_before_the_next_model_effect(runtime_env, monkeypatch):
    from pilot.execution_contract import ExecutionRuntimeError
    from tests.test_candidate_assessment_model import CONTENT
    from tests.test_candidate_review_postgres import BoundaryModel
    from tests.test_research_candidates_postgres import topic

    environment = runtime_env
    execution, _ = started(environment)

    class Model(BoundaryModel):
        def assess_before(self, _deadline, **kwargs):
            return self.assess(**kwargs)

    model = Model()
    fetcher = lambda _: [topic(905, title=CONTENT["title"], content=CONTENT["body"])]
    old = _runtime(environment, fetcher=fetcher, model=model)
    newer = _runtime(environment, fetcher=fetcher, model=model)
    task_id, run_id = execution["task_id"], execution["run_id"]
    original_advance = old.orchestrator.advance_one

    def resumed_after_takeover(*args, **kwargs):
        with environment.admin.connect() as connection:
            connection.execute(
                "UPDATE pilot_research_runtime SET lease_expires_at="
                "clock_timestamp()-interval '1 second' WHERE tenant_id=%s AND task_id=%s",
                (environment.tenant, task_id),
            )
        assert newer.advance(environment.claims, task_id, run_id)["acceptedOriginals"] == 1
        assert model.calls == 0
        return original_advance(*args, **kwargs)

    monkeypatch.setattr(old.orchestrator, "advance_one", resumed_after_takeover)
    with pytest.raises(ExecutionRuntimeError, match="lease_conflict"):
        old.advance(environment.claims, task_id, run_id)
    assert model.calls == 0
    status = newer.status(environment.claims, task_id)
    assert status["phase"] == "STOPPED" and status["canAdvance"] is False
    assert status["stopCode"] == "assessment_unknown"
