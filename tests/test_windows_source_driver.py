"""Windows driver tests: real private paths/Job; fixture source, not platform proof."""
import importlib
import importlib.util
import json
import hashlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows source driver')


def module():
    assert importlib.util.find_spec('app.windows_source_driver') is not None, 'Windows source driver missing'
    return importlib.import_module('app.windows_source_driver')


@pytest.fixture
def source(tmp_path, monkeypatch):
    api = module()
    from app.windows_private_directory import create_private_directory
    runtime = create_private_directory(tmp_path / 'runtime')
    profile = create_private_directory(tmp_path / 'profile')
    calls = []
    monkeypatch.setattr(api, 'verify_installed_runtime', lambda path: Path(sys.executable))
    def runner(command, **kwargs):
        calls.append((command, kwargs))
        output = Path(next(arg.split('=', 1)[1] for arg in command if arg.startswith('--save_data_path=')))
        (output / '.yike-collection-status.json').write_text(json.dumps({
            'schema_version': 'YIKE_MEDIACRAWLER_STATUS_V1', 'platform': 'bili',
            'status': 'SUCCEEDED_NO_DATA', 'error_code': None}), encoding='utf-8')
        (output / '.yike-collection-progress.json').write_text(json.dumps({
            'schema_version': 'YIKE_MEDIACRAWLER_PROGRESS_V1', 'platform': 'bili',
            'state': 'RUNNING', 'sequence': 1}), encoding='utf-8')
        return SimpleNamespace(returncode=0, cancelled=False, timed_out=False, stdout='private data', stderr='private data')
    monkeypatch.setattr(api, 'run_supervised_process', runner)
    args = dict(runtime_path=runtime, profile_path=profile, output_path=tmp_path / 'output',
                platform='BILIBILI', query='中文 é😀', max_records=20, timeout_seconds=60)
    return SimpleNamespace(api=api, args=args, calls=calls, runner=runner)


def test_fixed_command_environment_and_no_data(source, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'must-not-inherit')
    monkeypatch.setenv('YIKE_SESSION_TOKEN', 'must-not-inherit')
    result = source.api.collect_windows_source(**source.args)
    assert result['state'] == 'COLLECTED' and result['records'] == []
    assert result['task_completed'] is False
    command, options = source.calls[0]
    # Portable _pth ignores PYTHONDONTWRITEBYTECODE; use an explicit child flag.
    assert command[:5] == [sys.executable, '-B', '-X', 'utf8', str(source.args['runtime_path'] / 'main.py')]
    assert '--keywords=中文 é😀' in command
    assert command[command.index('--crawler_max_notes_count') + 1] == '5'
    assert command[command.index('--max_comments_count_singlenotes') + 1] == '4'
    assert options['env']['YIKE_PROFILE_PATH'] == str(source.args['profile_path'])
    assert not any('DATABASE' in key or 'TOKEN' in key for key in options['env'])
    assert 0 < options['timeout_seconds'] <= 60
    assert 'private data' not in str(result)


def test_expected_xhs_account_selects_fixed_project_wrapper_and_public_env(source, monkeypatch):
    def run(command, **kwargs):
        result = source.runner(command, **kwargs)
        for name in ('.yike-collection-status.json', '.yike-collection-progress.json'):
            path = source.args['output_path'] / name
            payload = json.loads(path.read_text()); payload['platform'] = 'xhs'
            path.write_text(json.dumps(payload))
        return result
    monkeypatch.setattr(source.api, 'run_supervised_process', run)
    expected = '66c01234abcdef0123456789'
    result = source.api.collect_windows_source(**(source.args | {'platform': 'XIAOHONGSHU'}), expected_account_public_id=expected)
    assert result['state'] == 'COLLECTED'
    command, kwargs = source.calls[0]
    assert command[:4] == [sys.executable, '-B', '-X', 'utf8']
    assert command[4] == str(Path(source.api.__file__).with_name('platform_collection_worker.py').resolve())
    assert kwargs['env']['YIKE_EXPECTED_ACCOUNT_PUBLIC_ID'] == expected
    assert kwargs['env']['PYTHONDONTWRITEBYTECODE'] == '1'
    assert kwargs['cwd'] == source.args['runtime_path']
    assert '--keywords=中文 é😀' in command and command[command.index('--platform') + 1] == 'xhs'


@pytest.mark.parametrize('value', ['bad', 'private?cookie=x', True])
def test_invalid_expected_account_driver_rejects_before_launch(source, value):
    with pytest.raises(source.api.WindowsSourceError):
        source.api.collect_windows_source(**(source.args | {'platform': 'XIAOHONGSHU'}), expected_account_public_id=value)
    assert not source.calls


