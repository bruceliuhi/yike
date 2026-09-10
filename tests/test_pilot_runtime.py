from __future__ import annotations

import inspect
import socket

import pytest
from fastapi.testclient import TestClient

from pilot.candidate_assessment_model import OpenAICompatibleCandidateAssessmentModel
from pilot.candidate_ingestion import CandidateIngestionStore
from pilot.candidate_review import CandidateReviewStore
from pilot.execution_runtime import ExecutionRuntime
from pilot.research_strategies import ResearchStrategyStore
from pilot.store import PilotStore


def _closed_values(function, seen=None):
    seen = set() if seen is None else seen
    if not inspect.isfunction(function) or id(function) in seen:
        return
    seen.add(id(function))
    for cell in function.__closure__ or ():
        try:
            value = cell.cell_contents
        except ValueError:
            continue
        yield value
        yield from _closed_values(value, seen)


def _route_service(app, path, service_type):
    endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", None) == path)
    matches = [value for value in _closed_values(endpoint) if isinstance(value, service_type)]
    assert len({id(value) for value in matches}) == 1
    return matches[0]


def test_build_runtime_app_composes_real_services_on_one_database_and_strategy_store():
    from pilot.runtime import build_runtime_app

    database = object()
    app = build_runtime_app(database, auth_secret="synthetic-auth-secret", environment={})

    store = _route_service(app, "/readyz", PilotStore)
    runtime = _route_service(app, "/api/ui/execution-operations", ExecutionRuntime)
    ingestion = _route_service(app, "/api/ui/candidate-batches", CandidateIngestionStore)
    review = _route_service(app, "/api/ui/candidate-reviews", CandidateReviewStore)
    strategies = _route_service(app, "/api/ui/research-strategies/prepare", ResearchStrategyStore)

    assert all(service.database is database for service in (store, runtime, ingestion, review, strategies))
    assert ingestion.execution_runtime is runtime
    assert runtime.strategy_resolver.__self__ is strategies
    assert review.strategy_resolver.__self__ is strategies
    assert review.strategy_snapshot_reader.__self__ is strategies
    assert review.strategy_snapshot_reader.__func__ is ResearchStrategyStore.read_snapshot
    assert runtime.capability_check is None
    assert review.model is None

    capabilities = TestClient(app).get("/api/ui/capabilities").json()["capabilities"]
    assert capabilities["task_execution"] == {"available": False}
    assert capabilities["outreach"] == {"available": False}


def test_explicit_foreground_mode_composes_bounded_policy_without_global_capability():
    from pilot.runtime import build_runtime_app
    from pilot.foreground_collection import foreground_collection_policy
    app = build_runtime_app(object(), auth_secret='synthetic-auth-secret',
                            environment={'YIKE_PILOT_COLLECTION_MODE':'xhs-foreground-v1'})
    runtime = _route_service(app, '/api/ui/execution-operations', ExecutionRuntime)
    assert runtime.capability_check is foreground_collection_policy
    assert TestClient(app).get('/api/ui/capabilities').json()['capabilities']['task_execution'] == {'available':False}


def test_absent_or_blank_assessment_configuration_keeps_model_unavailable():
    from pilot.runtime import build_runtime_app

    environment = {
        "YIKE_PILOT_ASSESSMENT_BASE_URL": " \t",
        "YIKE_PILOT_ASSESSMENT_API_KEY": "",
        "YIKE_PILOT_ASSESSMENT_MODEL": "\n",
    }
    app = build_runtime_app(object(), auth_secret="synthetic-auth-secret", environment=environment)

    review = _route_service(app, "/api/ui/candidate-reviews", CandidateReviewStore)
    assert review.model is None
    assert all(value is not environment for route in app.routes for value in _closed_values(getattr(route, "endpoint", None)))


