"""Real, disposable PostgreSQL only; admin provisions, restricted app imports.

Set both YIKE_PILOT_ADMIN_DATABASE_URL and YIKE_PILOT_DATABASE_URL to the
same isolated test database with distinct roles. No URL is logged or persisted.
The test runner must discard the database afterwards; tenant names are unique.
"""
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from psycopg import sql

from pilot.db import PilotDatabase
from pilot.research_import import import_reviewed_bundle
from pilot.store import PilotStore


TABLES = (
    "pilot_sources", "pilot_source_versions", "pilot_source_observations",
    "pilot_opportunities",
)


@pytest.fixture(scope="module")
def stores():
    admin_url = os.environ.get("YIKE_PILOT_ADMIN_DATABASE_URL")
    app_url = os.environ.get("YIKE_PILOT_DATABASE_URL")
    if not admin_url or not app_url:
        pytest.skip("requires separate admin/app URLs for isolated PostgreSQL")
    admin_database = PilotDatabase(admin_url)
    app_database = PilotDatabase(app_url)
    # Check the supplied roles and destination before any migration/provisioning.
    with admin_database.connect() as connection:
        admin_identity = connection.execute(
            "SELECT current_user, current_database(), inet_server_addr()::text, inet_server_port()"
        ).fetchone()
    with app_database.connect() as connection:
        app_identity = connection.execute(
            "SELECT current_user, current_database(), inet_server_addr()::text, inet_server_port()"
        ).fetchone()
        privileges = connection.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
    assert admin_identity[0] != app_identity[0], "admin and application roles must differ"
    assert admin_identity[1:] == app_identity[1:], "both roles must target the same isolated database"
    assert privileges == (False, False), "application imports must not bypass RLS"
    admin_database.migrate()
    # Test-only grants; never change production role configuration.
    with admin_database.connect() as connection:
        connection.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(app_identity[0])))
        connection.execute(sql.SQL(
            "GRANT SELECT, INSERT, UPDATE ON pilot_users, business_profiles, "
            "business_profile_versions, pilot_tasks, pilot_sources, pilot_source_versions, "
            "pilot_source_observations, pilot_opportunities, pilot_followups TO {}"
        ).format(sql.Identifier(app_identity[0])))
    return PilotStore(admin_database), PilotStore(app_database)


def customer(stores, label):
    admin, app = stores
    suffix = uuid4().hex
    tenant = admin.provision_tenant(f"TEST atomic import {label} {suffix}")
    user = admin.provision_user(tenant, f"TEST-{suffix}@example.invalid")
    profile = app.save_profile(user, {"description": "TEST 展台设计搭建，隔离回归数据"})
    app.confirm_profile(user, profile["version_id"])
    return tenant, user, profile["version_id"]


