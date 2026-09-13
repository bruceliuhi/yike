import json
import hashlib
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from time import monotonic
from datetime import datetime, timezone

import httpx
import pytest

from pilot.responses_bridge import ResponsesBridge


KEY = "synthetic-key-must-not-leak"
ALLOWED = (("mcp__yike_public", "read_public_page"),)


def request(bridge, payload, **kwargs):
    headers = {"Authorization": "Bearer " + bridge.token, **kwargs.pop("headers", {})}
    return httpx.post(bridge.base_url + "/responses", headers=headers, json=payload, timeout=5, **kwargs)


def sse(*events):
    return "".join(f"event: {kind}\ndata: {json.dumps(data)}\n\n" for kind, data in events).encode()


def real_sse(alias):
    events = [
        ("response.created", {"type": "response.created", "response": {"status": "in_progress", "output": []}}),
        ("response.in_progress", {"type": "response.in_progress", "response": {"status": "in_progress"}}),
        ("response.output_item.added", {"type": "response.output_item.added", "item": {
            "type": "function_call", "name": alias, "arguments": "", "call_id": "c-real"}}),
        ("response.function_call_arguments.delta", {"type": "response.function_call_arguments.delta",
                                                     "delta": '{"url":"https://example.com/"}'}),
        ("response.function_call_arguments.done", {"type": "response.function_call_arguments.done",
                                                    "arguments": '{"url":"https://example.com/"}'}),
        ("response.output_item.done", {"type": "response.output_item.done", "item": {
            "type": "function_call", "name": alias,
            "arguments": '{"url":"https://example.com/"}', "call_id": "c-real"}}),
        ("response.completed", {"type": "response.completed", "response": {"status": "completed", "output": [
            {"type": "function_call", "name": alias,
             "arguments": '{"url":"https://example.com/"}', "call_id": "c-real"}]}}),
    ]
    return sse(*events) + b"data: [DONE]\n\n"


