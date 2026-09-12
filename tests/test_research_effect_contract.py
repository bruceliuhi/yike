from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pytest

from pilot.execution_contract import ExecutionRuntimeError
from pilot.research_context import compile_research_context
from pilot.research_effect_contract import effect_input, effect_result
from pilot.responses_bridge import _alias
from tests.test_research_context import projected_v2


def binding():
    return compile_research_context(projected_v2())["binding"]


@pytest.mark.parametrize("code", ["not_found", "unsupported_media_type", "too_large"])
def test_known_read_failure_is_separate_copied_exact_contract(code):
    from pilot import research_effect_contract as contract
    result = {"status": "FAILED", "code": code, "replayed": False}
    validator = getattr(contract, "known_read_failure", None)
    assert callable(validator)
    actual = validator("READ", {"url": "https://example.com/"}, result)
    assert actual == result and actual is not result
    assert contract.is_known_read_failure("READ", {"url": "https://example.com/"}, result)
    with pytest.raises(ExecutionRuntimeError):
        effect_result("READ", {"url": "https://example.com/"}, result)


@pytest.mark.parametrize("kind,payload,patch", [
    ("MODEL", {"url": "https://example.com/"}, {}),
    ("SEARCH", {"url": "https://example.com/"}, {}),
    ("READ", {"url": "https://example.com/#fragment"}, {}),
    ("READ", {"url": "https://example.com/", "extra": True}, {}),
    ("READ", {"url": "https://example.com/"}, {"extra": True}),
    ("READ", {"url": "https://example.com/"}, {"code": "unavailable"}),
    ("READ", {"url": "https://example.com/"}, {"code": "access_restricted"}),
    ("READ", {"url": "https://example.com/"}, {"code": "rate_limited"}),
    ("READ", {"url": "https://example.com/"}, {"replayed": True}),
    ("READ", {"url": "https://example.com/"}, {"replayed": 0}),
])
def test_known_read_failure_rejects_unvalidated_outcomes(kind, payload, patch):
    from pilot import research_effect_contract as contract
    validator = getattr(contract, "known_read_failure", None)
    assert callable(validator)
    result = {"status": "FAILED", "code": "not_found", "replayed": False} | patch
    with pytest.raises(ExecutionRuntimeError, match="^invalid_effect_result$"):
        validator(kind, payload, result)
    assert not contract.is_known_read_failure(kind, payload, result)


def model_payload():
    alias = _alias("mcp__yike_public", "search_public_web")
    return {"model": "public-model", "input": [{"role": "user", "content": "find buyers"}],
            "tools": [{"type": "function", "name": alias,
                       "parameters": {"type": "object"}}], "stream": True}


def model_result(*, name="search_public_web", namespace="mcp__yike_public", usage=None,
                 arguments='{"query":"buyer"}'):
    usage = {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5} if usage is None else usage
    item = {"type": "function_call", "namespace": namespace, "name": name,
            "arguments": arguments, "call_id": "c1"}
    events = [
        ("response.output_item.done", {"type": "response.output_item.done", "item": item}),
        ("response.completed", {"type": "response.completed", "response": {
            "status": "completed", "output": [item], "usage": usage}}),
    ]
    body = "".join(f"event: {kind}\ndata: {json.dumps(event)}\n\n" for kind, event in events)
    return {"status": 200, "code": "ok", "body": body, "usage": usage}


