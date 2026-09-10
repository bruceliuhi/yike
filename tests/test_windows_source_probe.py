"""Read-only governed install probe: no browser/source execution or capabilities."""
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

import pytest
from tests.test_windows_collection_host import Input


def module():
    assert importlib.util.find_spec('app.windows_source_probe'), 'source probe missing'
    return importlib.import_module('app.windows_source_probe')


def frame(path):
    return (json.dumps(dict(schema_version='windows-source-probe-v1', runtime_path=str(path))) + '\n').encode()


def test_probe_verifies_only_under_runtime_lock_and_emits_no_details(tmp_path, monkeypatch):
    api = module()
    events = []
    from contextlib import contextmanager
    @contextmanager
    def locked(paths):
        assert paths == [tmp_path]
        events.append('locked'); yield; events.append('unlocked')
    def verify(path):
        assert events == ['locked'] and path == tmp_path
        events.append('verified')
        print('private diagnostic')
        return tmp_path / 'private-python.exe'
    monkeypatch.setattr(api, '_exclusive_paths', locked)
    monkeypatch.setattr(api, 'verify_installed_runtime', verify)
    stream, output = Input(frame(tmp_path)), io.BytesIO()
    try: assert api.main(stream, output) == 0
    finally: stream.closed.set()
    assert json.loads(output.getvalue()) == dict(schema_version='windows-source-probe-v1', state='READY')
    assert events == ['locked', 'verified', 'unlocked'] and len(output.getvalue()) < 16384


@pytest.mark.parametrize('raw', [b'{}', b'[]\n', b'{"x":NaN}\n', b'{"x":1,"x":2}\n',
    b'\xff\n', b' ' * 65536 + b'\n'], ids=['no-lf', 'array', 'nan', 'duplicate', 'utf8', 'overlong'])
def test_invalid_probe_input_is_one_sanitized_failure(raw, monkeypatch):
    api = module(); calls = []
    monkeypatch.setattr(api, 'verify_installed_runtime', lambda _: calls.append(True))
    out = io.BytesIO(); assert api.main(io.BytesIO(raw), out) == 0
    assert json.loads(out.getvalue())['state'] == 'FAILED' and not calls
    assert len(out.getvalue().splitlines()) == 1


def test_eof_cancel_never_reports_ready_after_verification(tmp_path, monkeypatch):
    api = module(); stream = Input(frame(tmp_path)); output = io.BytesIO()
    def verify(_):
        stream.closed.set()
        assert stream.reading.wait(2)
        return tmp_path
    monkeypatch.setattr(api, 'verify_installed_runtime', verify)
    stream.closed.set()
    api.main(stream, output)
    assert json.loads(output.getvalue())['state'] == 'FAILED'


@pytest.mark.skipif(sys.platform != 'win32', reason='actual Windows private install')
def test_actual_installed_probe_real_fixed_module_is_read_only():
    api = module()
    installed = Path(os.environ.get('YIKE_SOURCE_INSTALLED_CHECK',
        'C:/Users/bruce/AI/意客AI2026/.runtime/windows-installed-xhs-20260910-02'))
    if not installed.exists(): pytest.skip('Operator installed runtime unavailable; never downloads')
    receipt = installed / '.yike-windows-install.json'
    before = receipt.read_bytes()
    proc = subprocess.Popen([sys.executable, '-X', 'utf8', '-m', 'app.windows_source_probe'],
        cwd=Path(api.__file__).resolve().parents[1], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    result = queue.Queue()
    reader = threading.Thread(target=lambda: result.put(proc.stdout.readline()), daemon=True); reader.start()
    try:
        proc.stdin.write(frame(installed)); proc.stdin.flush()
        assert json.loads(result.get(timeout=30)) == dict(schema_version='windows-source-probe-v1', state='READY')
        assert proc.wait(timeout=5) == 0 and proc.stderr.read() == b'' and proc.stdout.read() == b''
        assert receipt.read_bytes() == before
    finally:
        if proc.poll() is None: proc.kill(); proc.wait(timeout=5)
        for stream in (proc.stdin, proc.stdout, proc.stderr): stream.close()
        reader.join(3)
