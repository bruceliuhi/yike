"""Customer context contract on disposable restricted PG; no provider calls."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest

from pilot.auth import issue_token, verify_token_claims
from pilot.execution_contract import ExecutionRuntimeError
from pilot.store import PilotStore
from tests.test_candidate_review_postgres import (
    databases, env, execution_databases, execution_env, raw_databases, raw_env, seed,
)
from tests.test_confirmed_strategy_review_postgres import real_strategy_env
from tests.test_research_execution_postgres import services, signed_start
from tests.test_research_quote_postgres import _request
from tests.test_execution_runtime_postgres import SECRET, start, apply, operation
from tests.test_research_strategies_postgres import configuration, prepare_body, confirm_body, revoke_body

ROOT=Path(__file__).parents[1]


def test_customer_context_store_exists():
    assert importlib.util.find_spec('pilot.customer_research_context') is not None


def dynamic_start(env):
    config=configuration(publicSource='public-web-agent-v1',research=dict(version=1,
        demandTypes=['INQUIRY','REPLACEMENT'],maxSoubei=10,
        limits=dict(sources=10,minutes=10,modelCalls=10),stopAtAnyLimit=True,
        evidenceOrder='SOURCE_MATCH_CONTEXT',
        dynamicScope=dict(version=1,maxAgeDays=60,timezone='Asia/Shanghai')))
    pending=env.strategies.prepare(env.claims,prepare_body(env,configuration=config))
    env.confirmed=env.strategies.confirm(env.claims,confirm_body(pending))
    env.snapshot=env.confirmed['snapshot']
    quotes, service=services(env)
    request=start(env)
    quote=quotes.quote(env.claims,_request(env,env.confirmed)|{'requestId':request.request_id})
    return service.start(env.claims,request,signed_start(env,request),quote['authorizationToken'])['execution']


@pytest.fixture
def context_env(real_strategy_env):
    env=real_strategy_env
    with env.db.connect() as connection:
        role=connection.execute('SELECT current_user').fetchone()[0]
    with env.admin.connect() as connection:
        connection.execute("SELECT set_config('yike.app_role',%s,true)",(role,))
        connection.execute((ROOT/'deploy/grant_customer_research_context.sql').read_text())
    return env


def load(env,execution,claims=None):
    from pilot.customer_research_context import CustomerResearchContextStore
    return CustomerResearchContextStore(env.runtime).load(claims or env.claims,
        task_id=execution['task_id'],run_id=execution['run_id'])


def test_customer_snapshot_preserves_multiline_and_replays_without_resource_consumption(context_env):
    env=context_env
    description=('服务内容：企业自动化\n'+'字'*8000)[:8000]
    assert len(description)==8000
    profile=PilotStore(env.admin).save_profile(env.claims.user_id,{'description':description})
    PilotStore(env.admin).confirm_profile(env.claims.user_id,profile['version_id'])
    env.profile=profile['version_id']
    execution=dynamic_start(env)
    first=load(env,execution); parsed=json.loads(first['context_json'])
    assert parsed['seller_description']==description
    assert parsed['schema_version']=='research-context-v2'
    assert parsed['history_scope']=='NONE' and parsed['history']==[]
    assert parsed['strategy_snapshot']==env.snapshot
    assert load(env,execution)==first
    with env.admin.connect() as connection:
        created=connection.execute('SELECT created_at FROM pilot_collection_tasks WHERE task_id=%s',
            (execution['task_id'],)).fetchone()[0]
        assert parsed['reference_time']==created.isoformat()
        assert connection.execute('SELECT count(*) FROM pilot_customer_research_contexts WHERE task_id=%s',
            (execution['task_id'],)).fetchone()[0]==1
        assert connection.execute('SELECT count(*) FROM pilot_research_resource_events WHERE task_id=%s',
            (execution['task_id'],)).fetchone()[0]==0


def test_snapshot_scope_cancel_and_strategy_revocation(context_env):
    env=context_env; execution=dynamic_start(env)
    first=load(env,execution)
    for user in env.users[1:]:
        claims=verify_token_claims(issue_token(user,SECRET),SECRET)
        with pytest.raises(ExecutionRuntimeError): load(env,execution,claims)
    with pytest.raises(ExecutionRuntimeError): load(env,execution|{'run_id':str(uuid4())})
    env.strategies.revoke(env.claims,revoke_body(env.confirmed))
    with pytest.raises(ExecutionRuntimeError): load(env,execution)
    # A new signed task has its own context; cancelled tasks never reload for use.
    other=dynamic_start(env); load(env,other)
    apply(env,operation(env,'CANCEL',other))
    with pytest.raises(ExecutionRuntimeError): load(env,other)
    assert first['binding']['profile_version_id']==env.profile


def test_snapshot_concurrent_load_is_single_and_immutable(context_env):
    env=context_env; execution=dynamic_start(env)
    with ThreadPoolExecutor(max_workers=2) as pool:
        values=list(pool.map(lambda _:load(env,execution),range(2)))
    assert values[0]==values[1]
    with env.admin.connect() as connection:
        assert connection.execute('SELECT count(*) FROM pilot_customer_research_contexts WHERE task_id=%s',
            (execution['task_id'],)).fetchone()[0]==1
    with pytest.raises(psycopg.Error):
        with env.admin.connect() as connection:
            connection.execute("UPDATE pilot_customer_research_contexts SET context='{}'::jsonb WHERE task_id=%s",
                (execution['task_id'],))


def test_history_is_same_business_owner_scoped_known_not_draft_contact(context_env):
    env=context_env
    seed(env,public_url='https://example.com/known',title='制造设备方案',body='具体需求原文')
    execution=dynamic_start(env)
    compiled=load(env,execution)
    parsed=json.loads(compiled['context_json'])
    assert parsed['history_scope']=='PARTIAL'
    assert len(parsed['history'])==1
    assert parsed['history'][0]['state']=='KNOWN'
    assert parsed['history'][0]['source_urls']==['https://example.com/known']
    assert compiled['entry_urls'] == (
        'https://www.v2ex.com/recent',
        'https://www.v2ex.com/go/qna',
        'https://www.v2ex.com/go/outsourcing',
        'https://example.com/known',
    )


def test_profile_revocation_blocks_existing_context(context_env):
    env=context_env; execution=dynamic_start(env); load(env,execution)
    with env.admin.connect() as connection:
        connection.execute("UPDATE business_profile_versions SET status='REVOKED' WHERE profile_version_id=%s",(env.profile,))
    with pytest.raises(ExecutionRuntimeError): load(env,execution)


def snapshot_row(env,execution):
    with env.admin.connect() as connection:
        with connection.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            cursor.execute('SELECT * FROM pilot_customer_research_contexts WHERE task_id=%s',
                (execution['task_id'],))
            return cursor.fetchone()


def insert_snapshot(connection,row):
    values=[json.dumps(value) if name in ('context','binding') else value for name,value in row.items()]
    connection.execute('INSERT INTO pilot_customer_research_contexts ('+','.join(row)+') VALUES ('+
        ','.join('%s::jsonb' if name in ('context','binding') else '%s' for name in row)+')',values)


@pytest.mark.parametrize('tamper',['profile_hash','reference_time','reservation'])
def test_database_rejects_context_not_bound_to_actual_task_and_profile(context_env,tamper):
    env=context_env; execution=dynamic_start(env); load(env,execution)
    row=snapshot_row(env,execution)
    with env.admin.connect() as connection:
        connection.execute('DELETE FROM pilot_customer_research_contexts WHERE task_id=%s',(execution['task_id'],))
    if tamper=='profile_hash':
        row['profile_sha256']='a'*64
        row['context']['profile_sha256']='a'*64
        row['binding']['profile_sha256']='a'*64
    elif tamper=='reference_time': row['context']['reference_time']='2000-01-01T00:00:00+00:00'
    else: row['reservation_id']=str(uuid4())
    with pytest.raises(psycopg.Error):
        with env.admin.connect() as connection: insert_snapshot(connection,row)


def test_rls_hides_other_owner_and_cannot_insert_cross_owner(context_env):
    env=context_env; execution=dynamic_start(env); load(env,execution)
    row=snapshot_row(env,execution)
    with env.db.connect() as connection:
        connection.execute("SELECT set_config('yike.tenant_id',%s,true),set_config('yike.user_id',%s,true)",
            (env.tenant,env.users[1]))
        assert connection.execute('SELECT count(*) FROM pilot_customer_research_contexts').fetchone()[0]==0
        with pytest.raises(psycopg.Error):
            with connection.transaction(): insert_snapshot(connection,row)


def test_stored_binding_tamper_is_rejected_not_repaired(context_env):
    env=context_env; execution=dynamic_start(env); load(env,execution)
    row=snapshot_row(env,execution); row['binding']['context_sha256']='b'*64
    with env.admin.connect() as connection:
        connection.execute('DELETE FROM pilot_customer_research_contexts WHERE task_id=%s',(execution['task_id'],))
        insert_snapshot(connection,row)
    with pytest.raises(ExecutionRuntimeError,match='strategy_conflict'): load(env,execution)
    assert snapshot_row(env,execution)['binding']==row['binding']


def test_invalid_context_rolls_back_and_post_insert_session_revocation_rolls_back(context_env,monkeypatch):
    env=context_env
    profile=PilotStore(env.admin).save_profile(env.claims.user_id,{'description':'服务内容：access_token=synthetic-only'})
    PilotStore(env.admin).confirm_profile(env.claims.user_id,profile['version_id'])
    env.profile=profile['version_id']; execution=dynamic_start(env)
    with pytest.raises(ExecutionRuntimeError): load(env,execution)
    assert snapshot_row(env,execution) is None
    profile=PilotStore(env.admin).save_profile(env.claims.user_id,{'description':'企业流程自动化'})
    PilotStore(env.admin).confirm_profile(env.claims.user_id,profile['version_id'])
    env.profile=profile['version_id']; execution=dynamic_start(env)
    active=env.runtime._active; calls=[]
    def revoked_after_insert(cursor,claims):
        present=cursor.execute('SELECT count(*) FROM pilot_customer_research_contexts WHERE task_id=%s',
            (execution['task_id'],)).fetchone()[0]
        if present:
            calls.append(True)
            raise ExecutionRuntimeError('invalid_session',401)
        return active(cursor,claims)
    monkeypatch.setattr(env.runtime,'_active',revoked_after_insert)
    with pytest.raises(ExecutionRuntimeError,match='invalid_session'): load(env,execution)
    assert len(calls)==1 and snapshot_row(env,execution) is None


def test_material_revocation_blocks_research_context_reload(context_env):
    from tests.test_material_profile_references import _ready,DESCRIPTION
    from tests.test_materials_store import mutate
    env=context_env
    with env.db.connect() as connection: role=connection.execute('SELECT current_user').fetchone()[0]
    with env.admin.connect() as connection:
        connection.execute("SELECT set_config('yike.app_role',%s,true)",(role,))
        connection.execute((ROOT/'deploy/grant_materials.sql').read_text())
    material_env=SimpleNamespace(db=env.db,profiles=[env.profile],claims=[env.claims])
    try:
        materials,source,ready=_ready(material_env)
        profile=PilotStore(env.admin).save_profile(env.claims.user_id,{'description':DESCRIPTION},material_references=[{
            'field':'service','sourceProfileVersionId':source,'materialId':ready['id'],
            'materialVersion':ready['version'],'extractionId':ready['extraction']['id']}])
        PilotStore(env.admin).confirm_profile(env.claims.user_id,profile['version_id'])
        env.profile=profile['version_id']; execution=dynamic_start(env)
        first=load(env,execution)
        assert '我们提供知识库实施。' not in first['context_json']  # Private source text is not exported.
        impact=materials.impact(env.claims,source,ready['id'],ready['version'],'revoke')
        mutate(materials,material_env,{'requestId':str(uuid4()),'profileVersionId':source,
            'change':{'kind':'revoke','materialId':ready['id'],'expectedVersion':ready['version'],
                'impactToken':impact['token']}})
        with pytest.raises(ExecutionRuntimeError): load(env,execution)
        assert snapshot_row(env,execution)['context']==json.loads(first['context_json'])
    finally:
        # Disposable synthetic fixture cleanup; production retains immutable material history.
        with env.admin.connect() as connection:
            for table in ('pilot_material_revisions','pilot_material_operations'):
                connection.execute(f'ALTER TABLE {table} DISABLE TRIGGER {table}_immutable')
            for table in ('pilot_material_profile_references','pilot_material_impact_tokens',
                          'pilot_material_operations','pilot_material_revisions'):
                connection.execute(f'DELETE FROM {table} WHERE tenant_id=%s',(env.tenant,))
            for table in ('pilot_material_revisions','pilot_material_operations'):
                connection.execute(f'ALTER TABLE {table} ENABLE TRIGGER {table}_immutable')
