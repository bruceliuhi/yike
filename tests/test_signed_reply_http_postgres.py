"""Real HTTP/Ed25519/PG reply association, with synthetic platform inputs."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from pilot.auth import issue_token
from pilot.reply_store import event_digest
from pilot.opportunity_evidence import evidence_digest
from pilot.execution_runtime import _hash
from pilot.signed_replies import evidence_row
from tests.test_outreach_dispatch_http_postgres import (
    databases as dispatch_databases, queue_databases, draft_databases,
    execution_databases, env, queued, dispatch, result, get, encoded, SECRET,
)
from tests.test_reply_contract import platform_event, manual_event
from tests.test_outreach_context_http_postgres import context
from tests.test_contact_drafts_http_postgres import body as draft_body, rehash, save
from tests.test_outreach_queue_http_postgres import sign, confirm
from tests.test_device_credentials_postgres import bind, challenge, complete
from pilot.auth import verify_token_claims
from pilot.device_credentials import DeviceCredentialStore
from nacl.signing import SigningKey
from types import SimpleNamespace
from fastapi.testclient import TestClient
from pilot.runtime import build_runtime_app
from pilot.store import PilotStore


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


def xhs_sent(env):
    note_id='a'*24
    author_id='c'*24
    account_id='d'*24
    store=PilotStore(env.app)
    device=store.register_device(env.users[0],'synthetic-xhs-reply-device')['device_id']
    connection=store.connect_platform(env.users[0],'XIAOHONGSHU',device,account_id,
        'vault://synthetic-xhs-reply-profile')
    with env.admin.connect() as conn:
        payload=conn.execute('SELECT payload FROM pilot_opportunity_evidence WHERE opportunity_id=%s',
            (env.opp,)).fetchone()[0]
        payload['source'].update(platform='XIAOHONGSHU',kind='POST',
            public_url=f'https://www.xiaohongshu.com/explore/{note_id}',external_source_id=note_id,
            external_comment_id=None,container_title=None,parent=None,author_public_id=author_id)
        conn.execute("SET LOCAL session_replication_role='replica'")
        conn.execute('UPDATE pilot_sources SET platform=%s,external_id=%s,public_url=%s WHERE source_id=%s',
            ('XIAOHONGSHU',note_id,payload['source']['public_url'],env.source))
        conn.execute("UPDATE pilot_platform_connections SET status='CONNECTED' WHERE connection_id=%s",
            (connection['connection_id'],))
        conn.execute('UPDATE pilot_opportunity_evidence SET payload=%s,payload_sha256=%s WHERE opportunity_id=%s',
            (Jsonb(payload),evidence_digest(payload),env.opp))
        version=conn.execute('SELECT connection_version FROM pilot_platform_connections WHERE connection_id=%s',
            (connection['connection_id'],)).fetchone()[0]
    draft=draft_body(env,channel='comment')
    draft['snapshot']['draft'].update(accountId=account_id,recipient=author_id)
    rehash(draft)
    assert save(env,draft).status_code==200
    context_request=dict(binding=draft['binding'],deviceId=device,
        connectionId=connection['connection_id'],connectionVersion=version)
    resolved=context(env,context_request)
    assert resolved.status_code==200,resolved.text
    headers=dict(env.client.headers)
    env.client=TestClient(build_runtime_app(env.app,auth_secret=SECRET,
        environment={'YIKE_PILOT_OUTREACH_PLATFORMS':'XIAOHONGSHU'}),base_url='https://pilot.example')
    env.client.headers.update(headers)
    key=SigningKey.generate()
    claims=verify_token_claims(env.client.headers['Authorization'].removeprefix('Bearer '),SECRET)
    bind(SimpleNamespace(service=DeviceCredentialStore(env.app),claims=claims,
        device=context_request['deviceId']),key)
    confirmation=dict(requestId=str(uuid4()),context=context_request,
        contextSha256=resolved.json()['contextSha256'],credentialVersion=1,humanConfirmed=True,
        channelCheck=dict(status='AVAILABLE',observedAt=datetime.now(UTC).isoformat()))
    assert confirm(env,confirmation,sign(env,confirmation,key)).status_code==200
    claim=dict(action='CLAIM',requestId=confirmation['requestId'],claimId=str(uuid4()),
        deviceId=context_request['deviceId'],credentialVersion=1,
        contextSha256=confirmation['contextSha256'])
    assert dispatch(env,claim,key).status_code==200
    sent=result(claim)
    sent['outcome']['proof']['externalId']='b'*24
    assert dispatch(env,sent,key).status_code==200
    return confirmation,claim,sent,key,resolved.json()


@pytest.mark.parametrize('env',['POST'],indirect=True)
def test_sync_context_returns_only_frozen_sent_xhs_post_origin(env):
    confirmation,claim,sent,_key,frozen=xhs_sent(env)
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_sources SET health='BLOCKED' WHERE source_id=%s",(env.source,))
        conn.execute("UPDATE business_profile_versions SET status='REVOKED' WHERE profile_version_id=%s",(env.profile,))
    response=env.client.post('/api/ui/replies/sync-context',json=dict(
        requestId=confirmation['requestId'],deviceId=claim['deviceId'],credentialVersion=1))
    assert response.status_code==200,response.text
    assert response.json()==dict(schemaVersion='reply-sync-context-v1',context=frozen,
        claimId=claim['claimId'],claimedAt=response.json()['claimedAt'],
        rootCommentId=sent['outcome']['proof']['externalId'],deviceId=claim['deviceId'],credentialVersion=1)
    assert response.json()['claimedAt'].endswith('+00:00')
    assert set(response.json())=={'schemaVersion','context','claimId','claimedAt','rootCommentId','deviceId','credentialVersion'}


@pytest.mark.parametrize('env',['POST'],indirect=True)
def test_sync_context_rejects_extra_wrong_owner_device_and_non_sent(env):
    confirmation,claim,_sent,_key,_frozen=xhs_sent(env)
    body=dict(requestId=confirmation['requestId'],deviceId=claim['deviceId'],credentialVersion=1)
    assert env.client.post('/api/ui/replies/sync-context',json=body|{'rootId':'b'*24}).status_code==422
    assert env.client.post('/api/ui/replies/sync-context',json=body|{'deviceId':str(uuid4())}).status_code==409
    for user in env.users[1:]:
        response=env.client.post('/api/ui/replies/sync-context',json=body,
            headers={'Authorization':'Bearer '+issue_token(user,SECRET)})
        assert response.status_code==409
    with env.admin.connect() as conn:
        conn.execute("SET LOCAL session_replication_role='replica'")
        conn.execute("UPDATE pilot_outreach_queue SET state='UNKNOWN' WHERE request_id=%s",(confirmation['requestId'],))
    assert env.client.post('/api/ui/replies/sync-context',json=body).status_code==409


@pytest.mark.parametrize('status',['SENT','FAILED','UNKNOWN'])
def test_sync_context_rejects_non_xhs_post_and_every_non_sent_state(env,status):
    queue,value,key=setup(env,status=status)
    body=dict(requestId=queue['requestId'],deviceId=value['deviceId'],credentialVersion=1)
    response=env.client.post('/api/ui/replies/sync-context',json=body)
    assert response.status_code==409,response.text


@pytest.mark.parametrize('env',['POST'],indirect=True)
def test_sync_context_rejects_valid_other_device_and_corrupt_root_without_writes(env):
    confirmation,claim,sent,_key,_frozen=xhs_sent(env)
    claims=verify_token_claims(env.client.headers['Authorization'].removeprefix('Bearer '),SECRET)
    other=PilotStore(env.app).register_device(env.users[0],'synthetic-other-device')['device_id']
    bind(SimpleNamespace(service=DeviceCredentialStore(env.app),claims=claims,device=other),SigningKey.generate())
    request=dict(requestId=confirmation['requestId'],deviceId=claim['deviceId'],credentialVersion=1)
    assert env.client.post('/api/ui/replies/sync-context',json=request|{'deviceId':other}).status_code==409
    with env.admin.connect() as conn:
        before=conn.execute('SELECT count(*) FROM pilot_outreach_results').fetchone()
        payload=conn.execute('SELECT payload FROM pilot_outreach_results WHERE result_id=%s',
            (sent['resultId'],)).fetchone()[0]
        payload['outcome']['proof']['externalId']='not-a-root-comment-id'
        conn.execute("SET LOCAL session_replication_role='replica'")
        conn.execute('UPDATE pilot_outreach_results SET payload=%s,request_sha256=%s WHERE result_id=%s',
            (Jsonb(payload),_hash(payload),sent['resultId']))
    assert env.client.post('/api/ui/replies/sync-context',json=request).status_code==409
    with env.admin.connect() as conn:
        assert conn.execute('SELECT count(*) FROM pilot_outreach_results').fetchone()==before


@pytest.mark.parametrize('env',['POST'],indirect=True)
def test_sync_context_rejects_confirmation_saved_under_a_different_request_id(env):
    confirmation,claim,_sent,_key,_frozen=xhs_sent(env)
    request=dict(requestId=confirmation['requestId'],deviceId=claim['deviceId'],credentialVersion=1)
    with env.admin.connect() as conn:
        payload=conn.execute('SELECT request_payload FROM pilot_outreach_queue WHERE request_id=%s',
            (confirmation['requestId'],)).fetchone()[0]
        conn.execute(sql.SQL('ALTER TABLE pilot_outreach_queue DROP CONSTRAINT IF EXISTS {}').format(
            sql.Identifier('pilot_outreach_queue_check')))
        payload['requestId']=str(uuid4())
        conn.execute("SET LOCAL session_replication_role='replica'")
        conn.execute('UPDATE pilot_outreach_queue SET request_payload=%s,request_sha256=%s WHERE request_id=%s',
            (Jsonb(payload),_hash(payload),confirmation['requestId']))
    assert env.client.post('/api/ui/replies/sync-context',json=request).status_code==409


@pytest.mark.parametrize('env',['POST'],indirect=True)
def test_sync_context_uses_current_key_after_same_device_credential_rotation(env):
    confirmation,claim,sent,key,frozen=xhs_sent(env)
    claims=verify_token_claims(env.client.headers['Authorization'].removeprefix('Bearer '),SECRET)
    identity=SimpleNamespace(service=DeviceCredentialStore(env.app),claims=claims,device=claim['deviceId'])
    new_key=SigningKey.generate()
    assert complete(identity,challenge(identity,'ROTATE',1,new_key),new_key,key)['credential_version']==2
    response=env.client.post('/api/ui/replies/sync-context',json=dict(
        requestId=confirmation['requestId'],deviceId=claim['deviceId'],credentialVersion=2))
    assert response.status_code==200,response.text
    assert response.json()['context']==frozen
    assert response.json()['rootCommentId']==sent['outcome']['proof']['externalId']
    assert response.json()['credentialVersion']==2


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
