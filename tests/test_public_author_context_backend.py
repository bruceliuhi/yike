from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

import pytest

from pilot.candidate_assessment_model import AssessmentModelError, validate_assessment
from pilot.candidate_contract import CandidateContractError, batch_fingerprint, content_version, validate_candidate_batch
from pilot.foreground_collection import configured_collection_policy
from pilot.foreground_collection import foreground_collection_support
from pilot.monitor_runtime import MonitorRuntime
from pilot.opportunity_evidence import _public_assessment, _public_source
from tests.test_candidate_assessment_model import CONTENT, DESCRIPTION, assessment
from tests.test_candidate_contract import anonymous_execution, batch, record


NOW = datetime(2026, 9, 9, 3, tzinfo=timezone.utc)


def context(**changes):
    value = {
        "schema_version": "v2ex-author-context-v1",
        "replies_expected": 2,
        "replies_read": 2,
        "replies_complete": True,
        "supplements_read": False,
        "author_replies": [
            {"id": "18012619", "body": "项目已经结束", "published_at": "2026-09-08T02:00:00Z"},
            {"id": "18012620", "body": "需要提供作品", "published_at": "2026-09-08T03:00:00Z"},
        ],
    }
    value.update(changes)
    return value


def public_record(**changes):
    value = record(kind="PAGE", external_source_id="1232232", external_comment_id=None,
                   public_url="https://www.v2ex.com/t/1232232", author_public_id="author-1",
                   published_at="2026-09-08T01:02:03Z", observed_at="2026-09-09T02:00:00Z",
                   normalizer_version="v2ex-author-page-v1", source_context=context())
    value.update(changes)
    return value


def public_batch(item):
    return batch(platform="PUBLIC_WEB", execution=anonymous_execution(), records=[item])


def test_author_context_is_optional_and_changes_only_new_content_versions():
    old = record()
    old_hash = content_version(validate_candidate_batch(batch(records=[old]), now=NOW).records[0])
    assert "source_context" not in validate_candidate_batch(batch(records=[old]), now=NOW).records[0].model_dump(exclude_unset=True)
    first = validate_candidate_batch(public_batch(public_record()), now=NOW).records[0]
    changed = validate_candidate_batch(public_batch(public_record(source_context=context(
        author_replies=[context()["author_replies"][0], {"id": "18012620", "body": "要求已更新", "published_at": "2026-09-08T03:00:00Z"}]))), now=NOW).records[0]
    assert content_version(first) != content_version(changed)
    assert old_hash == content_version(validate_candidate_batch(batch(records=[old]), now=NOW).records[0])


def test_author_reply_time_allows_unknown_main_post_time():
    parsed = validate_candidate_batch(public_batch(public_record(published_at=None)), now=NOW)
    assert parsed.records[0].published_at is None


