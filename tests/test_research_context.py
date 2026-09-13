from copy import deepcopy
import hashlib
import json
from pathlib import Path
from uuid import UUID

import pytest

from pilot.research_context import (
    ResearchContextError, compile_research_context, project_research_context_v2,
)
from pilot.research_strategy_contract import configuration_digest, strategy_snapshot


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


def dynamic_snapshot(*, industry=True):
    configuration = {
        "schema_version": "research-strategy-v1", "name": "客户动态研究",
        "source": "search", "keywords": ["机器视觉质检", "工厂知识库"],
        "exclusions": ["招聘"], "links": [], "mode": "once", "schedule": None,
        "research": {"version": 1, "demandTypes": ["INQUIRY", "CHANGE"],
                     "maxSoubei": 100, "limits": {"sources": 20, "minutes": 30, "modelCalls": 10},
                     "stopAtAnyLimit": True, "evidenceOrder": "SOURCE_MATCH_CONTEXT",
                     "dynamicScope": {"version": 1, "maxAgeDays": 60, "timezone": "Asia/Shanghai"}},
        "publicSource": "public-web-agent-v1",
    }
    if industry:
        configuration["industryStrategy"] = {
            "version": "industry-task-strategy-v1", "sourceTypes": ["PROCUREMENT", "COMPANY_UPDATE"],
            "intentSignals": ["正在寻找质检供应商"], "counterSignals": ["同行广告"],
        }
    return strategy_snapshot(
        context()["profile_version_id"], context()["strategy_version_id"],
        configuration, ["PUBLIC_WEB"], 20, 600,
    )


def projected_v2(**changes):
    snapshot = dynamic_snapshot()
    value = project_research_context_v2(
        seller_description="第一行：制造业客户\n第二行：AI 质检与知识库。",
        profile_sha256="a" * 64, strategy_snapshot=snapshot,
        reference_time="2026-09-13T09:30:00+08:00", history_scope="NONE", history=[],
    )
    value.update(changes)
    return value


def test_projects_and_compiles_complete_dynamic_snapshot_context_v2():
    value = projected_v2()
    assert value["schema_version"] == "research-context-v2"
    assert value["seller_description"].startswith("第一行") and "\n第二行" in value["seller_description"]
    assert value["strategy_snapshot"] == dynamic_snapshot()
    assert value["query_seeds"] == ["机器视觉质检", "工厂知识库"]
    assert value["exclusions"] == ["招聘", "同行广告"]
    assert value["intent_signals"] == ["正在寻找质检供应商"]
    result = compile_research_context(value)
    assert result["binding"]["schema_version"] == "research-context-v2"
    assert result["binding"]["profile_sha256"] == "a" * 64
    assert result["binding"]["configuration_sha256"] == configuration_digest(dynamic_snapshot())
    assert result["binding"]["rule_version"].startswith("opportunity-research-context-v2/")
    assert compile_research_context(deepcopy(value))["binding"] == result["binding"]


def test_v2_uses_fixed_demand_fallback_without_industry_strategy():
    snapshot = dynamic_snapshot(industry=False)
    value = project_research_context_v2(
        seller_description="企业系统实施", profile_sha256="b" * 64,
        strategy_snapshot=snapshot, reference_time="2026-09-13T09:30:00+08:00",
        history_scope="NONE", history=[],
    )
    assert value["intent_signals"] == [
        "询问方案、价格或寻找供应商", "明确业务变化并寻找外部解决方案"]
    compile_research_context(value)


@pytest.mark.parametrize(("with_research", "with_industry"), [
    (False, False), (False, True), (True, False), (True, True),
])
def test_v2_rejects_valid_legacy_snapshot_without_dynamic_scope_fail_closed(
        with_research, with_industry):
    configuration = deepcopy(dynamic_snapshot()["configuration"])
    configuration.pop("publicSource")
    if with_research:
        configuration["research"].pop("dynamicScope")
    else:
        configuration["research"] = None
    if not with_industry:
        configuration.pop("industryStrategy")
    legacy = strategy_snapshot(
        context()["profile_version_id"], context()["strategy_version_id"],
        configuration, ["PUBLIC_WEB"], 20, 600,
    )
    value = projected_v2(strategy_snapshot=legacy)
    assert_error(value)


