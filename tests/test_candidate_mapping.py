"""Synthetic raw-source to formal DTO checks; these are not platform proof."""

from copy import deepcopy
from datetime import datetime, timezone
from importlib import import_module
import json
from pathlib import Path
import traceback

import pytest
from pydantic import ValidationError

from pilot.candidate_contract import (
    CandidateBatch,
    CandidateContractError,
    batch_fingerprint,
    content_version,
    replay_decision,
    source_identity,
    validate_candidate_batch,
)


NOW = datetime(2026, 9, 9, 3, tzinfo=timezone.utc)
PLATFORMS = ("DOUYIN", "BILIBILI")
BODY = " \t原文 e\u0301 / é\r\n需要设备🧰\t "


def mapping_module():
    try:
        return import_module("connectors.candidate_mapping")
    except ModuleNotFoundError as error:
        if error.name != "connectors.candidate_mapping":
            raise
        pytest.fail("The approved raw COMMENT mapper has not been implemented")


def execution():
    return {
        "device_id": "device-1", "task_id": "task-1", "run_id": "run-1",
        "platform_run_id": "platform-run-1", "lease_id": "lease-1",
        "credential_version": 1, "execution_generation": 1,
        "access_mode": "PLATFORM_ACCOUNT", "connection_id": "connection-1",
        "connection_version": 1,
    }


def raw(platform="DOUYIN", comment_id="202"):
    source_field = "aweme_id" if platform == "DOUYIN" else "video_id"
    return {
        "content": {source_field: "101", "title": " 原标题 "},
        "comment": {"comment_id": comment_id, source_field: "101", "content": BODY,
                    "create_time": "2026-09-08T01:02:03Z",
                    "collected_at": "2026-09-09T02:00:00Z"},
    }


def build(records=None, platform="DOUYIN", **updates):
    options = {
        "platform": platform, "raw_records": [raw(platform)] if records is None else records,
        "request_id": "request-1", "profile_version_id": "profile-1",
        "strategy_version_id": "strategy-1", "execution": execution(),
        "collector_version": "collector-1", "query": " 原搜索词 ", "now": NOW,
    }
    options.update(updates)
    return mapping_module().build_comment_batch(**options)


def assert_mapping_error(records, platform="DOUYIN", **options):
    module = mapping_module()
    with pytest.raises(module.CandidateMappingError) as caught:
        build(records, platform, **options)
    assert caught.value.code == "INVALID_RAW_COMMENT_BATCH"
    assert str(caught.value) == "INVALID_RAW_COMMENT_BATCH"
    assert caught.value.__cause__ is None
    return caught.value


def assert_contract_error(records, code, platform="DOUYIN", **options):
    with pytest.raises(CandidateContractError) as caught:
        build(records, platform, **options)
    assert caught.value.code == code


@pytest.mark.parametrize("platform,fixture", [("DOUYIN", "dy"), ("BILIBILI", "bili")])
def test_existing_synthetic_fixtures_map_to_formal_frozen_whitelist(platform, fixture):
    payload = json.loads((Path(__file__).parent / "fixtures" / fixture / "comments.json").read_text(encoding="utf-8"))
    record = {"content": payload["contents"][0], "comment": payload["comments"][0]}
    before = deepcopy(record)
    batch = build([record], platform)
    item = batch.records[0]
    assert isinstance(batch, CandidateBatch)
    assert item.kind == "COMMENT" and item.body == record["comment"]["content"]
    assert item.author_public_id is None  # creator_hash is not a public author ID.
    assert item.parent.body == record["comment"]["parent_content"]
    assert item.parent.public_url is None
    assert item.published_at == "2026-08-11T16:00:00Z"
    assert item.observed_at == "2026-08-12T01:00:00Z"
    assert item.public_url == record["comment"]["comment_url"]
    assert item.normalizer_version == "raw-comment-candidate-v1"
    assert record == before
    assert validate_candidate_batch(batch.model_dump(mode="json"), now=NOW) == batch
    assert set(item.model_dump()) == {
        "kind", "external_source_id", "external_comment_id", "public_url", "title",
        "author_public_id", "body", "published_at", "observed_at", "parent",
        "collector_version", "normalizer_version", "query",
    }
    with pytest.raises(ValidationError):
        item.body = "changed"
    with pytest.raises(ValidationError):
        batch.execution.device_id = "changed"


