"""Explicit opt-in, real Windows portable artifact verification; no platform access.

The destination is a NEW retained artifact, not pytest's disposable directory.
No settings are inferred from a developer's installation or PATH.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

import pytest


_INPUTS = {
    'installed_runtime': 'YIKE_PORTABLE_SOURCE_RUNTIME',
    'python_home': 'YIKE_PORTABLE_PYTHON_HOME',
    'host_site_packages': 'YIKE_PORTABLE_HOST_SITE_PACKAGES',
    'destination': 'YIKE_PORTABLE_DESTINATION',
    'git_executable': 'YIKE_PORTABLE_GIT',
}


def test_real_portable_bundle_has_no_developer_python_dependency(tmp_path):
    if os.name != 'nt' or not all(os.environ.get(name) for name in _INPUTS.values()):
        pytest.skip('requires Windows and explicit new portable artifact inputs')
    assert importlib.util.find_spec('app.windows_portable_bundle') is not None, 'portable builder missing'
    from app.windows_portable_bundle import build_portable_bundle

    inputs = {key: Path(os.environ[name]) for key, name in _INPUTS.items()}
    destination = inputs['destination']
    assert not destination.exists(), 'this integration test never overwrites an artifact'
    relocated = destination.with_name(destination.name + '-relocated')
    assert not relocated.exists(), 'this integration test never overwrites a relocated artifact'
    result = build_portable_bundle(project_root=Path(__file__).resolve().parents[1], **inputs)
    # Move the generated tree, not just its interpreter's cwd. All paths must remain
    # usable after the original build destination itself has disappeared.
    assert destination.resolve().parent == relocated.resolve().parent
    assert destination.name.startswith('portable-') and relocated != destination
    destination.rename(relocated)
    assert not destination.exists()
    destination = relocated
    manifest = json.loads((destination / 'bundle-manifest.json').read_text(encoding='utf-8'))
    assert result == manifest
    _verify_relocated_bundle(destination, tmp_path)


def test_explicit_retained_portable_bundle(tmp_path):
    """Recheck unchanged bytes after a probe-only fix without rebuilding 1 GB."""
    keys = ('YIKE_PORTABLE_EXISTING', 'YIKE_PORTABLE_EXISTING_MANIFEST_SHA256')
    if os.name != 'nt' or not all(os.environ.get(key) for key in keys):
        pytest.skip('requires explicit retained artifact and previously observed manifest digest')
    destination = Path(os.environ[keys[0]])
    assert destination.is_absolute() and destination.name.endswith('-relocated')
    assert not destination.with_name(destination.name.removesuffix('-relocated')).exists()
    with (destination / 'bundle-manifest.json').open('rb') as handle:
        assert hashlib.file_digest(handle, 'sha256').hexdigest() == os.environ[keys[1]]
    _verify_relocated_bundle(destination, tmp_path)


def _verify_relocated_bundle(destination, tmp_path):
    from app.windows_private_directory import verify_private_tree
    verify_private_tree(destination)
    manifest = json.loads((destination / 'bundle-manifest.json').read_text(encoding='utf-8'))
    assert manifest['schema_version'] == 'YIKE_WINDOWS_PORTABLE_BUNDLE_V1'

    # Inspect the generated inventory independently, not via the builder's verifier.
    listed = set()
    for item in manifest['files']:
        relative = item['path']
        assert relative not in listed
        listed.add(relative)
        file = destination.joinpath(*relative.split('/'))
        assert file.resolve().is_relative_to(destination.resolve())
        assert not file.is_symlink() and file.stat().st_nlink == 1
        assert file.stat().st_size == item['size']
        with file.open('rb') as handle:
            assert hashlib.file_digest(handle, 'sha256').hexdigest() == item['sha256']
    assert listed == {
        p.relative_to(destination).as_posix()
        for p in destination.rglob('*') if p.is_file() and p.name != 'bundle-manifest.json'
    }

    # Deliberately use an unrelated cwd and invalid Python environment variables.
    # _pth must win without relying on another installed interpreter or site hook.
    # Windows os.environ iteration uppercases keys; index the required OS names
    # case-insensitively so the hostile Python environment still has Winsock.
    env = {key: os.environ[key] for key in ('SystemRoot', 'WINDIR', 'USERNAME') if key in os.environ}
    env.update(PATHEXT='.EXE',
               PATH=os.pathsep.join((str(Path(os.environ['SystemRoot']) / 'System32'),
                                   str(destination / 'runtime/.venv/Lib/site-packages/playwright/driver'))),
               TEMP=str(tmp_path), TMP=str(tmp_path), MPLCONFIGDIR=str(tmp_path),
               PLAYWRIGHT_BROWSERS_PATH=str(destination / 'runtime/.venv/playwright-browsers'),
               PYTHONHOME=str(tmp_path / 'nonexistent-home'),
               PYTHONPATH=str(tmp_path / 'untrusted-site'),
               PYTHONUSERBASE=str(tmp_path / 'untrusted-user-site'))
    script = (
        'import json,sys,pathlib,importlib; '
        'names=sys.argv[1:]; '
        'mods={name:str(pathlib.Path(importlib.import_module(name).__file__).resolve()) for name in names}; '
        'print(json.dumps({"executable":sys.executable,"paths":sys.path,"modules":mods,'
        '"isolated":sys.flags.isolated,"no_site":sys.flags.no_site}))'
    )
    for executable, modules in (
        (destination / 'host/python.exe', [
            'app.windows_collection_host', 'app.windows_platform_login', 'app.windows_source_probe',
            'app.windows_platform_outreach', 'app.platform_outreach_worker',
            'app.platform_outreach_runtime', 'app.xhs_comment_channel',
            'app.windows_process_job', 'pydantic', 'pydantic_core', 'idna',
        ]),
        (destination / 'runtime/.venv/Scripts/python.exe', ['playwright', 'pydantic', 'idna']),
    ):
        completed = subprocess.run([str(executable), '-B', '-X', 'utf8', '-c', script, *modules],
                                   cwd=tmp_path, env=env, capture_output=True, timeout=30)
        assert completed.returncode == 0, 'relocated Python import probe failed'
        observed = json.loads(completed.stdout)
        assert observed['isolated'] == 1 and observed['no_site'] == 1
        assert Path(observed['executable']).resolve() == executable.resolve()
        for name in [*observed['paths'], *observed['modules'].values()]:
            assert Path(name).resolve().is_relative_to(destination.resolve())

    from app.collector import run_supervised_process
    from app.windows_runtime_install import _BROWSER_PROBE
    executable = str(destination / manifest['entries']['runtime_python'])
    for arguments, cwd, expected in (
        ([str(destination / 'runtime/main.py'), '--help'], destination / 'runtime', ('xhs', 'dy', 'bili')),
        (['-c', _BROWSER_PROBE], tmp_path,
         ('YIKE_BUNDLED_CHROMIUM_LOCAL_OK ' + manifest['probes']['chromium']['browser_version'],)),
    ):
        completed = run_supervised_process([executable, '-B', '-X', 'utf8', *arguments],
                                          cwd=cwd, env=env, timeout_seconds=60)
        assert not completed.cancelled and not completed.timed_out and completed.returncode == 0
        assert all(value in completed.stdout for value in expected)

    # Probes and the independent imports must not silently mutate frozen payload bytes.
    assert not list(destination.rglob('__pycache__'))
    for item in manifest['files']:
        with (destination / item['path']).open('rb') as handle:
            assert hashlib.file_digest(handle, 'sha256').hexdigest() == item['sha256']
