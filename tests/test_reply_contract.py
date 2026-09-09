from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pilot.reply_contract import (
    ManualFollowupEvent,
    PlatformReplyEvent,
    ReplyEventRegistry,
    mark_read,
    parse_reply_event,
    transition_state,
)


def ids():
    return {name: str(uuid4()) for name in (
        "tenant_id", "user_id", "opportunity_id", "source_id",
        "outreach_request_id", "profile_version_id",
    )}


def platform_event(**changes):
    value = {
        "schema_version": "reply-event-v1",
        "event_id": str(uuid4()),
        **ids(),
        "kind": "PLATFORM_REPLY",
        "state": "ACTIVE",
        "platform": "XIAOHONGSHU",
        "channel": "dm",
        "external_reply_id": "reply-123",
        "sender_public_id": "author-1",
        "body": "想了解一下实施周期和大概费用。",
        "received_at": "2026-09-10T02:00:00Z",
        "observed_at": "2026-09-10T02:01:00Z",
        "read_state": "UNREAD",
        "read_at": None,
    }
    value.update(changes)
    return PlatformReplyEvent.model_validate(value)


def manual_event(**changes):
    value = {
        "schema_version": "reply-event-v1",
        "event_id": str(uuid4()),
        **ids(),
        "kind": "MANUAL_FOLLOWUP",
        "state": "ACTIVE",
        "action": "CONTACTED",
        "note": "人工电话沟通，约定补充需求信息。",
        "occurred_at": "2026-09-10T02:00:00Z",
        "observed_at": "2026-09-10T02:01:00Z",
    }
    value.update(changes)
    return ManualFollowupEvent.model_validate(value)


def test_platform_reply_is_bound_to_all_scope_and_outreach_ids():
    event = platform_event()
    assert event.tenant_id and event.user_id and event.opportunity_id
    assert event.source_id and event.outreach_request_id
    assert parse_reply_event(event.model_dump()) == event


def test_manual_fact_is_not_a_platform_reply_and_does_not_carry_channel_fields():
    event = manual_event()
    assert event.kind == "MANUAL_FOLLOWUP"
    with pytest.raises(ValidationError):
        manual_event(platform="XIAOHONGSHU")
    with pytest.raises(ValueError, match="platform reply"):
        mark_read(event, read_at=datetime(2026, 9, 10, 2, tzinfo=timezone.utc))


def test_unknown_read_state_is_preserved_and_cannot_be_marked_read_without_fact():
    event = platform_event(read_state="UNKNOWN", read_at=None)
    with pytest.raises(ValueError, match="unknown"):
        mark_read(event, read_at=datetime(2026, 9, 10, 2, tzinfo=timezone.utc))


def test_mark_read_requires_unread_and_produces_new_observed_fact():
    event = platform_event()
    updated = mark_read(
        event,
        read_at=datetime(2026, 9, 10, 2, 2, tzinfo=timezone.utc),
        observed_at=datetime(2026, 9, 10, 2, 3, tzinfo=timezone.utc),
    )
    assert updated.event_id == event.event_id
    assert updated.read_state == "READ"
    assert updated.read_at == "2026-09-10T02:02:00Z"
    with pytest.raises(ValueError, match="UNREAD"):
        mark_read(updated, read_at=datetime(2026, 9, 10, 2, 4, tzinfo=timezone.utc))


def test_state_transitions_are_forward_only_and_keep_scope():
    active = manual_event()
    corrected = manual_event(
        **{**active.model_dump(), "event_id": str(uuid4()), "state": "CORRECTED",
           "corrects_event_id": active.event_id, "reason": "原备注遗漏了会议时间。"}
    )
    assert transition_state(active, corrected) == corrected
    voided = manual_event(
        **{**active.model_dump(), "event_id": str(uuid4()), "state": "VOID",
           "corrects_event_id": active.event_id, "reason": "误记。"}
    )
    assert transition_state(active, voided) == voided
    with pytest.raises(ValueError, match="forward"):
        transition_state(corrected, active)
    with pytest.raises(ValueError, match="scope"):
        transition_state(active, manual_event(
            **{**active.model_dump(), "event_id": str(uuid4()), "state": "CORRECTED",
               "corrects_event_id": active.event_id, "reason": "范围不一致。", "tenant_id": str(uuid4())}
        ))


def test_state_transition_cannot_change_manual_fact_into_platform_fact():
    active = manual_event()
    platform = platform_event(
        tenant_id=active.tenant_id,
        user_id=active.user_id,
        opportunity_id=active.opportunity_id,
        source_id=active.source_id,
        outreach_request_id=active.outreach_request_id,
        profile_version_id=active.profile_version_id,
        state="CORRECTED",
        corrects_event_id=active.event_id,
        reason="事实类型不能改变。",
    )
    with pytest.raises(ValueError, match="scope"):
        transition_state(active, platform)


def test_registry_deduplicates_platform_facts_per_tenant_and_rejects_conflicts():
    registry = ReplyEventRegistry()
    first = platform_event()
    assert registry.record(first) == first
    assert registry.record(first.model_copy(update={"event_id": str(uuid4())})) == first
    with pytest.raises(ValueError, match="duplicate"):
        registry.record(first.model_copy(update={"body": "不同事实"}))
    with pytest.raises(ValueError, match="duplicate"):
        registry.record(first.model_copy(update={"opportunity_id": str(uuid4())}))
    other_tenant = platform_event(tenant_id=str(uuid4()), event_id=str(uuid4()))
    assert registry.record(other_tenant) == other_tenant


def test_registry_rejects_duplicate_observation_with_changed_read_fact():
    registry = ReplyEventRegistry()
    first = platform_event()
    registry.record(first)
    changed = first.model_copy(update={"read_state": "UNKNOWN", "read_at": None})
    with pytest.raises(ValueError, match="duplicate"):
        registry.record(changed)


@pytest.mark.parametrize(
    "changes",
    [
        {"tenant_id": "not-a-uuid"},
        {"body": "\x00bad"},
        {"read_state": "READ"},
        {"received_at": "2026-09-10T02:00:00"},
        {"__extra": True},
    ],
)
def test_strict_validation_rejects_malformed_or_unproven_facts(changes):
    with pytest.raises((ValidationError, ValueError)):
        platform_event(**changes)


def test_manual_event_rejects_future_occurrence():
    with pytest.raises(ValidationError, match="future"):
        manual_event(occurred_at="2099-01-01T00:00:00Z")
