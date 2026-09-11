"""Restricted PostgreSQL coverage for bounded persisted research advancement."""
from pathlib import Path
from datetime import UTC, datetime
from uuid import uuid4
import pytest
from tests.test_confirmed_strategy_review_postgres import real_strategy_env
from tests.test_research_resources_postgres import started, started_again, store
from tests.test_candidate_review_postgres import (databases, env, execution_databases,
    execution_env, raw_databases, raw_env)


def _stable(value):
    return value | {"usage": value["usage"] | {"resourceCloseout":
        value["usage"]["resourceCloseout"] | {"asOf": None}}}


def _runtime(env, *, fetcher, model):
    from pilot.candidate_review import CandidateReviewStore
    from pilot.research_assessment import ResearchAssessmentRunner
    from pilot.research_candidates import ResearchCandidateStore
    from pilot.research_orchestrator import ResearchOrchestrator
    from pilot.research_runtime import ResearchRuntimeService

    resources = store(env)
    reviews = CandidateReviewStore(env.db, model=model,
        strategy_resolver=env.strategies.resolve,
        strategy_snapshot_reader=env.strategies.read_snapshot,
        research_assessment=ResearchAssessmentRunner(resources))
    orchestrator = ResearchOrchestrator(ResearchCandidateStore(resources), reviews,
        fetcher=fetcher)
    return ResearchRuntimeService(orchestrator)


def _grant_runtime(env):
    with env.db.connect() as connection:
        role = connection.execute("SELECT current_user").fetchone()[0]
    with env.admin.connect() as connection:
        connection.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
        grant = (Path(__file__).parents[1] / "deploy/grant_research_runtime.sql").read_text()
        connection.execute(grant)


@pytest.fixture
def runtime_env(real_strategy_env):
    _grant_runtime(real_strategy_env)
    yield real_strategy_env
    with real_strategy_env.admin.connect() as connection:
        connection.execute("DELETE FROM pilot_research_runtime WHERE tenant_id=ANY(%s)",
            (real_strategy_env.tenants,))


def test_one_fresh_effect_per_advance_and_read_only_status(runtime_env):
    from tests.test_candidate_assessment_model import CONTENT
    from tests.test_candidate_review_postgres import BoundaryModel
    from tests.test_research_candidates_postgres import topic

    env = runtime_env
    execution, _ = started(env)
    reads = []
    class Model(BoundaryModel):
        def assess_before(self, deadline, **kwargs):
            assert deadline > datetime.now(UTC)
            return self.assess(**kwargs)
    model = Model()
    runtime = _runtime(env, fetcher=lambda _deadline: reads.append("read") or [
        topic(901, title=CONTENT["title"], content=CONTENT["body"]),
        topic(902, title=CONTENT["title"], content=CONTENT["body"]),
    ], model=model)
    task_id, run_id = execution["task_id"], execution["run_id"]
    assert runtime.capability(env.claims)["sourceScope"] == "V2EX_LATEST_INDEX"

    queued = runtime.status(env.claims, task_id)
    assert queued["phase"] == "QUEUED" and queued["canAdvance"] is True
    assert queued["usage"]["resourceCloseout"]["state"] == "OPEN"
    assert reads == [] and model.calls == 0

    after_source = runtime.advance(env.claims, task_id, run_id)
    assert after_source["phase"] == "RUNNING"
    assert after_source["acceptedOriginals"] == 2
    assert reads == ["read"] and model.calls == 0

    after_model_one = runtime.advance(env.claims, task_id, run_id)
    assert after_model_one["analyzedOriginals"] == 1
    assert reads == ["read"] and model.calls == 1
    after_model_two = runtime.advance(env.claims, task_id, run_id)
    assert after_model_two["phase"] == "COMPLETED"
    assert after_model_two["analyzedOriginals"] == 2
    assert len(after_model_two["candidateIds"]) == 2
    assert after_model_two["usage"]["actualSoubei"] is None
    assert after_model_two["usage"]["settlementState"] == "PENDING"
    closeout = after_model_two["usage"]["resourceCloseout"]
    assert closeout["state"] == "RECORDED" and closeout["overduePermits"] == 0
    assert datetime.fromisoformat(closeout["asOf"]).tzinfo is not None

    assert _stable(runtime.status(env.claims, task_id)) == _stable(after_model_two)
    assert _stable(runtime.advance(env.claims, task_id, run_id)) == _stable(after_model_two)
    assert reads == ["read"] and model.calls == 2


