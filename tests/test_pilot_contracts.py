from concurrent.futures import ThreadPoolExecutor
import inspect
import os
from pathlib import Path
from threading import Barrier

import pytest

from pilot.db import PilotDatabase, MissingDatabaseConfiguration
from pilot.store import PilotStore


MIGRATIONS = tuple(Path(__file__).parents[1].glob("migrations/10*_customer_pilot*.sql"))


def test_migration_declares_tenant_scope_and_profile_history():
    sql = "\n".join(path.read_text(encoding="utf-8") for path in MIGRATIONS)
    for marker in (
        "CREATE TABLE IF NOT EXISTS pilot_tenants",
        "CREATE TABLE IF NOT EXISTS business_profile_versions",
        "CREATE TABLE IF NOT EXISTS pilot_opportunities",
        "CREATE TABLE IF NOT EXISTS pilot_source_versions",
        "CREATE TABLE IF NOT EXISTS pilot_source_observations",
        "tenant_id TEXT NOT NULL",
        "ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE pilot_tenants ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE pilot_tenants FORCE ROW LEVEL SECURITY",
        "CREATE POLICY pilot_tenant_identity",
        "import_key TEXT NOT NULL",
        "pilot_source_versions_tenant_source_version_key",
        "pilot_source_observations_tenant_source_version_fkey",
    ):
        assert marker in sql


def test_production_database_requires_explicit_postgres_url(monkeypatch):
    monkeypatch.delenv("YIKE_PILOT_DATABASE_URL", raising=False)
    with pytest.raises(MissingDatabaseConfiguration):
        PilotDatabase.from_environment()


def test_sqlite_url_is_rejected_for_pilot(monkeypatch):
    monkeypatch.setenv("YIKE_PILOT_DATABASE_URL", "sqlite:///tmp/pilot.db")
    with pytest.raises(MissingDatabaseConfiguration):
        PilotDatabase.from_environment()


def test_provision_tenant_binds_new_tenant_before_force_rls_insert():
    source = inspect.getsource(PilotStore.provision_tenant)
    assert "set_config('yike.tenant_id', %s, false)" in source