def lead(external_id, url=None):
    return {
        "lead_id": external_id, "title": "TEST isolated budget inquiry", "buyer": "TEST buyer",
        "summary": "TEST no real procurement", "public_url": url or f"https://example.invalid/{external_id}",
        "source_platform": "test", "source_external_id": external_id,
        "source_published_at": (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "contact_path": "TEST no real contact", "public_excerpt": "TEST public excerpt",
        "match_reason": "TEST scope match", "action_signal": "TEST inquiry", "value_judgment": "TEST unknown value",
        "risk": "TEST not a customer opportunity", "draft_comment": "TEST public draft", "draft_dm": "TEST private draft",
    }


def bundle(profile_id, leads, bundle_id="TEST-atomic-package"):
    return {
        "bundle_id": bundle_id, "profile_version_id": profile_id, "audience": "CUSTOMER",
        "review_status": "APPROVED", "reviewer_id": "TEST-reviewer",
        "reviewed_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "leads": leads,
    }


def counts(app, tenant):
    with app.database.connect() as connection:
        connection.execute("SELECT set_config('yike.tenant_id', %s, true)", (tenant,))
        return {
            table: connection.execute(
                sql.SQL("SELECT COUNT(*) FROM {} WHERE tenant_id=%s").format(sql.Identifier(table)), (tenant,)
            ).fetchone()[0]
            for table in TABLES
        }


@pytest.mark.integration
def test_late_source_conflict_rolls_back_whole_bundle_including_observations(stores):
    _, app = stores
    tenant, user, pid = customer(stores, "rollback")
    app.import_opportunity(user, pid, "TEST-earlier:existing", lead("existing"))
    before = counts(app, tenant)
    assert set(before.values()) == {1}
    package = bundle(pid, [lead("new"), lead("existing", "https://example.invalid/conflict")])
    with pytest.raises(ValueError, match="source identity"):
        import_reviewed_bundle(app, user, pid, package)
    assert counts(app, tenant) == before
    assert len(app.list_opportunities(user)) == 1
    good = bundle(pid, [lead("new")])
    result = import_reviewed_bundle(app, user, pid, good)
    assert result[0]["created"] is True
    after = counts(app, tenant)
    assert set(after.values()) == {2}
    repeated = import_reviewed_bundle(app, user, pid, good)
    assert repeated == [{"opportunity_id": result[0]["opportunity_id"], "created": False}]
    assert counts(app, tenant) == after


@pytest.mark.integration
def test_same_import_key_cannot_hide_changed_public_url(stores):
    _, app = stores
    tenant, user, pid = customer(stores, "key-url")
    first = app.import_opportunity(user, pid, "TEST-fixed", lead("first"))
    before = counts(app, tenant)
    with pytest.raises(ValueError, match="source identity"):
        app.import_opportunity(user, pid, "TEST-fixed", lead("first", "https://example.invalid/changed"))
    assert counts(app, tenant) == before
    assert app.get_opportunity(user, first["opportunity_id"])["public_url"] == lead("first")["public_url"]


@pytest.mark.integration
def test_source_identity_conflict_within_one_new_bundle_leaves_no_rows(stores):
    _, app = stores
    tenant, user, pid = customer(stores, "intra-bundle")
    second = {**lead("same", "https://example.invalid/different"), "lead_id": "second-item"}
    with pytest.raises(ValueError, match="source identity"):
        import_reviewed_bundle(app, user, pid, bundle(pid, [lead("same"), second]))
    assert set(counts(app, tenant).values()) == {0}


@pytest.mark.integration
def test_list_and_detail_include_source_and_latest_followup_without_tenant_leak(stores):
    _, app = stores
    tenant, user, pid = customer(stores, "fields")
    other_tenant, other_user, other_pid = customer(stores, "other")
    first = app.import_opportunity(user, pid, "TEST-fields", lead("fields"))
    oid = first["opportunity_id"]
    before = app.get_opportunity(user, oid)
    row = app.list_opportunities(user)[0]
    assert row["latest_followup_status"] is None
    assert row["source_platform"] == "test"
    assert row["public_url"] == "https://example.invalid/fields"
    assert row["published_at"] is not None
    assert before["intent_status"] == "NEW"
    assert before["updated_at"] is not None
    app.record_followup(user, oid, "CONTACTED", "TEST initial manual record")
    app.record_followup(user, oid, "REPLIED", "TEST later manual record")
    row = app.list_opportunities(user)[0]
    detail = app.get_opportunity(user, oid)
    assert row["latest_followup_status"] == "REPLIED"
    assert detail["intent_status"] == row["intent_status"] == "CONTACTED"
    assert detail["updated_at"] >= before["updated_at"]
    assert app.list_opportunities(other_user) == []
    with pytest.raises(KeyError):
        app.get_opportunity(other_user, oid)
    with pytest.raises(ValueError, match="confirmed profile"):
        import_reviewed_bundle(app, other_user, pid, bundle(pid, [lead("foreign")]))
    assert set(counts(app, other_tenant).values()) == {0}
    # Same source/key can exist independently in another correctly bound tenant.
    second = app.import_opportunity(other_user, other_pid, "TEST-fields", lead("fields"))
    assert second["created"] is True and second["opportunity_id"] != oid
    with app.database.connect() as connection:
        connection.execute("SELECT set_config('yike.tenant_id', %s, true)", (other_tenant,))
        assert connection.execute("SELECT COUNT(*) FROM pilot_opportunities WHERE tenant_id=%s", (tenant,)).fetchone()[0] == 0


@pytest.mark.integration
def test_same_key_still_rejects_another_source_or_profile(stores):
    _, app = stores
    tenant, user, pid = customer(stores, "key-binding")
    app.import_opportunity(user, pid, "TEST-key", lead("first"))
    with pytest.raises(ValueError, match="existing source"):
        app.import_opportunity(user, pid, "TEST-key", lead("another"))
    next_profile = app.save_profile(user, {"description": "TEST changed profile"})
    app.confirm_profile(user, next_profile["version_id"])
    with pytest.raises(ValueError, match="existing profile"):
        app.import_opportunity(user, next_profile["version_id"], "TEST-key", lead("first"))
    assert set(counts(app, tenant).values()) == {1}