def test_terminal_commit_failure_recovers_without_repeating_effect(runtime_env, monkeypatch):
    from tests.test_candidate_review_postgres import BoundaryModel
    env = runtime_env
    execution, _ = started(env)
    reads = []
    runtime = _runtime(env, fetcher=lambda _: reads.append("read") or [], model=BoundaryModel())
    complete = runtime._complete
    def crash(*args):
        raise RuntimeError("synthetic terminal write failure")
    monkeypatch.setattr(runtime, "_complete", crash)
    task, run = execution["task_id"], execution["run_id"]
    with pytest.raises(RuntimeError, match="synthetic terminal"):
        runtime.advance(env.claims, task, run)
    # Until atomic terminal commit, the client must not report a completed task.
    assert runtime.status(env.claims, task)["phase"] != "COMPLETED"
    with env.admin.connect() as connection:
        connection.execute("UPDATE pilot_research_runtime SET lease_expires_at=clock_timestamp()-interval '1 second' "
            "WHERE tenant_id=%s AND task_id=%s AND current_owner IS NOT NULL", (env.tenant, task))
    monkeypatch.setattr(runtime, "_complete", complete)
    result = runtime.advance(env.claims, task, run)
    assert result["phase"] == "COMPLETED"
    assert runtime.execution.get_task(env.claims, task)["status"] == "SUCCEEDED"
    assert reads == ["read"]


def test_unknown_model_effect_is_visible_and_never_retried(runtime_env):
    from pilot.execution_contract import ExecutionRuntimeError
    from tests.test_candidate_assessment_model import CONTENT
    from tests.test_candidate_review_postgres import BoundaryModel
    from tests.test_research_candidates_postgres import topic

    env = runtime_env
    execution, _ = started(env)
    class UnknownModel(BoundaryModel):
        def assess_before(self, _deadline, **_kwargs):
            self.calls += 1
            raise TimeoutError("synthetic uncertain model boundary")
    model = UnknownModel()
    runtime = _runtime(env, fetcher=lambda _deadline: [topic(
        903, title=CONTENT["title"], content=CONTENT["body"])], model=model)
    task_id, run_id = execution["task_id"], execution["run_id"]
    runtime.advance(env.claims, task_id, run_id)
    runtime.advance(env.claims, task_id, run_id)
    stopped = runtime.status(env.claims, task_id)
    assert stopped["phase"] == "STOPPED"
    assert stopped["stopCode"] == "effect_unknown"
    assert stopped["effectsPending"] is False and stopped["newActionsBlocked"] is True
    assert stopped["usage"]["modelCalls"]["unknown"] == 1
    assert stopped["usage"]["resourceCloseout"]["state"] == "UNCERTAIN"
    assert _stable(runtime.advance(env.claims, task_id, run_id)) == _stable(stopped)
    assert model.calls == 1


def test_cancel_and_owner_isolation_block_new_effects(runtime_env):
    from pilot.auth import issue_token, verify_token_claims
    from pilot.execution_contract import ExecutionRuntimeError
    from tests.test_candidate_review_postgres import BoundaryModel
    from tests.test_execution_runtime_postgres import SECRET

    env = runtime_env
    execution, _ = started(env)
    calls = []
    runtime = _runtime(env, fetcher=lambda _deadline: calls.append("read") or [],
        model=BoundaryModel())
    task_id, run_id = execution["task_id"], execution["run_id"]
    with env.admin.connect() as connection:
        for table in ("pilot_collection_platform_runs", "pilot_collection_runs", "pilot_collection_tasks"):
            connection.execute(f"UPDATE {table} SET status='CANCELED' WHERE tenant_id=%s AND task_id=%s",
                (env.tenant, task_id))
    canceled = runtime.advance(env.claims, task_id, run_id)
    assert canceled["phase"] == "CANCELED" and canceled["canAdvance"] is False
    assert calls == []
    stranger = verify_token_claims(issue_token(env.users[1], SECRET), SECRET)
    with pytest.raises(ExecutionRuntimeError) as caught:
        runtime.status(stranger, task_id)
    assert (caught.value.code, caught.value.status) == ("task_not_found", 404)


