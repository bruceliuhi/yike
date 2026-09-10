"""Fixed, synthetic loopback protocol tests; never touch a platform."""
import importlib
import io
import json
import threading

import pytest


SCHEMA = "windows-platform-outreach-v1"


def api():
    return importlib.import_module("app.windows_platform_outreach")


def request(tmp_path):
    return {"schema_version": SCHEMA, "action": "CHECK", "runtime_path": str(tmp_path / "runtime"),
            "profile_path": str(tmp_path / "profile"), "output_path": str(tmp_path / "output"),
            "context": {"opaque": "body stays off argv"}, "timeout_seconds": 60}


@pytest.mark.parametrize("wire", [b"{}\n", b'{"x":NaN}\n', b'{"x":1,"x":2}\n', b"x" * 131072 + b"\n"])
def test_strict_first_frame_rejects_before_launch(tmp_path, monkeypatch, wire):
    host = api(); calls = []
    monkeypatch.setattr(host, "run_outreach", lambda **kw: calls.append(kw))
    output = io.BytesIO()
    assert host.main(io.BytesIO(wire), output) == 0
    assert json.loads(output.getvalue())["error_code"] == "OUTREACH_HOST_FAILED" and not calls


def test_operation_is_one_strict_frame_after_ready(tmp_path, monkeypatch):
    host = api(); calls = []
    monkeypatch.setattr(host, "_paths", lambda *values: tuple(tmp_path / str(i) for i, _ in enumerate(values)))
    monkeypatch.setattr(host, "run_outreach", lambda **kw: calls.append(kw) or (kw["on_ready"]({"status":"AVAILABLE"}) and {"observation":{"status":"AVAILABLE"}, "outcome": {"status": "UNKNOWN"}, "cleanupConfirmed": True}))
    stream = io.BytesIO((json.dumps(request(tmp_path)) + "\n" + json.dumps({"schema_version": SCHEMA, "action": "EXECUTE", "operation": {"requestId": "x", "claimId": "y", "dispatchBefore": "z"}}) + "\n").encode())
    output = io.BytesIO(); assert host.main(stream, output) == 0
    assert [json.loads(x)["state"] for x in output.getvalue().splitlines()] == ["READY", "RESULT"]
    assert len(calls) == 1


def test_duplicate_or_early_execute_is_not_run(tmp_path, monkeypatch):
    host = api(); calls = []
    monkeypatch.setattr(host, "run_outreach", lambda **kw: calls.append(kw) or {"observation":{}, "outcome": {}, "cleanupConfirmed": True})
    bad = {"schema_version": SCHEMA, "action": "EXECUTE", "operation": {}}
    output = io.BytesIO(); host.main(io.BytesIO((json.dumps(bad) + "\n").encode()), output)
    assert not calls and json.loads(output.getvalue())["state"] == "FAILED"
