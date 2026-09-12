"""Main-owned Windows source execution. Does not grant platform/lease authority.

Caller supplies an isolated profile for its authenticated connection and invokes
only within a live execution scope. Raw output is preserved for formal mapping;
COLLECTED is neither uploaded nor a server task completion.
"""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
import time

from app.collector import _EXIT_RESULTS, _minimal_child_environment, run_supervised_process
from app.repository import canonical_single_keyword
from app.platform_login_worker import valid_account
from app.windows_private_directory import create_private_directory, verify_private_tree
from app.windows_runtime_install import load_governance, PIN, WINDOWS_PYTHON, _within, _digest


class WindowsSourceError(RuntimeError):
    """Fixed codes only; never forward platform logs, paths or raw exceptions."""


_active_names: set[str] = set()
_active_lock = threading.Lock()


@contextmanager
def _exclusive_paths(paths):
    # Named mutexes cover independent processes; the local set also refuses
    # same-thread recursion (Windows mutexes alone are recursive).
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    with ExitStack() as stack:
        for path in sorted({os.path.normcase(str(Path(p).resolve())) for p in paths}):
            name = 'Local\\YikeSource-' + hashlib.sha256(path.encode('utf-8')).hexdigest()
            with _active_lock:
                if name in _active_names:
                    raise WindowsSourceError('source_busy')
                _active_names.add(name)
            def clear(owned=name):
                with _active_lock:
                    _active_names.remove(owned)
            stack.callback(clear)
            handle = kernel.CreateMutexW(None, False, name)
            if not handle:
                raise WindowsSourceError('source_lock_failed')
            stack.callback(kernel.CloseHandle, handle)
            if kernel.WaitForSingleObject(handle, 0) not in (0, 0x80):
                raise WindowsSourceError('source_busy')
            stack.callback(kernel.ReleaseMutex, handle)
        yield


def _json(path: Path) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError()
            result[key] = value
        return result
    with path.open('rb') as handle:
        raw = handle.read(4097)
    if len(raw) > 4096:
        raise ValueError()
    result = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    if not isinstance(result, dict):
        raise ValueError()
    return result


def verify_installed_runtime(runtime_path: Path) -> Path:
    """Read-only preflight under caller's runtime lock; no platform/browser start."""
    try:
        verify_private_tree(runtime_path)
        governed = load_governance(Path(__file__).resolve().parents[1])
        lock = governed['lock']
        receipt = _json(runtime_path / '.yike-windows-install.json')
        expected = dict(schema_version='YIKE_WINDOWS_RUNTIME_INSTALL_V1', commit=PIN,
                        lock_sha256=governed['lock_sha256'], patchset_sha256=lock['patchset_sha256'],
                        patched_tree_sha256=lock['patched_tree_sha256'], uv_version=lock['runtime_environment']['uv_version'],
                        python_path=WINDOWS_PYTHON, browser_path='.venv/playwright-browsers',
                        dependency_link_mode='copy', local_probe='PASSED', platform_readiness='UNVERIFIED')
        if (set(receipt) != set(expected) | {'browser_version'} or
                any(receipt.get(k) != v for k, v in expected.items()) or
                not isinstance(receipt['browser_version'], str) or
                not re.fullmatch(r'\d+\.\d+\.\d+\.\d+', receipt['browser_version'])):
            raise ValueError()
        for name, digest in lock['patched_files'].items():
            if _digest(_within(runtime_path, name)) != digest:
                raise ValueError()
        for key in ('lock', 'manifest'):
            spec = lock['runtime_environment']
            if _digest(_within(runtime_path, spec[key + '_path'])) != spec[key + '_sha256']:
                raise ValueError()
        python = _within(runtime_path, WINDOWS_PYTHON)
        if not python.is_file() or not (runtime_path / '.venv/Lib/site-packages/playwright/driver/node.exe').is_file():
            raise ValueError()
        if not (runtime_path / '.venv/playwright-browsers').is_dir():
            raise ValueError()
        return python
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        raise WindowsSourceError('source_runtime_invalid') from None


