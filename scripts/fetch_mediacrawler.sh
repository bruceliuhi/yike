#!/usr/bin/env bash
set -euo pipefail

readonly repository_url="https://github.com/NanmiCoder/MediaCrawler.git"
readonly pinned_commit="439509782cc2991c8ef7648e178d5847b0545798"
readonly destination="${1:?usage: fetch_mediacrawler.sh ABSOLUTE_DESTINATION}"
readonly project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly lock_path="${project_root}/vendor/mediacrawler.lock"

if [[ "${destination}" != /* ]]; then
  echo "destination must be absolute" >&2
  exit 2
fi
if [[ -e "${destination}" ]]; then
  echo "destination already exists" >&2
  exit 2
fi

git clone --filter=blob:none "${repository_url}" "${destination}"
git -C "${destination}" checkout --detach "${pinned_commit}"
test "$(git -C "${destination}" rev-parse HEAD)" = "${pinned_commit}"

python3 - "${lock_path}" "${project_root}" "${destination}" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

lock_path, project_root, runtime = map(Path, sys.argv[1:])
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
if subprocess.check_output(
    ["git", "-C", str(runtime), "rev-parse", "HEAD"], text=True
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
    )
    subprocess.run(
        ["git", "-C", str(runtime), "apply", "--unidiff-zero", str(patch_path)],
        check=True,
    )
if signature(patch_entries) != lock["patchset_sha256"]:
    raise SystemExit("patchset checksum mismatch")

changed = set(
    subprocess.check_output(
        ["git", "-C", str(runtime), "diff", "HEAD", "--name-only", "--"],
        text=True,
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
subprocess.run(["git", "-C", str(runtime), "diff", "--check"], check=True)

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
uv_version = subprocess.check_output(["uv", "--version"], text=True).split()[1]
if uv_version != runtime_environment["uv_version"]:
    raise SystemExit("uv version mismatch")
subprocess.run(
    [
        "uv", "sync", "--frozen", "--no-dev", "--no-install-project",
        "--project", str(runtime),
    ],
    check=True,
)
python_path = runtime / runtime_environment["python_path"]
playwright_path = runtime / runtime_environment["playwright_path"]
browser_path = runtime / runtime_environment["browser_path"]
browser_environment = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(browser_path)}
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
    env={**browser_environment, "YIKE_BROWSER_PATH": str(browser_path)},
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
temporary.write_text(
    json.dumps(
        {
            "schema_version": "YIKE_MEDIACRAWLER_RUNTIME_V1",
            "commit": lock["commit"],
            "patchset_sha256": lock["patchset_sha256"],
            "patched_tree_sha256": lock["patched_tree_sha256"],
            "browser_contract": browser_contract,
            "runtime_environment": runtime_environment,
        },
        sort_keys=True,
    ),
    encoding="utf-8",
)
temporary.replace(marker)
PY