def test_roundtrip_rewrites_only_protocol_function_names_and_history():
    seen = []
    aliases = []

    def provider(req):
        payload = json.loads(req.content)
        seen.append((req, payload))
        alias = payload["tools"][0]["name"]
        aliases.append(alias)
        assert alias != "read_public_page" and len(alias) <= 64
        assert payload["model"] == "test-model"
        assert payload["reasoning"] == {"effort": "low"}
        if len(seen) == 1:
            assert payload["input"][0]["business"] == {"type": "function_call", "name": "opaque"}
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse(
            ("response.output_item.added", {"type": "response.output_item.added", "item": {
                "type": "function_call", "name": alias, "arguments": '{"name":"' + alias + '"}', "call_id": "c1"}}),
            ("response.completed", {"type": "response.completed", "response": {"status": "completed", "output": [
                {"type": "function_call", "name": alias, "arguments": "{}", "call_id": "c1"}],
                "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}}}),
        ))

    with ResponsesBridge(api_key=KEY, model="test-model", max_requests=2, deadline=monotonic()+10,
                         allowed_tools=ALLOWED, transport=httpx.MockTransport(provider)) as bridge:
        payload = {"model": "ignored", "stream": True, "reasoning": {"effort": "low", "summary": "auto"},
                   "tools": [{"type": "namespace", "name": ALLOWED[0][0], "tools": [
                       {"type": "function", "name": ALLOWED[0][1], "description": "read",
                        "parameters": {"type": "object", "example": {"type": "function_call"}}},
                       {"type": "function", "name": "unadvertised", "parameters": {"type": "object"}}]},
                       {"type": "namespace", "name": "mcp__other", "tools": [
                           {"type": "function", "name": "other", "parameters": {"type": "object"}}]},
                       {"type": "web_search"}],
                   "input": [{"role": "user", "content": "hello", "business": {
                       "type": "function_call", "name": "opaque"}}]}
        first = request(bridge, payload)
        assert first.status_code == 200
        assert KEY not in first.text
        events = [json.loads(line[6:]) for line in first.text.splitlines() if line.startswith("data: ")]
        for item in (events[0]["item"], events[1]["response"]["output"][0]):
            assert item["name"] == ALLOWED[0][1]
            assert item["namespace"] == ALLOWED[0][0]
        assert aliases[0] in events[0]["item"]["arguments"]  # business argument text is untouched

        assert len(seen[0][1]["tools"]) == 1
        assert seen[0][1]["tools"][0]["parameters"]["example"] == {"type": "function_call"}
        second = request(bridge, {**payload, "tools": payload["tools"], "input": [events[0]["item"]]})
        assert second.status_code == 200
        assert seen[1][1]["input"][0]["name"] == seen[1][1]["tools"][0]["name"]
        assert "namespace" not in seen[1][1]["input"][0]
        assert seen[0][0].headers["authorization"] == "Bearer " + KEY
        assert bridge.records[-1]["usage"] == {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}


def test_assistant_history_supplies_required_status_without_changing_text_or_phase():
    messages=[{'type':'message','role':'assistant','phase':'commentary',
               'content':[{'type':'output_text','text':'我先查原文。'}]},
              {'type':'message','role':'assistant','status':'incomplete',
               'content':[{'type':'output_text','text':'已给出的部分内容'}]},
              {'role':'user','content':'继续','business':{'type':'message','role':'assistant'}}]
    original=json.loads(json.dumps(messages))
    def provider(req):
        inputs=json.loads(req.content)['input']
        assert inputs[0]==messages[0]|{'status':'completed'}
        assert inputs[1:]==messages[1:]
        return httpx.Response(200,headers={'content-type':'text/event-stream'},content=sse(
            ('response.completed',{'type':'response.completed','response':{'status':'completed','output':[]}})))
    with ResponsesBridge(api_key=KEY,model='test-model',max_requests=1,deadline=monotonic()+10,
                         allowed_tools=(),transport=httpx.MockTransport(provider)) as bridge:
        response=request(bridge,{'input':messages,'tools':[],'stream':True})
        assert response.status_code==200
    assert messages==original


def test_codex_client_metadata_is_removed_before_durable_admission_and_provider():
    from pilot.research_effect_contract import effect_input
    from tests.test_research_effect_contract import binding
    admitted, forwarded = [], []
    def dispatcher(kind, payload, deadline, perform):
        clean, _ = effect_input(kind, payload, binding())
        admitted.append(clean)
        return perform(deadline)
    def provider(req):
        forwarded.append(json.loads(req.content))
        return httpx.Response(200, headers={'content-type':'text/event-stream'}, content=sse(
            ('response.completed', {'type':'response.completed', 'response':{
                'status':'completed', 'output':[]}})))
    payload = {'stream':True, 'tools':[], 'input':[{'role':'user', 'content':'找企业知识库采购'}],
               'client_metadata':{'session_id':'synthetic-codex-session',
                   'x-codex-turn-metadata':'{"session_id":"synthetic-codex-session"}'}}
    original = json.loads(json.dumps(payload))
    with ResponsesBridge(api_key=KEY, model='test-model', max_requests=1,
            deadline=monotonic()+10, allowed_tools=(), effect_dispatcher=dispatcher,
            transport=httpx.MockTransport(provider)) as bridge:
        response = request(bridge, payload)
    assert response.status_code == 200
    assert len(admitted) == len(forwarded) == 1
    assert admitted[0] == forwarded[0]
    assert 'client_metadata' not in forwarded[0]
    assert forwarded[0]['input'] == original['input'] and payload == original


def test_business_session_credentials_are_not_removed_or_allowed_by_metadata_filter():
    from pilot.execution_contract import ExecutionRuntimeError
    from pilot.research_effect_contract import effect_input
    from tests.test_research_effect_contract import binding
    with ResponsesBridge(api_key=KEY, model='test-model', max_requests=1,
            deadline=monotonic()+10, allowed_tools=()) as bridge:
        payload = {'stream':True, 'tools':[], 'input':[{'role':'user',
            'content':'{"session_id":"synthetic-private-session"}'}]}
        outbound = bridge._outbound(payload)
        assert outbound['input'] == payload['input']
        with pytest.raises(ExecutionRuntimeError, match='^invalid_effect_input$'):
            effect_input('MODEL', outbound, binding())


def test_model_effect_dispatch_receives_normalized_outbound_and_shortened_deadline():
    seen = {}
    host_deadline = monotonic() + 10

    def dispatcher(kind, payload, deadline, perform):
        seen.update(kind=kind, payload=payload, deadline=deadline)
        return perform(deadline - 1)

    def provider(request):
        seen["provider"] = json.loads(request.content)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse(
            ("response.completed", {"type": "response.completed", "response": {
                "status": "completed", "output": []}})))

    with ResponsesBridge(api_key=KEY, model="forced", max_requests=1, deadline=host_deadline,
                         allowed_tools=(), effect_dispatcher=dispatcher,
                         transport=httpx.MockTransport(provider)) as bridge:
        response = request(bridge, {"model": "ignored", "tools": [], "input": []})
    assert response.status_code == 200
    assert seen["kind"] == "MODEL" and seen["deadline"] == host_deadline
    assert seen["payload"]["model"] == "forced" and seen["provider"] == seen["payload"]


def test_model_effect_preserves_exact_structured_text_format_through_admission():
    from pilot.research_effect_contract import effect_input
    from tests.test_research_effect_contract import binding

    schema = {"type": "object", "properties": {"status": {"type": "string", "enum": ["OK"]}},
              "required": ["status"], "additionalProperties": False}
    seen = {}

    def dispatcher(kind, payload, deadline, perform):
        admitted, _ = effect_input(kind, payload, binding())
        seen["admitted"] = admitted
        return perform(deadline)

    def provider(req):
        seen["provider"] = json.loads(req.content)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse(
            ("response.completed", {"type": "response.completed", "response": {
                "status": "completed", "output": []}})))

    text_format = {"type": "json_schema", "name": "page_selection", "strict": True,
                   "schema": schema}
    with ResponsesBridge(api_key=KEY, model="forced", max_requests=1,
            deadline=monotonic()+10, allowed_tools=(), effect_dispatcher=dispatcher,
            transport=httpx.MockTransport(provider)) as bridge:
        response = request(bridge, {"tools": [], "input": [], "stream": True,
                                    "text": {"format": text_format}})
    assert response.status_code == 200
    assert seen["admitted"]["text"]["format"] == text_format
    assert seen["provider"]["text"]["format"] == text_format


