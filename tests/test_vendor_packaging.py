import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

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


def _commit_and_pin(source: Path, lock: Path) -> str:
    subprocess.run(["git", "-C", str(source), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture update"], check=True)
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    data = json.loads(lock.read_text())
    data["commit"] = commit
    lock.write_text(json.dumps(data))
    return commit


def _run(source: Path, destination: Path, lock: Path):
    # Packaging must also work when invoked outside a Git working directory.
    return subprocess.run([str(SCRIPT), str(source), str(destination), str(lock)], cwd=source.parent, text=True, capture_output=True, check=False)


def test_package_is_pinned_git_bundle_and_keeps_license(tmp_path):
    source, lock = _git_runtime(tmp_path)
    bundle = tmp_path / "mediacrawler.bundle"
    result = _run(source, bundle, lock)
    assert result.returncode == 0, result.stderr
    manifest = json.loads(Path(str(bundle) + ".manifest.json").read_text())
    assert manifest["commit"] == subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    assert manifest["bundle_sha256"] == hashlib.sha256(bundle.read_bytes()).hexdigest()
    restored = tmp_path / "restored.git"
    subprocess.run(["git", "init", "--bare", "-q", str(restored)], check=True)
    subprocess.run(["git", "-C", str(restored), "fetch", str(bundle), "refs/yike/package:refs/yike/package"], check=True, capture_output=True)
    license_bytes = subprocess.check_output(["git", "-C", str(restored), "show", "refs/yike/package:LICENSE"])
    assert license_bytes == b"AUTHORIZED LICENSE\n"
    assert manifest["license_sha256"] == hashlib.sha256(license_bytes).hexdigest()
    assert bundle.stat().st_mode & 0o777 == 0o600
    assert Path(str(bundle) + ".manifest.json").stat().st_mode & 0o777 == 0o600


def test_package_fails_closed_for_dirty_source(tmp_path):
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


@pytest.mark.parametrize("kind", ["file", "symlink", "dangling_symlink"])
def test_package_preserves_existing_manifest_and_its_target(tmp_path, kind):
    source, lock = _git_runtime(tmp_path)
    bundle = tmp_path / "bundle"
    manifest = Path(str(bundle) + ".manifest.json")
    other = tmp_path / "do-not-overwrite"
    if kind == "file":
        manifest.write_text("existing manifest")
    elif kind == "symlink":
        other.write_text("existing private file")
        manifest.symlink_to(other)
    else:
        manifest.symlink_to(other)
    result = _run(source, bundle, lock)
    assert result.returncode != 0
    assert "output already exists" in result.stderr
    assert not bundle.exists()
    if kind == "file":
        assert manifest.read_text() == "existing manifest"
    else:
        assert manifest.is_symlink()
        if kind == "symlink":
            assert other.read_text() == "existing private file"
        else:
            assert not other.exists()


def test_package_preserves_source_refs_and_checkout(tmp_path):
    source, lock = _git_runtime(tmp_path)
    original = json.loads(lock.read_text())["commit"]
    subprocess.run(["git", "-C", str(source), "update-ref", "refs/yike/package", original], check=True)
    (source / "main.py").write_text("print('new pinned source')\n")
    pinned = _commit_and_pin(source, lock)
    refs_before = subprocess.check_output(["git", "-C", str(source), "show-ref"])
    result = _run(source, tmp_path / "bundle", lock)
    assert result.returncode == 0, result.stderr
    assert subprocess.check_output(["git", "-C", str(source), "show-ref"]) == refs_before
    assert subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip() == pinned
    assert subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"]) == b""


@pytest.mark.parametrize("private_path", ["config/.env", ".env.production", "config/.env.local", "nested/.ENV.staging"])
def test_package_rejects_committed_environment_files(tmp_path, private_path):
    source, lock = _git_runtime(tmp_path)
    private = source / private_path
    private.parent.mkdir(parents=True, exist_ok=True)
    private.write_text("PRIVATE=fixture-only\n")
    _commit_and_pin(source, lock)
    result = _run(source, tmp_path / "bundle", lock)
    assert result.returncode != 0
    assert "private-state path" in result.stderr
    assert not (tmp_path / "bundle").exists()


def test_package_rejects_environment_file_deleted_from_pinned_tree(tmp_path):
    source, lock = _git_runtime(tmp_path)
    private = source / "config" / ".env.production"
    private.parent.mkdir()
    private.write_text("PRIVATE=historical-fixture-only\n")
    _commit_and_pin(source, lock)
    private.unlink()
    _commit_and_pin(source, lock)
    result = _run(source, tmp_path / "bundle", lock)
    assert result.returncode != 0
    assert "private-state path" in result.stderr
    assert not (tmp_path / "bundle").exists()


def test_package_rejects_unpinned_clean_source(tmp_path):
    source, lock = _git_runtime(tmp_path)
    original_lock = lock.read_text()
    (source / "main.py").write_text("print('wrong version')\n")
    _commit_and_pin(source, lock)
    lock.write_text(original_lock)
    result = _run(source, tmp_path / "bundle", lock)
    assert result.returncode != 0
    assert "HEAD does not match" in result.stderr
    assert not (tmp_path / "bundle").exists()