def test_v2_preserves_8000_multiline_profile_and_v1_limits_remain_unchanged():
    seller = "甲\n" + "乙" * 7998
    assert compile_research_context(projected_v2(seller_description=seller))["context_json"]
    assert_error(context(seller_description="甲\n乙"))
    assert_error(context(seller_description="甲" * 4001))


@pytest.mark.parametrize("change", [
    {"profile_sha256": "A" * 64}, {"profile_sha256": "a" * 63},
    {"seller_description": "bad\x00text"},
    {"seller_description": "api_key=sk-live-1234567890abcdef"},
    {"profile_version_id": "33333333-3333-4333-8333-333333333333"},
    {"max_age_days": 61}, {"timezone": "Etc/UTC"},
    {"query_seeds": ["伪造查询"]}, {"exclusions": ["伪造排除"]},
])
def test_v2_rejects_bad_hash_text_and_projection_mismatches(change):
    assert_error(projected_v2(**change))


def test_v2_secret_scans_complete_strategy():
    value = projected_v2()
    value["strategy_snapshot"]["configuration"]["name"] = "password=synthetic-secret"
    assert_error(value)


def test_v2_accepts_large_valid_profile_and_partial_history():
    value=projected_v2(history=[{
        "project_key": f"project-{index}", "description": "历" * 500,
        "state": "KNOWN", "source_urls": ["https://example.com/" + "x" * 2000] * 3,
    } for index in range(30)], history_scope="PARTIAL",
        seller_description="甲" * 8000)
    compiled=compile_research_context(value)
    assert 250000 < len(compiled['context_json'].encode('utf-8')) < 512*1024
    assert json.loads(compiled['context_json'])==value


def test_v2_byte_guard_precedes_rule_loading_with_injected_encoded_size(monkeypatch):
    import pilot.research_context as module
    value=projected_v2()
    encode=module._canonical_json
    # Isolate the encoded-size guard; this is not a claim that valid field
    # maxima naturally exceed the deliberately generous 512 KiB budget.
    def oversized_context(item):
        encoded=encode(item)
        return encoded+' '* (512*1024) if item.get('schema_version')=='research-context-v2' else encoded
    monkeypatch.setattr(module,'_canonical_json',oversized_context)
    monkeypatch.setattr(module,'_load_rules',lambda:pytest.fail('oversize must reject before loading rules'))
    assert_error(value)


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
    assert set(ai) == {"instructions", "context_json", "binding", "entry_urls"}
    assert set(ai["binding"]) == expected_keys
    assert ai["binding"]["rule_version"] == (
        "opportunity-research-context-v1/ai-project-lead-research-1.0.0/entry-hints-v1/page-selection-v1/trusted-entries-v1/efficient-handoff-v1")
    assert ai["binding"]["profile_version_id"] == context()["profile_version_id"]
    assert len(ai["binding"]["rule_sha256"]) == 64
    assert len(ai["binding"]["context_sha256"]) == 64
    assert "客户服务" in ai["instructions"]
    assert "HOST_RESEARCH_CONTEXT_JSON" in ai["instructions"]
    assert "30–60" in ai["instructions"]
    assert "展台设计搭建" in non_ai["context_json"]
    assert "仅在客户行业与技术社区匹配时" in non_ai["instructions"]
    assert non_ai["binding"]["rule_sha256"] == hashlib.sha256(
        non_ai["instructions"].encode("utf-8")
    ).hexdigest()
    UUID(ai["binding"]["profile_version_id"])


def test_catalog_entry_hints_are_public_conditional_and_complete():
    from pilot.research_source_catalog import SOURCE_IDS, research_entry_hints

    hints = research_entry_hints()
    assert all(source_id in hints for source_id in SOURCE_IDS)
    assert "https://www.v2ex.com/recent" in hints
    assert "https://www.v2ex.com/go/qna" in hints
    assert "https://www.v2ex.com/go/outsourcing" in hints
    assert "/api/" not in hints
    assert "节点页不同于标签页" in hints
    assert "仅在客户行业与技术社区匹配时" in hints
    assert "搜索结果或成功读页链接" in hints
    assert "不得登录或重试" in hints
    assert "不代表穷尽" in hints


