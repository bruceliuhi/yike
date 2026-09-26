"""Qualification explanations preserve the existing brief's contact gate."""
from copy import deepcopy

import pytest

from pilot.brief_evidence_decisions import contact_evidence_decision, evidence_gap_summary


def ready_facts():
    return {
        "source_status": "OPEN", "intent_status": "NEW", "previously_contacted": False,
        "later_excluded": False, "strategy_current": True,
        "current_source_hash": "a" * 64, "captured_source_hash": "a" * 64,
        "verification": {"status": "OPEN", "contactMethod": "COMMENT"},
        "has_demand_excerpt": True,
    }


@pytest.mark.parametrize(("change", "expected"), [
    ({}, "ELIGIBLE"),
    ({"source_status": "UNKNOWN"}, "SOURCE_NOT_OPEN"),
    ({"intent_status": "CLOSED"}, "CLOSED_OR_EXCLUDED"),
    ({"later_excluded": True}, "CLOSED_OR_EXCLUDED"),
    ({"intent_status": "CONTACTED"}, "ALREADY_CONTACTED"),
    ({"previously_contacted": True}, "ALREADY_CONTACTED"),
    ({"strategy_current": False}, "STRATEGY_NOT_CURRENT"),
    ({"current_source_hash": "b" * 64}, "SOURCE_CHANGED"),
    ({"current_source_hash": None}, "SOURCE_VERSION_UNAVAILABLE"),
    ({"verification": None}, "SOURCE_NOT_REVERIFIED"),
    ({"verification": {"status": "BLOCKED", "contactMethod": "COMMENT"}}, "SOURCE_NOT_REVERIFIED"),
    ({"verification": {"status": "OPEN", "contactMethod": "NONE"}}, "CONTACT_PATH_UNVERIFIED"),
    ({"has_demand_excerpt": False}, "DEMAND_EVIDENCE_MISSING"),
])
def test_each_existing_contact_barrier_has_one_reason(change, expected):
    facts = ready_facts() | change
    before = deepcopy(facts)
    assert contact_evidence_decision(**facts) == expected
    assert facts == before


@pytest.mark.parametrize("method", ["COMMENT", "DM", "PUBLIC_CONTACT"])
def test_only_existing_contact_channels_remain_eligible(method):
    facts = ready_facts()
    facts["verification"]["contactMethod"] = method
    assert contact_evidence_decision(**facts) == "ELIGIBLE"


def test_retired_or_contacted_records_do_not_become_evidence_gap_counts():
    blocked = ready_facts() | {"strategy_current": False, "has_demand_excerpt": False}
    codes = [
        contact_evidence_decision(**(blocked | {"later_excluded": True})),
        contact_evidence_decision(**(blocked | {"intent_status": "CLOSED"})),
        contact_evidence_decision(**(blocked | {"previously_contacted": True})),
    ]
    assert evidence_gap_summary({code: 1 for code in codes}) == []


def test_gap_summary_is_bounded_counts_and_fixed_actions_without_private_text():
    summary = evidence_gap_summary({
        "SOURCE_CHANGED": 2, "DEMAND_EVIDENCE_MISSING": 1,
        "ELIGIBLE": 4, "ALREADY_CONTACTED": 9, "PRIVATE-NOTE": 11,
    })
    assert summary == [
        "2 条已纳入记录的原文版本已变化，需重新核验需求后再决定联系",
        "1 条已纳入记录缺少本人表达需求的原文依据，需补齐需求证据",
    ]
    assert "PRIVATE-NOTE" not in str(summary)
    assert evidence_gap_summary({"SOURCE_CHANGED": 0}) == []
