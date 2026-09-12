"""Pure configuration boundaries for the opt-in dynamic research worker."""
from pathlib import Path
import sys

import pytest


class BoundedModel:
    def assess_before(self, *_args, **_kwargs):
        raise AssertionError("configuration must not call the assessment provider")


def base_environment(mode="public-web-agent-v1"):
    return {
        "YIKE_PILOT_RESEARCH_MODE": mode,
        "YIKE_PILOT_RESEARCH_RULE_VERSION": "synthetic-v1",
        "YIKE_PILOT_RESEARCH_SOURCE_MILLI": "1000",
        "YIKE_PILOT_RESEARCH_MINUTE_MILLI": "1000",
        "YIKE_PILOT_RESEARCH_MODEL_CALL_MILLI": "1000",
    }


def agent_environment():
    shell = "/bin/sh"
    assert Path(shell).is_file() and Path(sys.executable).is_file()
    return {
        "YIKE_PILOT_RESEARCH_AGENT_CODEX_BINARY": shell,
        "YIKE_PILOT_RESEARCH_AGENT_PYTHON_BINARY": sys.executable,
        "YIKE_PILOT_RESEARCH_AGENT_API_KEY": "synthetic-provider-key",
        "YIKE_PILOT_RESEARCH_AGENT_MODEL": "synthetic/model-v1",
        "YIKE_PILOT_RESEARCH_AGENT_SEARCH_API_KEY": "synthetic-search-key",
    }


def test_fixed_mode_remains_accepted_without_agent_configuration():
    from pilot.research_runtime_config import research_configuration

    config = research_configuration(
        base_environment("public-v2ex-v1"),
        model=BoundedModel(),
        auth_secret="s" * 32,
    )
    assert config.dynamic_agent is None
    assert config.rule.ruleVersion == "synthetic-v1"


def test_dynamic_mode_requires_and_freezes_all_server_owned_agent_values():
    from pilot.research_runtime_config import research_configuration

    config = research_configuration(
        base_environment() | agent_environment(),
        model=BoundedModel(),
        auth_secret="s" * 32,
    )
    agent = config.dynamic_agent
    assert agent is not None
    assert agent.codex_binary == "/bin/sh"
    assert agent.python_binary == sys.executable
    assert agent.model == "synthetic/model-v1"
    rendered = repr(config) + repr(agent)
    assert "synthetic-provider-key" not in rendered
    assert "synthetic-search-key" not in rendered


@pytest.mark.parametrize("missing", [
    "YIKE_PILOT_RESEARCH_AGENT_CODEX_BINARY",
    "YIKE_PILOT_RESEARCH_AGENT_PYTHON_BINARY",
    "YIKE_PILOT_RESEARCH_AGENT_API_KEY",
    "YIKE_PILOT_RESEARCH_AGENT_MODEL",
    "YIKE_PILOT_RESEARCH_AGENT_SEARCH_API_KEY",
])
def test_agent_configuration_is_all_or_none_and_dynamic_fails_closed(missing):
    from pilot.research_runtime_config import research_configuration

    environment = base_environment() | agent_environment()
    environment[missing] = ""
    with pytest.raises(RuntimeError, match="^invalid_research_configuration$"):
        research_configuration(environment, model=BoundedModel(), auth_secret="s" * 32)


@pytest.mark.parametrize("patch", [
    {"YIKE_PILOT_RESEARCH_AGENT_CODEX_BINARY": "relative/codex"},
    {"YIKE_PILOT_RESEARCH_AGENT_PYTHON_BINARY": "/missing/python"},
    {"YIKE_PILOT_RESEARCH_AGENT_API_KEY": "has whitespace"},
    {"YIKE_PILOT_RESEARCH_AGENT_MODEL": ""},
])
def test_dynamic_agent_rejects_paths_and_values_the_worker_cannot_use(patch):
    from pilot.research_runtime_config import research_configuration

    with pytest.raises(RuntimeError, match="^invalid_research_configuration$"):
        research_configuration(
            base_environment() | agent_environment() | patch,
            model=BoundedModel(),
            auth_secret="s" * 32,
        )


def dynamic_configuration(*, sources=20, minutes=15, model_calls=20):
    from tests.test_research_strategies_postgres import configuration

    return configuration(
        publicSource="public-web-agent-v1",
        research={
            "version": 1,
            "demandTypes": ["INQUIRY"],
            "maxSoubei": 10,
            "limits": {
                "sources": sources,
                "minutes": minutes,
                "modelCalls": model_calls,
            },
            "stopAtAnyLimit": True,
            "evidenceOrder": "SOURCE_MATCH_CONTEXT",
            "dynamicScope": {
                "version": 1,
                "maxAgeDays": 60,
                "timezone": "Asia/Shanghai",
            },
        },
    )


def test_dynamic_policy_is_separate_and_enforces_confirmed_ceiling_bounds():
    from pilot.research_runtime_config import (
        dynamic_research_policy,
        dynamic_research_snapshot,
        public_research_policy,
    )

    configuration = dynamic_configuration()
    assert dynamic_research_policy("PUBLIC_WEB", "PUBLIC_ANONYMOUS", configuration)
    assert not public_research_policy("PUBLIC_WEB", "PUBLIC_ANONYMOUS", configuration)
    assert dynamic_research_snapshot({
        "platforms": ["PUBLIC_WEB"],
        "configuration": configuration,
        "max_records": 100,
        "max_runtime_seconds": 1800,
    })
    for limits in ((1, 15, 20), (101, 15, 20), (20, 0, 20),
                   (20, 31, 20), (20, 15, 1), (20, 15, 21)):
        value = dynamic_configuration(
            sources=limits[0], minutes=limits[1], model_calls=limits[2]
        )
        assert not dynamic_research_policy("PUBLIC_WEB", "PUBLIC_ANONYMOUS", value)
    for patch in ({"max_records": 0}, {"max_records": 101},
                  {"max_runtime_seconds": 0}, {"max_runtime_seconds": 1801}):
        snapshot = {
            "platforms": ["PUBLIC_WEB"],
            "configuration": configuration,
            "max_records": 20,
            "max_runtime_seconds": 900,
        } | patch
        assert not dynamic_research_snapshot(snapshot)
