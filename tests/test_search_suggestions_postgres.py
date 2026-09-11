"""Synthetic dedicated PostgreSQL with the real restricted application role."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from pilot.auth import issue_token, verify_token_claims
from pilot.db import PilotDatabase
from pilot.search_suggestion_model import SearchSuggestionError, validate_suggestion
from pilot.store import PilotStore
from tests.test_search_suggestions import implementation, body


ROOT = Path(__file__).parents[1]
MIGRATION = ROOT / "migrations/110_v02_search_suggestions.sql"
CONSENT_MIGRATION = ROOT / "migrations/128_v02_search_suggestion_consent.sql"
REJECTION_MIGRATION = ROOT / "migrations/129_v02_search_suggestion_rejections.sql"
GRANT = ROOT / "deploy/grant_search_suggestions.sql"
DESCRIPTION = "我们为食品工厂提供不锈钢输送设备，支持现场测量和定制交付。"
SAFE_FIELDS = {"request_id", "draft_id", "draft_revision", "profile_version_id", "profile_sha256",
               "rule_version", "model_provider", "model_name", "disclosure_policy_version", "state", "result", "usage",
               "error_code", "created_at", "updated_at", "profile_current"}


def result():
    return {"keywords": ["输送设备定制 采购"], "exclusions": ["招聘"],
            "rationale": "根据定制交付能力寻找采购业务表达。", "evidence": ["食品工厂", "不锈钢输送设备"],
            "unknowns": ["未说明服务地域"]}


def token_claims(user):
    return verify_token_claims(issue_token(user, "synthetic-store-secret"), "synthetic-store-secret")


@pytest.fixture(scope="module")
def databases():
    urls = [os.environ.get(name) for name in ("YIKE_SEARCH_SUGGESTION_TEST_DATABASE_URL",
                                            "YIKE_SEARCH_SUGGESTION_TEST_APP_DATABASE_URL")]
    if not all(urls):
        pytest.skip("dedicated search suggestion PostgreSQL required")
    for url in urls:
        parsed = urlsplit(url)
        assert parsed.hostname == "127.0.0.1" and parsed.path == "/win_search_suggestion"
    admin, app = map(PilotDatabase, urls)
    app_parts = urlsplit(urls[1])
    assert app_parts.username == "suggestion_app"
    admin.migrate()
    with admin.connect() as conn:
        conn.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB PASSWORD {}").format(
            sql.Identifier(app_parts.username), sql.Literal(app_parts.password)))
        conn.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(app_parts.username)))
        conn.execute(sql.SQL("GRANT SELECT ON pilot_users,business_profiles,business_profile_versions TO {}").format(sql.Identifier(app_parts.username)))
        # FOR UPDATE needs an UPDATE privilege, but this store does not own profile edits.
        conn.execute(sql.SQL("GRANT UPDATE(profile_id) ON business_profiles TO {}").format(sql.Identifier(app_parts.username)))
        conn.execute(sql.SQL("GRANT SELECT,INSERT ON pilot_session_revocations TO {}").format(sql.Identifier(app_parts.username)))
        if MIGRATION.exists():
            conn.execute(MIGRATION.read_text(encoding="utf-8"))
        if CONSENT_MIGRATION.exists():
            conn.execute(CONSENT_MIGRATION.read_text(encoding="utf-8"))
        if REJECTION_MIGRATION.exists():
            conn.execute(REJECTION_MIGRATION.read_text(encoding="utf-8"))
        if GRANT.exists():
            conn.execute("SELECT set_config('yike.app_role', %s, true)", (app_parts.username,))
            conn.execute(GRANT.read_text(encoding="utf-8"))
            # Runtime also installs material-reference permissions after migration 132.
            conn.execute((ROOT / "deploy/grant_materials.sql").read_text(encoding="utf-8"))
    return admin, app


@pytest.fixture
def env(databases):
    admin, app = databases
    provisioner = PilotStore(admin)
    tenant = provisioner.provision_tenant("synthetic-suggestion")
    foreign_tenant = provisioner.provision_tenant("synthetic-suggestion-other")
    user = provisioner.provision_user(tenant, f"{uuid4()}@example.invalid")
    other_user = provisioner.provision_user(tenant, f"{uuid4()}@example.invalid")
    foreign_user = provisioner.provision_user(foreign_tenant, f"{uuid4()}@example.invalid")
    profile = provisioner.save_profile(user, {"description": DESCRIPTION})
    provisioner.confirm_profile(user, profile["version_id"])
    return SimpleNamespace(admin=admin, database=app, provisioner=provisioner, tenant=tenant,
        foreign_tenant=foreign_tenant, user=user, other_user=other_user, foreign_user=foreign_user,
        claims=token_claims(user), other_claims=token_claims(other_user), foreign_claims=token_claims(foreign_user),
        profile=profile)


def store(env):
    return implementation().SearchSuggestionStore(env.database)


def request(env, **changes):
    return implementation().SearchSuggestionRequest(**body(profile_version_id=env.profile["version_id"], **changes))


def reserve(env, req=None, claims=None, **config):
    return store(env).reserve(claims or env.claims, req or request(env),
        **({"provider": "openai-compatible", "model": "synthetic-model-v1"} | config))


def counts(env):
    with env.admin.connect() as conn:
        return tuple(conn.execute(f"SELECT count(*) FROM {table} WHERE tenant_id=%s", (env.tenant,)).fetchone()[0]
                     for table in ("pilot_search_suggestion_requests", "pilot_search_suggestion_quota_events"))


def age_quota(env, seconds=3):
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_search_suggestion_quota_events SET created_at=clock_timestamp()-(%s * interval '1 second') WHERE tenant_id=%s",
                     (seconds, env.tenant))


def disclosure(env):
    digest = hashlib.sha256(json.dumps({"description": DESCRIPTION}, ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"accepted": True, "profile_sha256": digest,
            "model_provider": "openai-compatible", "model_name": "synthetic-model-v1",
            "policy_version": "profile-description-v1"}


def test_consent_snapshot_is_atomic_replay_bound_and_immutable(env):
    req = request(env)
    receipt, description = store(env).reserve(env.claims, req, provider="openai-compatible",
        model="synthetic-model-v1", disclosure=disclosure(env))
    assert description == DESCRIPTION and receipt["disclosure_policy_version"] == "profile-description-v1"
    assert store(env).reserve(env.claims, req, provider="openai-compatible",
        model="synthetic-model-v1", disclosure=disclosure(env)) == (receipt, None)
    changed = disclosure(env) | {"policy_version": "changed"}
    with pytest.raises(implementation().SearchSuggestionStoreError, match="request_conflict"):
        store(env).reserve(env.claims, req, provider="openai-compatible",
            model="synthetic-model-v1", disclosure=changed)
    with env.admin.connect() as conn, pytest.raises(psycopg.Error):
        conn.execute("UPDATE pilot_search_suggestion_requests SET disclosure_policy_version=NULL WHERE tenant_id=%s AND request_id=%s",
                     (env.tenant, req.request_id))


def test_restricted_postgres_http_consent_and_original_request_restore(env):
    from pilot.search_suggestion_api import register_search_suggestion_api
    from pilot.search_suggestion_service import SearchSuggestionService

    class SyntheticModel:
        provider, model, available = "openai-compatible", "synthetic-model-v1", True
        def generate(self, *, description): return result(), None
        def close(self, timeout_seconds=5): return True

    service = SearchSuggestionService(store(env), SyntheticModel())
    app, router = FastAPI(), APIRouter()
    register_search_suggestion_api(router, service, lambda request: SimpleNamespace(claims=env.claims), lambda request: None)
    app.include_router(router)
    client = TestClient(app)
    preview = client.get(f"/search-suggestions/preview?profileVersionId={env.profile['version_id']}")
    assert preview.status_code == 200
    req = body(profile_version_id=env.profile["version_id"])
    consent = {"accepted": True, "profile_sha256": preview.json()["profile_sha256"],
        "model_provider": preview.json()["model_provider"], "model_name": preview.json()["model_name"],
        "policy_version": preview.json()["disclosure_policy_version"]}
    submitted = client.post("/search-suggestions", json=req | {"disclosure": consent})
    assert submitted.status_code == 200 and submitted.json()["state"] == "PENDING"
    service.close()
    restored = SearchSuggestionService(store(env)).get_receipt(env.claims, req["request_id"])
    assert restored["request_id"] == req["request_id"] and restored["disclosure_policy_version"] == "profile-description-v1"


def test_migration_and_grant_exist(databases):
    assert MIGRATION.is_file(), "missing search suggestion migration 110"
    assert GRANT.is_file(), "missing search suggestion least-privilege grant"
    assert REJECTION_MIGRATION.is_file(), "missing search suggestion rejection migration 129"
    admin, app = databases
    with admin.connect() as conn:
        assert conn.execute("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                            "WHERE oid='pilot_search_suggestion_rejections'::regclass").fetchone()[0]
    with app.connect() as conn:
        assert conn.execute("SELECT has_table_privilege(current_user,'pilot_search_suggestion_rejections','SELECT') "
                            "AND has_table_privilege(current_user,'pilot_search_suggestion_rejections','INSERT')").fetchone()[0]
        assert not conn.execute("SELECT has_table_privilege(current_user,'pilot_search_suggestion_rejections','UPDATE') "
                                "OR has_table_privilege(current_user,'pilot_search_suggestion_rejections','DELETE')").fetchone()[0]


def test_rejection_is_durable_owner_isolated_and_prevents_later_reserve(env):
    req = request(env)
    before = counts(env)
    receipt = store(env).reject(env.claims, req, disclosure(env), "capability_unavailable")
    assert receipt["state"] == "NOT_SUBMITTED" and receipt["error_code"] == "capability_unavailable"
    assert receipt["result"] is receipt["usage"] is None and receipt["profile_current"] is False
    assert counts(env) == before
    assert store(env).get_receipt(env.claims, req.request_id) == receipt
    assert store(env).reserve(env.claims, req, provider="openai-compatible", model="synthetic-model-v1",
                              disclosure=disclosure(env)) == (receipt, None)
    with pytest.raises(implementation().SearchSuggestionStoreError, match="request_not_found"):
        store(env).get_receipt(env.other_claims, req.request_id)
    changed = implementation().SearchSuggestionRequest(**(req.model_dump() | {"draft_revision": 2}))
    with pytest.raises(implementation().SearchSuggestionStoreError, match="request_conflict"):
        store(env).replay_receipt(env.claims, changed, disclosure(env))


def test_restricted_http_post_and_get_restore_not_submitted_without_quota(env):
    from pilot.search_suggestion_api import register_search_suggestion_api
    from pilot.search_suggestion_service import SearchSuggestionService

    class UnavailableModel:
        provider, model, available = "openai-compatible", "synthetic-model-v1", False

    service = SearchSuggestionService(store(env), UnavailableModel())
    app, router = FastAPI(), APIRouter()
    register_search_suggestion_api(router, service, lambda request: SimpleNamespace(claims=env.claims), lambda request: None)
    app.include_router(router)
    client = TestClient(app)
    req = body(profile_version_id=env.profile["version_id"])
    before = counts(env)
    submitted = client.post("/search-suggestions", json=req | {"disclosure": disclosure(env)})
    restored = client.get(f"/search-suggestions/{req['request_id']}")
    assert submitted.status_code == restored.status_code == 200
    assert submitted.json() == restored.json()
    assert set(restored.json()) == SAFE_FIELDS and restored.json()["state"] == "NOT_SUBMITTED"
    assert counts(env) == before


def test_reject_after_acceptance_returns_actual_fact_and_old_insert_cannot_cross_tombstone(env):
    accepted = request(env)
    actual, _ = store(env).reserve(env.claims, accepted, provider="openai-compatible",
        model="synthetic-model-v1", disclosure=disclosure(env))
    assert store(env).reject(env.claims, accepted, disclosure(env), "suggestion_busy") == actual
    rejected = request(env)
    store(env).reject(env.claims, rejected, disclosure(env), "suggestion_busy")
    with env.admin.connect() as conn, pytest.raises(psycopg.Error) as raised:
        conn.execute("INSERT INTO pilot_search_suggestion_requests(tenant_id,owner_user_id,request_id,draft_id,draft_revision,"
            "profile_version_id,request_sha256,profile_sha256,origin_session_key,origin_session_expires_at,rule_version,"
            "model_provider,model_name,disclosure_policy_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (env.tenant, env.user, rejected.request_id, rejected.draft_id, rejected.draft_revision,
             rejected.profile_version_id, "b" * 64, disclosure(env)["profile_sha256"], env.claims.revocation_key,
             env.claims.expires_at, "search-suggestion-v1", "openai-compatible", "synthetic-model-v1",
             "profile-description-v1"))
    assert raised.value.sqlstate == "YS002"


def test_parallel_reject_and_reserve_leave_one_durable_fact(env):
    req = request(env)
    consent = disclosure(env)
    with ThreadPoolExecutor(max_workers=2) as pool:
        rejected = pool.submit(store(env).reject, env.claims, req, consent, "suggestion_busy")
        accepted = pool.submit(store(env).reserve, env.claims, req, provider="openai-compatible",
                               model="synthetic-model-v1", disclosure=consent)
        outcomes = [rejected.result(timeout=5), accepted.result(timeout=5)[0]]
    assert outcomes[0] == outcomes[1]
    with env.admin.connect() as conn:
        facts = [conn.execute(f"SELECT count(*) FROM {table} WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s",
                    (env.tenant, env.user, req.request_id)).fetchone()[0]
                 for table in ("pilot_search_suggestion_requests", "pilot_search_suggestion_rejections")]
    assert sum(facts) == 1


def test_reserve_persists_before_return_and_replays_without_description_or_config_change(env):
    req = request(env)
    receipt, description = reserve(env, req)
    assert description == DESCRIPTION
    assert set(receipt) == SAFE_FIELDS
    assert receipt["state"] == "PENDING" and receipt["profile_current"] is True
    assert receipt["result"] is receipt["usage"] is receipt["error_code"] is None
    assert receipt["profile_sha256"] == hashlib.sha256(json.dumps({"description": DESCRIPTION}, ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert store(env).get_receipt(env.claims, req.request_id) == receipt
    assert reserve(env, req, model="different-current-config") == (receipt, None)
    assert counts(env) == (1, 1)


@pytest.mark.parametrize("change", ["draft_id", "draft_revision", "profile_version_id"])
def test_same_request_different_body_conflicts_without_quota(env, change):
    req = request(env)
    reserve(env, req)
    changed = req.model_copy(update={change: 1 if change == "draft_revision" else str(uuid4())})
    with pytest.raises(implementation().SearchSuggestionStoreError, match="request_conflict"):
        reserve(env, changed)
    assert counts(env) == (1, 1)


@pytest.mark.parametrize("config", [{"provider": ""}, {"provider": "bad\nvalue"}, {"provider": "x" * 81},
                                  {"model": ""}, {"model": "secret\nmodel"}, {"model": "x" * 201}])
def test_invalid_controlled_model_config_does_not_reserve(env, config):
    with pytest.raises(implementation().SearchSuggestionStoreError, match="invalid_suggestion_configuration"):
        reserve(env, **config)
    assert counts(env) == (0, 0)


def test_success_is_revalidated_persisted_safe_and_immutable_on_replay(env):
    req = request(env)
    reserve(env, req)
    payload = result()
    usage = {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5, "provider_secret": "ignored"}
    receipt = store(env).finish(env.claims, req.request_id, content=payload, usage=usage)
    assert receipt["state"] == "SUCCEEDED" and receipt["result"] == payload
    assert receipt["usage"] == {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}
    payload["keywords"].append("changed")
    usage["total_tokens"] = 99
    assert store(env).get_receipt(env.claims, req.request_id) == receipt
    assert store(env).finish(env.claims, req.request_id, error="dispatch_failed") == receipt
    assert reserve(env, req) == (receipt, None)


@pytest.mark.parametrize("bad", ["wrong_evidence", "mutated_model", "extra_field"])
def test_bad_content_becomes_durable_failure_and_still_uses_quota(env, bad):
    req = request(env)
    reserve(env, req)
    payload = result()
    if bad == "wrong_evidence":
        payload["evidence"] = ["不存在的报价承诺"]
    elif bad == "extra_field":
        payload["approved"] = True
    else:
        payload = validate_suggestion(payload, description=DESCRIPTION)
        payload.keywords.append(12)
    receipt = store(env).finish(env.claims, req.request_id, content=payload)
    assert receipt["state"] == "FAILED" and receipt["error_code"] == "invalid_suggestion_result"
    assert receipt["result"] is receipt["usage"] is None
    assert reserve(env, req) == (receipt, None)
    assert counts(env) == (1, 1)


@pytest.mark.parametrize("usage", [{}, {"prompt_tokens": True, "completion_tokens": 2, "total_tokens": 3},
    {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 4},
    {"prompt_tokens": 2**31, "completion_tokens": 0, "total_tokens": 2**31}])
def test_finish_does_not_trust_usage(env, usage):
    req = request(env)
    reserve(env, req)
    assert store(env).finish(env.claims, req.request_id, content=result(), usage=usage)["usage"] is None


@pytest.mark.parametrize(("error", "state"), [("dispatch_failed", "FAILED"),
    (SearchSuggestionError("suggestion_result_unknown", 504), "UNKNOWN"),
    (SearchSuggestionError("suggestion_provider_rejected", 502), "FAILED")])
def test_error_outcomes_are_durable_not_reexecuted(env, error, state):
    req = request(env)
    reserve(env, req)
    receipt = store(env).finish(env.claims, req.request_id, error=error)
    assert receipt["state"] == state and receipt["result"] is None
    assert reserve(env, req) == (receipt, None)
    assert counts(env) == (1, 1)


def test_same_user_new_session_can_read_and_replay_but_cannot_finish_old_request(env):
    req = request(env)
    receipt, _ = reserve(env, req)
    new_claims = token_claims(env.user)
    assert store(env).get_receipt(new_claims, req.request_id) == receipt
    assert reserve(env, req, new_claims) == (receipt, None)
    with pytest.raises(implementation().SearchSuggestionStoreError, match="request_session_mismatch"):
        store(env).finish(new_claims, req.request_id, content=result())
    assert store(env).get_receipt(env.claims, req.request_id)["state"] == "PENDING"


def test_session_revoked_between_reserve_and_finish_preserves_pending(env):
    req = request(env)
    reserve(env, req)
    store(env).sessions.revoke([env.claims])
    for action in (lambda: store(env).finish(env.claims, req.request_id, content=result()),
                   lambda: store(env).get_receipt(env.claims, req.request_id), lambda: reserve(env, req)):
        with pytest.raises(implementation().SearchSuggestionStoreError, match="invalid_session"):
            action()
    assert store(env).get_receipt(token_claims(env.user), req.request_id)["state"] == "PENDING"
    assert counts(env) == (1, 1)


@pytest.mark.parametrize("change", ["confirm_new", "payload_only", "digest_only"])
def test_changed_profile_fails_late_result_without_exposing_content(env, change):
    req = request(env)
    reserve(env, req)
    if change == "confirm_new":
        new = env.provisioner.save_profile(env.user, {"description": "我们提供库存软件。"})
        env.provisioner.confirm_profile(env.user, new["version_id"])
    else:
        column, value = ("payload", json.dumps({"description": "不同原文"})) if change == "payload_only" else ("content_sha256", "0" * 64)
        with env.admin.connect() as conn:
            conn.execute(sql.SQL("UPDATE business_profile_versions SET {}=%s WHERE profile_version_id=%s").format(sql.Identifier(column)),
                         (value, env.profile["version_id"]))
    receipt = store(env).finish(env.claims, req.request_id, content=result())
    assert receipt["state"] == "FAILED" and receipt["error_code"] == "profile_changed"
    assert receipt["result"] is None and receipt["profile_current"] is False
    assert reserve(env, req) == (receipt, None)


def test_historical_success_is_preserved_with_current_profile_flag(env):
    req = request(env)
    reserve(env, req)
    receipt = store(env).finish(env.claims, req.request_id, content=result())
    new = env.provisioner.save_profile(env.user, {"description": "我们提供库存软件。"})
    assert store(env).get_receipt(env.claims, req.request_id)["profile_current"] is True
    env.provisioner.confirm_profile(env.user, new["version_id"])
    assert store(env).get_receipt(env.claims, req.request_id) == receipt | {"profile_current": False}


def test_request_results_hidden_from_other_users_and_tenants(env):
    req = request(env)
    reserve(env, req)
    for claims in (env.other_claims, env.foreign_claims):
        for action in (lambda: store(env).get_receipt(claims, req.request_id),
                       lambda: store(env).finish(claims, req.request_id, content=result())):
            with pytest.raises(implementation().SearchSuggestionStoreError, match="request_not_found"):
                action()


def test_tenant_quota_is_shared_across_users_and_foreign_tenant_is_independent(env):
    reserve(env)
    with pytest.raises(implementation().SearchSuggestionStoreError, match="suggestion_rate_limited"):
        reserve(env, claims=env.other_claims)
    other_profile = env.provisioner.save_profile(env.foreign_user, {"description": DESCRIPTION})
    env.provisioner.confirm_profile(env.foreign_user, other_profile["version_id"])
    req = implementation().SearchSuggestionRequest(**body(profile_version_id=other_profile["version_id"]))
    assert reserve(env, req, env.foreign_claims)[1] == DESCRIPTION
    age_quota(env)
    assert reserve(env, claims=env.other_claims)[1] == DESCRIPTION
    assert counts(env) == (2, 2)


def test_hourly_quota_counts_failed_and_unknown_requests_but_replay_is_free(env):
    requests = []
    for index in range(10):
        age_quota(env)
        req = request(env)
        claims = env.claims if index % 2 == 0 else env.other_claims
        reserve(env, req, claims)
        error = "dispatch_failed" if index % 2 == 0 else SearchSuggestionError("suggestion_result_unknown", 504)
        store(env).finish(claims, req.request_id, error=error)
        requests.append(req)
    age_quota(env)
    with pytest.raises(implementation().SearchSuggestionStoreError, match="suggestion_quota_exceeded"):
        reserve(env)
    assert reserve(env, requests[0])[1] is None
    assert counts(env) == (10, 10)
    age_quota(env, 3601)
    assert reserve(env)[1] == DESCRIPTION


def test_concurrent_same_request_from_distinct_sessions_reserves_once(env):
    req = request(env)
    claims = [token_claims(env.user) for _ in range(6)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda auth: reserve(env, req, auth), claims))
    assert sum(description is not None for _, description in results) == 1
    assert all(receipt == results[0][0] for receipt, _ in results)
    assert counts(env) == (1, 1)


def test_restricted_rls_and_exact_grants(env):
    req = request(env)
    reserve(env, req)
    with env.database.connect() as conn:
        assert conn.execute("SELECT rolsuper,rolbypassrls,rolcreaterole,rolcreatedb FROM pg_roles WHERE rolname=current_user").fetchone() == (False, False, False, False)
        for table in ("pilot_search_suggestion_requests", "pilot_search_suggestion_quota_events"):
            assert conn.execute("SELECT row_security_active(%s::regclass)", (table,)).fetchone()[0]
            assert conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))).fetchone()[0] == 0
            for privilege in ("DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
                assert not conn.execute("SELECT has_table_privilege(current_user,%s,%s)", (table, privilege)).fetchone()[0]
        assert not conn.execute("SELECT has_table_privilege(current_user,'pilot_search_suggestion_quota_events','UPDATE')").fetchone()[0]
        conn.execute("SELECT set_config('yike.tenant_id',%s,true),set_config('yike.user_id',%s,true)", (env.tenant, env.other_user))
        assert conn.execute("SELECT count(*) FROM pilot_search_suggestion_requests").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM pilot_search_suggestion_quota_events").fetchone()[0] == 1
        conn.execute("SELECT set_config('yike.user_id',%s,true)", (env.user,))
        assert conn.execute("SELECT count(*) FROM pilot_search_suggestion_requests").fetchone()[0] == 1
        with pytest.raises(psycopg.Error), conn.transaction():
            conn.execute("UPDATE pilot_search_suggestion_requests SET owner_user_id=%s WHERE request_id=%s", (env.other_user, req.request_id))
        for statement in ("DELETE FROM pilot_search_suggestion_requests", "TRUNCATE pilot_search_suggestion_requests",
                          "UPDATE pilot_search_suggestion_quota_events SET created_at=clock_timestamp()"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                conn.execute(statement)


def test_migration_and_grants_reapply_and_preserve_existing_receipt(env):
    req = request(env)
    receipt, _ = reserve(env, req)
    with env.admin.connect() as conn:
        conn.execute(MIGRATION.read_text(encoding="utf-8"))
        conn.execute("SELECT set_config('yike.app_role','suggestion_app',true)")
        conn.execute(GRANT.read_text(encoding="utf-8"))
    assert store(env).get_receipt(env.claims, req.request_id) == receipt


def test_grant_rejects_admin_and_owner_roles(env):
    with env.admin.connect() as conn:
        for role in ("postgres", "missing_suggestion_role"):
            with pytest.raises(psycopg.Error), conn.transaction():
                conn.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
                conn.execute(GRANT.read_text(encoding="utf-8"))


def wait_for_profile_lock(admin):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with admin.connect() as conn:
            if conn.execute("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE '%business_profiles%FOR UPDATE%')").fetchone()[0]:
                return
        time.sleep(.02)
    pytest.fail("profile row wait was not observed")


def test_finish_rechecks_wall_clock_expiry_after_profile_lock_wait(env):
    claims = replace(env.claims, expires_at=int(time.time()) + 2)
    req = request(env)
    reserve(env, req, claims)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with env.admin.connect() as conn:
            conn.execute("SELECT profile_id FROM business_profiles WHERE profile_id=%s FOR UPDATE", (env.profile["profile_id"],))
            future = pool.submit(store(env).finish, claims, req.request_id, content=result())
            wait_for_profile_lock(env.admin)
            while time.time() <= claims.expires_at:
                time.sleep(.05)
        with pytest.raises(implementation().SearchSuggestionStoreError, match="invalid_session"):
            future.result(timeout=5)
    assert store(env).get_receipt(token_claims(env.user), req.request_id)["state"] == "PENDING"
    assert counts(env) == (1, 1)


@pytest.mark.parametrize("description", ["", "\u200b\t", "missing-description", 12, None, "a" * 8001])
def test_reserve_rejects_bad_confirmed_description_without_quota(env, description):
    payload = {"description": description, "note": "synthetic"}
    if description == "missing-description":
        payload = {"note": "synthetic missing description"}
    version = env.provisioner.save_profile(env.user, payload)
    env.provisioner.confirm_profile(env.user, version["version_id"])
    req = implementation().SearchSuggestionRequest(**body(profile_version_id=version["version_id"]))
    with pytest.raises(implementation().SearchSuggestionStoreError, match="profile_unavailable"):
        reserve(env, req)
    assert counts(env) == (0, 0)


def test_draft_and_foreign_profile_cannot_reserve(env):
    draft = env.provisioner.save_profile(env.user, {"description": "新的未确认画像"})
    for version in (draft["version_id"], str(uuid4())):
        req = implementation().SearchSuggestionRequest(**body(profile_version_id=version))
        with pytest.raises(implementation().SearchSuggestionStoreError, match="profile_unavailable"):
            reserve(env, req)
    req = request(env)
    with pytest.raises(implementation().SearchSuggestionStoreError, match="profile_unavailable"):
        reserve(env, req, env.foreign_claims)
    assert counts(env) == (0, 0)


@pytest.mark.parametrize("changes", [{"user_id": "\ud800"}, {"user_id": "\x00"},
                                    {"expires_at": True}, {"revocation_key": "bad"}])
def test_malformed_claims_are_fixed_errors(env, changes):
    with pytest.raises(implementation().SearchSuggestionStoreError, match="invalid_session") as raised:
        reserve(env, claims=replace(env.claims, **changes))
    assert raised.value.__context__ is None
    assert counts(env) == (0, 0)


def test_finish_checks_original_session_expiration_binding(env):
    req = request(env)
    reserve(env, req)
    changed = replace(env.claims, expires_at=env.claims.expires_at + 60)
    with pytest.raises(implementation().SearchSuggestionStoreError, match="request_session_mismatch"):
        store(env).finish(changed, req.request_id, content=result())
    assert store(env).get_receipt(env.claims, req.request_id)["state"] == "PENDING"


def test_store_revalidates_constructed_request_instances(env):
    req = implementation().SearchSuggestionRequest.model_construct(**body(profile_version_id=env.profile["version_id"], draft_revision=True))
    with pytest.raises(implementation().SearchSuggestionStoreError, match="invalid_request"):
        reserve(env, req)
    assert counts(env) == (0, 0)


def test_database_trigger_prevents_binding_changes_and_terminal_rewrites(env):
    req = request(env)
    reserve(env, req)
    with env.database.connect() as conn:
        conn.execute("SELECT set_config('yike.tenant_id',%s,true),set_config('yike.user_id',%s,true)", (env.tenant, env.user))
        with pytest.raises(psycopg.Error) as raised, conn.transaction():
            conn.execute("UPDATE pilot_search_suggestion_requests SET state='FAILED',error_code='dispatch_failed',model_name='changed' WHERE request_id=%s", (req.request_id,))
        assert raised.value.sqlstate == "YS001"
    store(env).finish(env.claims, req.request_id, content=result())
    with env.database.connect() as conn:
        conn.execute("SELECT set_config('yike.tenant_id',%s,true),set_config('yike.user_id',%s,true)", (env.tenant, env.user))
        with pytest.raises(psycopg.Error) as raised, conn.transaction():
            conn.execute("UPDATE pilot_search_suggestion_requests SET result='{}'::jsonb WHERE request_id=%s", (req.request_id,))
        assert raised.value.sqlstate == "YS001"


def test_request_and_quota_insert_rollback_together(env):
    with env.admin.connect() as conn:
        conn.execute("REVOKE INSERT ON pilot_search_suggestion_quota_events FROM suggestion_app")
    try:
        with pytest.raises(implementation().SearchSuggestionStoreError, match="suggestion_store_unavailable") as raised:
            reserve(env)
        assert raised.value.__cause__ is raised.value.__context__ is None
        assert counts(env) == (0, 0)
    finally:
        with env.admin.connect() as conn:
            conn.execute("SELECT set_config('yike.app_role','suggestion_app',true)")
            conn.execute(GRANT.read_text(encoding="utf-8"))


def test_grant_removes_direct_excess_privileges_and_rejects_inherited_excess(env):
    with env.admin.connect() as conn:
        conn.execute("GRANT DELETE,TRUNCATE ON pilot_search_suggestion_requests TO suggestion_app")
        conn.execute("GRANT UPDATE ON pilot_search_suggestion_quota_events TO suggestion_app")
        conn.execute("SELECT set_config('yike.app_role','suggestion_app',true)")
        conn.execute(GRANT.read_text(encoding="utf-8"))
        assert not conn.execute("SELECT has_table_privilege('suggestion_app','pilot_search_suggestion_requests','DELETE')").fetchone()[0]
        assert not conn.execute("SELECT has_table_privilege('suggestion_app','pilot_search_suggestion_quota_events','UPDATE')").fetchone()[0]
        with conn.transaction(force_rollback=True):
            conn.execute("GRANT DELETE ON pilot_search_suggestion_requests TO PUBLIC")
            with pytest.raises(psycopg.Error), conn.transaction():
                conn.execute(GRANT.read_text(encoding="utf-8"))


@pytest.mark.parametrize("role_kind", ["owner", "privileged_member"])
def test_grant_rejects_restricted_owner_and_privileged_membership(env, role_kind):
    role = "synthetic_guard_" + uuid4().hex
    with env.admin.connect() as conn, conn.transaction(force_rollback=True):
        conn.execute(sql.SQL("CREATE ROLE {} NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB").format(sql.Identifier(role)))
        if role_kind == "owner":
            conn.execute(sql.SQL("ALTER TABLE pilot_search_suggestion_requests OWNER TO {}").format(sql.Identifier(role)))
        else:
            conn.execute(sql.SQL("GRANT postgres TO {}").format(sql.Identifier(role)))
        conn.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
        with pytest.raises(psycopg.Error), conn.transaction():
            conn.execute(GRANT.read_text(encoding="utf-8"))


def test_reserve_waits_for_profile_confirmation_then_observes_revocation(env):
    new = env.provisioner.save_profile(env.user, {"description": "我们提供库存软件。"})
    req = request(env)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with env.admin.connect() as conn:
            conn.execute("SELECT profile_id FROM business_profiles WHERE profile_id=%s FOR UPDATE", (env.profile["profile_id"],))
            future = pool.submit(reserve, env, req)
            wait_for_profile_lock(env.admin)
            conn.execute("UPDATE business_profile_versions SET status='REVOKED' WHERE profile_version_id=%s", (env.profile["version_id"],))
            conn.execute("UPDATE business_profile_versions SET status='CONFIRMED' WHERE profile_version_id=%s", (new["version_id"],))
        with pytest.raises(implementation().SearchSuggestionStoreError, match="profile_unavailable"):
            future.result(timeout=5)
    assert counts(env) == (0, 0)


@pytest.mark.parametrize("target", ["suggestion_app", "PUBLIC"])
def test_grant_clears_direct_or_rejects_inherited_column_update_privileges(env, target):
    with env.admin.connect() as conn, conn.transaction(force_rollback=True):
        recipient = sql.SQL("PUBLIC") if target == "PUBLIC" else sql.Identifier(target)
        conn.execute(sql.SQL("GRANT UPDATE(created_at) ON pilot_search_suggestion_quota_events TO {}").format(recipient))
        assert conn.execute("SELECT has_any_column_privilege('suggestion_app','pilot_search_suggestion_quota_events','UPDATE')").fetchone()[0]
        conn.execute("SELECT set_config('yike.app_role','suggestion_app',true)")
        if target == "suggestion_app":
            conn.execute(GRANT.read_text(encoding="utf-8"))
            assert not conn.execute("SELECT has_any_column_privilege('suggestion_app','pilot_search_suggestion_quota_events','UPDATE')").fetchone()[0]
        else:
            with pytest.raises(psycopg.Error), conn.transaction():
                conn.execute(GRANT.read_text(encoding="utf-8"))


@pytest.mark.parametrize("via_bridge", [False, True], ids=["direct-parent", "transitive-parent"])
@pytest.mark.parametrize(("table", "privilege", "column"), [
    ("pilot_search_suggestion_requests", "TRUNCATE", None),
    ("pilot_search_suggestion_quota_events", "TRUNCATE", None),
    ("pilot_search_suggestion_quota_events", "UPDATE", "created_at"),
])
def test_grant_rejects_noinherit_set_role_privilege_closure(env, via_bridge, table, privilege, column):
    """A NOINHERIT role still reaches parent ACLs through SET ROLE on PG16."""
    reserve(env)
    parent = "synthetic_set_parent_" + uuid4().hex
    bridge = "synthetic_set_bridge_" + uuid4().hex if via_bridge else None
    with env.admin.connect() as conn:
        conn.execute("ALTER ROLE suggestion_app NOINHERIT")
        for role in (parent, bridge):
            if role:
                conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB").format(sql.Identifier(role)))
        conn.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(parent), sql.Identifier(bridge or "suggestion_app")))
        if bridge:
            conn.execute(sql.SQL("GRANT {} TO suggestion_app").format(sql.Identifier(bridge)))
        grant_privilege = sql.SQL("UPDATE(created_at)") if column else sql.SQL("TRUNCATE")
        conn.execute(sql.SQL("GRANT SELECT,{} ON {} TO {}").format(grant_privilege, sql.Identifier(table), sql.Identifier(parent)))
    try:
        with env.admin.connect() as conn:
            assert conn.execute("SELECT pg_has_role('suggestion_app',%s,'SET')", (parent,)).fetchone()[0]
            if column:
                assert not conn.execute("SELECT has_any_column_privilege('suggestion_app',%s,'UPDATE')", (table,)).fetchone()[0]
            else:
                assert not conn.execute("SELECT has_table_privilege('suggestion_app',%s,'TRUNCATE')", (table,)).fetchone()[0]
        # Use the actual restricted login, not an administrator impersonation.
        # Roll back the synthetic TRUNCATE so later checks retain their fixtures.
        with env.database.connect() as conn, conn.transaction(force_rollback=True):
            conn.execute("SELECT set_config('yike.tenant_id',%s,true),set_config('yike.user_id',%s,true)", (env.tenant, env.user))
            conn.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(parent)))
            if column:
                assert conn.execute("SELECT has_column_privilege(current_user,%s,%s,'UPDATE')", (table, column)).fetchone()[0]
            else:
                assert conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))).fetchone()[0] == 1
                conn.execute(sql.SQL("TRUNCATE {}").format(sql.Identifier(table)))
                assert conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))).fetchone()[0] == 0
        with env.admin.connect() as conn:
            conn.execute("SELECT set_config('yike.app_role','suggestion_app',true)")
            with pytest.raises(psycopg.Error), conn.transaction():
                conn.execute(GRANT.read_text(encoding="utf-8"))
    finally:
        with env.admin.connect() as conn:
            conn.execute(sql.SQL("REVOKE {} FROM {}").format(sql.Identifier(parent), sql.Identifier(bridge or "suggestion_app")))
            if bridge:
                conn.execute(sql.SQL("REVOKE {} FROM suggestion_app").format(sql.Identifier(bridge)))
                conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(bridge)))
            conn.execute(sql.SQL("REVOKE ALL ON {} FROM {}").format(sql.Identifier(table), sql.Identifier(parent)))
            conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(parent)))
            conn.execute("ALTER ROLE suggestion_app INHERIT")
