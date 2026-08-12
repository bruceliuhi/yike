from typing import Any, Mapping

from app.normalizer import (
    PlatformResponseChanged,
    normalize_time,
    optional_text,
    raw_sha256,
    require_text,
    sha256_text,
)
from app.repository import NormalizedSignal


def normalize_douyin(record: Mapping[str, Any]) -> NormalizedSignal:
    content = record.get("content") or {}
    comment = record.get("comment") or record
    if not isinstance(content, Mapping) or not isinstance(comment, Mapping):
        raise PlatformResponseChanged(
            "PLATFORM_RESPONSE_CHANGED: invalid Douyin envelope"
        )

    aweme_id = require_text(content, "aweme_id")
    source_url = f"https://www.douyin.com/video/{aweme_id}"
    comment_id = require_text(comment, "comment_id", "cid")
    body = require_text(comment, "content", "text", "body")
    comment_url = optional_text(comment, "comment_url", "url")
    if not comment_url:
        comment_url = source_url

    return NormalizedSignal(
        platform="dy",
        external_source_id=aweme_id,
        source_title=require_text(content, "title", "desc"),
        source_url=source_url,
        source_author_public_id=require_text(
            content, "creator_hash", "user_id", "sec_uid", "uid"
        ),
        external_comment_id=comment_id,
        parent_comment_id=optional_text(comment, "parent_comment_id", "reply_id"),
        parent_body=optional_text(comment, "parent_content", "parent_body"),
        comment_url=comment_url,
        author_public_id=require_text(
            comment, "creator_hash", "user_id", "sec_uid", "uid"
        ),
        body=body,
        body_sha256=sha256_text(body),
        published_at=normalize_time(comment.get("create_time") or comment.get("published_at")),
        collected_at=normalize_time(comment.get("collected_at")),
        raw_sha256=raw_sha256(comment),
        normalizer_version="dy-v1",
    )
