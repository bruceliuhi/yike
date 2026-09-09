import hashlib
import json
import os
from pathlib import Path
import subprocess

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "package_mediacrawler.sh"


def _git_runtime(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "runtime"
    source.mkdir(mode=0o700)
    (source / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (source / "LICENSE").write_text("AUTHORIZED LICENSE\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.invalid", "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.invalid"}
    subprocess.run(["git", "-C", str(source), "commit", "-qm", "fixture"], check=True, env=env)
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    lock = tmp_path / "mediacrawler.lock"
    lock.write_text(json.dumps({"schema_version": "YIKE_MEDIACRAWLER_LOCK_V2", "commit": commit, "patches": [], "patchset_sha256": hashlib.sha256(b"[]").hexdigest()}), encoding="utf-8")
    return source, lock


def _run(source: Path, destination: Path, lock: Path):
    return subprocess.run([str(SCRIPT), str(source), str(destination), str(lock)], cwd=PROJECT_ROOT, text=True, capture_output=True, check=False)


def test_package_is_pinned_git_bundle_and_keeps_license(tmp_path):
    source, lock = _git_runtime(tmp_path)
    bundle = tmp_path / "mediacrawler.bundle"
    result = _run(source, bundle, lock)
    assert result.returncode == 0, result.stderr
    manifest = json.loads(Path(str(bundle) + ".manifest.json").read_text())
    assert manifest["commit"] == subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    assert manifest["bundle_sha256"] == hashlib.sha256(bundle.read_bytes()).hexdigest()
    assert b"AUTHORIZED LICENSE" in subprocess.check_output(["git", "-C", str(source), "show", manifest["commit"] + ":LICENSE"])


def test_package_fails_closed_for_dirty_or_unpinned_source(tmp_path):
    source, lock = _git_runtime(tmp_path)
    (source / ".env").write_text("SECRET=not-for-package\n", encoding="utf-8")
    result = _run(source, tmp_path / "bundle", lock)
    assert result.returncode != 0
    assert not (tmp_path / "bundle").exists()


def test_package_rejects_destination_inside_source(tmp_path):
    source, lock = _git_runtime(tmp_path)
    result = _run(source, source / "bundle", lock)
    assert result.returncode != 0
    assert not (source / "bundle").exists()