@pytest.mark.parametrize("platform", PLATFORMS)
def test_original_unicode_anonymity_and_unknown_publication_survive(platform):
    record = raw(platform)
    record["content"].update(title=None, creator_hash="source-hash", user_id="source-user",
                             create_time="2026-09-01T00:00:00Z")
    record["comment"].update(create_time=None, nickname="buyer", creator_hash="buyer-hash")
    item = build([record], platform).records[0]
    assert item.body == BODY and item.title is None and item.author_public_id is None
    assert item.published_at is None and item.parent is None
    assert item.query == " 原搜索词 "


@pytest.mark.parametrize("platform,fields,expected", [
    ("DOUYIN", {"sec_uid": " secure ", "user_id": "user", "uid": "uid"}, " secure "),
    ("DOUYIN", {"sec_uid": None, "user_id": "user", "uid": "uid"}, "user"),
    ("DOUYIN", {"uid": "uid"}, "uid"),
    ("BILIBILI", {"mid": " mid ", "user_id": "user"}, " mid "),
    ("BILIBILI", {"mid": None, "user_id": "user"}, "user"),
])
def test_author_namespaces_have_explicit_precedence_without_trimming(platform, fields, expected):
    record = raw(platform)
    record["comment"].update(fields)
    assert build([record], platform).records[0].author_public_id == expected


@pytest.mark.parametrize("platform,field", [("DOUYIN", "uid"), ("BILIBILI", "user_id")])
@pytest.mark.parametrize("bad", [True, 123, 1.5, [], {}])
def test_even_unused_author_aliases_have_strict_types(platform, field, bad):
    record = raw(platform)
    record["comment"].update(sec_uid="good", mid="good", **{field: bad})
    assert_mapping_error([record], platform)


@pytest.mark.parametrize("platform", ["dy", "douyin", "bili", "PUBLIC_WEB", None, [], {}, True])
def test_only_two_exact_service_platforms_are_accepted(platform):
    assert_mapping_error([], platform)


@pytest.mark.parametrize("record", [None, [], {}, {"content": {}}, {"comment": {}},
                                   {"content": [], "comment": {}}, {"content": {}, "comment": []}])
def test_explicit_content_and_comment_mapping_envelope_is_required(record):
    assert_mapping_error([record])


@pytest.mark.parametrize("records", [(), {}, "records", 1, True])
def test_batch_requires_a_list(records):
    assert_mapping_error(records)


@pytest.mark.parametrize("platform", PLATFORMS)
def test_empty_and_full_batches_validate_and_101_is_rejected(platform):
    assert build([], platform).records == ()
    records = [raw(platform, str(index + 1)) for index in range(100)]
    assert len(build(records, platform).records) == 100
    assert_mapping_error(records + [raw(platform, "999")], platform)


@pytest.mark.parametrize("bad", [True, False, 1.0, [], {}, "", " 101", "101 ", "01", "0", -1, "1e3", "１２３", "1" * 21])
@pytest.mark.parametrize("location", ["source", "comment"])
def test_numeric_ids_reject_coercion_and_malformed_syntax(location, bad):
    record = raw()
    record["content" if location == "source" else "comment"]["aweme_id" if location == "source" else "comment_id"] = bad
    assert_mapping_error([record])


@pytest.mark.parametrize("platform", PLATFORMS)
def test_strict_integer_ids_have_equivalent_canonical_identity(platform):
    string_record = raw(platform)
    numeric_record = deepcopy(string_record)
    field = "aweme_id" if platform == "DOUYIN" else "video_id"
    numeric_record["content"][field] = 101
    numeric_record["comment"].update({field: 101, "comment_id": 202})
    assert build([string_record], platform) == build([numeric_record], platform)


