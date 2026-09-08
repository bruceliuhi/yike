from __future__ import annotations

import json

import pytest


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


def test_web_start_does_not_run_migrations_as_app_role(monkeypatch):
    from pilot import cli

    class FakeDatabase:
        def migrate(self):
            raise AssertionError("web process must not run privileged migrations")

    class FakeStore:
        def __init__(self, database):
            self.database = database

    called = {}
    monkeypatch.setenv("YIKE_PILOT_DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("YIKE_PILOT_AUTH_SECRET", "test-secret")
    monkeypatch.setattr(cli.PilotDatabase, "from_environment", lambda: FakeDatabase())
    monkeypatch.setattr(cli, "PilotStore", FakeStore)
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kwargs: called.update(kwargs))

    cli.web()
    assert called["access_log"] is False
    assert called["proxy_headers"] is False
    assert called["forwarded_allow_ips"] == ""


def test_migrate_command_is_available_for_trusted_admin(monkeypatch):
    from pilot import cli

    class FakeDatabase:
        def __init__(self):
            self.migrated = False

        def migrate(self):
            self.migrated = True

    database = FakeDatabase()
    monkeypatch.setattr(cli.PilotDatabase, "from_environment", lambda: database)
    assert cli.migrate([]) == 0
    assert database.migrated is True


def test_web_rejects_wildcard_forwarded_proxy_allowlist(monkeypatch):
    from pilot import cli

    class FakeDatabase:
        pass

    monkeypatch.setenv("YIKE_PILOT_DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("YIKE_PILOT_AUTH_SECRET", "test-secret")
    monkeypatch.setenv("YIKE_PILOT_PROXY_HEADERS", "1")
    monkeypatch.setenv("YIKE_PILOT_FORWARDED_ALLOW_IPS", "10.0.0.1, *")
    monkeypatch.setattr(cli.PilotDatabase, "from_environment", lambda: FakeDatabase())
    monkeypatch.setattr(cli, "PilotStore", lambda database: type("Store", (), {"database": database})())
    with pytest.raises(RuntimeError, match="must not contain wildcard"):
        cli.web()
