"""Synthetic private reply bridge tests; never touch a platform."""
import asyncio
import importlib
import socket
import threading
import io
import json
import time
from contextlib import asynccontextmanager

import pytest


SCHEMA = "windows-platform-outreach-v1"
ROOT = "a" * 24
CLAIMED = "2026-09-11T10:00:00+00:00"
READ = {"readReplies": {"rootCommentId": ROOT, "claimedAt": CLAIMED}}
OBS = {"status": "AVAILABLE"}


def test_read_replies_second_frame_has_distinct_internal_operation():
    host = importlib.import_module("app.windows_platform_outreach")
    external = {"schema_version": SCHEMA, "action": "READ_REPLIES",
                "operation": {"rootCommentId": ROOT, "claimedAt": CLAIMED}}
    assert host._second(io.BytesIO(host._wire(external))) == READ
    assert host._read_operation(READ) == READ


@pytest.mark.parametrize("operation", [
    {"readReplies": {"rootCommentId": ROOT, "claimedAt": CLAIMED}, "requestId": "r"},
    {"readReplies": {"rootCommentId": ROOT, "claimedAt": CLAIMED, "extra": True}},
    {"readReplies": {"rootCommentId": "A" * 24, "claimedAt": CLAIMED}},
    {"readReplies": {"rootCommentId": ROOT, "claimedAt": "2026-09-11T10:00:00"}},
])
def test_internal_read_operation_rejects_mixed_extra_or_invalid(operation):
    host = importlib.import_module("app.windows_platform_outreach")
    with pytest.raises(ValueError):
        host._read_operation(operation)


def test_worker_read_replies_uses_read_method_exactly_once(monkeypatch):
    worker = importlib.import_module("app.platform_outreach_worker")
    runtime = importlib.import_module("app.platform_outreach_runtime")
    calls = []

    class Channel:
        async def check(self, context):
            return OBS

        async def execute(self, *args):
            pytest.fail("read operation must not execute")

        async def read_replies(self, context, root_comment_id, claimed_at):
            calls.append((context, root_comment_id, claimed_at))
            return {"status": "COMPLETE", "items": [{"body": "x" * 40000}]}

    @asynccontextmanager
    async def opened(context, **kwargs):
        yield Channel()

    monkeypatch.setattr(runtime, "open_xhs_comment_channel", opened)
    local, peer = socket.socketpair()
    errors = []

    def child():
        try:
            asyncio.run(worker._run(local))
        except BaseException as exc:
            errors.append(exc)
        finally:
            local.close()

    thread = threading.Thread(target=child, daemon=True)
    thread.start()
    peer.sendall(worker._wire({"context": {"opaque": "context"}}))
    peer.settimeout(1)
    assert b'"state":"READY"' in peer.recv(8192)
    peer.sendall(worker._wire({"operation": READ}))
    received = b""
    while b"\n" not in received:
        received += peer.recv(65536)
    peer.close(); thread.join(1)
    assert not errors
    assert calls == [({"opaque": "context"}, ROOT, CLAIMED)]
    assert len(received) > 32768 and b'"state":"RESULT"' in received


def test_worker_rejects_read_result_over_512k(monkeypatch):
    worker = importlib.import_module("app.platform_outreach_worker")
    runtime = importlib.import_module("app.platform_outreach_runtime")

    class Channel:
        async def check(self, context): return OBS
        async def read_replies(self, *args):
            return {"status": "COMPLETE", "items": [{"body": "x" * (512 * 1024)}]}

    @asynccontextmanager
    async def opened(context, **kwargs): yield Channel()
    monkeypatch.setattr(runtime, "open_xhs_comment_channel", opened)
    local, peer = socket.socketpair(); errors = []
    def child():
        try: asyncio.run(worker._run(local))
        except BaseException as exc: errors.append(exc)
        finally: local.close()
    thread = threading.Thread(target=child, daemon=True); thread.start()
    peer.sendall(worker._wire({"context": {}})); peer.settimeout(1); assert b"READY" in peer.recv(8192)
    peer.sendall(worker._wire({"operation": READ})); thread.join(1); peer.close()
    assert errors


