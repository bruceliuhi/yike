"""Synthetic evidence and local transport tests; not real buyer/model proof."""
import copy
import asyncio
from contextlib import contextmanager
import importlib
import importlib.util
import json
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback

import httpx
import pytest


DESCRIPTION = "我们为食品工厂提供不锈钢  输送设备和安装服务。"
CONTENT = {"title": "食品工厂扩产", "body": "我们工厂想采购输送设备，月底前找团队报价。",
           "parent": {"title": None, "body": "我们有预算十万急找软件开发。"}}


def module():
    name = "pilot.candidate_assessment_model"
    assert importlib.util.find_spec(name) is not None, "candidate assessment model is missing"
    return importlib.import_module(name)


def assessment():
    return {
        "businessMatch": {"level": "HIGH", "reason": "业务与设备匹配。", "citations": [
            {"field": "profile.description", "quote": "不锈钢  输送设备"},
            {"field": "title", "quote": "食品工厂"}]},
        "intent": {"level": "HIGH", "reason": "本人明确采购。", "citations": [
            {"field": "body", "quote": "采购输送设备"}]},
        "urgency": {"level": "MEDIUM", "reason": "提及月底但日期尚未核验。", "citations": [
            {"field": "body", "quote": "月底前"}]},
        "actionability": {"level": "UNKNOWN", "reason": "尚未核验联系入口。", "citations": []},
        "purchaseType": "PROJECT", "grade": "A", "decision": "REVIEW",
        "evidence": {"matchReason": "设备服务匹配。", "actionSignal": "本人询价。",
                     "value": "推断可能需要设备安装。", "risk": "实际交期未核验。", "unknowns": "预算和联系入口未知。"},
        "summary": "有本人业务与采购动作，仍需人工复核。",
        "draftComment": "看到你们食品工厂在扩产，输送设备是接到现有生产线上吗？",
        "draftDm": "看到你们在找月底前的输送设备报价，这次主要想改哪段产线？",
    }


def validate(value=None, *, description=DESCRIPTION, content=None):
    return module().validate_assessment(assessment() if value is None else value,
        description=description, content=copy.deepcopy(CONTENT) if content is None else content)


def test_complete_assessment_preserves_verbatim_quotes_and_independent_dimensions():
    result = validate()
    assert result.model_dump() == assessment()
    assert result.businessMatch.citations[0].quote == "不锈钢  输送设备"
    assert result.actionability.level == "UNKNOWN"
    with pytest.raises(Exception):
        result.grade = "S"


@pytest.mark.parametrize("field", list(assessment()))
def test_every_output_field_is_required(field):
    value = assessment()
    del value[field]
    with pytest.raises(module().AssessmentModelError):
        validate(value)


@pytest.mark.parametrize("extra", ["author", "publishedAt", "publicUrl", "reviewer", "reviewedAt", "status", "sourceStatus"])
def test_model_cannot_supply_authoritative_metadata(extra):
    with pytest.raises(module().AssessmentModelError):
        validate(assessment() | {extra: "APPROVED"})


@pytest.mark.parametrize("path,value", [
    (("grade",), "C"), (("grade",), True), (("decision",), "APPROVED"),
    (("purchaseType",), "OPEN"), (("summary",), 4), (("summary",), "\u200b\x00"),
    (("intent", "level"), "high"), (("intent", "level"), True),
    (("intent", "reason"), " "), (("intent", "reason"), None),
    (("intent", "citations"), []), (("intent", "citations"), ()),
    (("intent", "citations"), [{"field": "body", "quote": "预算十万"}]),
    (("intent", "citations"), [{"field": "parent.body", "quote": "有预算十万"}]),
    (("urgency", "citations"), [{"field": "profile.description", "quote": "食品工厂"}]),
    (("businessMatch", "citations"), [{"field": "profile.description", "quote": "不锈钢 输送设备"}]),
    (("businessMatch", "citations"), [{"field": "author", "quote": "匿名"}]),
    (("businessMatch", "citations"), [{"field": "body", "quote": ""}]),
    (("businessMatch", "citations"), [{"field": "body", "quote": True}]),
    (("businessMatch", "citations"), [{"field": "parent.title", "quote": "食品工厂"}]),
    (("businessMatch", "citations"), [{"field": "body", "quote": "我们", "verified": True}]),
    (("evidence", "unknowns"), []), (("evidence", "risk"), ""),
    (("draftComment",), "字" * 121), (("draftDm",), "字" * 121),
    (("draftComment",), ""), (("draftDm",), "\ud800"),
])
def test_rejects_bad_types_quotes_parent_only_intent_and_drafts(path, value):
    payload = assessment()
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(module().AssessmentModelError) as raised:
        validate(payload)
    assert (raised.value.code, raised.value.status) == ("invalid_assessment_result", 502)
    assert raised.value.__context__ is None


