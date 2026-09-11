"""Material profile to strategy authority, restricted local PG; no external AI/platform."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from psycopg import sql

from pilot.execution_contract import ExecutionRuntimeError
from pilot.research_strategies import ResearchStrategyStore
from pilot.store import PilotStore
from tests.test_materials_store import database, env, mutate
from tests.test_material_profile_references import _ready, DESCRIPTION
from tests.test_research_strategies_postgres import prepare_body, confirm_body, revoke_body


def authority(env):
    from pathlib import Path
    with env.admin.connect() as conn:
        role=sql.Identifier(env.db.role)
        conn.execute(sql.SQL('GRANT SELECT ON business_profiles TO {}').format(role))
        conn.execute(sql.SQL('GRANT UPDATE(name) ON business_profiles TO {}').format(role))
        conn.execute(sql.SQL('GRANT UPDATE(status) ON business_profile_versions TO {}').format(role))
        conn.execute("SELECT set_config('yike.app_role',%s,true)",(env.db.role,))
        conn.execute((Path(__file__).parents[1]/'deploy/grant_research_strategies.sql').read_text())
    return ResearchStrategyStore(env.db)


def adopted(env):
    materials,source,record=_ready(env)
    profiles=PilotStore(env.admin)
    saved=profiles.save_profile(env.users[0],{'description':DESCRIPTION},material_references=[{
        'field':'service','sourceProfileVersionId':source,'materialId':record['id'],
        'materialVersion':record['version'],'extractionId':record['extraction']['id']}])
    profiles.confirm_profile(env.users[0],saved['version_id'])
    return saved,materials,source,record


def ready_strategy(env,profile):
    store=authority(env)
    request=prepare_body(SimpleNamespace(profile=profile))
    prepared=store.prepare(env.claims[0],request)
    confirmed=store.confirm(env.claims[0],confirm_body(prepared))
    return store,confirmed


def test_material_profile_reaches_confirmed_strategy_and_readonly_snapshot(env):
    saved,_,_,_=adopted(env)
    store,confirmed=ready_strategy(env,saved['version_id'])
    with env.db.connect() as conn,conn.cursor() as cursor:
        resolved=store.resolve(cursor,env.claims[0],saved['version_id'],confirmed['strategy_version_id'])
        assert resolved.configuration_sha256==confirmed['configuration_sha256']
    with env.db.connect() as conn,conn.cursor() as cursor:
        cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        cursor.execute("SELECT set_config('yike.user_id',%s,true),set_config('yike.tenant_id',%s,true)",(env.users[0],env.tenant))
        snapshot=store.read_snapshot(cursor,env.claims[0],saved['version_id'],confirmed['strategy_version_id'])
        assert snapshot['configuration_sha256']==confirmed['configuration_sha256']


@pytest.mark.parametrize('managed',[False,True])
def test_manual_and_legacy_profiles_remain_usable(env,managed):
    profiles=PilotStore(env.admin)
    saved=profiles.save_profile(env.users[0],{'description':DESCRIPTION},**({'material_references':[]} if managed else {}))
    profiles.confirm_profile(env.users[0],saved['version_id'])
    _,confirmed=ready_strategy(env,saved['version_id'])
    assert confirmed['state']=='CONFIRMED'


def test_revocation_preserves_receipt_but_stops_new_strategy_use(env):
    saved,materials,source,record=adopted(env)
    store,confirmed=ready_strategy(env,saved['version_id'])
    impact=materials.impact(env.claims[0],source,record['id'],record['version'],'revoke')
    result=mutate(materials,env,{'requestId':str(uuid4()),'profileVersionId':source,
        'change':{'kind':'revoke','materialId':record['id'],'expectedVersion':record['version'],'impactToken':impact['token']}})
    assert result['status']=='SUCCEEDED'
    assert store.get_receipt(env.claims[0],confirmed['request_id'])==confirmed
    assert store.get_strategy(env.claims[0],confirmed['strategy_version_id'])['profile_current'] is False
    with env.db.connect() as conn,conn.cursor() as cursor,pytest.raises(ExecutionRuntimeError):
        store.resolve(cursor,env.claims[0],saved['version_id'],confirmed['strategy_version_id'])
    assert store.revoke(env.claims[0],revoke_body(confirmed))['state']=='REVOKED'
