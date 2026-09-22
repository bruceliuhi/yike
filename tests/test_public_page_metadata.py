"""Publisher-declared metadata is evidence, not verified buyer identity."""
import hashlib

import pytest
from pydantic import ValidationError

from pilot import open_web_reader_worker as worker
from pilot.open_web_reader import valid_page_evidence
from pilot.dynamic_research_candidates import _record
from pilot.candidate_contract import CandidateRecord, content_version
from tests.test_open_web_reader import install_transport, response


def metadata(raw="2026-09-04", *, value=None, precision="DATE"):
    return {
        "schema_version": "public-page-metadata-v1",
        "publication": {"raw": raw, "declaration": "article:published_time",
                        "value": value or raw, "precision": precision},
        "author": {"raw": "企业采购部", "declaration": "author", "value": "企业采购部"},
    }


def evidence(meta=None):
    text = "我们需要企业知识库方案与报价。"
    result = {"url": "https://example.com/buyer", "title": "采购需求", "text": text,
              "observed_at": "2026-09-21T12:00:00Z", "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
              "read_scope": "PUBLIC_PAGE_TEXT"}
    if meta is not None:
        result["page_metadata"] = meta
    return result


@pytest.mark.parametrize("raw,value,precision", [
    ("2026-09-04", "2026-09-04", "DATE"),
    ("2026-09-04T11:20:30+08:00", "2026-09-04T03:20:30Z", "SECOND"),
    ("2026-09-04 11:20:30", "2026-09-04T11:20:30", "LOCAL_SECOND"),
])
def test_reader_retains_declared_metadata_without_changing_original(monkeypatch, raw, value, precision):
    html = ('<html><head><title>采购需求</title>'
            f'<meta property="article:published_time" content="{raw}">'
            '<meta name="author" content="企业采购部"></head>'
            '<body>我们需要企业知识库方案与报价。</body></html>')
    install_transport(monkeypatch, response(html.encode()))
    result = worker.read_request({"url": "https://example.com/buyer", "timeout_seconds": 3})
    assert result.get("page_metadata") == metadata(raw, value=value, precision=precision)
    assert result["text"] == evidence()["text"]
    assert result["content_sha256"] == evidence()["content_sha256"]
    assert valid_page_evidence(result, result["url"])


@pytest.mark.parametrize("head", [
    '<meta property="article:modified_time" content="2026-09-04">',
    '<meta property="article:published_time" content="2026-02-30">',
    '<meta property="article:published_time" content="2099-09-04">',
    '<meta property="article:published_time" content="2026-09-04"><meta name="datepublished" content="2026-09-05">',
    '<meta name="author" content="甲"><meta name="author" content="乙">',
])
def test_ambiguous_invalid_future_or_modified_claims_do_not_become_publication(monkeypatch, head):
    install_transport(monkeypatch, response(f'<html><head>{head}</head><body>需求原文</body></html>'.encode()))
    result = worker.read_request({"url": "https://example.com/", "timeout_seconds": 3})
    assert "page_metadata" not in result


def test_body_template_script_metadata_is_not_page_metadata(monkeypatch):
    html = '<html><head><template><meta name="author" content="伪作者"></template></head><body><meta name="author" content="评论者">需求</body></html>'
    install_transport(monkeypatch, response(html.encode()))
    result = worker.read_request({"url": "https://example.com/", "timeout_seconds": 3})
    assert "page_metadata" not in result


@pytest.mark.parametrize("html", [
    '<html><head><title>需求</title><div>正文<meta name="author" content="评论者"></div></html>',
    '<html><head><title>需求</title>正文<meta name="author" content="评论者"></html>',
    '<html><head></head><body>正文<head><meta name="author" content="评论者"></head></body></html>',
    '<html><head><title><meta name="author" content="评论者"></title></head><body>正文</body></html>',
])
def test_implicit_body_or_title_metadata_is_not_publisher_declaration(monkeypatch, html):
    install_transport(monkeypatch, response(html.encode()))
    result = worker.read_request({"url": "https://example.com/", "timeout_seconds": 3})
    assert "page_metadata" not in result