def test_model_effect_can_return_trusted_replay_without_provider_io():
    body = sse(("response.completed", {"type": "response.completed", "response": {
        "status": "completed", "output": [], "usage": {"total_tokens": 7}}})).decode()
    replay = {"status": 200, "code": "ok", "body": body,
              "usage": {"total_tokens": 7}}
    with ResponsesBridge(api_key=KEY, model="m", max_requests=1, deadline=monotonic()+10,
                         allowed_tools=(), effect_dispatcher=lambda *_: replay,
                         transport=httpx.MockTransport(lambda _: pytest.fail("must not call provider"))) as bridge:
        response = request(bridge, {"tools": [], "input": []})
        assert response.status_code == 200
        assert bridge.records[0]["usage"] == {"total_tokens": 7}


@pytest.mark.parametrize("effect_result", [
    None,
    {"status": 200, "code": "ok", "body": "valid type", "usage": []},
    {"status": 418, "code": "private", "body": "private", "usage": None},
    {"status": True, "code": "ok", "body": "", "usage": None},
    {"status": 502, "code": "provider_error", "body": "private", "usage": None},
])
def test_invalid_or_denied_model_effect_is_fixed_error_without_provider(effect_result):
    dispatcher = (lambda *_: (_ for _ in ()).throw(RuntimeError("private secret"))) \
        if effect_result is None else (lambda *_: effect_result)
    with ResponsesBridge(api_key=KEY, model="m", max_requests=1, deadline=monotonic()+10,
                         allowed_tools=(), effect_dispatcher=dispatcher,
                         transport=httpx.MockTransport(lambda _: pytest.fail("must not call provider"))) as bridge:
        response = request(bridge, {"tools": [], "input": []})
        assert response.status_code == 502
        assert response.json() == {"error": {"code": "provider_error"}}
        assert "private" not in response.text + repr(bridge.records)