def test_parent_context_is_allowed_but_never_sufficient_for_personal_intent():
    value = assessment()
    value["intent"]["citations"].append({"field": "parent.body", "quote": "预算十万"})
    assert validate(value).intent.level == "HIGH"


@pytest.mark.parametrize("decision", ["OBSERVE", "EXCLUDE"])
def test_observe_exclude_do_not_manufacture_grades(decision):
    value = assessment() | {"decision": decision}
    with pytest.raises(module().AssessmentModelError):
        validate(value)
    assert validate(value | {"grade": None}).grade is None


def test_short_drafts_are_allowed_but_same_or_blank_drafts_are_not():
    assert validate(assessment() | {"draftComment": "需要设备安装吗？", "draftDm": "产线主要生产什么？"})
    with pytest.raises(module().AssessmentModelError):
        validate(assessment() | {"draftDm": assessment()["draftComment"]})
    with pytest.raises(module().AssessmentModelError):
        validate(assessment() | {"draftDm": " " + assessment()["draftComment"] + " "})


@pytest.mark.parametrize("description", [None, 5, True, "", " ", "\u200b", "x" * 8001, "bad\ud800"])
def test_invalid_description_is_a_safe_input_error(description):
    with pytest.raises(module().AssessmentModelError) as raised:
        validate(description=description)
    assert (raised.value.code, raised.value.status) == ("invalid_assessment_input", 400)
    assert raised.value.__context__ is None


@pytest.mark.parametrize("content", [[], {}, {"body": "text"}, CONTENT | {"author": "secret"},
    CONTENT | {"body": True}, CONTENT | {"body": ""}, CONTENT | {"body": "\ud800"},
    CONTENT | {"body": "字" * 45000}, CONTENT | {"parent": {"body": "x", "title": None, "author": "x"}},
])
def test_invalid_or_oversized_content_is_rejected(content):
    with pytest.raises(module().AssessmentModelError) as raised:
        validate(content=content)
    assert (raised.value.code, raised.value.status) == ("invalid_assessment_input", 400)


def test_revalidates_constructed_objects_and_mutated_nested_citations():
    implementation = module()
    forged = implementation.AssessmentContent.model_construct(**(assessment() | {"grade": True}))
    with pytest.raises(implementation.AssessmentModelError):
        validate(forged)
    valid = validate()
    valid.intent.citations.append({"field": "body", "quote": "fake"})
    with pytest.raises(implementation.AssessmentModelError):
        validate(valid)


def test_safe_errors_reject_unapproved_codes_and_statuses():
    error = module().AssessmentModelError("secret provider error", 200)
    assert (str(error), error.code, error.status) == ("invalid_assessment_result", "invalid_assessment_result", 502)


def adapter(**options):
    implementation = module()
    assert hasattr(implementation, "OpenAICompatibleCandidateAssessmentModel"), "missing assessment HTTP adapter"
    return implementation.OpenAICompatibleCandidateAssessmentModel(**{
        "base_url": "https://model.example/v1", "api_key": "synthetic-test-secret", "model": "test/model-v1", **options})


@contextmanager
def internal_client(**options):
    """Own only a mock-boundary async client; no real pooled cross-loop I/O."""
    client = httpx.AsyncClient(**options)
    try:
        yield client
    finally:
        asyncio.run(client.aclose())