def test_migration_registration_and_restricted_grants(runtime_env):
    from pilot.db import PilotDatabase
    env = runtime_env
    assert ("v02-research-runtime", Path(__file__).parents[1] /
        "migrations/137_v02_research_runtime.sql") in PilotDatabase.migration_paths
    with env.db.connect() as connection:
        role = connection.execute("SELECT current_user").fetchone()[0]
    with env.admin.connect() as connection:
        assert connection.execute("SELECT has_table_privilege(%s,'pilot_research_runtime','SELECT,INSERT')",
            (role,)).fetchone()[0]
        for privilege in ("DELETE", "TRUNCATE", "TRIGGER", "REFERENCES"):
            assert not connection.execute(
                "SELECT has_table_privilege(%s,'pilot_research_runtime',%s)",
                (role, privilege)).fetchone()[0]


def test_durable_stop_reason_and_active_lease_prevent_client_spin(runtime_env, monkeypatch):
    from pilot.execution_contract import ExecutionRuntimeError
    from tests.test_candidate_review_postgres import BoundaryModel

    env = runtime_env
    execution, _ = started(env)
    runtime = _runtime(env, fetcher=lambda _deadline: [], model=BoundaryModel())
    task_id, run_id = execution["task_id"], execution["run_id"]

    def exhausted(*_args, **_kwargs):
        raise ExecutionRuntimeError("resource_limit_exceeded", 409)
    monkeypatch.setattr(runtime.orchestrator, "advance_one", exhausted)
    with pytest.raises(ExecutionRuntimeError, match="resource_limit_exceeded"):
        runtime.advance(env.claims, task_id, run_id)
    stopped = runtime.status(env.claims, task_id)
    assert stopped["phase"] == "STOPPED"
    assert stopped["stopCode"] == "resource_limit_exceeded"
    assert stopped["canAdvance"] is False and stopped["newActionsBlocked"] is True

    with env.admin.connect() as connection:
        connection.execute("UPDATE pilot_research_runtime SET phase='RUNNING',stop_code=NULL,"
            "current_owner=%s,lease_expires_at=clock_timestamp()+interval '2 minutes' "
            "WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s",
            (str(uuid4()), env.tenant, env.claims.user_id, task_id))
    leased = runtime.status(env.claims, task_id)
    assert leased["phase"] == "RUNNING"
    assert leased["canAdvance"] is False and leased["newActionsBlocked"] is True
    assert leased["usage"]["resourceCloseout"]["state"] == "DRAINING"


