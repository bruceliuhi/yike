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
import hashlib, json, shutil, subprocess, sys
from pathlib import Path
source, destination, lock_path = (Path(v).resolve() for v in sys.argv[1:])
def fail(message): raise SystemExit(message)
if destination == source or destination.is_relative_to(source): fail('destination must not be inside source')
try: lock = json.loads(lock_path.read_text(encoding='utf-8'))
except (OSError, json.JSONDecodeError) as exc: fail(f'invalid MediaCrawler lock: {exc}')
commit = lock.get('commit')
if lock.get('schema_version') != 'YIKE_MEDIACRAWLER_LOCK_V2' or not isinstance(commit, str) or len(commit) != 40: fail('unsupported or invalid MediaCrawler lock')
try:
    head = subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=all'], text=True)
    license_text = subprocess.check_output(['git','-C',str(source),'show',f'{commit}:LICENSE'], text=True)
    tracked = subprocess.check_output(['git','-C',str(source),'ls-files','-z']) .decode().split('\0')
except (OSError, subprocess.CalledProcessError): fail('source must be a pinned git checkout containing LICENSE')
if head != commit: fail('source HEAD does not match MediaCrawler lock commit')
if dirty.strip(): fail('source checkout must be clean')
if not license_text.strip(): fail('upstream LICENSE is missing')
for item in filter(None, tracked):
    lower = item.lower()
    name = Path(item).name.lower()
    if lower in {'.env','.env.local'} or 'browser_data' in lower or name in {'cookies','cookie.json','storage_state.json','token.json'}: fail(f'source contains private-state path: {item}')
patch_entries=[]
for entry in lock.get('patches',[]):
    path=(lock_path.parent.parent/entry['path']).resolve()
    if not path.is_file() or not path.is_relative_to(lock_path.parent.parent.resolve()): fail(f'MediaCrawler patch is missing: {entry["path"]}')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != entry.get('sha256'): fail(f'MediaCrawler patch checksum mismatch: {entry["path"]}')
    patch_entries.append((entry['path'],digest))
patchset=hashlib.sha256(json.dumps(patch_entries,separators=(',',':')).encode()).hexdigest()
if patchset != lock.get('patchset_sha256'): fail('MediaCrawler patchset checksum mismatch')
bundle=destination
manifest_path=Path(str(bundle)+'.manifest.json')
try:
    ref = 'refs/yike/package'
    subprocess.run(['git','-C',str(source),'update-ref',ref,commit],check=True,capture_output=True)
    try:
        subprocess.run(['git','-C',str(source),'bundle','create',str(bundle),ref],check=True,capture_output=True)
    finally:
        subprocess.run(['git','-C',str(source),'update-ref','-d',ref],check=True,capture_output=True)
    subprocess.run(['git','bundle','verify',str(bundle)],check=True,capture_output=True)
    manifest={'schema_version':'YIKE_MEDIACRAWLER_PACKAGE_V2','commit':commit,'bundle_sha256':hashlib.sha256(bundle.read_bytes()).hexdigest(),'lock_sha256':hashlib.sha256(lock_path.read_bytes()).hexdigest(),'patchset_sha256':patchset,'license_sha256':hashlib.sha256(license_text.encode()).hexdigest()}
    manifest_path.write_text(json.dumps(manifest,sort_keys=True,separators=(',',':')),encoding='utf-8')
    bundle.chmod(0o600); manifest_path.chmod(0o600)
except Exception:
    bundle.unlink(missing_ok=True); manifest_path.unlink(missing_ok=True); raise
print(json.dumps({'schema_version':manifest['schema_version'],'commit':commit,'bundle':str(bundle)},separators=(',',':')))
PY