def test_unbounded_integer_ids_are_sanitized_before_decimal_conversion():
    record = raw()
    record["comment"]["comment_id"] = 10 ** 5000
    assert_mapping_error([record])


@pytest.mark.parametrize("platform,scope,field,bad", [
    ("DOUYIN", "comment", "cid", "203"),
    ("BILIBILI", "comment", "rpid", "203"),
    ("BILIBILI", "content", "aid", "102"),
    ("BILIBILI", "comment", "aid", "102"),
    ("DOUYIN", "comment", "text", "different"),
    ("DOUYIN", "comment", "body", "different"),
    ("BILIBILI", "comment", "body", "different"),
    ("DOUYIN", "comment", "published_at", "2026-09-08T01:02:04Z"),
])
def test_conflicting_aliases_are_rejected(platform, scope, field, bad):
    record = raw(platform)
    record[scope][field] = bad
    assert_mapping_error([record], platform)


@pytest.mark.parametrize("platform", PLATFORMS)
def test_matching_aliases_and_equivalent_time_representations_are_accepted(platform):
    record = raw(platform)
    record["comment"].update(body=BODY, published_at="2026-09-08T01:02:03Z",
                             create_time=1788829323)
    record["comment"]["cid" if platform == "DOUYIN" else "rpid"] = 202
    assert build([record], platform).records[0].body == BODY


@pytest.mark.parametrize("platform", PLATFORMS)
def test_title_precedes_distinct_description_and_description_is_nullable_fallback(platform):
    record = raw(platform)
    record["content"]["desc"] = " Different description "
    assert build([record], platform).records[0].title == " 原标题 "
    record["content"].pop("title")
    assert build([record], platform).records[0].title == " Different description "
    record["content"]["title"] = None
    assert build([record], platform).records[0].title is None


@pytest.mark.parametrize("platform", PLATFORMS)
def test_comment_source_mismatch_is_rejected(platform):
    record = raw(platform)
    record["comment"]["aweme_id" if platform == "DOUYIN" else "video_id"] = "999"
    assert_mapping_error([record], platform)


@pytest.mark.parametrize("bad", ["", " \r\n\t", 123, True, [], "bad\x00", "bad\x85", "bad\ud800", "a" * 20001])
@pytest.mark.parametrize("location", ["body", "parent", "title"])
def test_text_errors_are_formal_errors_and_never_repaired(location, bad):
    record = raw()
    if location == "title":
        record["content"]["title"] = bad
    elif location == "parent":
        record["comment"].update(parent_comment_id="201", parent_body=bad)
    else:
        record["comment"]["content"] = bad
    assert_contract_error([record], "INVALID_RECORD")


@pytest.mark.parametrize("location", ["create_time", "collected_at", "parent_create_time"])
@pytest.mark.parametrize("bad", [True, False, 1.0, "1788829323", 1788829323000, "", "2026-02-30T00:00:00Z",
                                "2026-09-08T01:02:03+00:00", "٢٠٢٦-09-08T01:02:03Z", [], {}])
def test_strict_raw_times_reject_malformed_or_ambiguous_values(location, bad):
    record = raw()
    record["comment"].update(parent_comment_id="201", **{location: bad})
    assert_mapping_error([record])


@pytest.mark.parametrize("platform", PLATFORMS)
def test_epoch_zero_is_known_for_child_parent_and_observation(platform):
    record = raw(platform)
    record["comment"].update(create_time=0, collected_at=0, parent_comment_id="201", parent_create_time=0)
    item = build([record], platform).records[0]
    assert item.published_at == item.parent.published_at == item.observed_at == "1970-01-01T00:00:00Z"


@pytest.mark.parametrize("missing", [True, False])
def test_collected_at_is_required_and_has_no_source_parent_or_now_fallback(missing):
    record = raw()
    record["content"]["collected_at"] = "2026-09-09T01:00:00Z"
    record["comment"].update(parent_comment_id="201", parent_create_time="2026-09-01T00:00:00Z")
    if missing:
        record["comment"].pop("collected_at")
    else:
        record["comment"]["collected_at"] = None
    assert_mapping_error([record])


