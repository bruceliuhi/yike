from copy import deepcopy
from pathlib import Path
from uuid import UUID

import pytest

from pilot.research_context import ResearchContextError, compile_research_context


def context(**changes):
    value = {
        "schema_version": "research-context-v1",
        "profile_version_id": "11111111-1111-4111-8111-111111111111",
        "strategy_version_id": "22222222-2222-4222-8222-222222222222",
        "seller_description": "为制造企业交付 AI 质检和知识库项目。",
        "reference_time": "2026-09-13T09:30:00+08:00",
        "timezone": "Asia/Shanghai",
        "max_age_days": 30,
        "query_seeds": ["机器视觉质检"],
        "intent_signals": ["求供应商", "询价"],
        "exclusions": ["招聘"],
        "history_scope": "PARTIAL",
        "history": [{
            "project_key": "project-1",
            "description": "旧的质检项目",
            "state": "CONTACTED",
            "source_urls": ["https://example.com/projects/1"],
        }],
    }
    value.update(changes)
    return value


def assert_error(value, code="invalid_research_context"):
    with pytest.raises(ResearchContextError, match=f"^{code}$") as raised:
        compile_research_context(value)
    assert raised.value.code == code


def test_compiles_ai_and_non_ai_service_contexts_with_host_binding():
    ai = compile_research_context(context())
    non_ai = compile_research_context(context(
        seller_description="为企业提供展台设计搭建与现场执行。",
        query_seeds=["展台搭建供应商"], intent_signals=["寻找搭建商"],
    ))
    expected_keys = {"rule_version", "rule_sha256", "context_sha256",
                     "profile_version_id", "strategy_version_id"}
    assert set(ai) == {"instructions", "context_json", "binding"}
    assert set(ai["binding"]) == expected_keys
    assert ai["binding"]["rule_version"] == (
        "opportunity-research-context-v1/ai-project-lead-research-1.0.0")
    assert ai["binding"]["profile_version_id"] == context()["profile_version_id"]
    assert len(ai["binding"]["rule_sha256"]) == 64
    assert len(ai["binding"]["context_sha256"]) == 64
    assert "客户服务" in ai["instructions"]
    assert "HOST_RESEARCH_CONTEXT_JSON" in ai["instructions"]
    assert "30–60" in ai["instructions"]
    assert "展台设计搭建" in non_ai["context_json"]
    UUID(ai["binding"]["profile_version_id"])


@pytest.mark.parametrize("value", [None, [], "x", 1, True])
def test_rejects_non_plain_object(value):
    assert_error(value)


@pytest.mark.parametrize("change", [
    lambda v: v.pop("timezone"),
    lambda v: v.update(extra=True),
    lambda v: v.update(schema_version="research-context-v2"),
    lambda v: v.update(profile_version_id="11111111-1111-4111-8111-11111111111A"),
    lambda v: v.update(strategy_version_id=UUID(v["strategy_version_id"])),
    lambda v: v.update(max_age_days=True),
    lambda v: v.update(max_age_days=0),
    lambda v: v.update(timezone="No/Such"),
    lambda v: v.update(reference_time="2026-09-13T09:30:00"),
    lambda v: v.update(seller_description="bad\x00text"),
    lambda v: v.update(seller_description="\ud800"),
    lambda v: v.update(intent_signals=[]),
    lambda v: v.update(query_seeds=["x"] * 21),
    lambda v: v.update(exclusions=[""]),
    lambda v: v.update(history_scope="NONE"),
    lambda v: v.update(history_scope="FULL"),
    lambda v: v.update(history=[v["history"][0] | {"forged": True}]),
    lambda v: v.update(history=[v["history"][0] | {"source_urls": ["http://example.com"]}]),
    lambda v: v.update(history=[v["history"][0] | {"source_urls": ["https://u:p@example.com/x"]}]),
    lambda v: v.update(history=[v["history"][0] | {"source_urls": ["https://example.com/x?token=secret"]}]),
])
def test_rejects_invalid_shapes_scalars_time_unicode_history_and_urls(change):
    value = context()
    change(value)
    assert_error(value)