@pytest.mark.parametrize("attributes", [
    'name="author" content="甲" content="乙"',
    'name="author" name="datepublished" content="2026-09-04"',
    'property="article:published_time" property="author" content="2026-09-04"',
])
def test_duplicate_critical_meta_attributes_are_ambiguous(monkeypatch, attributes):
    html = f'<html><head><meta {attributes}></head><body>需求原文</body></html>'
    install_transport(monkeypatch, response(html.encode()))
    result = worker.read_request({"url": "https://example.com/", "timeout_seconds": 3})
    assert "page_metadata" not in result


@pytest.mark.parametrize("meta", [metadata(), metadata("2026-09-04T03:20:30Z", precision="SECOND"),
                                  metadata("2026-09-04T03:20:30", precision="LOCAL_SECOND")])
def test_exact_metadata_passes_evidence_boundary(meta):
    value = evidence(meta)
    assert valid_page_evidence(value, value["url"])


@pytest.mark.parametrize("field,value", [("value", "2026-09-05"), ("raw", "2026-02-30"),
                                        ("precision", "MINUTE"), ("declaration", "article:modified_time")])
def test_metadata_claims_cannot_change_during_validation(field, value):
    meta = metadata(); meta["publication"][field] = value
    result = evidence(meta)
    assert not valid_page_evidence(result, result["url"])


@pytest.mark.parametrize("meta", [metadata(), metadata("2026-09-04T11:20:30+08:00", value="2026-09-04T03:20:30Z", precision="SECOND")])
def test_candidate_keeps_metadata_and_does_not_invent_identity_or_midnight(meta):
    record = _record({"result": {"evidence": evidence(meta)}})
    assert record is not None
    assert record.model_dump().get("page_metadata") == meta
    assert record.author_public_id is None
    assert record.published_at == (meta["publication"]["value"] if meta["publication"]["precision"] == "SECOND" else None)
    assert record.normalizer_version == "dynamic-public-read-v2"
    assert content_version(record) != content_version(_record({"result": {"evidence": evidence()}}))


def test_candidate_rejects_metadata_on_other_sources_and_mismatched_projection():
    legacy = _record({"result": {"evidence": evidence()}}).model_dump()
    current = legacy | {"page_metadata": metadata(), "normalizer_version": "dynamic-public-read-v2"}
    assert CandidateRecord.model_validate(current).model_dump()["page_metadata"] == metadata()
    for patch in ({"kind": "POST"}, {"author_public_id": "inferred-buyer"},
                  {"normalizer_version": "legacy"}, {"published_at": "2026-09-04T00:00:00Z"},
                  {"collector_version": "other-reader-v1"},
                  {"page_metadata": None}):
        with pytest.raises(ValidationError):
            CandidateRecord.model_validate(current | patch)


def test_absent_metadata_does_not_change_legacy_content_hash():
    record = _record({"result": {"evidence": evidence()}})
    assert "page_metadata" not in record.model_dump()
    assert record.normalizer_version == "dynamic-public-read-v1"
    assert record.published_at is None


def test_fixed_evidence_preserves_page_claims_separately_from_verification():
    from pilot.opportunity_evidence import _public_source
    record = _record({"result": {"evidence": evidence(metadata())}})
    raw = {"kind": "PAGE", "platform": "PUBLIC_WEB", "external_source_id": "source",
           "external_comment_id": None, "version_id": "version", "content_version": content_version(record),
           "content": record.model_dump()}
    source = _public_source(raw)
    assert source.get("page_metadata") == metadata()
    assert source["author_public_id"] is None and source["published_at"] is None


def test_metadata_does_not_change_old_hashes_but_distinct_claim_is_new_version():
    record = _record({"result": {"evidence": evidence(metadata())}})
    other = metadata(); other["author"] = {"raw": "另一发布者", "declaration": "author", "value": "另一发布者"}
    changed = _record({"result": {"evidence": evidence(other)}})
    assert record.body == changed.body
    assert content_version(record) != content_version(changed)


