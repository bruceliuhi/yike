from __future__ import annotations

import io
import json
import subprocess
import sys
import threading
import time
from datetime import datetime

import pytest

from pilot import public_search_worker as worker
from pilot.public_search import PublicSearchSession, normalize_query, valid_search_result


def _searched(query="中文 需求", **changes):
    value = {
        "status": "SEARCHED",
        "query": query,
        "observed_at": "2026-09-12T01:02:03+00:00",
        "read_scope": "SEARCH_RESULTS",
        "results": [],
        "omitted_count": 0,
        "replayed": False,
    }
    value.update(changes)
    return value


def _install_worker_http(monkeypatch, payload, *, status=200, content_length=None):
    body = json.dumps(payload, ensure_ascii=False).encode()
    seen = {}

    class Response:
        def __init__(self):
            self.status = status

        def getheader(self, name):
            if name.lower() == "content-length":
                return str(len(body) if content_length is None else content_length)
            return None

        def read(self, amount):
            seen["read_amount"] = amount
            return body

    class Connection:
        def __init__(self, host, port, timeout, context):
            seen["connection"] = (host, port, timeout, context is not None)

        def request(self, method, path, body, headers):
            seen["request"] = (method, path, body, headers)

        def getresponse(self):
            return Response()

        def close(self):
            seen["closed"] = True

    monkeypatch.setattr(worker.http.client, "HTTPSConnection", Connection)
    return seen


def test_normalize_query_contract():
    assert normalize_query(" 中文 \t  需求 \n") == "中文 需求"
    for value in ("", "   ", "x" * 513, "ok\x00bad", 123):
        with pytest.raises(ValueError) as error:
            normalize_query(value)  # type: ignore[arg-type]
        assert str(error.value) == "invalid_query"


def test_worker_posts_fixed_request_and_normalizes_deduplicates_and_caps(monkeypatch):
    organic = [
        {"link": "https://Example.com:443/a#frag", "title": " A   title ", "snippet": " S  text ", "date": " yesterday ", "position": 7},
        {"link": "https://example.com/a", "title": "duplicate", "position": 2},
        {"link": "http://unsafe.example/", "title": "unsafe"},
    ] + [{"link": f"https://example.com/{index}", "position": 0} for index in range(20)]
    seen = _install_worker_http(monkeypatch, {"organic": organic})
    result = worker.search_request({"query": "中文 需求", "api_key": "SECRET", "timeout_seconds": 4})

    assert seen["connection"][:3] == ("google.serper.dev", 443, 4)
    method, path, body, headers = seen["request"]
    assert (method, path) == ("POST", "/search")
    assert json.loads(body) == {"q": "中文 需求", "num": 10, "hl": "zh-cn"}
    assert headers["X-API-KEY"] == "SECRET"
    assert len(result["results"]) == 10
    assert result["results"][0] == {"url": "https://example.com/a", "title": "A title", "snippet": "S text", "date_hint": "yesterday", "rank": 7}
    assert result["results"][1]["rank"] == 4
    assert result["omitted_count"] == len(organic) - 10
    assert result["read_scope"] == "SEARCH_RESULTS"
    assert datetime.fromisoformat(result["observed_at"]).utcoffset() is not None
    assert "SECRET" not in json.dumps(result)


def test_worker_nullable_hints_and_empty_organic(monkeypatch):
    _install_worker_http(monkeypatch, {"organic": [{"link": "https://example.com/"}]})
    item = worker.search_request({"query": "q", "api_key": "k", "timeout_seconds": 2})["results"][0]
    assert item == {"url": "https://example.com/", "title": None, "snippet": None, "date_hint": None, "rank": 1}

    _install_worker_http(monkeypatch, {"organic": []})
    assert worker.search_request({"query": "q", "api_key": "k", "timeout_seconds": 2})["results"] == []


