import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from psycopg import sql

from pilot.auth import issue_token, verify_token_claims
from pilot.db import PilotDatabase
from pilot.material_contract import MaterialError, MaterialRequest
from pilot.materials import MaterialStore
from pilot.store import PilotStore
from tests.test_device_credentials_postgres import RoleDatabase


SECRET = "synthetic-material-test-key"


class Model:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, 0

    def extract(self, text):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


@pytest.fixture(scope="module")
def database():
    admin_url = os.environ.get("YIKE_MATERIAL_TEST_DATABASE_URL")
    if not admin_url:
        pytest.skip("dedicated material PostgreSQL required")
    admin = PilotDatabase(admin_url)
    admin.migrate()
    role = "material_test_" + uuid4().hex
    with admin.connect() as conn:
        conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE").format(sql.Identifier(role)))
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
        conn.execute(sql.SQL("GRANT SELECT ON pilot_users,business_profile_versions TO {}").format(sql.Identifier(role)))
        conn.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
        conn.execute((Path(__file__).parents[1] / "deploy/grant_session_revocations.sql").read_text())
        conn.execute((Path(__file__).parents[1] / "deploy/grant_materials.sql").read_text())
    yield SimpleNamespace(admin=admin, app=RoleDatabase(admin, role))
    with admin.connect() as conn:
        conn.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
        conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


@pytest.fixture
def env(database):
    provisioner = PilotStore(database.admin)
    tenant = provisioner.provision_tenant("synthetic-material")
    users = [provisioner.provision_user(tenant, f"{uuid4()}@example.invalid") for _ in range(2)]
    other_tenant = provisioner.provision_tenant("synthetic-material-other")
    users.append(provisioner.provision_user(other_tenant, f"{uuid4()}@example.invalid"))
    profiles = [provisioner.save_profile(user, {"description": "synthetic only"})["version_id"] for user in users]
    claims = [verify_token_claims(issue_token(user, SECRET), SECRET) for user in users]
    yield SimpleNamespace(db=database.app, admin=database.admin, tenant=tenant, users=users, profiles=profiles, claims=claims)


def save_request(profile, material_id="local-" + "a" * 64, request_id=None, expected=None, text="我们服务制造企业，覆盖上海。"):
    return {"requestId": request_id or str(uuid4()), "profileVersionId": profile,
            "change": {"kind": "save", "materialId": material_id, "expectedVersion": expected,
                       "input": {"name": "介绍", "text": text, "purpose": "产品介绍", "visibility": "internal"}}}


def mutate(store, env, body, owner=0):
    return store.mutate(env.claims[owner], body)


def test_contract_is_strict_and_rejects_invalid_material_input(env):
    body = save_request(env.profiles[0])
    body["extra"] = True
    with pytest.raises(ValueError):
        MaterialRequest.model_validate(body)
    body = save_request(env.profiles[0])
    body["change"]["input"]["text"] = "bad\0text"
    with pytest.raises(ValueError):
        MaterialRequest.model_validate(body)


def test_save_is_append_only_cas_and_stable_idempotent(env):
    store = MaterialStore(env.db)
    request = save_request(env.profiles[0])
    receipt = mutate(store, env, request)
    assert receipt["status"] == "SUCCEEDED"
    assert receipt["record"]["status"] == "DRAFT"
    assert receipt["record"]["version"] == 1
    assert mutate(store, env, request) == receipt
    changed = save_request(env.profiles[0], request_id=request["requestId"], text="changed")
    with pytest.raises(MaterialError) as error:
        mutate(store, env, changed)
    assert error.value.code == "material_request_conflict"
    stale = save_request(env.profiles[0], material_id=request["change"]["materialId"], expected=7)
    failed = mutate(store, env, stale)
    assert failed["status"] == "FAILED" and failed["confirmedNoChange"] is True
    assert failed["message"] == "资料版本已变化，请刷新后重试。"
    assert store.operation(env.claims[0], env.profiles[0], stale["requestId"]) == failed
    assert store.operation(env.claims[0], env.profiles[0], request["requestId"]) == receipt


