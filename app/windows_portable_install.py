"""Verify and privately install one bound offline portable payload."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys

from app.windows_private_directory import create_private_directory, verify_private_tree


SCHEMA = "YIKE_WINDOWS_PORTABLE_BUNDLE_V1"
MANIFEST = "bundle-manifest.json"
ENTRIES = {
    "host_python": "host/python.exe",
    "project_root": "project",
    "runtime_root": "runtime",
    "runtime_python": "runtime/.venv/Scripts/python.exe",
}
REQUIRED_FILES = {
    ENTRIES["host_python"],
    ENTRIES["runtime_python"],
    "project/app/windows_platform_outreach.py",
    "project/app/platform_outreach_worker.py",
    "project/app/platform_outreach_runtime.py",
    "project/app/xhs_comment_channel.py",
    "project/app/windows_portable_install.py",
}
MAX_MANIFEST = 16 * 1024 * 1024
MAX_FILES = 50_000
MAX_FILE = 512 * 1024 * 1024
MAX_TOTAL = 4 * 1024 * 1024 * 1024
BLOCK = 1024 * 1024


class PortableInstallError(RuntimeError):
    """Public fixed-code failure; paths and underlying exceptions stay private."""


def _fail() -> None:
    raise PortableInstallError("PORTABLE_INSTALL_FAILED")


def _is_link_or_non_file(path: Path, *, directory: bool = False) -> bool:
    metadata = path.lstat()
    reparse = bool(getattr(metadata, "st_file_attributes", 0) & 0x400)
    expected = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    return reparse or stat.S_ISLNK(metadata.st_mode) or not expected or (not directory and metadata.st_nlink != 1)


def _relative(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or not value.isprintable():
        _fail()
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") or part.endswith((" ", ".")) for part in path.parts):
        _fail()
    return path.as_posix()


def _sha256(path: Path, expected_size: int | None = None) -> str:
    if _is_link_or_non_file(path):
        _fail()
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(BLOCK):
            digest.update(block)
            size += len(block)
    if expected_size is not None and size != expected_size:
        _fail()
    return digest.hexdigest()


def _read_manifest(source: Path, expected_sha256: str) -> tuple[bytes, dict[str, tuple[int, str]]]:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        _fail()
    manifest_path = source / MANIFEST
    if _is_link_or_non_file(manifest_path) or manifest_path.stat().st_size > MAX_MANIFEST:
        _fail()
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        _fail()
    try:
        manifest = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail()
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA or manifest.get("entries") != ENTRIES:
        _fail()
    files = manifest.get("files")
    if not isinstance(files, list) or not files or len(files) > MAX_FILES:
        _fail()
    inventory: dict[str, tuple[int, str]] = {}
    folded: set[str] = set()
    total = 0
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "size", "sha256"}:
            _fail()
        name = _relative(item["path"])
        size, digest = item["size"], item["sha256"]
        if (name == MANIFEST or name.casefold() in folded or not isinstance(size, int) or isinstance(size, bool)
                or size < 0 or size > MAX_FILE or not isinstance(digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            _fail()
        total += size
        if total > MAX_TOTAL:
            _fail()
        folded.add(name.casefold())
        inventory[name] = (size, digest)
    if not REQUIRED_FILES.issubset(inventory):
        _fail()
    return raw, inventory


def _inventory(root: Path) -> set[str]:
    found: set[str] = set()

    def visit(directory: Path) -> None:
        if _is_link_or_non_file(directory, directory=True):
            _fail()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                if entry.is_symlink():
                    _fail()
                metadata = path.lstat()
                if getattr(metadata, "st_file_attributes", 0) & 0x400:
                    _fail()
                if stat.S_ISDIR(metadata.st_mode):
                    visit(path)
                elif stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1:
                    found.add(path.relative_to(root).as_posix())
                else:
                    _fail()

    visit(root)
    return found


def _verify_tree(root: Path, inventory: dict[str, tuple[int, str]], manifest_sha256: str) -> None:
    expected = set(inventory) | {MANIFEST}
    if _inventory(root) != expected or _sha256(root / MANIFEST) != manifest_sha256:
        _fail()
    for name, (size, digest) in inventory.items():
        if _sha256(root / name, size) != digest:
            _fail()


def _copy_file(source: Path, destination: Path, size: int, digest: str) -> None:
    copied = hashlib.sha256()
    copied_size = 0
    with source.open("rb") as incoming, destination.open("xb") as outgoing:
        while block := incoming.read(BLOCK):
            copied.update(block)
            copied_size += len(block)
            outgoing.write(block)
        outgoing.flush()
        os.fsync(outgoing.fileno())
    if copied_size != size or copied.hexdigest() != digest:
        _fail()


def install_portable_bundle(source, destination, manifest_sha256):
    """Copy an already verified payload without running code, network, or children."""
    try:
        if sys.platform != "win32":
            _fail()
        source = Path(source).absolute()
        destination = Path(destination).absolute()
        if not source.is_dir() or not destination.parent.is_dir() or _is_link_or_non_file(source, directory=True):
            _fail()
        source_real = source.resolve(strict=True)
        destination_real = destination.resolve(strict=False)
        if source_real == destination_real or source_real in destination_real.parents or destination_real in source_real.parents:
            _fail()
        raw_manifest, inventory = _read_manifest(source, manifest_sha256)
        _verify_tree(source, inventory, manifest_sha256)
        if os.path.lexists(destination):
            verify_private_tree(destination)
            _verify_tree(destination, inventory, manifest_sha256)
            return {"state": "READY", "manifestSha256": manifest_sha256}

        destination = create_private_directory(destination)
        directories = {destination}

        def ensure_directory(path: Path) -> None:
            if path not in directories:
                ensure_directory(path.parent)
                create_private_directory(path)
                directories.add(path)

        for name, (size, digest) in sorted(inventory.items()):
            target = destination / name
            ensure_directory(target.parent)
            _copy_file(source / name, target, size, digest)
        _copy_file(source / MANIFEST, destination / MANIFEST, len(raw_manifest), manifest_sha256)
        verify_private_tree(destination)
        _verify_tree(destination, inventory, manifest_sha256)
        return {"state": "READY", "manifestSha256": manifest_sha256}
    except PortableInstallError:
        raise
    except (Exception, KeyboardInterrupt):
        raise PortableInstallError("PORTABLE_INSTALL_FAILED") from None


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        _fail()


def main(argv=None) -> int:
    try:
        parser = _Parser(add_help=False)
        parser.add_argument("--source", required=True)
        parser.add_argument("--destination", required=True)
        parser.add_argument("--manifest-sha256", required=True)
        values = parser.parse_args(argv)
        result = install_portable_bundle(values.source, values.destination, values.manifest_sha256)
        print(json.dumps(result, separators=(",", ":")))
        return 0
    except (Exception, KeyboardInterrupt):
        print('{"state":"FAILED","error":"PORTABLE_INSTALL_FAILED"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
