"""Windows login host protocol and physical Job cleanup; no platform access."""
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
import time
from types import SimpleNamespace

import pytest

from tests.test_windows_collection_host import Input


SCHEMA = 'windows-platform-login-v1'
ACCOUNT = '66c01234abcdef0123456789'


def module():
    assert importlib.util.find_spec('app.windows_platform_login'), 'login host missing'
    return importlib.import_module('app.windows_platform_login')


def request(tmp_path):
    return dict(schema_version=SCHEMA, runtime_path=str(tmp_path / 'runtime'),
        profile_path=str(tmp_path / 'profile'), output_path=str(tmp_path / 'output'),
        platform='XIAOHONGSHU', timeout_seconds=60)


@pytest.fixture
def source(tmp_path, monkeypatch):
    api = module()
    from app.windows_private_directory import create_private_directory
    runtime = create_private_directory(tmp_path / 'runtime')
    calls, opened = [], []
    monkeypatch.setattr(api, 'verify_installed_runtime', lambda _: Path(sys.executable))
    def runner(command, **kwargs):
        calls.append((command, kwargs))
        output = Path(kwargs['env']['YIKE_LOGIN_OUTPUT_PATH'])
        (output / '.yike-login-opened.json').write_text(json.dumps(dict(schema_version=SCHEMA, state='OPENED')))
        kwargs['poll_callback']()
        kwargs['poll_callback']()
        (output / '.yike-login-terminal.json').write_text(json.dumps(dict(schema_version=SCHEMA,
            state='AUTHENTICATED', account_public_id=ACCOUNT, checked_at='2026-09-10T00:00:00Z')))
        return SimpleNamespace(returncode=0, cancelled=False, timed_out=False, stdout='secret logs', stderr='private token')
    monkeypatch.setattr(api, 'run_supervised_process', runner)
    args = request(tmp_path)
    args.pop('schema_version')
    for name in ('runtime_path', 'profile_path', 'output_path'): args[name] = Path(args[name])
    return SimpleNamespace(api=api, args=args, calls=calls, opened=opened, runner=runner)


@pytest.mark.skipif(sys.platform != 'win32', reason='native private directories')
def test_fixed_worker_launch_environment_private_profile_and_opened_once(source, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'secret')
    monkeypatch.setenv('YIKE_SESSION_TOKEN', 'secret')
    result = source.api.login_windows_platform(**source.args, on_opened=lambda: source.opened.append(True))
    assert result['state'] == 'AUTHENTICATED' and result['account_public_id'] == ACCOUNT
    assert source.opened == [True]
    command, kw = source.calls[0]
    # Portable _pth ignores PYTHONDONTWRITEBYTECODE; the flag must reach the child.
    assert command == [sys.executable, '-B', '-X', 'utf8', str(Path(source.api.__file__).with_name('platform_login_worker.py').resolve())]
    assert kw['cwd'] == source.args['runtime_path']
    assert kw['env']['YIKE_PROFILE_PATH'] == str(source.args['profile_path'])
    assert 'DATABASE_URL' not in kw['env'] and 'YIKE_SESSION_TOKEN' not in kw['env']
    assert kw['env']['PYTHONDONTWRITEBYTECODE'] == '1'
    assert 0 < kw['timeout_seconds'] <= 60 and source.args['profile_path'].is_dir()
    assert 'secret' not in str(result)


@pytest.mark.skipif(sys.platform != 'win32', reason='native browser profile ACL')
def test_browser_atomic_write_acl_can_be_reused_across_login_attempts(source, monkeypatch):
    from tests.test_windows_private_directory import _security
    def runner(command, **kwargs):
        result = source.runner(command, **kwargs)
        local_state = Path(kwargs['env']['YIKE_PROFILE_PATH']) / 'Local State'
        local_state.write_bytes(b'fixture, not account data')
        _security(local_state, _security(local_state).replace(';ID;', ';;'), protected=False)
        return result
    monkeypatch.setattr(source.api, 'run_supervised_process', runner)
    first = source.api.login_windows_platform(**source.args, on_opened=lambda: None)
    assert first['state'] == 'AUTHENTICATED'
    second = source.api.login_windows_platform(**(source.args | {
        'output_path': source.args['output_path'].with_name('output-next')}), on_opened=lambda: None)
    assert second['state'] == 'AUTHENTICATED' and len(source.calls) == 2


