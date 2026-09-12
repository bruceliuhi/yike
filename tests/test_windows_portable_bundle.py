"""Portable builder invariants with tiny real disk inventories; external probes controlled."""
import base64
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import zipfile

import pytest


def implementation():
    assert importlib.util.find_spec('app.windows_portable_bundle'), 'portable builder missing'
    return importlib.import_module('app.windows_portable_bundle')


def test_portable_builder_exists():
    assert callable(implementation().build_portable_bundle)


@pytest.mark.skipif(os.name == 'nt', reason='non-Windows rejection boundary')
def test_non_windows_rejected_without_creating_output(tmp_path):
    api = implementation()
    output = tmp_path / 'not-created'
    with pytest.raises(api.PortableBundleError, match='PORTABLE_WINDOWS_REQUIRED'):
        api.build_portable_bundle(project_root=tmp_path, installed_runtime=tmp_path,
            python_home=tmp_path, host_site_packages=tmp_path, destination=output,
            git_executable=tmp_path / 'git.exe')
    assert not output.exists()


def put(root, name, data=b'fixture'):
    path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data); return path


def distribution(root, name, version='1.0', files=None):
    package = name.replace('-', '_'); info = f'{package}-{version}.dist-info'
    values = {f'{package}/__init__.py': b'', f'{info}/METADATA': f'Name: {name}\nVersion: {version}\n'.encode(),
              f'{info}/licenses/LICENSE': b'fixture license'} | (files or {})
    rows = []
    for path, data in values.items():
        put(root, path, data); digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()
        rows.append(f'{path},sha256={digest},{len(data)}')
    put(root, f'{info}/RECORD', ('\n'.join(rows) + f'\n{info}/RECORD,,\n').encode())


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    if os.name != 'nt':
        pytest.skip('requires native Windows paths and private directory ACLs')
    api = implementation(); inventory = importlib.import_module('app.windows_portable_inventory')
    project, runtime, python, host = [tmp_path / name for name in ('project', 'installed', 'python-home', 'host-site')]
    for directory in (project, runtime, python, host): directory.mkdir()
    for name in inventory.HOST_FILES: put(project, name, b'# host fixture\n')
    host_lock = '\n'.join(f'[[package]]\nname = "{name}"\nversion = "1.0"\n' for name in inventory.HOST_PACKAGES)
    put(project, 'uv.lock', host_lock.encode()); put(project, 'pyproject.toml', b'[project]\nname="fixture"\n')
    put(project, 'vendor/mediacrawler.lock', b'governed')
    put(project, 'vendor/patches/mediacrawler/one.patch', b'patch')
    for name in inventory.HOST_PACKAGES: distribution(host, name)
    for name in inventory.CORE_FILES: put(python, name)
    put(python, 'Lib/os.py'); put(python, 'Lib/encodings/__init__.py'); put(python, 'DLLs/_ssl.pyd')
    put(python, 'Lib/site-packages/secret.py', b'not copied'); put(python, 'Lib/__pycache__/os.pyc', b'not copied')
    source = {'main.py': b'# governed main\n', 'LICENSE': b'source license', 'uv.lock':
        b'[[package]]\nname="mediacrawler"\nversion="0.1"\nsource={virtual="."}\ndependencies=[{name="playwright"}]\n[[package]]\nname="playwright"\nversion="1.0"\n',
        'pyproject.toml': b'[project]\nname="mediacrawler"\n'}
    for name, value in source.items(): put(runtime, name, value)
    browser_config = {'browsers': [{'name': name, 'revision': '1'} for name in ('chromium','chromium-headless-shell','ffmpeg','winldd')]}
    distribution(runtime / '.venv/Lib/site-packages', 'playwright', files={
        'playwright/driver/node.exe': b'node', 'playwright/driver/package/browsers.json': json.dumps(browser_config).encode()})
    for name in ('chromium','chromium_headless_shell','ffmpeg','winldd'): put(runtime, f'.venv/playwright-browsers/{name}-1/LICENSE', b'browser license')
    put(runtime, '.venv/Scripts/python.exe', b'old venv launcher'); put(runtime, '.venv/pyvenv.cfg', b'home=C:/developer')
    put(runtime, '.yike-windows-install.json', b'{"browser_version":"149.0.0.0"}')
    put(runtime, 'browser_data/profile/Cookies', b'private-cookie'); put(runtime, '.env', b'private-token')
    git = put(tmp_path, 'git.exe')
    lock = {'patchset_sha256': '1'*64, 'patched_tree_sha256': '2'*64, 'patched_files': {},
            'patches': [{'path': 'vendor/patches/mediacrawler/one.patch'}]}
    state = SimpleNamespace(calls=[], fail=None, cancelled=False, source=source, lock=lock)
    monkeypatch.setattr(api, 'verify_installed_runtime', lambda path: path / '.venv/Scripts/python.exe')
    monkeypatch.setattr(api, 'load_governance', lambda _: {'lock': lock, 'lock_sha256': '3'*64})
    def run(command, **kwargs):
        state.calls.append((command, kwargs)); text = ''
        if command[0] == str(git):
            if 'ls-tree' in command:
                text = ''.join('100644 blob ' + hashlib.sha1(b'blob ' + str(len(data)).encode() + bytes([0]) + data).hexdigest() + '\t' + name + '\0' for name, data in source.items())
            elif 'rev-parse' in command: text = api.PIN if str(runtime) in command else 'a'*40
            elif 'status' in command: text = ''
        elif '--help' in command: text = 'usage main.py xhs dy bili'
        elif 'YIKE_PORTABLE_HOST_OK' in command[-1]: text = 'YIKE_PORTABLE_HOST_OK 3.11.14'
        elif 'YIKE_BUNDLED_CHROMIUM_LOCAL_OK' in command[-1]: text = 'YIKE_BUNDLED_CHROMIUM_LOCAL_OK 149.0.0.0'
        else: text = 'YIKE_PORTABLE_CORE_OK 3.11.14'
        failed = state.fail is not None and any(state.fail in value for value in command)
        return SimpleNamespace(returncode=1 if failed else 0, stdout=text, stderr='private diagnostic',
                               cancelled=bool(failed and state.cancelled), timed_out=False)
    monkeypatch.setattr(api, 'run_supervised_process', run)
    monkeypatch.setenv('DATABASE_URL', 'private-token'); monkeypatch.setenv('PYTHONHOME', 'C:/developer')
    options = dict(project_root=project, installed_runtime=runtime, python_home=python,
                   host_site_packages=host, destination=tmp_path / 'new payload', git_executable=git)
    return api, state, options