def test_resource_closeout_tracks_cancelled_inflight_expiry_and_late_finish(runtime_env):
    from tests.test_candidate_review_postgres import BoundaryModel
    from tests.test_execution_runtime_postgres import apply, operation
    env = runtime_env
    execution, reservation = started(env)
    runtime = _runtime(env, fetcher=lambda _: [], model=BoundaryModel())
    resource_store = store(env)
    issued = resource_store.begin(env.claims, task_id=execution["task_id"], run_id=execution["run_id"],
        action_id=str(uuid4()), resource="SOURCE_READ", input_sha256="a" * 64)["event"]
    assert runtime.status(env.claims, execution["task_id"])["usage"]["resourceCloseout"]["state"] == "DRAINING"
    apply(env, operation(env, "CANCEL", execution))
    assert runtime.status(env.claims, execution["task_id"])["usage"]["resourceCloseout"]["state"] == "DRAINING"
    resource_store.finish(env.claims, task_id=execution["task_id"], run_id=execution["run_id"],
        action_id=issued["action_id"], permit_id=issued["permit_id"], status="FAILED")
    action_id, permit_id = str(uuid4()), str(uuid4())
    with env.admin.connect() as connection:
        connection.execute("INSERT INTO pilot_research_resource_events(tenant_id,owner_user_id,reservation_id,task_id,run_id,"
            "action_id,permit_id,resource,input_sha256,issued_at,deadline_at) VALUES(%s,%s,%s,%s,%s,%s,%s,'SOURCE_READ',"
            "%s,clock_timestamp()-interval '2 seconds',clock_timestamp()-interval '1 second')", (env.tenant,
             env.claims.user_id, reservation["reservation_id"], execution["task_id"], execution["run_id"],
             action_id, permit_id, "c" * 64))
    overdue = runtime.status(env.claims, execution["task_id"])["usage"]["resourceCloseout"]
    assert overdue["state"] == "UNCERTAIN" and overdue["overduePermits"] == 1
    with env.admin.connect() as connection:
        assert connection.execute("SELECT status,finished_at FROM pilot_research_resource_events "
            "WHERE tenant_id=%s AND action_id=%s", (env.tenant, action_id)).fetchone() == ("ISSUED", None)
    resource_store.finish(env.claims, task_id=execution["task_id"], run_id=execution["run_id"],
        action_id=action_id, permit_id=permit_id, status="FAILED")
    recorded = runtime.status(env.claims, execution["task_id"])["usage"]["resourceCloseout"]
    assert recorded["state"] == "RECORDED" and recorded["overduePermits"] == 0


def test_resource_closeout_unknown_and_stopped_nonterminal_are_never_recorded(runtime_env):
    from tests.test_candidate_review_postgres import BoundaryModel
    env = runtime_env
    execution, _ = started(env)
    runtime = _runtime(env, fetcher=lambda _: [], model=BoundaryModel())
    issued = store(env).begin(env.claims, task_id=execution["task_id"], run_id=execution["run_id"],
        action_id=str(uuid4()), resource="MODEL_CALL", input_sha256="b" * 64)["event"]
    store(env).finish(env.claims, task_id=execution["task_id"], run_id=execution["run_id"],
        action_id=issued["action_id"], permit_id=issued["permit_id"], status="UNKNOWN")
    assert runtime.status(env.claims, execution["task_id"])["usage"]["resourceCloseout"]["state"] == "UNCERTAIN"
    other, _ = started_again(env)
    with env.admin.connect() as connection:
        connection.execute("INSERT INTO pilot_research_runtime(tenant_id,owner_user_id,task_id,run_id,phase,stop_code) "
            "VALUES(%s,%s,%s,%s,'STOPPED','synthetic_stop')", (env.tenant, env.claims.user_id,
             other["task_id"], other["run_id"]))
    assert runtime.status(env.claims, other["task_id"])["usage"]["resourceCloseout"]["state"] == "OPEN"


def test_resource_closeout_database_inputs_share_one_read_only_repeatable_snapshot(runtime_env, monkeypatch):
    from tests.test_candidate_review_postgres import BoundaryModel
    env = runtime_env
    execution, _ = started(env)
    runtime = _runtime(env, fetcher=lambda _: [], model=BoundaryModel())
    observed = []
    original = runtime._usage
    def inspect_transaction(cursor, *args):
        cursor.execute("SHOW transaction_isolation")
        isolation = cursor.fetchone()[0]
        cursor.execute("SHOW transaction_read_only")
        observed.append((isolation, cursor.fetchone()[0]))
        return original(cursor, *args)
    monkeypatch.setattr(runtime, "_usage", inspect_transaction)
    result = runtime.status(env.claims, execution["task_id"])
    assert observed == [("repeatable read", "on")]
    assert datetime.fromisoformat(result["usage"]["resourceCloseout"]["asOf"]).tzinfo is not None


