"""Real HTTP/Ed25519/PG reply association, with synthetic platform inputs."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from pilot.auth import issue_token
from pilot.reply_store import event_digest
from pilot.signed_replies import evidence_row
from tests.test_outreach_dispatch_http_postgres import (
    databases as dispatch_databases, queue_databases, draft_databases,
    execution_databases, env, queued, dispatch, result, get, encoded, SECRET,
)
from tests.test_reply_contract import platform_event, manual_event


@pytest.fixture(scope='module')
def databases(dispatch_databases):
    admin,app=dispatch_databases
    with admin.connect() as conn:
        conn.execute("SELECT set_config('yike.app_role',%s,true)",(app.role,))
        for name in ('grant_reply_events.sql','grant_outreach_contract.sql'):
            conn.execute((Path(__file__).parents[1]/'deploy'/name).read_text())
    return admin,app


def setup(env,status='SENT'):
    queue,claim,key=queued(env)
    assert dispatch(env,claim,key).status_code==200
    if status!='UNKNOWN': assert dispatch(env,result(claim,status),key).status_code==200
    now=datetime.now(UTC).isoformat()
    event=platform_event(tenant_id=env.tenant,user_id=env.users[0],opportunity_id=env.opp,
        source_id=env.source,profile_version_id=env.profile,outreach_request_id=queue['requestId'],
        platform='BILIBILI',channel='dm',sender_public_id='comment-author',received_at=now,observed_at=now)
    value=dict(deviceId=claim['deviceId'],credentialVersion=1,claimId=claim['claimId'],
        contextSha256=claim['contextSha256'],event=event.model_dump())
    return queue,value,key


def signed(env,value,key):
    response=env.client.post('/api/ui/replies/signing-payload',json={'request':value})
    assert response.status_code==200,response.text
    return dict(request=value,signature=encoded(key.sign(response.json()['signing_payload'].encode()).signature))


def record(env,value,key):
    return env.client.post('/api/ui/replies/signed',json=signed(env,value,key))


def evidence(env,**kw):
    return env.client.get(f'/api/ui/opportunities/{env.opp}/replies/evidence',**kw)


def test_evidence_row_projects_stored_revision():
    event=platform_event()
    assert evidence_row((event.model_dump(),event_digest(event),None,7))['revision']==7


def test_signed_reply_reaches_original_opportunity_without_old_117_or_mutating_send(env):
    queue,value,key=setup(env,status='UNKNOWN')
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_sources SET health='BLOCKED' WHERE source_id=%s",(env.source,))
        conn.execute("UPDATE business_profile_versions SET status='REVOKED' WHERE profile_version_id=%s",(env.profile,))
    reply=record(env,value,key)
    assert reply.status_code==200,reply.text
    output=reply.json()
    assert output['revision']==1
    assert output['event']==value['event']
    assert output['verification']['authority']=='DEVICE_ATTESTED_PLATFORM_REPLY'
    assert output['verification']['claimId']==value['claimId']
    assert record(env,value,key).json()==output
    assert evidence(env).json()==[output]
    assert env.client.get(f'/api/ui/opportunities/{env.opp}/replies').json()==[value['event']]
    assert get(env,queue).json()['state']=='UNKNOWN'
    assert env.client.post('/api/ui/replies',json=value['event']).status_code==409
    with env.admin.connect() as conn:
        assert conn.execute('SELECT count(*) FROM pilot_outreach_confirmations WHERE request_id=%s',(queue['requestId'],)).fetchone()==(0,)


@pytest.mark.parametrize('change',['sender','channel','source','profile','claim','context','future','failed'])
def test_wrong_origin_or_non_reply_facts_cannot_be_attributed(env,change):
    queue,value,key=setup(env,status='FAILED' if change=='failed' else 'SENT')
    if change=='sender': value['event']['sender_public_id']='unrelated-commenter'
    elif change=='channel': value['event']['channel']='comment'
    elif change=='source': value['event']['source_id']=str(uuid4())
    elif change=='profile': value['event']['profile_version_id']=str(uuid4())
    elif change=='claim': value['claimId']=str(uuid4())
    elif change=='context': value['contextSha256']='0'*64
    elif change=='future':
        later=(datetime.now(UTC)+timedelta(days=1)).isoformat()
        value['event'].update(received_at=later,observed_at=later)
    response=record(env,value,key)
    assert response.status_code==409,response.text
    assert evidence(env).json()==[]


def test_forged_signature_cross_owner_and_duplicate_native_observation(env):
    queue,value,key=setup(env)
    payload=signed(env,value,key); forged=copy.deepcopy(payload); forged['signature']=encoded(b'0'*64)
    assert env.client.post('/api/ui/replies/signed',json=forged).status_code==400
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:env.client.post('/api/ui/replies/signed',json=payload),range(2)))
    assert [r.status_code for r in responses]==[200,200]
    assert responses[0].json()==responses[1].json()
    duplicate=copy.deepcopy(value); duplicate['event']['event_id']=str(uuid4())
    assert record(env,duplicate,key).json()==responses[0].json()
    assert len(evidence(env).json())==1
    for user in env.users[1:]:
        headers={'Authorization':'Bearer '+issue_token(user,SECRET)}
        assert evidence(env,headers=headers).json()==[]
        assert env.client.post('/api/ui/replies/signed',json=payload,headers=headers).status_code in (400,404,409)
    assert 'signature' not in str(evidence(env).json())


def test_manual_record_stays_manual_and_native_read_revision_keeps_its_proof(env):
    queue,value,key=setup(env)
    first=record(env,value,key)
    assert first.status_code==200
    changed=copy.deepcopy(value)
    now=datetime.now(UTC).isoformat()
    changed['event'].update(read_state='READ',read_at=now,observed_at=now)
    assert record(env,changed,key).status_code==200
    event=manual_event(tenant_id=env.tenant,user_id=env.users[0],opportunity_id=env.opp,
        source_id=env.source,profile_version_id=env.profile,outreach_request_id=queue['requestId'])
    assert env.client.post('/api/ui/replies',json=event.model_dump()).status_code==200
    rows=evidence(env).json()
    assert len(rows)==3
    native=[r for r in rows if r['event']['kind']=='PLATFORM_REPLY']
    assert [r['revision'] for r in native]==[1,2]
    assert all(r['verification']['authority']=='DEVICE_ATTESTED_PLATFORM_REPLY' for r in native)
    manual=[r for r in rows if r['event']['kind']=='MANUAL_FOLLOWUP']
    assert manual[0]['revision']==1
    assert manual[0]['verification']=={'authority':'MANUAL_RECORD'}


@pytest.mark.parametrize('new_event_id',[False,True])
def test_later_poll_of_same_reply_reuses_first_verified_observation(env,new_event_id):
    queue,value,key=setup(env)
    original=record(env,value,key)
    assert original.status_code==200
    polled=copy.deepcopy(value)
    if new_event_id: polled['event']['event_id']=str(uuid4())
    polled['event']['observed_at']=datetime.now(UTC).isoformat()
    again=record(env,polled,key)
    assert again.status_code==200,again.text
    assert again.json()==original.json()
    assert len(evidence(env).json())==1
