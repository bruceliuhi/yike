"""Real Windows supervisor lifecycle; no platform or customer process is started."""
import os
import ctypes
from ctypes import wintypes
import subprocess
import sys
import time

import pytest

from app.collector import run_supervised_process

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='actual Windows lifecycle')


@pytest.fixture
def owned_processes(monkeypatch):
    # Preserve real Popen behavior while retaining exact owned handles for RED cleanup.
    original = subprocess.Popen
    processes = []
    def spawn(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(subprocess, 'Popen', spawn)
    yield processes
    for process in processes:
        if process.poll() is None:
            process.kill()
        try:
            process.communicate(timeout=3)
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()


def run(tmp_path, code, **options):
    return run_supervised_process([sys.executable, '-c', code], cwd=tmp_path,
        env=dict(os.environ), timeout_seconds=options.pop('timeout_seconds', 5),
        poll_interval_seconds=0.03, terminate_grace_seconds=0.5, **options)


def test_windows_success_preserves_output_and_nonzero_code(tmp_path, owned_processes):
    result = run(tmp_path, "import sys; print('original output'); print('original error',file=sys.stderr); sys.exit(7)")
    assert result.returncode == 7
    assert result.stdout.strip() == 'original output'
    assert result.stderr.strip() == 'original error'
    assert not result.cancelled and not result.timed_out


def test_windows_python_output_preserves_chinese_and_emoji(tmp_path, owned_processes):
    result = run(tmp_path, "print('原文 😀')")
    assert result.returncode == 0
    assert result.stdout.strip() == '原文 😀'


@pytest.mark.parametrize('cancel', [True, False])
def test_windows_cancel_and_timeout_are_confirmed(tmp_path, owned_processes, cancel):
    started = time.monotonic()
    result = run(tmp_path, 'import time; time.sleep(10)', timeout_seconds=0.3 if not cancel else 5,
        cancel_requested=(lambda: time.monotonic() - started > 0.3) if cancel else None)
    assert result.cancelled is cancel
    assert result.timed_out is not cancel
    assert time.monotonic() - started < 4
    assert all(process.poll() is not None for process in owned_processes)


def test_windows_callback_exception_cleans_up_and_preserves_error(tmp_path, owned_processes):
    def poll():
        raise ValueError('callback aborted')
    with pytest.raises(ValueError, match='callback aborted'):
        run(tmp_path, 'import time; time.sleep(10)', poll_callback=poll)
    assert all(process.poll() is not None for process in owned_processes)


def test_windows_unconfirmed_cleanup_is_not_retried_or_reported_success(tmp_path, owned_processes, monkeypatch):
    from app.windows_process_job import WindowsProcessJob
    calls = []
    def unconfirmed(job, timeout_seconds):
        calls.append(job)
        raise OSError('test cleanup unconfirmed')
    monkeypatch.setattr(WindowsProcessJob, 'terminate_and_wait', unconfirmed)
    with pytest.raises(OSError, match='test cleanup unconfirmed'):
        run(tmp_path, 'import time; time.sleep(5)', cancel_requested=lambda: True)
    assert len(calls) == 1
    # The independent final close still invokes OS kill-on-close, not another retry.
    for process in owned_processes:
        assert process.returncode is not None, 'owned launcher was not reaped'
        assert process.stdout.closed and process.stderr.closed


def test_windows_callback_with_cleanup_error_reaps_launcher_and_releases_pipes(tmp_path, owned_processes, monkeypatch):
    from app.windows_process_job import WindowsProcessJob
    def unconfirmed(job, timeout_seconds):
        raise OSError('test query failed')
    def aborted():
        raise ValueError('test callback aborted')
    monkeypatch.setattr(WindowsProcessJob, 'terminate_and_wait', unconfirmed)
    with pytest.raises(OSError, match='test query failed'):
        run(tmp_path, 'import time; time.sleep(5)', poll_callback=aborted)
    for process in owned_processes:
        assert process.returncode is not None, 'owned launcher was not reaped'
        assert process.stdout.closed and process.stderr.closed


def test_windows_parent_exit_cleans_descendant_with_inherited_output(tmp_path, owned_processes):
    # Descendant holds both pipes open after the real command exits with 5.
    # A bounded fallback lifetime prevents a failed RED run leaving an orphan.
    code = "import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(2)']); sys.exit(5)"
    started = time.monotonic()
    result = run(tmp_path, code, timeout_seconds=0.8)
    assert result.returncode == 5
    assert not result.timed_out and not result.cancelled
    assert time.monotonic() - started < 1.8


@pytest.mark.parametrize('cancel', [True, False])
def test_windows_supervisor_stops_real_descendant(tmp_path, owned_processes, cancel):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    marker = tmp_path / 'owned-child-pid'
    child = 'import time; time.sleep(5)'
    code = ("import subprocess,sys,time; from pathlib import Path; "
        f"p=subprocess.Popen([sys.executable,'-c',{child!r}]); "
        f"Path({str(marker)!r}).write_text(str(p.pid)); time.sleep(5)")
    handle = None
    def observe():
        nonlocal handle
        if handle is None and marker.exists():
            content = marker.read_text()
            if content:
                handle = kernel.OpenProcess(0x100000 | 1, False, int(content))
                assert handle, 'could not capture owned descendant handle'
    try:
        result = run(tmp_path, code, timeout_seconds=1.0, poll_callback=observe,
            cancel_requested=(lambda: handle is not None) if cancel else None)
        assert handle, 'test never observed a real descendant'
        assert result.cancelled is cancel and result.timed_out is not cancel
        assert kernel.WaitForSingleObject(handle, 1000) == 0, 'descendant still running'
    finally:
        if handle:
            if kernel.WaitForSingleObject(handle, 0) != 0:
                kernel.TerminateProcess(handle, 1)
                assert kernel.WaitForSingleObject(handle, 2000) == 0
            kernel.CloseHandle(handle)
