"""Composition/HTTP contracts only; synthetic config never runs a provider."""
import socket

import pytest
from fastapi.testclient import TestClient

from pilot.dynamic_research_runtime import DynamicResearchRuntimeService
from pilot.execution_contract import ExecutionRuntimeError
from pilot.execution_runtime import ExecutionRuntime
from pilot.research_execution import ResearchExecutionService
from pilot.research_quote import ResearchQuoteService
from pilot.research_runtime import ResearchRuntimeService
from pilot.runtime import build_runtime_app
from tests.test_dynamic_research_config import base_environment, agent_environment, dynamic_configuration
from tests.test_pilot_runtime import _route_service
from tests.test_research_execution_api import Runtime, Service, client


def environment():
    return base_environment() | agent_environment() | {
        "YIKE_PILOT_ASSESSMENT_BASE_URL": "https://model.example/v1",
        "YIKE_PILOT_ASSESSMENT_API_KEY": "synthetic-assessment-key",
        "YIKE_PILOT_ASSESSMENT_MODEL": "synthetic/assessment-v1",
    }


def test_dynamic_assembly_shares_authority_without_enabling_ordinary_collection(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("composition must not contact a provider")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    app = build_runtime_app(object(), auth_secret="s" * 32, environment=environment())
    fixed = _route_service(app, "/api/ui/research-execution/capability", ResearchRuntimeService)
    dynamic = fixed.dynamic
    assert isinstance(dynamic, DynamicResearchRuntimeService)
    try:
        execution = _route_service(app, "/api/ui/research-execution/start", ResearchExecutionService)
        quotes = _route_service(app, "/api/ui/research-usage/quote", ResearchQuoteService)
        ordinary = _route_service(app, "/api/ui/execution-operations", ExecutionRuntime)
        assert dynamic.fixed is fixed and dynamic.execution is execution.runtime
        assert dynamic.candidates.journal is dynamic.journal
        assert dynamic.journal.resources is fixed.orchestrator.sources.resources
        assert dynamic.journal.resources.research_capability is quotes.research_capability
        config = dynamic_configuration()
        snapshot = {"platforms": ["PUBLIC_WEB"], "configuration": config,
                    "max_records": 20, "max_runtime_seconds": 900}
        assert execution.runtime.capability_check("PUBLIC_WEB", "PUBLIC_ANONYMOUS", config)
        assert quotes.research_capability(snapshot)
        assert ordinary.capability_check is None
        assert not execution.runtime.capability_check("XIAOHONGSHU", "LOCAL_AUTHORIZED", config)
    finally:
        assert dynamic.shutdown()


@pytest.mark.parametrize("confirmed", [True, False])
def test_runtime_lifespan_closes_dynamic_and_preserves_existing_cleanup(monkeypatch, confirmed):
    from pilot.search_suggestion_service import SearchSuggestionService
    app = build_runtime_app(object(), auth_secret="s" * 32, environment=environment())
    fixed = _route_service(app, "/api/ui/research-execution/capability", ResearchRuntimeService)
    assert fixed.dynamic is not None
    calls = []
    original = fixed.dynamic.shutdown
    def shutdown(*, timeout_seconds):
        calls.append(("dynamic", timeout_seconds))
        assert original(timeout_seconds=timeout_seconds)
        return confirmed
    monkeypatch.setattr(fixed.dynamic, "shutdown", shutdown)
    monkeypatch.setattr(SearchSuggestionService, "close",
                        lambda _self, *, timeout_seconds: calls.append(("suggestions", timeout_seconds)) or True)
    if confirmed:
        with TestClient(app):
            assert not calls
    else:
        with pytest.raises(RuntimeError, match="^dynamic_research_shutdown_unconfirmed$"):
            with TestClient(app):
                assert not calls
    assert calls == [("dynamic", 5), ("suggestions", 5)]


class DynamicRuntime(Runtime):
    def capability(self, claims, *, source_catalog_version=None, source_plan_version=None,
                   dynamic_research_version=None):
        self.calls.append(("capability", claims, source_catalog_version,
                           source_plan_version, dynamic_research_version))
        return DynamicResearchRuntimeService.capability() if dynamic_research_version else {
            "contractVersion": 3 if source_plan_version else 2 if source_catalog_version else 1}


def test_dynamic_http_negotiation_is_exclusive_read_only_and_preserves_old_versions():
    runtime = DynamicRuntime()
    http = client(Service(), runtime)
    path = "/api/ui/research-execution/capability"
    response = http.get(path + "?dynamic_research_version=1")
    assert response.status_code == 200
    assert response.json() == DynamicResearchRuntimeService.capability()
    assert response.headers["cache-control"] == "no-store"
    assert runtime.calls[-1][2:] == (None, None, 1)
    for query in ("dynamic_research_version=2", "dynamic_research_version=01",
                  "dynamic_research_version=1&dynamic_research_version=1",
                  "dynamic_research_version=1&source_plan_version=1",
                  "dynamic_research_version=1&source_catalog_version=1",
                  "dynamic_research_version=1&key=synthetic-secret"):
        rejected = http.get(path + "?" + query)
        assert rejected.status_code == 422
        assert rejected.json() == {"detail": {"code": "invalid_request"}}
    assert len(runtime.calls) == 1
    for query, version in (("", 1), ("?source_catalog_version=1", 2), ("?source_plan_version=1", 3)):
        assert http.get(path + query).json() == {"contractVersion": version}


def test_unavailable_dynamic_mode_exposes_only_exact_negotiation_error():
    class Unsupported(DynamicRuntime):
        def capability(self, claims, **kwargs):
            raise ExecutionRuntimeError("invalid_request", 422)
    response = client(Service(), Unsupported()).get(
        "/api/ui/research-execution/capability?dynamic_research_version=1")
    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "invalid_request"}}
