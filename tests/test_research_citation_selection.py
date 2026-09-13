import hashlib
import importlib
import importlib.util
import json

import pytest

from pilot.execution_contract import ExecutionRuntimeError
from pilot.research_page_selection import parse_page_selection


def citation_module():
    assert importlib.util.find_spec("pilot.research_citation_selection") is not None
    return importlib.import_module("pilot.research_citation_selection")


def evidence(url, text):
    return {"url": url, "text": text,
            "content_sha256": hashlib.sha256(text.encode()).hexdigest()}


def choice(pages, summary="逐页引用选择完成"):
    return json.dumps({"schema_version": "research-citation-choice-v1",
                       "summary": summary, "pages": pages}, ensure_ascii=False)


def page(item, quote_ref="q1", decision="ASSESS", reason="POSSIBLE_DEMAND"):
    return {"url": item["url"], "content_sha256": item["content_sha256"],
            "decision": decision, "reason": reason, "quote_ref": quote_ref}


def test_citation_fragments_preserve_original_unicode_and_long_tail():
    module = citation_module()
    text = "甲\n🙂e\u0301 " * 101
    pieces = module.citation_fragments(text)
    assert "".join(item["text"] for item in pieces) == text
    assert all(1 <= len(item["text"]) <= 400 for item in pieces)
    assert [item["quote_ref"] for item in pieces] == [f"q{i}" for i in range(1, len(pieces)+1)]
    assert pieces[-1]["text"] == text[400 * (len(pieces)-1):]


def test_citation_schema_is_exact_and_detached():
    module = citation_module()
    first = module.citation_choice_schema()
    assert set(first["properties"]) == {"schema_version", "summary", "pages"}
    assert first["properties"]["schema_version"]["enum"] == ["research-citation-choice-v1"]
    item = first["properties"]["pages"]["items"]
    assert set(item["properties"]) == {
        "url", "content_sha256", "decision", "reason", "quote_ref",
    }
    assert "quote" not in item["required"] and "quote_ref" in item["required"]
    first["properties"].clear()
    assert module.citation_choice_schema()["properties"]


def test_expand_choices_reconstructs_only_host_fragments_then_passes_original_parser():
    module = citation_module()
    first = evidence("https://example.com/a", "前" * 400 + "后部需求：找团队报价。")
    second = evidence("https://example.com/b", "行业目录，仅作背景。")
    raw = choice([
        page(first, "q2"),
        page(second, "q1", decision="BACKGROUND", reason="INDEX"),
    ])
    expanded = module.expand_citation_choices(raw, [first, second])
    parsed = parse_page_selection(expanded, [first, second])
    assert parsed[0]["quote"] == first["text"][400:]
    assert parsed[1]["quote"] == second["text"]
    assert json.loads(expanded)["schema_version"] == "research-page-selection-v1"


@pytest.mark.parametrize("raw,evidences", [
    (lambda a, b: choice([page(a, "q0"), page(b)]), None),
    (lambda a, b: choice([page(a, "q2"), page(b)]), None),
    (lambda a, b: choice([page(a), page(b) | {"content_sha256": "0" * 64}]), None),
    (lambda a, b: choice([page(a), page(a)]), None),
    (lambda a, b: choice([page(a)]), None),
    (lambda a, b: choice([page(a), page(b) | {"extra": True}]), None),
    (lambda a, b: choice([page(a), page(b)]).replace(
        '"schema_version": "research-citation-choice-v1"',
        '"schema_version": "research-citation-choice-v1", "schema_version": "research-citation-choice-v1"'), None),
    (lambda a, b: json.dumps({"schema_version":"research-page-selection-v1",
        "summary":"不得降级", "pages":[page(a), page(b)]}, ensure_ascii=False), None),
])
def test_expand_rejects_bad_ref_cross_page_hash_duplicate_missing_extra_rekey_and_v1(raw, evidences):
    module = citation_module()
    first = evidence("https://example.com/a", "短页")
    second = evidence("https://example.com/b", "另一页" * 150)
    with pytest.raises(ExecutionRuntimeError, match="^research_selection_invalid$"):
        module.expand_citation_choices(raw(first, second), evidences or [first, second])


def test_whitespace_fragment_is_not_promoted_past_original_literal_validator():
    module = citation_module()
    item = evidence("https://example.com/space", " " * 400 + "真实需求")
    with pytest.raises(ExecutionRuntimeError, match="^research_selection_invalid$"):
        module.expand_citation_choices(choice([page(item, "q1")]), [item])


def test_expand_rejects_unbounded_numeric_quote_ref_with_fixed_error():
    module = citation_module()
    item = evidence("https://example.com/long-ref", "真实需求")
    with pytest.raises(ExecutionRuntimeError, match="^research_selection_invalid$"):
        module.expand_citation_choices(choice([page(item, "q" + "9" * 5000)]), [item])
