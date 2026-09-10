#!/usr/bin/env python3
"""Versioned encrypt-then-MAC sidecars. Never accept legacy path-key MACs."""
from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import stat
import sys

PREFIX = b'YIKE-BACKUP-MAC-V2\n'
DOMAIN = b'yike-pilot-backup-auth-v2\x00'
ITERATIONS = 200_000


def secret_bytes(path: Path) -> bytes:
    resolved = path.resolve(strict=True)
    if resolved.is_relative_to(Path(__file__).resolve().parents[1]):
        raise ValueError()
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077
                or info.st_uid != os.getuid() or info.st_size > 65536):
            raise ValueError()
        raw = stream.read(65537)
    # OpenSSL's file password source consumes the first line. Bound that line
    # below its input buffer limit; never put the secret in argv or diagnostics.
    secret = raw.split(b'\n', 1)[0]
    if not secret.strip() or len(secret) > 512 or b'\x00' in secret or b'\r' in secret:
        raise ValueError()
    return secret


def mac(path: Path, secret: bytes) -> bytes:
    with path.open('rb') as stream:
        head = stream.read(16)
        if len(head) != 16 or not head.startswith(b'Salted__'):
            raise ValueError()
        # Independent salt/domain from OpenSSL's encryption KDF, without a
        # fast password-check oracle. The encrypted header is authenticated too.
        key = hashlib.pbkdf2_hmac('sha256', secret, DOMAIN + head, ITERATIONS, 32)
        digest = hmac.new(key, DOMAIN + head, hashlib.sha256)
        size = len(head)
        while block := stream.read(1024 * 1024):
            digest.update(block)
            size += len(block)
        if size < 32:
            raise ValueError()
        return PREFIX + digest.digest()


def write_exclusive(path: Path, value: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def require_destination_outside_repository(path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    destination = path.parent.resolve(strict=True) / path.name
    if destination == repository or destination.is_relative_to(repository):
        raise ValueError()


def main(argv: list[str]) -> int:
    try:
        if len(argv) == 3 and argv[0] == 'snapshot':
            snapshot = Path(argv[2])
            require_destination_outside_repository(snapshot)
            write_exclusive(snapshot, secret_bytes(Path(argv[1])) + b'\n')
            return 0
        if len(argv) == 3 and argv[0] == 'publish':
            os.link(argv[1], argv[2], follow_symlinks=False)
            return 0
        if len(argv) != 4 or argv[0] not in ('create', 'verify'):
            raise ValueError()
        mode, cipher, secret, sidecar = argv
        if mode == 'verify':
            with Path(sidecar).open('rb') as stream:
                supplied = stream.read(len(PREFIX) + 33)
            if len(supplied) != len(PREFIX) + 32 or not supplied.startswith(PREFIX):
                raise ValueError()
        expected = mac(Path(cipher), secret_bytes(Path(secret)))
        if mode == 'verify':
            if not hmac.compare_digest(supplied, expected):
                raise ValueError()
        else:
            write_exclusive(Path(sidecar), expected)
        return 0
    except Exception:
        print('backup integrity operation failed (requires valid V2 format and secret)', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
