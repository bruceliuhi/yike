"""Focused contract and dedicated real PostgreSQL monitor plan checks."""
from datetime import timedelta
import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
import pytest
from pydantic import ValidationError
from psycopg import sql

from pilot.monitor_contract import CreateMonitorPlanRequest, SetMonitorPlanStateRequest
from pilot.auth import issue_token, verify_token_claims
from pilot.db import PilotDatabase
from pilot.monitor_plans import MonitorPlanStore
from pilot.research_strategies import ResearchStrategyStore
from pilot.store import PilotStore

ROOT = Path(__file__).parents[1]
SECRET = "synthetic-monitor-test"


def create_body(**changes):
    return dict(schema_version="monitor-plans-v1", request_id=str(uuid4()),
                profile_version_id=str(uuid4()), strategy_version_id=str(uuid4()),
                human_confirmed=True) | changes


@pytest.mark.parametrize("field,value", [
    ("human_confirmed", 1), ("human_confirmed", False),
    ("schema_version", "monitor-plans"), ("request_id", "bad"),
])
def test_create_contract_is_strict(field, value):
    with pytest.raises(ValidationError):
        CreateMonitorPlanRequest.model_validate(create_body(**{field: value}))


def test_forged_create_instance_is_revalidated():
    valid = CreateMonitorPlanRequest.model_validate(create_body())
    forged = valid.model_copy(update={"human_confirmed": 1})
    with pytest.raises(ValidationError):
        CreateMonitorPlanRequest.model_validate(forged)
    with pytest.raises(ValidationError):
        CreateMonitorPlanRequest.model_validate(valid.model_copy(update={"unexpected": True}))


@pytest.mark.parametrize("field,value", [
    ("expected_revision", True), ("expected_revision", 0),
    ("human_confirmed", 1), ("state", "STOPPED"), ("plan_id", "bad"),
])
def test_state_contract_is_strict(field, value):
    body = dict(schema_version="monitor-plans-v1", request_id=str(uuid4()),
                plan_id=str(uuid4()), expected_revision=1, state="PAUSED", human_confirmed=True)
    with pytest.raises(ValidationError):
        SetMonitorPlanStateRequest.model_validate(body | {field: value})


def test_error_status_is_fixed():
    from pilot.monitor_contract import MonitorPlanError
    assert (MonitorPlanError("plan_not_found", 200).code,
            MonitorPlanError("plan_not_found", 200).status) == ("plan_not_found", 404)
    assert (MonitorPlanError("secret", 200).code,
            MonitorPlanError("secret", 200).status) == ("monitor_store_unavailable", 503)


@pytest.fixture(scope="module")
def pg():
    url = os.environ.get("YIKE_MONITOR_TEST_DATABASE_URL")
    if not url:
        pytest.skip("dedicated monitor PostgreSQL required")
    parsed = urlsplit(url)
    assert parsed.hostname == "127.0.0.1" and parsed.path == "/yike_monitor_test"
    admin = PilotDatabase(url)
    admin.migrate()
    role, password = "monitor_app", "synthetic-monitor-app"
    with admin.connect() as conn:
        conn.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
        conn.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB PASSWORD {}")
                     .format(sql.Identifier(role), sql.Literal(password)))
        conn.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
        conn.execute(sql.SQL("GRANT SELECT ON pilot_users,business_profiles,business_profile_versions TO {}").format(sql.Identifier(role)))
        conn.execute(sql.SQL("GRANT UPDATE(name) ON business_profiles TO {}").format(sql.Identifier(role)))
        conn.execute(sql.SQL("GRANT UPDATE(status) ON business_profile_versions TO {}").format(sql.Identifier(role)))
        conn.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
        for name in ("grant_session_revocations.sql", "grant_research_strategies.sql", "grant_monitor_plans.sql"):
            conn.execute((ROOT / "deploy" / name).read_text())
    app_url = urlunsplit((parsed.scheme, f"{role}:{password}@{parsed.hostname}:{parsed.port}", parsed.path, "", ""))
    yield admin, PilotDatabase(app_url)
    with admin.connect() as conn:
        conn.execute("DROP OWNED BY monitor_app")
        conn.execute("DROP ROLE monitor_app")


@pytest.fixture
def monitor_env(pg, monkeypatch):
    admin, app = pg
    provisioner = PilotStore(admin)
    tenant = provisioner.provision_tenant("synthetic-monitor")
    user = provisioner.provision_user(tenant, f"{uuid4()}@example.invalid")
    profile = provisioner.save_profile(user, {"description": "设备采购需求监控"})
    provisioner.confirm_profile(user, profile["version_id"])
    claims = verify_token_claims(issue_token(user, SECRET), SECRET)
    strategies = ResearchStrategyStore(app)
    schedule = dict(kind="daily", times=["09:00"], interval=1, start="09:00", end="18:00",
                    timezone="UTC", policyVersion=1)
    config = dict(schema_version="research-strategy-v1", name="监控", source="search",
                  keywords=["设备采购"], exclusions=[], links=[], mode="monitor", schedule=schedule, research=None)
    prepared = strategies.prepare(claims, dict(schema_version="strategy-confirmation-v1", request_id=str(uuid4()),
        draft_id=str(uuid4()), draft_revision=1, profile_version_id=profile["version_id"], configuration=config,
        platforms=["PUBLIC_WEB"], max_records=10, max_runtime_seconds=600))
    confirmed = strategies.confirm(claims, dict(schema_version="strategy-confirmation-v1", request_id=str(uuid4()),
        strategy_version_id=prepared["strategy_version_id"], configuration_sha256=prepared["configuration_sha256"], human_confirmed=True))
    # This store slice only verifies DB time is passed and strict-future output is persisted;
    # calendar semantics have their own root-owned tests.
    import pilot.monitor_calendar as calendar
    monkeypatch.setattr(calendar, "next_occurrence", lambda schedule, *, after: after + timedelta(hours=1))
    return SimpleNamespace(admin=admin, app=app, claims=claims, profile=profile["version_id"],
        strategy=confirmed, strategies=strategies,
        store=MonitorPlanStore(app, strategy_resolver=strategies.resolve))