def _collection_limits(platform, max_records, collection_mode='search'):
    if collection_mode != 'search':
        if platform != 'BILIBILI' or collection_mode not in ('detail', 'creator'):
            raise WindowsSourceError('source_input_invalid')
        contents = 1 if collection_mode == 'detail' else min(5, max(1, max_records // 2))
        return contents, max(0, (max_records - contents) // contents)
    max_contents = min(5, max_records)
    # Zhihu emits POST as well as COMMENT; its governed source applies one
    # shared output budget instead of the legacy per-content comment limit.
    return max_contents, max_records if platform == 'ZHIHU' else max_records // max_contents


def collect_windows_source(*, runtime_path: Path, profile_path: Path, output_path: Path,
                           platform: str, query: str | None, max_records: int, timeout_seconds: int,
                           cancel_requested=None, expected_account_public_id=None, native_link=None) -> dict:
    from app.collection_output import read_collection_output, CollectionOutputError
    from pilot.native_collection_links import validate_bili_collection_target
    if sys.platform != 'win32':
        raise WindowsSourceError('windows_required')
    started = time.monotonic()
    try:
        if (platform not in ('DOUYIN', 'BILIBILI', 'XIAOHONGSHU', 'ZHIHU') or type(max_records) is not int or not 1 <= max_records <= 100
                or type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 900):
            raise WindowsSourceError('source_input_invalid')
        mode = 'search'
        if native_link is not None:
            target = validate_bili_collection_target(native_link)
            if platform != 'BILIBILI' or query is not None or not valid_account(platform, expected_account_public_id):
                raise WindowsSourceError('source_input_invalid')
            mode = target['kind']
        elif not isinstance(query, str) or not 1 <= len(query) <= 80 or canonical_single_keyword(query) != query:
            raise WindowsSourceError('source_input_invalid')
        if (platform == 'ZHIHU' or expected_account_public_id is not None) and not valid_account(platform, expected_account_public_id):
            raise WindowsSourceError('source_input_invalid')
        paths = [Path(p) for p in (runtime_path, profile_path, output_path)]
        if any(not p.is_absolute() or p.drive.startswith('\\') for p in paths):
            raise WindowsSourceError('source_input_invalid')
        resolved = [p.resolve() for p in paths]
        if any(a.is_relative_to(b) or b.is_relative_to(a) for i, a in enumerate(resolved) for b in resolved[i + 1:]):
            raise WindowsSourceError('source_input_invalid')
        runtime_path, profile_path, output_path = paths
        if os.path.lexists(output_path):
            raise WindowsSourceError('source_output_exists')
        def interrupted():
            if cancel_requested and cancel_requested():
                return {'state': 'CANCELLED', 'task_completed': False}
            if time.monotonic() - started >= timeout_seconds:
                return {'state': 'TIMED_OUT', 'task_completed': False}
            return None
        with _exclusive_paths([runtime_path, profile_path]):
            if stopped := interrupted():
                return stopped
            python = verify_installed_runtime(runtime_path)
            verify_private_tree(profile_path)
            if stopped := interrupted():
                return stopped
            output_path = create_private_directory(output_path)
            temporary = output_path / '.temporary'
            temporary.mkdir()
            (temporary / 'matplotlib').mkdir()
            code = {'BILIBILI': 'bili', 'DOUYIN': 'dy', 'XIAOHONGSHU': 'xhs', 'ZHIHU':'zhihu'}[platform]
            environment = _minimal_child_environment(
                YIKE_PROFILE_PATH=str(profile_path),
                PLAYWRIGHT_BROWSERS_PATH=str(runtime_path / '.venv/playwright-browsers'),
                TEMP=str(temporary), TMP=str(temporary), MPLCONFIGDIR=str(temporary / 'matplotlib'))
            environment['PATH'] = str(runtime_path / '.venv/Lib/site-packages/playwright/driver') + os.pathsep + environment.get('PATH', '')
            entrypoint = runtime_path / 'main.py'
            if expected_account_public_id is not None:
                entrypoint = Path(__file__).with_name('platform_collection_worker.py').resolve()
                environment['YIKE_EXPECTED_ACCOUNT_PUBLIC_ID'] = expected_account_public_id
                environment['YIKE_COLLECTION_PLATFORM'] = platform
                environment['PYTHONDONTWRITEBYTECODE'] = '1'
            # Sample several comments per post (including replies when available)
            # rather than spending the entire budget on first-comment-only posts.
            max_contents, comments_per_content = _collection_limits(platform, max_records, mode)
            selector = '--keywords=' + query if mode == 'search' else (
                ('--specified_id=' if mode == 'detail' else '--creator_id=') + target['canonical_url'])
            command = [str(python), '-B', '-X', 'utf8', str(entrypoint), '--platform', code,
                       '--lt', 'qrcode', '--type', mode, selector,
                       '--get_comment', 'yes', '--get_sub_comment', 'yes', '--headless', 'no',
                       '--save_data_option', 'jsonl', '--save_data_path=' + str(output_path),
                       '--crawler_max_notes_count', str(max_contents), '--max_comments_count_singlenotes', str(comments_per_content),
                       '--max_concurrency_num', '1', '--enable_ip_proxy', 'no']
            if stopped := interrupted():
                return stopped
            result = run_supervised_process(command, cwd=runtime_path, env=environment,
                timeout_seconds=timeout_seconds - (time.monotonic() - started), cancel_requested=cancel_requested)
            # The supervisor has already waited for the complete owned tree.
            verify_private_tree(profile_path)
            verify_private_tree(output_path)
            if stopped := interrupted():
                return stopped
            if result.cancelled or result.timed_out:
                return {'state': 'CANCELLED' if result.cancelled else 'TIMED_OUT', 'task_completed': False}
            terminal = _json(output_path / '.yike-collection-status.json')
            if set(terminal) != {'schema_version', 'platform', 'status', 'error_code'} or terminal['schema_version'] != 'YIKE_MEDIACRAWLER_STATUS_V1' or terminal['platform'] != code:
                raise ValueError()
            pair = (terminal['status'], terminal['error_code'])
            if result.returncode != 0:
                if _EXIT_RESULTS.get(result.returncode) != pair:
                    raise ValueError()
                return {'state': pair[0], 'error_code': pair[1], 'task_completed': False}
            if pair not in (('SUCCEEDED', None), ('SUCCEEDED_NO_DATA', None)):
                raise ValueError()
            progress = _json(output_path / '.yike-collection-progress.json')
            if (set(progress) != {'schema_version', 'platform', 'state', 'sequence'} or
                    progress['schema_version'] != 'YIKE_MEDIACRAWLER_PROGRESS_V1' or progress['platform'] != code or
                    progress['state'] != 'RUNNING' or type(progress['sequence']) is not int or progress['sequence'] < 1):
                raise ValueError()
            records = (read_collection_output(output_path, platform, max_records) if mode == 'search' else
                read_collection_output(output_path, platform, max_records, collection_mode=mode))
            if bool(records) != (pair[0] == 'SUCCEEDED'):
                raise ValueError()
            if stopped := interrupted():
                return stopped
            return {'state': 'COLLECTED', 'records': records, 'output_path': str(output_path),
                    'query': query, 'collector_version': 'mediacrawler-' + PIN + ('' if mode == 'search' else '-bili-links-v1'), 'task_completed': False}
    except WindowsSourceError:
        raise
    except (OSError, ValueError, TypeError, RuntimeError, CollectionOutputError):
        raise WindowsSourceError('source_collection_failed') from None