def test_legacy_batch_fingerprint_omits_only_absent_source_context():
    payload = batch()
    parsed = validate_candidate_batch(payload, now=NOW)
    legacy = deepcopy(payload)
    legacy.pop("request_id")
    expected = hashlib.sha256(json.dumps(legacy, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()
    assert batch_fingerprint(parsed) == expected


@pytest.mark.parametrize("change", [
    {"replies_expected": 3}, {"replies_read": 1}, {"replies_complete": False},
    {"supplements_read": True}, {"supplements_read": 0}, {"author_replies": context()["author_replies"] * 51},
    {"author_replies": [{"id": "0", "body": "x", "published_at": "2026-09-08T02:00:00Z"}]},
    {"author_replies": [{"id": "9007199254740992", "body": "x", "published_at": "2026-09-08T02:00:00Z"}]},
    {"author_replies": [{"id": "1", "body": "x", "published_at": "2026-09-08T02:00:00Z"}, {"id": "1", "body": "y", "published_at": "2026-09-08T03:00:00Z"}]},
    {"author_replies": [{"id": "1", "body": "x", "published_at": "2026-09-08T00:00:00Z"}]},
    {"author_replies": [{"id": "1", "body": "x", "published_at": "2026-09-09T02:00:01Z"}]},
])
def test_author_context_rejects_mismatch_limits_ids_and_times(change):
    with pytest.raises(CandidateContractError) as caught:
        validate_candidate_batch(public_batch(public_record(source_context=context(**change))), now=NOW)
    assert caught.value.code in {"INVALID_RECORD", "INVALID_SOURCE_TIME"}


@pytest.mark.parametrize("change", [
    {"kind": "POST"}, {"external_source_id": None}, {"author_public_id": None},
    {"normalizer_version": "normalizer-1"},
])
def test_author_context_requires_public_page_identifiers_and_fixed_normalizer(change):
    item = public_record(**change)
    payload = public_batch(item)
    if change == {"kind": "POST"}:
        payload["platform"] = "BILIBILI"
        payload["execution"] = batch()["execution"]
        item["public_url"] = "https://www.bilibili.com/video/BV1abc"
    with pytest.raises(CandidateContractError):
        validate_candidate_batch(payload, now=NOW)


def test_model_accepts_dynamic_author_update_citations_as_personal_evidence():
    content = deepcopy(CONTENT) | {
        "author_updates": ["项目已经结束", "需要提供作品"],
        "source_read_scope": "AUTHOR_REPLIES_COUNT_MATCHED_SUPPLEMENTS_UNREAD",
    }
    value = assessment()
    value["intent"] = {"level": "LOW", "reason": "作者已结束项目。", "citations": [
        {"field": "author_updates.0", "quote": "项目已经结束"}]}
    value["urgency"] = {"level": "HIGH", "reason": "作者要求作品。", "citations": [
        {"field": "author_updates.1", "quote": "提供作品"}]}
    assert validate_assessment(value, description=DESCRIPTION, content=content).intent.level == "LOW"


def test_review_projection_keeps_only_author_bodies_and_read_scope():
    from pilot.candidate_review import _model_content
    body = public_record()
    projected = _model_content("PAGE", body)
    assert projected == {"title": body["title"], "body": body["body"], "parent": None,
        "author_updates": ["项目已经结束", "需要提供作品"],
        "source_read_scope": "AUTHOR_REPLIES_COUNT_MATCHED_SUPPLEMENTS_UNREAD"}
    assert "18012619" not in repr(projected) and "author-1" not in repr(projected)


def test_inclusion_evidence_preserves_and_revalidates_author_update_citations():
    parsed = validate_candidate_batch(public_batch(public_record()), now=NOW).records[0]
    raw = {"platform": "PUBLIC_WEB", "kind": "PAGE", "external_source_id": "1232232",
           "external_comment_id": None, "version_id": "version-1", "content_version": content_version(parsed),
           "content": parsed.model_dump(mode="json", include={"public_url", "title", "author_public_id",
               "body", "published_at", "parent", "source_context"}, exclude_none=True)}
    source = _public_source(raw)
    assert source["author_updates"] == ["项目已经结束", "需要提供作品"]
    value = assessment() | {"id": "assessment-1", "assessedAt": "2026-09-09T02:30:00+00:00",
        "profileId": "profile-1", "profileVersion": 1, "strategyVersionId": "strategy-1",
        "provider": "test", "model": "test", "rule_version": "rule-v2", "rule_sha256": "a" * 64}
    value["intent"] = {"level": "LOW", "reason": "已结束", "citations": [
        {"field": "author_updates.0", "quote": "已经结束"}]}
    value["businessMatch"]["citations"] = [{"field": "profile.description", "quote": "不锈钢  输送设备"}]
    value["urgency"] = {"level": "HIGH", "reason": "要求作品", "citations": [
        {"field": "author_updates.1", "quote": "提供作品"}]}
    projected = _public_assessment(value, source)
    assert {"dimension": "intent", "field": "source.author_updates.0", "quote": "已经结束"} in projected["citations"]


@pytest.mark.parametrize("content", [
    deepcopy(CONTENT) | {"author_updates": ["x"]},
    deepcopy(CONTENT) | {"source_read_scope": "AUTHOR_REPLIES_PARTIAL_SUPPLEMENTS_UNREAD"},
    deepcopy(CONTENT) | {"author_updates": ["x"] * 101, "source_read_scope": "AUTHOR_REPLIES_PARTIAL_SUPPLEMENTS_UNREAD"},
    deepcopy(CONTENT) | {"author_updates": ["x"], "source_read_scope": "COMPLETE"},
    deepcopy(CONTENT) | {"author_updates": [None], "source_read_scope": "AUTHOR_REPLIES_PARTIAL_SUPPLEMENTS_UNREAD"},
])
def test_model_projection_requires_bounded_paired_author_fields(content):
    from pilot.candidate_assessment_model import validate_assessment_input
    with pytest.raises(AssessmentModelError):
        validate_assessment_input(description=DESCRIPTION, content=content)


def test_missing_dynamic_author_citation_is_a_safe_model_error():
    content = deepcopy(CONTENT) | {"author_updates": ["一条"],
        "source_read_scope": "AUTHOR_REPLIES_PARTIAL_SUPPLEMENTS_UNREAD"}
    value = assessment()
    value["intent"]["citations"] = [{"field": "author_updates.9", "quote": "一条"}]
    with pytest.raises(AssessmentModelError) as caught:
        validate_assessment(value, description=DESCRIPTION, content=content)
    assert (caught.value.code, caught.value.status) == ("invalid_assessment_result", 502)


def test_new_mode_accepts_all_fixed_sources_but_only_it_accepts_author_source():
    config = {"schema_version": "research-strategy-v1", "name": "项目", "source": "search",
              "keywords": ["项目"], "exclusions": [], "links": [], "mode": "once",
              "schedule": None, "research": None, "publicSource": "v2ex-outsourcing-authors-v1"}
    new = configured_collection_policy({"YIKE_PILOT_COLLECTION_MODE": "four-platform-public-project-monitor-v1"})
    for source in ("v2ex-latest-v1", "v2ex-qna-v1", "v2ex-outsourcing-authors-v1"):
        assert new("PUBLIC_WEB", "PUBLIC_ANONYMOUS", config | {"publicSource":source})
    schedule = {"kind":"daily", "times":["09:30"], "interval":1, "start":"09:00", "end":"18:00",
                "timezone":"Asia/Shanghai", "policyVersion":1}
    assert new("PUBLIC_WEB", "PUBLIC_ANONYMOUS", config | {"mode":"monitor", "schedule":schedule})
    for old_mode in ("four-platform-public-monitor-v1", "four-platform-public-sampling-monitor-v1",
                     "four-platform-public-node-monitor-v1"):
        assert not configured_collection_policy({"YIKE_PILOT_COLLECTION_MODE": old_mode})(
            "PUBLIC_WEB", "PUBLIC_ANONYMOUS", config)
    assert not new("PUBLIC_WEB", "PUBLIC_ANONYMOUS", config | {"research": {
        "version": 1, "demandTypes": ["INQUIRY"], "maxSoubei": 1,
        "limits": {"sources": 1, "minutes": 1, "modelCalls": 1},
        "stopAtAnyLimit": True, "evidenceOrder": "SOURCE_MATCH_CONTEXT"}})


def test_new_mode_capability_defaults_latest_and_catalogs_three_fixed_sources():
    from contextlib import nullcontext
    from types import SimpleNamespace
    policy = configured_collection_policy({"YIKE_PILOT_COLLECTION_MODE": "four-platform-public-project-monitor-v1"})
    database = SimpleNamespace(connect=lambda: nullcontext(
        SimpleNamespace(cursor=lambda: nullcontext(object()))))
    runtime = SimpleNamespace(database=database, _active=lambda *_: None, capability_check=policy)
    assert foreground_collection_support(runtime, "claims") == {
        "schema_version":"foreground-collection-support-v1", "mode":"four-platform-foreground-v1",
        "public_source":"v2ex-latest-v1", "public_sources":["v2ex-latest-v1", "v2ex-qna-v1", "v2ex-outsourcing-authors-v1"],
        "public_monitor":True}
    assert MonitorRuntime(database, runtime).support("claims") == {
        "schema_version":"monitor-runtime-support-v1", "mode":"four-platform-monitor-v1",
        "public_source":"v2ex-latest-v1", "public_sources":["v2ex-latest-v1", "v2ex-qna-v1", "v2ex-outsourcing-authors-v1"]}