@pytest.mark.integration
def test_two_tenants_are_isolated_and_import_is_idempotent():
    url = os.environ.get("YIKE_PILOT_ADMIN_DATABASE_URL")
    if not url:
        pytest.skip("set YIKE_PILOT_ADMIN_DATABASE_URL for PostgreSQL integration")
    admin_database = PilotDatabase(url)
    admin_database.migrate()
    admin_database.migrate()
    with admin_database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE pilot_source_observations DROP CONSTRAINT IF EXISTS pilot_source_observations_tenant_source_version_fkey")
            cursor.execute("ALTER TABLE pilot_source_versions DROP CONSTRAINT IF EXISTS pilot_source_versions_tenant_source_version_key")
            cursor.execute("ALTER TABLE pilot_source_observations ADD CONSTRAINT pilot_source_observations_tenant_id_source_version_id_fkey FOREIGN KEY (tenant_id, source_version_id) REFERENCES pilot_source_versions(tenant_id, source_version_id)")
    admin_database.migrate()
    with admin_database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_constraint WHERE conname='pilot_source_versions_tenant_source_version_key'")
            assert cursor.fetchone() is not None
            cursor.execute("SELECT 1 FROM pg_constraint WHERE conname='pilot_source_observations_tenant_source_version_fkey'")
            assert cursor.fetchone() is not None
    with admin_database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='pilot_app') THEN CREATE ROLE pilot_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'pilot_app'; ELSE ALTER ROLE pilot_app NOSUPERUSER NOBYPASSRLS; END IF; END $$;")
            cursor.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO pilot_app")
            cursor.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO pilot_app")
    # Use the explicitly supplied restricted application URL when available;
    # replacing a historical fixture credential can silently leave the test on
    # the admin/superuser connection and invalidate the RLS assertion.
    database = PilotDatabase(os.environ.get("YIKE_PILOT_DATABASE_URL") or url.replace('pilot:pilot@', 'pilot_app:pilot_app@'))
    store = PilotStore(database)
    # Tenant and user provisioning is trusted-admin work; the application role
    # is intentionally unable to enumerate or create tenant-directory rows.
    admin_store = PilotStore(admin_database)
    first = admin_store.provision_tenant("alpha")
    second = admin_store.provision_tenant("beta")
    first_user = admin_store.provision_user(first, "alpha@example.invalid")
    second_user = admin_store.provision_user(second, "beta@example.invalid")
    profile = store.save_profile(first_user, {"service": "展台设计搭建", "region": "北京"})
    assert store.get_profile_version(first_user, profile["version_id"])["status"] == "DRAFT"
    repeated_profile = store.save_profile(first_user, {"service": "展台设计搭建", "region": "北京"})
    assert repeated_profile["version_id"] == profile["version_id"]
    assert repeated_profile["version"] == profile["version"]
    with pytest.raises(ValueError, match="confirmed profile"):
        store.import_opportunity(first_user, profile["version_id"], "blocked-import", {"title": "t", "buyer": "b", "summary": "s", "public_url": "https://example.invalid/source/draft", "source_platform": "xiaohongshu", "source_external_id": "draft", "contact_path": "原帖评论", "draft_comment": "c", "draft_dm": "d"})
    store.confirm_profile(first_user, profile["version_id"])
    assert store.get_task(first_user, f"research:{profile['version_id']}")["status"] == "PENDING"
    opportunity = {
        "title": "寻找展台设计搭建团队",
        "buyer": "匿名企业采购负责人",
        "summary": "秋季展会需要从方案到搭建的一体化服务",
        "public_url": "https://example.invalid/source/one",
        "source_platform": "xiaohongshu",
        "source_external_id": "source-one",
        "source_published_at": "2026-09-01T09:00:00Z",
        "contact_path": "原帖评论",
        "public_excerpt": "秋季展会寻展台设计搭建团队",
        "match_reason": "明确寻源且有具体场景",
        "action_signal": "正在比较服务商",
        "value_judgment": "项目型服务，具备扩展价值",
        "risk": "预算未公开",
        "draft_comment": "方便的话想了解一下展会城市和面积，我可以先帮你判断需求范围。",
        "draft_dm": "看到你在找展台团队。若项目还在评估，我可以先按城市、面积和交付时间帮你梳理一下，不急着报价。",
    }
    created = store.import_opportunity(first_user, profile["version_id"], "run-1:source-one", opportunity)
    repeated = store.import_opportunity(first_user, profile["version_id"], "run-1:source-one", opportunity)
    assert created["opportunity_id"] == repeated["opportunity_id"]
    assert repeated["created"] is False
    assert len(store.list_opportunities(first_user)) == 1
    sibling = store.import_opportunity(first_user, profile["version_id"], "run-2:source-one", opportunity)
    assert sibling["created"] is False
    assert sibling["opportunity_id"] == created["opportunity_id"]
    assert len(store.list_opportunities(first_user)) == 1
    with pytest.raises(ValueError, match="source identity"):
        store.import_opportunity(first_user, profile["version_id"], "run-3:source-one", {**opportunity, "public_url": "https://example.invalid/source/conflict"})
    assert store.list_opportunities(second_user) == []
    store.record_followup(first_user, created["opportunity_id"], "REPLIED", "对方回复，愿意沟通")
    assert store.list_followups(first_user, created["opportunity_id"])[0]["status"] == "REPLIED"
    assert store.list_all_followups(first_user)[0]["opportunity_id"] == created["opportunity_id"]
    store.set_source_status(first_user, created["opportunity_id"], "BLOCKED")
    assert store.get_opportunity(first_user, created["opportunity_id"])["source_status"] == "BLOCKED"
    assert {row["source_status"] for row in store.list_opportunities(first_user)} == {"BLOCKED"}
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (first,))
            cursor.execute("SELECT health FROM pilot_sources WHERE tenant_id=%s AND external_id=%s", (first, "source-one"))
            assert cursor.fetchone()[0] == "BLOCKED"
    assert next(row for row in store.list_opportunities(first_user) if row["opportunity_id"] == created["opportunity_id"])["intent_status"] == "CONTACTED"
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (second,))
            cursor.execute("SELECT COUNT(*) FROM pilot_opportunities WHERE tenant_id=%s", (first,))
            assert cursor.fetchone()[0] == 0
    with pytest.raises(KeyError):
        store.get_opportunity(second_user, created["opportunity_id"])

    claimed = store.claim_task(first_user, "research:2026-09-08", "worker-a", lease_seconds=60)
    assert claimed is not None
    assert claimed["status"] == "RUNNING"
    assert store.claim_task(first_user, "research:2026-09-08", "worker-b", lease_seconds=60) is None
    assert store.complete_task(first_user, "research:2026-09-08", "worker-b") is False
    assert store.complete_task(first_user, "research:2026-09-08", "worker-a") is True
    assert store.complete_task(first_user, "research:2026-09-08", "worker-a") is True
    assert store.complete_task(first_user, "research:2026-09-08", "worker-b") is False
    assert store.claim_task(first_user, "research:2026-09-08", "worker-b", lease_seconds=60) is None

    assert store.claim_task(first_user, "research:lease-expiry", "worker-a", lease_seconds=60) is not None
    with admin_database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE pilot_tasks SET lease_until=CURRENT_TIMESTAMP - INTERVAL '1 second' WHERE task_key=%s", ("research:lease-expiry",))
    takeover = store.claim_task(first_user, "research:lease-expiry", "worker-b", lease_seconds=60)
    assert takeover is not None
    assert takeover["lease_owner"] == "worker-b"
    assert store.complete_task(first_user, "research:lease-expiry", "worker-a") is False

    assert store.claim_task(first_user, "research:retry", "worker-a", lease_seconds=60) is not None
    assert store.fail_task(first_user, "research:retry", "worker-a") is True
    assert store.fail_task(first_user, "research:retry", "worker-a") is True
    assert store.fail_task(first_user, "research:retry", "worker-b") is False
    assert store.list_failed_tasks(first_user)[0]["status"] == "FAILED"
    retried = store.claim_task(first_user, "research:retry", "worker-b", lease_seconds=60)
    assert retried is not None
    assert retried["lease_owner"] == "worker-b"
    with pytest.raises(ValueError):
        store.claim_task(first_user, "", "worker-a")
    assert store.claim_task(second_user, "research:2026-09-08", "worker-z", lease_seconds=60) is not None
    assert store.get_task(first_user, "research:2026-09-08")["status"] == "DONE"

    updated = store.save_profile(first_user, {"service": "展台设计搭建", "region": "上海"})
    assert updated["version"] == 2
    assert store.get_profile_version(first_user, profile["version_id"])["payload"]["region"] == "北京"
    store.confirm_profile(first_user, updated["version_id"])
    store.confirm_profile(first_user, updated["version_id"])
    assert store.get_profile_version(first_user, updated["version_id"])["status"] == "CONFIRMED"
    assert store.get_profile_version(first_user, profile["version_id"])["status"] == "REVOKED"
    with pytest.raises(ValueError, match="confirmed profile"):
        store.import_opportunity(first_user, profile["version_id"], "blocked-old-profile", opportunity)
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (first,))
            cursor.execute("SELECT COUNT(*) FROM pilot_source_observations")
            assert cursor.fetchone()[0] == 2


