from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _secret_file(tmp_path: Path) -> Path:
    secret = tmp_path / "backup-passphrase"
    secret.write_text("pilot-test-secret\n", encoding="utf-8")
    secret.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return secret


def _fake_pg_tools(tmp_path: Path, restored_path: Path | None = None) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    dump = bindir / "pg_dump"
    dump.write_text("#!/bin/sh\nprintf 'pilot-dump-fixture'\n", encoding="utf-8")
    dump.chmod(0o700)
    if restored_path is not None:
        restore = bindir / "pg_restore"
        restore.write_text(
            "#!/bin/bash\n"
            f"cp -- \"${{@: -1}}\" \"{restored_path}\"\n",
            encoding="utf-8",
        )
        restore.chmod(0o700)
    return bindir


def test_backup_writes_authenticated_sidecar(tmp_path: Path) -> None:
    secret = _secret_file(tmp_path)
    bindir = _fake_pg_tools(tmp_path)
    backup = tmp_path / "pilot.dump.enc"
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "YIKE_PILOT_DATABASE_URL": "postgresql://example.invalid/pilot",
        "YIKE_PILOT_BACKUP_PASSPHRASE_FILE": str(secret),
    }

    result = subprocess.run(
        ["bash", str(ROOT / "scripts/backup_pilot.sh"), str(backup)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert backup.is_file()
    assert (tmp_path / "pilot.dump.enc.mac").is_file()


def test_restore_rejects_tampered_backup_before_pg_restore(tmp_path: Path) -> None:
    secret = _secret_file(tmp_path)
    restored = tmp_path / "restored.dump"
    bindir = _fake_pg_tools(tmp_path, restored)
    backup = tmp_path / "pilot.dump.enc"
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "YIKE_PILOT_DATABASE_URL": "postgresql://example.invalid/pilot",
        "YIKE_PILOT_BACKUP_PASSPHRASE_FILE": str(secret),
    }

    created = subprocess.run(
        ["bash", str(ROOT / "scripts/backup_pilot.sh"), str(backup)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert created.returncode == 0, created.stderr

    backup.write_bytes(backup.read_bytes() + b"tamper")
    rejected = subprocess.run(
        ["bash", str(ROOT / "scripts/restore_pilot.sh"), str(backup)],
        env={**env, "CONFIRM_RESTORE": "YES"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert rejected.returncode != 0
    assert "integrity" in (rejected.stderr + rejected.stdout).lower()
    assert not restored.exists()
