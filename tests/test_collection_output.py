import importlib.util
import json
import os

import pytest

from app.collection_output import CollectionOutputError, read_collection_output


STAMP = 1789000000123


def write_rows(root, platform="DOUYIN", contents=None, comments=None):
    field = "aweme_id" if platform == "DOUYIN" else "video_id"
    leaf = root / ("douyin" if platform == "DOUYIN" else "bili") / "jsonl"
    leaf.mkdir(parents=True, exist_ok=True)
    if contents is None:
        contents = [{field: "123", "title": "标题"}]
    if comments is None:
        comments = [{field: 123, "comment_id": "456", "content": "原文", "last_modify_ts": STAMP}]
    for kind, rows in (("contents", contents), ("comments", comments)):
        (leaf / f"search_{kind}_test.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
        )
    return leaf


def rejected(root, platform="DOUYIN", max_records=100):
    with pytest.raises(CollectionOutputError) as caught:
        read_collection_output(root, platform, max_records)
    assert str(caught.value) == caught.value.code == "INVALID_COLLECTION_OUTPUT"


def test_collection_output_api_exists():
    assert importlib.util.find_spec("app.collection_output") is not None
    from app.collection_output import CollectionOutputError, read_collection_output
    assert callable(read_collection_output)
    assert issubclass(CollectionOutputError, ValueError)


@pytest.mark.parametrize("platform", ["DOUYIN", "BILIBILI"])
def test_pairs_real_ids_preserves_raw_unicode_and_does_not_invent_author(tmp_path, platform):
    field = "aweme_id" if platform == "DOUYIN" else "video_id"
    body = " \t原文\r\ne\u0301\u00a0　\n "
    contents = [{field: "123", "title": " 标题\n"}]
    comments = [{field: 123, "comment_id": "456", "content": body,
                 "creator_hash": "opaque", "nickname": "匿名", "last_modify_ts": STAMP}]
    write_rows(tmp_path, platform, contents, comments)
    result = read_collection_output(tmp_path, platform, 1)
    assert result == [{"content": contents[0], "comment": dict(comments[0], collected_at="2026-09-10T00:26:40Z")}]


def test_no_files_or_no_comments_are_empty(tmp_path):
    assert read_collection_output(tmp_path, "DOUYIN", 1) == []
    write_rows(tmp_path, comments=[])
    assert read_collection_output(tmp_path, "DOUYIN", 1) == []


def test_pairs_by_id_not_row_order(tmp_path):
    write_rows(tmp_path, contents=[{"aweme_id": "2"}, {"aweme_id": "1"}], comments=[
        {"aweme_id": "1", "comment_id": "3", "last_modify_ts": STAMP},
        {"aweme_id": "2", "comment_id": "4", "last_modify_ts": STAMP},
    ])
    assert [row["content"]["aweme_id"] for row in read_collection_output(tmp_path, "DOUYIN", 2)] == ["1", "2"]


@pytest.mark.parametrize("value", [True, False, 0, 101, -1, 1.0, "1", None])
def test_record_limit_is_exact_bounded_int(tmp_path, value):
    rejected(tmp_path, max_records=value)


@pytest.mark.parametrize("value", ["dy", "bili", "XIAOHONGSHU", "", None, []])
def test_platform_is_allowlisted(tmp_path, value):
    rejected(tmp_path, platform=value)


@pytest.mark.parametrize("side", ["contents", "comments"])
def test_record_overflow_is_not_truncated(tmp_path, side):
    rows = ([{"aweme_id": "123"}, {"aweme_id": "124"}] if side == "contents" else [
        {"aweme_id": "123", "comment_id": str(n), "last_modify_ts": STAMP} for n in (1, 2)])
    write_rows(tmp_path, **{side: rows})
    rejected(tmp_path, max_records=1)


@pytest.mark.parametrize("source", [None, True, 1.0, "00123", " 123", "+123", "１２３", "0", "1" * 21])
@pytest.mark.parametrize("side", ["contents", "comments"])
def test_invalid_source_id_is_rejected(tmp_path, side, source):
    row = {"aweme_id": source, "comment_id": "456", "last_modify_ts": STAMP}
    write_rows(tmp_path, **{side: [row]})
    rejected(tmp_path)


def test_comment_cannot_fall_back_to_only_content(tmp_path):
    write_rows(tmp_path, comments=[{"comment_id": "456", "last_modify_ts": STAMP}])
    rejected(tmp_path)


def test_orphan_comment_is_rejected(tmp_path):
    write_rows(tmp_path, contents=[])
    rejected(tmp_path)


@pytest.mark.parametrize("platform,alias", [("DOUYIN", "cid"), ("BILIBILI", "rpid")])
def test_comment_id_aliases_must_agree(tmp_path, platform, alias):
    field = "aweme_id" if platform == "DOUYIN" else "video_id"
    comment = {field: "123", "comment_id": "456", alias: 456, "last_modify_ts": STAMP}
    write_rows(tmp_path, platform, comments=[comment])
    assert len(read_collection_output(tmp_path, platform, 1)) == 1
    comment[alias] = 457
    write_rows(tmp_path, platform, comments=[comment])
    rejected(tmp_path, platform)


