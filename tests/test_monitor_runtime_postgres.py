"""Focused monitor-runtime contract checks; PostgreSQL scenarios use their own DB."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from psycopg import sql
from nacl.signing import SigningKey

from pilot.auth import issue_token, verify_token_claims
from pilot.db import PilotDatabase
from pilot.device_credentials import DeviceCredentialStore
from pilot.execution_contract import ExecutionRuntimeError
from pilot.execution_contract import ExecutionOperation
from pilot.execution_runtime import ExecutionRuntime, execution_signing_payload
from pilot.monitor_plans import MonitorPlanStore
from pilot.monitor_runtime import MonitorRuntime
from pilot.monitor_runtime_contract import MonitorPulseRequest
from pilot.research_strategies import ResearchStrategyStore
from pilot.store import PilotStore
from tests.test_device_credentials_postgres import RoleDatabase, bind, wait_for_lock
from tests.test_device_keys import encoded


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


@pytest.fixture(scope="module")
def runtime_databases():
    url = os.environ.get("YIKE_MONITOR_RUNTIME_TEST_DATABASE_URL")
    if not url:
        pytest.skip("dedicated monitor runtime PostgreSQL required")
    admin = PilotDatabase(url)
    admin.migrate()
    role = "monitor_behavior_" + uuid4().hex
    root = Path(__file__).parents[1]
    with admin.connect() as connection:
        connection.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB")
                           .format(sql.Identifier(role)))
        connection.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}") .format(sql.Identifier(role)))
        connection.execute(sql.SQL("GRANT SELECT ON pilot_users,business_profiles,business_profile_versions TO {}")
                           .format(sql.Identifier(role)))
        connection.execute(sql.SQL("GRANT UPDATE(name) ON business_profiles TO {}") .format(sql.Identifier(role)))
        connection.execute(sql.SQL("GRANT UPDATE(status) ON business_profile_versions TO {}") .format(sql.Identifier(role)))
        connection.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
        for filename in ("grant_session_revocations.sql", "grant_device_credentials.sql",
                         "grant_connection_operations.sql", "grant_execution_runtime.sql",
                         "grant_research_strategies.sql", "grant_monitor_plans.sql",
                         "grant_monitor_runtime.sql", "grant_research_execution.sql"):
            connection.execute((root / "deploy" / filename).read_text())
    yield admin, RoleDatabase(admin, role)
    with admin.connect() as connection:
        connection.execute(sql.SQL("DROP OWNED BY {}") .format(sql.Identifier(role)))
        connection.execute(sql.SQL("DROP ROLE {}") .format(sql.Identifier(role)))


@pytest.fixture
def runtime_env(runtime_databases):
    admin, database = runtime_databases
    provisioner = PilotStore(admin)
    tenant = provisioner.provision_tenant("synthetic-monitor-runtime")
    user = provisioner.provision_user(tenant, f"{uuid4()}@example.invalid")
    claims = verify_token_claims(issue_token(user, "synthetic-monitor-runtime"), "synthetic-monitor-runtime")
    store = PilotStore(database)
    device = store.register_device(user, "synthetic-monitor-runtime")["device_id"]
    key = SigningKey.generate()
    bind(SimpleNamespace(service=DeviceCredentialStore(database), claims=claims, device=device), key)
    connection = store.connect_platform(user, "BILIBILI", device, "synthetic-account", "vault://synthetic")
    with admin.connect() as conn:
        conn.execute("UPDATE pilot_platform_connections SET status='CONNECTED' WHERE connection_id=%s",
                     (connection["connection_id"],))
        connection["connection_version"] = conn.execute(
            "SELECT connection_version FROM pilot_platform_connections WHERE connection_id=%s",
            (connection["connection_id"],)).fetchone()[0]
    profile = provisioner.save_profile(user, {"description": "真实数据库中的合成监控契约"})
    provisioner.confirm_profile(user, profile["version_id"])
    schedule = dict(kind="interval", times=[], interval=1, start="00:00", end="23:59",
                    timezone="UTC", policyVersion=1)
    configuration = dict(schema_version="research-strategy-v1", name="监控策略", source="search",
                         keywords=["设备采购"], exclusions=[], links=[], mode="monitor",
                         schedule=schedule, research=None)
    strategies = ResearchStrategyStore(database)
    prepared = strategies.prepare(claims, dict(schema_version="strategy-confirmation-v1",
        request_id=str(uuid4()), draft_id=str(uuid4()), draft_revision=1,
        profile_version_id=profile["version_id"], configuration=configuration,
        platforms=["BILIBILI"], max_records=10, max_runtime_seconds=600))
    strategy = strategies.confirm(claims, dict(schema_version="strategy-confirmation-v1",
        request_id=str(uuid4()), strategy_version_id=prepared["strategy_version_id"],
        configuration_sha256=prepared["configuration_sha256"], human_confirmed=True))
    plans = MonitorPlanStore(database, strategy_resolver=strategies.resolve)
    plan = plans.create(claims, dict(schema_version="monitor-plans-v1", request_id=str(uuid4()),
        profile_version_id=profile["version_id"], strategy_version_id=strategy["strategy_version_id"],
        human_confirmed=True))["plan"]
    policy = lambda platform, access_mode, config: (
        platform in ("XIAOHONGSHU", "DOUYIN", "BILIBILI")
        and access_mode == "PLATFORM_ACCOUNT" and config.get("mode") == "monitor"
        and config.get("schedule", {}).get("policyVersion") == 1)
    execution = ExecutionRuntime(database, strategy_resolver=strategies.resolve, capability_check=policy)
    monitor = MonitorRuntime(database, execution)
    execution.monitor_runtime = monitor
    target = dict(platform="BILIBILI", access_mode="PLATFORM_ACCOUNT",
                  connection_id=connection["connection_id"], connection_version=connection["connection_version"])
    yield SimpleNamespace(admin=admin, database=database, tenant=tenant, user=user, claims=claims,
        device=device, key=key, profile=profile["version_id"], strategy=strategy,
        plan=plan, plans=plans, execution=execution, monitor=monitor, target=target)
    # This database is disposable and root owns its lifecycle. Immutable audit
    # rows deliberately are not weakened for fixture cleanup.


def runtime_pulse(env, **changes):
    return dict(schema_version="monitor-runtime-v1", plan_id=env.plan["plan_id"],
                device_id=env.device, monitor_session_id=str(uuid4()), credential_version=1,
                targets=[env.target]) | changes


def force_due_window(env):
    with env.admin.connect() as connection:
        connection.execute("UPDATE pilot_monitor_bindings SET last_seen_at=clock_timestamp()-interval '30 seconds' "
                           "WHERE tenant_id=%s AND plan_id=%s", (env.tenant, env.plan["plan_id"]))
        connection.execute("UPDATE pilot_monitor_plans SET next_due_at=clock_timestamp()-interval '10 seconds' "
                           "WHERE tenant_id=%s AND plan_id=%s", (env.tenant, env.plan["plan_id"]))


def sign_apply(env, body):
    operation = ExecutionOperation.model_validate(body)
    signature = encoded(env.key.sign(execution_signing_payload(
        tenant_id=env.tenant, claims=env.claims, operation=operation).encode()).signature)
    return env.execution.apply(env.claims, operation, signature)


def test_real_pg_offline_then_concurrent_reservation_and_restart_recovery(runtime_env):
    env = runtime_env
    session = str(uuid4())
    with env.admin.connect() as connection:
        connection.execute("UPDATE pilot_monitor_plans SET next_due_at=clock_timestamp()-interval '10 seconds' "
                           "WHERE tenant_id=%s AND plan_id=%s", (env.tenant, env.plan["plan_id"]))
    first = env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    assert first["state"] == "SKIPPED_OFFLINE" and first["occurrence"] is None
    force_due_window(env)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: env.monitor.pulse(
            env.claims, runtime_pulse(env, monitor_session_id=session)), range(2)))
    assert results[0]["state"] == results[1]["state"] == "READY"
    assert results[0]["occurrence"] == results[1]["occurrence"]
    assert results[0]["occurrence"]["task_id"] is None
    assert results[0]["occurrence"]["start_request"] == ExecutionOperation.model_validate(
        results[0]["occurrence"]["start_request"]).model_dump(mode="json")
    recovered = env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=str(uuid4())))
    assert recovered["state"] == "RECOVERY_REQUIRED"
    with pytest.raises(ExecutionRuntimeError, match="monitor_binding_conflict"):
        env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session,
            credential_version=2))


def test_real_pg_reserved_start_claim_and_pause_fence(runtime_env):
    env = runtime_env
    session = str(uuid4())
    env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    force_due_window(env)
    ready = env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    begun = sign_apply(env, ready["occurrence"]["start_request"])
    running = env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    assert running["state"] == "RUNNING" and running["occurrence"]["task_id"] == begun["task_id"]
    claim = dict(schema_version="execution-runtime-v1", request_id=str(uuid4()), operation="CLAIM",
                 device_id=env.device, credential_version=1, profile_version_id=None,
                 strategy_version_id=None, configuration_sha256=None, targets=None,
                 task_id=begun["task_id"], platform_run_id=begun["platform_runs"][0]["platform_run_id"],
                 lease_id=None, execution_generation=None)
    leased = sign_apply(env, claim)
    assert leased["status"] == "RUNNING" and leased["execution_generation"] == 1
    env.plans.set_state(env.claims, dict(schema_version="monitor-plans-v1", request_id=str(uuid4()),
        plan_id=env.plan["plan_id"], expected_revision=1, state="PAUSED", human_confirmed=True))
    renew = claim | dict(request_id=str(uuid4()), operation="RENEW", lease_id=leased["lease_id"],
                         execution_generation=leased["execution_generation"])
    with pytest.raises(ExecutionRuntimeError, match="monitor_plan_inactive"):
        sign_apply(env, renew)


def test_real_pg_unreserved_and_expired_monitor_start_are_rejected(runtime_env, monkeypatch):
    env = runtime_env
    session = str(uuid4())
    env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    force_due_window(env)
    ready = env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    forged = ready["occurrence"]["start_request"] | {"request_id": str(uuid4())}
    with pytest.raises(ExecutionRuntimeError, match="monitor_occurrence_required"):
        sign_apply(env, forged)
    def expired_now(cursor):
        cursor.execute("SELECT clock_timestamp()+interval '120 seconds'")
        return cursor.fetchone()[0]
    monkeypatch.setattr(env.execution, "_now", expired_now)
    with pytest.raises(ExecutionRuntimeError, match="monitor_occurrence_expired"):
        sign_apply(env, ready["occurrence"]["start_request"])


def begin_and_claim(env, session):
    env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    force_due_window(env)
    ready = env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    begun = sign_apply(env, ready["occurrence"]["start_request"])
    claim = dict(schema_version="execution-runtime-v1", request_id=str(uuid4()), operation="CLAIM",
                 device_id=env.device, credential_version=1, profile_version_id=None,
                 strategy_version_id=None, configuration_sha256=None, targets=None,
                 task_id=begun["task_id"], platform_run_id=begun["platform_runs"][0]["platform_run_id"],
                 lease_id=None, execution_generation=None)
    return begun, claim, sign_apply(env, claim)


def test_real_pg_inflight_renew_holds_plan_share_lock_against_other_session_pause(runtime_env, monkeypatch):
    env = runtime_env
    session = str(uuid4())
    _, claim, leased = begin_and_claim(env, session)
    renew = claim | dict(request_id=str(uuid4()), operation="RENEW", lease_id=leased["lease_id"],
                         execution_generation=leased["execution_generation"])
    other_claims = verify_token_claims(issue_token(env.user, "synthetic-monitor-runtime"),
                                       "synthetic-monitor-runtime")
    guarded, release = Event(), Event()
    original = env.monitor.guard_task

    def guarded_task(*args):
        original(*args)
        guarded.set()
        assert release.wait(3)

    monkeypatch.setattr(env.monitor, "guard_task", guarded_task)
    pause = dict(schema_version="monitor-plans-v1", request_id=str(uuid4()),
                 plan_id=env.plan["plan_id"], expected_revision=1,
                 state="PAUSED", human_confirmed=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        renewing = pool.submit(sign_apply, env, renew)
        assert guarded.wait(3)
        pausing = pool.submit(env.plans.set_state, other_claims, pause)
        try:
            wait_for_lock(env.admin, "pilot_monitor_plans WHERE tenant_id=")
            assert not pausing.done()
        finally:
            release.set()
        assert renewing.result(timeout=3)["status"] == "RUNNING"
        assert pausing.result(timeout=3)["plan"]["state"] == "PAUSED"


def test_real_pg_busy_pulse_refreshes_seen_and_skips_due_before_cancel(runtime_env):
    env = runtime_env
    session = str(uuid4())
    env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    force_due_window(env)
    ready = env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    begun = sign_apply(env, ready["occurrence"]["start_request"])
    force_due_window(env)
    busy = env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    assert busy["state"] == "RUNNING"
    with env.admin.connect() as connection:
        seen, due = connection.execute(
            "SELECT b.last_seen_at,p.next_due_at FROM pilot_monitor_bindings b "
            "JOIN pilot_monitor_plans p USING(tenant_id,owner_user_id,plan_id) "
            "WHERE b.tenant_id=%s AND b.plan_id=%s AND b.plan_revision=1",
            (env.tenant, env.plan["plan_id"])).fetchone()
        now = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    assert now - seen < timedelta(seconds=5) and due > now
    cancel = dict(schema_version="execution-runtime-v1", request_id=str(uuid4()), operation="CANCEL",
                  device_id=env.device, credential_version=1, profile_version_id=None,
                  strategy_version_id=None, configuration_sha256=None, targets=None,
                  task_id=begun["task_id"], platform_run_id=None, lease_id=None,
                  execution_generation=None)
    assert sign_apply(env, cancel)["status"] == "CANCELED"
    after = env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    assert after["state"] == "WAITING" and after["occurrence"] is None


def test_real_pg_old_revision_pending_is_recovery_not_ready(runtime_env):
    env = runtime_env
    session = str(uuid4())
    env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    force_due_window(env)
    original = env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    pause = env.plans.set_state(env.claims, dict(schema_version="monitor-plans-v1", request_id=str(uuid4()),
        plan_id=env.plan["plan_id"], expected_revision=1, state="PAUSED", human_confirmed=True))["plan"]
    env.plans.set_state(env.claims, dict(schema_version="monitor-plans-v1", request_id=str(uuid4()),
        plan_id=env.plan["plan_id"], expected_revision=pause["revision"], state="ACTIVE", human_confirmed=True))
    recovered = env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    assert recovered["state"] == "RECOVERY_REQUIRED"
    assert recovered["occurrence"]["start_request"] == original["occurrence"]["start_request"]


def test_real_pg_start_plan_lock_is_nowait_busy(runtime_env):
    env = runtime_env
    session = str(uuid4())
    env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    force_due_window(env)
    ready = env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    with env.admin.connect() as blocker:
        blocker.execute("SELECT 1 FROM pilot_monitor_plans WHERE tenant_id=%s AND plan_id=%s FOR UPDATE",
                        (env.tenant, env.plan["plan_id"]))
        with pytest.raises(ExecutionRuntimeError, match="monitor_plan_busy"):
            sign_apply(env, ready["occurrence"]["start_request"])


def test_real_pg_client_capacity_skips_without_reservation_or_catchup(runtime_env):
    env = runtime_env
    session = str(uuid4())
    env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    force_due_window(env)
    busy = env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session, can_start=False))
    assert busy['state'] == 'SKIPPED_BUSY' and busy['occurrence'] is None
    with env.admin.connect() as connection:
        assert connection.execute('SELECT count(*) FROM pilot_monitor_occurrences WHERE plan_id=%s',
                                  (env.plan['plan_id'],)).fetchone() == (0,)
        seen = connection.execute('SELECT last_seen_at FROM pilot_monitor_bindings WHERE plan_id=%s',
                                  (env.plan['plan_id'],)).fetchone()[0]
        assert connection.execute('SELECT clock_timestamp()').fetchone()[0] - seen < timedelta(seconds=5)
    free = env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session, can_start=True))
    assert free['state'] == 'WAITING' and free['occurrence'] is None
    force_due_window(env)
    ready = env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session, can_start=True))
    assert ready['state'] == 'READY'
    retained = env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session, can_start=False))
    assert retained['occurrence'] == ready['occurrence']


def test_real_pg_support_requires_explicit_monitor_deployment_policy(runtime_env):
    from pilot.foreground_collection import three_platform_collection_policy, three_platform_monitor_policy
    env = runtime_env
    env.execution.capability_check = three_platform_collection_policy
    assert env.monitor.support(env.claims)['mode'] is None
    env.execution.capability_check = three_platform_monitor_policy
    assert env.monitor.support(env.claims) == {
        'schema_version': 'monitor-runtime-support-v1', 'mode': 'three-platform-monitor-v1'}
