from copy import deepcopy
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from pilot.candidate_contract import CandidateContractError, batch_fingerprint, content_version, replay_decision, source_identity, validate_candidate_batch

NOW = datetime(2026, 9, 9, 3, tzinfo=timezone.utc)


def record(**updates):
    data = {"kind":"POST", "external_source_id":"post-1", "external_comment_id":None,
        "public_url":"https://www.bilibili.com/video/BV1abc", "title":"原始标题",
        "author_public_id":None, "body":" 原始正文\n", "published_at":"2026-09-08T01:02:03Z",
        "observed_at":"2026-09-09T02:00:00Z", "parent":None,
        "collector_version":"collector-1", "normalizer_version":"normalizer-1", "query":"采购线索"}
    data.update(updates); return data


def batch(**updates):
    data = {"schema_version":"candidate-upload-v1", "request_id":"request-1", "platform":"BILIBILI",
        "profile_version_id":"profile-1", "strategy_version_id":"strategy-1",
        "execution":{"device_id":"device-1", "task_id":"task-1", "run_id":"run-1",
            "platform_run_id":"platform-run-1", "lease_id":"lease-1", "credential_version":1,
            "execution_generation":1, "access_mode":"PLATFORM_ACCOUNT",
            "connection_id":"connection-1", "connection_version":1}, "records":[record()]}
    data.update(updates); return data


def assert_code(payload, code):
    with pytest.raises(CandidateContractError) as caught: validate_candidate_batch(payload, now=NOW)
    assert caught.value.code == code


def anonymous_execution():
    return {**batch()["execution"], "access_mode":"PUBLIC_ANONYMOUS", "connection_id":None, "connection_version":None}


def test_public_anonymous_empty_batch_is_valid_frozen_and_nonmutating():
    payload = batch(platform="PUBLIC_WEB", execution=anonymous_execution(), records=[]); original=deepcopy(payload)
    parsed = validate_candidate_batch(payload, now=NOW)
    assert parsed.records == () and payload == original
    with pytest.raises(ValidationError): parsed.platform = "DOUYIN"
    with pytest.raises(ValidationError): parsed.execution.device_id = "other"


@pytest.mark.parametrize("bad_platform", [[], {}, True, None])
def test_public_entry_rejects_wrong_type_platform_with_stable_batch_error(bad_platform):
    assert_code(batch(platform=bad_platform), "INVALID_BATCH")


def test_public_entry_accepts_valid_platform_control():
    assert validate_candidate_batch(batch(platform="BILIBILI"), now=NOW).platform == "BILIBILI"


@pytest.mark.parametrize("field", ["connection_id", "connection_version"])
def test_account_connection_fields_must_be_both_present(field):
    execution=batch()["execution"]; execution[field]=None
    assert_code(batch(execution=execution), "INVALID_EXECUTION_CLAIM")


def test_anonymous_mode_is_web_only_and_connectionless():
    assert_code(batch(execution=anonymous_execution()), "INVALID_EXECUTION_CLAIM")
    execution=anonymous_execution(); execution["connection_id"]="connection-1"
    assert_code(batch(platform="PUBLIC_WEB", execution=execution, records=[]), "INVALID_EXECUTION_CLAIM")


@pytest.mark.parametrize("bad", [True, False, 0, -1, 1.0, "1"])
def test_versions_are_strict_positive_integers(bad):
    execution=batch()["execution"]; execution["execution_generation"]=bad
    assert_code(batch(execution=execution), "INVALID_EXECUTION_CLAIM")


@pytest.mark.parametrize("where,field,code", [("top","tenant_id","INVALID_BATCH"),
    ("top","APPROVED","INVALID_BATCH"), ("execution","reviewer","INVALID_EXECUTION_CLAIM"),
    ("execution","token","INVALID_EXECUTION_CLAIM"), ("record","status","INVALID_RECORD"),
    ("parent","owner","INVALID_RECORD")])
def test_unknown_or_authority_fields_are_rejected(where, field, code):
    payload=batch()
    if where=="top": payload[field]="secret"
    elif where=="execution": payload["execution"][field]="secret"
    elif where=="record": payload["records"][0][field]="secret"
    else:
        payload["records"][0].update(kind="COMMENT", external_comment_id="reply-1",
            parent={"external_comment_id":"reply-0", "body":None, "author_public_id":None,
                    "published_at":None, "public_url":None, field:"secret"})
    assert_code(payload, code)


