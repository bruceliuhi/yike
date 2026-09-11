"""Offline strategy contract and transport checks; no model network or quality claim."""
from copy import deepcopy
import json

import httpx
import pytest

import pilot.search_suggestion_model as suggestion_model
from pilot.search_suggestion_model import (
    OpenAICompatibleSearchSuggestionModel,
    SearchSuggestionError,
    validate_suggestion,
)


DESCRIPTION = "我们为食品工厂提供不锈钢输送设备，由工厂采购负责人决策，采用现场测量和定制交付。"


def suggestion(*, strategy=True):
    value = {
        "keywords": ["食品输送线 定制"], "exclusions": ["招聘"],
        "rationale": "建议从采购角色和定制交付方式寻找需求表达，并优先关注采购内容。",
        "evidence": ["食品工厂", "不锈钢输送设备"], "unknowns": ["预算未说明"],
    }
    if strategy:
        value["strategy"] = {
            "version": "industry-search-strategy-v1", "buyerRole": "工厂采购负责人",
            "salesMotion": "现场测量和定制交付", "sourceTypes": ["PROCUREMENT", "SOCIAL_POST"],
            "intentSignals": ["正在寻找供应商"], "counterSignals": ["同行服务广告"],
            "basis": ["食品工厂", "现场测量和定制交付"],
        }
    return value


def envelope(payload):
    return {"choices": [{"finish_reason": "stop", "message": {
        "role": "assistant", "content": json.dumps(payload, ensure_ascii=False), "refusal": None,
    }}]}


def adapter(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICompatibleSearchSuggestionModel(
        base_url="https://model.example/v1", api_key="synthetic-key", model="synthetic-model",
        http_client=client,
    ), client


def test_strategy_validates_and_serializes_verbatim_while_legacy_omits_the_field():
    payload = suggestion()
    before = deepcopy(payload)
    assert suggestion_model.serialize_suggestion(validate_suggestion(payload, description=DESCRIPTION)) == before
    assert payload == before
    missing = suggestion()
    missing["strategy"].update(buyerRole=None, salesMotion=None)
    assert suggestion_model.serialize_suggestion(
        validate_suggestion(missing, description=DESCRIPTION))["strategy"] == missing["strategy"]
    legacy = suggestion(strategy=False)
    assert suggestion_model.serialize_suggestion(validate_suggestion(legacy, description=DESCRIPTION)) == legacy
    assert "strategy" not in suggestion_model.serialize_suggestion(validate_suggestion(legacy, description=DESCRIPTION))


@pytest.mark.parametrize("change", [
    {"version": "industry-search-strategy-v2"},
    {"buyerRole": "董事长"},
    {"salesMotion": "订阅制"},
    {"basis": ["并不存在的画像依据"]},
    {"sourceTypes": ["DOUYIN"]},
    {"intentSignals": [" 采购需求 ", "采购需求"]},
    {"unexpectedPermission": "APPROVED"},
])
def test_strategy_rejects_unknown_forged_duplicate_and_extra_values(change):
    payload = suggestion()
    payload["strategy"].update(change)
    with pytest.raises(SearchSuggestionError, match="invalid_suggestion_result"):
        validate_suggestion(payload, description=DESCRIPTION)


def test_current_adapter_requires_strategy_in_schema_and_response():
    captured = {}

    def handle(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, json=envelope(suggestion()))

    model, client = adapter(handle)
    try:
        result, usage = model.generate(description=DESCRIPTION)
    finally:
        client.close()
    schema = captured["response_format"]["json_schema"]
    assert schema["strict"] is True
    assert "strategy" in schema["schema"]["required"]
    assert schema["schema"]["properties"]["strategy"]["$ref"].endswith("RequiredIndustrySearchStrategy")
    assert result.strategy.version == "industry-search-strategy-v1"
    assert suggestion_model.serialize_suggestion(result) == suggestion()
    assert usage is None
    system = captured["messages"][0]["content"]
    assert all(text in system for text in ("买方角色", "交易/交付方式", "sourceTypes", "unknowns"))


def test_current_adapter_rejects_legacy_response_without_strategy():
    model, client = adapter(lambda request: httpx.Response(200, json=envelope(suggestion(strategy=False))))
    try:
        with pytest.raises(SearchSuggestionError) as raised:
            model.generate(description=DESCRIPTION)
    finally:
        client.close()
    assert (raised.value.code, raised.value.status) == ("invalid_suggestion_result", 502)
