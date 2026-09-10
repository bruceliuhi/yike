"""Actual authenticated HTTP, Ed25519 and restricted PG; no real platform send."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from psycopg.errors import InsufficientPrivilege, RaiseException
from fastapi.testclient import TestClient
from nacl.signing import SigningKey

from pilot.auth import issue_token, verify_token_claims
from pilot.device_credentials import DeviceCredentialStore
from pilot.runtime import build_runtime_app
from tests.test_contact_drafts_http_postgres import databases as draft_databases, env, execution_databases, SECRET, body, rehash, save
from tests.test_device_credentials_postgres import bind
from tests.test_device_keys import encoded
from tests.test_outreach_context_http_postgres import prepared, context


@pytest.fixture(scope='module')
def databases(draft_databases):
    admin,app=draft_databases
    with admin.connect() as conn:
        conn.execute("SELECT set_config('yike.app_role',%s,true)",(app.role,))
        for name in ('grant_outreach_queue.sql','grant_outreach_dispatch.sql'):
            conn.execute((Path(__file__).parents[1]/'deploy'/name).read_text())
    return admin,app


def request(env):
    context_request,_=prepared(env)
    current=context(env,context_request)
    assert current.status_code==200,current.text
    key=SigningKey.generate()
    claims=verify_token_claims(env.client.headers['Authorization'].removeprefix('Bearer '),SECRET)
    bind(SimpleNamespace(service=DeviceCredentialStore(env.app),claims=claims,device=context_request['deviceId']),key)
    value=dict(requestId=str(uuid4()),context=context_request,contextSha256=current.json()['contextSha256'],
        credentialVersion=1,humanConfirmed=True,channelCheck=dict(status='AVAILABLE',
            observedAt=datetime.now(UTC).isoformat()))
    return value,key


def sign(env,value,key):
    response=env.client.post('/api/ui/outreach/signing-payload',json={'request':value})
    assert response.status_code==200,response.text
    result=response.json()
    return encoded(key.sign(result['signing_payload'].encode()).signature)


def confirm(env,value,signature):
    return env.client.post('/api/ui/outreach/queue',json={'request':value,'signature':signature})


def get(env,value,**kw): return env.client.get('/api/ui/outreach/queue/'+value['requestId'],**kw)


def test_confirm_original_request_restart_and_cancel_without_any_send(env):
    value,key=request(env); signature=sign(env,value,key)
    response=confirm(env,value,signature)
    assert response.status_code==200,response.text
    receipt=response.json()
    assert receipt['state']=='QUEUED' and receipt['requestId']==value['requestId']
    assert receipt['deliveryConfirmed'] is False
    assert get(env,value).json()==receipt
    assert confirm(env,value,signature).json()==receipt
    restarted=TestClient(build_runtime_app(env.app,auth_secret=SECRET,environment={}),base_url='https://pilot.example')
    restarted.headers.update(env.client.headers)
    assert restarted.get('/api/ui/outreach/queue/'+value['requestId']).json()==receipt
    cancelled=env.client.post('/api/ui/outreach/queue/'+value['requestId']+'/cancel')
    assert cancelled.status_code==200 and cancelled.json()['state']=='CANCELLED'
    assert confirm(env,value,signature).json()==cancelled.json()
    assert get(env,value).json()==cancelled.json()
    assert env.client.get('/api/ui/capabilities').json()['capabilities']['outreach']=={'available':False}


def test_new_uuid_does_not_bypass_pending_and_cancel_requires_new_confirmation(env):
    value,key=request(env); signature=sign(env,value,key)
    assert confirm(env,value,signature).status_code==200
    changed=copy.deepcopy(value); changed['requestId']=str(uuid4())
    assert confirm(env,changed,sign(env,changed,key)).status_code==409
    assert env.client.post('/api/ui/outreach/queue/'+value['requestId']+'/cancel').status_code==200
    assert confirm(env,changed,sign(env,changed,key)).status_code==200


@pytest.mark.parametrize('change',['hash','stale-check','human','signature','connection'])
def test_invalid_confirmation_fails_without_queue_write(env,change):
    value,key=request(env)
    if change=='hash': value['contextSha256']='0'*64
    elif change=='stale-check': value['channelCheck']['observedAt']=(datetime.now(UTC)-timedelta(minutes=10)).isoformat()
    elif change=='human': value['humanConfirmed']=False
    signature=sign(env,value,key) if change!='human' else encoded(b'0'*64)
    if change=='signature': signature=encoded(b'0'*64)
    if change=='connection':
        with env.admin.connect() as conn:
            conn.execute("UPDATE pilot_platform_connections SET status='DISCONNECTED' WHERE connection_id=%s",(value['context']['connectionId'],))
    response=confirm(env,value,signature)
    assert response.status_code in (400,409,422),response.text
    assert get(env,value).status_code==404


def test_owner_isolation_and_old_signature_cannot_be_used_by_another_session(env):
    value,key=request(env); signature=sign(env,value,key)
    original_auth=env.client.headers['Authorization']
    env.client.headers['Authorization']='Bearer '+issue_token(env.users[0],SECRET)
    assert confirm(env,value,signature).status_code==400
    assert confirm(env,value,sign(env,value,key)).status_code==200
    env.client.headers['Authorization']=original_auth
    for user in env.users[1:]:
        headers={'Authorization':'Bearer '+issue_token(user,SECRET)}
        assert get(env,value,headers=headers).status_code==404
        assert env.client.post('/api/ui/outreach/queue/'+value['requestId']+'/cancel',headers=headers).status_code==404


def test_same_request_concurrency_and_changed_binding_history(env):
    value,key=request(env); signature=sign(env,value,key)
    with ThreadPoolExecutor(max_workers=3) as pool:
        receipts=list(pool.map(lambda _:confirm(env,value,signature),range(3)))
    assert [r.status_code for r in receipts]==[200,200,200]
    assert receipts[0].json()==receipts[1].json()==receipts[2].json()
    changed=copy.deepcopy(value); changed['channelCheck']['observedAt']=datetime.now(UTC).isoformat()
    assert confirm(env,changed,sign(env,changed,key)).status_code==409
    with env.app.connect() as conn:
        assert conn.execute('SELECT count(*) FROM pilot_outreach_queue').fetchone()==(0,)


def test_latest_draft_rechecked_but_original_receipt_survives_later_edit(env):
    value,key=request(env); signature=sign(env,value,key)
    old=env.client.get(f'/api/ui/opportunities/{env.opp}/contact-drafts/dm').json()['snapshot']['draft']
    update=body(env,content='新版人工短句',saved=old['content'],version=old['version']+1,
        previous=value['context']['binding']['requestId'])
    update['snapshot']['draft'].update(accountId=old['accountId'],recipient=old['recipient'])
    rehash(update)
    saved=save(env,update)
    assert saved.status_code==200,saved.text
    assert confirm(env,value,signature).status_code==409
    assert get(env,value).status_code==404
    value['context']['binding']=update['binding']
    value['contextSha256']=context(env,value['context']).json()['contextSha256']
    signature=sign(env,value,key)
    receipt=confirm(env,value,signature)
    assert receipt.status_code==200
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_sources SET health='BLOCKED' WHERE source_id=%s",(env.source,))
    assert confirm(env,value,signature).json()==receipt.json()
    assert get(env,value).json()==receipt.json()


def test_queue_payload_and_cancelled_state_cannot_be_rewritten(env):
    value,key=request(env)
    assert confirm(env,value,sign(env,value,key)).status_code==200
    assert env.client.post('/api/ui/outreach/queue/'+value['requestId']+'/cancel').status_code==200
    for query,error in [
        ("UPDATE pilot_outreach_queue SET request_payload='{}'::jsonb",InsufficientPrivilege),
        ("DELETE FROM pilot_outreach_queue",InsufficientPrivilege),
        ("UPDATE pilot_outreach_queue SET state='QUEUED'",RaiseException),
    ]:
        with pytest.raises(error), env.app.connect() as conn:
            conn.execute("SELECT set_config('yike.tenant_id',%s,true),set_config('yike.user_id',%s,true)",
                (env.tenant,env.users[0]))
            conn.execute(query+' WHERE request_id=%s',(value['requestId'],))
