#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly source_path="${1:?usage: package_mediacrawler.sh ABSOLUTE_SOURCE ABSOLUTE_DESTINATION}"
readonly destination="${2:?usage: package_mediacrawler.sh ABSOLUTE_SOURCE ABSOLUTE_DESTINATION}"
readonly project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly lock_path="${project_root}/vendor/mediacrawler.lock"

if [[ "${source_path}" != /* || "${destination}" != /* ]]; then
  echo "source and destination must be absolute" >&2
  exit 2
fi
if [[ ! -d "${source_path}" || -L "${source_path}" ]]; then
  echo "source must be a regular directory" >&2
  exit 2
fi
if [[ -e "${destination}" || -L "${destination}" ]]; then
  echo "destination already exists" >&2
  exit 2
fi
if [[ ! -f "${lock_path}" ]]; then
  echo "MediaCrawler lock is missing" >&2
  exit 2
fi

python3 - "${source_path}" "${destination}" "${lock_path}" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

source, destination, lock_path = map(Path, sys.argv[1:])
source = source.resolve()
destination = Path(destination)
lock_path = Path(lock_path).resolve()

def fail(message: str) -> None:
    raise SystemExit(message)

if destination.resolve().is_relative_to(source):
    fail("destination must not be inside source runtime")

try:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    fail(f"invalid MediaCrawler lock: {exc}")

if lock.get("schema_version") != "YIKE_MEDIACRAWLER_LOCK_V2":
    fail("unsupported MediaCrawler lock schema")
commit = lock.get("commit")
if not isinstance(commit, str) or len(commit) != 40:
    fail("MediaCrawler lock commit is invalid")

patch_entries = []
for patch in lock.get("patches", []):
    if not isinstance(patch, dict) or not isinstance(patch.get("path"), str):
        fail("MediaCrawler patch entry is invalid")
    patch_path = (lock_path.parent.parent / patch["path"]).resolve()
    if not patch_path.is_relative_to(lock_path.parent.parent.resolve()) or not patch_path.is_file():
        fail(f"MediaCrawler patch is missing: {patch['path']}")
    digest = hashlib.sha256(patch_path.read_bytes()).hexdigest()
    if digest != patch.get("sha256"):
        fail(f"MediaCrawler patch checksum mismatch: {patch['path']}")
    patch_entries.append((patch["path"], digest))

def signature(entries: list[tuple[str, str]]) -> str:
    payload = json.dumps(entries, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

if signature(patch_entries) != lock.get("patchset_sha256"):
    fail("MediaCrawler patchset checksum mismatch")

license_path = source / "LICENSE"
if license_path.is_symlink() or not license_path.is_file():
    fail("upstream LICENSE is missing")
marker_path = source / ".yike-runtime.json"
if marker_path.is_symlink() or not marker_path.is_file():
    fail("verified runtime marker is missing")
try:
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    fail(f"invalid runtime marker: {exc}")
if marker.get("schema_version") != "YIKE_MEDIACRAWLER_RUNTIME_V1":
    fail("unsupported runtime marker schema")
for key in (
    "commit", "patchset_sha256", "patched_tree_sha256", "progress_contract",
    "browser_contract", "profile_contract", "runtime_environment",
):
    if marker.get(key) != lock.get(key):
        fail(f"runtime marker {key} mismatch")
if marker.get("commit") != commit:
    fail("runtime marker commit mismatch")

excluded = {".git", ".venv", "browser_data"}
for path in source.rglob("*"):
    relative = path.relative_to(source)
    if relative.parts and relative.parts[0] in excluded:
        continue
    if path.is_symlink():
        fail(f"runtime contains an unsupported symlink: {relative}")

destination.mkdir(mode=0o700)
try:
    for item in source.iterdir():
        if item.name in excluded:
            continue
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target, symlinks=False)
        else:
            shutil.copy2(item, target)
    destination.chmod(0o700)
except Exception:
    shutil.rmtree(destination)
    raise

print(json.dumps({
    "schema_version": "YIKE_MEDIACRAWLER_PACKAGE_V1",
    "commit": commit,
    "patchset_sha256": lock["patchset_sha256"],
    "destination": str(destination),
}, sort_keys=True))
PY
