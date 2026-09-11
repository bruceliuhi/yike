"""Synthetic pinned Zhihu JSONL; no live platform or account access."""
from copy import deepcopy
from datetime import UTC, datetime
import json

import pytest

from app.collection_output import CollectionOutputError, read_collection_output

STAMP = 1789000000123


def test_portable_host_contains_the_new_mapper_dependency():
    from app.windows_portable_inventory import HOST_FILES
    assert "connectors/zhihu_mapping.py" in HOST_FILES


def content(kind="answer", identifier="101", **changes):
    url = {"answer": f"https://www.zhihu.com/question/9/answer/{identifier}",
           "article": f"https://zhuanlan.zhihu.com/p/{identifier}",
           "zvideo": f"https://www.zhihu.com/zvideo/{identifier}"}[kind]
    return dict(content_type=kind, content_id=identifier, content_url=url,
                question_id="9" if kind == "answer" else "", title="原题",
                content_text=" \t想找一家做设备检测的公司\r\n", created_time=1788900000,
                last_modify_ts=STAMP, **changes)


def comment(kind="answer", **changes):
    row = dict(content_type=kind, content_id="101", comment_id="202",
               parent_comment_id="0", content=" 请问能承接吗？ ", publish_time=0,
               last_modify_ts=STAMP+1000, creator_hash="not-public-identity")
    return row | changes


def write(root, contents, comments):
    leaf = root / "zhihu" / "jsonl"
    leaf.mkdir(parents=True, exist_ok=True)
    for kind, rows in (("contents", contents), ("comments", comments)):
        (leaf / f"search_{kind}_test.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False)+"\n" for row in rows), encoding="utf-8")


def test_posts_and_comments_match_type_and_id_and_keep_own_observation(tmp_path):
    write(tmp_path, [content(), content("article")], [comment("article")])
    rows = read_collection_output(tmp_path, "ZHIHU", 3)
    assert len(rows) == 3
    assert [row["content"]["content_type"] for row in rows] == ["answer", "article", "article"]
    assert rows[0]["content"]["content_text"] == content()["content_text"]
    assert rows[0]["content"]["collected_at"] == "2026-09-10T00:26:40Z"
    assert rows[2]["comment"]["collected_at"] == "2026-09-10T00:26:41Z"


@pytest.mark.parametrize("problem", ["orphan", "conflict", "duplicate", "overbudget", "missing_observation", "unknown_type", "blank_answer"])
def test_invalid_batch_is_not_returned_as_partial_success(tmp_path, problem):
    posts, comments, limit = [content()], [comment()], 3
    if problem == "orphan": comments[0]["content_type"] = "article"
    if problem == "conflict":
        other = deepcopy(posts[0]); other["content_text"] = "different"; posts.append(other)
    if problem == "duplicate": comments.append(deepcopy(comments[0]))
    if problem == "overbudget": limit = 1
    if problem == "missing_observation": posts[0].pop("last_modify_ts")
    if problem == "unknown_type": posts[0]["content_type"] = "question"
    if problem == "blank_answer": posts[0]["content_text"] = " "
    write(tmp_path, posts, comments)
    with pytest.raises(CollectionOutputError, match="INVALID_COLLECTION_OUTPUT"):
        read_collection_output(tmp_path, "ZHIHU", limit)


def test_blank_video_can_supply_comment_context_but_not_a_fake_post(tmp_path):
    video = content("zvideo"); video["content_text"] = ""
    write(tmp_path, [video], [comment("zvideo")])
    rows = read_collection_output(tmp_path, "ZHIHU", 1)
    assert len(rows) == 1 and "comment" in rows[0]


def test_pinned_output_flows_to_formal_candidate_contract(tmp_path):
    from connectors.candidate_mapping import build_comment_batch
    from tests.test_candidate_mapping import execution
    write(tmp_path, [content(), content("article")], [comment("article")])
    result = build_comment_batch(platform="ZHIHU", raw_records=read_collection_output(tmp_path, "ZHIHU", 3),
        request_id="request-z", profile_version_id="profile-z", strategy_version_id="strategy-z",
        execution=execution(), collector_version="pinned-zhihu", query="设备检测",
        now=datetime(2026, 9, 11, tzinfo=UTC))
    assert [row.kind for row in result.records] == ["POST", "POST", "COMMENT"]
    assert [row.external_source_id for row in result.records] == ["answer:101", "article:101", "article:101"]
    assert result.records[-1].published_at is None
    assert all(row.author_public_id is None for row in result.records)
    assert result.records[-1].public_url == "https://zhuanlan.zhihu.com/p/101"