@pytest.mark.parametrize('change', [dict(platform='ZHIHU'), dict(query='a,b'), dict(query=''),
    dict(max_records=101), dict(max_records=True), dict(timeout_seconds=0), dict(timeout_seconds=True)])
def test_invalid_or_unsupported_never_launches(source, change):
    with pytest.raises(source.api.WindowsSourceError):
        source.api.collect_windows_source(**(source.args | change))
    assert source.calls == [] and not source.args['output_path'].exists()


def test_cancel_before_launch_preserves_no_output(source):
    result = source.api.collect_windows_source(**source.args, cancel_requested=lambda: True)
    assert result['state'] == 'CANCELLED'
    assert not source.calls and not source.args['output_path'].exists()


@pytest.mark.parametrize('kind', ['cancelled', 'timed_out', 'unknown', 'no-marker', 'bad-progress'])
def test_failure_does_not_consume_output(source, monkeypatch, kind):
    def run(*args, **kwargs):
        result = source.runner(*args, **kwargs)
        if kind in ('cancelled', 'timed_out'): setattr(result, kind, True)
        elif kind == 'unknown': result.returncode = 99
        elif kind == 'no-marker': (source.args['output_path'] / '.yike-collection-status.json').unlink()
        else: (source.args['output_path'] / '.yike-collection-progress.json').write_text('{}')
        return result
    monkeypatch.setattr(source.api, 'run_supervised_process', run)
    if kind in ('cancelled', 'timed_out'):
        result = source.api.collect_windows_source(**source.args)
        assert result['state'] == ('CANCELLED' if kind == 'cancelled' else 'TIMED_OUT')
        assert 'records' not in result
    else:
        with pytest.raises(source.api.WindowsSourceError): source.api.collect_windows_source(**source.args)
    assert source.args['output_path'].is_dir()


def test_existing_output_and_overlapping_directories_rejected(source):
    source.args['output_path'].mkdir()
    with pytest.raises(source.api.WindowsSourceError): source.api.collect_windows_source(**source.args)
    with pytest.raises(source.api.WindowsSourceError):
        source.api.collect_windows_source(**(source.args | {'output_path': source.args['profile_path'] / 'child'}))
    assert not source.calls


def test_profile_mutual_exclusion_covers_cleanup(source):
    with source.api._exclusive_paths([source.args['profile_path']]):
        # Windows mutexes are reentrant on their owning thread: use another thread.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            future = pool.submit(source.api.collect_windows_source, **source.args)
            with pytest.raises(source.api.WindowsSourceError, match='source_busy'): future.result()
    assert not source.calls


@pytest.fixture
def governed(tmp_path, monkeypatch):
    api = module()
    from app.windows_private_directory import create_private_directory
    from app.windows_runtime_install import PIN, WINDOWS_PYTHON
    root = create_private_directory(tmp_path / 'installed')
    payloads = {'main.py': b'fixed source', 'uv.lock': b'fixed deps', 'pyproject.toml': b'fixed manifest'}
    for name, raw in payloads.items(): (root / name).write_bytes(raw)
    lock = {'patched_files': {'main.py': hashlib.sha256(payloads['main.py']).hexdigest()},
            'patchset_sha256': 'a' * 64, 'patched_tree_sha256': 'b' * 64,
            'runtime_environment': {'uv_version': '0.11.6', 'lock_path': 'uv.lock',
                'lock_sha256': hashlib.sha256(payloads['uv.lock']).hexdigest(), 'manifest_path': 'pyproject.toml',
                'manifest_sha256': hashlib.sha256(payloads['pyproject.toml']).hexdigest()}}
    monkeypatch.setattr(api, 'load_governance', lambda _: {'lock': lock, 'lock_sha256': 'c' * 64})
    for name in [WINDOWS_PYTHON, '.venv/Lib/site-packages/playwright/driver/node.exe']:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
    (root / '.venv/playwright-browsers').mkdir()
    receipt = dict(schema_version='YIKE_WINDOWS_RUNTIME_INSTALL_V1', commit=PIN,
        lock_sha256='c' * 64, patchset_sha256='a' * 64, patched_tree_sha256='b' * 64,
        uv_version='0.11.6', python_path=WINDOWS_PYTHON, browser_path='.venv/playwright-browsers',
        dependency_link_mode='copy', local_probe='PASSED', platform_readiness='UNVERIFIED', browser_version='149.0.1.2')
    marker = root / '.yike-windows-install.json'
    marker.write_text(json.dumps(receipt), encoding='utf-8')
    return api, root, marker, receipt


def test_preflight_requires_measured_bytes_not_only_receipt(governed):
    api, root, marker, receipt = governed
    assert api.verify_installed_runtime(root) == root / '.venv/Scripts/python.exe'
    (root / 'main.py').write_text('changed', encoding='utf-8')
    with pytest.raises(api.WindowsSourceError, match='source_runtime_invalid'): api.verify_installed_runtime(root)


