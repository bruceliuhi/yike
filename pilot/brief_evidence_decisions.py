"""Explain existing Pilot contact barriers without scoring or granting permission.

Call only after session, owner, profile and immutable evidence validation. These
pure projections consume existing PostgreSQL facts; they do no lookup, storage,
cross-source identity inference or external action. Each record has one primary
reason, so a missing-evidence count cannot double-count it.
"""
from __future__ import annotations

from collections.abc import Mapping


def contact_evidence_decision(
    *, source_status: str, intent_status: str, previously_contacted: bool,
    later_excluded: bool, strategy_current: bool, current_source_hash: str | None,
    captured_source_hash: str, verification: Mapping | None, has_demand_excerpt: bool,
) -> str:
    # Lifecycle facts take precedence over recoverable gaps: closed, excluded
    # and contacted records must not be marketed as new opportunities to revive.
    if later_excluded or intent_status == "CLOSED":
        return "CLOSED_OR_EXCLUDED"
    if previously_contacted or intent_status == "CONTACTED":
        return "ALREADY_CONTACTED"
    if source_status != "OPEN":
        return "SOURCE_NOT_OPEN"
    if not strategy_current:
        return "STRATEGY_NOT_CURRENT"
    if current_source_hash is None:
        return "SOURCE_VERSION_UNAVAILABLE"
    if current_source_hash != captured_source_hash:
        return "SOURCE_CHANGED"
    if not verification or verification.get("status") != "OPEN":
        return "SOURCE_NOT_REVERIFIED"
    if verification.get("contactMethod") not in {"COMMENT", "DM", "PUBLIC_CONTACT"}:
        return "CONTACT_PATH_UNVERIFIED"
    if not has_demand_excerpt:
        return "DEMAND_EVIDENCE_MISSING"
    return "ELIGIBLE"


_GAP_ACTIONS = (
    ("SOURCE_NOT_OPEN", "的当前来源状态未确认开放，需打开原文核对可访问性"),
    ("STRATEGY_NOT_CURRENT", "所用研究条件已不是当前确认版本，需按当前条件重新复核"),
    ("SOURCE_VERSION_UNAVAILABLE", "的当前原文版本无法核对，需重新读取原文并复核"),
    ("SOURCE_CHANGED", "的原文版本已变化，需重新核验需求后再决定联系"),
    ("SOURCE_NOT_REVERIFIED", "缺少当前可用的原文核验，需打开来源重新确认"),
    ("CONTACT_PATH_UNVERIFIED", "尚未确认可用的联系入口，需核实评论、私信或公开商务入口"),
    ("DEMAND_EVIDENCE_MISSING", "缺少本人表达需求的原文依据，需补齐需求证据"),
)


def evidence_gap_summary(counts: Mapping[str, int]) -> list[str]:
    """Fixed display text only; no user text or excluded/contacted totals leak in."""
    return [
        f"{counts[code]} 条已纳入记录{action}"
        for code, action in _GAP_ACTIONS
        if type(counts.get(code)) is int and 0 < counts[code] <= 1000
    ]
