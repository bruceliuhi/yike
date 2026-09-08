from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cp06_validate_env.sh"


def _base_env(tmp_path: Path) -> dict[str, str]:
    passphrase = tmp_path / "backup-passphrase"
    passphrase.write_text("pilot-production-passphrase\n", encoding="utf-8")
    passphrase.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return {
        **os.environ,
        "YIKE_PILOT_DATABASE_URL": "postgresql://pilot:secret@private-db:5432/pilot",
        "YIKE_PILOT_AUTH_SECRET": "a" * 48,
        "YIKE_PILOT_BACKUP_PASSPHRASE_FILE": str(passphrase),
        "YIKE_PILOT_PROXY_HEADERS": "0",
        "YIKE_PILOT_DEV_LOGIN": "0",
    }


def _run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_production_preflight_accepts_minimal_secure_environment(tmp_path: Path) -> None:
    result = _run(_base_env(tmp_path))

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "cp06-preflight: pass"
    assert "secret" not in result.stdout.lower()


def test_production_preflight_rejects_dev_login_and_wildcard_proxy(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    env["YIKE_PILOT_DEV_LOGIN"] = "1"
    env["YIKE_PILOT_PROXY_HEADERS"] = "1"
    env["YIKE_PILOT_FORWARDED_ALLOW_IPS"] = "*"

    result = _run(env)

    assert result.returncode != 0
    assert "dev login" in result.stderr.lower()


def test_production_preflight_rejects_invalid_database_and_weak_secret(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    env["YIKE_PILOT_DATABASE_URL"] = "sqlite:///tmp/pilot.db"
    env["YIKE_PILOT_AUTH_SECRET"] = "short"

    result = _run(env)

    assert result.returncode != 0
    assert "database" in result.stderr.lower()


def test_production_preflight_rejects_group_readable_backup_passphrase(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    passphrase = Path(env["YIKE_PILOT_BACKUP_PASSPHRASE_FILE"])
    passphrase.chmod(0o640)

    result = _run(env)

    assert result.returncode != 0
    assert "passphrase" in result.stderr.lower()