def envelope():
    return {"choices": [{"finish_reason": "stop", "message": {
        "role": "assistant", "content": json.dumps(assessment(), ensure_ascii=False), "refusal": None}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}}


def run_response(response):
    requests = []
    def handle(request):
        requests.append(request)
        return response
    with internal_client(transport=httpx.MockTransport(handle), follow_redirects=True) as client:
        try:
            return adapter(http_client=client).assess(description=DESCRIPTION, content=CONTENT)
        finally:
            assert len(requests) == 1


def safe_error(call, code="invalid_assessment_result", status=502):
    with pytest.raises(module().AssessmentModelError) as caught:
        call()
    error = caught.value
    assert (str(error), error.code, error.status) == (code, code, status)
    assert error.__cause__ is None and error.__context__ is None
    rendered = "".join(traceback.format_exception(error))
    assert "SECRET_PROVIDER_RESPONSE" not in rendered
    assert "synthetic-test-secret" not in rendered


def test_rules_use_both_versioned_files_and_cross_industry_contract():
    implementation = module()
    assert hasattr(implementation, "load_assessment_rules"), "missing packaged rule loader"
    version, digest, prompt = implementation.load_assessment_rules()
    assert version == "candidate-assessment-v1/ai-project-lead-research-1.0.0"
    root = Path(__file__).resolve().parents[1]
    for path in ("SKILL.md", "references/qualification-and-evidence.md"):
        assert (root / "skills/ai-project-lead-research-v1" / path).read_text() in prompt
    assert digest == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert "跨行业" in prompt and "画像优先" in prompt
    assert "父帖" in prompt and "不代表发送授权" in prompt
    assert "唯一Offer意客AI" not in prompt
    assert implementation.load_assessment_rules() == (version, digest, prompt)


def test_adapter_uses_fixed_rules_and_sends_only_projected_data_with_strict_schema():
    calls = []
    def handle(request):
        calls.append(request)
        assert request.method == "POST" and str(request.url) == "https://model.example/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer synthetic-test-secret"
        assert set(request.extensions["timeout"].values()) == {7}
        body = json.loads(request.content)
        assert body["max_tokens"] == 4096 and body["model"] == "test/model-v1"
        assert [m["role"] for m in body["messages"]] == ["system", "user"]
        assert body["messages"][0]["content"] == module().load_assessment_rules()[2]
        assert DESCRIPTION not in body["messages"][0]["content"]
        assert json.loads(body["messages"][1]["content"]) == {"description": DESCRIPTION, "content": CONTENT}
        schema = body["response_format"]["json_schema"]
        assert schema["strict"] is True
        assert schema["schema"]["additionalProperties"] is False
        assert set(schema["schema"]["required"]) == set(assessment())
        return httpx.Response(200, json=envelope())
    with internal_client(transport=httpx.MockTransport(handle)) as client:
        model = adapter(http_client=client, timeout_seconds=7)
        assert "synthetic-test-secret" not in repr(model) and "model.example" not in repr(model)
        result, usage = model.assess(description=DESCRIPTION, content=CONTENT)
        assert result.model_dump() == assessment()
        assert usage == {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}
        assert not client.is_closed
    assert len(calls) == 1
    assert model.provider == "openai-compatible"
    assert (model.rule_version, model.rule_sha256) == module().load_assessment_rules()[:2]


@pytest.mark.parametrize("key,value", [
    ("base_url", "http://model.example"), ("base_url", "http://127.0.0.1.evil.example"),
    ("base_url", "https://user:password@model.example"), ("base_url", "https://model.example?key=secret"),
    ("base_url", "https://model.example#x"), ("base_url", "https://model.example\\evil"),
    ("base_url", " https://model.example"), ("base_url", "https://model.example:99999"),
    ("base_url", "https://"), ("base_url", 3), ("api_key", ""), ("api_key", "bad\nkey"),
    ("api_key", None), ("api_key", b"secret"), ("model", ""), ("model", "bad\ud800"),
    ("timeout_seconds", 0), ("timeout_seconds", 60.1), ("timeout_seconds", True),
    ("timeout_seconds", float("nan")), ("timeout_seconds", float("inf")),
    ("timeout_seconds", "30"), ("http_client", object()),
])
def test_bad_configuration_is_safe(key, value):
    safe_error(lambda: adapter(**{key: value}), "invalid_assessment_configuration", 500)


@pytest.mark.parametrize("base_url", ["https://model.example/v1/", "http://localhost:8080", "http://127.12.3.4", "http://[::1]:8080"])
def test_supported_endpoint_configuration(base_url):
    assert adapter(base_url=base_url, timeout_seconds=60).timeout_seconds == 60


@pytest.mark.parametrize("status,code,error_status", [
    (301, "invalid_assessment_result", 502), (302, "invalid_assessment_result", 502),
    (307, "invalid_assessment_result", 502), (308, "invalid_assessment_result", 502),
    (400, "assessment_provider_rejected", 502), (401, "assessment_provider_rejected", 502),
    (429, "assessment_provider_rejected", 502), (500, "assessment_result_unknown", 504),
    (503, "assessment_result_unknown", 504),
])
def test_http_errors_do_not_retry_or_redirect(status, code, error_status):
    safe_error(lambda: run_response(httpx.Response(status, headers={"location": "https://other.example"},
        text="SECRET_PROVIDER_RESPONSE")), code, error_status)


@pytest.mark.parametrize("raw", [b"\xff", b"[]", b"null", b"{}", b'{"a":1,"a":2}',
    b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1e9999}', b"```json\n{}\n```", b"{} trailing"])
def test_outer_json_is_strict(raw):
    safe_error(lambda: run_response(httpx.Response(200, content=raw)))


@pytest.mark.parametrize("raw", ["[]", "null", '{"x":1,"x":2}', '{"x":NaN}', '{"x":1e9999}', "```json\n{}\n```", "{} trailing"])
def test_inner_json_is_strict(raw):
    value = envelope()
    value["choices"][0]["message"]["content"] = raw
    safe_error(lambda: run_response(httpx.Response(200, json=value)))


@pytest.mark.parametrize("change", [{"finish_reason": "length"}, {"finish_reason": "tool_calls"}, {"finish_reason": "content_filter"}])
def test_incomplete_or_tool_output_is_not_success(change):
    value = envelope()
    value["choices"][0].update(change)
    safe_error(lambda: run_response(httpx.Response(200, json=value)))


@pytest.mark.parametrize("change", [{"refusal": "SECRET_PROVIDER_RESPONSE"}, {"role": "user"},
    {"tool_calls": [{"function": {"name": "send"}}]}, {"function_call": {"name": "send"}},
    {"content": None}, {"content": []}, {"content": ""}])
def test_refusals_and_bad_messages_fail_closed(change):
    value = envelope()
    value["choices"][0]["message"].update(change)
    safe_error(lambda: run_response(httpx.Response(200, json=value)))


@pytest.mark.parametrize("choices", [[], {}, [None], [{"message": None}], [envelope()["choices"][0]] * 2])
def test_ambiguous_response_envelope_is_rejected(choices):
    safe_error(lambda: run_response(httpx.Response(200, json=envelope() | {"choices": choices})))


@pytest.mark.parametrize("usage", [None, {}, [], {"prompt_tokens": 2},
    {"prompt_tokens": True, "completion_tokens": 1, "total_tokens": 2},
    {"prompt_tokens": 1.0, "completion_tokens": 1, "total_tokens": 2},
    {"prompt_tokens": "1", "completion_tokens": 1, "total_tokens": 2},
    {"prompt_tokens": -1, "completion_tokens": 2, "total_tokens": 1},
    {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 3},
    {"prompt_tokens": 2**31, "completion_tokens": 0, "total_tokens": 2**31},
])
def test_invalid_usage_is_unknown_not_zero(usage):
    assert run_response(httpx.Response(200, json=envelope() | {"usage": usage}))[1] is None


def test_zero_usage_is_valid_and_only_measured_fields_are_returned():
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    assert run_response(httpx.Response(200, json=envelope() | {"usage": usage | {"secret": "ignored"}}))[1] == usage


def test_nonfinite_number_in_unused_envelope_field_is_still_rejected():
    raw = json.dumps(envelope())[:-1] + ',"ignored":1e9999}'
    safe_error(lambda: run_response(httpx.Response(200, content=raw)))


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout, httpx.WriteError, httpx.ReadError])
def test_transport_exception_has_no_sensitive_context(error):
    requests = []
    def handle(request):
        requests.append(request)
        raise error("SECRET_PROVIDER_RESPONSE synthetic-test-secret")
    with internal_client(transport=httpx.MockTransport(handle)) as client:
        safe_error(lambda: adapter(http_client=client).assess(description=DESCRIPTION, content=CONTENT),
                   "assessment_result_unknown", 504)
    assert len(requests) == 1


