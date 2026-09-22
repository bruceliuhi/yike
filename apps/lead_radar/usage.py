"""Usage and source-result charging rules for Lead Radar.

This module deliberately defines a small, auditable resource unit rather than a
price.  One SOUBEI is the current internal unit for a newly accepted source
result.  Duplicates, empty searches and failed source calls have a zero charge;
the result of each attempt is still written to the usage ledger.
"""

from __future__ import annotations

from typing import Any


RULE_VERSION = "source-result-v1"
UNIT = "SOUBEI"
DISPLAY_UNIT = "搜贝"

ACTION_COSTS: dict[str, int] = {
    "create_search_task": 1,
    "enrich_entity": 1,
    "get_research_brief": 0,
    "create_monitor_schedule": 1,
    "get_search_status": 0,
    "fetch_search_results": 0,
    "get_feed": 0,
    "get_feed_event": 0,
    "review_feed_event": 0,
    "export_opportunities": 0,
}

OUTCOMES = {"SUCCESS", "DUPLICATE", "NO_RESULT", "FAILED"}

# Keep the rule explicit and source agnostic.  A future provider may override
# this table only after its tariff is approved and versioned.
SOURCE_RESULT_COSTS: dict[str, dict[str, int]] = {
    "authorized_search_api": {"SUCCESS": 1, "DUPLICATE": 0, "NO_RESULT": 0, "FAILED": 0},
    "search_index_import": {"SUCCESS": 1, "DUPLICATE": 0, "NO_RESULT": 0, "FAILED": 0},
    "public_url_capture": {"SUCCESS": 1, "DUPLICATE": 0, "NO_RESULT": 0, "FAILED": 0},
    "public_url_batch_capture": {"SUCCESS": 1, "DUPLICATE": 0, "NO_RESULT": 0, "FAILED": 0},
    "public_url_reopen": {"SUCCESS": 1, "DUPLICATE": 0, "NO_RESULT": 0, "FAILED": 0},
    # Source IDs used by the planner.  They are quoted here even while blocked
    # so a plan can show the same rule before a connector is enabled.
    "public_web": {"SUCCESS": 1, "DUPLICATE": 0, "NO_RESULT": 0, "FAILED": 0},
    "xiaohongshu_public": {"SUCCESS": 1, "DUPLICATE": 0, "NO_RESULT": 0, "FAILED": 0},
    "douyin_public": {"SUCCESS": 1, "DUPLICATE": 0, "NO_RESULT": 0, "FAILED": 0},
    "bilibili_public": {"SUCCESS": 1, "DUPLICATE": 0, "NO_RESULT": 0, "FAILED": 0},
    "zhihu_public": {"SUCCESS": 1, "DUPLICATE": 0, "NO_RESULT": 0, "FAILED": 0},
    "manual_public_evidence": {"SUCCESS": 1, "DUPLICATE": 0, "NO_RESULT": 0, "FAILED": 0},
    "feishu_authorized": {"SUCCESS": 1, "DUPLICATE": 0, "NO_RESULT": 0, "FAILED": 0},
    "crm_authorized": {"SUCCESS": 1, "DUPLICATE": 0, "NO_RESULT": 0, "FAILED": 0},
}


def charge_for(operation: str, outcome: str, units: int = 1) -> int:
    """Return the charge for a single ledger entry.

    ``units`` is normally one per source result.  It is set to zero for a
    no-result or failed attempt.  Rejecting unknown outcomes prevents a caller
    from silently turning an unclassified state into a billable result.
    """

    normalized = str(outcome or "").upper()
    if normalized not in OUTCOMES:
        raise ValueError("usage_outcome_invalid")
    bounded_units = max(0, int(units))
    if operation not in SOURCE_RESULT_COSTS:
        raise ValueError("usage_operation_invalid")
    rate = SOURCE_RESULT_COSTS[operation]
    return rate[normalized] * bounded_units


def cost_estimate(source_id: str, maximum_results: int) -> dict[str, Any]:
    """Return a customer-readable source quote without reserving usage."""

    maximum = max(0, int(maximum_results))
    if source_id not in SOURCE_RESULT_COSTS:
        # An unregistered source may still be shown in a blocked plan, but it
        # must never receive a made-up tariff or a billable estimate.
        return {
            "source_id": source_id,
            "unit": UNIT,
            "display_unit": DISPLAY_UNIT,
            "rule_version": RULE_VERSION,
            "per_success": None,
            "per_duplicate": None,
            "per_no_result": None,
            "per_failure": None,
            "maximum_results": maximum,
            "maximum_credits": None,
            "settlement": "UNKNOWN",
            "reason": "来源尚未登记计量规则，不估算也不扣费。",
        }
    return {
        "source_id": source_id,
        "unit": UNIT,
        "display_unit": DISPLAY_UNIT,
        "rule_version": RULE_VERSION,
        "per_success": charge_for(source_id, "SUCCESS"),
        "per_duplicate": charge_for(source_id, "DUPLICATE"),
        "per_no_result": charge_for(source_id, "NO_RESULT"),
        "per_failure": charge_for(source_id, "FAILED"),
        "maximum_results": maximum,
        "maximum_credits": charge_for(source_id, "SUCCESS", maximum),
        "settlement": "NOT_STARTED",
    }


def source_metadata(source_id: str, outcome: str, **extra: Any) -> dict[str, Any]:
    metadata = {
        "source_id": source_id,
        "outcome": str(outcome).upper(),
        "rule_version": RULE_VERSION,
        "unit": UNIT,
    }
    metadata.update(extra)
    return metadata


def action_cost(action: str) -> int:
    if action not in ACTION_COSTS:
        raise ValueError("usage_action_invalid")
    return ACTION_COSTS[action]
