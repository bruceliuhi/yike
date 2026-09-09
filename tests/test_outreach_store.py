from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from pilot.outreach_contract import ChannelCapability, DraftBinding, SourceObject, bind_confirmation, map_recipient
from pilot.outreach_store import OutreachConfirmationStore, OutreachStoreError, decode_snapshot, snapshot_record


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


class Cursor:
    def __init__(self, rows):
        self.rows = iter(rows)

    def execute(self, *_args):
        return None

    def fetchone(self):
        return next(self.rows)


def test_authoritative_facts_must_match_current_open_source_and_connection():
    snapshot = objects()
    # The helper only needs the same source/draft/mapping objects used to make it.
    from pilot.outreach_contract import ChannelCapability, DraftBinding, map_recipient
    source = SourceObject(
        schema_version="outreach-source-v1", source_id=snapshot.source_id,
        opportunity_id=snapshot.opportunity_id, platform="XIAOHONGSHU",
        public_url="https://www.xiaohongshu.com/explore/abc", author_public_id=snapshot.recipient_id,
        source_version=snapshot.source_version,
    )
    mapping = map_recipient(source, ChannelCapability(
        schema_version="outreach-capability-v1", channel="dm", status="AVAILABLE",
        connection_id=snapshot.account_id, connection_version=snapshot.connection_version,
        checked_at="2026-09-10T01:00:00Z", reason="人工验证",
    ), {
        "schema_version": "outreach-recipient-v1", "source_id": source.source_id,
        "opportunity_id": source.opportunity_id, "channel": "dm", "recipient_id": source.author_public_id,
        "recipient_label": "公开作者", "connection_id": snapshot.account_id,
        "connection_version": snapshot.connection_version, "status": "MAPPED",
    })
    draft = DraftBinding(
        schema_version="outreach-draft-v1", draft_id=str(uuid4()), opportunity_id=source.opportunity_id,
        source_id=source.source_id, source_version=source.source_version, channel="dm", content="x",
        version=snapshot.version, account_id=snapshot.account_id,
        connection_version=snapshot.connection_version, recipient_id=source.author_public_id,
    )
    cursor = Cursor([
        ("XIAOHONGSHU", source.public_url, "UNVERIFIED"),
        (source.source_id, "OPEN"),
        ("XIAOHONGSHU", "CONNECTED", snapshot.connection_version),
    ])
    OutreachConfirmationStore._assert_authoritative_facts(cursor, "tenant-1", source, draft, mapping)

    blocked = Cursor([
        ("XIAOHONGSHU", source.public_url, "BLOCKED"),
    ])
    with pytest.raises(OutreachStoreError, match="source_facts_unavailable"):
        OutreachConfirmationStore._assert_authoritative_facts(blocked, "tenant-1", source, draft, mapping)