def _page(url="https://example.com/"):
    text = "public evidence"
    return {"url": url, "title": "Example", "text": text,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "read_scope": "PUBLIC_PAGE_TEXT"}


def test_public_read_endpoint_uses_same_admission_and_closes_owned_service():
    class Reader:
        def __init__(self): self.calls = []; self.closed = 0
        def read(self, url, *, deadline):
            self.calls.append((url, deadline))
            return {"status": "READ", "evidence": _page(url),
                    "review_status": "UNREVIEWED", "replayed": False}
        def close(self): self.closed += 1

    reader = Reader()
    with ResponsesBridge(api_key=KEY, model="m", max_requests=1, deadline=monotonic()+10,
                         allowed_tools=(), read_service=reader,
                         transport=httpx.MockTransport(lambda _: None)) as bridge:
        assert bridge.read_url == bridge.base_url + "/public-read"
        assert httpx.get(bridge.read_url, headers={"Authorization": "Bearer " + bridge.token}).status_code == 405
        assert httpx.post(bridge.read_url, headers={"Authorization": "Bearer wrong"},
                          json={"url": "https://example.com/"}).status_code == 401
        assert reader.calls == []
        response = httpx.post(bridge.read_url, headers={"Authorization": "Bearer " + bridge.token},
                              json={"url": "https://example.com/"})
        assert response.status_code == 200 and response.json()["status"] == "READ"
        assert reader.calls == [("https://example.com/", bridge._deadline)]
    assert reader.closed == 1


def test_public_read_invalid_envelope_fails_closed_and_absent_service_has_no_route():
    class Reader:
        def read(self, url, *, deadline): return {"status": "READ", "evidence": {"secret": "private"}, "review_status": "UNREVIEWED", "replayed": False}
        def close(self): pass

    with ResponsesBridge(api_key=KEY, model="m", max_requests=1, deadline=monotonic()+10,
                         allowed_tools=(), read_service=Reader(),
                         transport=httpx.MockTransport(lambda _: None)) as bridge:
        response = httpx.post(bridge.read_url, headers={"Authorization": "Bearer " + bridge.token},
                              json={"url": "https://example.com/"})
        assert response.json() == {"status": "FAILED", "code": "unavailable", "replayed": False}
        assert "private" not in response.text
    with ResponsesBridge(api_key=KEY, model="m", max_requests=1, deadline=monotonic()+10,
                         allowed_tools=(), transport=httpx.MockTransport(lambda _: None)) as bridge:
        assert bridge.read_url is None
        assert httpx.post(bridge.base_url + "/public-read").status_code == 404


@pytest.mark.parametrize("effect_dispatcher,read_service", [(False, None), (None, object())])
def test_new_bridge_dependencies_require_callable_interfaces(effect_dispatcher, read_service):
    with pytest.raises(Exception, match="^invalid_config$"):
        ResponsesBridge(api_key=KEY, model="m", max_requests=1, deadline=monotonic()+10,
                        allowed_tools=(), effect_dispatcher=effect_dispatcher, read_service=read_service)


@pytest.mark.parametrize("case", ["auth", "path", "method", "malformed", "oversized", "expired"])
def test_local_admission_rejects_without_provider(case):
    calls = 0
    def provider(_):
        nonlocal calls
        calls += 1
        raise AssertionError("provider must not be called")
    deadline = monotonic()-1 if case == "expired" else monotonic()+10
    with ResponsesBridge(api_key=KEY, model="m", max_requests=1, deadline=deadline,
                         allowed_tools=ALLOWED, transport=httpx.MockTransport(provider)) as bridge:
        headers = {"Authorization": "Bearer " + ("wrong" if case == "auth" else bridge.token)}
        url = bridge.base_url + ("/wrong" if case == "path" else "/responses")
        if case == "method": response = httpx.get(url, headers=headers)
        elif case == "malformed": response = httpx.post(url, headers={**headers, "content-type": "application/json"}, content=b"{")
        elif case == "oversized": response = httpx.post(url, headers={**headers, "content-type": "application/json"}, content=b'"' + b"x"*(2*1024*1024) + b'"')
        else: response = httpx.post(url, headers=headers, json={"tools": [], "input": []})
        assert response.status_code in {400, 401, 404, 405, 408, 413}
        assert KEY not in response.text
    assert calls == 0


