from __future__ import annotations

import os
import shutil
import stat
import subprocess
import hashlib
import hmac
import sys
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
        "YIKE_PILOT_ADMIN_DATABASE_URL": "postgresql://example.invalid/pilot",
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


def test_backup_never_falls_back_to_runtime_database_url(tmp_path: Path) -> None:
    secret = _secret_file(tmp_path)
    bindir = _fake_pg_tools(tmp_path)
    backup = tmp_path / "pilot.dump.enc"
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/backup_pilot.sh"), str(backup)],
        env={
            **os.environ,
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "YIKE_PILOT_DATABASE_URL": "postgresql://app.invalid/pilot",
            "YIKE_PILOT_BACKUP_PASSPHRASE_FILE": str(secret),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "yike_pilot_admin_database_url" in result.stderr.lower()
    assert not backup.exists()


def test_backup_requires_the_separate_admin_database_connection(tmp_path: Path) -> None:
    secret = _secret_file(tmp_path)
    backup = tmp_path / "pilot.dump.enc"
    env = {
        **os.environ,
        "YIKE_PILOT_DATABASE_URL": "postgresql://app@example.invalid/pilot",
        "YIKE_PILOT_BACKUP_PASSPHRASE_FILE": str(secret),
    }

    result = subprocess.run(
        ["bash", str(ROOT / "scripts/backup_pilot.sh"), str(backup)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "admin_database_url" in result.stderr.lower()
    assert not backup.exists()


def test_restore_requires_an_explicit_isolated_target(tmp_path: Path) -> None:
    secret = _secret_file(tmp_path)
    env = {
        **os.environ,
        "YIKE_PILOT_ADMIN_DATABASE_URL": "postgresql://admin@example.invalid/pilot",
        "YIKE_PILOT_BACKUP_PASSPHRASE_FILE": str(secret),
        "CONFIRM_RESTORE": "YES",
    }

    result = subprocess.run(
        ["bash", str(ROOT / "scripts/restore_pilot.sh")],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "yike_restore_target=isolated" in result.stderr.lower()


def test_restore_rejects_tampered_backup_before_pg_restore(tmp_path: Path) -> None:
    secret = _secret_file(tmp_path)
    restored = tmp_path / "restored.dump"
    bindir = _fake_pg_tools(tmp_path, restored)
    backup = tmp_path / "pilot.dump.enc"
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "YIKE_PILOT_ADMIN_DATABASE_URL": "postgresql://example.invalid/pilot",
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
        env={**env, "CONFIRM_RESTORE": "YES", "YIKE_RESTORE_TARGET": "isolated"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert rejected.returncode != 0
    assert "integrity" in (rejected.stderr + rejected.stdout).lower()
    assert not restored.exists()


def test_restore_never_falls_back_to_runtime_database_url(tmp_path: Path) -> None:
    secret, restored, backup, env, run = _case(tmp_path)
    env.pop("YIKE_PILOT_ADMIN_DATABASE_URL")
    env["YIKE_PILOT_DATABASE_URL"] = "postgresql://app.invalid/pilot"

    result = run("restore_pilot.sh")

    assert result.returncode != 0
    assert "yike_pilot_admin_database_url" in result.stderr.lower()
    assert not restored.exists()


def _case(tmp_path):
    secret = _secret_file(tmp_path)
    restored = tmp_path / 'restored.dump'
    bindir = _fake_pg_tools(tmp_path, restored)
    backup = tmp_path / 'pilot.dump.enc'
    env = {**os.environ, 'PATH': f"{bindir}:{os.environ['PATH']}",
           'YIKE_PILOT_ADMIN_DATABASE_URL': 'postgresql://example.invalid/pilot',
           'YIKE_PILOT_BACKUP_PASSPHRASE_FILE': str(secret), 'CONFIRM_RESTORE': 'YES', 'YIKE_RESTORE_TARGET': 'isolated'}
    def run(script):
        return subprocess.run(['bash', str(ROOT / 'scripts' / script), str(backup)],
                              env=env, capture_output=True, text=True)
    assert run('backup_pilot.sh').returncode == 0
    return secret, restored, backup, env, run


def test_v2_auth_uses_secret_contents_and_survives_secret_relocation(tmp_path):
    secret, restored, backup, env, run = _case(tmp_path)
    mac = Path(str(backup) + '.mac').read_bytes()
    assert mac.startswith(b'YIKE-BACKUP-MAC-V2\n')
    relocated = tmp_path / 'relocated-secret'
    relocated.write_bytes(secret.read_bytes()); relocated.chmod(0o600)
    env['YIKE_PILOT_BACKUP_PASSPHRASE_FILE'] = str(relocated)
    result = run('restore_pilot.sh')
    assert result.returncode == 0, result.stderr
    assert restored.read_bytes() == b'pilot-dump-fixture'


def test_changed_secret_fails_integrity_before_restore(tmp_path):
    secret, restored, backup, env, run = _case(tmp_path)
    secret.write_text('different-secret\n')
    result = run('restore_pilot.sh')
    assert result.returncode != 0
    assert 'integrity' in result.stderr.lower()
    assert not restored.exists()


def test_legacy_path_mac_is_rejected_even_when_forged_to_match_ciphertext(tmp_path):
    secret, restored, backup, env, run = _case(tmp_path)
    # This is exactly the old publicly derivable key; a valid old ciphertext
    # plus this forged sidecar must not enter decryption or pg_restore.
    Path(str(backup)+'.mac').write_bytes(hmac.new(
        f'file:{secret}'.encode(), backup.read_bytes(), hashlib.sha256).digest())
    result = run('restore_pilot.sh')
    assert result.returncode != 0
    assert 'integrity' in result.stderr.lower()
    assert not restored.exists()


def test_backup_does_not_overwrite_existing_ciphertext_or_sidecar(tmp_path):
    secret, restored, backup, env, run = _case(tmp_path)
    before = (backup.read_bytes(), Path(str(backup)+'.mac').read_bytes())
    assert run('backup_pilot.sh').returncode != 0
    assert before == (backup.read_bytes(), Path(str(backup)+'.mac').read_bytes())


def test_restore_decrypts_verified_private_snapshot_not_changed_original(tmp_path):
    secret, restored, backup, env, run = _case(tmp_path)
    wrapper = tmp_path / 'bin' / 'python3'
    # Mutate only this fixture's original after successful authentication. The
    # restore must use its already-authenticated private ciphertext snapshot.
    wrapper.write_text('#!' + sys.executable + '\nimport os,subprocess,sys\n'
        + 'from pathlib import Path\n'
        + 'code=subprocess.call([' + repr(sys.executable) + ']+sys.argv[1:])\n'
        + 'if code==0 and sys.argv[2]=="verify": Path(os.environ["TEST_ORIGINAL_BACKUP"]).write_bytes(b"changed")\n'
        + 'raise SystemExit(code)\n')
    wrapper.chmod(0o700)
    env['TEST_ORIGINAL_BACKUP'] = str(backup)
    result = run('restore_pilot.sh')
    assert result.returncode == 0, result.stderr
    assert backup.read_bytes() == b'changed'
    assert restored.read_bytes() == b'pilot-dump-fixture'


def _rotating_python_wrapper(path: Path, original_secret: Path) -> None:
    path.write_text(
        '#!' + sys.executable + '\n'
        + 'import os, subprocess, sys\n'
        + 'from pathlib import Path\n'
        + 'code = subprocess.call([' + repr(sys.executable) + '] + sys.argv[1:])\n'
        + 'if code == 0 and len(sys.argv) > 2 and sys.argv[2] == "snapshot":\n'
        + '    Path(os.environ["TEST_ORIGINAL_SECRET"]).write_text("rotated-secret\\n")\n'
        + 'raise SystemExit(code)\n',
        encoding='utf-8',
    )
    path.chmod(0o700)


def test_backup_uses_one_private_secret_snapshot_if_original_rotates(tmp_path):
    secret = _secret_file(tmp_path)
    original = secret.read_bytes()
    restored = tmp_path / 'restored.dump'
    bindir = _fake_pg_tools(tmp_path, restored)
    _rotating_python_wrapper(bindir / 'python3', secret)
    backup = tmp_path / 'pilot.dump.enc'
    env = {
        **os.environ,
        'PATH': f"{bindir}:{os.environ['PATH']}",
        'YIKE_PILOT_ADMIN_DATABASE_URL': 'postgresql://example.invalid/pilot',
        'YIKE_PILOT_BACKUP_PASSPHRASE_FILE': str(secret),
        'TEST_ORIGINAL_SECRET': str(secret),
    }

    created = subprocess.run(
        ['bash', str(ROOT / 'scripts/backup_pilot.sh'), str(backup)],
        env=env, capture_output=True, text=True,
    )
    assert created.returncode == 0, created.stderr
    assert secret.read_text(encoding='utf-8') == 'rotated-secret\n'
    recovery_secret = tmp_path / 'recovery-secret'
    recovery_secret.write_bytes(original)
    recovery_secret.chmod(0o600)
    env['YIKE_PILOT_BACKUP_PASSPHRASE_FILE'] = str(recovery_secret)
    restored_result = subprocess.run(
        ['bash', str(ROOT / 'scripts/restore_pilot.sh'), str(backup)],
        env={**env, 'CONFIRM_RESTORE': 'YES', 'YIKE_RESTORE_TARGET': 'isolated'}, capture_output=True, text=True,
    )
    assert restored_result.returncode == 0, restored_result.stderr
    assert restored.read_bytes() == b'pilot-dump-fixture'


def test_restore_uses_one_private_secret_snapshot_if_original_rotates(tmp_path):
    secret, restored, backup, env, run = _case(tmp_path)
    _rotating_python_wrapper(tmp_path / 'bin' / 'python3', secret)
    env['TEST_ORIGINAL_SECRET'] = str(secret)

    result = run('restore_pilot.sh')

    assert result.returncode == 0, result.stderr
    assert secret.read_text(encoding='utf-8') == 'rotated-secret\n'
    assert restored.read_bytes() == b'pilot-dump-fixture'


def test_backup_exact_publish_rejects_directory_created_after_precheck(tmp_path):
    secret = _secret_file(tmp_path)
    bindir = _fake_pg_tools(tmp_path)
    backup = tmp_path / 'pilot.dump.enc'
    wrapper = bindir / 'python3'
    wrapper.write_text(
        '#!' + sys.executable + '\n'
        + 'import os, subprocess, sys\n'
        + 'from pathlib import Path\n'
        + 'code = subprocess.call([' + repr(sys.executable) + '] + sys.argv[1:])\n'
        + 'if code == 0 and len(sys.argv) > 2 and sys.argv[2] == "create":\n'
        + '    Path(os.environ["TEST_BACKUP_TARGET"]).mkdir()\n'
        + 'raise SystemExit(code)\n',
        encoding='utf-8',
    )
    wrapper.chmod(0o700)
    env = {
        **os.environ,
        'PATH': f"{bindir}:{os.environ['PATH']}",
        'YIKE_PILOT_ADMIN_DATABASE_URL': 'postgresql://example.invalid/pilot',
        'YIKE_PILOT_BACKUP_PASSPHRASE_FILE': str(secret),
        'TEST_BACKUP_TARGET': str(backup),
    }

    result = subprocess.run(
        ['bash', str(ROOT / 'scripts/backup_pilot.sh'), str(backup)],
        env=env, capture_output=True, text=True,
    )

    assert result.returncode != 0
    assert backup.is_dir()
    assert list(backup.iterdir()) == []
    assert not Path(str(backup) + '.mac').exists()


def test_backup_rejects_repository_destination_before_creating_temp_files(tmp_path):
    repo = tmp_path / 'repo'
    scripts = repo / 'scripts'
    scripts.mkdir(parents=True)
    shutil.copy2(ROOT / 'scripts/backup_pilot.sh', scripts)
    shutil.copy2(ROOT / 'scripts/backup_auth.py', scripts)
    secret = _secret_file(tmp_path)
    bindir = _fake_pg_tools(tmp_path)
    backup = repo / 'pilot.dump.enc'
    env = {
        **os.environ,
        'PATH': f"{bindir}:{os.environ['PATH']}",
        'YIKE_PILOT_ADMIN_DATABASE_URL': 'postgresql://example.invalid/pilot',
        'YIKE_PILOT_BACKUP_PASSPHRASE_FILE': str(secret),
    }

    result = subprocess.run(
        ['bash', str(scripts / 'backup_pilot.sh'), str(backup)],
        env=env, capture_output=True, text=True,
    )

    assert result.returncode != 0
    assert not backup.exists()
    assert not list(repo.glob('.yike-backup.*'))


def test_snapshot_helper_rejects_repository_target_without_writing_secret(tmp_path):
    repo = tmp_path / 'repo'
    scripts = repo / 'scripts'
    scripts.mkdir(parents=True)
    helper = scripts / 'backup_auth.py'
    shutil.copy2(ROOT / 'scripts/backup_auth.py', helper)
    secret = _secret_file(tmp_path)
    snapshot = repo / 'passphrase.snapshot'

    result = subprocess.run(
        [sys.executable, str(helper), 'snapshot', str(secret), str(snapshot)],
        capture_output=True, text=True,
    )

    assert result.returncode != 0
    assert not snapshot.exists()