def test_response_byte_limit_applies_while_streaming():
    class LargeStream(httpx.AsyncByteStream):
        chunks = 0
        closed = False
        async def __aiter__(self):
            for _ in range(100):
                self.chunks += 1
                yield b" " * 16384
        async def aclose(self):
            self.closed = True
    stream = LargeStream()
    safe_error(lambda: run_response(httpx.Response(200, stream=stream)))
    assert stream.chunks == 17 and stream.closed
    raw = json.dumps(envelope()).encode()
    raw += b" " * (256 * 1024 - len(raw))
    assert run_response(httpx.Response(200, content=raw))[0].model_dump() == assessment()


def test_invalid_input_never_contacts_provider():
    def handle(request):
        pytest.fail("invalid input must not contact provider")
    with internal_client(transport=httpx.MockTransport(handle)) as client:
        safe_error(lambda: adapter(http_client=client).assess(description=DESCRIPTION, content=CONTENT | {"author": "private"}),
                   "invalid_assessment_input", 400)


def test_default_transport_disables_retries(monkeypatch):
    options = []
    def transport_factory(**kwargs):
        options.append(kwargs)
        return httpx.MockTransport(lambda request: httpx.Response(200, json=envelope()))
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport_factory)
    assert adapter().assess(description=DESCRIPTION, content=CONTENT)[0].model_dump() == assessment()
    assert options == [{"retries": 0}]