def test_attempt_cap_is_reserved_before_io_and_requests_are_serial():
    entered = threading.Event(); release = threading.Event(); active = 0; peak = 0
    def provider(_):
        nonlocal active, peak
        active += 1; peak = max(peak, active); entered.set(); release.wait(2); active -= 1
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              content=sse(("response.completed", {"type": "response.completed", "response": {"status": "completed", "output": []}})))
    with ResponsesBridge(api_key=KEY, model="m", max_requests=1, deadline=monotonic()+10,
                         allowed_tools=ALLOWED, transport=httpx.MockTransport(provider)) as bridge:
        result = []
        t = threading.Thread(target=lambda: result.append(request(bridge, {"tools": [], "input": []})))
        t.start(); assert entered.wait(1)
        capped = request(bridge, {"tools": [], "input": []})
        release.set(); t.join()
        assert capped.status_code == 429 and result[0].status_code == 200 and peak == 1


@pytest.mark.parametrize("provider", [
    lambda _: httpx.Response(400, content=b"private-provider-body"),
    lambda _: (_ for _ in ()).throw(httpx.ConnectError("private-network-error")),
    lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, content=b"event: response.output_item.added\ndata: {bad}\n\n"),
    lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse(
        ("response.output_item.added", {"type": "response.output_item.added", "item": {"type": "function_call", "name": "unknown", "arguments": "{}"}}))),
])
def test_provider_failures_are_fixed_safe_errors(provider):
    with ResponsesBridge(api_key=KEY, model="m", max_requests=1, deadline=monotonic()+10,
                         allowed_tools=ALLOWED, transport=httpx.MockTransport(provider)) as bridge:
        response = request(bridge, {"tools": [], "input": []})
        assert response.status_code == 502
        assert response.json() == {"error": {"code": "provider_error"}}
        assert KEY not in repr(bridge.records)
        assert "private" not in repr(bridge.records) + response.text


def test_cleanup_releases_listener():
    bridge = ResponsesBridge(api_key=KEY, model="m", max_requests=1, deadline=monotonic()+10,
                             allowed_tools=ALLOWED, transport=httpx.MockTransport(lambda _: None))
    bridge.__enter__(); url = bridge.base_url; bridge.__exit__(None, None, None)
    with pytest.raises(httpx.TransportError):
        httpx.post(url + "/responses", timeout=.2)


def test_deadline_expiring_during_provider_io_cannot_become_success():
    def provider(_):
        time.sleep(.05)
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              content=sse(("response.completed", {"type": "response.completed", "response": {
                                  "status": "completed", "output": []}})))
    with ResponsesBridge(api_key=KEY, model="m", max_requests=1, deadline=monotonic()+.02,
                         allowed_tools=ALLOWED, transport=httpx.MockTransport(provider)) as bridge:
        response = request(bridge, {"tools": [], "input": []})
        assert response.status_code == 408
        assert response.json() == {"error": {"code": "deadline_exceeded"}}


@pytest.mark.parametrize("deadline", [True, float("nan"), float("inf"), float("-inf")])
def test_deadline_must_be_a_finite_number(deadline):
    with pytest.raises(Exception) as caught:
        ResponsesBridge(api_key=KEY, model="m", max_requests=1, deadline=deadline,
                        allowed_tools=ALLOWED, transport=httpx.MockTransport(lambda _: None))
    assert str(caught.value) == "invalid_config"


