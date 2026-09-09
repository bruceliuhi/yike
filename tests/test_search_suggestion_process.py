"""Synthetic loopback HTTP and real owned child-process lifecycle tests."""
import importlib.util
import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


DESCRIPTION = "我们为制造企业提供设备维修与预防性维护。"
CONTENT = dict(keywords=["设备维修服务"], exclusions=[], rationale="业务介绍明确提供设备维护。",
               evidence=["设备维修与预防性维护"], unknowns=["服务地区尚未明确"])
USAGE = dict(prompt_tokens=10, completion_tokens=20, total_tokens=30)


def module():
    assert importlib.util.find_spec("pilot.search_suggestion_process") is not None, "process runner is missing"
    from pilot import search_suggestion_process
    return search_suggestion_process


@contextmanager
def provider(mode="success"):
    received, stop = threading.Event(), threading.Event()
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            requests.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            received.set()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if mode == "slow":
                try:
                    while not stop.wait(0.02):
                        self.wfile.write(b" ")
                        self.wfile.flush()
                except OSError:
                    pass
            else:
                body = dict(choices=[dict(finish_reason="stop", message=dict(
                    role="assistant", content=json.dumps(CONTENT, ensure_ascii=False)))], usage=USAGE)
                self.wfile.write(json.dumps(body, ensure_ascii=False).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", received, requests
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        serving.join(timeout=3)
        assert not serving.is_alive()


@pytest.fixture
def children(monkeypatch):
    original = subprocess.Popen
    created = []

    def track(*args, **kwargs):
        child = original(*args, **kwargs)
        created.append((child, args, kwargs))
        return child

    monkeypatch.setattr(subprocess, "Popen", track)
    yield created
    for child, _, _ in created:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=3)


def runner(base_url, **changes):
    return module().ProcessSearchSuggestionModel(base_url=base_url, api_key="synthetic-process-key",
        model="synthetic-model", **changes)


def test_real_child_returns_grounded_result_then_exits(children, monkeypatch):
    monkeypatch.setenv("YIKE_PILOT_ADMIN_DATABASE_URL", "synthetic-never-inherited")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    with provider() as (url, received, requests):
        model = runner(url)
        try:
            content, usage = model.generate(description=DESCRIPTION)
            assert content.model_dump() == CONTENT
            assert usage == USAGE
            assert received.is_set() and len(requests) == 1
            assert requests[0][0] == "/chat/completions"
            assert json.loads(requests[0][1]["messages"][1]["content"]) == {"description": DESCRIPTION}
            assert model.provider == "openai-compatible" and model.model == "synthetic-model"
            assert children[0][0].poll() == 0
            _, args, kwargs = children[0]
            assert "synthetic-process-key" not in str(args)
            assert DESCRIPTION not in str(args)
            assert "YIKE_PILOT_ADMIN_DATABASE_URL" not in kwargs["env"]
            assert "HTTP_PROXY" not in kwargs["env"]
            assert kwargs["stderr"] == subprocess.DEVNULL
            assert not kwargs.get("shell", False)
        finally:
            assert model.close()
            assert model.close()


def test_total_deadline_stops_continuously_active_stream(children):
    from pilot.search_suggestion_model import SearchSuggestionError
    with provider("slow") as (url, received, requests):
        model = runner(url, timeout_seconds=1, total_timeout_seconds=2)
        started = time.monotonic()
        try:
            with pytest.raises(SearchSuggestionError) as caught:
                model.generate(description=DESCRIPTION)
            assert caught.value.code == "suggestion_result_unknown"
            assert caught.value.__context__ is None
            assert received.is_set() and len(requests) == 1
            assert children[0][0].poll() is not None
            assert time.monotonic() - started < 5.5
        finally:
            assert model.close()


def test_close_stops_both_running_children_and_rejects_later_calls(children):
    from pilot.search_suggestion_model import SearchSuggestionError
    with provider("slow") as (url, received, requests):
        model = runner(url, total_timeout_seconds=30)
        with ThreadPoolExecutor(2) as pool:
            calls = [pool.submit(model.generate, description=DESCRIPTION) for _ in range(2)]
            assert received.wait(5)
            deadline = time.monotonic() + 5
            while len(requests) < 2 and time.monotonic() < deadline:
                time.sleep(0.01)
            assert len(requests) == 2
            started = time.monotonic()
            assert model.close(timeout_seconds=5)
            assert time.monotonic() - started < 5.5
            for call in calls:
                with pytest.raises(SearchSuggestionError):
                    call.result(timeout=1)
        assert all(child.poll() is not None for child, _, _ in children)
        with pytest.raises(module().SearchSuggestionProcessUnavailable) as caught:
            model.generate(description=DESCRIPTION)
        assert caught.value.code == "dispatch_failed"
        assert len(children) == 2


def test_stdin_block_before_child_reads_is_inside_total_deadline(monkeypatch, children):
    from pilot.search_suggestion_model import SearchSuggestionError
    tracked = subprocess.Popen

    def stuck_before_read(args, **kwargs):
        return tracked([sys.executable, "-I", "-c", "import time; time.sleep(60)"], **kwargs)

    monkeypatch.setattr(subprocess, "Popen", stuck_before_read)
    model = runner("http://127.0.0.1:1", total_timeout_seconds=1)
    started = time.monotonic()
    try:
        with pytest.raises(SearchSuggestionError) as caught:
            model.generate(description="合成资料" * 2000)
        assert caught.value.code == "suggestion_result_unknown"
        assert time.monotonic() - started < 4.5
        assert children[0][0].poll() is not None
    finally:
        assert model.close()