def test_main_allows_large_result_only_after_read_is_accepted(tmp_path, monkeypatch):
    host = importlib.import_module("app.windows_platform_outreach")
    monkeypatch.setattr(host, "_paths", lambda *values: tuple(tmp_path / str(i) for i, _ in enumerate(values)))
    outcome = {"status": "COMPLETE", "items": [{"body": "x" * 40000}]}

    def run(**kwargs):
        kwargs["on_ready"](OBS)
        peer.sendall(host._wire({"schema_version": SCHEMA, "action": "READ_REPLIES",
                                 "operation": {"rootCommentId": ROOT, "claimedAt": CLAIMED}}))
        end = time.monotonic() + 1
        while time.monotonic() < end:
            if kwargs["take_operation"]() == READ:
                peer.shutdown(socket.SHUT_WR)
                return {"observation": OBS, "outcome": outcome, "cleanupConfirmed": True}
            time.sleep(.001)
        pytest.fail("read operation not delivered")

    monkeypatch.setattr(host, "run_outreach", run)
    local, peer = socket.socketpair(); peer.sendall(host._wire({
        "schema_version": SCHEMA, "action": "CHECK", "runtime_path": "C:\\runtime",
        "profile_path": "D:\\profile", "output_path": "E:\\output",
        "context": {}, "timeout_seconds": 60}))
    output = io.BytesIO()
    with local, peer, local.makefile("rb") as stream:
        assert host.main(stream, output) == 0
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [message["state"] for message in messages] == ["READY", "RESULT"]
    assert messages[1]["outcome"] == outcome
    assert len(output.getvalue()) > 32768


@pytest.mark.parametrize("operation", [
    {"readReplies": {"rootCommentId": ROOT, "claimedAt": CLAIMED},
     "requestId": "r", "claimId": "c", "dispatchBefore": "z"},
    {"readReplies": {"rootCommentId": ROOT, "claimedAt": CLAIMED, "extra": 1}},
])
def test_worker_rejects_mixed_or_extra_read_operation_before_channel_action(monkeypatch, operation):
    worker = importlib.import_module("app.platform_outreach_worker")
    runtime = importlib.import_module("app.platform_outreach_runtime")
    acted = threading.Event()
    class Channel:
        async def check(self, context): return OBS
        async def execute(self, *args): acted.set()
        async def read_replies(self, *args): acted.set()
    @asynccontextmanager
    async def opened(context, **kwargs): yield Channel()
    monkeypatch.setattr(runtime, "open_xhs_comment_channel", opened)
    local, peer = socket.socketpair()
    def child():
        try: asyncio.run(worker._run(local))
        except BaseException: pass
        finally: local.close()
    thread = threading.Thread(target=child, daemon=True); thread.start()
    peer.sendall(worker._wire({"context": {}})); peer.settimeout(1); assert b"READY" in peer.recv(8192)
    peer.sendall(worker._wire({"operation": operation})); thread.join(1); peer.close()
    assert not acted.is_set()


def test_worker_eof_cancels_inflight_read_and_closes_channel(monkeypatch):
    worker = importlib.import_module("app.platform_outreach_worker")
    runtime = importlib.import_module("app.platform_outreach_runtime")
    entered, closed = threading.Event(), threading.Event()
    class Channel:
        async def check(self, context): return OBS
        async def read_replies(self, *args):
            entered.set()
            await asyncio.Event().wait()
    @asynccontextmanager
    async def opened(context, **kwargs):
        try: yield Channel()
        finally: closed.set()
    monkeypatch.setattr(runtime, "open_xhs_comment_channel", opened)
    local, peer = socket.socketpair()
    def child():
        try: asyncio.run(worker._run(local))
        except BaseException: pass
        finally: local.close()
    thread = threading.Thread(target=child, daemon=True); thread.start()
    peer.sendall(worker._wire({"context": {}})); peer.settimeout(1); assert b"READY" in peer.recv(8192)
    peer.sendall(worker._wire({"operation": READ})); assert entered.wait(1)
    peer.shutdown(socket.SHUT_WR)
    assert closed.wait(.5)
    peer.close(); thread.join(.5)
    assert not thread.is_alive()
