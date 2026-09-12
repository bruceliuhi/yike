"""Fixed portable file inventories. No discovery through Python/Git/user PATH."""
from __future__ import annotations

import ast
import base64
import csv
from dataclasses import dataclass
import hashlib
import importlib.metadata
import io
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tomllib

HOST_PACKAGES = ('annotated-types', 'idna', 'pydantic', 'pydantic-core', 'typing-extensions', 'typing-inspection')
CORE_FILES = ('python.exe', 'python3.dll', 'python311.dll', 'vcruntime140.dll', 'vcruntime140_1.dll', 'LICENSE.txt')
HOST_FILES = ('app/__init__.py', 'app/collector.py', 'app/collectors/__init__.py', 'app/collectors/bilibili.py',
    'app/collectors/douyin.py', 'app/normalizer.py', 'app/repository.py', 'app/collection_output.py',
    'app/windows_private_directory.py', 'app/windows_process_job.py', 'app/windows_runtime_install.py',
    'app/windows_portable_install.py',
    'app/windows_source_driver.py', 'app/windows_collection_host.py', 'app/windows_source_probe.py',
    'app/windows_platform_login.py', 'app/platform_login_worker.py', 'app/platform_collection_worker.py',
    'app/bili_search_progress.py',
    'app/windows_platform_outreach.py', 'app/platform_outreach_worker.py',
    'app/platform_outreach_runtime.py', 'app/xhs_comment_channel.py',
    'connectors/__init__.py', 'connectors/models.py', 'connectors/normalizer.py', 'connectors/platforms.py',
    'connectors/bilibili.py', 'connectors/douyin.py', 'connectors/candidate_mapping.py', 'connectors/zhihu_mapping.py',
    'pilot/__init__.py', 'pilot/candidate_contract.py', 'pilot/native_collection_links.py',
    'pilot/native_search_cursor.py', 'pilot/native_search_progress.py', 'pilot/execution_contract.py')
PRIVATE_PARTS = {'browser_data', 'cookies', 'login data', 'history', 'local state', 'preferences', '.git',
                 '.yike-install-cache', '.env', '.env.local', '.env.production'}
# These two governed wheels install non-code data outside site-packages.
# Match package, locked version and raw RECORD spelling before any normalization.
EXTERNAL_WHEEL_FILES = {
    ('fonttools', '4.58.4', '../../share/man/man1/ttx.1'): 'share/man/man1/ttx.1',
    ('greenlet', '3.5.3', '../../include/site/python3.11/greenlet/greenlet.h'):
        'include/site/python3.11/greenlet/greenlet.h',
}


class PortableBundleError(RuntimeError):
    """Fixed build failure only; never include source paths or subprocess output."""


def fail(code='PORTABLE_INPUT_INVALID'):
    raise PortableBundleError(code)


def check_path(path, *, directory=None):
    path = Path(path)
    if (not path.is_absolute() or not re.match(r'^[A-Za-z]:[\\/]', str(path)) or
            any(not part.isprintable() or ':' in part or part.endswith((' ', '.')) for part in path.parts[1:])):
        fail()
    for item in reversed((path, *path.parents)):
        metadata = item.lstat()
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, 'st_file_attributes', 0) & 0x400:
            fail('PORTABLE_LINK_REJECTED')
        if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink != 1: fail('PORTABLE_LINK_REJECTED')
    if directory is True and not path.is_dir() or directory is False and not path.is_file(): fail()
    return path


def relative(name):
    value = PurePosixPath(name)
    if (not isinstance(name, str) or '\\' in name or ':' in name or not name.isprintable() or
            value.is_absolute() or not value.parts or any(part in ('', '.', '..') or part.endswith((' ', '.')) for part in value.parts)):
        fail('PORTABLE_FILE_REJECTED')
    if any(part.lower() in PRIVATE_PARTS for part in value.parts): fail('PORTABLE_PRIVATE_FILE_REJECTED')
    return value.as_posix()


def digest(path, guard=lambda: None, algorithm='sha256'):
    result = hashlib.new(algorithm)
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024): guard(); result.update(block)
    return result.hexdigest()


@dataclass(frozen=True)
class File:
    source: Path
    path: str
    size: int
    sha256: str


def file(source, target, guard=lambda: None):
    guard(); check_path(source, directory=False)
    metadata = source.stat()
    return File(source, relative(target), metadata.st_size, digest(source, guard))


def tree(root, target, guard=lambda: None, *, exclude=(), reject_cache=False):
    check_path(root, directory=True)
    result = []
    def visit(current):
        for path in sorted(current.iterdir()):
            guard()
            if path.name == '__pycache__' or path.suffix in ('.pyc', '.pyo'):
                if reject_cache: fail('PORTABLE_OUTPUT_CHANGED')
                continue
            if path.name in exclude: continue
            check_path(path)
            if path.is_dir(): visit(path)
            elif path.is_file(): result.append(file(path, target + '/' + path.relative_to(root).as_posix(), guard))
            else: fail('PORTABLE_FILE_REJECTED')
    visit(root)
    return result