def test_kind_ids_page_boundary_and_parent_id_only():
    assert_code(batch(records=[record(kind="COMMENT")]), "INVALID_RECORD")
    assert_code(batch(records=[record(external_comment_id="reply-1")]), "INVALID_RECORD")
    assert_code(batch(records=[record(kind="PAGE")]), "INVALID_RECORD")
    web=batch(platform="PUBLIC_WEB", execution=anonymous_execution(), records=[record(kind="PAGE",
        external_source_id=None, public_url="https://example.org/page")])
    assert validate_candidate_batch(web, now=NOW).records[0].external_source_id is None
    child=record(kind="COMMENT", external_comment_id="reply-1", parent={"external_comment_id":"reply-0",
        "body":None, "author_public_id":None, "published_at":None, "public_url":None})
    assert validate_candidate_batch(batch(records=[child]), now=NOW).records[0].parent.body is None


def test_unknown_and_old_published_time_are_preserved():
    parsed=validate_candidate_batch(batch(records=[record(published_at=None)]), now=NOW)
    assert parsed.records[0].published_at is None and parsed.records[0].body == " 原始正文\n"
    assert validate_candidate_batch(batch(records=[record(published_at="2020-01-01T00:00:00Z")]), now=NOW)


@pytest.mark.parametrize("field,value", [("observed_at","2026-09-09T03:00:01Z"),
    ("observed_at","2026-02-30T00:00:00Z"), ("observed_at","2026-09-09T03:00:00+00:00"),
    ("published_at","2026-09-09T02:00:01Z")])
def test_invalid_source_times_are_rejected(field, value):
    assert_code(batch(records=[record(**{field:value})]), "INVALID_SOURCE_TIME")


def test_parent_time_and_identity_rules():
    parent={"external_comment_id":"reply-0", "body":None, "author_public_id":None,
        "published_at":"2026-09-09T02:00:01Z", "public_url":None}
    child=record(kind="COMMENT", external_comment_id="reply-1", published_at="2026-09-09T02:00:00Z", parent=parent)
    assert_code(batch(records=[child]), "INVALID_SOURCE_TIME")
    child["parent"].update(external_comment_id="reply-1", published_at=None)
    assert_code(batch(records=[child]), "INVALID_RECORD")


@pytest.mark.parametrize("body", [" \n\t", "bad\x00body", "x"*20001])
def test_body_boundaries(body): assert_code(batch(records=[record(body=body)]), "INVALID_RECORD")


@pytest.mark.parametrize("control", [chr(127), chr(133), chr(159)])
def test_body_rejects_del_and_c1_controls(control):
    assert_code(batch(records=[record(body=f"prefix{control}suffix")]), "INVALID_RECORD")


@pytest.mark.parametrize("control", [chr(127), chr(133), chr(159)])
def test_parent_body_rejects_del_and_c1_controls(control):
    parent = {"external_comment_id":"reply-0", "body":f"prefix{control}suffix",
        "author_public_id":None, "published_at":None, "public_url":None}
    child = record(kind="COMMENT", external_comment_id="reply-1", parent=parent)
    assert_code(batch(records=[child]), "INVALID_RECORD")


def test_body_preserves_unicode_and_allowed_whitespace_controls():
    body = "中文😊\t下一列\n换行\r返回"
    parsed = validate_candidate_batch(batch(records=[record(body=body)]), now=NOW)
    assert parsed.records[0].body == body


@pytest.mark.parametrize("url", ["https://user:pass@bilibili.com/video/1",
    "https://bilibili.com:8443/video/1", "https://localhost/page", "https://127.0.0.1/page",
    "https://10.0.0.1/page", "https://bilibili.com.evil.test/video/1",
    "https://bilibili.com/video/1?token=secret", "https://bilibili.com/video/1?%74oken=secret",
    "https://bilibili.com/video/1#bad/fragment", "https://bilibili.com\\@evil.test/video/1"])
def test_unsafe_urls(url): assert_code(batch(records=[record(public_url=url)]), "INVALID_SOURCE_URL")


@pytest.mark.parametrize("url", [
    "https://localhost./page",
    "https://127.1/page",
    "https://2130706433/page",
    "https://0x7f000001/page",
    "https://0177.0.0.1/page",
])
def test_noncanonical_local_or_numeric_hosts_are_rejected(url):
    payload = batch(platform="PUBLIC_WEB", execution=anonymous_execution(), records=[
        record(kind="PAGE", external_source_id=None, public_url=url)
    ])
    assert_code(payload, "INVALID_SOURCE_URL")


