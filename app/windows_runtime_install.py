"""Governed Windows runtime provisioner. Installation is not platform readiness."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Callable

from app.collector import _minimal_child_environment, run_supervised_process

REPOSITORY = 'https://github.com/NanmiCoder/MediaCrawler.git'
PIN = '439509782cc2991c8ef7648e178d5847b0545798'
WINDOWS_PYTHON = '.venv/Scripts/python.exe'
_NODE_DRIVER = '.venv/Lib/site-packages/playwright/driver'
_BROWSERS = '.venv/playwright-browsers'
_RECEIPT = '.yike-windows-install.json'
_BROWSER_PROBE = '''
import os
from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    executable = Path(p.chromium.executable_path).resolve(strict=True)
    assert executable.is_relative_to(Path(os.environ['PLAYWRIGHT_BROWSERS_PATH']).resolve(strict=True))
    browser = p.chromium.launch(headless=True, executable_path=str(executable))
    try:
        context = browser.new_context()
        context.route('**/*', lambda route: route.abort())
        page = context.new_page()
        page.set_content('<main>意客AI 原文证据 é😀</main>')
        assert page.url == 'about:blank'
        assert page.locator('main').inner_text() == '意客AI 原文证据 é😀'
        print('YIKE_BUNDLED_CHROMIUM_LOCAL_OK ' + browser.version)
    finally:
        browser.close()
'''


class RuntimeInstallError(RuntimeError):
    """Only fixed error codes are exposed; subprocess output may contain secrets."""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _signature(entries) -> str:
    return hashlib.sha256(json.dumps(entries, separators=(',', ':')).encode()).hexdigest()


def _within(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or '\\' in relative or ':' in relative:
        raise ValueError('relative path required')
    parsed = PurePosixPath(relative)
    if parsed.is_absolute() or not parsed.parts or any(p in ('.', '..') for p in parsed.parts):
        raise ValueError('relative path required')
    path = root.joinpath(*parsed.parts).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('path escaped root')
    return path


def load_governance(project_root: Path) -> dict:
    try:
        lock_path = project_root / 'vendor/mediacrawler.lock'
        raw = lock_path.read_bytes()
        lock = json.loads(raw)
        if (not isinstance(lock, dict) or not isinstance(lock.get('patches'), list)
                or not isinstance(lock.get('patched_files'), dict)
                or not isinstance(lock.get('runtime_environment'), dict)):
            raise ValueError('invalid governance structure')
        if (lock['schema_version'] != 'YIKE_MEDIACRAWLER_LOCK_V2'
                or lock['repository'] != REPOSITORY or lock['commit'] != PIN):
            raise ValueError('unsupported source')
        patches = []
        entries = []
        for patch in lock['patches']:
            path = _within(project_root, patch['path'])
            if not path.is_relative_to((project_root / 'vendor/patches/mediacrawler').resolve()):
                raise ValueError('patch outside governance')
            digest = _digest(path)
            if digest != patch['sha256']:
                raise ValueError('patch changed')
            patches.append(path)
            entries.append((patch['path'], digest))
        if not patches or _signature(entries) != lock['patchset_sha256']:
            raise ValueError('patch set changed')
        entries = sorted(lock['patched_files'].items())
        if not entries or _signature(entries) != lock['patched_tree_sha256']:
            raise ValueError('patched tree changed')
        for name, digest in entries:
            _within(project_root, name)
            if not re.fullmatch('[0-9a-f]{64}', digest):
                raise ValueError('invalid digest')
        environment = lock['runtime_environment']
        if not re.fullmatch(r'\d+\.\d+\.\d+', environment['uv_version']):
            raise ValueError('invalid uv version')
        for path_key, sha_key in [('lock_path', 'lock_sha256'), ('manifest_path', 'manifest_sha256')]:
            _within(project_root, environment[path_key])
            if not re.fullmatch('[0-9a-f]{64}', environment[sha_key]):
                raise ValueError('invalid dependency digest')
        return {'lock': lock, 'lock_sha256': hashlib.sha256(raw).hexdigest(), 'patches': patches}
    except (OSError, ValueError, TypeError, KeyError):
        raise RuntimeInstallError('governance_invalid') from None


def _private_directories():
    from app.windows_private_directory import create_private_directory, verify_private_tree
    return create_private_directory, verify_private_tree


def _installer_environment() -> dict[str, str]:
    # uv may locate its managed Python/cache through these ordinary OS paths.
    environment = _minimal_child_environment(**{
        name: os.environ[name] for name in ('USERPROFILE', 'LOCALAPPDATA', 'APPDATA', 'TEMP', 'TMP')
        if name in os.environ
    })
    environment.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0', UV_NO_CONFIG='1')
    return environment


def install_runtime(destination: Path, *, git_executable: Path, uv_executable: Path,
                    project_root: Path | None = None,
                    cancel_requested: Callable[[], bool] | None = None,
                    stage_callback: Callable[[str], None] | None = None) -> dict:
    """Create a NEW private runtime. On error preserve it, without a success receipt.

    Executable and resource paths are trusted bootstrap/operator inputs, not IPC.
    No resume/adoption or profile repair is performed by this installation API.
    """
    if sys.platform != 'win32':
        raise RuntimeInstallError('windows_required')
    destination = Path(destination)
    if (not destination.is_absolute() or destination.drive.startswith('\\')
            or os.path.lexists(destination) or not destination.parent.is_dir()):
        raise RuntimeInstallError('new_absolute_destination_required')
    for executable in (git_executable, uv_executable):
        if not executable.is_absolute() or not executable.is_file() or executable.suffix.lower() != '.exe':
            raise RuntimeInstallError('absolute_tool_executable_required')
    governed = load_governance(project_root or Path(__file__).resolve().parents[1])
    lock = governed['lock']
    environment = _installer_environment()

    def guard():
        if cancel_requested and cancel_requested():
            raise RuntimeInstallError('install_cancelled')

    def stage(name):
        guard()
        if stage_callback:
            stage_callback(name)
        guard()

    def run(command, *, cwd, env=environment, timeout=60):
        guard()
        result = run_supervised_process([str(arg) for arg in command], cwd=cwd, env=env,
                                        timeout_seconds=timeout, cancel_requested=cancel_requested)
        if result.cancelled:
            raise RuntimeInstallError('install_cancelled')
        if result.timed_out:
            raise RuntimeInstallError('install_timed_out')
        if result.returncode != 0:
            raise RuntimeInstallError('install_command_failed')
        guard()
        return result.stdout.strip()

    try:
        stage('PREFLIGHT')
        measured_uv = run([uv_executable, '--version'], cwd=destination.parent).split()
        if len(measured_uv) < 2 or measured_uv[:2] != ['uv', lock['runtime_environment']['uv_version']]:
            raise RuntimeInstallError('uv_version_mismatch')
        create_private, verify_private = _private_directories()
        destination = create_private(destination)
        stage('SOURCE')
        run([git_executable, 'clone', '--no-checkout', '--no-hardlinks', '--template=', REPOSITORY, destination],
            cwd=destination.parent, timeout=600)

        def git(*args):
            return run([git_executable, '-C', destination, *args], cwd=destination)

        git('config', '--local', 'core.autocrlf', 'false')
        git('checkout', '--detach', PIN)
        if git('rev-parse', 'HEAD') != PIN:
            raise RuntimeInstallError('source_pin_mismatch')
        for patch in governed['patches']:
            git('apply', '--check', '--unidiff-zero', '--whitespace=error-all', patch)
            git('apply', '--index', '--unidiff-zero', patch)
        changed = set(git('diff', 'HEAD', '--name-only', '--').splitlines())
        # Governance may additionally pin unchanged upstream dependencies.
        # Reject every ungoverned change; verify all pinned bytes below.
        if not changed.issubset(lock['patched_files']):
            raise RuntimeInstallError('patched_file_set_mismatch')
        for name, digest in lock['patched_files'].items():
            if _digest(_within(destination, name)) != digest:
                raise RuntimeInstallError('patched_file_checksum_mismatch')
        git('diff', 'HEAD', '--check')
        for key in ('lock', 'manifest'):
            spec = lock['runtime_environment']
            if _digest(_within(destination, spec[key + '_path'])) != spec[key + '_sha256']:
                raise RuntimeInstallError('dependency_checksum_mismatch')
        cache = destination / '.yike-install-cache'
        for directory in (cache, cache / 'tmp', cache / 'matplotlib'):
            directory.mkdir()
        environment.update(TEMP=str(cache / 'tmp'), TMP=str(cache / 'tmp'), MPLCONFIGDIR=str(cache / 'matplotlib'))
        stage('DEPENDENCIES')
        run([uv_executable, 'sync', '--no-config', '--frozen', '--no-dev', '--no-install-project',
             '--link-mode', 'copy', '--python', '3.11', '--project', destination], cwd=destination, timeout=900)
        python = destination / WINDOWS_PYTHON
        driver = destination / _NODE_DRIVER
        if not python.is_file() or not (driver / 'node.exe').is_file():
            raise RuntimeInstallError('windows_runtime_layout_missing')
        environment.update(PATH=str(driver) + os.pathsep + environment.get('PATH', ''),
                           PLAYWRIGHT_BROWSERS_PATH=str(destination / _BROWSERS))
        stage('BROWSER')
        run([python, '-X', 'utf8', '-m', 'playwright', 'install', 'chromium'], cwd=destination, timeout=600)
        stage('LOCAL_PROBE')
        help_text = run([python, '-X', 'utf8', 'main.py', '--help'], cwd=destination)
        if not all(platform in help_text for platform in ('xhs', 'dy', 'bili')):
            raise RuntimeInstallError('runtime_cli_probe_failed')
        probe = run([python, '-X', 'utf8', '-c', _BROWSER_PROBE], cwd=destination)
        matched = re.fullmatch(r'YIKE_BUNDLED_CHROMIUM_LOCAL_OK (\d+\.\d+\.\d+\.\d+)', probe)
        if not matched:
            raise RuntimeInstallError('runtime_browser_probe_failed')
        stage('PRIVATE_TREE_CHECK')
        verify_private(destination)
        guard()
        receipt = {'schema_version': 'YIKE_WINDOWS_RUNTIME_INSTALL_V1', 'commit': PIN,
                   'lock_sha256': governed['lock_sha256'], 'patchset_sha256': lock['patchset_sha256'],
                   'patched_tree_sha256': lock['patched_tree_sha256'], 'uv_version': measured_uv[1],
                   'python_path': WINDOWS_PYTHON, 'browser_path': _BROWSERS,
                   'browser_version': matched.group(1), 'dependency_link_mode': 'copy',
                   'local_probe': 'PASSED', 'platform_readiness': 'UNVERIFIED'}
        # Publish only a completely flushed receipt. Keep any failed temporary
        # write as diagnostic evidence; Windows rename never replaces a target.
        temporary = destination / (_RECEIPT + '.tmp')
        with temporary.open('x', encoding='utf-8', newline='\n') as handle:
            json.dump(receipt, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        guard()
        temporary.rename(destination / _RECEIPT)
        if stage_callback:
            stage_callback('INSTALLED_LOCAL_PROBE_ONLY')
        return receipt
    except RuntimeInstallError:
        raise
    except (OSError, ValueError):
        raise RuntimeInstallError('runtime_install_failed') from None


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description='Install a new governed Windows runtime; no platform login or sending.')
    parser.add_argument('--destination', required=True, type=Path)
    parser.add_argument('--git', required=True, type=Path)
    parser.add_argument('--uv', required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        install_runtime(arguments.destination, git_executable=arguments.git, uv_executable=arguments.uv,
                        stage_callback=lambda name: print(name, flush=True))
        return 0
    except RuntimeInstallError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
