#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly -a YIKE_ENV_ALLOWLIST=(
  DISPLAY HOME LANG LC_ALL LC_CTYPE LOGNAME PATH SHELL SSL_CERT_DIR
  SSL_CERT_FILE SYSTEMROOT TERM TMPDIR USER WAYLAND_DISPLAY WINDIR XAUTHORITY
)
YIKE_PRIVATE_ENV=()
for name in "${YIKE_ENV_ALLOWLIST[@]}"; do
  if [[ -n "${!name:-}" ]]; then
    YIKE_PRIVATE_ENV+=("${name}=${!name}")
  fi
done

run_private() {
  env -i "${YIKE_PRIVATE_ENV[@]}" "$@"
}

readonly repository_url="https://github.com/NanmiCoder/MediaCrawler.git"
readonly pinned_commit="439509782cc2991c8ef7648e178d5847b0545798"
readonly destination="${1:?usage: fetch_mediacrawler.sh ABSOLUTE_DESTINATION [BUNDLE_PATH]}"
readonly package_path="${2:-${YIKE_MEDIACRAWLER_PACKAGE_PATH:-}}"
readonly project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly lock_path="${project_root}/vendor/mediacrawler.lock"

if [[ "${destination}" != /* ]]; then
  echo "destination must be absolute" >&2
  exit 2
fi
if [[ -e "${destination}" || -L "${destination}" ]]; then
  echo "destination already exists" >&2
  exit 2
fi

if [[ -n "${package_path}" ]]; then
  if [[ "${package_path}" != /* || ! -f "${package_path}" ]]; then
    echo "package bundle must be an existing absolute file" >&2
    exit 2
  fi
  run_private python3 - "${package_path}" "${lock_path}" <<'PY'
import hashlib, json, sys
from pathlib import Path
bundle, lock_path = map(Path, sys.argv[1:])
manifest_path = Path(str(bundle) + ".manifest.json")
try:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
except (OSError, ValueError) as exc:
    raise SystemExit(f"invalid MediaCrawler package manifest: {exc}")
if manifest.get("schema_version") != "YIKE_MEDIACRAWLER_PACKAGE_V2":
    raise SystemExit("unsupported MediaCrawler package manifest")
if manifest.get("bundle_sha256") != hashlib.sha256(bundle.read_bytes()).hexdigest():
    raise SystemExit("MediaCrawler package checksum mismatch")
if manifest.get("commit") != lock.get("commit"):
    raise SystemExit("MediaCrawler package commit mismatch")
if manifest.get("patchset_sha256") != lock.get("patchset_sha256"):
    raise SystemExit("MediaCrawler package patchset mismatch")
if manifest.get("lock_sha256") != hashlib.sha256(lock_path.read_bytes()).hexdigest():
    raise SystemExit("MediaCrawler package lock checksum mismatch")
PY
  run_private git init -q "${destination}"
  run_private git -C "${destination}" remote add package "${package_path}"
  run_private git -C "${destination}" fetch --quiet package refs/yike/package:refs/remotes/package/pinned
else
  run_private git clone --filter=blob:none "${repository_url}" "${destination}"
fi
run_private chmod 700 "${destination}"
run_private git -C "${destination}" checkout --detach "${pinned_commit}"
test "$(run_private git -C "${destination}" rev-parse HEAD)" = "${pinned_commit}"
if [[ -n "${package_path}" ]]; then
  run_private python3 - "${package_path}" "${destination}/LICENSE" <<'PY'
import hashlib, json, sys
from pathlib import Path
bundle, license_path = map(Path, sys.argv[1:])
manifest = json.loads(Path(str(bundle) + ".manifest.json").read_text(encoding="utf-8"))
if manifest.get("license_sha256") != hashlib.sha256(license_path.read_bytes()).hexdigest():
    raise SystemExit("MediaCrawler package license checksum mismatch")
PY
fi

run_private python3 - "${lock_path}" "${project_root}" "${destination}" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

lock_path, project_root, runtime = map(Path, sys.argv[1:])
YIKE_ENV_ALLOWLIST = (
    "DISPLAY", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "LOGNAME", "PATH",
    "SHELL", "SSL_CERT_DIR", "SSL_CERT_FILE", "SYSTEMROOT", "TERM", "TMPDIR",
    "USER", "WAYLAND_DISPLAY", "WINDIR", "XAUTHORITY",
)


def child_environment(**runtime_values):
    environment = {
        name: os.environ[name]
        for name in YIKE_ENV_ALLOWLIST
        if name in os.environ
    }
    environment.update(runtime_values)
    return environment


base_environment = child_environment()
lock = json.loads(lock_path.read_text(encoding="utf-8"))
if lock.get("schema_version") != "YIKE_MEDIACRAWLER_LOCK_V2":
    raise SystemExit("unsupported MediaCrawler lock schema")
browser_contract = lock.get("browser_contract")
if browser_contract != {
    "engine": "playwright-bundled-chromium",
    "launch_channel": None,
    "user_agent_mode": "playwright-default",
}:
    raise SystemExit("unsupported browser runtime contract")
profile_contract = lock.get("profile_contract")
if profile_contract != {
    "root": "browser_data",
    "platform_paths": {
        "bili": "browser_data/bili_user_data_dir",
        "dy": "browser_data/dy_user_data_dir",
    },
    "directory_mode": "0700",
    "file_mode": "0600",
}:
    raise SystemExit("unsupported private profile contract")
if lock.get("progress_contract") != "YIKE_MEDIACRAWLER_PROGRESS_V1":
    raise SystemExit("unsupported progress contract")
if subprocess.check_output(
    ["git", "-C", str(runtime), "rev-parse", "HEAD"],
    text=True,
    env=base_environment,
).strip() != lock["commit"]:
    raise SystemExit("MediaCrawler pin mismatch")

def signature(entries):
    payload = json.dumps(entries, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

patch_entries = []
for patch in lock["patches"]:
    patch_path = (project_root / patch["path"]).resolve()
    if not patch_path.is_relative_to((project_root / "vendor/patches/mediacrawler").resolve()):
        raise SystemExit("patch path escaped governed directory")
    digest = hashlib.sha256(patch_path.read_bytes()).hexdigest()
    if digest != patch["sha256"]:
        raise SystemExit(f"patch checksum mismatch: {patch['path']}")
    patch_entries.append((patch["path"], digest))
    subprocess.run(
        [
            "git", "-C", str(runtime), "apply", "--check",
            "--unidiff-zero", "--whitespace=error-all", str(patch_path),
        ],
        check=True,
        env=base_environment,
    )
    subprocess.run(
        [
            "git", "-C", str(runtime), "apply", "--index",
            "--unidiff-zero", str(patch_path),
        ],
        check=True,
        env=base_environment,
    )
if signature(patch_entries) != lock["patchset_sha256"]:
    raise SystemExit("patchset checksum mismatch")

changed = set(
    subprocess.check_output(
        ["git", "-C", str(runtime), "diff", "HEAD", "--name-only", "--"],
        text=True,
        env=base_environment,
    ).splitlines()
)
if changed != set(lock["patched_files"]):
    raise SystemExit("patched file set mismatch")
file_entries = []
for relative, expected in sorted(lock["patched_files"].items()):
    path = (runtime / relative).resolve()
    if not path.is_relative_to(runtime.resolve()):
        raise SystemExit("patched file escaped runtime")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        raise SystemExit(f"patched file checksum mismatch: {relative}")
    file_entries.append((relative, digest))
if signature(file_entries) != lock["patched_tree_sha256"]:
    raise SystemExit("patched tree checksum mismatch")
subprocess.run(
    ["git", "-C", str(runtime), "diff", "HEAD", "--check"],
    check=True,
    env=base_environment,
)

runtime_environment = lock.get("runtime_environment")
required_environment_keys = {
    "uv_version",
    "lock_path",
    "lock_sha256",
    "manifest_path",
    "manifest_sha256",
    "python_path",
    "playwright_path",
    "browser_path",
}
if not isinstance(runtime_environment, dict) or set(runtime_environment) != required_environment_keys:
    raise SystemExit("runtime environment contract mismatch")
for path_key, sha_key in (
    ("lock_path", "lock_sha256"),
    ("manifest_path", "manifest_sha256"),
):
    path = (runtime / runtime_environment[path_key]).resolve()
    if not path.is_relative_to(runtime.resolve()) or not path.is_file():
        raise SystemExit(f"runtime dependency file missing: {path_key}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != runtime_environment[sha_key]:
        raise SystemExit(f"runtime dependency checksum mismatch: {path_key}")
uv_version = subprocess.check_output(
    ["uv", "--version"], text=True, env=base_environment
).split()[1]
if uv_version != runtime_environment["uv_version"]:
    raise SystemExit("uv version mismatch")
subprocess.run(
    [
        "uv", "sync", "--frozen", "--no-dev", "--no-install-project",
        "--project", str(runtime),
    ],
    check=True,
    env=base_environment,
)
python_path = runtime / runtime_environment["python_path"]
playwright_path = runtime / runtime_environment["playwright_path"]
browser_path = runtime / runtime_environment["browser_path"]
browser_environment = child_environment(
    PLAYWRIGHT_BROWSERS_PATH=str(browser_path)
)
subprocess.run(
    [str(playwright_path), "install", "chromium"],
    check=True,
    env=browser_environment,
    timeout=600,
)
browser_probe = subprocess.run(
    [
        str(python_path),
        "-c",
        (
            "import os; from pathlib import Path; "
            "from playwright.sync_api import sync_playwright; "
            "browser_path=Path(os.environ['YIKE_BROWSER_PATH']).resolve(); "
            "p=sync_playwright().start(); "
            "executable=Path(p.chromium.executable_path).resolve(); "
            "assert executable.is_file() and executable.is_relative_to(browser_path.resolve()); "
            "browser=p.chromium.launch(headless=True); "
            "assert browser.browser_type.name == 'chromium'; "
            "context=browser.new_context(); page=context.new_page(); "
            "assert page.evaluate('navigator.userAgent'); "
            "browser.close(); p.stop(); print('YIKE_BUNDLED_CHROMIUM_OK')"
        ),
    ],
    check=True,
    capture_output=True,
    text=True,
    cwd=runtime,
    env=child_environment(
        PLAYWRIGHT_BROWSERS_PATH=str(browser_path),
        YIKE_BROWSER_PATH=str(browser_path),
    ),
    timeout=60,
)
if browser_probe.stdout.strip() != "YIKE_BUNDLED_CHROMIUM_OK":
    raise SystemExit("bundled Chromium probe failed")
subprocess.run(
    [str(python_path), str(runtime / "main.py"), "--help"],
    check=True,
    capture_output=True,
    text=True,
    cwd=runtime,
    env=browser_environment,
    timeout=60,
)

marker = runtime / ".yike-runtime.json"
temporary = runtime / ".yike-runtime.json.tmp"
browser_data = runtime / profile_contract["root"]
browser_data.mkdir(mode=0o700, exist_ok=True)
browser_data.chmod(0o700)
for relative in profile_contract["platform_paths"].values():
    profile = runtime / relative
    if not profile.resolve().is_relative_to(browser_data.resolve()):
        raise SystemExit("profile path escaped private runtime root")
    profile.mkdir(mode=0o700, exist_ok=True)
    profile.chmod(0o700)
temporary.write_text(
    json.dumps(
        {
            "schema_version": "YIKE_MEDIACRAWLER_RUNTIME_V1",
            "commit": lock["commit"],
            "patchset_sha256": lock["patchset_sha256"],
            "patched_tree_sha256": lock["patched_tree_sha256"],
            "progress_contract": lock["progress_contract"],
            "browser_contract": browser_contract,
            "profile_contract": profile_contract,
            "runtime_environment": runtime_environment,
        },
        sort_keys=True,
    ),
    encoding="utf-8",
)
temporary.chmod(0o600)
temporary.replace(marker)
marker.chmod(0o600)
PY
