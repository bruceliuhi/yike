from uuid import uuid4

import pytest

from pilot.reply_contract import PlatformReplyEvent
from pilot.reply_store import ReplyStoreError, decode_event, event_digest, event_record


def event():
    ids = {name: str(uuid4()) for name in (
        "tenant_id", "user_id", "opportunity_id", "source_id", "outreach_request_id", "profile_version_id"
    )}
    return PlatformReplyEvent(
        schema_version="reply-event-v1", event_id=str(uuid4()), **ids,
        kind="PLATFORM_REPLY", state="ACTIVE", platform="XIAOHONGSHU", channel="dm",
        external_reply_id="reply-1", sender_public_id="author-1", body="请问周期和费用？",
        received_at="2026-09-10T02:00:00Z", observed_at="2026-09-10T02:01:00Z",
        read_state="UNREAD", read_at=None,
    )


def test_event_record_round_trips_without_losing_scope():
    value = event()
    record = event_record(value)
    assert record["payload_sha256"] == event_digest(value)
    assert decode_event(record["payload"], record["payload_sha256"]) == value
    assert record["body"] == value.body


def test_decode_event_rejects_tampered_digest():
    value = event()
    record = event_record(value)
    with pytest.raises(ReplyStoreError, match="stored_event_invalid"):
        decode_event(record["payload"], "0" * 64)
