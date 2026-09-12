"""Explicit single-source research configuration; no default pricing or enablement."""
from dataclasses import dataclass, field
import hashlib
import hmac
import re

from pydantic import ValidationError

from pilot.dynamic_research_config import dynamic_agent_configuration
from pilot.research_quote import ResearchQuoteRule
from pilot.research_strategy_contract import ResearchStrategyConfiguration
from pilot.research_source_catalog import SOURCE_IDS


_NAMES = ("MODE", "RULE_VERSION", "SOURCE_MILLI", "MINUTE_MILLI", "MODEL_CALL_MILLI")
_AGENT_NAMES = ("CODEX_BINARY", "PYTHON_BINARY", "API_KEY", "MODEL", "SEARCH_API_KEY")


@dataclass(frozen=True)
class ResearchConfiguration:
    rule: ResearchQuoteRule
    signing_secret: bytes = field(repr=False)
    dynamic_agent: object | None = field(default=None, repr=False)


def research_configuration(environment, *, model, auth_secret):
    values = [environment.get("YIKE_PILOT_RESEARCH_" + name, "") for name in _NAMES]
    agent_values = tuple(environment.get("YIKE_PILOT_RESEARCH_AGENT_" + name, "")
                         for name in _AGENT_NAMES)
    try:
        agent = dynamic_agent_configuration(agent_values)
    except (TypeError, ValueError):
        raise RuntimeError("invalid_research_configuration") from None
    if not any(value.strip() for value in values) and agent is None:
        return None
    dynamic = values[0] == "public-web-agent-v1"
    valid = (values[0] in ("public-v2ex-v1", "public-web-agent-v1")
        and (not dynamic or agent is not None)
        and isinstance(auth_secret, str) and len(auth_secret.encode()) >= 32
        and callable(getattr(model, "assess_before", None))
        and all(re.fullmatch(r"[1-9][0-9]{0,6}", value) for value in values[2:]))
    if valid:
        try:
            rule = ResearchQuoteRule(values[1], *(int(value) for value in values[2:]))
        except ValueError:
            valid = False
    if not valid:
        raise RuntimeError("invalid_research_configuration")
    # Independent signing domain; auth-key rotation intentionally invalidates unused quotes.
    secret = hmac.new(auth_secret.encode(), b"yike:research-quote-signing:v1", hashlib.sha256).digest()
    return ResearchConfiguration(rule, secret, agent if dynamic else None)


def public_research_policy(platform, access_mode, configuration):
    if platform != "PUBLIC_WEB" or access_mode != "PUBLIC_ANONYMOUS":
        return False
    try:
        parsed = ResearchStrategyConfiguration.model_validate(configuration)
    except (ValidationError, TypeError, ValueError, RecursionError):
        return False
    return (parsed.publicSource in SOURCE_IDS and parsed.source == "search"
        and parsed.mode == "once" and parsed.schedule is None and parsed.research is not None
        and not parsed.links and bool(parsed.keywords)
        and all(term == term.strip() and "," not in term for term in parsed.keywords))


def public_research_snapshot(snapshot):
    valid = (type(snapshot) is dict and snapshot.get("platforms") == ["PUBLIC_WEB"]
        and public_research_policy("PUBLIC_WEB", "PUBLIC_ANONYMOUS", snapshot.get("configuration")))
    if valid and (plan := snapshot['configuration']['research'].get('sourcePlan')):
        total = snapshot.get('max_records')
        return type(total) is int and len(plan['sources']) <= total <= 100
    return valid


def dynamic_research_policy(platform, access_mode, configuration):
    if platform != "PUBLIC_WEB" or access_mode != "PUBLIC_ANONYMOUS":
        return False
    try:
        parsed = ResearchStrategyConfiguration.model_validate(configuration)
    except (ValidationError, TypeError, ValueError, RecursionError):
        return False
    research = parsed.research
    if (parsed.publicSource != "public-web-agent-v1" or parsed.source != "search"
            or parsed.mode != "once" or parsed.schedule is not None or parsed.links
            or research is None or research.dynamicScope is None
            or research.provenance is not None or research.sourcePlan is not None
            or parsed.platformQueries is not None or not parsed.keywords):
        return False
    limits = research.limits
    return (2 <= limits.sources <= 100 and 2 <= limits.modelCalls <= 20
            and 1 <= limits.minutes <= 30
            and all(term == term.strip() and "," not in term for term in parsed.keywords))


def dynamic_research_snapshot(snapshot):
    return (type(snapshot) is dict
        and snapshot.get("platforms") == ["PUBLIC_WEB"]
        and dynamic_research_policy(
            "PUBLIC_WEB", "PUBLIC_ANONYMOUS", snapshot.get("configuration")
        )
        and type(snapshot.get("max_records")) is int
        and 1 <= snapshot["max_records"] <= 100
        and type(snapshot.get("max_runtime_seconds")) is int
        and 1 <= snapshot["max_runtime_seconds"] <= 1800)


def configured_research_policy(dynamic_enabled):
    def policy(platform, access_mode, configuration):
        return (public_research_policy(platform, access_mode, configuration)
                or dynamic_enabled is True
                and dynamic_research_policy(platform, access_mode, configuration))
    return policy


def configured_research_snapshot(dynamic_enabled):
    def snapshot(value):
        return (public_research_snapshot(value)
                or dynamic_enabled is True and dynamic_research_snapshot(value))
    return snapshot