@pytest.mark.parametrize('change', [dict(platform='WEIBO'), dict(timeout_seconds=True),
    dict(timeout_seconds=181), dict(runtime_path='relative'), dict(cookie='private'), dict(schema_version='other')])
def test_invalid_request_rejected_before_launch(tmp_path, monkeypatch, change):
    api = module()
    calls = []
    monkeypatch.setattr(api, 'login_windows_platform', lambda **kw: calls.append(kw))
    stream = Input(json.dumps(request(tmp_path) | change).encode() + b'\n')
    output = io.BytesIO()
    try: assert api.main(stream, output) == 0
    finally: stream.closed.set()
    assert json.loads(output.getvalue())['state'] == 'FAILED' and calls == []
    assert b'private' not in output.getvalue()


@pytest.mark.parametrize('frame', [b'{}', b'[]\n', b'{"x":NaN}\n', b'{"x":1,"x":2}\n',
    b'\xff\n', b' ' * 65536 + b'\n'], ids=['no-lf', 'array', 'nan', 'duplicate', 'utf8', 'oversize'])
def test_strict_json_and_byte_limit(frame, monkeypatch):
    api = module()
    calls = []
    monkeypatch.setattr(api, 'login_windows_platform', lambda **kw: calls.append(kw))
    output = io.BytesIO()
    assert api.main(io.BytesIO(frame), output) == 0
    assert json.loads(output.getvalue())['state'] == 'FAILED' and not calls


@pytest.mark.skipif(sys.platform != 'win32', reason='native private directories')
@pytest.mark.parametrize('kind', ['overlap', 'existing-output', 'bad-marker', 'bad-time', 'secret-code', 'cleanup-unknown'])
def test_failures_cannot_claim_authenticated_or_cancelled(source, monkeypatch, kind):
    if kind == 'overlap': source.args['output_path'] = source.args['profile_path'] / 'nested'
    if kind == 'existing-output': source.args['output_path'].mkdir()
    def runner(command, **kw):
        if kind == 'cleanup-unknown': raise OSError('secret unconfirmed cleanup')
        result = source.runner(command, **kw)
        output = Path(kw['env']['YIKE_LOGIN_OUTPUT_PATH'])
        if kind == 'bad-marker': (output / '.yike-login-terminal.json').write_text('{"state":"AUTHENTICATED","secret":"private"}')
        if kind == 'bad-time': (output / '.yike-login-terminal.json').write_text(json.dumps(dict(schema_version=SCHEMA, state='AUTHENTICATED', account_public_id=ACCOUNT, checked_at='tomorrow')))
        if kind == 'secret-code': (output / '.yike-login-terminal.json').write_text(json.dumps(dict(schema_version=SCHEMA, state='FAILED', error_code='secret token')))
        return result
    monkeypatch.setattr(source.api, 'run_supervised_process', runner)
    result = source.api.login_windows_platform(**source.args, on_opened=lambda: None)
    assert result['state'] == 'FAILED' and 'account_public_id' not in result
    if kind == 'cleanup-unknown': assert result['error_code'] == 'SOURCE_HOST_FAILED'
    assert 'secret' not in str(result)


@pytest.mark.parametrize('extra', [b'', b'x'])
def test_opened_then_eof_or_extra_input_waits_for_cleanup_before_terminal(tmp_path, monkeypatch, extra):
    api = module()
    stream = Input(json.dumps(request(tmp_path)).encode() + b'\n')
    stream.extra = extra
    output = io.BytesIO()
    opened, cancelling, cleanup = threading.Event(), threading.Event(), threading.Event()
    def driver(**kwargs):
        kwargs['on_opened'](); opened.set()
        while not kwargs['cancel_requested'](): threading.Event().wait(.005)
        cancelling.set()
        assert cleanup.wait(3)
        return dict(schema_version=SCHEMA, state='CANCELLED')
    monkeypatch.setattr(api, 'login_windows_platform', driver)
    thread = threading.Thread(target=lambda: api.main(stream, output))
    thread.start()
    try:
        assert opened.wait(3)
        stream.closed.set()
        assert cancelling.wait(3)
        assert thread.is_alive() and len(output.getvalue().splitlines()) == 1
    finally:
        cleanup.set(); stream.closed.set(); thread.join(3)
    assert [json.loads(line)['state'] for line in output.getvalue().splitlines()] == ['OPENED', 'CANCELLED']


