"""Private fixed XHS login host. OPENED is not an authenticated connection."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
import threading
import time

from app.collector import _minimal_child_environment, run_supervised_process
from app.windows_private_directory import create_private_directory, verify_private_tree
from app.windows_source_driver import _exclusive_paths, verify_installed_runtime


SCHEMA = 'windows-platform-login-v1'
_OPENED = dict(schema_version=SCHEMA, state='OPENED')
_FIELDS = {'schema_version', 'runtime_path', 'profile_path', 'output_path', 'platform', 'timeout_seconds'}
_FAILURES = {'CANCELLED', 'TIMED_OUT', 'FAILED', 'BLOCKED_INPUT'}
_CODES = {'PLATFORM_AUTH_REQUIRED', 'PLATFORM_PERMISSION_DENIED', 'PLATFORM_VERIFICATION_REQUIRED',
    'PLATFORM_RATE_LIMITED', 'PLATFORM_RESPONSE_CHANGED', 'PLATFORM_ACCOUNT_UNVERIFIED',
    'COLLECTION_NETWORK_FAILED', 'COLLECTION_PARSE_FAILED', 'COLLECTION_PROCESS_FAILED',
    'PLATFORM_LOGIN_CANCELLED', 'SOURCE_HOST_FAILED'}


def _failure(code='PLATFORM_LOGIN_FAILED', state='FAILED'):
    return dict(schema_version=SCHEMA, state=state, error_code=code)


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result: raise ValueError()
        result[key] = value
    return result


def _constant(_): raise ValueError()


def _decode(raw):
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_constant)


def _paths(runtime_path, profile_path, output_path):
    paths = []
    for value in (runtime_path, profile_path, output_path):
        if not isinstance(value, (str, Path)): raise ValueError()
        text = str(value)
        if not text.isprintable() or not re.match(r'^[A-Za-z]:[\\/]', text): raise ValueError()
        text.encode('utf-8')
        path = Path(value)
        if not path.is_absolute() or len(path.drive) != 2: raise ValueError()
        paths.append(path)
    resolved = [path.resolve() for path in paths]
    if any(a.is_relative_to(b) or b.is_relative_to(a) for i, a in enumerate(resolved) for b in resolved[i + 1:]):
        raise ValueError()
    return paths


def _request(stdin):
    frame = stdin.readline(65537)
    if isinstance(frame, str): frame = frame.encode('utf-8')
    if len(frame) > 65536 or not frame.endswith(b'\n'): raise ValueError()
    value = _decode(frame)
    if not isinstance(value, dict) or set(value) != _FIELDS or value['schema_version'] != SCHEMA:
        raise ValueError()
    if any(not isinstance(value[key], str) for key in ('runtime_path', 'profile_path', 'output_path')): raise ValueError()
    if value['platform'] != 'XIAOHONGSHU' or type(value['timeout_seconds']) is not int or not 1 <= value['timeout_seconds'] <= 180:
        raise ValueError()
    paths = _paths(*(value[key] for key in ('runtime_path', 'profile_path', 'output_path')))
    for key, path in zip(('runtime_path', 'profile_path', 'output_path'), paths): value[key] = path
    value.pop('schema_version')
    return value


def _marker(path):
    info = path.stat(follow_symlinks=False)
    if path.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400 or info.st_nlink != 1:
        raise ValueError()
    with path.open('rb') as stream: raw = stream.read(4097)
    if len(raw) > 4096: raise ValueError()
    return _decode(raw)


def _terminal(value):
    if not isinstance(value, dict) or value.get('schema_version') != SCHEMA: raise ValueError()
    if value.get('state') == 'AUTHENTICATED':
        if set(value) != {'schema_version', 'state', 'account_public_id', 'checked_at'}: raise ValueError()
        if not isinstance(value['account_public_id'], str) or not re.fullmatch(r'[A-Za-z0-9]{8,32}', value['account_public_id']): raise ValueError()
        when = value['checked_at']
        if not isinstance(when, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', when): raise ValueError()
        datetime.strptime(when, '%Y-%m-%dT%H:%M:%SZ')
    elif value.get('state') in _FAILURES:
        if set(value) not in ({'schema_version', 'state'}, {'schema_version', 'state', 'error_code'}): raise ValueError()
        if 'error_code' in value and value['error_code'] not in _CODES: raise ValueError()
    else: raise ValueError()
    return value


def login_windows_platform(*, runtime_path, profile_path, output_path, platform,
                           timeout_seconds, on_opened, cancel_requested=None):
    started = time.monotonic()
    def interrupted():
        if cancel_requested and cancel_requested(): return _failure('PLATFORM_LOGIN_CANCELLED', 'CANCELLED')
        if time.monotonic() - started >= timeout_seconds: return dict(schema_version=SCHEMA, state='TIMED_OUT')
        return None
    try:
        if sys.platform != 'win32' or platform != 'XIAOHONGSHU' or type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 180:
            raise ValueError()
        runtime_path, profile_path, output_path = _paths(runtime_path, profile_path, output_path)
        if os.path.lexists(output_path): raise ValueError()
        with _exclusive_paths([runtime_path, profile_path]):
            if stopped := interrupted(): return stopped
            python = verify_installed_runtime(runtime_path)
            if os.path.lexists(profile_path): verify_private_tree(profile_path)
            else: profile_path = create_private_directory(profile_path)
            if stopped := interrupted(): return stopped
            output_path = create_private_directory(output_path)
            temporary = output_path / '.temporary'
            temporary.mkdir()
            (temporary / 'matplotlib').mkdir()
            env = _minimal_child_environment(YIKE_PROFILE_PATH=str(profile_path),
                YIKE_LOGIN_OUTPUT_PATH=str(output_path),
                PYTHONDONTWRITEBYTECODE='1',
                PLAYWRIGHT_BROWSERS_PATH=str(runtime_path / '.venv/playwright-browsers'),
                TEMP=str(temporary), TMP=str(temporary), MPLCONFIGDIR=str(temporary / 'matplotlib'))
            env['PATH'] = str(runtime_path / '.venv/Lib/site-packages/playwright/driver') + os.pathsep + env.get('PATH', '')
            opened = False
            def poll():
                nonlocal opened
                if opened: return
                marker = output_path / '.yike-login-opened.json'
                if not os.path.lexists(marker): return
                if _marker(marker) != _OPENED: raise ValueError()
                on_opened()
                opened = True
            command = [str(python), '-B', '-X', 'utf8', str(Path(__file__).with_name('platform_login_worker.py').resolve())]
            if stopped := interrupted(): return stopped
            result = run_supervised_process(command, cwd=runtime_path, env=env,
                timeout_seconds=timeout_seconds - (time.monotonic() - started),
                cancel_requested=cancel_requested, poll_callback=poll)
            # Only here has the entire Windows Job been physically stopped.
            verify_private_tree(profile_path)
            verify_private_tree(output_path)
            poll()
            if stopped := interrupted(): return stopped
            if result.cancelled: return _failure('PLATFORM_LOGIN_CANCELLED', 'CANCELLED')
            if result.timed_out: return dict(schema_version=SCHEMA, state='TIMED_OUT')
            if result.returncode != 0: return _failure('SOURCE_HOST_FAILED')
            terminal = _terminal(_marker(output_path / '.yike-login-terminal.json'))
            if terminal['state'] == 'AUTHENTICATED' and not opened: raise ValueError()
            return terminal
    except KeyboardInterrupt:
        # Supervisor re-raises only after cleanup; unconfirmed cleanup is OSError.
        return _failure('PLATFORM_LOGIN_CANCELLED', 'CANCELLED')
    except Exception:
        return _failure('SOURCE_HOST_FAILED')


def _watch(stdin, cancelled):
    try: stdin.read(1)
    except Exception: pass
    finally: cancelled.set()


def main(stdin=None, stdout=None):
    if stdin is None: stdin = sys.stdin.buffer.raw
    if stdout is None: stdout = sys.stdout.buffer
    cancelled = threading.Event()
    emitted_opened = False
    written = 0
    def emit(payload):
        nonlocal written
        wire = (json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n').encode('utf-8')
        if written + len(wire) > 16384: raise ValueError()
        stdout.write(wire); stdout.flush()
        written += len(wire)
    def opened():
        nonlocal emitted_opened
        if not emitted_opened:
            emit(_OPENED)
            emitted_opened = True
    with open(os.devnull, 'w', encoding='utf-8') as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
        try:
            payload = _request(stdin)
        except Exception:
            terminal = _failure('PLATFORM_LOGIN_INPUT_INVALID')
        except KeyboardInterrupt:
            terminal = _failure('PLATFORM_LOGIN_CANCELLED', 'CANCELLED')
        else:
            threading.Thread(target=_watch, args=(stdin, cancelled), daemon=True).start()
            try:
                terminal = _terminal(login_windows_platform(**payload, on_opened=opened, cancel_requested=cancelled.is_set))
            except (Exception, KeyboardInterrupt):
                terminal = _failure('SOURCE_HOST_FAILED')
        try: emit(terminal)
        except (OSError, ValueError): pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
