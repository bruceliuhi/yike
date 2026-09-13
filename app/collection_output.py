"""Strict reader for a stopped collector's private JSONL output tree."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import stat


_MAX_FILES = 64
_MAX_BYTES = 16 * 1024 * 1024
_MAX_LINE_BYTES = 2 * 1024 * 1024
_NUMERIC_ID = re.compile(r"[1-9][0-9]{0,19}")
_XHS_ID = re.compile(r"[A-Za-z0-9]{8,32}")
_PLATFORMS = {"DOUYIN": ("douyin", "aweme_id", "cid"),
              "BILIBILI": ("bili", "video_id", "rpid"),
              "XIAOHONGSHU": ("xhs", "note_id", "id"),
              "ZHIHU": ("zhihu", "content_id", "comment_id")}
_FILENAME = re.compile(r"(search|detail|creator)_(contents|comments)_[^/\\:]+\.jsonl")
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class CollectionOutputError(ValueError):
    """Never expose source data or local paths through error messages."""

    def __init__(self):
        self.code = "INVALID_COLLECTION_OUTPUT"
        super().__init__(self.code)


def _check_stat(info: os.stat_result, *, directory: bool) -> None:
    if (stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            or (not directory and info.st_nlink != 1)):
        raise CollectionOutputError()


def _check_directory(path: Path) -> bool:
    """Check every existing ancestor without following a link/reparse point."""
    for part in (*reversed(path.parents), path):
        try:
            info = part.lstat()
        except FileNotFoundError:
            return False
        _check_stat(info, directory=True)
    return True


def _object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CollectionOutputError()
        result[key] = value
    return result


def _nonfinite(_: str) -> None:
    raise CollectionOutputError()


def _float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise CollectionOutputError()
    return number


def _id(value: object, platform: str = "DOUYIN") -> str:
    if platform == "XIAOHONGSHU" and isinstance(value, str) and _XHS_ID.fullmatch(value):
        return value
    if type(value) is int:
        value = str(value)
    if not isinstance(value, str) or not _NUMERIC_ID.fullmatch(value):
        raise CollectionOutputError()
    return value


def _source_id(row: dict, platform: str) -> str:
    field = _PLATFORMS[platform][1]
    source = _id(row.get(field), platform)
    if platform == "ZHIHU":
        kind = row.get("content_type")
        if kind not in ("answer", "article", "zvideo"):
            raise CollectionOutputError()
        return f"{kind}:{source}"
    if platform == "BILIBILI" and row.get("aid") is not None and _id(row["aid"]) != source:
        raise CollectionOutputError()
    if platform == "XIAOHONGSHU" and row.get("source_id") is not None and _id(row["source_id"], platform) != source:
        raise CollectionOutputError()
    return source


def _comment_id(row: dict, platform: str) -> str:
    fields = ("comment_id", _PLATFORMS[platform][2])
    values = [_id(row[field], platform) for field in fields if row.get(field) is not None]
    if not values or any(value != values[0] for value in values):
        raise CollectionOutputError()
    return values[0]


def _with_observation(row: dict) -> dict:
    # The pinned upstream store emits integer milliseconds, not publication time.
    millis = row.get("last_modify_ts")
    if type(millis) is not int or millis < 0:
        raise CollectionOutputError()
    seconds = millis // 1000
    instant = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    observed = instant.isoformat(timespec="seconds").replace("+00:00", "Z")
    if "collected_at" in row:
        supplied = row["collected_at"]
        if not ((type(supplied) is int and supplied == seconds)
                or (isinstance(supplied, str) and supplied == observed)):
            raise CollectionOutputError()
    return dict(row, collected_at=observed)


def _content_identity(row: dict, platform: str, source: str) -> str:
    canonical = dict(row)
    canonical[_PLATFORMS[platform][1]] = source
    if platform == "BILIBILI" and canonical.get("aid") is not None:
        canonical["aid"] = source
    # JSON comparison distinguishes e.g. true from 1 while leaving all text exact.
    return json.dumps(canonical, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _read(output_dir: Path, platform: str, max_records: int, collection_mode: str) -> list[dict]:
    if (not isinstance(output_dir, Path) or ".." in output_dir.parts
            or not isinstance(platform, str) or platform not in _PLATFORMS
            or type(max_records) is not int or not 1 <= max_records <= 100
            or collection_mode not in ('search', 'detail', 'creator')
            or (collection_mode != 'search' and platform != 'BILIBILI')):
        raise CollectionOutputError()
    root = output_dir.absolute()
    leaf = root / _PLATFORMS[platform][0] / "jsonl"
    if not _check_directory(leaf):
        return []
    resolved_root = root.resolve(strict=True)
    files = []
    with os.scandir(leaf) as entries:
        for count, entry in enumerate(entries, 1):
            if count > _MAX_FILES:
                raise CollectionOutputError()
            path = Path(entry.path)
            info = path.lstat()
            _check_stat(info, directory=False)
            if not path.resolve(strict=True).is_relative_to(resolved_root):
                raise CollectionOutputError()
            match = _FILENAME.fullmatch(entry.name)
            if match:
                if match[1] != collection_mode:
                    if collection_mode != 'search':
                        raise CollectionOutputError()
                    continue
                files.append((path, match[2], info))
    if sum(info.st_size for _, _, info in files) > _MAX_BYTES:
        raise CollectionOutputError()

    contents: dict[str, dict] = {}
    identities: dict[str, str] = {}
    comments: list[tuple[str, dict]] = []
    comment_ids: set[str] = set()
    counts = {"contents": 0, "comments": 0}
    total = 0
    for path, kind, expected in sorted(files):
        _check_directory(path.parent)
        _check_stat(path.lstat(), directory=False)
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            _check_stat(opened, directory=False)
            if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
                    expected.st_dev, expected.st_ino, expected.st_size, expected.st_mtime_ns):
                raise CollectionOutputError()
            while True:
                raw = stream.readline(min(_MAX_LINE_BYTES, _MAX_BYTES - total) + 1)
                if not raw:
                    break
                total += len(raw)
                if len(raw) > _MAX_LINE_BYTES or total > _MAX_BYTES:
                    raise CollectionOutputError()
                row = json.loads(raw.decode("utf-8"), object_pairs_hook=_object,
                                 parse_constant=_nonfinite, parse_float=_float)
                if not isinstance(row, dict):
                    raise CollectionOutputError()
                counts[kind] += 1
                if counts[kind] > max_records:
                    raise CollectionOutputError()
                source = _source_id(row, platform)
                if kind == "contents":
                    identity = _content_identity(row, platform, source)
                    if source in identities and identities[source] != identity:
                        raise CollectionOutputError()
                    identities[source] = identity
                    contents.setdefault(source, row)
                else:
                    comment_id = _comment_id(row, platform)
                    if comment_id in comment_ids:
                        raise CollectionOutputError()
                    comment_ids.add(comment_id)
                    comments.append((source, _with_observation(row)))
            final = os.fstat(stream.fileno())
            _check_stat(final, directory=False)
            if (final.st_size, final.st_mtime_ns) != (opened.st_size, opened.st_mtime_ns):
                raise CollectionOutputError()
    if any(source not in contents for source, _ in comments):
        raise CollectionOutputError()
    if collection_mode != 'search' or platform == 'XIAOHONGSHU':
        observed = {source: _with_observation(row) for source, row in contents.items()}
        result = [{'content': row} for row in observed.values()]
        result += [{'content': observed[source], 'comment': row} for source, row in comments]
        if len(result) > max_records:
            raise CollectionOutputError()
        return result
    if platform == "ZHIHU":
        # Main posts carry their own observation. A comment-only legacy reader
        # would silently discard buyer demand expressed in an answer/article.
        posts = []
        observed_contents = {}
        for source, row in contents.items():
            observed_contents[source] = _with_observation(row)
            body = row.get("content_text")
            if not isinstance(body, str):
                raise CollectionOutputError()
            if not body.strip():
                if row["content_type"] != "zvideo":
                    raise CollectionOutputError()
                continue
            posts.append({"content": observed_contents[source]})
        result = posts + [{"content": observed_contents[source], "comment": row} for source, row in comments]
        if len(result) > max_records:
            raise CollectionOutputError()
        return result
    return [{"content": contents[source], "comment": row} for source, row in comments]


def read_collection_output(output_dir: Path, platform: str, max_records: int, *, collection_mode: str = 'search') -> list[dict]:
    """Return complete ID-matched records or one sanitized error, never a prefix.

    The caller must stop its writer and validate the private tree before calling.
    This reader grants no execution, upload or source-verification authority.
    """
    try:
        return _read(output_dir, platform, max_records, collection_mode)
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        raise CollectionOutputError() from None
