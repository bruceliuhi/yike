from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pilot.outreach_contract import (
    ChannelCapability,
    DraftBinding,
    IdempotencyRegistry,
    SendReceipt,
    SourceObject,
    bind_confirmation,
    map_recipient,
)


def source() -> SourceObject:
    return SourceObject(
        schema_version="outreach-source-v1",
        source_id=str(uuid4()),
        opportunity_id=str(uuid4()),
        platform="XIAOHONGSHU",
        public_url="https://www.xiaohongshu.com/explore/abc",
        author_public_id="author-1",
        source_version=1,
    )


def capability(connection_id: str) -> ChannelCapability:
    return ChannelCapability(
        schema_version="outreach-capability-v1",
        channel="dm",
        status="AVAILABLE",
        connection_id=connection_id,
        connection_version=3,
        checked_at="2026-09-10T01:00:00Z",
        reason="当前登录会话已人工验证",
    )


def draft(source_obj: SourceObject, connection_id: str) -> DraftBinding:
    return DraftBinding(
        schema_version="outreach-draft-v1",
        draft_id=str(uuid4()),
        opportunity_id=source_obj.opportunity_id,
        source_id=source_obj.source_id,
        source_version=source_obj.source_version,
        channel="dm",
        content="您好，看到您在找方案，方便说下时间吗？",
        version=1,
        account_id=connection_id,
        connection_version=3,
        recipient_id=source_obj.author_public_id,
    )


def recipient(source_obj: SourceObject, connection_id: str):
    return {
        "schema_version": "outreach-recipient-v1",
        "source_id": source_obj.source_id,
        "opportunity_id": source_obj.opportunity_id,
        "channel": "dm",
        "recipient_id": source_obj.author_public_id,
        "recipient_label": "公开作者",
        "connection_id": connection_id,
        "connection_version": 3,
        "status": "MAPPED",
    }


def test_confirmation_snapshot_is_stable_and_idempotent():
    source_obj = source()
    connection_id = str(uuid4())
    mapping = map_recipient(source_obj, capability(connection_id), recipient(source_obj, connection_id))
    item = draft(source_obj, connection_id)
    now = datetime(2026, 9, 10, 2, tzinfo=timezone.utc)
    snapshot = bind_confirmation(
        source_obj, item, mapping, request_id=str(uuid4()),
        expires_at=now + timedelta(minutes=15), confirmed_at=now,
    )
    assert snapshot.is_valid_for(item, mapping, now + timedelta(minutes=1))
    registry = IdempotencyRegistry()
    assert registry.bind(snapshot) == registry.bind(snapshot)
    assert registry.get(snapshot.request_id) == snapshot


@pytest.mark.parametrize("field,value", [("source_version", 0), ("channel", "SMS")])
def test_source_rejects_invalid_values(field, value):
    values = source().model_dump()
    values[field] = value
    with pytest.raises(ValidationError):
        SourceObject.model_validate(values)


def test_capability_and_receipt_fail_closed():
    with pytest.raises(ValidationError):
        ChannelCapability(
            schema_version="outreach-capability-v1", channel="dm", status="AVAILABLE",
            connection_id=None, connection_version=None,
            checked_at="2026-09-10T01:00:00Z", reason="未验证",
        )
    receipt = SendReceipt(
        schema_version="outreach-send-v1", request_id=str(uuid4()), opportunity_id=str(uuid4()),
        channel="dm", version=1, status="UNKNOWN",
    )
    assert receipt.status == "UNKNOWN"
    with pytest.raises(ValidationError):
        SendReceipt(
            schema_version="outreach-send-v1", request_id=str(uuid4()), opportunity_id=str(uuid4()),
            channel="dm", version=1, status="SENT", confirmed=False,
        )


def test_changed_connection_invalidates_existing_confirmation():
    source_obj = source()
    connection_id = str(uuid4())
    mapping = map_recipient(source_obj, capability(connection_id), recipient(source_obj, connection_id))
    item = draft(source_obj, connection_id)
    now = datetime(2026, 9, 10, 2, tzinfo=timezone.utc)
    snapshot = bind_confirmation(
        source_obj, item, mapping, request_id=str(uuid4()),
        expires_at=now + timedelta(minutes=15), confirmed_at=now,
    )
    changed = item.model_copy(update={"connection_version": 4})
    assert not snapshot.is_valid_for(changed, mapping, now + timedelta(minutes=1))


def test_source_version_and_recipient_are_bound():
    source_obj = source()
    connection_id = str(uuid4())
    cap = capability(connection_id)
    bad = recipient(source_obj, connection_id)
    bad["recipient_id"] = "another-public-id"
    with pytest.raises(ValueError, match="source author"):
        map_recipient(source_obj, cap, bad)
    mapping = map_recipient(source_obj, cap, recipient(source_obj, connection_id))
    item = draft(source_obj, connection_id)
    now = datetime(2026, 9, 10, 2, tzinfo=timezone.utc)
    snapshot = bind_confirmation(
        source_obj, item, mapping, request_id=str(uuid4()),
        expires_at=now + timedelta(minutes=15), confirmed_at=now,
    )
    changed = item.model_copy(update={"source_version": 2})
    assert not snapshot.is_valid_for(changed, mapping, now + timedelta(minutes=1))


def test_confirmation_is_not_valid_before_confirmed_at():
    source_obj = source()
    connection_id = str(uuid4())
    mapping = map_recipient(source_obj, capability(connection_id), recipient(source_obj, connection_id))
    item = draft(source_obj, connection_id)
    confirmed = datetime(2026, 9, 10, 2, tzinfo=timezone.utc)
    snapshot = bind_confirmation(
        source_obj, item, mapping, request_id=str(uuid4()),
        expires_at=confirmed + timedelta(minutes=15), confirmed_at=confirmed,
    )
    assert not snapshot.is_valid_for(item, mapping, confirmed - timedelta(seconds=1))


def test_idempotency_rejects_same_request_with_changed_binding():
    source_obj = source()
    connection_id = str(uuid4())
    mapping = map_recipient(source_obj, capability(connection_id), recipient(source_obj, connection_id))
    item = draft(source_obj, connection_id)
    now = datetime(2026, 9, 10, 2, tzinfo=timezone.utc)
    request_id = str(uuid4())
    first = bind_confirmation(
        source_obj, item, mapping, request_id=request_id,
        expires_at=now + timedelta(minutes=15), confirmed_at=now,
    )
    changed = item.model_copy(update={"version": 2})
    second = bind_confirmation(
        source_obj, changed, mapping, request_id=request_id,
        expires_at=now + timedelta(minutes=15), confirmed_at=now,
    )
    registry = IdempotencyRegistry()
    registry.bind(first)
    with pytest.raises(ValueError, match="request_id binding conflict"):
        registry.bind(second)