@pytest.mark.parametrize("seconds", [0, -1, True, 61, float("nan"), float("inf"), "2"])
def test_invalid_total_deadline_does_not_start_child(seconds, children):
    from pilot.search_suggestion_model import SearchSuggestionError
    with pytest.raises(SearchSuggestionError) as caught:
        runner("http://127.0.0.1:1", total_timeout_seconds=seconds)
    assert caught.value.code == "invalid_suggestion_configuration"
    assert not children


def test_third_concurrent_call_is_not_dispatched(children):
    with provider("slow") as (url, received, requests):
        model = runner(url)
        with ThreadPoolExecutor(2) as pool:
            pending = [pool.submit(model.generate, description=DESCRIPTION) for _ in range(2)]
            try:
                deadline = time.monotonic() + 5
                while len(requests) < 2 and time.monotonic() < deadline:
                    time.sleep(0.01)
                assert len(requests) == 2
                with pytest.raises(module().SearchSuggestionProcessUnavailable):
                    model.generate(description=DESCRIPTION)
                assert len(children) == 2
            finally:
                assert model.close()
                for item in pending:
                    assert item.exception(timeout=1) is not None


def test_close_cannot_pass_an_unfinished_process_start(monkeypatch, children):
    tracked = subprocess.Popen
    starting, release = threading.Event(), threading.Event()
    sent = []
    actual_communicate = module()._communicate

    def record_send(*args, **kwargs):
        sent.append(True)
        return actual_communicate(*args, **kwargs)

    monkeypatch.setattr(module(), "_communicate", record_send)

    def delayed_start(*args, **kwargs):
        starting.set()
        assert release.wait(5)
        return tracked(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", delayed_start)
    model = runner("http://127.0.0.1:1")
    with ThreadPoolExecutor(1) as pool:
        call = pool.submit(model.generate, description=DESCRIPTION)
        try:
            assert starting.wait(3)
            assert model.close(timeout_seconds=0.05) is False
            assert model.available is False
        finally:
            release.set()
        assert call.exception(timeout=5) is not None
        assert model.close()
        assert len(children) == 1 and children[0][0].poll() is not None
        assert sent == [], "close won during STARTING; no profile bytes may be dispatched"


@pytest.mark.parametrize("phase", ["dns", "transport_close"])
def test_deadline_includes_stuck_dns_and_transport_cleanup(monkeypatch, children, phase):
    tracked = subprocess.Popen
    with provider() as (url, received, requests):
        def stuck_adapter(args, **kwargs):
            worker = args[-1]
            patch = ("import socket; socket.getaddrinfo=lambda *a,**k: time.sleep(60); " if phase == "dns" else
                     "import httpx; httpx.HTTPTransport.__exit__=lambda *a,**k: time.sleep(60); ")
            script = "import time,runpy; " + patch + "runpy.run_path(__import__('sys').argv[1],run_name='__main__')"
            return tracked([sys.executable, "-I", "-X", "utf8", "-c", script, worker], **kwargs)

        monkeypatch.setattr(subprocess, "Popen", stuck_adapter)
        model = runner(url, total_timeout_seconds=2)
        started = time.monotonic()
        try:
            with pytest.raises(Exception) as caught:
                model.generate(description=DESCRIPTION)
            assert caught.value.code == "suggestion_result_unknown"
            assert time.monotonic() - started < 5.5
            assert children[0][0].poll() is not None
            assert bool(requests) is (phase == "transport_close")
        finally:
            assert model.close()


def test_failed_spawn_is_known_not_dispatched_and_does_not_poison(monkeypatch, children):
    def unavailable(*args, **kwargs):
        raise OSError("synthetic-secret-not-a-public-error")

    monkeypatch.setattr(subprocess, "Popen", unavailable)
    model = runner("http://127.0.0.1:1")
    with pytest.raises(module().SearchSuggestionProcessUnavailable) as caught:
        model.generate(description=DESCRIPTION)
    assert str(caught.value) == "dispatch_failed" and caught.value.__context__ is None
    assert model.available
    assert model.close()
    assert not children


def test_pipe_close_failure_is_safe_unknown_and_poisoned(monkeypatch, children):
    with provider() as (url, received, requests):
        tracked = subprocess.Popen

        def failed_close(*args, **kwargs):
            child = tracked(*args, **kwargs)
            real_close = child.stdin.close

            def close():
                real_close()
                raise OSError("synthetic-secret-close-error")

            child.stdin.close = close
            return child

        monkeypatch.setattr(subprocess, "Popen", failed_close)
        model = runner(url)
        with pytest.raises(Exception) as caught:
            model.generate(description=DESCRIPTION)
        assert getattr(caught.value, "code", None) == "suggestion_result_unknown"
        assert "synthetic-secret" not in str(caught.value)
        assert not model.available
        assert model.close(timeout_seconds=0) is False
        with pytest.raises(module().SearchSuggestionProcessUnavailable):
            model.generate(description=DESCRIPTION)