@pytest.mark.parametrize("updates", [
    {"create_time": "2026-09-09T02:00:01Z"},
    {"collected_at": "2026-09-09T03:00:01Z"},
    {"parent_comment_id": "201", "parent_create_time": "2026-09-08T01:02:04Z"},
    {"create_time": None, "parent_comment_id": "201", "parent_create_time": "2026-09-09T02:00:01Z"},
])
def test_time_ordering_errors_retain_formal_stable_codes(updates):
    record = raw()
    record["comment"].update(updates)
    assert_contract_error([record], "INVALID_SOURCE_TIME")


@pytest.mark.parametrize("platform,alias", [("DOUYIN", "reply_id"), ("BILIBILI", "parent_id")])
@pytest.mark.parametrize("value", [0, "0", None, "201", 201])
def test_parent_aliases_preserve_id_only_or_explicit_zero_sentinel(platform, alias, value):
    record = raw(platform)
    record["comment"][alias] = value
    parent = build([record], platform).records[0].parent
    if value in (0, "0", None):
        assert parent is None
    else:
        assert parent.model_dump() == {"external_comment_id": "201", "body": None,
                                      "author_public_id": None, "published_at": None, "public_url": None}


@pytest.mark.parametrize("platform", PLATFORMS)
def test_explicit_parent_fields_preserve_original_values_without_fallback(platform):
    record = raw(platform)
    base = "https://www.douyin.com/video/101" if platform == "DOUYIN" else "https://www.bilibili.com/video/av101"
    parent_url = base + ("?comment_id=201" if platform == "DOUYIN" else "#reply201")
    record["comment"].update(parent_comment_id="201", parent_content=BODY,
                             parent_author_public_id=" parent ", parent_create_time=0,
                             parent_comment_url=parent_url)
    item = build([record], platform).records[0]
    assert item.parent.body == BODY and item.parent.author_public_id == " parent "
    assert item.parent.public_url == parent_url and item.parent.published_at == "1970-01-01T00:00:00Z"


@pytest.mark.parametrize("field,value", [("parent_body", BODY), ("parent_author_public_id", "user"),
                                         ("parent_create_time", 0), ("parent_url", "https://example.com")])
@pytest.mark.parametrize("parent_id", [None, "0"])
def test_orphan_parent_metadata_is_rejected(field, value, parent_id):
    record = raw()
    record["comment"].update(parent_comment_id=parent_id, **{field: value})
    assert_mapping_error([record])


@pytest.mark.parametrize("platform,field", [("DOUYIN", "parent_aweme_id"), ("BILIBILI", "parent_video_id"),
                                           ("BILIBILI", "parent_aid")])
def test_parent_source_is_checked_when_explicit(platform, field):
    record = raw(platform)
    record["comment"].update(parent_comment_id="201", **{field: "101"})
    assert build([record], platform).records[0].parent.external_comment_id == "201"
    record["comment"][field] = "999"
    assert_mapping_error([record], platform)


@pytest.mark.parametrize("platform,alias", [("DOUYIN", "reply_id"), ("BILIBILI", "parent_id")])
def test_parent_id_conflict_and_self_parent_reject(platform, alias):
    record = raw(platform)
    record["comment"].update(parent_comment_id="201", **{alias: "200"})
    assert_mapping_error([record], platform)
    record["comment"].update(parent_comment_id="202", **{alias: "202"})
    assert_contract_error([record], "INVALID_RECORD", platform)


@pytest.mark.parametrize("aliases", [
    {"parent_body": "one", "parent_content": "two"},
    {"parent_create_time": 0, "parent_published_at": "1970-01-01T00:00:01Z"},
    {"parent_url": "one", "parent_comment_url": "two"},
])
def test_parent_alias_conflicts_reject(aliases):
    record = raw()
    record["comment"].update(parent_comment_id="201", **aliases)
    assert_mapping_error([record])


