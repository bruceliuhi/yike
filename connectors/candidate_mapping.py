"""Offline raw COMMENT mapping into the formal, untrusted candidate contract.

This explicit module depends on the pilot DTO. The legacy pure parser package
does not import it. Constructed permalinks are claims, not live verification.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
import re
from typing import Any, Callable

from pilot.candidate_contract import CandidateBatch, validate_candidate_batch


_NUMERIC_ID = re.compile(r"[1-9][0-9]{0,19}")
_BVID = re.compile(r"BV1[1-9A-HJ-NP-Za-km-z]{9}")
_XHS_ID = re.compile(r"[A-Za-z0-9]{8,32}")
_UTC_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_NORMALIZER_VERSION = "raw-comment-candidate-v1"


class CandidateMappingError(ValueError):
    """Sanitized raw-shape failure; never includes values from the source."""

    def __init__(self):
        self.code = "INVALID_RAW_COMMENT_BATCH"
        super().__init__(self.code)


def _numeric_id(value: object, *, parent: bool = False) -> str | None:
    if type(value) is int:
        if not (0 if parent else 1) <= value < 10 ** 20:
            raise CandidateMappingError() from None
        value = str(value)
    if not isinstance(value, str):
        raise CandidateMappingError() from None
    if parent and value == "0":
        return None
    if not _NUMERIC_ID.fullmatch(value):
        raise CandidateMappingError() from None
    return value


def _time(value: object) -> str:
    if type(value) is int:
        try:
            instant = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=value)
        except (OverflowError, ValueError):
            raise CandidateMappingError() from None
        return instant.isoformat(timespec="seconds").replace("+00:00", "Z")
    if not isinstance(value, str) or not _UTC_TIME.fullmatch(value):
        raise CandidateMappingError() from None
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise CandidateMappingError() from None
    return value


def _aliases(
    data: Mapping[str, Any], names: tuple[str, ...],
    convert: Callable[[object], object] | None = None,
) -> Any:
    """Null is unknown; conflicting known values cannot silently win."""
    values = [data[name] for name in names if data.get(name) is not None]
    if convert is not None:
        values = [convert(value) for value in values]
    if not values:
        return None
    if any(value != values[0] for value in values[1:]):
        raise CandidateMappingError() from None
    return values[0]


def _title(content: Mapping[str, Any]) -> object:
    # A title and description may differ. Explicit null title remains unknown.
    selected = "title" if "title" in content else "desc"
    for field in ("title", "desc"):
        if field != selected and content.get(field) is not None and not isinstance(content[field], str):
            raise CandidateMappingError() from None
    return content.get(selected)


def _author(comment: Mapping[str, Any], names: tuple[str, ...]) -> str | None:
    # These are different public namespaces, not same-semantic aliases.
    values = [comment[name] for name in names if comment.get(name) is not None]
    if any(not isinstance(value, str) for value in values):
        raise CandidateMappingError() from None
    return values[0] if values else None


def _checked_url(value: object, expected: str) -> str:
    # Exact established URL shapes also exclude credentials, tracking, controls,
    # alternate origins and mismatched targets. Never clean a provided URL.
    if not isinstance(value, str) or value != expected:
        raise CandidateMappingError() from None
    return value


def _bili_post_record(content: object, collector_version: str, query: str | None) -> dict:
    if not isinstance(content, Mapping):
        raise CandidateMappingError()
    source_id = _aliases(content, ('video_id', 'aid'), _numeric_id)
    if source_id is None:
        raise CandidateMappingError()
    bvid = content.get('bvid')
    if bvid is not None and (not isinstance(bvid, str) or not _BVID.fullmatch(bvid)):
        raise CandidateMappingError()
    url = f"https://www.bilibili.com/video/{bvid if bvid is not None else 'av' + source_id}"
    if content.get('video_url') is not None:
        _checked_url(content['video_url'], url)
    title = _title(content)
    body = content.get('desc')
    if body is None or (isinstance(body, str) and not body.strip()):
        body = title  # A title-only video is source text, not a generated summary.
    return dict(kind='POST', external_source_id=source_id, external_comment_id=None,
        public_url=url, title=title, body=body, author_public_id=_author(content, ('mid', 'user_id')),
        published_at=_aliases(content, ('create_time', 'published_at'), _time),
        observed_at=_time(content.get('collected_at')), parent=None,
        collector_version=collector_version, normalizer_version='raw-bili-post-candidate-v1', query=query)


def _record(platform: str, raw: object, collector_version: str, query: str | None) -> dict:
    if not isinstance(raw, Mapping):
        raise CandidateMappingError() from None
    if platform == 'BILIBILI' and set(raw) == {'content'}:
        return _bili_post_record(raw['content'], collector_version, query)
    content, comment = raw.get("content"), raw.get("comment")
    if not isinstance(content, Mapping) or not isinstance(comment, Mapping):
        raise CandidateMappingError() from None

    if platform == "DOUYIN":
        source_fields = ("aweme_id",)
        comment_fields = ("comment_id", "cid")
        body_fields = ("content", "text", "body")
        parent_fields = ("parent_comment_id", "reply_id")
        parent_source_fields = ("parent_aweme_id",)
        author_fields = ("sec_uid", "user_id", "uid")
        source_url_field = "aweme_url"
    elif platform == "XIAOHONGSHU":
        source_fields = ("note_id", "source_id", "id")
        comment_fields = ("comment_id", "id")
        body_fields = ("content", "text", "body")
        parent_fields = ("parent_comment_id", "parent_id")
        parent_source_fields = ("parent_note_id", "parent_source_id")
        author_fields = ("user_id", "sec_uid", "uid")
        source_url_field = "note_url"
    else:
        source_fields = ("video_id", "aid")
        comment_fields = ("comment_id", "rpid")
        body_fields = ("content", "body")
        parent_fields = ("parent_comment_id", "parent_id")
        parent_source_fields = ("parent_video_id", "parent_aid")
        author_fields = ("mid", "user_id")
        source_url_field = "video_url"

    converter = (lambda value: value if isinstance(value, str) and _XHS_ID.fullmatch(value) else (_numeric_id(value))) if platform == "XIAOHONGSHU" else _numeric_id
    source_id = _aliases(content, source_fields, converter)
    comment_id = _aliases(comment, comment_fields, converter)
    if source_id is None or comment_id is None:
        raise CandidateMappingError() from None
    # XHS comment.id identifies the comment, not its containing note.
    comment_source_fields = ("note_id", "source_id") if platform == "XIAOHONGSHU" else source_fields
    comment_source = _aliases(comment, comment_source_fields, converter)
    if comment_source is not None and comment_source != source_id:
        raise CandidateMappingError() from None

    if platform == "DOUYIN":
        source_url = f"https://www.douyin.com/video/{source_id}"
        suffix = "?comment_id="
    elif platform == "BILIBILI":
        bvid = content.get("bvid")
        if bvid is not None and (not isinstance(bvid, str) or not _BVID.fullmatch(bvid)):
            raise CandidateMappingError() from None
        source_url = f"https://www.bilibili.com/video/{bvid if bvid is not None else 'av' + source_id}"
        suffix = "#reply"
    else:
        source_url = f"https://www.xiaohongshu.com/explore/{source_id}"
        suffix = "?comment_id="
    if content.get(source_url_field) is not None:
        _checked_url(content[source_url_field], source_url)
    provided_url = _aliases(comment, ("comment_url", "url"))
    public_url = (
        _checked_url(provided_url, source_url + suffix + comment_id)
        if provided_url is not None else
        source_url if platform == "DOUYIN" else source_url + suffix + comment_id
    )

    # Source publication is not a comment timestamp, but its supplied aliases
    # must still be unambiguous. It never fills the comment's unknown time.
    _aliases(content, ("create_time", "published_at"), _time)
    published_at = _aliases(comment, ("create_time", "published_at"), _time)
    observed_at = _time(comment.get("collected_at"))
    parent_id = _aliases(comment, parent_fields, (lambda value: value if isinstance(value, str) and _XHS_ID.fullmatch(value) else _numeric_id(value, parent=True)) if platform == "XIAOHONGSHU" else lambda value: _numeric_id(value, parent=True))
    parent_body = _aliases(comment, ("parent_content", "parent_body"))
    parent_time = _aliases(comment, ("parent_create_time", "parent_published_at"), _time)
    parent_url = _aliases(comment, ("parent_comment_url", "parent_url"))
    parent_author = comment.get("parent_author_public_id")
    parent_source = _aliases(comment, parent_source_fields, converter)
    parent = None
    if parent_id is None:
        if any(value is not None for value in (parent_body, parent_time, parent_url, parent_author, parent_source)):
            raise CandidateMappingError() from None
    else:
        if parent_source is not None and parent_source != source_id:
            raise CandidateMappingError() from None
        parent = {
            "external_comment_id": parent_id,
            "body": parent_body,
            "author_public_id": parent_author,
            "published_at": parent_time,
            "public_url": None if parent_url is None else _checked_url(parent_url, source_url + suffix + parent_id),
        }

    return {
        "kind": "COMMENT",
        "external_source_id": source_id,
        "external_comment_id": comment_id,
        "public_url": public_url,
        "title": _title(content),
        "author_public_id": _author(comment, author_fields),
        "body": _aliases(comment, body_fields),
        "published_at": published_at,
        "observed_at": observed_at,
        "parent": parent,
        "collector_version": collector_version,
        "normalizer_version": _NORMALIZER_VERSION,
        "query": query,
    }


def build_comment_batch(
    *, platform: str, raw_records: list, request_id: str, profile_version_id: str,
    strategy_version_id: str, execution: object, collector_version: str,
    query: str | None = None, now: datetime,
) -> CandidateBatch:
    """Map one all-or-nothing batch, then invoke the real formal validator.

    ``now`` must be a caller-supplied trustworthy, timezone-aware clock value.
    Execution remains a claim; this function grants no capability or authority.
    Raw records are neither changed nor logged, and no I/O is performed.
    """
    if not isinstance(platform, str) or platform not in ("XIAOHONGSHU", "DOUYIN", "BILIBILI", "ZHIHU"):
        raise CandidateMappingError() from None
    if not isinstance(raw_records, list) or len(raw_records) > 100:
        raise CandidateMappingError() from None
    if platform == "ZHIHU":
        from connectors.zhihu_mapping import map_zhihu_record
        records = [map_zhihu_record(raw, collector_version, query) for raw in raw_records]
    else:
        records = [_record(platform, raw, collector_version, query) for raw in raw_records]
    payload = {
        "schema_version": "candidate-upload-v1",
        "request_id": request_id,
        "platform": platform,
        "profile_version_id": profile_version_id,
        "strategy_version_id": strategy_version_id,
        "execution": execution,
        "records": records,
    }
    return validate_candidate_batch(payload, now=now)