def lock_packages(lock_path):
    check_path(lock_path, directory=False)
    packages = tomllib.loads(lock_path.read_text(encoding='utf-8'))['package']
    result = {}
    for package in packages:
        name, version = package['name'], package['version']
        if name in result or not re.fullmatch(r'[a-z0-9][a-z0-9-]*', name) or not isinstance(version, str): fail('PORTABLE_DEPENDENCY_INVALID')
        result[name] = package
    return result


def marker_matches(marker, python_version):
    """Evaluate only declarative lock comparisons, never eval/import arbitrary code."""
    environment = {'python_full_version': python_version, 'python_version': '.'.join(python_version.split('.')[:2]),
                   'sys_platform': 'win32', 'platform_machine': 'AMD64', 'platform_python_implementation': 'CPython',
                   'implementation_name': 'cpython', 'os_name': 'nt'}
    def visit(node):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            values = [visit(item) for item in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.left, ast.Name) and len(node.comparators) == 1:
            name = node.left.id; right = node.comparators[0]
            if name not in environment or not isinstance(right, ast.Constant) or not isinstance(right.value, str): fail('PORTABLE_LOCK_INVALID')
            left, right = environment[name], right.value
            if name.startswith('python_'):
                left, right = tuple(map(int, left.split('.'))), tuple(map(int, right.split('.')))
                length = max(len(left), len(right)); left += (0,) * (length-len(left)); right += (0,) * (length-len(right))
            operation = node.ops[0]
            if isinstance(operation, ast.Eq): return left == right
            if isinstance(operation, ast.NotEq): return left != right
            if isinstance(operation, ast.Lt): return left < right
            if isinstance(operation, ast.LtE): return left <= right
            if isinstance(operation, ast.Gt): return left > right
            if isinstance(operation, ast.GtE): return left >= right
        fail('PORTABLE_LOCK_INVALID')
    return visit(ast.parse(marker, mode='eval').body)


def dependencies(packages, roots, python_version):
    selected = set()
    def visit(name):
        if name in selected: return
        if name not in packages: fail('PORTABLE_DEPENDENCY_INVALID')
        selected.add(name)
        for dependency in packages[name].get('dependencies', []):
            if 'marker' not in dependency or marker_matches(dependency['marker'], python_version): visit(dependency['name'])
    for root in roots: visit(root)
    return {name: packages[name]['version'] for name in sorted(selected) if not packages[name].get('source', {}).get('virtual')}


def package_files(site, expected, target, guard=lambda: None):
    """Copy exact installed RECORD inventories and verify wheel-file hashes first."""
    check_path(site, directory=True)
    distributions = {}
    for distribution in importlib.metadata.distributions(path=[str(site)]):
        name = re.sub(r'[-_.]+', '-', distribution.metadata['Name']).lower()
        if name in expected:
            if name in distributions or distribution.version != expected[name]: fail('PORTABLE_DEPENDENCY_INVALID')
            distributions[name] = distribution
    if set(distributions) != set(expected): fail('PORTABLE_DEPENDENCY_INVALID')
    result = {}
    for name, distribution in sorted(distributions.items()):
        record = distribution.read_text('RECORD')
        if record is None: fail('PORTABLE_DEPENDENCY_INVALID')
        for row in csv.reader(io.StringIO(record)):
            if len(row) != 3: fail('PORTABLE_DEPENDENCY_INVALID')
            path, fingerprint, size = row
            # Console-script launchers embed build-machine paths and are never used.
            if re.fullmatch(r'\.\./\.\./Scripts/[A-Za-z0-9_.-]+(?:\.exe|\.py)', path): continue
            external = EXTERNAL_WHEEL_FILES.get((name, distribution.version, path))
            if external is not None:
                if target != 'runtime/.venv/Lib/site-packages': fail('PORTABLE_FILE_REJECTED')
                entry = file(site.parent.parent / external, 'runtime/.venv/' + external, guard)
            else:
                path = relative(path)
                if '__pycache__' in PurePosixPath(path).parts or path.endswith(('.pyc', '.pyo')): continue
                if path.endswith('.pth') or Path(path).name == 'direct_url.json': fail('PORTABLE_DEPENDENCY_INVALID')
                entry = file(site / path, target + '/' + path, guard)
            if fingerprint:
                if not fingerprint.startswith('sha256='): fail('PORTABLE_DEPENDENCY_INVALID')
                expected_digest = base64.urlsafe_b64decode(fingerprint[7:] + '=' * (-len(fingerprint[7:]) % 4)).hex()
                if entry.sha256 != expected_digest or str(entry.size) != size: fail('PORTABLE_DEPENDENCY_INVALID')
            elif not path.endswith('.dist-info/RECORD'): fail('PORTABLE_DEPENDENCY_INVALID')
            if entry.path in result and result[entry.path] != entry: fail('PORTABLE_DEPENDENCY_INVALID')
            result[entry.path] = entry
    return list(result.values())