@pytest.mark.parametrize("url", [
    "https://localhost。/",
    "https://localhost．/",
    "https://localhost｡/",
    "https://127.0.0.1。/",
    "https://127.0.0.1．/",
    "https://127.0.0.1｡/",
    "https://%6cocalhost/",
    "https://%31%32%37.0.0.1/",
    "https://example..org/",
    "https://example.org../",
])
def test_encoded_equivalent_or_malformed_hosts_are_rejected(url):
    payload = batch(platform="PUBLIC_WEB", execution=anonymous_execution(), records=[
        record(kind="PAGE", external_source_id=None, public_url=url)
    ])
    assert_code(payload, "INVALID_SOURCE_URL")


@pytest.mark.parametrize("url", ["https://example.org/page", "https://example.org./page", "https://8.8.8.8/page"])
def test_public_web_accepts_public_domain_and_ip_controls(url):
    payload = batch(platform="PUBLIC_WEB", execution=anonymous_execution(), records=[
        record(kind="PAGE", external_source_id=None, public_url=url)
    ])
    assert validate_candidate_batch(payload, now=NOW)


@pytest.mark.parametrize("parent_url", ["", "x" * 2049, "not-a-url", "https://127.1/reply"])
def test_non_null_parent_url_uses_full_source_url_validation(parent_url):
    parent = {"external_comment_id":"reply-0", "body":None, "author_public_id":None,
        "published_at":None, "public_url":parent_url}
    child = record(kind="COMMENT", external_comment_id="reply-1", parent=parent)
    assert_code(batch(records=[child]), "INVALID_SOURCE_URL")


@pytest.mark.parametrize("parent_url", [
    "https://localhost。/reply",
    "https://localhost．/reply",
    "https://localhost｡/reply",
    "https://127.0.0.1。/reply",
    "https://127.0.0.1．/reply",
    "https://127.0.0.1｡/reply",
    "https://%6cocalhost/reply",
    "https://%31%32%37.0.0.1/reply",
])
def test_parent_url_rejects_encoded_or_equivalent_local_hosts(parent_url):
    parent = {"external_comment_id":"reply-0", "body":None, "author_public_id":None,
        "published_at":None, "public_url":parent_url}
    child = record(kind="COMMENT", external_comment_id="reply-1", parent=parent)
    assert_code(batch(platform="PUBLIC_WEB", execution=anonymous_execution(), records=[child]), "INVALID_SOURCE_URL")


def test_null_parent_url_is_allowed():
    parent = {"external_comment_id":"reply-0", "body":None, "author_public_id":None,
        "published_at":None, "public_url":None}
    child = record(kind="COMMENT", external_comment_id="reply-1", parent=parent)
    assert validate_candidate_batch(batch(records=[child]), now=NOW).records[0].parent.public_url is None


def test_bilibili_reply_fragment_is_allowed():
    payload=batch(records=[record(kind="COMMENT", external_comment_id="reply-1",
        public_url="https://www.bilibili.com/video/BV1abc#reply:123")])
    assert validate_candidate_batch(payload, now=NOW)


def test_identity_scopes_public_web_by_normalized_origin():
    first=validate_candidate_batch(batch(platform="PUBLIC_WEB", execution=anonymous_execution(),
        records=[record(external_source_id="123", public_url="https://EXAMPLE.org/a")]), now=NOW).records[0]
    same=first.model_copy(update={"public_url":"https://example.org/other", "observed_at":"2026-09-09T02:30:00Z"})
    other=first.model_copy(update={"public_url":"https://example.net/a"})
    assert source_identity(first,"PUBLIC_WEB") == source_identity(same,"PUBLIC_WEB")
    assert source_identity(first,"PUBLIC_WEB") != source_identity(other,"PUBLIC_WEB")


def test_public_web_origin_identity_normalizes_trailing_dot():
    first=validate_candidate_batch(batch(platform="PUBLIC_WEB", execution=anonymous_execution(),
        records=[record(external_source_id="123", public_url="https://EXAMPLE.org./a")]), now=NOW).records[0]
    same=first.model_copy(update={"public_url":"https://example.org/other"})
    assert source_identity(first,"PUBLIC_WEB") == source_identity(same,"PUBLIC_WEB")


