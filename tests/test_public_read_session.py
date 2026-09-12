import hashlib
import time
from datetime import datetime, timezone

import pytest

from pilot.open_web_reader import PublicReadError
from pilot.public_read_session import PublicReadSession


def evidence(url):
    text = "original"
    return {"url": url, "title": None, "text": text, "observed_at": "2026-09-12T01:02:03+00:00", "content_sha256": hashlib.sha256(text.encode()).hexdigest(), "read_scope": "PUBLIC_PAGE_TEXT"}


class Reader:
    def __init__(self): self.calls=[]; self.closed=False
    def read(self, url, *, deadline):
        assert isinstance(deadline, datetime) and deadline.tzinfo is not None
        self.calls.append((url, deadline)); return evidence(url)
    def close(self): self.closed=True


def dispatcher(kind, payload, deadline, perform):
    assert kind == "READ" and payload == {"url": payload["url"]}
    return perform(deadline)


def test_session_normalizes_checks_allowlist_dispatches_and_caches():
    reader=Reader(); allowed=[]
    session=PublicReadSession(max_reads=1, deadline=time.monotonic()+30,
        allowed_url=lambda url: allowed.append(url) or True,
        effect_dispatcher=dispatcher, reader=reader)
    first=session.read("https://Example.com:443/a#x", deadline=time.monotonic()+10)
    second=session.read("https://example.com/a", deadline=time.monotonic()+10)
    assert first["status"] == "READ" and first["review_status"] == "UNREVIEWED"
    assert second == first | {"replayed": True}
    assert allowed == ["https://example.com/a", "https://example.com/a"]
    assert len(reader.calls) == 1


def test_undiscovered_invalid_and_budget_fail_without_dispatch():
    calls=[]; reader=Reader()
    session=PublicReadSession(max_reads=1, deadline=time.monotonic()+30,
        allowed_url=lambda url: False, effect_dispatcher=lambda **kw: calls.append(kw), reader=reader)
    assert session.read("https://example.com/", deadline=time.monotonic()+10) == {"status":"FAILED","code":"invalid_url","replayed":False}
    assert calls == [] and reader.calls == []


def test_failure_is_cached_and_close_blocks_late_success():
    class Failing(Reader):
        def read(self,url,*,deadline): self.calls.append(url); raise PublicReadError("timeout")
    reader=Failing(); session=PublicReadSession(max_reads=1, deadline=time.monotonic()+30, allowed_url=lambda u:True, effect_dispatcher=dispatcher, reader=reader)
    assert session.read("https://example.com/",deadline=time.monotonic()+10)["code"] == "timeout"
    assert session.read("https://example.com/",deadline=time.monotonic()+10) == {"status":"FAILED","code":"timeout","replayed":True}
    session.close(); assert reader.closed
    assert session.read("https://other.example/",deadline=time.monotonic()+10)["code"] == "closed"


@pytest.mark.parametrize("kwargs", [
    dict(max_reads=0, deadline=time.monotonic()+1, allowed_url=lambda u:True, effect_dispatcher=dispatcher),
    dict(max_reads=1, deadline=float("inf"), allowed_url=lambda u:True, effect_dispatcher=dispatcher),
    dict(max_reads=1, deadline=time.monotonic()+1801, allowed_url=lambda u:True, effect_dispatcher=dispatcher),
])
def test_strict_constructor(kwargs):
    with pytest.raises(ValueError): PublicReadSession(**kwargs)