def test_runtime_documentation_does_not_break_legacy_squirrel_package_reader(fixture, tmp_path):
    api, state, options = fixture
    documentation = ('docs/项目代码结构.md', 'docs/项目架构文档.md',
                     'docs/static/images/修改代理密钥.png', 'docs/.vitepress/config.mjs')
    resources = ('docs/hit_stopwords.txt', 'docs/STZHONGS.TTF', 'NOTICE')
    for name in (*documentation, *resources):
        state.source[name] = b'governed resource'
        put(options['installed_runtime'], name, state.source[name])
    manifest = api.build_portable_bundle(**options)
    # Squirrel uses the legacy .NET Framework Package reader for uninstall
    # registration, not Python's Unicode-aware zipfile reader. Reproduce that
    # exact boundary with a tiny package containing the real output inventory.
    package = tmp_path / 'fixture.nupkg'
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml',
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="md" ContentType="text/plain"/></Types>')
        for item in manifest['files']:
            archive.write(options['destination'] / item['path'], 'lib/net45/' + item['path'])
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
        'Add-Type -AssemblyName WindowsBase; try { '
        '$p = [IO.Packaging.Package]::Open($env:YIKE_TEST_NUPKG, [IO.FileMode]::Open, [IO.FileAccess]::Read); '
        'try { @($p.GetParts()).Count } finally { $p.Close() } '
        '} catch { $_.Exception.GetBaseException().Message; exit 1 }'],
        env={**os.environ, 'YIKE_TEST_NUPKG': str(package)}, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout.decode(errors='replace')
    paths = {item['path'] for item in manifest['files']}
    assert not any('runtime/' + name in paths for name in documentation)
    for name in ('main.py', 'LICENSE', *resources):
        assert (options['destination'] / 'runtime' / name).read_bytes() == state.source[name]
    for name in documentation:
        assert (options['installed_runtime'] / name).read_bytes() == state.source[name]


