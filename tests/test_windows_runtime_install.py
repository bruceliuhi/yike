"""Governance and orchestration tests; native ACL and actual installation tested separately."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest


def installer():
    assert importlib.util.find_spec('app.windows_runtime_install') is not None, 'Windows installer missing'
    return importlib.import_module('app.windows_runtime_install')


def test_current_governance_keeps_posix_lock_and_derives_windows_paths():
    module = installer()
    root = Path(__file__).resolve().parents[1]
    governed = module.load_governance(root)
    assert governed['lock']['runtime_environment']['python_path'] == '.venv/bin/python'
    assert governed['lock_sha256'] == hashlib.sha256((root / 'vendor/mediacrawler.lock').read_bytes()).hexdigest()
    assert module.WINDOWS_PYTHON == '.venv/Scripts/python.exe'


def test_bad_patch_bytes_refused_before_installation(tmp_path):
    module = installer()
    root = Path(__file__).resolve().parents[1]
    vendor = tmp_path / 'vendor'
    vendor.mkdir()
    lock = json.loads((root / 'vendor/mediacrawler.lock').read_text())
    (vendor / 'mediacrawler.lock').write_text(json.dumps(lock))
    for patch in lock['patches']:
        file = tmp_path / patch['path']
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b'changed patch')
    with pytest.raises(module.RuntimeInstallError, match='governance_invalid'):
        module.load_governance(tmp_path)


def test_governance_rejects_source_or_patch_escape(tmp_path):
    module = installer()
    vendor = tmp_path / 'vendor'
    vendor.mkdir()
    lock = json.loads((Path(__file__).resolve().parents[1] / 'vendor/mediacrawler.lock').read_text())
    lock['repository'] = 'https://untrusted.invalid/source.git'
    (vendor / 'mediacrawler.lock').write_text(json.dumps(lock))
    with pytest.raises(module.RuntimeInstallError, match='governance_invalid'):
        module.load_governance(tmp_path)
    lock['repository'] = module.REPOSITORY
    lock['patches'][0]['path'] = '../outside.patch'
    (vendor / 'mediacrawler.lock').write_text(json.dumps(lock))
    with pytest.raises(module.RuntimeInstallError, match='governance_invalid'):
        module.load_governance(tmp_path)


@pytest.fixture
def install_fixture(tmp_path, monkeypatch):
    module = installer()
    assert hasattr(module, 'install_runtime'), 'Executable provisioner missing'
    project = tmp_path / 'project'
    patch = project / 'vendor/patches/mediacrawler/one.patch'
    patch.parent.mkdir(parents=True)
    patch.write_bytes(b'governed test patch\n')
    payloads = {'main.py': b'fixture source\n', 'uv.lock': b'fixture frozen lock\n', 'pyproject.toml': b'fixture manifest\n'}
    source_lock = json.loads((Path(__file__).resolve().parents[1] / 'vendor/mediacrawler.lock').read_text())
    source_lock['patches'] = [{'path': 'vendor/patches/mediacrawler/one.patch', 'sha256': hashlib.sha256(patch.read_bytes()).hexdigest()}]
    source_lock['patchset_sha256'] = module._signature([(p['path'], p['sha256']) for p in source_lock['patches']])
    source_lock['patched_files'] = {'main.py': hashlib.sha256(payloads['main.py']).hexdigest()}
    source_lock['patched_tree_sha256'] = module._signature(sorted(source_lock['patched_files'].items()))
    for key, name in [('lock', 'uv.lock'), ('manifest', 'pyproject.toml')]:
        source_lock['runtime_environment'][key + '_sha256'] = hashlib.sha256(payloads[name]).hexdigest()
    (project / 'vendor/mediacrawler.lock').write_text(json.dumps(source_lock))
    git, uv = tmp_path / 'git.exe', tmp_path / 'uv.exe'
    git.touch()
    uv.touch()
    state = SimpleNamespace(calls=[], checked=[], stages=[], failure=None, bad_probe=False, cancelled=False,
                            version='0.11.6', wrong_source=False, acl_failure=False)
    destination = tmp_path / '中文 runtime with spaces'

    def create(path):
        path.mkdir()
        return path

    def verify(path):
        state.checked.append(path)
        if state.acl_failure:
            raise OSError('fixture private ACL error containing secret')

    # Native checks have their own real Windows tests; only the external installer is simulated here.
    monkeypatch.setattr(module, '_private_directories', lambda: (create, verify))
    def run(command, **kwargs):
        state.calls.append((command, kwargs))
        assert kwargs['timeout_seconds'] > 0
        output = ''
        if command == [str(uv), '--version']:
            output = 'uv ' + state.version
        if 'clone' in command:
            for name, data in payloads.items():
                (destination / name).write_bytes(data)
        if 'rev-parse' in command:
            output = '0' * 40 if state.wrong_source else module.PIN
        if '--name-only' in command:
            output = 'main.py\n'
        if 'sync' in command:
            python = destination / module.WINDOWS_PYTHON
            python.parent.mkdir(parents=True)
            python.touch()
            node = destination / '.venv/Lib/site-packages/playwright/driver/node.exe'
            node.parent.mkdir(parents=True)
            node.touch()
        if '-c' in command and command[0].endswith('python.exe'):
            output = 'wrong' if state.bad_probe else 'YIKE_BUNDLED_CHROMIUM_LOCAL_OK 149.0.0.0'
        if '--help' in command:
            output = 'usage: main.py xhs dy bili'
        failed = state.failure and state.failure in command
        return SimpleNamespace(returncode=1 if failed else 0, stdout=output, stderr='private stderr',
                               cancelled=bool(failed and state.cancelled), timed_out=bool(failed and not state.cancelled))
    monkeypatch.setattr(module, 'run_supervised_process', run)
    monkeypatch.setenv('YIKE_PILOT_AUTH_SECRET', 'not-forwarded')
    monkeypatch.setenv('UV_INDEX_URL', 'https://not-forwarded.invalid')
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', 'not-forwarded')
    monkeypatch.setenv('NODE_OPTIONS', 'not-forwarded')
    def install():
        return module.install_runtime(destination, git_executable=git, uv_executable=uv, project_root=project,
                                      stage_callback=state.stages.append)
    return module, state, destination, install


@pytest.mark.skipif(os.name != 'nt', reason='Windows provisioner')
def test_frozen_copy_install_only_publishes_receipt_after_probes(install_fixture):
    module, state, destination, install = install_fixture
    receipt = install()
    assert receipt['schema_version'] == 'YIKE_WINDOWS_RUNTIME_INSTALL_V1'
    assert receipt['platform_readiness'] == 'UNVERIFIED'
    assert receipt['commit'] == module.PIN
    assert state.checked == [destination]
    assert not (destination / '.yike-runtime.json').exists()
    assert json.loads((destination / '.yike-windows-install.json').read_text()) == receipt
    commands = [command for command, _ in state.calls]
    sync = next(c for c in commands if 'sync' in c)
    assert '--frozen' in sync and '--no-install-project' in sync and '--no-dev' in sync
    assert sync[sync.index('--link-mode') + 1] == 'copy'
    assert sync[sync.index('--python') + 1] == '3.11'
    assert commands.index(sync) > next(i for i, c in enumerate(commands) if '--name-only' in c)
    for _, options in state.calls:
        env = options['env']
        assert 'YIKE_PILOT_AUTH_SECRET' not in env and 'UV_INDEX_URL' not in env and 'NODE_OPTIONS' not in env
        assert env['GIT_CONFIG_GLOBAL'] == os.devnull and env['GIT_TERMINAL_PROMPT'] == '0'
    probe = next(options for command, options in state.calls if '-c' in command and command[0].endswith('python.exe'))
    assert probe['env']['PATH'].split(os.pathsep)[0] == str(destination / '.venv/Lib/site-packages/playwright/driver')
    assert probe['env']['PATHEXT'] == '.EXE'
    assert Path(probe['env']['TEMP']).is_relative_to(destination)
    assert state.stages[-1] == 'INSTALLED_LOCAL_PROBE_ONLY'


@pytest.mark.skipif(os.name != 'nt', reason='Windows provisioner')
@pytest.mark.parametrize('failure', ['version', 'source', 'timeout', 'cancel', 'probe', 'acl'])
def test_failure_preserves_partial_install_without_success(install_fixture, failure):
    module, state, destination, install = install_fixture
    if failure == 'version':
        state.version = '0.9.17'
    elif failure == 'source':
        state.wrong_source = True
    elif failure in ('timeout', 'cancel'):
        state.failure, state.cancelled = 'sync', failure == 'cancel'
    elif failure == 'probe':
        state.bad_probe = True
    else:
        state.acl_failure = True
    with pytest.raises(module.RuntimeInstallError) as error:
        install()
    assert 'secret' not in str(error.value) and 'private stderr' not in str(error.value)
    assert not (destination / '.yike-windows-install.json').exists()
    assert not (destination / '.yike-runtime.json').exists()
    if failure == 'version':
        assert not destination.exists()
    else:
        assert destination.exists()
    if failure == 'source':
        assert not any('sync' in command for command, _ in state.calls)


@pytest.mark.skipif(os.name != 'nt', reason='Windows provisioner')
def test_existing_destination_is_never_adopted(install_fixture):
    module, state, destination, install = install_fixture
    destination.mkdir()
    original = destination / 'user-file'
    original.write_bytes(b'keep me')
    with pytest.raises(module.RuntimeInstallError):
        install()
    assert original.read_bytes() == b'keep me'
    assert not state.calls


@pytest.mark.skipif(os.name != 'nt', reason='Windows provisioner')
def test_disk_failure_does_not_publish_receipt(install_fixture, monkeypatch):
    module, state, destination, install = install_fixture
    def disk_failure(_):
        raise OSError('disk failure private detail')
    monkeypatch.setattr(module.os, 'fsync', disk_failure)
    with pytest.raises(module.RuntimeInstallError):
        install()
    assert not (destination / '.yike-windows-install.json').exists()


@pytest.mark.parametrize('field,value', [('patched_files', []), ('patches', {}), ('runtime_environment', [])])
def test_malformed_governance_uses_bounded_error(tmp_path, field, value):
    module = installer()
    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / 'vendor', tmp_path / 'vendor')
    path = tmp_path / 'vendor/mediacrawler.lock'
    lock = json.loads(path.read_text())
    lock[field] = value
    path.write_text(json.dumps(lock))
    with pytest.raises(module.RuntimeInstallError, match='^governance_invalid$'):
        module.load_governance(tmp_path)
