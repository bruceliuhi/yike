"""Synthetic fixed-source Zhihu rows mapped into the formal DTO."""
from copy import deepcopy
from datetime import datetime, UTC

import pytest

from connectors.candidate_mapping import CandidateMappingError, build_comment_batch
from connectors.zhihu_mapping import map_zhihu_record


NOW=datetime(2026,9,11,8,tzinfo=UTC)


def content(kind="answer", identifier="101", body=" 原文逐字 🧰 "):
    url=(f"https://www.zhihu.com/question/501/answer/{identifier}" if kind=="answer" else
         f"https://zhuanlan.zhihu.com/p/{identifier}" if kind=="article" else
         f"https://www.zhihu.com/zvideo/{identifier}")
    return {"content_id":identifier,"content_type":kind,"content_text":body,"content_url":url,
        "question_id":"501" if kind=="answer" else "","title":"标题","created_time":1789099200,
        "updated_time":1789099300,"last_modify_ts":1789101000000,"collected_at":"2026-09-11T04:30:00Z",
        "creator_hash":"anonymous","user_nickname":"匿***"}


def comment(kind="answer", identifier="101"):
    return {"comment_id":"202","parent_comment_id":"201","content":" 评论逐字 ","publish_time":1789099400,
        "content_id":identifier,"content_type":kind,"last_modify_ts":1789101060000,
        "collected_at":"2026-09-11T04:31:00Z","creator_hash":"anonymous-comment","user_nickname":"用***"}


def options(records):
    return dict(platform="ZHIHU",raw_records=records,request_id="request-1",profile_version_id="profile-1",
        strategy_version_id="strategy-1",execution={"device_id":"device-1","task_id":"task-1","run_id":"run-1",
        "platform_run_id":"platform-run-1","lease_id":"lease-1","credential_version":1,"execution_generation":1,
        "access_mode":"PLATFORM_ACCOUNT","connection_id":"connection-1","connection_version":1},
        collector_version="collector-1",query="采购",now=NOW)


def test_answer_article_same_numeric_id_are_distinct_posts_and_raw_is_unchanged():
    records=[{"content":content("answer")},{"content":content("article")}]
    before=deepcopy(records)
    batch=build_comment_batch(**options(records))
    assert [item.kind for item in batch.records]==["POST","POST"]
    assert [item.external_source_id for item in batch.records]==["answer:101","article:101"]
    assert [item.body for item in batch.records]==[" 原文逐字 🧰 "]*2
    assert all(item.author_public_id is None for item in batch.records)
    assert records==before


def test_comment_uses_own_body_time_observation_and_real_content_url():
    raw={"content":content(),"comment":comment()}
    item=map_zhihu_record(raw,"collector-1","采购")
    assert item["kind"]=="COMMENT" and item["external_source_id"]=="answer:101"
    assert item["external_comment_id"]=="202" and item["public_url"]==raw["content"]["content_url"]
    assert item["body"]==" 评论逐字 " and item["published_at"]=="2026-09-11T04:03:20Z"
    assert item["observed_at"]=="2026-09-11T04:31:00Z" and item["author_public_id"] is None
    assert item["parent"]=={"external_comment_id":"201","body":None,"author_public_id":None,
        "published_at":None,"public_url":None}


def test_blank_video_can_carry_comment_but_cannot_create_post():
    c=content("zvideo",body="")
    item=map_zhihu_record({"content":c,"comment":comment("zvideo")},"collector-1",None)
    assert item["kind"]=="COMMENT" and item["external_source_id"]=="zvideo:101"
    with pytest.raises(CandidateMappingError): map_zhihu_record({"content":c},"collector-1",None)


@pytest.mark.parametrize("mutate",[
    lambda c,m: c.update(content_type="question"),
    lambda c,m: c.update(content_url="https://www.zhihu.com/question/501"),
    lambda c,m: c.update(content_text=""),
    lambda c,m: m.update(content_id="999"),
    lambda c,m: m.update(content_type="article"),
    lambda c,m: m.update(parent_comment_id="01"),
])
def test_invalid_type_url_body_association_and_parent_id_fail_closed(mutate):
    c,m=content(),comment(); mutate(c,m)
    with pytest.raises(CandidateMappingError): map_zhihu_record({"content":c,"comment":m},"collector-1","采购")


def test_unknown_publication_is_null_future_observation_is_contract_rejected_and_blank_video_post_fails():
    c=content(); c["created_time"]=0
    assert map_zhihu_record({"content":c},"collector-1",None)["published_at"] is None
    c["collected_at"]="2026-09-12T00:00:00Z"
    with pytest.raises(Exception,match="INVALID_SOURCE_TIME"):
        build_comment_batch(**options([{"content":c}]))
    with pytest.raises(CandidateMappingError):
        map_zhihu_record({"content":content("zvideo",body="")},"collector-1",None)


@pytest.mark.parametrize("field,bad",[("parent_comment_id",False),("parent_comment_id",0.0),
    ("publish_time",False),("publish_time",0.0)])
def test_optional_ids_and_times_do_not_coerce_bool_or_float(field,bad):
    c,m=content(),comment(); m[field]=bad
    with pytest.raises(CandidateMappingError): map_zhihu_record({"content":c,"comment":m},"collector-1",None)


def test_unhashable_content_type_is_sanitized():
    c=content(); c["content_type"]=[]
    with pytest.raises(CandidateMappingError) as caught:
        map_zhihu_record({"content":c},"collector-1",None)
    assert str(caught.value)=="INVALID_RAW_COMMENT_BATCH" and caught.value.__cause__ is None
