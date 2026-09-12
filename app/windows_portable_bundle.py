"""Build a new isolated offline payload. Never installs tools or contacts a platform."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from app.collector import run_supervised_process
from app.windows_private_directory import create_private_directory, verify_private_tree
from app.windows_runtime_install import load_governance, PIN, _BROWSER_PROBE
from app.windows_source_driver import verify_installed_runtime, _exclusive_paths
from app.windows_portable_inventory import (HOST_FILES, HOST_PACKAGES, CORE_FILES, PortableBundleError,
    check_path, fail, file, tree, relative, digest, lock_packages, dependencies, package_files)

SCHEMA = 'YIKE_WINDOWS_PORTABLE_BUNDLE_V1'
ENTRIES = dict(host_python='host/python.exe', project_root='project', runtime_root='runtime', runtime_python='runtime/.venv/Scripts/python.exe')
_CORE_PROBE = "import sys; from pathlib import Path; assert sys.version_info[:2]==(3,11) and sys.maxsize>2**32 and Path(sys.base_prefix).resolve()==Path(sys.executable).resolve().parent; print('YIKE_PORTABLE_CORE_OK '+sys.version.split()[0])"
_HOST_PROBE = '''
import sys
from pathlib import Path
assert sys.flags.isolated == 1 and sys.flags.no_site == 1 and sys.dont_write_bytecode
import app.windows_collection_host, app.windows_platform_login, app.windows_source_probe
import app.platform_collection_worker, app.platform_login_worker, app.windows_process_job, app.collection_output
import app.windows_platform_outreach, app.platform_outreach_worker
import app.platform_outreach_runtime, app.xhs_comment_channel
import app.windows_portable_install
import pydantic, pydantic_core, idna
root = Path(sys.executable).resolve().parents[1]
assert all(Path(value).resolve().is_relative_to(root) for value in sys.path)
for module in list(sys.modules.values()):
    source = getattr(module, '__file__', None)
    if source and not source.startswith('<'): assert Path(source).resolve().is_relative_to(root)
print('YIKE_PORTABLE_HOST_OK '+sys.version.split()[0])
'''


def build_portable_bundle(*, project_root, installed_runtime, python_home, host_site_packages,
                          destination, git_executable, cancel_requested=None):
    """Publish manifest only after three physically stopped local probes succeed.

    Input trees stay read-only. Failed output is retained without a manifest;
    no adoption, deletion, repair, network retry or capability grant is implied.
    """
    def guard():
        if cancel_requested and cancel_requested(): fail('PORTABLE_CANCELLED')

    def run(command, *, cwd, environment, timeout=60):
        guard()
        result = run_supervised_process([str(value) for value in command], cwd=cwd, env=environment,
                                       timeout_seconds=timeout, cancel_requested=cancel_requested)
        if result.cancelled: fail('PORTABLE_CANCELLED')
        if result.timed_out: fail('PORTABLE_TIMED_OUT')
        if result.returncode != 0: fail('PORTABLE_PROBE_FAILED')
        guard(); return result.stdout.strip()

    try:
        guard()
        if sys.platform != 'win32': fail('PORTABLE_WINDOWS_REQUIRED')
        roots = [check_path(value, directory=True) for value in (project_root, installed_runtime, python_home, host_site_packages)]
        project, runtime, core, host_site = roots
        git = check_path(git_executable, directory=False)
        if git.suffix.lower() != '.exe': fail()
        output = Path(destination)
        if (not output.is_absolute() or not re.match(r'^[A-Za-z]:[\\/]', str(output)) or
                output.name.endswith((' ', '.')) or not output.name.isprintable() or os.path.lexists(output)):
            fail('PORTABLE_DESTINATION_INVALID')
        check_path(output.parent, directory=True)
        all_roots = roots + [output]
        for index, left in enumerate(all_roots):
            for right in all_roots[index+1:]:
                if left.is_relative_to(right) or right.is_relative_to(left): fail('PORTABLE_PATH_OVERLAP')
        environment = {name: os.environ[name] for name in ('SystemRoot','WINDIR','USERNAME','TEMP','TMP') if name in os.environ}
        environment.update(PATHEXT='.EXE', PYTHONDONTWRITEBYTECODE='1', GIT_CONFIG_NOSYSTEM='1',
                           GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0')
        def git_run(root, *args): return run([git, '-C', root, *args], cwd=root, environment=environment)
        with _exclusive_paths([runtime]):
            verify_installed_runtime(runtime)
            governance = load_governance(project); lock = governance['lock']
            if git_run(runtime, 'rev-parse', 'HEAD') != PIN: fail('PORTABLE_SOURCE_INVALID')
            project_commit = git_run(project, 'rev-parse', 'HEAD')
            if not re.fullmatch('[0-9a-f]{40}', project_commit): fail('PORTABLE_SOURCE_INVALID')
            project_dirty = bool(git_run(project, 'status', '--porcelain', '--untracked-files=no'))
            files = []
            for name in CORE_FILES: check_path(core / name, directory=False)
            version = run([core/'python.exe', '-B', '-I', '-S', '-X', 'utf8', '-c', _CORE_PROBE], cwd=core, environment=environment)
            match = re.fullmatch(r'YIKE_PORTABLE_CORE_OK (3\.11\.\d+)', version)
            if not match: fail('PORTABLE_PYTHON_INVALID')
            python_version = match.group(1)
            for entry in git_run(runtime, 'ls-tree', '-r', '-z', '--full-tree', PIN).split('\0'):
                if not entry: continue
                mode_blob, name = entry.split('\t', 1); mode, kind, sha1 = mode_blob.split()
                if mode not in ('100644','100755') or kind != 'blob': fail('PORTABLE_SOURCE_INVALID')
                if name.startswith('.env'): continue
                entry = file(runtime/name, 'runtime/'+relative(name), guard)
                if name in lock['patched_files']:
                    if entry.sha256 != lock['patched_files'][name]: fail('PORTABLE_SOURCE_INVALID')
                else:
                    value = hashlib.sha1(b'blob '+str(entry.size).encode()+b'\0')
                    with entry.source.open('rb') as source:
                        while block := source.read(1024*1024): guard(); value.update(block)
                    if value.hexdigest() != sha1: fail('PORTABLE_SOURCE_INVALID')
                # The pinned documentation site is not executable payload. Keep
                # docs/hit_stopwords.txt and docs/STZHONGS.TTF: runtime config
                # references them. Still verify every original blob above, and
                # never omit governed patches or license/notice files.
                documentation = name.startswith('docs/') and (
                    name.endswith('.md') or name.startswith(('docs/static/', 'docs/.vitepress/')))
                if not documentation or name in lock['patched_files']:
                    files.append(entry)
            names = {entry.path for entry in files}
            for name, expected in lock['patched_files'].items():
                if 'runtime/'+name not in names:
                    entry = file(runtime/name, 'runtime/'+name, guard)
                    if entry.sha256 != expected: fail('PORTABLE_SOURCE_INVALID')
                    files.append(entry)
            files.append(file(runtime/'.yike-windows-install.json', 'runtime/.yike-windows-install.json', guard))
            for name in HOST_FILES + ('uv.lock','pyproject.toml','vendor/mediacrawler.lock'):
                files.append(file(project/name, 'project/'+name, guard))
            for patch in lock['patches']: files.append(file(project/patch['path'], 'project/'+patch['path'], guard))
            for name in ('LICENSE','LICENSE.txt','NOTICE'):
                if (project/name).is_file(): files.append(file(project/name, 'project/'+name, guard))
            files.extend(tree(core/'Lib', 'python/Lib', guard, exclude=('site-packages','ensurepip','idlelib')))
            files.extend(tree(core/'DLLs', 'python/DLLs', guard))
            for name in CORE_FILES:
                for prefix in ('host', 'runtime/.venv/Scripts'):
                    files.append(file(core/name, prefix+'/'+name, guard))
            host_packages = lock_packages(project/'uv.lock')
            host_expected = dependencies(host_packages, HOST_PACKAGES, python_version)
            crawler_packages = lock_packages(runtime/'uv.lock')
            crawler_expected = dependencies(crawler_packages, ('mediacrawler',), python_version)
            files.extend(package_files(host_site, host_expected, 'host/site-packages', guard))
            site = runtime/'.venv/Lib/site-packages'
            files.extend(package_files(site, crawler_expected, 'runtime/.venv/Lib/site-packages', guard))
            browsers = json.loads((site/'playwright/driver/package/browsers.json').read_text(encoding='utf-8'))['browsers']
            for name in ('chromium','chromium-headless-shell','ffmpeg','winldd'):
                matches = [item for item in browsers if item['name'] == name]
                if len(matches) != 1 or not re.fullmatch(r'\d+', matches[0]['revision']): fail('PORTABLE_BROWSER_INVALID')
                directory = name.replace('-', '_')+'-'+matches[0]['revision']
                files.extend(tree(runtime/'.venv/playwright-browsers'/directory, 'runtime/.venv/playwright-browsers/'+directory, guard))
            # Case-insensitive collision rejection applies to all Windows output paths.
            if len({entry.path.lower() for entry in files}) != len(files): fail('PORTABLE_FILE_REJECTED')
            # Squirrel's legacy .NET Package reader corrupts Unicode ZIP names
            # during uninstall registration. Fail before publishing, rather than
            # silently dropping or renaming a future required runtime resource.
            if any(not entry.path.isascii() for entry in files): fail('PORTABLE_SQUIRREL_NON_ASCII_PATH')
            guard(); output = create_private_directory(output)
            directories = {output}
            def parent(path):
                if path not in directories:
                    parent(path.parent); create_private_directory(path); directories.add(path)
            for entry in sorted(files, key=lambda item: item.path):
                guard(); check_path(entry.source, directory=False)
                target = output/entry.path; parent(target.parent)
                copied = hashlib.sha256(); size = 0
                with entry.source.open('rb') as source, target.open('xb') as destination_file:
                    while block := source.read(1024*1024):
                        guard(); copied.update(block); size += len(block); destination_file.write(block)
                    destination_file.flush(); os.fsync(destination_file.fileno())
                if copied.hexdigest() != entry.sha256 or size != entry.size: fail('PORTABLE_SOURCE_CHANGED')
            generated = {
                'host/python311._pth': '.\n../python/Lib/\n../python/DLLs/\nsite-packages/\n../project/\n',
                'runtime/.venv/Scripts/python311._pth': '.\n../../../python/Lib/\n../../../python/DLLs/\n../Lib/site-packages/\n../../\n../../../project/\n'}
            for name, content in generated.items():
                with (output/name).open('x', encoding='utf-8', newline='\n') as target:
                    target.write(content); target.flush(); os.fsync(target.fileno())
            # Temp/cache/profile files belong outside the deliverable and are never inventoried.
            with tempfile.TemporaryDirectory(prefix='yike-portable-probe-', dir=output.parent) as temporary:
                probe_env = {key: value for key,value in environment.items() if not key.startswith('GIT_')}
                probe_env.update(TEMP=temporary, TMP=temporary, MPLCONFIGDIR=temporary,
                    PATH=str(output/'runtime/.venv/Lib/site-packages/playwright/driver'),
                    PLAYWRIGHT_BROWSERS_PATH=str(output/'runtime/.venv/playwright-browsers'))
                host_result = run([output/'host/python.exe','-B','-X','utf8','-c',_HOST_PROBE], cwd=Path(temporary), environment=probe_env)
                if host_result != 'YIKE_PORTABLE_HOST_OK '+python_version: fail('PORTABLE_HOST_PROBE_FAILED')
                help_text = run([output/ENTRIES['runtime_python'],'-B','-X','utf8',output/'runtime/main.py','--help'], cwd=output/'runtime', environment=probe_env)
                if not all(name in help_text for name in ('xhs','dy','bili')): fail('PORTABLE_CLI_PROBE_FAILED')
                browser_text = run([output/ENTRIES['runtime_python'],'-B','-X','utf8','-c',_BROWSER_PROBE], cwd=Path(temporary), environment=probe_env)
                browser = re.fullmatch(r'YIKE_BUNDLED_CHROMIUM_LOCAL_OK (\d+\.\d+\.\d+\.\d+)', browser_text)
                receipt = json.loads((runtime/'.yike-windows-install.json').read_text(encoding='utf-8'))
                if not browser or browser.group(1) != receipt['browser_version']: fail('PORTABLE_BROWSER_PROBE_FAILED')
            verify_private_tree(output); guard()
            actual = tree(output, 'payload', guard, reject_cache=True)
            expected_paths = {entry.path for entry in files} | set(generated)
            if {entry.path.removeprefix('payload/') for entry in actual} != expected_paths: fail('PORTABLE_OUTPUT_CHANGED')
            expected_hashes = {entry.path: entry.sha256 for entry in files}
            expected_hashes.update({name: hashlib.sha256(content.encode('utf-8')).hexdigest() for name,content in generated.items()})
            for entry in actual:
                name = entry.path.removeprefix('payload/')
                if name in expected_hashes and entry.sha256 != expected_hashes[name]: fail('PORTABLE_OUTPUT_CHANGED')
            manifest = dict(schema_version=SCHEMA, source=dict(project_commit=project_commit, project_dirty=project_dirty,
                mediacrawler_commit=PIN, governance_lock_sha256=governance['lock_sha256'], patchset_sha256=lock['patchset_sha256'],
                patched_tree_sha256=lock['patched_tree_sha256'], host_lock_sha256=digest(project/'uv.lock', guard)),
                entries=ENTRIES.copy(), dependencies={key:[dict(name=name,version=version) for name,version in sorted(value.items())]
                    for key,value in [('host',host_expected),('crawler',crawler_expected)]},
                probes=dict(host=dict(status='PASSED',python_version=python_version), runtime_cli=dict(status='PASSED'),
                            chromium=dict(status='PASSED',browser_version=browser.group(1))),
                files=[dict(path=entry.path.removeprefix('payload/'),size=entry.size,sha256=entry.sha256) for entry in sorted(actual,key=lambda entry:entry.path)])
            temporary = output/'bundle-manifest.json.tmp'
            with temporary.open('x', encoding='utf-8', newline='\n') as stream:
                json.dump(manifest, stream, ensure_ascii=False, sort_keys=True, separators=(',',':')); stream.write('\n')
                stream.flush(); os.fsync(stream.fileno())
            guard(); temporary.rename(output/'bundle-manifest.json')
            return manifest
    except PortableBundleError: raise
    except (Exception, KeyboardInterrupt): raise PortableBundleError('PORTABLE_BUILD_FAILED') from None