@pytest.mark.parametrize("platform", PLATFORMS)
def test_missing_urls_use_established_source_permalink_rule(platform):
    item = build(platform=platform).records[0]
    expected = "https://www.douyin.com/video/101" if platform == "DOUYIN" else "https://www.bilibili.com/video/av101#reply202"
    assert item.public_url == expected
    if platform == "BILIBILI":
        record = raw(platform)
        record["content"]["bvid"] = "BV1xx411c7mD"
        assert build([record], platform).records[0].public_url == "https://www.bilibili.com/video/BV1xx411c7mD#reply202"
        record["content"].pop("video_id")
        assert_mapping_error([record], platform)


@pytest.mark.parametrize("bad", ["", " BV1xx411c7mD", "BV1bad", True, 123, {}, []])
def test_bvid_is_validated_without_sanitizing_or_conversion(bad):
    record = raw("BILIBILI")
    record["content"]["bvid"] = bad
    assert_mapping_error([record], "BILIBILI")


@pytest.mark.parametrize("platform", PLATFORMS)
@pytest.mark.parametrize("where", ["source", "comment", "parent"])
@pytest.mark.parametrize("bad", ["", 123, " https://www.douyin.com/video/101", "https://127.0.0.1/x",
                                "https://www.bilibili.com.evil.test/video/av101", "https://user:secret@www.bilibili.com/video/av101",
                                "https://www.douyin.com/video/101?token=secret", "https://www.douyin.com/video/101%0A"])
def test_provided_unsafe_urls_are_rejected_and_never_replaced(platform, where, bad):
    record = raw(platform)
    if where == "source":
        record["content"]["aweme_url" if platform == "DOUYIN" else "video_url"] = bad
    elif where == "parent":
        record["comment"].update(parent_comment_id="201", parent_url=bad)
    else:
        record["comment"]["comment_url"] = bad
    assert_mapping_error([record], platform)


@pytest.mark.parametrize("platform", PLATFORMS)
def test_well_formed_url_must_match_source_comment_and_parent_ids(platform):
    record = raw(platform)
    base = "https://www.douyin.com/video/101" if platform == "DOUYIN" else "https://www.bilibili.com/video/av101"
    suffix = "?comment_id=" if platform == "DOUYIN" else "#reply"
    record["comment"]["comment_url"] = base + suffix + "999"
    assert_mapping_error([record], platform)
    record["comment"]["comment_url"] = base + suffix + "202"
    record["comment"]["url"] = base + suffix + "999"
    assert_mapping_error([record], platform)
    record["comment"].pop("url")
    record["comment"].update(parent_comment_id="201", parent_url=base + suffix + "202")
    assert_mapping_error([record], platform)
    record["comment"].pop("parent_url")
    record["content"]["aweme_url" if platform == "DOUYIN" else "video_url"] = base.replace("101", "999")
    assert_mapping_error([record], platform)  # checked even though comment_url is valid.


@pytest.mark.parametrize("platform", PLATFORMS)
def test_repeats_and_conflicts_use_the_real_formal_batch_rules(platform):
    first = raw(platform)
    same = deepcopy(first)
    same["comment"]["collected_at"] = "2026-09-09T02:30:00Z"
    assert_contract_error([first, same], "DUPLICATE_RECORD", platform)
    same["comment"]["content"] = "Changed original"
    assert_contract_error([first, same], "SOURCE_VERSION_CONFLICT", platform)
    assert build([same], platform).records[0].body == "Changed original"


@pytest.mark.parametrize("change", [
    {"access_mode": "PUBLIC_ANONYMOUS", "connection_id": None, "connection_version": None},
    {"execution_generation": True}, {"connection_id": None}, {"tenant_id": "tenant-1"},
    {"reviewer": "reviewer"}, {"status": "APPROVED"}, {"token": "SENSITIVE-MARKER-91"},
])
def test_invalid_execution_or_extra_authority_retain_formal_error(change):
    assert_contract_error([raw()], "INVALID_EXECUTION_CLAIM", execution={**execution(), **change})