def test_real_fixed_module_invalid_stdin_never_leaks():
    module()
    proc = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'app.windows_platform_login'],
        input=b'{"private":"token"}\n', capture_output=True, timeout=10,
        cwd=Path(__file__).resolve().parents[1])
    assert proc.returncode == 0 and proc.stderr == b''
    assert len(proc.stdout.splitlines()) == 1 and json.loads(proc.stdout)['state'] == 'FAILED'
    assert b'private' not in proc.stdout


@pytest.mark.skipif(sys.platform != 'win32', reason='actual Windows Job')
@pytest.mark.parametrize('cancel', [True, False])
def test_real_job_cancellation_or_timeout_stops_owned_descendant_before_terminal(source, monkeypatch, cancel):
    from app.collector import run_supervised_process
    script = '''import json, os, subprocess, sys, time
from pathlib import Path
out = Path(os.environ['YIKE_LOGIN_OUTPUT_PATH'])
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
(out / 'child.pid').write_text(str(child.pid))
(out / '.yike-login-opened.json').write_text(json.dumps(dict(schema_version='windows-platform-login-v1', state='OPENED')))
time.sleep(120)
'''
    def runner(command, **kwargs):
        return run_supervised_process([sys.executable, '-X', 'utf8', '-c', script], **kwargs)
    monkeypatch.setattr(source.api, 'run_supervised_process', runner)
    pidfile = source.args['output_path'] / 'child.pid'
    result = source.api.login_windows_platform(**(source.args | {'timeout_seconds': 1}),
        on_opened=lambda: source.opened.append(True), cancel_requested=lambda: cancel and pidfile.exists())
    assert result['state'] == ('CANCELLED' if cancel else 'TIMED_OUT')
    assert source.opened == [True]
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x100000, False, int(pidfile.read_text()))
    if handle:
        try: assert kernel.WaitForSingleObject(handle, 0) == 0
        finally: kernel.CloseHandle(handle)


@pytest.mark.parametrize('cancel', [True, False])
def test_real_pipe_opened_then_terminal_and_no_buffered_stdin_shutdown_deadlock(tmp_path, cancel):
    module()
    marker = tmp_path / 'fixture-stop'
    script = '''import sys, time
from pathlib import Path
from app import windows_platform_login as host
def driver(**kw):
    kw['on_opened']()
    if sys.argv[2] == 'cancel':
        while not kw['cancel_requested'](): time.sleep(.005)
        Path(sys.argv[1]).write_text('physically-stopped')
        return dict(schema_version=host.SCHEMA, state='CANCELLED')
    return dict(schema_version=host.SCHEMA, state='AUTHENTICATED', account_public_id='66c01234abcdef0123456789', checked_at='2026-09-10T00:00:00Z')
host.login_windows_platform = driver
raise SystemExit(host.main())
'''
    proc = subprocess.Popen([sys.executable, '-X', 'utf8', '-c', script, str(marker),
        'cancel' if cancel else 'success'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=Path(__file__).resolve().parents[1])
    frames = queue.Queue()
    def read():
        for line in proc.stdout: frames.put(line)
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        proc.stdin.write(json.dumps(request(tmp_path)).encode() + b'\n'); proc.stdin.flush()
        assert json.loads(frames.get(timeout=5))['state'] == 'OPENED'
        if cancel: proc.stdin.close()
        result = json.loads(frames.get(timeout=5))
        assert result['state'] == ('CANCELLED' if cancel else 'AUTHENTICATED')
        assert proc.wait(timeout=5) == 0
        if cancel: assert marker.read_text() == 'physically-stopped'
        else: assert not proc.stdin.closed
        reader.join(3)
        assert frames.empty() and proc.stderr.read() == b''
    finally:
        if proc.poll() is None: proc.kill(); proc.wait(timeout=5)
        for stream in (proc.stdin, proc.stdout, proc.stderr): stream.close()
        reader.join(3)