@pytest.mark.parametrize(
    "present",
    [
        {"YIKE_PILOT_ASSESSMENT_BASE_URL"},
        {"YIKE_PILOT_ASSESSMENT_API_KEY"},
        {"YIKE_PILOT_ASSESSMENT_MODEL"},
        {"YIKE_PILOT_ASSESSMENT_BASE_URL", "YIKE_PILOT_ASSESSMENT_API_KEY"},
        {"YIKE_PILOT_ASSESSMENT_BASE_URL", "YIKE_PILOT_ASSESSMENT_MODEL"},
        {"YIKE_PILOT_ASSESSMENT_API_KEY", "YIKE_PILOT_ASSESSMENT_MODEL"},
    ],
)
def test_partial_assessment_configuration_fails_closed(present):
    from pilot.runtime import build_runtime_app

    complete = {
        "YIKE_PILOT_ASSESSMENT_BASE_URL": "https://model.example/v1",
        "YIKE_PILOT_ASSESSMENT_API_KEY": "synthetic-model-secret",
        "YIKE_PILOT_ASSESSMENT_MODEL": "synthetic/model-v1",
    }
    environment = {name: value for name, value in complete.items() if name in present}

    with pytest.raises(RuntimeError) as caught:
        build_runtime_app(object(), auth_secret="synthetic-auth-secret", environment=environment)

    assert str(caught.value) == "invalid_assessment_configuration"
    assert caught.value.__cause__ is None and caught.value.__context__ is None


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("YIKE_PILOT_ASSESSMENT_BASE_URL", " https://model.example/v1"),
        ("YIKE_PILOT_ASSESSMENT_API_KEY", "synthetic secret with spaces"),
        ("YIKE_PILOT_ASSESSMENT_MODEL", "synthetic model"),
    ],
)
def test_invalid_complete_assessment_configuration_is_safe_and_value_free(name, value):
    from pilot.runtime import build_runtime_app

    environment = {
        "YIKE_PILOT_ASSESSMENT_BASE_URL": "https://model.example/v1",
        "YIKE_PILOT_ASSESSMENT_API_KEY": "synthetic-model-secret",
        "YIKE_PILOT_ASSESSMENT_MODEL": "synthetic/model-v1",
    }
    environment[name] = value

    with pytest.raises(RuntimeError) as caught:
        build_runtime_app(object(), auth_secret="synthetic-auth-secret", environment=environment)

    assert str(caught.value) == "invalid_assessment_configuration"
    assert value not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_complete_assessment_configuration_builds_adapter_without_network_or_normalization(monkeypatch):
    from pilot.runtime import build_runtime_app

    def network_forbidden(*_args, **_kwargs):
        raise AssertionError("runtime assembly must not connect to a provider or source")

    monkeypatch.setattr(socket, "create_connection", network_forbidden)
    monkeypatch.setattr(socket.socket, "connect", network_forbidden)
    environment = {
        "YIKE_PILOT_ASSESSMENT_BASE_URL": "https://model.example/v1",
        "YIKE_PILOT_ASSESSMENT_API_KEY": "synthetic-model-secret",
        "YIKE_PILOT_ASSESSMENT_MODEL": "synthetic/model-v1",
    }

    app = build_runtime_app(object(), auth_secret="synthetic-auth-secret", environment=environment)
    model = _route_service(app, "/api/ui/candidate-reviews", CandidateReviewStore).model

    assert isinstance(model, OpenAICompatibleCandidateAssessmentModel)
    assert (model.base_url, model.api_key, model.model) == tuple(environment.values())
    assert model.timeout_seconds == 30


def test_runtime_rejects_inherited_admin_database_url_before_service_assembly():
    from pilot.runtime import build_runtime_app

    secret_admin_url = "postgresql://admin:synthetic-secret@private.invalid/pilot"
    with pytest.raises(RuntimeError) as caught:
        build_runtime_app(
            object(),
            auth_secret="synthetic-auth-secret",
            environment={"YIKE_PILOT_ADMIN_DATABASE_URL": secret_admin_url},
        )

    assert str(caught.value) == "admin_database_url_forbidden_in_web_runtime"
    assert secret_admin_url not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_blank_admin_database_url_is_not_treated_as_inherited_admin_authority():
    from pilot.runtime import build_runtime_app

    app = build_runtime_app(
        object(), auth_secret="synthetic-auth-secret", environment={"YIKE_PILOT_ADMIN_DATABASE_URL": " \t"}
    )

    assert isinstance(_route_service(app, "/readyz", PilotStore), PilotStore)