def test_actual_runtime_app_authenticated_http_start_advance_and_status(runtime_env, monkeypatch):
    from fastapi.testclient import TestClient
    from pilot.auth import issue_token, verify_token_claims
    from pilot.candidate_assessment_model import OpenAICompatibleCandidateAssessmentModel
    import pilot.runtime as runtime_module
    from pilot.research_orchestrator import ResearchOrchestrator
    from tests.test_candidate_assessment_model import CONTENT
    from tests.test_candidate_review_postgres import BoundaryModel
    from tests.test_execution_runtime_postgres import SECRET, start
    from tests.test_research_candidates_postgres import topic
    from tests.test_research_execution_postgres import signed_start
    from tests.test_research_quote_postgres import _confirmed_research, _request
    from tests.test_research_strategies_postgres import prepare_body, confirm_body

    env = runtime_env
    _, _, _, _, _, legacy_confirmed = _confirmed_research(env)
    configuration = legacy_confirmed["snapshot"]["configuration"] | {
        "publicSource": "v2ex-latest-v1"}
    pending = env.strategies.prepare(env.claims, prepare_body(env, configuration=configuration))
    confirmed = env.strategies.confirm(env.claims, confirm_body(pending))
    env.confirmed, env.snapshot = confirmed, confirmed["snapshot"]
    model_calls = []
    class HttpModel(OpenAICompatibleCandidateAssessmentModel):
        def assess_before(self, _deadline, **kwargs):
            model_calls.append(kwargs)
            return BoundaryModel().assess(**kwargs)
    model = HttpModel("https://example.invalid/v1", "synthetic-key", "synthetic-model")
    monkeypatch.setattr(runtime_module, "_assessment_model", lambda _environment: model)
    monkeypatch.setattr(runtime_module, "ResearchOrchestrator", lambda sources, reviews:
        ResearchOrchestrator(sources, reviews, fetcher=lambda _deadline: [topic(
            904, title=CONTENT["title"], content=CONTENT["body"])]))
    environment = {
        "YIKE_PILOT_RESEARCH_MODE": "public-v2ex-v1",
        "YIKE_PILOT_RESEARCH_RULE_VERSION": "synthetic-review-rule-v1",
        "YIKE_PILOT_RESEARCH_SOURCE_MILLI": "100",
        "YIKE_PILOT_RESEARCH_MINUTE_MILLI": "200",
        "YIKE_PILOT_RESEARCH_MODEL_CALL_MILLI": "300",
    }
    http_secret = SECRET + "-long-enough-for-research-signing"
    token = issue_token(env.claims.user_id, http_secret)
    env.claims = verify_token_claims(token, http_secret)
    app = runtime_module.build_runtime_app(env.db, auth_secret=http_secret, environment=environment)
    headers = {"Authorization": "Bearer " + token}
    operation = start(env)
    with TestClient(app, base_url="https://pilot.example") as client:
        assert client.get("/api/ui/research-execution/capability").status_code == 401
        quote_response = client.post("/api/ui/research-usage/quote",
            json=_request(env, confirmed) | {"requestId": operation.request_id}, headers=headers)
        assert quote_response.status_code == 200
        quote = quote_response.json()
        start_response = client.post("/api/ui/research-execution/start", json={
            "request": operation.model_dump(mode="json"),
            "signature": signed_start(env, operation),
            "authorization_token": quote["authorizationToken"],
        }, headers=headers)
        assert start_response.status_code == 200
        execution = start_response.json()["execution"]
        task_id, run_id = execution["task_id"], execution["run_id"]
        first = client.post(f"/api/ui/research-execution/tasks/{task_id}/advance",
            json={"runId": run_id}, headers=headers)
        assert first.status_code == 200 and first.json()["acceptedOriginals"] == 1
        second = client.post(f"/api/ui/research-execution/tasks/{task_id}/advance",
            json={"runId": run_id}, headers=headers)
        assert second.status_code == 200 and second.json()["phase"] == "COMPLETED"
        status = client.get(f"/api/ui/research-execution/tasks/{task_id}", headers=headers)
        assert status.status_code == 200 and _stable(status.json()) == _stable(second.json())
        feed = client.get(f"/api/ui/execution-task-feed/{task_id}", headers=headers)
        assert feed.status_code == 200 and feed.json()["item"]["research"] is True
    assert len(model_calls) == 1
