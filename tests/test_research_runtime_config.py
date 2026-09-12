from copy import deepcopy

import pytest

from tests.test_pilot_runtime import _route_service


def environment():
    return {"YIKE_PILOT_RESEARCH_MODE": "public-v2ex-v1",
        "YIKE_PILOT_RESEARCH_RULE_VERSION": "synthetic-v1",
        "YIKE_PILOT_RESEARCH_SOURCE_MILLI": "1000",
        "YIKE_PILOT_RESEARCH_MINUTE_MILLI": "1000",
        "YIKE_PILOT_RESEARCH_MODEL_CALL_MILLI": "1000"}


class BoundedModel:
    def assess_before(self, *args, **kwargs):
        raise AssertionError("configuration must not call model")


def test_disabled_has_no_implicit_rates_or_capability():
    from pilot.research_runtime_config import research_configuration
    assert research_configuration({}, model=None, auth_secret="short") is None


@pytest.mark.parametrize("change", [
    {"YIKE_PILOT_RESEARCH_MODE": "wrong"},
    {"YIKE_PILOT_RESEARCH_MODE": ""},
    {"YIKE_PILOT_RESEARCH_SOURCE_MILLI": ""},
    {"YIKE_PILOT_RESEARCH_SOURCE_MILLI": "-1"},
    {"YIKE_PILOT_RESEARCH_SOURCE_MILLI": "1.5"},
    {"YIKE_PILOT_RESEARCH_SOURCE_MILLI": "1000001"},
    {"YIKE_PILOT_RESEARCH_RULE_VERSION": "bad\nrule"},
])
def test_partial_or_invalid_config_fails_closed_without_values(change):
    from pilot.research_runtime_config import research_configuration
    with pytest.raises(RuntimeError, match="^invalid_research_configuration$"):
        research_configuration(environment() | change, model=BoundedModel(), auth_secret="s" * 32)


def test_requires_bounded_model_and_strong_existing_signing_secret():
    from pilot.research_runtime_config import research_configuration
    for model, secret in ((None, "s" * 32), (object(), "s" * 32), (BoundedModel(), "short")):
        with pytest.raises(RuntimeError, match="^invalid_research_configuration$"):
            research_configuration(environment(), model=model, auth_secret=secret)
    config = research_configuration(environment(), model=BoundedModel(), auth_secret="s" * 32)
    assert config.rule.ruleVersion == "synthetic-v1"
    assert len(config.signing_secret) == 32 and config.signing_secret != b"s" * 32
    assert "signing_secret" not in repr(config)


def test_scope_is_explicit_single_source_research_only():
    from pilot.research_runtime_config import public_research_policy, public_research_snapshot
    from tests.test_research_strategies_postgres import configuration
    config = configuration()
    config.update(publicSource="v2ex-latest-v1", research={"version": 1,
        "demandTypes": ["INQUIRY"], "maxSoubei": 10,
        "limits": {"sources": 10, "minutes": 10, "modelCalls": 10},
        "stopAtAnyLimit": True, "evidenceOrder": "SOURCE_MATCH_CONTEXT"})
    assert public_research_policy("PUBLIC_WEB", "PUBLIC_ANONYMOUS", config)
    assert public_research_snapshot({"platforms": ["PUBLIC_WEB"], "configuration": config})
    for platform, mode in (("BILIBILI", "PUBLIC_ANONYMOUS"), ("PUBLIC_WEB", "LOCAL_AUTHORIZED")):
        assert not public_research_policy(platform, mode, config)
    for patch in ({"publicSource": None}, {"research": None}, {"mode": "monitor"}, {"links": ["https://v2ex.com/t/1"]}):
        assert not public_research_policy("PUBLIC_WEB", "PUBLIC_ANONYMOUS", deepcopy(config) | patch)
    assert public_research_policy(
        "PUBLIC_WEB", "PUBLIC_ANONYMOUS", deepcopy(config) | {"publicSource": "v2ex-qna-v1"})
    assert not public_research_snapshot({"platforms": ["PUBLIC_WEB", "BILIBILI"], "configuration": config})


def test_runtime_assembly_preserves_ordinary_capability_and_injects_research():
    from pilot.runtime import build_runtime_app
    from pilot.foreground_collection import four_platform_public_monitor_policy
    from pilot.execution_runtime import ExecutionRuntime
    from pilot.research_runtime import ResearchRuntimeService
    from pilot.research_execution import ResearchExecutionService
    from pilot.research_quote import ResearchQuoteService
    from pilot.candidate_review import CandidateReviewStore
    database = object()
    app = build_runtime_app(database, auth_secret="s" * 32, environment=environment() |
        {"YIKE_PILOT_COLLECTION_MODE": "four-platform-public-monitor-v1",
         "YIKE_PILOT_ASSESSMENT_BASE_URL": "https://model.example/v1",
         "YIKE_PILOT_ASSESSMENT_API_KEY": "synthetic-secret",
         "YIKE_PILOT_ASSESSMENT_MODEL": "synthetic/model-v1"})
    ordinary = _route_service(app, "/api/ui/execution-operations", ExecutionRuntime)
    execution = _route_service(app, "/api/ui/research-execution/start", ResearchExecutionService)
    quotes = _route_service(app, "/api/ui/research-usage/quote", ResearchQuoteService)
    research = _route_service(app, "/api/ui/research-execution/capability", ResearchRuntimeService)
    review = _route_service(app, "/api/ui/candidate-reviews", CandidateReviewStore)
    assert ordinary.capability_check is four_platform_public_monitor_policy
    assert execution.runtime is not ordinary and execution.runtime.database is database
    assert research.execution is execution.runtime
    assert execution.quotes is quotes and research.orchestrator.reviews is review
    assert review.research_assessment.resources is research.orchestrator.sources.resources
