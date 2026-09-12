import json
import socket
import threading
import time
from time import monotonic

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
    started = monotonic(); bridge.__exit__(None, None, None)
    assert monotonic() - started < 1
    release.set(); thread.join(1)
    assert not thread.is_alive()
    assert result == [None] or result[0].status_code != 200
