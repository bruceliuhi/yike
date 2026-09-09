#!/usr/bin/env bash
set -euo pipefail
umask 077
source_path="${1:?usage: package_mediacrawler.sh SOURCE DEST_BUNDLE [LOCK]}"
destination="${2:?usage: package_mediacrawler.sh SOURCE DEST_BUNDLE [LOCK]}"
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
lock_path="${3:-${project_root}/vendor/mediacrawler.lock}"
[[ "$source_path" = /* && "$destination" = /* && "$lock_path" = /* ]] || { echo 'paths must be absolute' >&2; exit 2; }
[[ -d "$source_path" && ! -L "$source_path" ]] || { echo 'source must be a regular directory' >&2; exit 2; }
[[ ! -e "$destination" && ! -L "$destination" ]] || { echo 'destination already exists' >&2; exit 2; }
python3 - "$source_path" "$destination" "$lock_path" <<'PY'
import hashlib, json, os, re, subprocess, sys, tempfile
from pathlib import Path
# Resolve the parent only: resolving the final output component would follow a
# symlink before the exclusive publication checks below can reject it.
source = Path(sys.argv[1]).resolve()
requested_destination = Path(sys.argv[2])
destination = requested_destination.parent.resolve() / requested_destination.name
lock_path = Path(sys.argv[3]).resolve()
def fail(message): raise SystemExit(message)
if destination == source or destination.is_relative_to(source): fail('destination must not be inside source')
manifest_path = Path(str(destination) + '.manifest.json')
for output in (destination, manifest_path):
    if os.path.lexists(output): fail(f'output already exists: {output}')
try: lock = json.loads(lock_path.read_text(encoding='utf-8'))
except (OSError, json.JSONDecodeError) as exc: fail(f'invalid MediaCrawler lock: {exc}')
commit = lock.get('commit')
if lock.get('schema_version') != 'YIKE_MEDIACRAWLER_LOCK_V2' or not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}', commit): fail('unsupported or invalid MediaCrawler lock')
try:
    head = subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=all'], text=True)
    license_bytes = subprocess.check_output(['git','-C',str(source),'show',f'{commit}:LICENSE'])
    tracked = subprocess.check_output(['git','-C',str(source),'ls-files','-z']).decode().split('\0')
    history = subprocess.check_output(['git','-C',str(source),'log',commit,'--pretty=format:','--name-only','-z']).decode().split('\0')
except (OSError, subprocess.CalledProcessError): fail('source must be a pinned git checkout containing LICENSE')
if head != commit: fail('source HEAD does not match MediaCrawler lock commit')
if dirty.strip(): fail('source checkout must be clean')
if not license_bytes.strip(): fail('upstream LICENSE is missing')
for item in filter(None, set(tracked) | set(history)):
    # Git log separates commits with newlines even with NUL path delimiters.
    lower = item.lstrip('\r\n').lower()
    name = Path(lower).name
    if any(part.startswith('.env') and part != '.env.example' for part in Path(lower).parts) or 'browser_data' in lower or re.search(r'(^|[._-])(cookie|cookies|token|secret|credential)([._-]|$)', name): fail(f'source contains private-state path: {item}')
patch_entries=[]
for entry in lock.get('patches',[]):
    path=(lock_path.parent.parent/entry['path']).resolve()
    if not path.is_file() or not path.is_relative_to(lock_path.parent.parent.resolve()): fail(f'MediaCrawler patch is missing: {entry["path"]}')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != entry.get('sha256'): fail(f'MediaCrawler patch checksum mismatch: {entry["path"]}')
    patch_entries.append((entry['path'],digest))
patchset=hashlib.sha256(json.dumps(patch_entries,separators=(',',':')).encode()).hexdigest()
if patchset != lock.get('patchset_sha256'): fail('MediaCrawler patchset checksum mismatch')
published = []
with tempfile.TemporaryDirectory(prefix='.yike-package-', dir=destination.parent) as temporary:
    stage = Path(temporary)
    repository = stage / 'repository.git'
    staged_bundle = stage / 'source.bundle'
    staged_manifest = stage / 'source.bundle.manifest.json'
    # Only the private temporary repository owns refs/yike/package. Never
    # overwrite or delete refs in the caller's authorized source checkout.
    subprocess.run(['git','init','--bare','-q',str(repository)],check=True,capture_output=True)
    subprocess.run(['git','-C',str(repository),'fetch','--no-tags',str(source),f'{commit}:refs/yike/package'],check=True,capture_output=True)
    subprocess.run(['git','-C',str(repository),'bundle','create',str(staged_bundle),'refs/yike/package'],check=True,capture_output=True)
    subprocess.run(['git','-C',str(repository),'bundle','verify',str(staged_bundle)],check=True,capture_output=True)
    manifest={'schema_version':'YIKE_MEDIACRAWLER_PACKAGE_V2','commit':commit,'bundle_sha256':hashlib.sha256(staged_bundle.read_bytes()).hexdigest(),'lock_sha256':hashlib.sha256(lock_path.read_bytes()).hexdigest(),'patchset_sha256':patchset,'license_sha256':hashlib.sha256(license_bytes).hexdigest()}
    staged_manifest.write_text(json.dumps(manifest,sort_keys=True,separators=(',',':')),encoding='utf-8')
    staged_bundle.chmod(0o600); staged_manifest.chmod(0o600)
    try:
        # Hard links publish complete files atomically and fail if the target
        # exists, including dangling symlinks or a concurrent writer's output.
        # Publish the manifest first so an observable bundle always has it.
        for staged, output in ((staged_manifest, manifest_path), (staged_bundle, destination)):
            identity = staged.stat()
            os.link(staged, output)
            published.append((output, identity.st_dev, identity.st_ino))
    except Exception:
        for output, device, inode in reversed(published):
            try:
                current = output.lstat()
                if (current.st_dev, current.st_ino) == (device, inode): output.unlink()
            except FileNotFoundError:
                pass
        raise
print(json.dumps({'schema_version':manifest['schema_version'],'commit':commit,'bundle':str(destination)},separators=(',',':')))
PY
