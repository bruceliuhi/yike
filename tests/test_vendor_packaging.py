import json
import os
from pathlib import Path
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "package_mediacrawler.sh"
LOCK = PROJECT_ROOT / "vendor" / "mediacrawler.lock"


def _runtime(tmp_path: Path, *, license_text: str = "upstream license\n") -> Path:
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    (runtime / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (runtime / "LICENSE").write_text(license_text, encoding="utf-8")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    marker = {
        "schema_version": "YIKE_MEDIACRAWLER_RUNTIME_V1",
        "commit": lock["commit"],
        "patchset_sha256": lock["patchset_sha256"],
        "patched_tree_sha256": lock["patched_tree_sha256"],
        "progress_contract": lock["progress_contract"],
        "browser_contract": lock["browser_contract"],
        "profile_contract": lock["profile_contract"],
        "runtime_environment": lock["runtime_environment"],
    }
    (runtime / ".yike-runtime.json").write_text(
        json.dumps(marker), encoding="utf-8"
    )
    return runtime


def _run(source: Path, destination: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), str(source), str(destination)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={"PATH": os.environ["PATH"]},
    )


def test_package_copies_runtime_and_upstream_license_without_private_state(tmp_path):
    source = _runtime(tmp_path, license_text="ORIGINAL LICENSE\n")
    (source / "NOTICE").write_text("ORIGINAL NOTICE\n", encoding="utf-8")
    (source / ".venv").mkdir()
    (source / "browser_data").mkdir()
    destination = tmp_path / "packaged"

    result = _run(source, destination)

    assert result.returncode == 0, result.stderr
    assert (destination / "main.py").is_file()
    assert (destination / "LICENSE").read_text() == "ORIGINAL LICENSE\n"
    assert (destination / "NOTICE").read_text() == "ORIGINAL NOTICE\n"
    assert not (destination / ".venv").exists()
    assert not (destination / "browser_data").exists()
    assert (destination / ".yike-runtime.json").is_file()
    assert destination.stat().st_mode & 0o777 == 0o700


def test_package_fails_closed_when_license_missing(tmp_path):
    source = _runtime(tmp_path)
    (source / "LICENSE").unlink()
    destination = tmp_path / "packaged"

    result = _run(source, destination)

    assert result.returncode != 0
    assert "license" in result.stderr.lower()
    assert not destination.exists()


def test_package_fails_closed_when_marker_commit_or_patchset_mismatch(tmp_path):
    source = _runtime(tmp_path)
    marker = json.loads((source / ".yike-runtime.json").read_text())
    marker["commit"] = "0" * 40
    (source / ".yike-runtime.json").write_text(json.dumps(marker))
    destination = tmp_path / "packaged"

    result = _run(source, destination)

    assert result.returncode != 0
    assert "commit" in result.stderr.lower()
    assert not destination.exists()


def test_package_refuses_existing_destination(tmp_path):
    source = _runtime(tmp_path)
    destination = tmp_path / "packaged"
    destination.mkdir()
    sentinel = destination / "sentinel"
    sentinel.write_text("keep", encoding="utf-8")

    result = _run(source, destination)

    assert result.returncode != 0
    assert "exist" in result.stderr.lower()
    assert sentinel.read_text() == "keep"