def test_real_local_http_success_and_provider_failure():
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["content-length"]))))
            self.send_response(200 if len(requests) == 1 else 503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(envelope()).encode())
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        model = adapter(base_url=f"http://127.0.0.1:{server.server_port}/v1")
        assert model.assess(description=DESCRIPTION, content=CONTENT)[0].model_dump() == assessment()
        safe_error(lambda: model.assess(description=DESCRIPTION, content=CONTENT), "assessment_result_unknown", 504)
        assert len(requests) == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_installed_wheel_has_identical_rules_and_missing_rules_fail_closed(tmp_path):
    implementation = module()
    assert hasattr(implementation, "load_assessment_rules"), "missing packaged rule loader"
    expected = implementation.load_assessment_rules()
    root = Path(__file__).resolve().parents[1]
    built = subprocess.run(["uv", "build", "--wheel", "--offline", "--out-dir", str(tmp_path / "dist"), str(root)],
                           capture_output=True, text=True, timeout=60)
    assert built.returncode == 0, built.stderr
    wheel, = (tmp_path / "dist").glob("*.whl")
    installed = tmp_path / "installed"
    install = subprocess.run(["uv", "pip", "install", "--target", str(installed), "--no-deps", "--offline", str(wheel)],
                             capture_output=True, text=True, timeout=30)
    assert install.returncode == 0, install.stderr
    # Isolated interpreter: remove checkout, import only the installed wheel's
    # pilot package while reusing installed dependencies (no provider/network).
    script = "import sys,json; sys.path.insert(0,sys.argv[1]); from pilot.candidate_assessment_model import load_assessment_rules; print(json.dumps(load_assessment_rules()))"
    result = subprocess.run([sys.executable, "-I", "-c", script, str(installed)], cwd=tmp_path,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert tuple(json.loads(result.stdout)) == expected
    resource = installed / "pilot/_assessment_rules/SKILL.md"
    assert resource.read_bytes() == (root / "skills/ai-project-lead-research-v1/SKILL.md").read_bytes()
    resource.unlink()
    broken = subprocess.run([sys.executable, "-I", "-c", script, str(installed)], cwd=tmp_path,
                            capture_output=True, text=True, timeout=10)
    assert broken.returncode != 0 and "assessment_rules_unavailable" in broken.stderr
    assert "FileNotFoundError" not in broken.stderr


def test_input_and_draft_exact_upper_bounds_remain_usable():
    implementation = module()
    content = {"title": None, "body": "x", "parent": None}
    overhead = len(json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode()) - 1
    content["body"] = "x" * (128 * 1024 - overhead)
    assert implementation.validate_assessment_input(description="字" * 8000, content=content) is None
    content["body"] += "x"
    safe_error(lambda: implementation.validate_assessment_input(description=DESCRIPTION, content=content),
               "invalid_assessment_input", 400)
    value = assessment() | {"draftComment": "评" * 120, "draftDm": "信" * 120}
    assert len(validate(value).draftComment) == 120


def test_model_request_and_grounding_share_snapshot_when_callers_mutate_content():
    content = copy.deepcopy(CONTENT)
    def handle(request):
        content["body"] = "后来发生了变化"
        content["parent"]["body"] = "父帖也更新了"
        return httpx.Response(200, json=envelope())
    with internal_client(transport=httpx.MockTransport(handle)) as client:
        result, _ = adapter(http_client=client).assess(description=DESCRIPTION, content=content)
    assert result.model_dump() == assessment()


def test_nested_output_extras_and_missing_fields_are_rejected():
    for field in ("level", "reason", "citations"):
        value = assessment()
        del value["intent"][field]
        safe_error(lambda: validate(value))
    for key in ("intent", "evidence"):
        value = assessment()
        value[key]["author"] = "fabricated"
        safe_error(lambda: validate(value))


def test_comment_container_title_cannot_be_personal_intent_evidence():
    content = {"title": None, "body": "这个怎么做？", "parent": {"title": "工厂急找团队报价", "body": None}}
    value = assessment()
    value["businessMatch"]["citations"] = [{"field": "profile.description", "quote": "食品工厂"}]
    value["urgency"] = {"level": "UNKNOWN", "reason": "本人未说明时间。", "citations": []}
    value["intent"]["citations"] = [{"field": "parent.title", "quote": "急找团队报价"}]
    safe_error(lambda: validate(value, content=content))
    value["intent"]["citations"] = [{"field": "title", "quote": "急找团队报价"}]
    safe_error(lambda: validate(value, content=content))


def test_real_slow_drip_is_cancelled_at_total_deadline_and_disconnects():
    requests = []
    disconnected = threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(self.rfile.read(int(self.headers["content-length"])))
            self.send_response(200)
            self.end_headers()
            raw = json.dumps(envelope()).encode()
            try:
                for offset in range(0, len(raw), 100):
                    self.wfile.write(raw[offset:offset + 100])
                    self.wfile.flush()
                    time.sleep(0.03)  # Below each read timeout, above total budget.
            except (BrokenPipeError, ConnectionResetError):
                disconnected.set()
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        model = adapter(base_url=f"http://127.0.0.1:{server.server_port}/v1", timeout_seconds=0.08)
        started = time.monotonic()
        safe_error(lambda: model.assess(description=DESCRIPTION, content=CONTENT), "assessment_result_unknown", 504)
        assert time.monotonic() - started < 0.3
        assert disconnected.wait(timeout=0.3), "cancel must close the socket, not abandon a worker"
        assert len(requests) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("phase", ["headers", "body"])
def test_total_timeout_awaits_cancellation_and_closes_owned_transport(monkeypatch, phase):
    events = []
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            try:
                events.append("read")
                await asyncio.sleep(10)
                yield b"unreachable"
            finally:
                events.append("read_cancelled")
        async def aclose(self):
            events.append("response_closed")
    class Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            events.append("request")
            if phase == "headers":
                try:
                    await asyncio.sleep(10)
                finally:
                    events.append("headers_cancelled")
            return httpx.Response(200, stream=Stream())
        async def aclose(self):
            events.append("transport_closed")
    def factory(**options):
        assert options == {"retries": 0}
        return Transport()
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", factory)
    model = adapter(timeout_seconds=0.03)
    started = time.monotonic()
    safe_error(lambda: model.assess(description=DESCRIPTION, content=CONTENT), "assessment_result_unknown", 504)
    assert time.monotonic() - started < 0.25
    if phase == "body":
        assert events == ["request", "read", "read_cancelled", "response_closed", "transport_closed"]
    else:
        assert events == ["request", "headers_cancelled", "transport_closed"]


def test_sync_entrypoint_rejects_running_loop_without_abandoned_coroutine():
    model = adapter()
    async def call():
        safe_error(lambda: model.assess(description=DESCRIPTION, content=CONTENT), "invalid_assessment_configuration", 500)
    asyncio.run(call())
