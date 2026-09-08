from __future__ import annotations

import json


def test_provision_tenant_is_trusted_cli_only(monkeypatch, capsys):
    from pilot import cli

    class FakeDatabase:
        def migrate(self):
            pass

    class FakeStore:
        def __init__(self, database):
            self.database = database

        def provision_tenant(self, name):
            assert name == "试用团队"
            return "tenant-1"

    monkeypatch.setenv("YIKE_PILOT_DATABASE_URL", "postgresql://example")
    monkeypatch.setattr(cli.PilotDatabase, "from_environment", lambda: FakeDatabase())
    monkeypatch.setattr(cli, "PilotStore", FakeStore)

    assert cli.provision(["tenant", "--name", "试用团队"]) == 0
    assert json.loads(capsys.readouterr().out) == {"tenant_id": "tenant-1"}


def test_provision_user_requires_explicit_tenant(monkeypatch, capsys):
    from pilot import cli

    monkeypatch.delenv("YIKE_PILOT_DATABASE_URL", raising=False)
    assert cli.provision(["user", "--tenant-id", "tenant-1", "--email", "a@example.com"]) == 2
    assert "YIKE_PILOT_DATABASE_URL" in capsys.readouterr().err
