import hashlib
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from pilot.open_web_reader import PublicReadError
from pilot.read_tool_client import ReadToolClient


def raw(url="https://example.com/"):
    text="ok"
    return {"url":url,"title":None,"text":text,"observed_at":"2026-09-12T01:02:03+00:00","content_sha256":hashlib.sha256(text.encode()).hexdigest(),"read_scope":"PUBLIC_PAGE_TEXT"}


@pytest.mark.parametrize("url", ["https://127.0.0.1:1/v1/public-read","http://localhost:1/v1/public-read","http://user@127.0.0.1:1/v1/public-read","http://127.0.0.1:1/wrong","http://127.0.0.1/v1/public-read"])
def test_strict_configuration(url):
    with pytest.raises(ValueError): ReadToolClient(url=url,token="token")


def test_posts_exact_envelope_and_returns_valid_evidence(monkeypatch):
    seen={}; value=raw()
    original=httpx.Client
    def handler(request):
        seen["request"]=request
        return httpx.Response(200,json={"status":"READ","evidence":value,"review_status":"UNREVIEWED","replayed":False})
    monkeypatch.setattr(httpx,"Client",lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    client=ReadToolClient(url="http://127.0.0.1:1234/v1/public-read",token="token")
    assert client.read(value["url"],deadline=datetime.now(timezone.utc)+timedelta(seconds=2)) == value
    request=seen["request"]
    assert request.url.path == "/v1/public-read"
    assert request.headers["authorization"] == "Bearer token"
    assert request.read() == b'{"url":"https://example.com/"}'


def test_failure_codes_are_mapped(monkeypatch):
    original=httpx.Client
    def client_for(payload):
        return lambda **kw: original(transport=httpx.MockTransport(lambda req:httpx.Response(200,json=payload)),**kw)
    monkeypatch.setattr(httpx,"Client",client_for({"status":"FAILED","code":"timeout","replayed":False}))
    client=ReadToolClient(url="http://127.0.0.1:1234/v1/public-read",token="token")
    with pytest.raises(PublicReadError) as error: client.read("https://example.com/",deadline=datetime.now(timezone.utc)+timedelta(seconds=2))
    assert error.value.code == "timeout"


def test_rejects_evidence_returned_after_absolute_deadline(monkeypatch):
    original = httpx.Client

    def handler(_request):
        time.sleep(0.08)
        return httpx.Response(200, json={
            "status": "READ", "evidence": raw(),
            "review_status": "UNREVIEWED", "replayed": False,
        })

    monkeypatch.setattr(
        httpx, "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    client = ReadToolClient(
        url="http://127.0.0.1:1234/v1/public-read", token="token")

    with pytest.raises(PublicReadError) as error:
        client.read(
            "https://example.com/",
            deadline=datetime.now(timezone.utc) + timedelta(seconds=0.03))

    assert error.value.code == "timeout"


def test_client_timeout_is_capped_at_21_seconds(monkeypatch):
    seen = {}
    original = httpx.Client

    def make_client(**kwargs):
        seen["timeout"] = kwargs["timeout"]
        return original(transport=httpx.MockTransport(lambda _request: httpx.Response(
            200, json={"status": "READ", "evidence": raw(),
                       "review_status": "UNREVIEWED", "replayed": False})), **kwargs)

    monkeypatch.setattr(httpx, "Client", make_client)
    client = ReadToolClient(
        url="http://127.0.0.1:1234/v1/public-read", token="token")

    client.read(
        "https://example.com/",
        deadline=datetime.now(timezone.utc) + timedelta(seconds=60))

    assert seen["timeout"] == 21.0