def test_compiler_derives_catalog_and_known_history_but_exact_negative_wins():
    known = "https://example.com/known-entry"
    blocked = "https://example.com/blocked-entry"
    prose_only = "https://example.com/prose-only"
    value = context(
        seller_description="服务说明 " + prose_only,
        query_seeds=[prose_only],
        history=[
            {"project_key":"known", "description":"已知", "state":"KNOWN",
             "source_urls":[known, blocked]},
            {"project_key":"closed", "description":"关闭", "state":"CLOSED",
             "source_urls":[blocked]},
        ],
    )
    compiled = compile_research_context(value)
    assert compiled["entry_urls"] == (
        "https://www.v2ex.com/recent",
        "https://www.v2ex.com/go/qna",
        "https://www.v2ex.com/go/outsourcing",
        known,
    )
    assert blocked not in compiled["entry_urls"] and prose_only not in compiled["entry_urls"]
    assert "/trusted-entries-v1/efficient-handoff-v1" in compiled["binding"]["rule_version"]
    detached = compiled["entry_urls"]
    value["history"][0]["source_urls"].append("https://example.com/later")
    assert detached == compiled["entry_urls"]


def test_compiler_entry_order_is_stable_and_capped_at_twenty():
    history = [{"project_key":f"known-{index}", "description":"已知", "state":"KNOWN",
                "source_urls":[f"https://example.com/known-{index}"]}
               for index in range(20)]
    entries = compile_research_context(context(history=history))["entry_urls"]
    assert len(entries) == 20
    assert entries[:3] == ("https://www.v2ex.com/recent", "https://www.v2ex.com/go/qna",
                           "https://www.v2ex.com/go/outsourcing")
    assert entries[-1] == "https://example.com/known-16"


def test_changed_entry_hints_change_only_rule_binding(monkeypatch):
    import pilot.research_context as module

    baseline = compile_research_context(context())
    monkeypatch.setattr(module, "research_entry_hints", lambda: "changed advisory hints")
    changed = compile_research_context(context())
    assert changed["binding"]["rule_sha256"] != baseline["binding"]["rule_sha256"]
    assert changed["binding"]["context_sha256"] == baseline["binding"]["context_sha256"]
    assert changed["context_json"] == baseline["context_json"]
    assert changed["binding"]["rule_sha256"] == hashlib.sha256(
        changed["instructions"].encode("utf-8")
    ).hexdigest()


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


def test_page_selection_contract_is_versioned_and_participates_in_rule_hash():
    from pilot.research_page_selection import SELECTION_INSTRUCTIONS
    result = compile_research_context(context())
    assert result["instructions"].endswith(SELECTION_INSTRUCTIONS)
    assert "/page-selection-v1/" in result["binding"]["rule_version"]
    assert result["binding"]["rule_sha256"] == hashlib.sha256(
        result["instructions"].encode("utf-8")
    ).hexdigest()


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


def test_compiled_stage_projection_is_shorter_and_preserves_business_rules():
    import pilot.research_context as module

    documents = module._load_rules()
    compiled = compile_research_context(context())
    instructions = compiled["instructions"]
    assert len(instructions.encode("utf-8")) < sum(
        len(value.encode("utf-8")) for value in documents.values()
    )
    for filename, contents in sorted(documents.items()):
        digest = hashlib.sha256(contents.encode("utf-8")).hexdigest()
        assert f"{filename}: sha256:{digest}" in instructions
    for phrase in (
        "客户画像优先", "业务问题", "可交付物", "采购动作", "四条发现路径",
        "直接寻源", "失败/替换", "需求评论", "带在手项目", "独立来源",
        "作者扩展", "搜索摘要", "作者原文时间", "第三方回复", "评论作者时间",
        "购买对象", "资金归属", "硬件支出", "会员费用", "工资", "第三方报价",
        "预算未知", "联系路径未知", "成果", "驻场", "按成果结算", "DIY",
        "本人业务询价", "中间方", "反证", "净新增", "人工批准", "只读",
    ):
        assert phrase in instructions
    assert "不写入文件" in instructions
    assert "不生成联系内容" in instructions


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