@pytest.mark.parametrize("field", ["request_id", "profile_version_id", "strategy_version_id"])
def test_invalid_batch_versions_retain_formal_error(field):
    assert_contract_error([raw()], "INVALID_BATCH", **{field: "bad value"})


def test_raw_extras_are_not_upload_authority_or_evidence_fields():
    record = raw()
    record["comment"].update(tenant_id="tenant", reviewer="reviewer", status="APPROVED", token="secret",
                             raw_sha256="digest", verifiable=True, normalizer_version="fake")
    item = build([record]).records[0]
    assert item.normalizer_version == "raw-comment-candidate-v1"
    assert not any(key in item.model_dump() for key in ("tenant_id", "reviewer", "status", "token", "raw_sha256", "verifiable"))


def test_formal_fingerprint_replay_and_version_semantics_are_preserved():
    original = build()
    retry = build(request_id="retry")
    digest = batch_fingerprint(original)
    assert digest == batch_fingerprint(retry)
    assert replay_decision(None, digest) == "NEW"
    assert replay_decision(digest, batch_fingerprint(retry)) == "REPLAY"
    observation = raw()
    observation["comment"]["collected_at"] = "2026-09-09T02:30:00Z"
    observed = build([observation], query="new", collector_version="collector-2")
    assert content_version(original.records[0]) == content_version(observed.records[0])
    assert source_identity(original.records[0], "DOUYIN") == source_identity(observed.records[0], "DOUYIN")
    assert replay_decision(digest, batch_fingerprint(observed)) == "CONFLICT"
    for options in ({"profile_version_id": "profile-2"}, {"strategy_version_id": "strategy-2"},
                    {"execution": {**execution(), "execution_generation": 2}}):
        assert digest != batch_fingerprint(build(**options))
    changed = raw()
    changed["comment"]["content"] += "新增"
    assert content_version(original.records[0]) != content_version(build([changed]).records[0])


def test_bad_record_rejects_whole_batch_without_mutating_input_or_leaking():
    records = [raw(comment_id="201"), raw()]
    marker = "SENSITIVE-RAW-MARKER-192"
    records[-1]["comment"]["comment_url"] = "https://www.douyin.com/video/101?token=" + marker
    before = deepcopy(records)
    error = assert_mapping_error(records)
    assert records == before
    assert marker not in str(error) and marker not in repr(error)
    assert marker not in "".join(traceback.format_exception(error))


def test_trusted_now_is_required_and_not_replaced_with_wall_clock():
    with pytest.raises(ValueError, match="^now must be timezone-aware$"):
        build(now=datetime(2026, 9, 9))
    assert_contract_error([raw()], "INVALID_SOURCE_TIME", now=datetime(2026, 8, 1, tzinfo=timezone.utc))


def xhs_raw():
    # Synthetic values with the actual 24-character hexadecimal source shape.
    return {
        "content": {"note_id": "66c01234abcdef0123456789", "title": " 原标题 e\u0301 "},
        "comment": {
            "comment_id": "66c11234abcdef0123456789", "content": BODY,
            "collected_at": "2026-09-09T02:00:00Z",
        },
    }


@pytest.mark.parametrize('description', [None, '', ' \t', BODY])
def test_xhs_post_preserves_real_body_or_title_only_fallback(description):
    content = dict(xhs_raw()['content'], desc=description, time='2026-09-08T01:02:03Z',
                   collected_at='2026-09-09T02:00:00Z', user_id='public-author')
    original = deepcopy(content)
    item = build([{'content': content}], 'XIAOHONGSHU').records[0]
    assert item.kind == 'POST'
    assert item.body == (BODY if description == BODY else content['title'])
    assert item.published_at == content['time'] and item.author_public_id == 'public-author'
    assert content == original


