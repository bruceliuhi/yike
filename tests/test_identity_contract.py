from pathlib import Path

import pytest

from pilot.identity import IdentityValidationError, validate_connection_input, validate_execution_event
from pilot.store import PilotStore
from pilot.ui_api import register_ui_api


MIGRATION = Path(__file__).parents[1] / "migrations" / "104_v02_identity_execution.sql"


def test_identity_migration_contains_tenant_scoped_device_connection_and_events():
    sql = MIGRATION.read_text(encoding="utf-8")
    for marker in (
        "CREATE TABLE IF NOT EXISTS pilot_devices",
        "CREATE TABLE IF NOT EXISTS pilot_platform_connections",
        "CREATE TABLE IF NOT EXISTS pilot_execution_events",
        "ENABLE ROW LEVEL SECURITY",
        "FORCE ROW LEVEL SECURITY",
        "session_ref TEXT NOT NULL",
        "execution_generation BIGINT NOT NULL",
        "pilot_tenant_scope",
    ):
        assert marker in sql


def test_connection_input_rejects_credentials_and_unknown_platforms():
    with pytest.raises(IdentityValidationError):
        validate_connection_input("unknown", "device-1", "acct", "vault://ref")
    with pytest.raises(IdentityValidationError):
        validate_connection_input("BILIBILI", "device-1", "acct", "token=secret")


def test_connection_input_accepts_opaque_vault_reference():
    assert validate_connection_input("BILIBILI", "device-1", "public-account", "vault://tenant/device/bili") == {
        "platform": "BILIBILI",
        "device_id": "device-1",
        "account_public_id": "public-account",
        "session_ref": "vault://tenant/device/bili",
    }


def test_execution_event_requires_positive_generation_and_safe_event_type():
    with pytest.raises(IdentityValidationError):
        validate_execution_event("started", 0, {})
    with pytest.raises(IdentityValidationError):
        validate_execution_event("cookie_dump", 1, {})
    with pytest.raises(IdentityValidationError):
        validate_execution_event("COLLECTION_PROGRESS", 1, {"token": "never-store"})
    assert validate_execution_event("COLLECTION_STARTED", 2, {"query": "agent"})["execution_generation"] == 2


def test_store_exposes_tenant_scoped_identity_operations():
    for name in ("register_device", "revoke_device", "connect_platform", "disconnect_platform", "append_execution_event"):
        assert hasattr(PilotStore, name)


def test_ui_api_exposes_identity_routes():
    from fastapi import FastAPI

    app = FastAPI()
    register_ui_api(app, object(), auth_secret="secret", dev_login=True)
    paths = {route.path for route in app.routes}
    assert {"/api/ui/devices", "/api/ui/connections", "/api/ui/execution-events"} <= paths