@pytest.mark.integration
def test_concurrent_profile_confirmation_keeps_one_current_version():
    url = os.environ.get("YIKE_PILOT_ADMIN_DATABASE_URL")
    if not url:
        pytest.skip("set YIKE_PILOT_ADMIN_DATABASE_URL for PostgreSQL integration")
    database = PilotDatabase(url)
    database.migrate()
    store = PilotStore(database)
    tenant_id = store.provision_tenant("concurrent-profile")
    user_id = store.provision_user(tenant_id, "concurrent@example.invalid")
    first = store.save_profile(user_id, {"description": "版本一"})
    second = store.save_profile(user_id, {"description": "版本二"})
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE OR REPLACE FUNCTION pilot_test_confirm_delay() RETURNS trigger
                LANGUAGE plpgsql AS $$
                BEGIN
                    IF NEW.status = 'CONFIRMED' AND OLD.status = 'DRAFT' THEN
                        PERFORM pg_sleep(0.2);
                    END IF;
                    RETURN NEW;
                END $$
            """)
            cursor.execute("DROP TRIGGER IF EXISTS pilot_test_confirm_delay_trigger ON business_profile_versions")
            cursor.execute("""
                CREATE TRIGGER pilot_test_confirm_delay_trigger
                BEFORE UPDATE ON business_profile_versions
                FOR EACH ROW EXECUTE FUNCTION pilot_test_confirm_delay()
            """)
    start = Barrier(2)

    def confirm(version_id):
        start.wait(timeout=5)
        store.confirm_profile(user_id, version_id)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(confirm, (first["version_id"], second["version_id"])))
    finally:
        with database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DROP TRIGGER IF EXISTS pilot_test_confirm_delay_trigger ON business_profile_versions")
                cursor.execute("DROP FUNCTION IF EXISTS pilot_test_confirm_delay()")
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT version, status FROM business_profile_versions WHERE tenant_id=%s ORDER BY version",
                (tenant_id,),
            )
            statuses = cursor.fetchall()
    assert [status for _, status in statuses].count("CONFIRMED") == 1
    assert {version for version, status in statuses if status == "CONFIRMED"} <= {first["version"], second["version"]}
