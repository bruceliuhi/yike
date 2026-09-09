from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from pilot.outreach_contract import ChannelCapability, DraftBinding, SourceObject, bind_confirmation, map_recipient
from pilot.outreach_store import OutreachStoreError, decode_snapshot, snapshot_record


def objects():
    source = SourceObject(
        schema_version="outreach-source-v1", source_id=str(uuid4()), opportunity_id=str(uuid4()),
        platform="XIAOHONGSHU", public_url="https://www.xiaohongshu.com/explore/abc",
        author_public_id="author-public-id", source_version=2,
    )
    account = str(uuid4())
    capability = ChannelCapability(
        schema_version="outreach-capability-v1", channel="dm", status="AVAILABLE",
        connection_id=account, connection_version=4, checked_at="2026-09-10T01:00:00Z", reason="人工验证",
    )
    mapping = map_recipient(source, capability, {
        "schema_version": "outreach-recipient-v1", "source_id": source.source_id,
        "opportunity_id": source.opportunity_id, "channel": "dm", "recipient_id": source.author_public_id,
        "recipient_label": "公开作者", "connection_id": account, "connection_version": 4, "status": "MAPPED",
    })
    draft = DraftBinding(
        schema_version="outreach-draft-v1", draft_id=str(uuid4()), opportunity_id=source.opportunity_id,
        source_id=source.source_id, source_version=source.source_version, channel="dm",
        content="您好，方便沟通一下需求吗？", version=1, account_id=account, connection_version=4,
        recipient_id=source.author_public_id,
    )
    now = datetime(2026, 9, 10, 2, tzinfo=timezone.utc)
    return bind_confirmation(source, draft, mapping, request_id=str(uuid4()), expires_at=now + timedelta(minutes=10), confirmed_at=now)


def test_snapshot_record_does_not_persist_plaintext_body():
    snapshot = objects()
    record = snapshot_record(snapshot)
    assert record["content_sha256"] == snapshot.content_sha256
    assert "您好，方便沟通一下需求吗？" not in str(record)
    assert decode_snapshot(record["snapshot"], record["snapshot_sha256"]) == snapshot


def test_decode_snapshot_rejects_tampering():
    snapshot = objects()
    record = snapshot_record(snapshot)
    tampered = dict(record["snapshot"], connection_version=999)
    with pytest.raises(OutreachStoreError, match="stored_snapshot_invalid"):
        decode_snapshot(tampered, record["snapshot_sha256"])