@pytest.mark.parametrize('change', [dict(commit='bad'), dict(platform_readiness='READY'), dict(python_path='other.exe'),
    dict(local_probe='FAILED'), dict(dependency_link_mode='hardlink')])
def test_bad_install_receipt_cannot_launch(governed, change):
    api, root, marker, receipt = governed
    marker.write_text(json.dumps(receipt | change), encoding='utf-8')
    with pytest.raises(api.WindowsSourceError, match='source_runtime_invalid'): api.verify_installed_runtime(root)


def test_real_windows_process_keeps_raw_text_and_sanitizes_environment(source, monkeypatch):
    # Fixture subprocess under the real Windows Job. No platform network or browser.
    from app.collector import run_supervised_process
    script = '''import json, os, sys
from pathlib import Path
output = Path(next(arg.split('=', 1)[1] for arg in sys.argv if arg.startswith('--save_data_path=')))
assert not any('DATABASE' in key or 'TOKEN' in key for key in os.environ)
data = output / 'bili' / 'jsonl'
data.mkdir(parents=True)
def write(path, value): path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
write(data / 'search_contents_1.jsonl', {'video_id': '123', 'title': 'source'})
write(data / 'search_comments_1.jsonl', {'video_id': '123', 'comment_id': '456', 'content': '  é😀原文\\n\\t  ', 'last_modify_ts': 1789000000123})
write(output / '.yike-collection-status.json', {'schema_version': 'YIKE_MEDIACRAWLER_STATUS_V1', 'platform': 'bili', 'status': 'SUCCEEDED', 'error_code': None})
write(output / '.yike-collection-progress.json', {'schema_version': 'YIKE_MEDIACRAWLER_PROGRESS_V1', 'platform': 'bili', 'state': 'RUNNING', 'sequence': 1})
print('private stdout not forwarded')
'''
    (source.args['runtime_path'] / 'main.py').write_text(script, encoding='utf-8')
    monkeypatch.setattr(source.api, 'run_supervised_process', run_supervised_process)
    monkeypatch.setenv('DATABASE_URL', 'private')
    result = source.api.collect_windows_source(**source.args)
    assert result['state'] == 'COLLECTED' and result['task_completed'] is False
    assert result['records'][0]['comment']['content'] == '  é😀原文\n\t  '
    assert result['records'][0]['comment']['last_modify_ts'] == 1789000000123
    assert result['records'][0]['comment']['collected_at'] == '2026-09-10T00:26:40Z'
    assert 'private stdout' not in str(result)
    from datetime import datetime, timezone
    from connectors.candidate_mapping import build_comment_batch
    from tests.test_candidate_mapping import execution
    mapped = build_comment_batch(platform='BILIBILI', raw_records=result['records'], request_id='request-1',
        profile_version_id='profile-1', strategy_version_id='strategy-1', execution=execution(),
        collector_version=result['collector_version'], query=result['query'], now=datetime(2026, 9, 10, 1, tzinfo=timezone.utc))
    assert mapped.records[0].body == '  é😀原文\n\t  '
    assert mapped.records[0].author_public_id is None


@pytest.mark.parametrize('cancel', [False, True])
def test_real_process_timeout_or_cancel_waits_for_owned_child(source, monkeypatch, cancel):
    import ctypes
    from ctypes import wintypes
    from app.collector import run_supervised_process
    script = '''import subprocess, sys, time
from pathlib import Path
output = Path(next(arg.split('=', 1)[1] for arg in sys.argv if arg.startswith('--save_data_path=')))
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
(output / 'child.pid').write_text(str(child.pid))
time.sleep(120)
'''
    (source.args['runtime_path'] / 'main.py').write_text(script, encoding='utf-8')
    monkeypatch.setattr(source.api, 'run_supervised_process', run_supervised_process)
    def requested():
        return cancel and (source.args['output_path'] / 'child.pid').exists()
    result = source.api.collect_windows_source(**(source.args | {'timeout_seconds': 2}), cancel_requested=requested)
    assert result['state'] == ('CANCELLED' if cancel else 'TIMED_OUT')
    pid = int((source.args['output_path'] / 'child.pid').read_text())
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x100000, False, pid)
    if handle:
        try: assert kernel.WaitForSingleObject(handle, 0) == 0
        finally: kernel.CloseHandle(handle)


@pytest.mark.skipif(not os.environ.get('YIKE_SOURCE_INSTALLED_CHECK'), reason='operator installed runtime path required')
def test_actual_installed_runtime_read_only_preflight():
    api = module()
    root = Path(os.environ['YIKE_SOURCE_INSTALLED_CHECK'])
    with api._exclusive_paths([root]):
        assert api.verify_installed_runtime(root) == root / '.venv/Scripts/python.exe'