def test_none_scope_requires_empty_history_and_complete_allows_history():
    none = compile_research_context(context(history_scope="NONE", history=[]))
    complete = compile_research_context(context(history_scope="COMPLETE"))
    assert '"history":[]' in none["context_json"]
    assert '"history_scope":"COMPLETE"' in complete["context_json"]


@pytest.mark.parametrize("reference_time", [
    "2026-09-13T01:30:00Z",
    "2026-09-13T01:30:00+00:00",
])
def test_aware_utc_reference_time_is_valid_with_business_timezone(reference_time):
    result = compile_research_context(context(
        reference_time=reference_time, timezone="Asia/Shanghai"))
    assert f'"reference_time":"{reference_time}"' in result["context_json"]


def test_source_urls_use_anonymous_https_normalization():
    item = context()["history"][0] | {"source_urls": ["https://EXAMPLE.com"]}
    result = compile_research_context(context(history=[item]))
    assert '"source_urls":["https://example.com/"]' in result["context_json"]


def test_rejects_context_over_32_kib_and_credential_material():
    large = context(
        query_seeds=[f"{index:02d}" + "词" * 158 for index in range(20)],
        intent_signals=[f"{index:02d}" + "意" * 158 for index in range(20)],
        exclusions=[f"{index:02d}" + "排" * 158 for index in range(20)],
        history=[{
            "project_key": f"project-{index}", "description": "历" * 500,
            "state": "KNOWN", "source_urls": ["https://example.com/x"],
        } for index in range(30)],
    )
    assert_error(large)
    assert_error(context(seller_description="供应商 api_key=sk-live-1234567890abcdef"))


def test_canonical_hash_is_order_independent_and_content_bound():
    original = context()
    reversed_order = dict(reversed(list(original.items())))
    first = compile_research_context(original)
    reordered = compile_research_context(reversed_order)
    changed = compile_research_context(original | {"max_age_days": 31})
    assert first["context_json"] == reordered["context_json"]
    assert first["binding"] == reordered["binding"]
    assert first["binding"]["context_sha256"] != changed["binding"]["context_sha256"]
    copied = deepcopy(first)
    copied["binding"]["profile_version_id"] = "changed"
    assert compile_research_context(original)["binding"] == first["binding"]


def test_packaged_rule_directory_is_authoritative_and_missing_fails(monkeypatch, tmp_path):
    import pilot.research_context as module
    packaged = tmp_path / "_research_rules"
    packaged.mkdir()
    monkeypatch.setattr(module, "_PACKAGE_RULES", packaged)
    assert_error(context(), "research_rules_unavailable")


def test_each_source_rule_filename_and_text_participates_in_hash(monkeypatch, tmp_path):
    import pilot.research_context as module
    source = tmp_path / "skills" / "ai-project-lead-research-v1"
    (source / "references").mkdir(parents=True)
    for relative in module._RULE_FILES:
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"rule:{relative}\n", encoding="utf-8")
    monkeypatch.setattr(module, "_PACKAGE_RULES", tmp_path / "absent")
    monkeypatch.setattr(module, "_SOURCE_RULES", source)
    baseline = compile_research_context(context())["binding"]["rule_sha256"]
    for relative in module._RULE_FILES:
        target = source / relative
        original = target.read_text(encoding="utf-8")
        target.write_text(original + "changed\n", encoding="utf-8")
        assert compile_research_context(context())["binding"]["rule_sha256"] != baseline
        target.write_text(original, encoding="utf-8")


def test_oversize_or_invalid_utf8_rules_fail_with_fixed_error(monkeypatch, tmp_path):
    import pilot.research_context as module
    rules = tmp_path / "_research_rules"
    (rules / "references").mkdir(parents=True)
    for relative in module._RULE_FILES:
        target = rules / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("valid\n", encoding="utf-8")
    monkeypatch.setattr(module, "_PACKAGE_RULES", rules)
    (rules / module._RULE_FILES[0]).write_bytes(b"x" * (64 * 1024 + 1))
    assert_error(context(), "research_rules_unavailable")
    (rules / module._RULE_FILES[0]).write_bytes(b"\xff")
    assert_error(context(), "research_rules_unavailable")
