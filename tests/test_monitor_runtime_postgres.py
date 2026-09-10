"""Focused monitor-runtime contract checks; PostgreSQL scenarios use their own DB."""
import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from pydantic import ValidationError
from psycopg import sql

from pilot.db import PilotDatabase
from pilot.execution_contract import ExecutionRuntimeError
from pilot.execution_runtime import ExecutionRuntime
from pilot.monitor_runtime_contract import MonitorPulseRequest


def pulse_body(**changes):
    return dict(
        schema_version="monitor-runtime-v1",
        plan_id=str(uuid4()),
        device_id=str(uuid4()),
        monitor_session_id=str(uuid4()),
        credential_version=1,
        targets=[dict(platform="PUBLIC_WEB", access_mode="PUBLIC_ANONYMOUS",
                      connection_id=None, connection_version=None)],
    ) | changes


@pytest.mark.parametrize("change", [
    {"schema_version": "monitor-runtime"},
    {"plan_id": "bad"},
    {"monitor_session_id": "BAD"},
    {"credential_version": True},
    {"credential_version": 0},
    {"targets": []},
    {"targets": [dict(platform="PUBLIC_WEB", access_mode="PUBLIC_ANONYMOUS",
                      connection_id=None, connection_version=None)] * 2},
    {"server_time": "2026-09-11T00:00:00Z"},
    {"human_confirmed": True},
])
def test_pulse_contract_is_strict(change):
    with pytest.raises((ValidationError, ValueError, ExecutionRuntimeError)):
        MonitorPulseRequest.model_validate(pulse_body(**change))


def test_execution_runtime_monitor_hook_defaults_to_none():
    runtime = ExecutionRuntime(object())
    assert runtime.monitor_runtime is None


def test_migration_forces_owner_rls_and_grant_preserves_immutable_columns():
    url = os.environ.get("YIKE_MONITOR_RUNTIME_TEST_DATABASE_URL")
    if not url:
        pytest.skip("dedicated monitor runtime PostgreSQL required")
    database = PilotDatabase(url)
    database.migrate()
    role = "monitor_runtime_" + uuid4().hex
    root = Path(__file__).parents[1]
    with database.connect() as connection:
        connection.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB")
                           .format(sql.Identifier(role)))
        connection.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
        connection.execute((root / "deploy" / "grant_monitor_runtime.sql").read_text())
        rows = connection.execute("SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class "
                                  "WHERE relname IN ('pilot_monitor_bindings','pilot_monitor_occurrences') ORDER BY relname").fetchall()
        assert rows == [("pilot_monitor_bindings", True, True),
                        ("pilot_monitor_occurrences", True, True)]
        assert connection.execute("SELECT has_column_privilege(%s,'pilot_monitor_bindings','device_id','UPDATE')", (role,)).fetchone() == (False,)
        assert connection.execute("SELECT has_column_privilege(%s,'pilot_monitor_bindings','last_seen_at','UPDATE')", (role,)).fetchone() == (True,)
        assert connection.execute("SELECT has_column_privilege(%s,'pilot_monitor_occurrences','start_request','UPDATE')", (role,)).fetchone() == (False,)
        assert connection.execute("SELECT has_column_privilege(%s,'pilot_monitor_occurrences','status','UPDATE')", (role,)).fetchone() == (True,)
        connection.execute(sql.SQL("DROP OWNED BY {}") .format(sql.Identifier(role)))
        connection.execute(sql.SQL("DROP ROLE {}") .format(sql.Identifier(role)))