@pytest.mark.parametrize('origin', ['runtime', 'patched-runtime', 'dependency'])
def test_unexpected_non_ascii_payload_path_fails_before_output_not_silently_dropped(fixture, origin):
    api, state, options = fixture
    name = '模块.py'
    if origin == 'dependency':
        distribution(options['host_site_packages'], 'idna', files={'idna/' + name: b'required'})
    else:
        put(options['installed_runtime'], name, b'required')
        if origin == 'runtime': state.source[name] = b'required'
        else: state.lock['patched_files'][name] = hashlib.sha256(b'required').hexdigest()
    with pytest.raises(api.PortableBundleError, match='PORTABLE_SQUIRREL_NON_ASCII_PATH'):
        api.build_portable_bundle(**options)
    assert not options['destination'].exists()


def test_new_layout_is_relative_isolated_complete_and_secrets_never_enter_manifest(fixture):
    api, state, options = fixture; manifest = api.build_portable_bundle(**options); output = options['destination']
    assert manifest['schema_version'] == 'YIKE_WINDOWS_PORTABLE_BUNDLE_V1'
    assert json.loads((output / 'bundle-manifest.json').read_text()) == manifest
    assert manifest['entries']['runtime_python'] == 'runtime/.venv/Scripts/python.exe'
    assert (output / 'host/python.exe').read_bytes() == (options['python_home'] / 'python.exe').read_bytes()
    for name in ('host/python311._pth', 'runtime/.venv/Scripts/python311._pth'):
        contents = (output / name).read_text(); assert 'import site' not in contents and ':' not in contents and contents.endswith('\n')
    assert not (output / 'runtime/.venv/pyvenv.cfg').exists()
    assert not list(output.rglob('*.pyc'))
    assert not (output / 'runtime/browser_data').exists() and not (output / 'runtime/.env').exists()
    files = {p.relative_to(output).as_posix(): p for p in output.rglob('*') if p.is_file() and p.name != 'bundle-manifest.json'}
    assert set(files) == {entry['path'] for entry in manifest['files']}
    for entry in manifest['files']:
        assert files[entry['path']].stat().st_size == entry['size']
        assert hashlib.sha256(files[entry['path']].read_bytes()).hexdigest() == entry['sha256']
    for command, kwargs in state.calls:
        assert 'DATABASE_URL' not in kwargs['env'] and 'PYTHONHOME' not in kwargs['env']
        if command[0].endswith('python.exe'): assert '-B' in command
    assert 'private-token' not in json.dumps(manifest) and 'private-cookie' not in json.dumps(manifest) and 'developer' not in json.dumps(manifest)


@pytest.mark.parametrize('case', ['existing', 'overlap', 'relative', 'hardlink', 'missing-dependency', 'tampered-dependency', 'private-record'])
def test_bad_input_is_rejected_before_destination_created(fixture, case):
    api, state, options = fixture
    if case == 'existing': options['destination'].mkdir(); put(options['destination'], 'keep', b'untouched')
    elif case == 'overlap': options['destination'] = options['installed_runtime'] / 'nested'
    elif case == 'relative': options['python_home'] = Path('relative')
    elif case == 'hardlink':
        target = options['python_home'] / 'python.exe'; target.unlink(); os.link(options['python_home'] / 'python311.dll', target)
    elif case == 'missing-dependency': (options['host_site_packages'] / 'idna-1.0.dist-info/METADATA').unlink()
    elif case == 'tampered-dependency': (options['host_site_packages'] / 'idna/__init__.py').write_text('changed')
    else:
        with (options['host_site_packages'] / 'idna-1.0.dist-info/RECORD').open('a') as handle: handle.write('../../private/Cookies,,\n')
    with pytest.raises(api.PortableBundleError) as error: api.build_portable_bundle(**options)
    assert str(error.value).startswith('PORTABLE_') and 'private' not in str(error.value)
    assert not (options['destination'] / 'bundle-manifest.json').exists()
    if case == 'existing': assert (options['destination'] / 'keep').read_bytes() == b'untouched'
    else: assert not options['destination'].exists()


@pytest.mark.parametrize('probe', ['YIKE_PORTABLE_HOST_OK', '--help', 'YIKE_BUNDLED_CHROMIUM_LOCAL_OK'])
def test_failed_probe_never_publishes_success_or_raw_logs(fixture, probe):
    api, state, options = fixture; state.fail = probe
    with pytest.raises(api.PortableBundleError) as error: api.build_portable_bundle(**options)
    assert not (options['destination'] / 'bundle-manifest.json').exists()
    assert 'private' not in str(error.value)