def monitor_body(env, **changes):
    return create_body(profile_version_id=env.profile,
        strategy_version_id=env.strategy["strategy_version_id"], **changes)


def test_create_survives_restart_replays_and_conflicts(monitor_env):
    env = monitor_env
    body = monitor_body(env)
    receipt = env.store.create(env.claims, body)
    assert receipt["plan"]["plan_id"] == body["request_id"]
    assert receipt["plan"]["execution_status"] == "NOT_CONNECTED"
    restarted = MonitorPlanStore(env.app, strategy_resolver=env.strategies.resolve)
    assert restarted.create(env.claims, body) == receipt
    assert restarted.get_receipt(env.claims, body["request_id"]) == receipt
    from pilot.monitor_contract import MonitorPlanError
    with pytest.raises(MonitorPlanError, match="request_conflict"):
        restarted.create(env.claims, body | {"profile_version_id": str(uuid4())})


def test_pause_resume_cas_and_revoked_strategy_fence(monitor_env):
    env = monitor_env
    created = env.store.create(env.claims, monitor_body(env))
    plan = created["plan"]
    pause = dict(schema_version="monitor-plans-v1", request_id=str(uuid4()), plan_id=plan["plan_id"],
                 expected_revision=1, state="PAUSED", human_confirmed=True)
    paused = env.store.set_state(env.claims, pause)["plan"]
    assert paused["revision"] == 2 and paused["next_due_at"] is None
    from pilot.monitor_contract import MonitorPlanError
    with pytest.raises(MonitorPlanError, match="plan_conflict"):
        env.store.set_state(env.claims, pause | {"request_id": str(uuid4())})
    env.strategies.revoke(env.claims, dict(schema_version="strategy-confirmation-v1", request_id=str(uuid4()),
        strategy_version_id=env.strategy["strategy_version_id"]))
    with pytest.raises(MonitorPlanError, match="strategy_conflict"):
        env.store.set_state(env.claims, pause | {"request_id": str(uuid4()), "expected_revision": 2, "state": "ACTIVE"})
    assert env.store.list(env.claims)["plans"][0]["state"] == "PAUSED"


def test_owner_tenant_and_session_are_fail_closed(monitor_env):
    env = monitor_env
    env.store.create(env.claims, monitor_body(env))
    provisioner = PilotStore(env.admin)
    other_tenant = provisioner.provision_tenant("synthetic-monitor-other")
    other_user = provisioner.provision_user(other_tenant, f"{uuid4()}@example.invalid")
    other_claims = verify_token_claims(issue_token(other_user, SECRET), SECRET)
    assert env.store.list(other_claims)["plans"] == []
    from pilot.auth import TokenClaims
    from pilot.monitor_contract import MonitorPlanError
    forged = TokenClaims(env.claims.user_id, env.claims.expires_at, "x" * 64)
    with pytest.raises(MonitorPlanError, match="invalid_session"):
        env.store.list(forged)


@pytest.mark.parametrize("mode,version", [("once", 1), ("monitor", None)])
def test_create_rejects_once_and_unversioned_schedule(monitor_env, mode, version):
    env = monitor_env
    schedule = dict(kind="daily", times=["09:00"], interval=1, start="09:00", end="18:00", timezone="UTC")
    if version is not None:
        schedule["policyVersion"] = version
    config = dict(schema_version="research-strategy-v1", name="不支持的日程", source="search",
                  keywords=["设备"], exclusions=[], links=[], mode=mode, schedule=schedule, research=None)
    prepared = env.strategies.prepare(env.claims, dict(schema_version="strategy-confirmation-v1", request_id=str(uuid4()),
        draft_id=str(uuid4()), draft_revision=1, profile_version_id=env.profile, configuration=config,
        platforms=["PUBLIC_WEB"], max_records=10, max_runtime_seconds=600))
    confirmed = env.strategies.confirm(env.claims, dict(schema_version="strategy-confirmation-v1", request_id=str(uuid4()),
        strategy_version_id=prepared["strategy_version_id"], configuration_sha256=prepared["configuration_sha256"], human_confirmed=True))
    body = create_body(profile_version_id=env.profile, strategy_version_id=confirmed["strategy_version_id"])
    from pilot.monitor_contract import MonitorPlanError
    with pytest.raises(MonitorPlanError, match="unsupported_schedule"):
        env.store.create(env.claims, body)
