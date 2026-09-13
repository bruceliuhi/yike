"""Durable host effects on disposable restricted PG; synthetic providers only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC,datetime
import importlib.util
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

import psycopg
import pytest

from pilot.execution_contract import ExecutionRuntimeError
from tests.test_customer_research_context_postgres import (
    context_env,real_strategy_env,databases,env,execution_databases,execution_env,
    raw_databases,raw_env,dynamic_start,load,
)
from tests.test_research_resources_postgres import store
from tests.test_research_runtime_postgres import _grant_runtime
from tests.test_execution_runtime_postgres import apply,operation
from tests.test_execution_runtime_postgres import SECRET
from pilot.auth import issue_token,verify_token_claims
from pilot.durable_research_dispatch import DurableResearchDispatcher
from pilot.research_effects import dispatch_effect,EffectDispatchError
from tests.test_research_effect_contract import model_payload,model_result

ROOT=Path(__file__).parents[1]


def test_journal_exists():
    assert importlib.util.find_spec('pilot.research_effect_journal') is not None


def known_failure():
    return {'status':'FAILED','code':'not_found','replayed':False}


@pytest.mark.parametrize('code', ['not_found', 'unsupported_media_type', 'too_large', 'connection_unavailable'])
def test_known_failed_read_atomic_finish_replay_and_next_url(journal_env, code):
    env=journal_env; payload={'url':'https://example.com/missing'}
    failure=known_failure() | {'code':code}
    entry=begin(env,kind='READ',payload=payload)['entry']
    final=finish(env,entry,'FAILED',failure)
    assert final['result']==failure and final['output_sha256']
    assert states(env)==[('FAILED','FAILED')]
    assert finish(env,entry,'FAILED',failure)==final
    assert begin(env,kind='READ',payload=payload)=={'created':False,'entry':final}
    with pytest.raises(ExecutionRuntimeError):
        begin(env,sequence=2,kind='READ',payload=payload)
    assert counts(env)==(1,1)
    assert begin(env,sequence=2,kind='READ',payload={'url':'https://example.com/other'})['created']


def test_deferred_one_sided_failed_hash_rolls_back(journal_env):
    env=journal_env; entry=begin(env,kind='READ',payload={'url':'https://example.com/missing'})['entry']
    updated=[]
    with pytest.raises(psycopg.Error):
        with env.db.connect() as connection:
            env.runtime._active(connection.cursor(),env.claims)
            connection.execute("UPDATE pilot_research_resource_events SET status='FAILED',output_sha256=%s "
                'WHERE permit_id=%s',('b'*64,entry['permit_id']))
            updated.append(True)  # Must fail at commit, not before journal can be updated.
    assert updated==[True]
    assert states(env)==[('ISSUED','ISSUED')]


def test_connection_failure_survives_migration_rerun(journal_env):
    env=journal_env
    entry=begin(env,kind='READ',payload={'url':'https://example.com/unreachable'})['entry']
    final=finish(env,entry,'FAILED',known_failure() | {'code':'connection_unavailable'})
    env.admin.migrate()
    assert states(env)==[('FAILED','FAILED')]
    assert begin(env,kind='READ',payload=entry['payload'])['entry']==final


def test_migration_checksum_mismatch_rolls_back_new_work(databases, tmp_path, monkeypatch):
    admin, _=databases
    name='synthetic_migration_'+uuid4().hex
    added=tmp_path/'added.sql'
    added.write_text(f'CREATE TABLE {name} (id INTEGER)',encoding='utf-8')
    changed=tmp_path/'changed.sql'
    changed.write_text('SELECT 1',encoding='utf-8')
    original_version=admin.migration_paths[0][0]
    monkeypatch.setattr(admin,'migration_paths',((name,added),(original_version,changed)))
    with pytest.raises(RuntimeError,match='migration checksum mismatch'):
        admin.migrate()
    with admin.connect() as connection:
        assert connection.execute('SELECT to_regclass(%s)',(name,)).fetchone()[0] is None
        assert connection.execute('SELECT 1 FROM pilot_schema_meta WHERE version=%s',(name,)).fetchone() is None


@pytest.mark.parametrize('change',['cancel','profile','lease'])
def test_known_read_replay_and_next_remain_authority_bound(journal_env,change):
    env=journal_env; payload={'url':'https://example.com/missing'}
    entry=begin(env,kind='READ',payload=payload)['entry']
    finish(env,entry,'FAILED',known_failure())
    if change=='cancel': apply(env,operation(env,'CANCEL',env.execution))
    else:
        with env.admin.connect() as connection:
            if change=='profile': connection.execute("UPDATE business_profile_versions SET status='REVOKED' WHERE profile_version_id=%s",(env.profile,))
            else: connection.execute("UPDATE pilot_research_runtime SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE tenant_id=%s",(env.tenant,))
    with pytest.raises(ExecutionRuntimeError): begin(env,kind='READ',payload=payload)
    with pytest.raises(ExecutionRuntimeError): begin(env,sequence=2)
    assert counts(env)==(1,1)


@pytest.mark.parametrize('status',['FAILED','UNKNOWN'])
def test_legacy_read_failure_still_blocks_next_effect(journal_env,status):
    env=journal_env
    entry=begin(env,kind='READ',payload={'url':'https://example.com/missing'})['entry']
    finish(env,entry,status)
    with pytest.raises(ExecutionRuntimeError): begin(env,sequence=2)
    assert counts(env)==(1,1)


def test_normal_resource_finish_cannot_write_failed_hash(journal_env):
    env=journal_env; entry=begin(env,kind='READ',payload={'url':'https://example.com/missing'})['entry']
    with pytest.raises(ExecutionRuntimeError,match='invalid_request'):
        env.resources.finish(env.claims,task_id=entry['task_id'],run_id=entry['run_id'],
            action_id=entry['action_id'],permit_id=entry['permit_id'],status='FAILED',output_sha256='b'*64)
    assert states(env)==[('ISSUED','ISSUED')]


@pytest.mark.parametrize('kind,patch',[
    ('SEARCH',{}),('MODEL',{}),('READ',{'extra':True}),
    ('READ',{'code':'access_restricted'}),('READ',{'code':'unavailable'}),
    ('READ',{'replayed':True}),
])
def test_journal_rejects_wrong_kind_or_nonexact_failed_result(journal_env,kind,patch):
    env=journal_env
    payload=model_payload() if kind=='MODEL' else {'url':'https://example.com/missing'} if kind=='READ' else None
    entry=begin(env,kind=kind,payload=payload)['entry']
    with pytest.raises(ExecutionRuntimeError): finish(env,entry,'FAILED',known_failure()|patch)
    assert states(env)==[('ISSUED','ISSUED')]


def test_known_failed_receipt_replay_has_no_io_and_new_sequence_same_url_closes(journal_env):
    env=journal_env; calls=[]; payload={'url':'https://example.com/missing'}
    first=dispatcher(env)
    assert first('READ',payload,time.monotonic()+20,lambda _:calls.append('READ') or known_failure())==known_failure()
    replay=dispatcher(env)
    assert replay('READ',payload,time.monotonic()+20,lambda _:pytest.fail('replay I/O'))==known_failure()
    with pytest.raises(EffectDispatchError):
        replay('READ',payload,time.monotonic()+20,lambda _:pytest.fail('new-sequence retry'))
    with pytest.raises(EffectDispatchError):
        replay('SEARCH',{'query':'另一个来源'},time.monotonic()+20,lambda _:pytest.fail('closed dispatcher'))
    assert calls==['READ'] and counts(env)==(1,1)


def test_known_failure_committed_ack_loss_never_repeats(journal_env,monkeypatch):
    env=journal_env; gateway=dispatcher(env); calls=[]; finishes=[]; original=env.journal.finish
    def lose(*args,**kwargs):
        original(*args,**kwargs); finishes.append(True)
        raise ConnectionError('synthetic acknowledgement loss')
    monkeypatch.setattr(env.journal,'finish',lose)
    with pytest.raises(EffectDispatchError):
        gateway('READ',{'url':'https://example.com/missing'},time.monotonic()+20,
            lambda _:calls.append('READ') or known_failure())
    with pytest.raises(EffectDispatchError):
        gateway('READ',{'url':'https://example.com/other'},time.monotonic()+20,
            lambda _:pytest.fail('no I/O after uncertain finish'))
    assert calls==['READ'] and finishes==[True] and states(env)==[('FAILED','FAILED')]


@pytest.mark.parametrize('tamper',['resource','action_id','input_sha256','output_sha256','status','run_id','result','payload','context'])
def test_prior_failure_predicate_binds_complete_receipt(journal_env,tamper):
    from pilot.research_resources import _event
    import copy
    env=journal_env; entry=begin(env,kind='READ',payload={'url':'https://example.com/missing'})['entry']
    entry=finish(env,entry,'FAILED',known_failure())
    with env.db.connect() as connection:
        cursor=connection.cursor(); tenant=env.runtime._active(cursor,env.claims)
        event=_event(env.resources._select(cursor,tenant,env.claims.user_id,entry['task_id'],entry['run_id'],entry['action_id']))
    assert env.journal.prior_effect_valid(entry,event)
    bad=copy.deepcopy(entry)
    if tamper=='result': bad['result']['extra']=True
    elif tamper=='payload': bad['payload']['url']='https://example.com/other'
    elif tamper=='context': bad['context_binding']['context_sha256']='f'*64
    elif tamper=='resource': event['resource']='MODEL_CALL'
    elif tamper=='status': event['status']='SUCCEEDED'
    else: event[tamper]='a'*64 if tamper.endswith('sha256') else str(uuid4())
    assert not env.journal.prior_effect_valid(bad,event)


def test_corrupt_paired_digest_blocks_new_effect_and_dynamic_stop(journal_env):
    from pilot.dynamic_research_runtime import DynamicResearchRuntimeService
    from types import SimpleNamespace
    env=journal_env; entry=begin(env,kind='READ',payload={'url':'https://example.com/missing'})['entry']
    # Synthetic corrupt storage: shape and two-table pairing match, content digest does not.
    with env.db.connect() as connection:
        cursor=connection.cursor(); tenant=env.runtime._active(cursor,env.claims)
        cursor.execute("UPDATE pilot_research_resource_events SET status='FAILED',output_sha256=%s WHERE permit_id=%s",('b'*64,entry['permit_id']))
        cursor.execute("UPDATE pilot_research_effect_journal SET status='FAILED',result=%s::jsonb,output_sha256=%s WHERE permit_id=%s",
            (json.dumps(known_failure()),'b'*64,entry['permit_id']))
    with pytest.raises(ExecutionRuntimeError): begin(env,sequence=2)
    with pytest.raises(ExecutionRuntimeError): begin(env,kind='READ',payload=entry['payload'])
    with env.db.connect() as connection:
        cursor=connection.cursor(); tenant=env.runtime._active(cursor,env.claims)
        assert DynamicResearchRuntimeService._effect_stop(SimpleNamespace(journal=env.journal),cursor,tenant,
            env.claims.user_id,entry['task_id'],entry['run_id'])=='effect_failed'
    assert counts(env)==(1,1)


@pytest.fixture
def journal_env(context_env):
    from pilot.research_effect_journal import ResearchEffectJournal
    env=context_env; _grant_runtime(env)
    with env.db.connect() as connection: role=connection.execute('SELECT current_user').fetchone()[0]
    with env.admin.connect() as connection:
        connection.execute("SELECT set_config('yike.app_role',%s,true)",(role,))
        connection.execute((ROOT/'deploy/grant_research_effect_journal.sql').read_text())
    env.execution=dynamic_start(env)
    env.compiled=load(env,env.execution)
    env.owner=str(uuid4())
    with env.admin.connect() as connection:
        connection.execute("INSERT INTO pilot_research_runtime(tenant_id,owner_user_id,task_id,run_id,"
            "generation,current_owner,lease_expires_at,phase) VALUES (%s,%s,%s,%s,1,%s,clock_timestamp()+interval '5 minutes','RUNNING')",
            (env.tenant,env.claims.user_id,env.execution['task_id'],env.execution['run_id'],env.owner))
    env.resources=store(env); env.journal=ResearchEffectJournal(env.resources)
    yield env
    with env.admin.connect() as connection:
        connection.execute('DELETE FROM pilot_research_effect_journal WHERE tenant_id=%s',(env.tenant,))
        connection.execute('DELETE FROM pilot_research_runtime WHERE tenant_id=%s',(env.tenant,))


def begin(env,sequence=1,kind='SEARCH',payload=None,**changes):
    values=dict(task_id=env.execution['task_id'],run_id=env.execution['run_id'],sequence=sequence,
        generation=1,coordinator_owner=env.owner,context_binding=env.compiled['binding'],kind=kind,
        payload=payload or {'query':'企业知识库 找团队'})
    return env.journal.begin(env.claims,**(values|changes))


def result(query='企业知识库 找团队'):
    return dict(status='SEARCHED',query=query,observed_at=datetime.now(UTC).isoformat(),
        read_scope='SEARCH_RESULTS',results=[dict(url='https://example.com/need',title='项目需求',
        snippet='摘要不是原文',date_hint=None,rank=1)],omitted_count=0,replayed=False)


def finish(env,entry,status='SUCCEEDED',value=None):
    return env.journal.finish(env.claims,task_id=entry['task_id'],run_id=entry['run_id'],
        sequence=entry['sequence'],permit_id=entry['permit_id'],status=status,
        result=value if value is not None else result() if status=='SUCCEEDED' else None)


def counts(env):
    with env.admin.connect() as connection:
        return tuple(connection.execute(f'SELECT count(*) FROM {table} WHERE tenant_id=%s',(env.tenant,)).fetchone()[0]
            for table in ('pilot_research_resource_events','pilot_research_effect_journal'))


def test_atomic_issue_finish_replay_and_input_conflict(journal_env):
    env=journal_env
    with ThreadPoolExecutor(2) as pool: grants=list(pool.map(lambda _:begin(env),range(2)))
    assert sorted(g['created'] for g in grants)==[False,True]
    assert grants[0]['entry']==grants[1]['entry']
    assert counts(env)==(1,1)
    entry=grants[0]['entry']; value=result()
    final=finish(env,entry,value=value)
    assert final['status']=='SUCCEEDED' and final['result']==value
    assert finish(env,entry,value=value)==final
    assert begin(env)=={'created':False,'entry':final}
    with pytest.raises(ExecutionRuntimeError): begin(env,payload={'query':'更换输入'})
    assert counts(env)==(1,1)


@pytest.mark.parametrize('reason',['generation','owner','lease','cancel','profile','context','gap'])
def test_invalid_admission_has_no_new_permits(journal_env,reason):
    env=journal_env; changes={}
    if reason=='generation': changes['generation']=2
    elif reason=='owner': changes['coordinator_owner']=str(uuid4())
    elif reason=='context': changes['context_binding']=env.compiled['binding']|{'context_sha256':'a'*64}
    elif reason=='gap': changes['sequence']=2
    elif reason=='cancel': apply(env,operation(env,'CANCEL',env.execution))
    else:
        with env.admin.connect() as connection:
            if reason=='lease': connection.execute("UPDATE pilot_research_runtime SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE tenant_id=%s",(env.tenant,))
            if reason=='profile': connection.execute("UPDATE business_profile_versions SET status='REVOKED' WHERE profile_version_id=%s",(env.profile,))
    with pytest.raises(ExecutionRuntimeError): begin(env,**changes)
    assert counts(env)==(0,0)


def test_unknown_occupies_unit_and_no_following_sequence(journal_env):
    env=journal_env; entry=begin(env)['entry']; final=finish(env,entry,'UNKNOWN')
    assert final['status']=='UNKNOWN' and final['result'] is None
    assert begin(env)['created'] is False
    with pytest.raises(ExecutionRuntimeError): begin(env,sequence=2)
    assert counts(env)==(1,1)


def test_cancel_preserves_admitted_facts_but_blocks_replay_and_next(journal_env):
    env=journal_env; entry=begin(env)['entry']
    apply(env,operation(env,'CANCEL',env.execution))
    assert finish(env,entry)['status']=='SUCCEEDED'
    with pytest.raises(ExecutionRuntimeError): begin(env)
    with pytest.raises(ExecutionRuntimeError): begin(env,sequence=2)
    assert counts(env)==(1,1)


def test_source_budget_exhaustion_has_no_extra_journal(journal_env):
    env=journal_env
    for sequence in range(1,11): finish(env,begin(env,sequence=sequence)['entry'])
    with pytest.raises(ExecutionRuntimeError,match='resource_limit_exceeded'): begin(env,sequence=11)
    assert counts(env)==(10,10)


@pytest.mark.parametrize('cancel_after_limit', [False, True])
def test_source_admission_limit_keeps_other_resource_admission_authoritative(journal_env, cancel_after_limit):
    env=journal_env; gateway=dispatcher(env)
    for _ in range(10):
        gateway('SEARCH', {'query':'企业知识库 找团队'}, time.monotonic()+30, lambda _:result())
    for _ in range(2):
        with pytest.raises(EffectDispatchError):
            gateway('SEARCH', {'query':'另一查询'}, time.monotonic()+30,
                    lambda _:pytest.fail('exhausted source must never perform'))
    assert counts(env)==(10,10)
    if cancel_after_limit:
        apply(env,operation(env,'CANCEL',env.execution))
        with pytest.raises(EffectDispatchError):
            gateway('MODEL',model_payload(),time.monotonic()+30,
                    lambda _:pytest.fail('cancellation must still block'))
        assert counts(env)==(10,10)
    else:
        assert gateway('MODEL',model_payload(),time.monotonic()+30,
                       lambda _:model_result())==model_result()
        assert counts(env)==(11,11)
        with env.admin.connect() as connection:
            assert connection.execute('SELECT sequence,kind FROM pilot_research_effect_journal '
                'WHERE tenant_id=%s ORDER BY sequence DESC LIMIT 1',(env.tenant,)).fetchone()==(11,'MODEL')


@pytest.mark.parametrize('change',['capability','rule'])
def test_replay_requires_current_resource_authority(journal_env,change):
    env=journal_env; finish(env,begin(env)['entry'])
    if change=='capability': env.resources.research_capability=lambda _snapshot:False
    else:
        from pilot.research_quote import ResearchQuoteRule
        env.resources.rule=ResearchQuoteRule('changed-rule-v1',100,200,300)
    with pytest.raises(ExecutionRuntimeError): begin(env)
    assert counts(env)==(1,1)


def dispatcher(env):
    return DurableResearchDispatcher(env.journal,env.claims,task_id=env.execution['task_id'],
        run_id=env.execution['run_id'],generation=1,coordinator_owner=env.owner,
        context_binding=env.compiled['binding'])


def states(env):
    with env.admin.connect() as connection:
        return connection.execute('SELECT e.status,j.status FROM pilot_research_resource_events e '
            'JOIN pilot_research_effect_journal j USING(tenant_id,owner_user_id,permit_id) '
            'WHERE e.tenant_id=%s ORDER BY j.sequence',(env.tenant,)).fetchall()


def test_gateway_model_search_read_persist_before_io_and_replay_without_io(journal_env):
    env=journal_env; gateway=dispatcher(env); calls=[]
    text='客户原文：我们需要企业资料检索与出处引用，想找团队做一期。'
    page=dict(status='READ',evidence=dict(url='https://example.com/need',title='需求原文',text=text,
        observed_at=datetime.now(UTC).isoformat(),content_sha256=hashlib.sha256(text.encode()).hexdigest(),
        read_scope='PUBLIC_PAGE_TEXT'),review_status='UNREVIEWED',replayed=False)
    effects=[('MODEL',model_payload(),model_result()),
             ('SEARCH',{'query':'企业知识库 找团队'},result()),
             ('READ',{'url':'https://example.com/need'},page)]
    for sequence,(kind,payload,value) in enumerate(effects,1):
        outer=time.monotonic()+30
        def perform(deadline):
            # A second real connection sees both records before synthetic I/O.
            assert states(env)==[('SUCCEEDED','SUCCEEDED')]*(sequence-1)+[('ISSUED','ISSUED')]
            assert time.monotonic()<deadline<=outer
            calls.append(kind)
            return value
        assert dispatch_effect(gateway,kind=kind,payload=payload,deadline=outer,perform=perform)==value
    with env.admin.connect() as connection:
        rows=connection.execute('SELECT kind,result FROM pilot_research_effect_journal '
            'WHERE tenant_id=%s ORDER BY sequence',(env.tenant,)).fetchall()
        assert rows==[(kind,value) for kind,_payload,value in effects]
        assert connection.execute('SELECT resource,count(*) FROM pilot_research_resource_events '
            'WHERE tenant_id=%s GROUP BY resource ORDER BY resource',(env.tenant,)).fetchall()==[
                ('MODEL_CALL',1),('SOURCE_READ',2)]
    # Same generation/scope replay uses persisted complete results, no new network operation.
    replay=dispatcher(env)
    for kind,payload,value in effects:
        assert dispatch_effect(replay,kind=kind,payload=payload,deadline=time.monotonic()+30,
            perform=lambda _deadline:pytest.fail('replay must not call provider'))==value
    assert calls==['MODEL','SEARCH','READ'] and counts(env)==(3,3)


def test_invalid_provider_result_is_unknown_and_stops_dispatcher(journal_env):
    env=journal_env; gateway=dispatcher(env); calls=[]
    def invalid(_deadline):
        calls.append('io'); return {'status':'FAILED','code':'unavailable'}
    for _ in range(2):
        with pytest.raises(EffectDispatchError):
            dispatch_effect(gateway,kind='SEARCH',payload={'query':'企业知识库 找团队'},
                deadline=time.monotonic()+30,perform=invalid)
    assert calls==['io'] and states(env)==[('UNKNOWN','UNKNOWN')]
    with pytest.raises(EffectDispatchError):
        dispatch_effect(dispatcher(env),kind='SEARCH',payload={'query':'企业知识库 找团队'},
            deadline=time.monotonic()+30,perform=invalid)
    assert calls==['io'] and counts(env)==(1,1)


def test_committed_finish_with_lost_ack_never_retries_effect_or_finish(journal_env,monkeypatch):
    env=journal_env; gateway=dispatcher(env); calls=[]; finishes=[]
    original=env.journal.finish
    def lost_ack(claims,**kwargs):
        original(claims,**kwargs)  # The actual PG commit succeeded before transport uncertainty.
        finishes.append('committed')
        raise ConnectionError('synthetic lost acknowledgement')
    monkeypatch.setattr(env.journal,'finish',lost_ack)
    for _ in range(2):
        with pytest.raises(EffectDispatchError):
            dispatch_effect(gateway,kind='SEARCH',payload={'query':'企业知识库 找团队'},
                deadline=time.monotonic()+30,perform=lambda _deadline:calls.append('io') or result())
    assert calls==['io'] and finishes==['committed']
    assert states(env)==[('SUCCEEDED','SUCCEEDED')] and counts(env)==(1,1)


def test_issued_hook_failure_rolls_back_both_records(journal_env,monkeypatch):
    env=journal_env; original=env.resources.begin
    def failing(claims,**kwargs):
        callback=kwargs['_on_issued']
        def issued(cursor,tenant,event):
            callback(cursor,tenant,event)
            cursor.execute('SELECT count(*) FROM pilot_research_effect_journal WHERE tenant_id=%s',(tenant,))
            assert cursor.fetchone()[0]==1
            raise ValueError('synthetic-hook-failure')
        return original(claims,**(kwargs|{'_on_issued':issued}))
    monkeypatch.setattr(env.resources,'begin',failing)
    with pytest.raises(ExecutionRuntimeError,match='^resource_unavailable$'): begin(env)
    assert counts(env)==(0,0)


def test_resource_issued_hook_only_fresh_and_invalid_hook_before_db(journal_env,monkeypatch):
    env=journal_env; calls=[]
    args=dict(task_id=env.execution['task_id'],run_id=env.execution['run_id'],action_id=str(uuid4()),
        resource='SOURCE_READ',input_sha256='a'*64,_on_issued=lambda _c,_t,e:calls.append(e['permit_id']))
    first=env.resources.begin(env.claims,**args)
    assert env.resources.begin(env.claims,**args)==first|{'created':False}
    assert calls==[first['event']['permit_id']] and counts(env)==(1,0)
    monkeypatch.setattr(env.runtime.database,'connect',lambda:pytest.fail('invalid callback must not open DB'))
    with pytest.raises(ExecutionRuntimeError,match='invalid_request'):
        env.resources.begin(env.claims,**(args|{'_on_issued':True}))


def test_journal_result_failure_rolls_back_resource_finish(journal_env):
    env=journal_env; entry=begin(env)['entry']; value=result()
    with env.admin.connect() as connection:
        connection.execute("ALTER TABLE pilot_research_effect_journal ADD CONSTRAINT synthetic_finish_failure CHECK(status<>'SUCCEEDED') NOT VALID")
    try:
        with pytest.raises(ExecutionRuntimeError): finish(env,entry,value=value)
        assert states(env)==[('ISSUED','ISSUED')]
    finally:
        with env.admin.connect() as connection:
            connection.execute('ALTER TABLE pilot_research_effect_journal DROP CONSTRAINT synthetic_finish_failure')
    assert finish(env,entry,value=value)['result']==value


def test_final_session_check_rolls_back_both_results(journal_env,monkeypatch):
    env=journal_env; entry=begin(env)['entry']; original=env.runtime._active
    def revoked(cursor,claims):
        tenant=original(cursor,claims)
        cursor.execute('SELECT status FROM pilot_research_effect_journal WHERE permit_id=%s',(entry['permit_id'],))
        if cursor.fetchone()[0]!='ISSUED': raise ExecutionRuntimeError('invalid_session',401)
        return tenant
    monkeypatch.setattr(env.runtime,'_active',revoked)
    with pytest.raises(ExecutionRuntimeError,match='invalid_session'): finish(env,entry)
    assert states(env)==[('ISSUED','ISSUED')]


@pytest.mark.parametrize('change',['lease','generation','profile','strategy'])
def test_authority_change_after_issue_allows_closeout_only(journal_env,change):
    env=journal_env; entry=begin(env)['entry']
    if change=='strategy':
        from tests.test_research_strategies_postgres import revoke_body
        env.strategies.revoke(env.claims,revoke_body(env.confirmed))
    else:
        with env.admin.connect() as connection:
            if change=='lease': connection.execute("UPDATE pilot_research_runtime SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE tenant_id=%s",(env.tenant,))
            elif change=='generation': connection.execute('UPDATE pilot_research_runtime SET generation=2 WHERE tenant_id=%s',(env.tenant,))
            else: connection.execute("UPDATE business_profile_versions SET status='REVOKED' WHERE profile_version_id=%s",(env.profile,))
    assert finish(env,entry)['status']=='SUCCEEDED'
    with pytest.raises(ExecutionRuntimeError): begin(env)
    with pytest.raises(ExecutionRuntimeError): begin(env,sequence=2)
    assert counts(env)==(1,1)


def test_cross_owner_rls_and_immutable_payload_terminal_result(journal_env):
    env=journal_env; entry=begin(env)['entry']; final=finish(env,entry)
    for user in env.users[1:]:
        claims=verify_token_claims(issue_token(user,SECRET),SECRET)
        with pytest.raises(ExecutionRuntimeError):
            env.journal.finish(claims,task_id=entry['task_id'],run_id=entry['run_id'],sequence=1,
                permit_id=entry['permit_id'],status='UNKNOWN')
        with env.db.connect() as connection:
            connection.execute("SELECT set_config('yike.tenant_id',%s,true),set_config('yike.user_id',%s,true)",
                (env.tenant,user))
            assert connection.execute('SELECT count(*) FROM pilot_research_effect_journal').fetchone()[0]==0
    with env.db.connect() as connection:
        connection.execute("SELECT set_config('yike.tenant_id',%s,true),set_config('yike.user_id',%s,true)",
            (env.tenant,env.claims.user_id))
        for field,value in [('payload','{}'),('result','{}')]:
            with pytest.raises(psycopg.Error):
                with connection.transaction():
                    connection.execute(f'UPDATE pilot_research_effect_journal SET {field}=%s::jsonb WHERE permit_id=%s',
                        (value,entry['permit_id']))
    with pytest.raises(ExecutionRuntimeError): finish(env,entry,value=result('different query'))
    assert begin(env)['entry']==final


@pytest.mark.parametrize('tamper',['kind','context','lease','generation','status'])
def test_database_rejects_forged_journal_binding(journal_env,tamper):
    env=journal_env; entry=begin(env)['entry']
    with env.admin.connect() as connection:
        with connection.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            cursor.execute('SELECT * FROM pilot_research_effect_journal WHERE permit_id=%s',(entry['permit_id'],))
            row=cursor.fetchone()
        connection.execute('DELETE FROM pilot_research_effect_journal WHERE permit_id=%s',(entry['permit_id'],))
    if tamper=='kind': row['kind']='MODEL'
    elif tamper=='context': row['context_binding']['context_sha256']='b'*64
    elif tamper=='lease':
        from datetime import timedelta
        row['deadline_at']+=timedelta(hours=1)
    elif tamper=='generation': row['generation']=2
    else: row['status']='UNKNOWN'
    with pytest.raises(psycopg.Error):
        with env.db.connect() as connection:
            connection.execute("SELECT set_config('yike.tenant_id',%s,true),set_config('yike.user_id',%s,true)",
                (env.tenant,env.claims.user_id))
            columns=list(row)
            connection.execute('INSERT INTO pilot_research_effect_journal ('+','.join(columns)+') VALUES ('+
                ','.join('%s::jsonb' if name in ('payload','context_binding','result') else '%s' for name in columns)+')',
                [json.dumps(row[name]) if name in ('payload','context_binding') else row[name] for name in columns])
