"""Real Windows-only process tests; never enumerate or kill unrelated processes."""

import ctypes
from ctypes import wintypes
import importlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest


pytestmark = pytest.mark.skipif(os.name != "nt", reason="requires Windows Job Objects")


def _jobs():
    assert importlib.util.find_spec("app.windows_process_job") is not None, (
        "Windows Job Object implementation is missing"
    )
    return importlib.import_module("app.windows_process_job")


@pytest.fixture
def native():
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    api.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    api.TerminateProcess.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    return api


def _command(script, *args):
    return [sys.executable, "-I", "-S", "-c", script, *map(str, args)]


def _wait_file(path, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and path.read_text(encoding="utf-8").strip():
            return path.read_text(encoding="utf-8").strip()
        time.sleep(0.02)
    pytest.fail("owned test process did not become ready")


def _open_owned(native, path):
    pid = int(_wait_file(path))
    handle = native.OpenProcess(0x100000 | 0x0001, False, pid)
    assert handle, "could not open owned test process"
    return handle


def _cleanup(process, job):
    try:
        if job is not None:
            job.close()
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()


def _cleanup_handles(native, handles):
    for handle in handles:
        if native.WaitForSingleObject(handle, 0) == 258:
            native.TerminateProcess(handle, 1)
            native.WaitForSingleObject(handle, 5000)
        native.CloseHandle(handle)


_TREE = """
import os, pathlib, subprocess, sys, time
directory = pathlib.Path(sys.argv[1])
depth = int(sys.argv[2])
if depth:
    subprocess.Popen([sys.executable, '-I', '-S', '-c', sys.argv[3],
                      str(directory), str(depth - 1), sys.argv[3]])
(directory / ('pid-' + str(depth))).write_text(str(os.getpid()), encoding='utf-8')
time.sleep(30)
"""


def test_output_error_exit_code_and_gate_stdin_closed(tmp_path):
    jobs = _jobs()
    process = job = None
    try:
        process, job = jobs.launch_job_process(
            _command("import sys; print('hello'); print('warning', file=sys.stderr); sys.exit(7)"),
            cwd=tmp_path, env=os.environ.copy(),
        )
        assert process.stdin is None
        stdout, stderr = process.communicate(timeout=8)
        assert stdout == "hello\n"
        assert stderr == "warning\n"
        assert process.returncode == 7
        assert process.communicate(timeout=0.1) == (stdout, stderr)
        assert job.terminate_and_wait(3) is True
    finally:
        _cleanup(process, job)


def test_original_command_does_not_run_until_job_assignment(tmp_path, monkeypatch):
    jobs = _jobs()
    marker = tmp_path / "command-ran"
    real_assign = jobs.WindowsProcessJob.assign
    checked = []

    def inspect_then_assign(job, process):
        time.sleep(0.3)
        checked.append(not marker.exists() and process.poll() is None)
        real_assign(job, process)

    monkeypatch.setattr(jobs.WindowsProcessJob, "assign", inspect_then_assign)
    process = job = None
    try:
        process, job = jobs.launch_job_process(
            _command("import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('yes')", marker),
            cwd=tmp_path, env=os.environ.copy(),
        )
        process.communicate(timeout=8)
        assert checked == [True]
        assert marker.read_text() == "yes"
    finally:
        _cleanup(process, job)


def test_assignment_failure_never_runs_command_and_reaps_launcher(tmp_path, monkeypatch):
    jobs = _jobs()
    marker = tmp_path / "command-ran"
    launchers = []

    def fail_assign(job, process):
        launchers.append(process)
        raise OSError("sensitive-command-or-environment")

    monkeypatch.setattr(jobs.WindowsProcessJob, "assign", fail_assign)
    try:
        with pytest.raises(jobs.WindowsProcessJobError) as caught:
            jobs.launch_job_process(
                _command("import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('yes')", marker),
                cwd=tmp_path, env=os.environ.copy(),
            )
        assert "sensitive" not in str(caught.value)
        assert not marker.exists()
        assert len(launchers) == 1 and launchers[0].poll() is not None
        assert all(pipe is None or pipe.closed for pipe in (
            launchers[0].stdin, launchers[0].stdout, launchers[0].stderr,
        ))
    finally:
        for launcher in launchers:
            _cleanup(launcher, None)


def test_terminate_wait_stops_command_children_and_grandchildren(native, tmp_path):
    jobs = _jobs()
    process = job = None
    handles = []
    try:
        process, job = jobs.launch_job_process(
            _command(_TREE, tmp_path, 2, _TREE), cwd=tmp_path, env=os.environ.copy(),
        )
        for depth in range(3):
            handles.append(_open_owned(native, tmp_path / f"pid-{depth}"))
        assert job.terminate_and_wait(5) is True
        # Job accounting may reach zero before all process handles are signaled.
        assert all(native.WaitForSingleObject(handle, 5000) == 0 for handle in handles)
        process.communicate(timeout=5)
        assert process.poll() is not None
    finally:
        _cleanup(process, job)
        _cleanup_handles(native, handles)


def test_close_is_idempotent_and_kills_owned_processes(native, tmp_path):
    jobs = _jobs()
    process = job = None
    handles = []
    try:
        process, job = jobs.launch_job_process(
            _command(_TREE, tmp_path, 0, _TREE), cwd=tmp_path, env=os.environ.copy(),
        )
        handles.append(_open_owned(native, tmp_path / "pid-0"))
        job.close()
        job.close()
        assert native.WaitForSingleObject(handles[0], 5000) == 0
        process.communicate(timeout=5)
    finally:
        _cleanup(process, job)
        _cleanup_handles(native, handles)


def test_abrupt_job_owner_exit_kills_tree_without_python_cleanup(native, tmp_path):
    jobs = _jobs()
    owner = None
    handles = []
    owner_script = """
import os, sys, time
from app.windows_process_job import launch_job_process
process, job = launch_job_process(sys.argv[2:], cwd=sys.argv[1], env=os.environ.copy())
time.sleep(30)
"""
    try:
        # The owner needs the checkout import path, but its bootstrap remains isolated.
        owner = subprocess.Popen(
            [sys.executable, "-c", owner_script, str(tmp_path), *_command(_TREE, tmp_path, 2, _TREE)],
            cwd=Path(__file__).resolve().parents[1],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for depth in range(3):
            handles.append(_open_owned(native, tmp_path / f"pid-{depth}"))
        owner.kill()
        owner.wait(timeout=5)
        assert all(native.WaitForSingleObject(handle, 5000) == 0 for handle in handles)
    finally:
        _cleanup(owner, None)
        _cleanup_handles(native, handles)


def test_command_gets_explicit_environment_cwd_and_no_gate_input(tmp_path):
    jobs = _jobs()
    env = os.environ.copy()
    env["YIKE_JOB_TEST_VALUE"] = "原文 😀"
    caller_env = dict(env)
    before = dict(os.environ)
    process = job = None
    try:
        process, job = jobs.launch_job_process(
            [sys.executable, "-c", "import os,sys; print(os.getcwd()); print(os.environ['YIKE_JOB_TEST_VALUE']); print(repr(sys.stdin.read()))"],
            cwd=tmp_path, env=env,
        )
        stdout, stderr = process.communicate(timeout=8)
        assert stdout.splitlines() == [str(tmp_path), "原文 😀", "''"]
        assert stderr == ""
        assert dict(os.environ) == before
        assert env == caller_env
    finally:
        _cleanup(process, job)


def test_original_start_failure_is_sanitized(tmp_path):
    jobs = _jobs()
    process = job = None
    try:
        process, job = jobs.launch_job_process(
            [str(tmp_path / "sensitive-missing-program.exe")], cwd=tmp_path, env=os.environ.copy(),
        )
        stdout, stderr = process.communicate(timeout=8)
        assert process.returncode != 0
        assert stdout == ""
        assert "sensitive" not in stderr
        assert "Traceback" not in stderr
        assert stderr.strip() == "windows_process_start_failed"
    finally:
        _cleanup(process, job)


def test_delayed_assignment_still_owns_virtualenv_command_tree(native, tmp_path, monkeypatch):
    jobs = _jobs()
    real_assign = jobs.WindowsProcessJob.assign

    def delayed_assign(job, process):
        # A Windows venv redirector has time to create its real interpreter here.
        time.sleep(0.5)
        real_assign(job, process)

    monkeypatch.setattr(jobs.WindowsProcessJob, "assign", delayed_assign)
    process = job = None
    handles = []
    try:
        process, job = jobs.launch_job_process(
            _command(_TREE, tmp_path, 2, _TREE), cwd=tmp_path, env=os.environ.copy(),
        )
        for depth in range(3):
            handles.append(_open_owned(native, tmp_path / f"pid-{depth}"))
        assert job.terminate_and_wait(5) is True
        assert all(native.WaitForSingleObject(handle, 1000) == 0 for handle in handles)
    finally:
        # Close descendant pipes before closing parent streams on test failure.
        _cleanup_handles(native, handles)
        _cleanup(process, job)


@pytest.mark.parametrize("base_executable", [None, "python.exe", "C:/missing-trusted-python.exe"])
def test_unavailable_trusted_interpreter_fails_closed(tmp_path, monkeypatch, base_executable):
    jobs = _jobs()
    marker = tmp_path / "command-ran"
    monkeypatch.setattr(sys, "_base_executable", base_executable)
    process = job = None
    try:
        with pytest.raises(jobs.WindowsProcessJobError):
            process, job = jobs.launch_job_process(
                _command("import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('yes')", marker),
                cwd=tmp_path, env=os.environ.copy(),
            )
        assert not marker.exists()
    finally:
        _cleanup(process, job)
