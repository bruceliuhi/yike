"""HTTP, signatures and restricted PostgreSQL; platform receipts are synthetic."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from pilot.runtime import build_runtime_app
from tests.test_outreach_queue_http_postgres import (
    databases as queue_databases, draft_databases, execution_databases, env,
    request, sign, confirm, get, encoded, SECRET,
)


@pytest.fixture(scope='module')
def databases(queue_databases):
    return queue_databases


def queued(env,enabled=True):
    original=env.client
    environment={'YIKE_PILOT_OUTREACH_PLATFORMS':'BILIBILI'} if enabled else {}
    env.client=TestClient(build_runtime_app(env.app,auth_secret=SECRET,environment=environment),base_url='https://pilot.example')
    env.client.headers.update(original.headers)
    value,key=request(env)
    assert confirm(env,value,sign(env,value,key)).status_code==200
    claim=dict(action='CLAIM',requestId=value['requestId'],claimId=str(uuid4()),
        deviceId=value['context']['deviceId'],credentialVersion=1,contextSha256=value['contextSha256'])
    return value,claim,key


def signed(env,value,key):
    response=env.client.post('/api/ui/outreach/dispatch/signing-payload',json={'request':value})
    assert response.status_code==200,response.text
    return dict(request=value,signature=encoded(key.sign(response.json()['signing_payload'].encode()).signature))


def dispatch(env,value,key):
    return env.client.post('/api/ui/outreach/dispatch',json=signed(env,value,key))


def result(claim,status='SENT'):
    value=copy.deepcopy(claim)
    value.update(action='RESULT',resultId=str(uuid4()),outcome=dict(status=status))
    if status!='UNKNOWN':
        value['outcome'].update(confirmed=True,proof=dict(
            kind='ACCEPTED' if status=='SENT' else 'REJECTED_NOT_DELIVERED',
            externalId='synthetic-platform-receipt',sha256='a'*64,observedAt=datetime.now(UTC).isoformat()))
        if status=='FAILED': value['outcome']['confirmedNotDelivered']=True
    return value


def test_claim_once_unknown_recovery_and_signed_platform_receipt(env):
    value,claim,key=queued(env)
    envelope=signed(env,claim,key)
    response=env.client.post('/api/ui/outreach/dispatch',json=envelope)
    assert response.status_code==200,response.text
    first=response.json()
    assert first['dispatchAllowed'] is True and first['state']=='UNKNOWN'
    assert first['context']['contextSha256']==value['contextSha256']
    assert 0<(datetime.fromisoformat(first['dispatchBefore'])-datetime.now(UTC)).total_seconds()<=30
    replay=env.client.post('/api/ui/outreach/dispatch',json=envelope)
    assert replay.status_code==200 and replay.json()['dispatchAllowed'] is False
    assert 'context' not in replay.json()
    restarted=TestClient(build_runtime_app(env.app,auth_secret=SECRET,environment={}),base_url='https://pilot.example')
    restarted.headers.update(env.client.headers)
    assert restarted.get('/api/ui/outreach/queue/'+value['requestId']).json()['dispatchAllowed'] is False
    unknown=dispatch(env,result(claim,'UNKNOWN'),key)
    assert unknown.status_code==200 and unknown.json()['state']=='UNKNOWN'
    # Later source changes cannot erase the frozen operation or block its result.
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_sources SET health='BLOCKED' WHERE source_id=%s",(env.source,))
    sent=result(claim)
    response=dispatch(env,sent,key)
    assert response.status_code==200,response.text
    assert response.json()['state']=='SENT' and response.json()['deliveryConfirmed'] is True
    assert response.json()['evidenceAuthority']=='DEVICE_ATTESTED_PLATFORM_RECEIPT'
    assert dispatch(env,sent,key).json()==response.json()
    assert get(env,value).json()['state']=='SENT'
    assert dispatch(env,result(claim,'FAILED'),key).status_code==409


def test_concurrent_claim_has_exactly_one_permission_and_no_cancel_or_new_uuid(env):
    value,claim,key=queued(env)
    payload=signed(env,claim,key)
    with ThreadPoolExecutor(max_workers=3) as pool:
        outputs=list(pool.map(lambda _:env.client.post('/api/ui/outreach/dispatch',json=payload),range(3)))
    assert [r.status_code for r in outputs]==[200]*3
    assert sum(r.json()['dispatchAllowed'] for r in outputs)==1
    assert env.client.post('/api/ui/outreach/queue/'+value['requestId']+'/cancel').status_code==409
    altered=copy.deepcopy(claim); altered['claimId']=str(uuid4())
    assert dispatch(env,altered,key).status_code==409
    another=copy.deepcopy(value); another['requestId']=str(uuid4())
    assert confirm(env,another,sign(env,another,key)).status_code==409


@pytest.mark.parametrize('change',['source','cancel','context','stale','disabled'])
def test_claim_rechecks_authorization_and_never_grants_stale_permission(env,change):
    value,claim,key=queued(env,enabled=change!='disabled')
    if change=='context': claim['contextSha256']='0'*64
    elif change=='cancel': env.client.post('/api/ui/outreach/queue/'+value['requestId']+'/cancel')
    elif change=='source':
        with env.admin.connect() as conn:
            conn.execute("UPDATE pilot_sources SET health='BLOCKED' WHERE source_id=%s",(env.source,))
    elif change=='stale':
        # Move only test queue timestamps with admin trigger bypass; no clock waiting.
        with env.admin.connect() as conn:
            conn.execute("SET LOCAL session_replication_role='replica'")
            conn.execute("UPDATE pilot_outreach_queue SET confirmed_at=clock_timestamp()-interval '5 minutes' WHERE request_id=%s",(value['requestId'],))
    response=dispatch(env,claim,key)
    assert response.status_code in (409,501),response.text
    assert get(env,value).json()['dispatchAllowed'] is False


def test_only_explicit_non_delivery_allows_fresh_confirmation(env):
    value,claim,key=queued(env)
    assert dispatch(env,claim,key).status_code==200
    bad=result(claim,'FAILED'); bad['outcome'].pop('confirmedNotDelivered')
    response=env.client.post('/api/ui/outreach/dispatch/signing-payload',json={'request':bad})
    assert response.status_code==422
    failed=result(claim,'FAILED')
    assert dispatch(env,failed,key).json()['state']=='FAILED'
    changed=copy.deepcopy(failed); changed['outcome']['proof']['externalId']='changed'
    assert dispatch(env,changed,key).status_code==409
    value['requestId']=str(uuid4())
    assert confirm(env,value,sign(env,value,key)).status_code==200
    reused=copy.deepcopy(claim); reused['requestId']=value['requestId']
    assert dispatch(env,reused,key).status_code==409


def test_result_requires_original_claim_and_session_device_signature(env):
    value,claim,key=queued(env)
    early=dispatch(env,result(claim),key)
    assert early.status_code==409
    payload=signed(env,claim,key); payload['signature']=encoded(b'0'*64)
    assert env.client.post('/api/ui/outreach/dispatch',json=payload).status_code==400
    assert dispatch(env,claim,key).status_code==200
    wrong=result(claim); wrong['claimId']=str(uuid4())
    assert dispatch(env,wrong,key).status_code==409
    future=result(claim); future['outcome']['proof']['observedAt']=(datetime.now(UTC)+timedelta(days=1)).isoformat()
    assert dispatch(env,future,key).status_code==409
