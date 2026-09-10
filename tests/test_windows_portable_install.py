"""Offline portable installer contract using tiny real files."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from app import windows_portable_install as installer


REQUIRED = (
    "host/python.exe",
    "runtime/.venv/Scripts/python.exe",
    "project/app/windows_platform_outreach.py",
    "project/app/platform_outreach_worker.py",
    "project/app/platform_outreach_runtime.py",
    "project/app/xhs_comment_channel.py",
    "project/app/windows_portable_install.py",
)


def _put(root: Path, name: str, content: bytes = b"tiny fixture") -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _payload(root: Path, extra_files: dict[str, bytes] | None = None) -> str:
    contents = {name: ("content:" + name).encode() for name in REQUIRED}
    contents.update(extra_files or {})
    for name, content in contents.items():
        _put(root, name, content)
    manifest = {
        "schema_version": "YIKE_WINDOWS_PORTABLE_BUNDLE_V1",
        "entries": {
            "host_python": "host/python.exe",
            "project_root": "project",
            "runtime_root": "runtime",
            "runtime_python": "runtime/.venv/Scripts/python.exe",
        },
        "files": [
            {"path": name, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
            for name, content in sorted(contents.items())
        ],
    }
    raw = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    (root / "bundle-manifest.json").write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def windows_acl(monkeypatch):
    monkeypatch.setattr(installer.sys, "platform", "win32")
    created: list[Path] = []
    verified: list[Path] = []

    def create(path: Path) -> Path:
        path.mkdir()
        created.append(path)
        return path

    monkeypatch.setattr(installer, "create_private_directory", create)
    monkeypatch.setattr(installer, "verify_private_tree", lambda path: verified.append(path))
    return created, verified


@pytest.mark.skipif(os.name == "nt", reason="non-Windows rejection boundary")
def test_non_windows_rejected_before_reading_or_creating(tmp_path):
    destination = tmp_path / "destination"
    with pytest.raises(installer.PortableInstallError, match="PORTABLE_INSTALL_FAILED"):
        installer.install_portable_bundle(tmp_path / "missing", destination, "0" * 64)
    assert not destination.exists()


def test_new_tree_is_private_complete_and_manifest_published_last(tmp_path, windows_acl):
    source = tmp_path / "source"
    source.mkdir()
    digest = _payload(source)
    destination = tmp_path / "destination"

    result = installer.install_portable_bundle(source, destination, digest)

    assert result == {"state": "READY", "manifestSha256": digest}
    assert {p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file()} == {
        *REQUIRED,
        "bundle-manifest.json",
    }
    assert (destination / "bundle-manifest.json").read_bytes() == (source / "bundle-manifest.json").read_bytes()
    created, verified = windows_acl
    assert created[0] == destination
    assert destination in verified


@pytest.mark.parametrize("damage", ["missing", "tampered", "extra", "manifest-self", "escape", "case-collision"])
def test_invalid_source_never_creates_destination(tmp_path, windows_acl, damage):
    source = tmp_path / "source"
    source.mkdir()
    digest = _payload(source)
    manifest_path = source / "bundle-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if damage == "missing":
        (source / REQUIRED[-1]).unlink()
    elif damage == "tampered":
        (source / REQUIRED[-1]).write_bytes(b"changed")
    elif damage == "extra":
        _put(source, "unlisted.txt")
    else:
        entry = dict(path="bundle-manifest.json" if damage == "manifest-self" else
                     "../escape" if damage == "escape" else REQUIRED[0].upper(), size=0, sha256="0" * 64)
        manifest["files"].append(entry)
        manifest_path.write_text(json.dumps(manifest, separators=(",", ":")) + "\n")
        digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    destination = tmp_path / "destination"

    with pytest.raises(installer.PortableInstallError, match="PORTABLE_INSTALL_FAILED"):
        installer.install_portable_bundle(source, destination, digest)
    assert not destination.exists()


@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
def test_source_links_are_rejected(tmp_path, windows_acl, kind):
    source = tmp_path / "source"
    source.mkdir()
    digest = _payload(source)
    target = source / REQUIRED[-1]
    original = source / "original"
    target.rename(original)
    if kind == "symlink":
        target.symlink_to(original)
    else:
        os.link(original, target)
    destination = tmp_path / "destination"

    with pytest.raises(installer.PortableInstallError, match="PORTABLE_INSTALL_FAILED"):
        installer.install_portable_bundle(source, destination, digest)
    assert not destination.exists()


def test_interrupted_copy_leaves_unpublished_partial_tree(tmp_path, windows_acl, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    digest = _payload(source)
    destination = tmp_path / "destination"
    original = installer._copy_file
    calls = 0

    def interrupt(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        return original(*args, **kwargs)

    monkeypatch.setattr(installer, "_copy_file", interrupt)
    with pytest.raises(installer.PortableInstallError, match="PORTABLE_INSTALL_FAILED"):
        installer.install_portable_bundle(source, destination, digest)
    assert destination.exists()
    assert not (destination / "bundle-manifest.json").exists()


def test_existing_valid_tree_is_verified_without_overwrite(tmp_path, windows_acl):
    source = tmp_path / "source"
    source.mkdir()
    digest = _payload(source)
    destination = tmp_path / "destination"
    installer.install_portable_bundle(source, destination, digest)
    before = {p.relative_to(destination).as_posix(): p.read_bytes() for p in destination.rglob("*") if p.is_file()}

    result = installer.install_portable_bundle(source, destination, digest)

    assert result["state"] == "READY"
    assert before == {p.relative_to(destination).as_posix(): p.read_bytes() for p in destination.rglob("*") if p.is_file()}


def test_existing_partial_tree_is_not_repaired_or_overwritten(tmp_path, windows_acl):
    source = tmp_path / "source"
    source.mkdir()
    digest = _payload(source)
    destination = tmp_path / "destination"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_bytes(b"keep")

    with pytest.raises(installer.PortableInstallError, match="PORTABLE_INSTALL_FAILED"):
        installer.install_portable_bundle(source, destination, digest)
    assert marker.read_bytes() == b"keep"
    assert list(destination.iterdir()) == [marker]


def test_cli_emits_only_fixed_ready_or_failed_json(tmp_path, windows_acl, capsys):
    source = tmp_path / "source"
    source.mkdir()
    digest = _payload(source)
    destination = tmp_path / "destination"

    assert installer.main(["--source", str(source), "--destination", str(destination),
                           "--manifest-sha256", digest]) == 0
    assert capsys.readouterr().out == json.dumps(
        {"state": "READY", "manifestSha256": digest}, separators=(",", ":")
    ) + "\n"
    assert installer.main(["--source", str(source), "--destination", str(tmp_path / "other"),
                           "--manifest-sha256", "bad"]) != 0
    assert capsys.readouterr().out == '{"state":"FAILED","error":"PORTABLE_INSTALL_FAILED"}\n'