@pytest.mark.parametrize("side", ["contents", "comments"])
def test_bilibili_source_aliases_cannot_conflict(tmp_path, side):
    row = {"video_id": "123", "aid": "124", "comment_id": "456", "last_modify_ts": STAMP}
    write_rows(tmp_path, "BILIBILI", **{side: [row]})
    rejected(tmp_path, "BILIBILI")


def test_identical_content_duplicate_allowed_but_conflict_rejected(tmp_path):
    write_rows(tmp_path, contents=[{"aweme_id": "123", "title": "a"}] * 2)
    assert len(read_collection_output(tmp_path, "DOUYIN", 2)) == 1
    write_rows(tmp_path, contents=[{"aweme_id": "123", "title": "a"}, {"aweme_id": 123, "title": "b"}])
    rejected(tmp_path)


@pytest.mark.parametrize("cross_source", [False, True])
def test_duplicate_comment_ids_rejected_even_when_identical(tmp_path, cross_source):
    write_rows(tmp_path, contents=[{"aweme_id": "123"}, {"aweme_id": "124"}], comments=[
        {"aweme_id": "123", "comment_id": "456", "last_modify_ts": STAMP},
        {"aweme_id": "124" if cross_source else "123", "cid": 456, "last_modify_ts": STAMP},
    ])
    rejected(tmp_path)


@pytest.mark.parametrize("stamp", [None, True, "1789000000123", 1789000000123.0, -1, 10**30])
def test_observation_requires_real_millisecond_timestamp(tmp_path, stamp):
    write_rows(tmp_path, comments=[{"aweme_id": "123", "comment_id": "456", "last_modify_ts": stamp, "create_time": 1789000000}])
    rejected(tmp_path)


@pytest.mark.parametrize("observed", [1789000000, "2026-09-10T00:26:40Z"])
def test_existing_collected_at_must_agree(tmp_path, observed):
    comment = {"aweme_id": "123", "comment_id": "456", "last_modify_ts": STAMP, "collected_at": observed}
    write_rows(tmp_path, comments=[comment])
    assert read_collection_output(tmp_path, "DOUYIN", 1)[0]["comment"]["collected_at"] == "2026-09-10T00:26:40Z"
    comment["collected_at"] = "2026-09-10T00:26:41Z"
    write_rows(tmp_path, comments=[comment])
    rejected(tmp_path)


@pytest.mark.parametrize("raw", [b'{"aweme_id":"123","aweme_id":"123"}\n',
    b'{"nested":{"x":1,"x":1}}\n', b'{"x":NaN}\n', b'{"x":Infinity}\n',
    b'{"x":-Infinity}\n', b'{"x":1e9999}\n', b'[]\n', b'null\n', b'3\n',
    b'\xff\n', b'\xef\xbb\xbf{}\n', b'\n', b'{oops}\n'])
def test_strict_jsonl_rejects_unsafe_shapes(tmp_path, raw):
    leaf = write_rows(tmp_path)
    (leaf / "search_contents_test.jsonl").write_bytes(raw)
    rejected(tmp_path)


def test_more_than_64_files_rejected(tmp_path):
    leaf = write_rows(tmp_path)
    for n in range(63):
        (leaf / f"search_comments_{n}.jsonl").write_bytes(b"")
    rejected(tmp_path)


def test_line_over_2_mib_rejected(tmp_path):
    write_rows(tmp_path, contents=[{"aweme_id": "123", "title": "x" * (2 * 1024 * 1024)}])
    rejected(tmp_path)


def test_total_over_16_mib_rejected(tmp_path):
    write_rows(tmp_path, contents=[{"aweme_id": str(n + 1), "title": "x" * (1024 * 1024)} for n in range(17)])
    rejected(tmp_path)


def test_hardlinked_file_rejected(tmp_path):
    leaf = write_rows(tmp_path)
    os.link(leaf / "search_contents_test.jsonl", tmp_path / "outside.jsonl")
    rejected(tmp_path)


@pytest.mark.parametrize("link_kind", ["file", "directory", "root"])
def test_symlinked_paths_rejected(tmp_path, link_kind):
    data = tmp_path / "data"
    leaf = write_rows(data)
    target = (leaf / "search_contents_test.jsonl" if link_kind == "file" else leaf if link_kind == "directory" else data)
    saved = target.with_name(target.name + "_real")
    target.rename(saved)
    try:
        target.symlink_to(saved, target_is_directory=link_kind != "file")
    except OSError as exc:
        pytest.skip(f"Native symlink unavailable: winerror={getattr(exc, 'winerror', None)}")
    rejected(data)


def test_path_traversal_component_rejected(tmp_path):
    write_rows(tmp_path)
    (tmp_path / "other").mkdir()
    rejected(tmp_path / "other" / "..")


@pytest.mark.skipif(os.name != "nt", reason="Windows junction test")
def test_native_junction_is_rejected(tmp_path):
    import _winapi

    data = tmp_path / "data"
    leaf = write_rows(data)
    saved = tmp_path / "outside-jsonl"
    leaf.rename(saved)
    _winapi.CreateJunction(str(saved), str(leaf))
    try:
        assert leaf.lstat().st_file_attributes & 0x400
        rejected(data)
    finally:
        # Remove only this test's junction, never the linked target tree.
        leaf.rmdir()