@pytest.mark.parametrize('changes', [
    {'source_id': '66c21234abcdef0123456789'}, {'id': '66c21234abcdef0123456789'},
    {'note_url': 'https://example.com/private'}, {'desc': 123}, {'user_id': 123},
    {'time': 1788829323000}, {'time': True}, {'published_at': '2026-09-08T01:02:04Z'},
])
def test_xhs_post_rejects_malformed_or_conflicting_source_metadata(changes):
    content = dict(xhs_raw()['content'], desc=BODY, time='2026-09-08T01:02:03Z',
                   collected_at='2026-09-09T02:00:00Z')
    content.update(changes)
    assert_mapping_error([{'content': content}], 'XIAOHONGSHU')


@pytest.mark.parametrize("fields", [
    ("note_id",), ("source_id",), ("note_id", "source_id"),
    ("parent_note_id",), ("parent_source_id",), ("parent_note_id", "parent_source_id"),
    ("note_id", "source_id", "parent_note_id", "parent_source_id"),
])
def test_xhs_hex_source_references_preserve_exact_comment_and_parent_evidence(fields):
    record = xhs_raw()
    note_id = record["content"]["note_id"]
    parent_id = "66c21234abcdef0123456789"
    record["comment"].update({field: note_id for field in fields})
    record["comment"].update(parent_comment_id=parent_id, parent_content=BODY)
    before = deepcopy(record)
    item = build([record], "XIAOHONGSHU").records[0]
    assert item.external_source_id == note_id
    assert item.external_comment_id == record["comment"]["comment_id"]
    assert item.body == BODY and item.title == record["content"]["title"]
    assert item.parent.external_comment_id == parent_id and item.parent.body == BODY
    assert item.parent.published_at is None and item.published_at is None
    assert item.public_url == f"https://www.xiaohongshu.com/explore/{note_id}?comment_id={item.external_comment_id}"
    assert record == before


@pytest.mark.parametrize("include_canonical", [False, True])
def test_xhs_comment_id_alias_is_not_mistaken_for_its_note_id(include_canonical):
    record = xhs_raw()
    comment_id = record["comment"]["comment_id"]
    record["comment"].update(id=comment_id, note_id=record["content"]["note_id"])
    if not include_canonical:
        record["comment"].pop("comment_id")
    record["content"]["id"] = record["content"]["note_id"]
    assert build([record], "XIAOHONGSHU").records[0].external_comment_id == comment_id


@pytest.mark.parametrize("scope,fields", [
    ("content", ("note_id", "source_id")),
    ("content", ("note_id", "id")),
    ("comment", ("comment_id", "id")),
    ("comment", ("note_id", "source_id")),
    ("comment", ("parent_note_id", "parent_source_id")),
    ("comment", ("parent_comment_id", "parent_id")),
])
def test_xhs_conflicting_semantic_id_aliases_are_rejected(scope, fields):
    record = xhs_raw()
    record["comment"]["parent_comment_id"] = "66c21234abcdef0123456789"
    record[scope].update({fields[0]: "66c01234abcdef0123456789",
                          fields[1]: "66c31234abcdef0123456789"})
    assert_mapping_error([record], "XIAOHONGSHU")


@pytest.mark.parametrize("field", ["note_id", "source_id", "parent_note_id", "parent_source_id"])
@pytest.mark.parametrize("bad", ["66c31234abcdef0123456789", " 66c01234abcdef0123456789",
                                  "66c01234abcdef0123456789 ", True, 1.0])
def test_xhs_source_references_reject_cross_source_and_noncanonical_values(field, bad):
    record = xhs_raw()
    record["comment"].update(parent_comment_id="66c21234abcdef0123456789", **{field: bad})
    assert_mapping_error([record], "XIAOHONGSHU")


@pytest.mark.parametrize("platform,fields", [
    ("DOUYIN", ("aweme_id", "parent_aweme_id")),
    ("BILIBILI", ("video_id", "parent_video_id")),
])
@pytest.mark.parametrize("index", [0, 1])
def test_numeric_platform_source_references_still_reject_xhs_hex_ids(platform, fields, index):
    record = raw(platform)
    record["comment"].update(parent_comment_id="201", **{fields[index]: "66c01234abcdef0123456789"})
    assert_mapping_error([record], platform)
