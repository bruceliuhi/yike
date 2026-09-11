import os
from types import SimpleNamespace
from uuid import uuid4

import pytest

from pilot.db import PilotDatabase
from pilot.store import PilotStore
from pilot.ui_api import ProfileInput


@pytest.fixture(scope="module")
def database():
    url = os.environ.get("YIKE_INDEPENDENT_PROFILE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("dedicated independent-profile PostgreSQL required")
    database = PilotDatabase(url)
    database.migrate()
    return database


@pytest.fixture
def env(database):
    store = PilotStore(database)
    tenant = store.provision_tenant("synthetic-independent-profiles")
    user = store.provision_user(tenant, f"{uuid4()}@example.invalid")
    other_tenant = store.provision_tenant("synthetic-independent-profiles-other")
    other_user = store.provision_user(other_tenant, f"{uuid4()}@example.invalid")
    return SimpleNamespace(database=database, store=store, tenant=tenant, user=user,
                           other_tenant=other_tenant, other_user=other_user)


def new_business(name, request_id=None):
    return {"requestId": request_id or str(uuid4()), "name": name}


def test_two_same_content_businesses_are_independent_and_old_tasks_remain(env):
    a = env.store.save_profile(env.user, {"description": "相同业务内容"}, new_business=new_business("业务 A"))
    b = env.store.save_profile(env.user, {"description": "相同业务内容"}, new_business=new_business("业务 B"))
    assert a["profile_id"] != b["profile_id"]
    env.store.confirm_profile(env.user, a["version_id"])
    env.store.confirm_profile(env.user, b["version_id"])
    a2 = env.store.save_profile(env.user, {"description": "业务 A 新版本"}, profile_entity_id=a["profile_id"])
    env.store.confirm_profile(env.user, a2["version_id"])
    assert env.store.get_profile_version(env.user, a["version_id"])["status"] == "REVOKED"
    assert env.store.get_profile_version(env.user, b["version_id"])["status"] == "CONFIRMED"
    assert env.store.get_profile_version(env.user, a2["version_id"])["status"] == "CONFIRMED"
    assert {item["profile_name"] for item in env.store.list_profiles(env.user)} == {"业务 A", "业务 B"}
    with env.database.connect() as connection:
        tasks = connection.execute("SELECT task_key FROM pilot_tasks WHERE tenant_id=%s", (env.tenant,)).fetchall()
    assert {row[0] for row in tasks} == {f"research:{a['version_id']}", f"research:{b['version_id']}",
                                        f"research:{a2['version_id']}"}


def test_new_business_request_is_stable_and_name_change_conflicts(env):
    request_id = str(uuid4())
    first = env.store.save_profile(env.user, {"description": "内容"},
        new_business=new_business("  稳定业务  ", request_id))
    replay = env.store.save_profile(env.user, {"description": "内容"},
        new_business=new_business("稳定业务", request_id))
    assert replay == first and first["profile_name"] == "稳定业务"
    with pytest.raises(ValueError, match="name"):
        env.store.save_profile(env.user, {"description": "内容"},
            new_business=new_business("另一个名称", request_id))


def test_explicit_entity_must_exist_in_tenant_and_base_must_belong_to_target(env):
    a = env.store.save_profile(env.user, {"description": "A"}, new_business=new_business("A"))
    b = env.store.save_profile(env.user, {"description": "B"}, new_business=new_business("B"))
    with pytest.raises(KeyError):
        env.store.save_profile(env.other_user, {"description": "越权"}, profile_entity_id=a["profile_id"])
    with pytest.raises(KeyError):
        env.store.save_profile(env.user, {"description": "不存在"}, profile_entity_id="f" * 32)
    with pytest.raises(ValueError, match="base"):
        env.store.save_profile(env.user, {"description": "A2"}, profile_entity_id=a["profile_id"],
                               base_profile_version_id=b["version_id"], material_references=[])


def test_profile_input_entity_choice_is_strict_and_mutually_exclusive():
    request_id = str(uuid4())
    parsed = ProfileInput(description="内容", newBusiness={"requestId": request_id, "name": "  新业务  "})
    assert parsed.newBusiness == {"requestId": request_id, "name": "新业务"}
    with pytest.raises(ValueError):
        ProfileInput(description="内容", profileEntityId="a" * 32,
                     newBusiness={"requestId": request_id, "name": "新业务"})
    for invalid in ("A" * 32, "arbitrary", "00000000-0000-0000-0000-000000000000"):
        with pytest.raises(ValueError):
            ProfileInput(description="内容", profileEntityId=invalid)
    with pytest.raises(ValueError):
        ProfileInput(description="内容", newBusiness={"requestId": request_id, "name": "bad\x00name"})
