"""Explicit single-source research configuration; no default pricing or enablement."""
from dataclasses import dataclass, field
import hashlib
import hmac
import re

from pydantic import ValidationError

from pilot.research_quote import ResearchQuoteRule
from pilot.research_strategy_contract import ResearchStrategyConfiguration
from pilot.research_source_catalog import SOURCE_IDS


_NAMES = ("MODE", "RULE_VERSION", "SOURCE_MILLI", "MINUTE_MILLI", "MODEL_CALL_MILLI")


@dataclass(frozen=True)
class ResearchConfiguration:
    rule: ResearchQuoteRule
    signing_secret: bytes = field(repr=False)


def research_configuration(environment, *, model, auth_secret):
    values = [environment.get("YIKE_PILOT_RESEARCH_" + name, "") for name in _NAMES]
    if not any(value.strip() for value in values):
        return None
    valid = (values[0] == "public-v2ex-v1" and callable(getattr(model, "assess_before", None))
        and isinstance(auth_secret, str) and len(auth_secret.encode()) >= 32
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
    return ResearchConfiguration(rule, secret)


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
