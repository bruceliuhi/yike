"""Composition tests only: no model network calls or customer database."""
from fastapi.testclient import TestClient
import pytest

from pilot.db import PilotDatabase


def test_absent_configuration_keeps_generation_off_but_registers_receipt_route():
    from pilot.runtime import build_runtime_app
    app = build_runtime_app(object(), auth_secret="synthetic-secret", environment={})
    paths = {route.path for route in app.routes}
    assert "/api/ui/search-suggestions/preview" in paths
    assert "/api/ui/search-suggestions/{request_id}" in paths
    with TestClient(app, base_url="https://testserver") as client:
        assert client.get("/api/ui/capabilities").json()["capabilities"]["search_suggestions"] == {"available": False}
        assert client.get("/api/ui/search-suggestions/00000000-0000-0000-0000-000000000001").status_code == 401


@pytest.mark.parametrize("config", [
    {"YIKE_PILOT_SEARCH_SUGGESTION_MODEL": "synthetic"},
    {"YIKE_PILOT_SEARCH_SUGGESTION_BASE_URL": "http://not-local.example/v1",
     "YIKE_PILOT_SEARCH_SUGGESTION_API_KEY": "private-synthetic-value",
     "YIKE_PILOT_SEARCH_SUGGESTION_MODEL": "synthetic"},
])
def test_incomplete_or_unsafe_configuration_fails_without_secret(config):
    from pilot.runtime import build_runtime_app
    with pytest.raises(RuntimeError, match="^invalid_search_suggestion_configuration$") as caught:
        build_runtime_app(object(), auth_secret="synthetic-secret", environment=config)
    assert caught.value.__context__ is None


def test_explicit_configuration_composes_process_model_and_closes_service(monkeypatch):
    import pilot.runtime as runtime
    made = []

    class SyntheticProcessModel:
        provider = "openai-compatible"
        available = True

        def __init__(self, **kwargs):
            self.model = kwargs["model"]
            self.closed = False
            made.append(self)

        def close(self, timeout_seconds=5):
            self.closed = True
            self.available = False
            return True

        def generate(self, **kwargs):
            raise AssertionError("app assembly must never call a model")

    monkeypatch.setattr(runtime, "ProcessSearchSuggestionModel", SyntheticProcessModel)
    app = runtime.build_runtime_app(object(), auth_secret="synthetic-secret", environment={
        "YIKE_PILOT_SEARCH_SUGGESTION_BASE_URL": "https://model.example/v1",
        "YIKE_PILOT_SEARCH_SUGGESTION_API_KEY": "synthetic-private-value",
        "YIKE_PILOT_SEARCH_SUGGESTION_MODEL": "synthetic/model-v1",
    })
    assert len(made) == 1
    with TestClient(app) as client:
        assert client.get("/api/ui/capabilities").json()["capabilities"]["search_suggestions"] == {"available": True}
        made[0].available = False
        assert client.get("/api/ui/capabilities").json()["capabilities"]["search_suggestions"] == {"available": False}
    assert made[0].closed


def test_search_consent_migration_registered_after_original_requests():
    names = [path.name for _, path in PilotDatabase.migration_paths]
    assert names.index("128_v02_search_suggestion_consent.sql") > names.index("110_v02_search_suggestions.sql")


def test_unconfirmed_shutdown_is_not_reported_as_stopped():
    from pilot.web import build_app

    class UnconfirmedService:
        available = False

        def close(self, timeout_seconds):
            assert timeout_seconds == 5
            return False

    app = build_app(object(), auth_secret="synthetic-secret", search_suggestions=UnconfirmedService())
    with pytest.raises(RuntimeError, match="^search_suggestion_shutdown_unconfirmed$"):
        with TestClient(app):
            pass
