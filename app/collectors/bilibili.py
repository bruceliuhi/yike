import re
from typing import Any, Mapping
from urllib.parse import urlsplit

from app.normalizer import (
    PlatformResponseChanged,
    first_present,
    normalize_time,
    optional_text,
    raw_sha256,
    require_text,
    sha256_text,
)
from app.repository import NormalizedSignal


_NUMERIC_ID = re.compile(r"^[1-9][0-9]{0,19}$")
_BVID = re.compile(r"^BV1[1-9A-HJ-NP-Za-km-z]{9}$")


def _numeric_id(value: str, field: str, *, zero_allowed: bool = False) -> str:
    if (zero_allowed and value == "0") or _NUMERIC_ID.fullmatch(value):
        return value
    raise PlatformResponseChanged(f"PLATFORM_RESPONSE_CHANGED: invalid {field}")


def _canonical_url(
    value: str,
    *,
    video_slug: str,
    comment_id: str | None = None,
) -> str:
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise PlatformResponseChanged("PLATFORM_RESPONSE_CHANGED: invalid Bilibili URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise PlatformResponseChanged(
            "PLATFORM_RESPONSE_CHANGED: invalid Bilibili URL"
        ) from error
    expected_fragment = f"reply{comment_id}" if comment_id is not None else ""
    expected = f"https://www.bilibili.com/video/{video_slug}"
    if expected_fragment:
        expected = f"{expected}#{expected_fragment}"
    if (
        value != expected
        or
        parsed.scheme != "https"
        or parsed.hostname != "www.bilibili.com"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path != f"/video/{video_slug}"
        or parsed.query
        or parsed.fragment != expected_fragment
    ):
        raise PlatformResponseChanged("PLATFORM_RESPONSE_CHANGED: invalid Bilibili URL")
    return value


def normalize_bilibili(record: Mapping[str, Any]) -> NormalizedSignal:
    content = record.get("content") or {}
    comment = record.get("comment") or record
    if not isinstance(content, Mapping) or not isinstance(comment, Mapping):
        raise PlatformResponseChanged(
            "PLATFORM_RESPONSE_CHANGED: invalid Bilibili envelope"
        )

    source_id = _numeric_id(require_text(content, "video_id", "aid"), "video_id")
    bvid = optional_text(content, "bvid")
    if bvid is not None and not _BVID.fullmatch(bvid):
        raise PlatformResponseChanged("PLATFORM_RESPONSE_CHANGED: invalid bvid")
    video_slug = bvid if bvid is not None else f"av{source_id}"
    provided_source_url = optional_text(content, "video_url")
    source_url = (
        _canonical_url(provided_source_url, video_slug=video_slug)
        if provided_source_url
        else f"https://www.bilibili.com/video/{video_slug}"
    )
    comment_id = _numeric_id(
        require_text(comment, "comment_id", "rpid"), "comment_id"
    )
    comment_source_id = optional_text(comment, "video_id", "aid")
    if comment_source_id is not None and _numeric_id(
        comment_source_id, "video_id"
    ) != source_id:
        raise PlatformResponseChanged(
            "PLATFORM_RESPONSE_CHANGED: comment source mismatch"
        )
    body = require_text(comment, "content", "body")
    comment_url = optional_text(comment, "comment_url", "url")
    if comment_url:
        comment_url = _canonical_url(
            comment_url, video_slug=video_slug, comment_id=comment_id
        )
    else:
        comment_url = f"{source_url}#reply{comment_id}"

    parent_comment_id = optional_text(comment, "parent_comment_id", "parent_id")
    if parent_comment_id is not None:
        parent_comment_id = _numeric_id(
            parent_comment_id, "parent_comment_id", zero_allowed=True
        )

    return NormalizedSignal(
        platform="bili",
        external_source_id=source_id,
        source_title=require_text(content, "title", "desc"),
        source_url=source_url,
        source_author_public_id=require_text(
            content, "creator_hash", "user_id", "mid"
        ),
        external_comment_id=comment_id,
        parent_comment_id=parent_comment_id,
        parent_body=optional_text(comment, "parent_content", "parent_body"),
        comment_url=comment_url,
        author_public_id=require_text(comment, "creator_hash", "user_id", "mid"),
        body=body,
        body_sha256=sha256_text(body),
        source_published_at=normalize_time(
            first_present(content, "create_time", "published_at")
        ),
        published_at=normalize_time(
            first_present(comment, "create_time", "published_at")
        ),
        collected_at=normalize_time(comment.get("collected_at")),
        raw_sha256=raw_sha256(comment),
        normalizer_version="bili-v1",
    )