def test_owner_profile_and_missing_operation_are_isolated(env):
    store = MaterialStore(env.db)
    request = save_request(env.profiles[0])
    mutate(store, env, request)
    assert store.list(env.claims[1], env.profiles[0]) == []
    with pytest.raises(MaterialError) as error:
        store.operation(env.claims[1], env.profiles[0], request["requestId"])
    assert (error.value.code, error.value.status) == ("material_operation_not_found", 404)
    with pytest.raises(MaterialError) as error:
        store.operation(env.claims[0], env.profiles[0], str(uuid4()))
    assert error.value.status == 404


def test_parse_revalidates_quotes_and_failure_is_honest(env):
    invalid = Model({"fields": {"service": "制造获客"}, "evidence": [{"field": "service", "quote": "不存在"}]})
    store = MaterialStore(env.db, invalid)
    saved = mutate(store, env, save_request(env.profiles[0]))["record"]
    parsed = mutate(store, env, {"requestId": str(uuid4()), "profileVersionId": env.profiles[0],
        "change": {"kind": "parse", "materialId": saved["id"], "expectedVersion": 1}})["record"]
    assert parsed["status"] == "FAILED"
    assert parsed["failure"] == "资料解析失败，请重试。"
    assert "extraction" not in parsed
    assert invalid.calls == 1


def test_concurrent_parse_replay_calls_model_once(env):
    model = Model({"fields": {"service": "制造企业"},
                   "evidence": [{"field": "service", "quote": "制造企业"}]})
    store = MaterialStore(env.db, model)
    saved = mutate(store, env, save_request(env.profiles[0]))["record"]
    request = {"requestId": str(uuid4()), "profileVersionId": env.profiles[0],
               "change": {"kind": "parse", "materialId": saved["id"], "expectedVersion": 1}}
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda _: mutate(store, env, request), range(2)))
    assert receipts[0] == receipts[1]
    assert model.calls == 1


def test_parse_confirm_impact_revoke_and_remove_preserve_history(env):
    text = "我们服务制造企业，覆盖上海。"
    model = Model({"fields": {"service": "制造企业获客", "regions": "上海"},
                   "evidence": [{"field": "service", "quote": "服务制造企业"},
                                {"field": "service", "quote": "制造企业"},
                                {"field": "regions", "quote": "上海"}]})
    store = MaterialStore(env.db, model)
    saved = mutate(store, env, save_request(env.profiles[0], text=text))["record"]
    parsed = mutate(store, env, {"requestId": str(uuid4()), "profileVersionId": env.profiles[0],
        "change": {"kind": "parse", "materialId": saved["id"], "expectedVersion": 1}})["record"]
    assert parsed["status"] == "REVIEW_REQUIRED" and parsed["version"] == 2
    confirmed = mutate(store, env, {"requestId": str(uuid4()), "profileVersionId": env.profiles[0],
        "change": {"kind": "confirm", "materialId": saved["id"], "expectedVersion": 2,
                   "extractionId": parsed["extraction"]["id"], "fields": {"service": " 制造业线索 "}}})["record"]
    assert confirmed["status"] == "READY" and confirmed["version"] == 3
    assert confirmed["extraction"]["fields"] == {"service": " 制造业线索 "}
    impact = store.impact(env.claims[0], env.profiles[0], saved["id"], 3, "revoke")
    assert impact["references"] == []
    revoked = mutate(store, env, {"requestId": str(uuid4()), "profileVersionId": env.profiles[0],
        "change": {"kind": "revoke", "materialId": saved["id"], "expectedVersion": 3,
                   "impactToken": impact["token"]}})["record"]
    assert revoked["status"] == "REVOKED" and revoked["version"] == 4
    assert revoked["extraction"]["materialVersion"] == 4
    removal = store.impact(env.claims[0], env.profiles[0], saved["id"], 4, "remove")
    receipt = mutate(store, env, {"requestId": str(uuid4()), "profileVersionId": env.profiles[0],
        "change": {"kind": "remove", "materialId": saved["id"], "expectedVersion": 4,
                   "impactToken": removal["token"]}})
    assert receipt["status"] == "SUCCEEDED" and "record" not in receipt
    assert store.list(env.claims[0], env.profiles[0]) == []
    with env.admin.connect() as conn:
        assert conn.execute("SELECT count(*) FROM pilot_material_revisions WHERE tenant_id=%s AND owner_user_id=%s AND material_id=%s",
                            (env.tenant, env.users[0], saved["id"])).fetchone()[0] == 5
