import hashlib
import json

import pytest

from pilot.execution_contract import ExecutionRuntimeError
import pilot.research_page_selection as selection_module
from pilot.research_page_selection import (
    SELECTION_INSTRUCTIONS,
    parse_page_selection,
    validate_page_selection,
)


def evidence(url="https://example.com/a", text="原文中的买方需求与报价请求"):
    return {"url": url, "text": text, "content_sha256": hashlib.sha256(text.encode()).hexdigest()}


def payload(pages, summary="逐页筛选完成"):
    return json.dumps({"schema_version": "research-page-selection-v1", "summary": summary,
                       "pages": pages}, ensure_ascii=False)


def decision(page, decision="ASSESS", reason="POSSIBLE_DEMAND", quote=None):
    return {"url": page["url"], "content_sha256": page["content_sha256"],
            "decision": decision, "reason": reason, "quote": quote or page["text"][:10]}


def test_parses_detached_mixed_decisions_and_collapses_duplicate_durable_version():
    first, second = evidence(), evidence("https://example.com/b", "这是行业索引页面")
    raw = [decision(first), decision(second, "BACKGROUND", "INDEX")]
    parsed = parse_page_selection(payload(raw), [first, dict(first), second])
    assert parsed == [raw[0] | {"schema_version": "research-page-selection-v1"},
                      raw[1] | {"schema_version": "research-page-selection-v1"}]
    parsed[0]["quote"] = "changed"
    assert raw[0]["quote"] != "changed"


@pytest.mark.parametrize("summary", [
    '```json\n{}\n```', '{"schema_version":"research-page-selection-v1"',
    '{"schema_version":"research-page-selection-v1","schema_version":"research-page-selection-v1","summary":"x","pages":[]}',
    '{"schema_version":"research-page-selection-v1","summary":"x","pages":[]} trailing',
    '{"schema_version":"research-page-selection-v1","summary":NaN,"pages":[]}',
])
def test_rejects_non_strict_json(summary):
    with pytest.raises(ExecutionRuntimeError, match="research_selection_invalid"):
        parse_page_selection(summary, [])


@pytest.mark.parametrize("mutate", [
    lambda root, page: root.update(extra=True),
    lambda root, page: page.update(extra=True),
    lambda root, page: root.update(schema_version="wrong"),
    lambda root, page: root.update(summary=""),
    lambda root, page: page.update(decision="MAYBE"),
    lambda root, page: page.update(reason="INDEX"),
    lambda root, page: page.update(quote="不存在"),
    lambda root, page: page.update(content_sha256="0" * 64),
    lambda root, page: page.update(url="https://example.com/other"),
])
def test_rejects_invalid_contract_or_evidence_mismatch(mutate):
    item = evidence(); page = decision(item); root = {
        "schema_version": "research-page-selection-v1", "summary": "x", "pages": [page]}
    mutate(root, page)
    with pytest.raises(ExecutionRuntimeError, match="research_selection_invalid"):
        parse_page_selection(json.dumps(root, ensure_ascii=False), [item])


def test_rejects_missing_duplicate_unread_and_bounds():
    first, second = evidence(), evidence("https://example.com/b", "第二页")
    bad = [
        payload([decision(first)]),
        payload([decision(first), decision(first)]),
        payload([decision(first), decision(evidence("https://example.com/c", "未读"))]),
        payload([decision(first, quote="字" * 401), decision(second)]),
        payload([decision(first), decision(second)], summary="字" * 2001),
    ]
    evidences = [[first, second], [first], [first, second], [first, second], [first, second]]
    for raw, durable in zip(bad, evidences):
        with pytest.raises(ExecutionRuntimeError, match="research_selection_invalid"):
            parse_page_selection(raw, durable)
    with pytest.raises(ExecutionRuntimeError, match="research_selection_invalid"):
        parse_page_selection("x" * (512 * 1024 + 1), [])


def test_validate_single_decision_and_instruction_uncertainty_policy():
    item = evidence(); value = decision(item) | {"schema_version": "research-page-selection-v1"}
    assert validate_page_selection(value, item) == value
    assert "ASSESS" in SELECTION_INSTRUCTIONS and "UNCERTAIN" in SELECTION_INSTRUCTIONS
    assert "预算" in SELECTION_INSTRUCTIONS and "身份" in SELECTION_INSTRUCTIONS
    assert "research-page-selection-v1" in SELECTION_INSTRUCTIONS


def test_selection_schema_is_exact_and_detached():
    assert callable(getattr(selection_module, "page_selection_schema", None))
    page_selection_schema = selection_module.page_selection_schema
    first = page_selection_schema()
    assert set(first["properties"]) == {"schema_version", "summary", "pages"}
    assert first["additionalProperties"] is False
    assert set(first["properties"]["pages"]["items"]["properties"]) == {
        "url", "content_sha256", "decision", "reason", "quote",
    }
    assert first["properties"]["schema_version"]["enum"] == [
        "research-page-selection-v1"
    ]
    assert first["properties"]["pages"]["items"]["properties"]["decision"]["enum"] == [
        "ASSESS", "BACKGROUND",
    ]
    assert set(first["properties"]["pages"]["items"]["properties"]["reason"]["enum"]) == {
        "POSSIBLE_DEMAND", "UNCERTAIN", "INDEX", "VENDOR_CONTENT",
        "NO_BUYER_SIGNAL", "STALE_OR_CLOSED", "IRRELEVANT",
    }
    first["properties"].clear()
    assert page_selection_schema()["properties"]


@pytest.mark.parametrize("raw,evidences", [
    ("\ud800", []),
    (payload([{"url": [], "content_sha256": {}, "decision": "ASSESS",
               "reason": "UNCERTAIN", "quote": "x"}]), []),
    (payload([decision(evidence(), quote=" ")]), [evidence()]),
    (payload([decision(evidence())]), [evidence() | {"text": 1}]),
])
def test_malformed_unicode_unhashable_identity_blank_quote_and_nontext_fail_fixed(raw, evidences):
    with pytest.raises(ExecutionRuntimeError, match="research_selection_invalid"):
        parse_page_selection(raw, evidences)


def test_duplicate_durable_version_can_differ_in_nonidentity_metadata():
    item = evidence()
    duplicate = item | {"title": "另一次读取标题", "observed_at": "later"}
    assert len(parse_page_selection(payload([decision(item)]), [item, duplicate])) == 1


def test_oversized_json_integer_uses_fixed_selection_error_without_relaxing_interpreter_limit():
    raw = ('{"schema_version":"research-page-selection-v1","summary":'
           + '1' * 5000 + ',"pages":[]}')
    with pytest.raises(ExecutionRuntimeError, match="research_selection_invalid"):
        parse_page_selection(raw, [])