def test_cancellation_never_creates_or_publishes(fixture):
    api, _, options = fixture
    with pytest.raises(api.PortableBundleError, match='PORTABLE_CANCELLED'):
        api.build_portable_bundle(**options, cancel_requested=lambda: True)
    assert not options['destination'].exists()


@pytest.mark.parametrize('changed', ['host/__pycache__/probe.pyc', 'host/python311._pth'])
def test_probe_cannot_mutate_or_add_ignored_output(fixture, monkeypatch, changed):
    api, _, options = fixture; original = api.run_supervised_process
    def probe(command, **kwargs):
        result = original(command, **kwargs)
        if 'YIKE_BUNDLED_CHROMIUM_LOCAL_OK' in command[-1]:
            put(options['destination'], changed, b'changed')
        return result
    monkeypatch.setattr(api, 'run_supervised_process', probe)
    with pytest.raises(api.PortableBundleError, match='PORTABLE_OUTPUT_CHANGED'):
        api.build_portable_bundle(**options)
    assert not (options['destination'] / 'bundle-manifest.json').exists()


def test_browser_version_must_match_governed_receipt(fixture, monkeypatch):
    api, _, options = fixture; original = api.run_supervised_process
    def probe(command, **kwargs):
        result = original(command, **kwargs)
        if 'YIKE_BUNDLED_CHROMIUM_LOCAL_OK' in command[-1]:
            result.stdout = 'YIKE_BUNDLED_CHROMIUM_LOCAL_OK 150.0.0.0'
        return result
    monkeypatch.setattr(api, 'run_supervised_process', probe)
    with pytest.raises(api.PortableBundleError, match='PORTABLE_BROWSER_PROBE_FAILED'):
        api.build_portable_bundle(**options)
    assert not (options['destination'] / 'bundle-manifest.json').exists()


@pytest.mark.parametrize(('package','version','external'), [('fonttools','4.58.4','share/man/man1/ttx.1'), ('greenlet','3.5.3','include/site/python3.11/greenlet/greenlet.h')])
@pytest.mark.skipif(os.name != 'nt', reason='requires native Windows file validation')
def test_fixed_wheel_data_outside_site_packages_is_preserved(tmp_path, package, version, external):
    from app.windows_portable_inventory import package_files
    site = tmp_path / 'venv/Lib/site-packages'
    distribution(site, package, version, files={'../../'+external: b'wheel data'})
    entries = package_files(site, {package:version}, 'runtime/.venv/Lib/site-packages')
    assert any(entry.path == 'runtime/.venv/'+external for entry in entries)


@pytest.mark.parametrize(('package','version','path','target'), [
    ('fonttools','4.58.4','../../share/man/man1/ttx.1.bak','runtime/.venv/Lib/site-packages'),
    ('fonttools','4.58.4','../../share/man/man1/../man1/ttx.1','runtime/.venv/Lib/site-packages'),
    ('fonttools','4.58.4','../../share/man/man1/Cookies','runtime/.venv/Lib/site-packages'),
    ('fonttools','4.58.4','../../share/man/man1/TTX.1','runtime/.venv/Lib/site-packages'),
    ('fonttools','4.58.5','../../share/man/man1/ttx.1','runtime/.venv/Lib/site-packages'),
    ('greenlet','3.5.3','../../share/man/man1/ttx.1','runtime/.venv/Lib/site-packages'),
    ('greenlet','3.5.3','../../include/site/python3.12/greenlet/greenlet.h','runtime/.venv/Lib/site-packages'),
    ('fonttools','4.58.4','../../share/man/man1/ttx.1','host/site-packages'),
])
@pytest.mark.skipif(os.name != 'nt', reason='requires native Windows file validation')
def test_external_wheel_path_exceptions_are_exact(tmp_path, package, version, path, target):
    from app.windows_portable_inventory import PortableBundleError, package_files
    site = tmp_path/'venv/Lib/site-packages'; distribution(site, package, version)
    record = site/f'{package}-{version}.dist-info/RECORD'
    with record.open('a') as stream: stream.write(f'{path},sha256=invalid,10\n')
    with pytest.raises(PortableBundleError, match='PORTABLE_FILE_REJECTED'):
        package_files(site, {package:version}, target)