def test_incomplete_request_body_is_bounded_by_mission_deadline():
    with ResponsesBridge(api_key=KEY, model="m", max_requests=1, deadline=monotonic()+.15,
                         allowed_tools=ALLOWED, transport=httpx.MockTransport(lambda _: None)) as bridge:
        port = int(bridge.base_url.rsplit(":", 1)[1].split("/", 1)[0])
        with socket.create_connection(("127.0.0.1", port), timeout=1) as client:
            client.sendall(("POST /v1/responses HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                            f"Authorization: Bearer {bridge.token}\r\nContent-Type: application/json\r\n"
                            "Content-Length: 100\r\n\r\n{}").encode())
            client.settimeout(1)
            response = client.recv(1000)
        assert b" 408 " in response or response == b""


def test_context_close_disconnects_an_inflight_local_request():
    entered = threading.Event(); release = threading.Event()
    def provider(_):
        entered.set(); release.wait(2)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse(
            ("response.completed", {"type": "response.completed", "response": {"status": "completed", "output": []}})))
    bridge = ResponsesBridge(api_key=KEY, model="m", max_requests=1, deadline=monotonic()+5,
                             allowed_tools=ALLOWED, transport=httpx.MockTransport(provider)).__enter__()
    result = []
    def local_request():
        try:
            result.append(request(bridge, {"tools": [], "input": []}))
        except httpx.TransportError:
            result.append(None)
    thread = threading.Thread(target=local_request)
    thread.start(); assert entered.wait(1)
    assert bridge.records == [{"ordinal": 1, "status": "unknown", "code": "in_flight",
                               "usage": None, "elapsed_seconds": 0.0}]
    started = monotonic(); bridge.__exit__(None, None, None)
    assert monotonic() - started < 1
    release.set(); thread.join(1)
    assert not thread.is_alive()
    assert result == [None] or result[0].status_code != 200
    assert bridge.records == [{"ordinal": 1, "status": "unknown", "code": "in_flight",
                               "usage": None, "elapsed_seconds": 0.0}]


def test_real_responses_sse_sequence_accepts_final_done_sentinel():
    def provider(req):
        alias = json.loads(req.content)["tools"][0]["name"]
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=real_sse(alias))
    tools = [{"type": "namespace", "name": ALLOWED[0][0], "tools": [
        {"type": "function", "name": ALLOWED[0][1], "parameters": {"type": "object"}}]}]
    with ResponsesBridge(api_key=KEY, model="m", max_requests=1, deadline=monotonic()+5,
                         allowed_tools=ALLOWED, transport=httpx.MockTransport(provider)) as bridge:
        response = request(bridge, {"stream": True, "tools": tools, "input": []})
        assert response.status_code == 200
        assert response.text.endswith("data: [DONE]\n\n")
        events = [json.loads(line[6:]) for line in response.text.splitlines()
                  if line.startswith("data: ") and line != "data: [DONE]"]
        call = next(event["item"] for event in events if event["type"] == "response.output_item.done")
        assert (call["namespace"], call["name"]) == ALLOWED[0]
        assert call["arguments"] == '{"url":"https://example.com/"}'


@pytest.mark.parametrize("body", [
    b"data: [DONE]\n\n",
    sse(("response.failed", {"type": "response.failed", "response": {"status": "failed"}}))
        + sse(("response.completed", {"type": "response.completed", "response": {"status": "completed", "output": []}})),
    sse(("response.completed", {"type": "response.completed", "response": {"status": "completed", "output": []}})) * 2,
    sse(("response.completed", {"type": "response.completed", "response": {"status": "completed", "output": []}}))
        + sse(("response.in_progress", {"type": "response.in_progress", "response": {"status": "in_progress"}})),
])
def test_invalid_terminal_sequences_fail_closed(body):
    provider = lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)
    with ResponsesBridge(api_key=KEY, model="m", max_requests=1, deadline=monotonic()+5,
                         allowed_tools=ALLOWED, transport=httpx.MockTransport(provider)) as bridge:
        assert request(bridge, {"tools": [], "input": []}).status_code == 502


