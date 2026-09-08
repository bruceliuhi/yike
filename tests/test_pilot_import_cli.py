from __future__ import annotations

import json


def test_import_command_requires_explicit_bundle_and_identity(monkeypatch, tmp_path, capsys):
    from pilot import cli

    monkeypatch.delenv("YIKE_PILOT_DATABASE_URL", raising=False)
    monkeypatch.delenv("YIKE_PILOT_AUTH_SECRET", raising=False)
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps({"review_status": "APPROVED", "bundle_id": "b1", "leads": []}), encoding="utf-8")

    assert cli.import_bundle(["--bundle", str(bundle_path), "--user-id", "u1", "--profile-version-id", "p1"]) == 2
    assert "YIKE_PILOT_DATABASE_URL" in capsys.readouterr().err


def test_import_command_prints_created_and_duplicate_counts(monkeypatch, tmp_path, capsys):
    from pilot import cli

    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps({"review_status": "APPROVED", "bundle_id": "b1", "leads": []}), encoding="utf-8")

    class FakeDatabase:
        def migrate(self):
            pass

    class FakeStore:
        def __init__(self, database):
            assert isinstance(database, FakeDatabase)

    monkeypatch.setenv("YIKE_PILOT_DATABASE_URL", "postgresql://example")
    monkeypatch.setattr(cli.PilotDatabase, "from_environment", lambda: FakeDatabase())
    monkeypatch.setattr(cli, "PilotStore", FakeStore)
    monkeypatch.setattr(cli, "import_reviewed_bundle", lambda store, user_id, profile_version_id, bundle: [{"created": True}, {"created": False}])

    assert cli.import_bundle(["--bundle", str(bundle_path), "--user-id", "u1", "--profile-version-id", "p1"]) == 0
    assert json.loads(capsys.readouterr().out) == {"bundle_id": "b1", "created": 1, "duplicates": 1, "total": 2}