@pytest.mark.parametrize("payload", [{}, {"organic": None}, {"organic": {}}, {"organic": ["bad"]}])
def test_worker_malformed_organic_is_not_an_empty_search(monkeypatch, payload):
    _install_worker_http(monkeypatch, payload)
    with pytest.raises(worker.WorkerError) as error:
        worker.search_request({"query": "q", "api_key": "k", "timeout_seconds": 2})
    assert error.value.code == "invalid_search_result"


@pytest.mark.parametrize("status,code", [(401, "auth_failed"), (403, "auth_failed"), (429, "rate_limited"), (500, "unavailable")])
def test_worker_maps_http_status_without_provider_data(monkeypatch, status, code):
    _install_worker_http(monkeypatch, {"error": "SECRET provider detail"}, status=status)
    with pytest.raises(worker.WorkerError) as error:
        worker.search_request({"query": "q", "api_key": "k", "timeout_seconds": 2})
    assert error.value.code == code and "provider" not in str(error.value)


def test_valid_search_result_enforces_exact_schema_and_bounded_fields():
    item = {"url": "https://example.com/", "title": None, "snippet": None, "date_hint": None, "rank": 1}
    assert valid_search_result(_searched(results=[item]), "中文 需求")
    invalid = [
        _searched(extra=True),
        _searched(query="other"),
        _searched(read_scope="READ"),
        _searched(observed_at="2026-09-12T01:02:03"),
        _searched(results=[item | {"title": "x" * 1001}]),
        _searched(results=[item | {"snippet": "x" * 2001}]),
        _searched(results=[item | {"date_hint": "x" * 201}]),
        _searched(results=[item | {"rank": 0}]),
        _searched(results=[item] * 11),
        _searched(omitted_count=-1),
    ]
    assert all(not valid_search_result(value, "中文 需求") for value in invalid)
    assert valid_search_result({"status": "FAILED", "code": "timeout", "replayed": False}, "中文 需求")
    assert not valid_search_result({"status": "FAILED", "code": "secret provider error", "replayed": False}, "中文 需求")


def test_session_caches_canonical_query_and_fixed_failures(monkeypatch):
    calls = []

    class Process:
        returncode = 0

        def communicate(self, data, timeout):
            request = json.loads(data)
            calls.append(request)
            return json.dumps({"ok": False, "code": "rate_limited"}), ""

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: Process())
    session = PublicSearchSession(api_key="synthetic-key", max_searches=2, deadline=time.monotonic() + 30)
    first = session.search(" 中文   需求 ")
    second = session.search("中文 需求")
    assert first == {"status": "FAILED", "code": "rate_limited", "replayed": False}
    assert second == {"status": "FAILED", "code": "rate_limited", "replayed": True}
    assert len(calls) == 1


def test_session_success_process_contract_and_key_only_on_stdin(monkeypatch):
    seen = {}

    class Process:
        returncode = 0

        def communicate(self, data, timeout):
            seen["stdin"] = json.loads(data)
            return json.dumps({"ok": True, "result": _searched()}), ""

    def popen(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return Process()

    monkeypatch.setattr(subprocess, "Popen", popen)
    session = PublicSearchSession(api_key="synthetic-key", max_searches=1, deadline=time.monotonic() + 30)
    result = session.search(" 中文   需求 ")
    assert result["query"] == "中文 需求" and result["replayed"] is False
    assert seen["argv"][1] == "-I" and "synthetic-key" not in " ".join(seen["argv"])
    assert seen["kwargs"]["env"] == {} and seen["kwargs"]["stderr"] is subprocess.DEVNULL
    assert seen["stdin"]["api_key"] == "synthetic-key"


def test_parent_rejects_non_exact_or_key_echoing_worker_output(monkeypatch):
    outputs = iter([
        {"ok": False, "code": "auth_failed", "detail": "synthetic-key"},
        {"ok": True, "result": _searched(results=[{
            "url": "https://user:synthetic-key@example.com/", "title": None,
            "snippet": None, "date_hint": None, "rank": 1,
        }])},
    ])

    class Process:
        returncode = 0

        def communicate(self, data, timeout):
            return json.dumps(next(outputs)), ""

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: Process())
    session = PublicSearchSession(api_key="synthetic-key", max_searches=2, deadline=time.monotonic() + 30)
    for query in ("one", "two"):
        result = session.search(query)
        assert result == {"status": "FAILED", "code": "invalid_search_result", "replayed": False}
        assert "synthetic-key" not in json.dumps(result)