def test_effect_input_is_copied_and_hashes_exact_versioned_binding():
    payload, digest = effect_input("MODEL", model_payload(), binding())
    expected = {"schema_version": "research-effect-input-v1", "kind": "MODEL",
                "payload": payload, "context_binding": binding()}
    assert digest == hashlib.sha256(json.dumps(
        expected, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode()).hexdigest()
    payload["input"].append({})
    assert len(model_payload()["input"]) == 1


@pytest.mark.parametrize("kind,payload", [
    ("SEARCH", {"query": " two   words "}),
    ("READ", {"url": "https://example.com/path#fragment"}),
    ("MODEL", {"model": "m", "input": [], "tools": [], "stream": False}),
    ("MODEL", {"model": "m", "input": [], "tools": [{"type": "function", "name": "unknown"}], "stream": True}),
])
def test_effect_input_rejects_nonexact_or_unknown_effects(kind, payload):
    with pytest.raises(ExecutionRuntimeError, match="^invalid_effect_input$") as raised:
        effect_input(kind, payload, binding())
    assert raised.value.status == 422


@pytest.mark.parametrize("mutate", [
    lambda value: value.update(extra=True),
    lambda value: value.update(schema_version="research-context-v1"),
    lambda value: value.update(rule_sha256="A" * 64),
    lambda value: value.update(profile_version_id="not-a-uuid"),
])
def test_effect_input_requires_exact_v2_binding(mutate):
    value = binding(); mutate(value)
    with pytest.raises(ExecutionRuntimeError, match="^invalid_effect_input$"):
        effect_input("MODEL", model_payload(), value)


@pytest.mark.parametrize("payload", [
    {"query": "apikey=private-value"},
    {"query": "x\x00y"},
    {"query": "x" * (2 * 1024 * 1024)},
])
def test_effect_input_rejects_secrets_controls_and_oversize(payload):
    with pytest.raises(ExecutionRuntimeError, match="^invalid_effect_input$"):
        effect_input("SEARCH", payload, binding())


@pytest.mark.parametrize("payload", [
    {"model": "m", "input": [{"role": "user", "password": "synthetic-value"}],
     "tools": [], "stream": True},
    {"model": "m", "input": [{"role": "user", "content":
     "source https://example.com/post?xsec_token=synthetic-value"}], "tools": [], "stream": True},
    {"model": "m", "input": [{"role": "user", "bad\x00key": "value"}],
     "tools": [], "stream": True},
])
def test_model_input_rejects_sensitive_keys_embedded_tokens_and_control_keys(payload):
    with pytest.raises(ExecutionRuntimeError, match="^invalid_effect_input$"):
        effect_input("MODEL", payload, binding())


def test_usage_token_counters_are_not_mistaken_for_credentials():
    payload = model_payload() | {"metadata": {
        "input_tokens": 3, "output_tokens": 2, "total_tokens": 5}}
    assert effect_input("MODEL", payload, binding())[0] == payload


@pytest.mark.parametrize("content", [
    "source https://example.com/post?sessionid=synthetic-only",
    "source https://user:synthetic@public.example/post",
    "source https://example.com/post?%74%6f%6b%65%6e=synthetic-only",
    '{"password":"synthetic-only"}',
    r'{\"refresh_token\":\"synthetic-only\"}',
])
def test_model_input_rejects_credentials_embedded_in_original_string_content(content):
    payload = {"model": "m", "input": [{"role": "user", "content": content}],
               "tools": [], "stream": True}
    with pytest.raises(ExecutionRuntimeError, match="^invalid_effect_input$"):
        effect_input("MODEL", payload, binding())


def test_model_input_allows_safe_public_urls_and_ordinary_token_words():
    payload = {"model": "m", "input": [{"role": "user", "content":
               "Count tokens at https://example.com/post?topic=tokenization"}],
               "tools": [], "stream": True,
               "metadata": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}}
    assert effect_input("MODEL", payload, binding())[0] == payload


def test_valid_model_restored_function_calls_are_unchanged():
    result = model_result()
    assert effect_result("MODEL", model_payload(), result) == result


@pytest.mark.parametrize("arguments", [
    '{"query":"https://example.com/post?sessionid=synthetic-only"}',
    r'{\"query\":\"https:\/\/example.com\/post?%72%65%66%72%65%73%68_%74%6f%6b%65%6e=synthetic-only\"}',
])
def test_model_result_rejects_credentials_in_restored_function_arguments(arguments):
    with pytest.raises(ExecutionRuntimeError, match="^invalid_effect_result$"):
        effect_result("MODEL", model_payload(), model_result(arguments=arguments))


@pytest.mark.parametrize("result", [
    model_result(name="unknown"),
    model_result(namespace="mcp__private"),
    model_result() | {"usage": {"total_tokens": 5}},
    {"status": 200, "code": "ok", "body": "arbitrary text", "usage": None},
])
def test_model_result_rejects_unknown_calls_text_and_usage_mismatch(result):
    with pytest.raises(ExecutionRuntimeError, match="^invalid_effect_result$") as raised:
        effect_result("MODEL", model_payload(), result)
    assert raised.value.status == 422


def test_search_and_read_success_results_are_exactly_validated():
    observed = datetime.now(timezone.utc).isoformat()
    search = {"status": "SEARCHED", "query": "buyer", "observed_at": observed,
              "read_scope": "SEARCH_RESULTS", "results": [], "omitted_count": 0,
              "replayed": False}
    assert effect_result("SEARCH", {"query": "buyer"}, search) == search
    text = "evidence"
    page = {"url": "https://example.com/", "title": None, "text": text,
            "observed_at": observed, "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "read_scope": "PUBLIC_PAGE_TEXT"}
    read = {"status": "READ", "evidence": page, "review_status": "UNREVIEWED", "replayed": False}
    assert effect_result("READ", {"url": "https://example.com/"}, read) == read
    with pytest.raises(ExecutionRuntimeError, match="^invalid_effect_result$"):
        effect_result("READ", {"url": "https://other.example/"}, read)