def test_unallowed_actual_custom_tool_calls_fail_but_output_business_data_is_untouched():
    completed = lambda output: httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse(
        ("response.completed", {"type": "response.completed", "response": {
            "status": "completed", "output": output}})))
    providers = [
        lambda _: completed([{"type": "custom_tool_call", "name": "forbidden", "input": "{}"}]),
        lambda _: completed([{"type": "function_call_output", "call_id": "c1", "output": {
            "type": "custom_tool_call", "name": "business-value"}}]),
    ]
    with ResponsesBridge(api_key=KEY, model="m", max_requests=2, deadline=monotonic()+5,
                         allowed_tools=ALLOWED, transport=httpx.MockTransport(lambda req: providers.pop(0)(req))) as bridge:
        assert request(bridge, {"tools": [], "input": []}).status_code == 502
        accepted = request(bridge, {"tools": [], "input": [{"type": "function_call_output", "call_id": "c1",
                            "output": {"type": "custom_tool_call", "name": "business-value"}}]})
        assert accepted.status_code == 200
        assert "business-value" in accepted.text

    with ResponsesBridge(api_key=KEY, model="m", max_requests=1, deadline=monotonic()+5,
                         allowed_tools=ALLOWED, transport=httpx.MockTransport(lambda _: completed([]))) as bridge:
        rejected = request(bridge, {"tools": [], "input": [
            {"type": "custom_tool_call", "name": "forbidden", "input": "{}"}]})
        assert rejected.status_code == 400


def test_drip_sse_cannot_extend_absolute_deadline(monkeypatch):
    body = sse(("response.completed", {"type": "response.completed", "response": {
        "status": "completed", "output": []}})) + b"data: [DONE]\n\n"

    class Drip(BaseHTTPRequestHandler):
        def log_message(self, *_):
            return
        def do_POST(self):
            length = int(self.headers["content-length"])
            self.rfile.read(length)
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            try:
                for byte in body:
                    self.wfile.write(bytes([byte])); self.wfile.flush(); time.sleep(.04)
            except (BrokenPipeError, ConnectionResetError):
                pass

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Drip)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True); thread.start()
    monkeypatch.setattr("pilot.responses_bridge._UPSTREAM",
                        f"http://127.0.0.1:{upstream.server_port}/responses")
    started = monotonic()
    try:
        with ResponsesBridge(api_key=KEY, model="m", max_requests=1, deadline=started+.2,
                             allowed_tools=ALLOWED, transport=httpx.HTTPTransport(retries=0)) as bridge:
            response = request(bridge, {"tools": [], "input": []})
            assert response.status_code == 408
    finally:
        upstream.shutdown(); upstream.server_close(); thread.join(1)
    assert monotonic() - started < .8


def test_drip_response_headers_cannot_extend_absolute_deadline(monkeypatch):
    class DripHeaders(BaseHTTPRequestHandler):
        def log_message(self, *_):
            return
        def do_POST(self):
            self.rfile.read(int(self.headers["content-length"]))
            raw = (b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
                   b"Content-Length: 1\r\nConnection: close\r\nX-Drip: 123456789012345\r\n\r\nx")
            try:
                for byte in raw:
                    self.connection.sendall(bytes([byte])); time.sleep(.04)
            except (BrokenPipeError, ConnectionResetError):
                pass

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), DripHeaders)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True); thread.start()
    monkeypatch.setattr("pilot.responses_bridge._UPSTREAM",
                        f"http://127.0.0.1:{upstream.server_port}/responses")
    started = monotonic()
    try:
        with ResponsesBridge(api_key=KEY, model="m", max_requests=1, deadline=started+.2,
                             allowed_tools=ALLOWED, transport=httpx.HTTPTransport(retries=0)) as bridge:
            response = request(bridge, {"tools": [], "input": []})
            assert response.status_code == 408
            elapsed = monotonic() - started
    finally:
        upstream.shutdown(); upstream.server_close(); thread.join(1)
    assert elapsed < .45
