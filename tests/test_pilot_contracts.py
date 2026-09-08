import os
from pathlib import Path

import pytest

from pilot.db import PilotDatabase, MissingDatabaseConfiguration
from pilot.store import PilotStore


MIGRATION = Path(__file__).parents[1] / "migrations" / "101_customer_pilot.sql"


def test_migration_declares_tenant_scope_and_profile_history():
    sql = MIGRATION.read_text(encoding="utf-8")
    for marker in (
        "CREATE TABLE IF NOT EXISTS pilot_tenants",
        "CREATE TABLE IF NOT EXISTS business_profile_versions",
        "CREATE TABLE IF NOT EXISTS pilot_opportunities",
        "CREATE TABLE IF NOT EXISTS pilot_source_versions",
        "CREATE TABLE IF NOT EXISTS pilot_source_observations",
        "tenant_id TEXT NOT NULL",
        "ENABLE ROW LEVEL SECURITY",
        "import_key TEXT NOT NULL",
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


@pytest.mark.integration
def test_two_tenants_are_isolated_and_import_is_idempotent():
    url = os.environ.get("YIKE_PILOT_DATABASE_URL")
    if not url:
        pytest.skip("set YIKE_PILOT_DATABASE_URL for PostgreSQL integration")
    admin_database = PilotDatabase(url)
    admin_database.migrate()
    admin_database.migrate()
    with admin_database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='pilot_app') THEN CREATE ROLE pilot_app LOGIN PASSWORD 'pilot_app'; END IF; END $$;")
            cursor.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO pilot_app")
            cursor.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO pilot_app")
    database = PilotDatabase(url.replace('pilot:pilot@', 'pilot_app:pilot_app@'))
    store = PilotStore(database)
    first = store.provision_tenant("alpha")
    second = store.provision_tenant("beta")
    first_user = store.provision_user(first, "alpha@example.invalid")
    second_user = store.provision_user(second, "beta@example.invalid")
    profile = store.save_profile(first_user, {"service": "展台设计搭建", "region": "北京"})
    assert store.get_profile_version(first_user, profile["version_id"])["status"] == "DRAFT"
    with pytest.raises(ValueError, match="confirmed profile"):
        store.import_opportunity(first_user, profile["version_id"], "blocked-import", {"title": "t", "buyer": "b", "summary": "s", "public_url": "https://example.invalid/source/draft", "source_platform": "xiaohongshu", "source_external_id": "draft", "contact_path": "原帖评论", "draft_comment": "c", "draft_dm": "d"})
    store.confirm_profile(first_user, profile["version_id"])
    opportunity = {
        "title": "寻找展台设计搭建团队",
        "buyer": "匿名企业采购负责人",
        "summary": "秋季展会需要从方案到搭建的一体化服务",
        "public_url": "https://example.invalid/source/one",
        "source_platform": "xiaohongshu",
        "source_external_id": "source-one",
        "source_published_at": "2026-09-01T09:00:00Z",
        "contact_path": "原帖评论",
        "draft_comment": "方便的话想了解一下展会城市和面积，我可以先帮你判断需求范围。",
        "draft_dm": "看到你在找展台团队。若项目还在评估，我可以先按城市、面积和交付时间帮你梳理一下，不急着报价。",
    }
    created = store.import_opportunity(first_user, profile["version_id"], "run-1:source-one", opportunity)
    repeated = store.import_opportunity(first_user, profile["version_id"], "run-1:source-one", opportunity)
    assert created["opportunity_id"] == repeated["opportunity_id"]
    assert repeated["created"] is False
    assert len(store.list_opportunities(first_user)) == 1
    assert store.list_opportunities(second_user) == []
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (second,))
            cursor.execute("SELECT COUNT(*) FROM pilot_opportunities WHERE tenant_id=%s", (first,))
            assert cursor.fetchone()[0] == 0
    with pytest.raises(KeyError):
        store.get_opportunity(second_user, created["opportunity_id"])
    updated = store.save_profile(first_user, {"service": "展台设计搭建", "region": "上海"})
    assert updated["version"] == 2
    assert store.get_profile_version(first_user, profile["version_id"])["payload"]["region"] == "北京"
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM pilot_source_observations")
            assert cursor.fetchone()[0] == 2
