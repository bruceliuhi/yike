"""Windows-owned process trees with a fail-closed, pre-execution assignment gate.

No process-name lookup or external utility is used. This module is safe to import
on other platforms; constructing a job there fails explicitly.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Mapping, Sequence


class WindowsProcessJobError(OSError):
    """A fixed, non-sensitive lifecycle error (never includes argv or env)."""


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
    )]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _BasicAccountingInformation(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.c_int64),
        ("TotalKernelTime", ctypes.c_int64),
        ("ThisPeriodTotalUserTime", ctypes.c_int64),
        ("ThisPeriodTotalKernelTime", ctypes.c_int64),
        ("TotalPageFaultCount", wintypes.DWORD),
        ("TotalProcesses", wintypes.DWORD),
        ("ActiveProcesses", wintypes.DWORD),
        ("TotalTerminatedProcesses", wintypes.DWORD),
    ]


_kernel32 = None
if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    ]
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _kernel32.TerminateJobObject.restype = wintypes.BOOL
    _kernel32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _kernel32.QueryInformationJobObject.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL


class WindowsProcessJob:
    """Own one non-inheritable, non-breakaway kill-on-close Job Object.

    The caller must close the job in a finally block. Its handle is never passed
    to the launcher, so even abrupt owner death triggers Windows tree cleanup.
    """

    def __init__(self) -> None:
        self._handle = None
        if _kernel32 is None:
            raise WindowsProcessJobError("windows_job_unavailable")
        # NULL SECURITY_ATTRIBUTES makes this unnamed job handle non-inheritable.
        self._handle = _kernel32.CreateJobObjectW(None, None)
        if not self._handle:
            raise WindowsProcessJobError("windows_job_create_failed")
        limits = _ExtendedLimitInformation()
        # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; neither breakaway flag is enabled.
        limits.BasicLimitInformation.LimitFlags = 0x00002000
        if not _kernel32.SetInformationJobObject(
            self._handle, 9, ctypes.byref(limits), ctypes.sizeof(limits),
        ):
            self.close()
            raise WindowsProcessJobError("windows_job_configure_failed")

    def assign(self, process: subprocess.Popen[str]) -> None:
        if self._handle is None:
            raise WindowsProcessJobError("windows_job_closed")
        # Popen owns this exact process handle; using it avoids PID reuse races.
        if not _kernel32.AssignProcessToJobObject(self._handle, int(process._handle)):
            raise WindowsProcessJobError("windows_job_assign_failed")

    def terminate_and_wait(self, timeout_seconds: float) -> bool:
        """Terminate every member and confirm zero active processes by deadline."""
        if self._handle is None:
            raise WindowsProcessJobError("windows_job_closed")
        if not math.isfinite(timeout_seconds) or timeout_seconds < 0:
            raise WindowsProcessJobError("windows_job_invalid_timeout")
        deadline = time.monotonic() + timeout_seconds
        if not _kernel32.TerminateJobObject(self._handle, 1):
            raise WindowsProcessJobError("windows_job_terminate_failed")
        while True:
            accounting = _BasicAccountingInformation()
            if not _kernel32.QueryInformationJobObject(
                self._handle, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None,
            ):
                raise WindowsProcessJobError("windows_job_query_failed")
            if accounting.ActiveProcesses == 0:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise WindowsProcessJobError("windows_job_termination_timeout")
            time.sleep(min(0.01, remaining))

    def close(self) -> None:
        if self._handle is None:
            return
        if not _kernel32.CloseHandle(self._handle):
            # Retain ownership for a retry and attempt fail-closed termination.
            # Do not report cleanup success when the handle could not be closed.
            _kernel32.TerminateJobObject(self._handle, 1)
            raise WindowsProcessJobError("windows_job_close_failed")
        self._handle = None


# Only standard-library imports run before the private stdin gate. -I -S excludes
# cwd/PYTHONPATH/site customization, so no original command code executes pre-job.
_BOOTSTRAP = """
import subprocess, sys
if sys.stdin.buffer.read(1) != b'1':
    sys.exit(125)
try:
    process = subprocess.Popen(sys.argv[1:], shell=False, stdin=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    code = process.wait()
except BaseException:
    sys.stderr.write('windows_process_start_failed\\n')
    sys.exit(125)
sys.exit(code)
"""


def launch_job_process(
    command: Sequence[str], *, cwd: str | Path, env: Mapping[str, str],
) -> tuple[subprocess.Popen[str], WindowsProcessJob]:
    """Launch only after job assignment; no uncontained fallback on any failure."""
    job = WindowsProcessJob()
    process = None
    try:
        # A Windows venv python.exe is a redirector: its real interpreter could
        # spawn before assignment. Use the running Python's trusted base binary,
        # never PATH lookup or a fallback to that redirector.
        interpreter = getattr(sys, "_base_executable", None)
        if not isinstance(interpreter, str) or not Path(interpreter).is_absolute():
            raise WindowsProcessJobError("windows_process_interpreter_unavailable")
        if not Path(interpreter).is_file():
            raise WindowsProcessJobError("windows_process_interpreter_unavailable")
        # Explicit UTF-8 pipe protocol for the managed Python runtime. Do not
        # mutate the caller's mapping or the long-lived owner's environment.
        child_env = dict(env)
        child_env["PYTHONIOENCODING"] = "utf-8"
        process = subprocess.Popen(
            [interpreter, "-I", "-S", "-c", _BOOTSTRAP, *command],
            cwd=cwd, env=child_env, shell=False, close_fds=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8",
        )
        job.assign(process)
        process.stdin.write("1")
        process.stdin.flush()
        process.stdin.close()
        # Popen.communicate must not try to flush a closed gate on later polls.
        process.stdin = None
        return process, job
    except BaseException as error:
        cleanup_failed = False
        try:
            job.close()
        except OSError:
            cleanup_failed = True
        if process is not None:
            try:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                cleanup_failed = True
            finally:
                for pipe in (process.stdin, process.stdout, process.stderr):
                    if pipe is not None:
                        try:
                            pipe.close()
                        except OSError:
                            cleanup_failed = True
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        code = "windows_process_cleanup_failed" if cleanup_failed else "windows_process_start_failed"
        raise WindowsProcessJobError(code) from None