def test_author_declaration_rejects_boundary_bom_consistently_with_client():
    meta = metadata(); meta["author"]["raw"] = meta["author"]["value"] = "\ufeff采购部"
    with pytest.raises(ValueError):
        worker.validate_page_metadata(meta)


@pytest.mark.parametrize("raw", ["2026-02-30", "2026-09-04T23:00:00+14:01", "2026-09-04T23:00:00+08:65",
                               "2026-09-04T23:00", "2026-09-04T23:00:00.123Z", "2026-09-04T23:00:00+15:00"])
def test_publication_does_not_silently_normalize_bad_dates_or_offsets(raw):
    with pytest.raises(ValueError):
        worker.validate_page_metadata(metadata(raw), observed_at="2026-09-21T00:00:00Z")


@pytest.mark.parametrize("raw", ["0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59-14:00"])
def test_publication_offset_outside_supported_calendar_is_validation_error(raw):
    with pytest.raises(ValueError):
        worker.validate_page_metadata(metadata(raw, precision="SECOND"))


def test_future_local_bound_is_not_used_as_a_publication_timezone():
    meta = metadata("2026-09-22T02:00:00", precision="LOCAL_SECOND")
    assert worker.validate_page_metadata(meta, observed_at="2026-09-21T12:00:00Z") == meta
    with pytest.raises(ValueError):
        worker.validate_page_metadata(meta, observed_at="2026-09-21T11:59:59Z")


def test_declared_metadata_does_not_bypass_human_buyer_attribution():
    from pilot.candidate_demand_evidence import is_dynamic, project_content
    record = _record({"result": {"evidence": evidence(metadata())}})
    raw = {"kind": "PAGE", "normalizer_version": record.normalizer_version,
           "collector_version": record.collector_version}
    assert is_dynamic(raw)
    original = {"title": record.title, "body": record.body, "parent": None}
    projected = project_content(original, raw, None)
    assert projected["source_read_scope"] == "UNATTRIBUTED_PAGE"
    assert projected["author_updates"] == []


def test_raw_runtime_revalidation_preserves_absence_without_hiding_forged_null():
    from pilot.execution_runtime import _raw_model
    legacy = _record({"result": {"evidence": evidence()}})
    assert "page_metadata" not in _raw_model(legacy)
    forged = legacy.model_copy(update={"page_metadata": None})
    assert "page_metadata" in _raw_model(forged)
    with pytest.raises(ValidationError):
        CandidateRecord.model_validate(_raw_model(forged))


def test_fixed_metadata_survives_signed_digest_and_corrupt_claim_is_rejected():
    from copy import deepcopy
    from datetime import UTC, datetime
    from tests.test_opportunity_evidence import inputs, OPPORTUNITY_ID, PROFILE_ID
    from pilot.opportunity_evidence import build_evidence, evidence_view, evidence_digest, OpportunityEvidenceError
    snapshot, assessment, observation, verification = inputs(kind="PAGE")
    raw = snapshot["raw"]; raw["platform"] = "PUBLIC_WEB"
    content = raw["content"]
    content.update(public_url="https://example.com/buyer", author_public_id=None,
                   published_at=None, page_metadata=metadata())
    raw["content_version"] = evidence_digest(content)
    assessment["businessMatch"]["citations"] = [{"field": "title", "quote": "食品工厂"}]
    assessment["urgency"]["citations"] = []
    payload = build_evidence(opportunity_id=OPPORTUNITY_ID, snapshot=snapshot, assessment=assessment,
        observation=observation, verification=verification, captured_at=datetime(2026, 9, 9, 10, tzinfo=UTC))
    viewed = evidence_view(payload, evidence_digest(payload), opportunity_id=OPPORTUNITY_ID, profile_version_id=PROFILE_ID)
    assert viewed["snapshot"]["source"]["page_metadata"] == metadata()
    invalid = deepcopy(payload); invalid["source"]["page_metadata"]["publication"]["value"] = "2026-09-05"
    # Even recomputing the outer digest must not make an inconsistent claim valid.
    with pytest.raises(OpportunityEvidenceError):
        evidence_view(invalid, evidence_digest(invalid), opportunity_id=OPPORTUNITY_ID, profile_version_id=PROFILE_ID)
