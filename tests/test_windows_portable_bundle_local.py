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
    result = build_portable_bundle(project_root=Path(__file__).resolve().parents[1], **inputs)
    manifest = json.loads((destination / 'bundle-manifest.json').read_text(encoding='utf-8'))
    assert result == manifest
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
    env = {key: value for key, value in os.environ.items() if key in ('SystemRoot', 'WINDIR')}
    env.update(PATH=str(Path(os.environ['SystemRoot']) / 'System32'),
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

    # Probes and the independent imports must not silently mutate frozen payload bytes.
    assert not list(destination.rglob('__pycache__'))