def test_search_limit_deadline_and_close_are_strict_failures(monkeypatch):
    class Process:
        returncode = 0

        def communicate(self, data, timeout):
            query = json.loads(data)["query"]
            return json.dumps({"ok": True, "result": _searched(query=query)}), ""

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: Process())
    session = PublicSearchSession(api_key="k", max_searches=1, deadline=time.monotonic() + 30)
    assert session.search("one")["status"] == "SEARCHED"
    assert session.search("two") == {"status": "FAILED", "code": "search_limit_reached", "replayed": False}
    session.close()
    session.close()
    assert session.search("three") == {"status": "FAILED", "code": "closed", "replayed": False}
    expired = PublicSearchSession(api_key="k", max_searches=1, deadline=time.monotonic() - 1)
    assert expired.search("q") == {"status": "FAILED", "code": "deadline_exceeded", "replayed": False}


def test_concurrent_same_query_consumes_one_attempt(monkeypatch):
    calls = 0
    entered = threading.Event()
    release = threading.Event()

    class Process:
        returncode = 0

        def communicate(self, data, timeout):
            nonlocal calls
            calls += 1
            entered.set()
            assert release.wait(2)
            return json.dumps({"ok": True, "result": _searched(query="same")}), ""

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: Process())
    session = PublicSearchSession(api_key="k", max_searches=1, deadline=time.monotonic() + 30)
    results = []
    threads = [threading.Thread(target=lambda: results.append(session.search("same"))) for _ in range(2)]
    for thread in threads:
        thread.start()
    assert entered.wait(2)
    release.set()
    for thread in threads:
        thread.join(2)
    assert calls == 1
    assert sorted(value["replayed"] for value in results) == [False, True]


def test_close_prevents_spawn_race_and_reaps_real_child(monkeypatch):
    real_popen = subprocess.Popen
    spawned = threading.Event()
    release = threading.Event()
    children = []

    def barrier_popen(*args, **kwargs):
        child = real_popen([sys.executable, "-c", "import time; time.sleep(30)"])
        children.append(child)
        spawned.set()
        assert release.wait(2)
        return child

    monkeypatch.setattr(subprocess, "Popen", barrier_popen)
    session = PublicSearchSession(api_key="synthetic-key", max_searches=2, deadline=time.monotonic() + 5)
    result = []
    search_thread = threading.Thread(target=lambda: result.append(session.search("q")))
    search_thread.start()
    assert spawned.wait(2)
    close_thread = threading.Thread(target=session.close)
    close_thread.start()
    time.sleep(0.05)
    assert close_thread.is_alive()
    release.set()
    search_thread.join(3)
    close_thread.join(3)
    try:
        assert children[0].poll() is not None
        assert session.search("new") == {"status": "FAILED", "code": "closed", "replayed": False}
    finally:
        if children[0].poll() is None:
            children[0].kill()
            children[0].wait()


def test_real_fixture_process_timeout_is_killed_and_reaped(monkeypatch):
    real_popen = subprocess.Popen
    children = []

    def sleeping_process(*args, **kwargs):
        child = real_popen([sys.executable, "-c", "import time; time.sleep(30)"],
                           stdin=kwargs["stdin"], stdout=kwargs["stdout"],
                           stderr=kwargs["stderr"], text=kwargs["text"], env=kwargs["env"])
        children.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", sleeping_process)
    session = PublicSearchSession(api_key="synthetic-key", max_searches=1, deadline=time.monotonic() + 0.05)
    assert session.search("q") == {"status": "FAILED", "code": "timeout", "replayed": False}
    assert children[0].poll() is not None
