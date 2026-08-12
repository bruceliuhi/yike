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


def normalize_bilibili(record: Mapping[str, Any]) -> NormalizedSignal:
    content = record.get("content") or {}
    comment = record.get("comment") or record
    if not isinstance(content, Mapping) or not isinstance(comment, Mapping):
        raise PlatformResponseChanged(
            "PLATFORM_RESPONSE_CHANGED: invalid Bilibili envelope"
        )

    source_id = require_text(content, "video_id", "aid")
    bvid = optional_text(content, "bvid")
    source_url = (
        f"https://www.bilibili.com/video/{bvid}"
        if bvid
        else f"https://www.bilibili.com/video/av{source_id.removeprefix('av')}"
    )
    comment_id = require_text(comment, "comment_id", "rpid")
    body = require_text(comment, "content", "body")
    comment_url = optional_text(comment, "comment_url", "url")
    if not comment_url:
        comment_url = f"{source_url}#reply{comment_id}"

    return NormalizedSignal(
        platform="bili",
        external_source_id=source_id,
        source_title=require_text(content, "title", "desc"),
        source_url=source_url,
        source_author_public_id=require_text(
            content, "creator_hash", "user_id", "mid"
        ),
        external_comment_id=comment_id,
        parent_comment_id=optional_text(comment, "parent_comment_id", "parent_id"),
        parent_body=optional_text(comment, "parent_content", "parent_body"),
        comment_url=comment_url,
        author_public_id=require_text(comment, "creator_hash", "user_id", "mid"),
        body=body,
        body_sha256=sha256_text(body),
        source_published_at=normalize_time(
            content.get("create_time") or content.get("published_at")
        ),
        published_at=normalize_time(comment.get("create_time") or comment.get("published_at")),
        collected_at=normalize_time(comment.get("collected_at")),
        raw_sha256=raw_sha256(comment),
        normalizer_version="bili-v1",
    )