def test_public_web_origin_identity_normalizes_idna_and_unicode_dot_equivalents():
    urls = [
        "https://xn--bcher-kva.example/a",
        "https://bücher.example/b",
        "https://bücher。example/c",
        "https://xn--bcher-kva.example./d",
    ]
    parsed = [validate_candidate_batch(batch(platform="PUBLIC_WEB", execution=anonymous_execution(),
        records=[record(external_source_id="123", public_url=url)]), now=NOW).records[0] for url in urls]
    assert [item.public_url for item in parsed] == urls
    assert len({source_identity(item, "PUBLIC_WEB") for item in parsed}) == 1
    assert len({content_version(item) for item in parsed}) == len(urls)


def test_content_version_inputs_and_platform_scoped_identity():
    parsed=validate_candidate_batch(batch(), now=NOW).records[0]
    assert source_identity(parsed,"BILIBILI") != source_identity(parsed,"DOUYIN")
    observation=parsed.model_copy(update={"query":"第二词", "observed_at":"2026-09-09T02:30:00Z", "collector_version":"v2"})
    assert content_version(parsed)==content_version(observation)
    assert content_version(parsed)!=content_version(parsed.model_copy(update={"body":"新正文"}))
    parent={"external_comment_id":"reply-0", "body":None, "author_public_id":None,
            "published_at":None, "public_url":None}
    comment=validate_candidate_batch(batch(records=[record(kind="COMMENT", external_comment_id="reply-1", parent=parent)]), now=NOW).records[0]
    changed_parent=comment.model_copy(update={"parent":comment.parent.model_copy(update={"body":"父正文"})})
    assert content_version(comment)!=content_version(changed_parent)

def test_anonymous_web_identity_uses_full_url_and_unpaired_surrogate_is_rejected():
    first=validate_candidate_batch(batch(platform="PUBLIC_WEB", execution=anonymous_execution(), records=[
        record(kind="PAGE", external_source_id=None, public_url="https://example.org/a")]), now=NOW).records[0]
    second=first.model_copy(update={"public_url":"https://example.org/b"})
    assert source_identity(first,"PUBLIC_WEB") != source_identity(second,"PUBLIC_WEB")
    assert_code(batch(records=[record(body="bad\ud800")]), "INVALID_RECORD")


def test_duplicate_and_version_conflict_are_distinct():
    same=record(); assert_code(batch(records=[same,deepcopy(same)]), "DUPLICATE_RECORD")
    changed=deepcopy(same); changed["body"]="更新正文"
    assert_code(batch(records=[same,changed]), "SOURCE_VERSION_CONFLICT")


def test_batch_fingerprint_is_canonical_and_binds_fields_except_request_id():
    parsed=validate_candidate_batch(batch(), now=NOW)
    reordered=validate_candidate_batch(dict(reversed(list(batch().items()))), now=NOW)
    assert batch_fingerprint(parsed)==batch_fingerprint(reordered)
    assert batch_fingerprint(parsed)==batch_fingerprint(parsed.model_copy(update={"request_id":"request-2"}))
    for changed in [parsed.model_copy(update={"strategy_version_id":"strategy-2"}),
        parsed.model_copy(update={"profile_version_id":"profile-2"}),
        parsed.model_copy(update={"execution":parsed.execution.model_copy(update={"execution_generation":2})}),
        parsed.model_copy(update={"records":(parsed.records[0].model_copy(update={"observed_at":"2026-09-09T02:30:00Z"}),)})]:
        assert batch_fingerprint(parsed)!=batch_fingerprint(changed)


def test_replay_decision():
    digest=batch_fingerprint(validate_candidate_batch(batch(), now=NOW))
    assert replay_decision(None,digest)=="NEW" and replay_decision(digest,digest)=="REPLAY"
    assert replay_decision(digest,"different")=="CONFLICT"


def test_now_and_public_error_do_not_leak_input():
    with pytest.raises(ValueError, match="^now must be timezone-aware$"): validate_candidate_batch(batch(), now=datetime(2026,9,9))
    secret="SENSITIVE-CANDIDATE-VALUE-987"
    with pytest.raises(CandidateContractError) as caught:
        validate_candidate_batch(batch(records=[record(body=secret, public_url="https://bilibili.com/?token="+secret)]), now=NOW)
    assert secret not in str(caught.value) and secret not in repr(caught.value)
