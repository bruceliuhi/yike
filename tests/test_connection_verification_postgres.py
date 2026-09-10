"""Synthetic VERIFY observations over real restricted PostgreSQL transactions."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import time
from uuid import uuid4

import pytest
import psycopg
from psycopg import sql
from fastapi.testclient import TestClient

from pilot.auth import issue_token,verify_token_claims
from pilot.connection_versions import ConnectionOperation,ConnectionOperationStore,ConnectionOperationError,MAX_VERSION
from pilot.web import build_app
from tests.test_connection_versions_postgres import databases,env,operation,wait_for_lock
from tests.test_connection_verification import verification


def registered(env):
    service=ConnectionOperationStore(env.database)
    receipt=service.apply(env.claims,operation(env))
    request=ConnectionOperation(**verification(device_id=env.device,
        connection_id=receipt['connection_id'],platform='BILIBILI',
        account_public_id='synthetic-id',session_ref='vault://synthetic'))
    return service,receipt,request


def check(service,env,receipt):
    with env.database.connect() as connection:
        return service.lock_current(connection.cursor(),env.claims,device_id=env.device,
            connection_id=receipt['connection_id'],connection_version=receipt['connection_version'],platform='BILIBILI')


def test_register_verify_current_and_historical_disconnect_http(env):
    service,original,request=registered(env)
    assert original['connection_status']=='UNVERIFIED'
    with pytest.raises(ConnectionOperationError,match='connection_unavailable'): check(service,env,original)
    headers={'Authorization':'Bearer '+env.token,'Origin':'https://testserver'}
    with TestClient(build_app(env.store,auth_secret='synthetic-connection-test-secret'),base_url='https://testserver') as client:
        response=client.post('/api/ui/connection-operations',json=request.model_dump(),headers=headers)
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        connected=response.json()
        assert connected['state']=='SUCCEEDED' and connected['connection_status']=='CONNECTED'
        assert connected['connection_version']==2 and 'vault://' not in response.text
        assert check(service,env,connected)['connection_version']==2
        assert client.post('/api/ui/connection-operations',json=request.model_dump(),headers=headers).json()==connected
        fresh=request.model_copy(update={'request_id':str(uuid4()),'expected_connection_version':2})
        assert client.post('/api/ui/connection-operations',json=fresh.model_dump(),headers=headers).json()['connection_version']==2
        disconnect=operation(env,action='DISCONNECT',connection_id=connected['connection_id'],expected_connection_version=2,
            platform=None,account_public_id=None,session_ref=None)
        result=client.post('/api/ui/connection-operations',json=disconnect.model_dump(),headers=headers).json()
        assert result['connection_status']=='DISCONNECTED' and result['connection_version']==3
        assert client.get('/api/ui/connection-operations/'+request.request_id,headers=headers).json()==connected
        assert client.post('/api/ui/connection-operations',json=request.model_dump(),headers=headers).json()==connected
        with pytest.raises(ConnectionOperationError,match='connection_version_conflict'): check(service,env,connected)
        for capability in ('platform_connections','task_execution','outreach','replies'):
            assert client.get('/api/ui/capabilities').json()['capabilities'][capability]=={'available':False}
        assert client.post('/api/ui/connection-operations',json=fresh.model_dump(),headers=headers|{'Origin':'https://evil.invalid'}).status_code==403
        assert client.post('/api/ui/connection-operations',json=fresh.model_dump()).status_code==401


@pytest.mark.parametrize('field,value', [('platform','DOUYIN'),('account_public_id','other-account'),
    ('session_ref','vault://other-profile'),('connection_id',str(uuid4()))])
def test_verify_rejects_wrong_connection_binding(env,field,value):
    service,original,request=registered(env)
    rejected=service.apply(env.claims,request.model_copy(update={field:value}))
    assert rejected['state']=='REJECTED' and rejected['error_code']=='connection_unavailable'
    assert env.store.list_connections(env.user)[0]['status']=='UNVERIFIED'


@pytest.mark.parametrize('owner', ['same','other_user','foreign_user','revoked'])
def test_verify_device_and_owner_are_bound(env,owner):
    service,original,request=registered(env)
    if owner=='same':
        device=env.store.register_device(env.user,'other-device')['device_id']
        request=request.model_copy(update={'device_id':device}); claims=env.claims
        code='connection_unavailable'
    elif owner=='revoked':
        env.store.revoke_device(env.user,env.device); claims=env.claims; code='device_unavailable'
    else:
        claims=verify_token_claims(issue_token(getattr(env,owner),'synthetic-connection-test-secret'),'synthetic-connection-test-secret')
        code='device_unavailable'
    assert service.apply(claims,request)['error_code']==code


def test_verify_revoked_session_rejected_without_receipt(env):
    service,original,request=registered(env)
    env.store.sessions.revoke([env.claims])
    with pytest.raises(ConnectionOperationError,match='invalid_session'): service.apply(env.claims,request)
    with env.admin.connect() as connection:
        assert connection.execute('SELECT count(*) FROM pilot_connection_operations WHERE request_id=%s',(request.request_id,)).fetchone()[0]==0


@pytest.mark.parametrize('state',['UNVERIFIED','EXPIRED','CONNECTED','DISCONNECTED'])
def test_verify_transition_and_version_boundary(env,state):
    service,original,request=registered(env)
    with env.admin.connect() as connection:
        connection.execute('ALTER TABLE pilot_platform_connections DISABLE TRIGGER pilot_connection_version_guard')
        connection.execute('UPDATE pilot_platform_connections SET status=%s,connection_version=%s WHERE connection_id=%s',(state,MAX_VERSION,original['connection_id']))
        connection.execute('ALTER TABLE pilot_platform_connections ENABLE TRIGGER pilot_connection_version_guard')
    request=request.model_copy(update={'expected_connection_version':MAX_VERSION})
    receipt=service.apply(env.claims,request)
    if state=='CONNECTED':
        assert receipt['state']=='SUCCEEDED' and receipt['connection_version']==MAX_VERSION
    else:
        assert receipt['error_code']==('connection_unavailable' if state=='DISCONNECTED' else 'connection_version_exhausted')


def test_expired_can_verify_but_disconnected_requires_register(env):
    service,original,request=registered(env)
    with env.admin.connect() as connection:
        connection.execute("UPDATE pilot_platform_connections SET status='EXPIRED' WHERE connection_id=%s",(original['connection_id'],))
    request=request.model_copy(update={'expected_connection_version':2})
    receipt=service.apply(env.claims,request)
    assert receipt['connection_status']=='CONNECTED' and receipt['connection_version']==3
    env.store.disconnect_platform(env.user,original['connection_id'])
    bad=request.model_copy(update={'request_id':str(uuid4()),'expected_connection_version':4})
    assert service.apply(env.claims,bad)['error_code']=='connection_unavailable'
    again=service.apply(env.claims,operation(env,expected_connection_version=4))
    assert again['connection_status']=='UNVERIFIED' and again['connection_version']==5
    assert service.apply(env.claims,bad.model_copy(update={'request_id':str(uuid4()),'expected_connection_version':5}))['connection_version']==6


def test_verify_stale_version_and_request_conflict(env):
    service,original,request=registered(env)
    assert service.apply(env.claims,request.model_copy(update={'expected_connection_version':2}))['error_code']=='connection_version_conflict'
    with pytest.raises(ConnectionOperationError,match='request_conflict'): service.apply(env.claims,request)


def test_verify_receipt_insert_failure_rolls_back(env):
    service,original,request=registered(env); name='verify_failure_'+uuid4().hex
    with env.admin.connect() as connection:
        connection.execute(sql.SQL('ALTER TABLE pilot_connection_operations ADD CONSTRAINT {} CHECK(request_id <> {})').format(sql.Identifier(name),sql.Literal(request.request_id)))
    try:
        with pytest.raises(psycopg.errors.CheckViolation): service.apply(env.claims,request)
        current=env.store.list_connections(env.user)[0]
        assert current['status']=='UNVERIFIED' and current['connection_version']==1
    finally:
        with env.admin.connect() as connection:
            connection.execute(sql.SQL('ALTER TABLE pilot_connection_operations DROP CONSTRAINT {}').format(sql.Identifier(name)))


@pytest.mark.parametrize('same_request',[False,True])
def test_concurrent_verification_and_replay(env,same_request):
    service,original,request=registered(env)
    other_claims=verify_token_claims(issue_token(env.user,'synthetic-connection-test-secret'),'synthetic-connection-test-secret')
    second=request if same_request else request.model_copy(update={'request_id':str(uuid4())})
    with ThreadPoolExecutor(2) as pool:
        with env.admin.connect() as blocker:
            blocker.execute('SELECT 1 FROM pilot_devices WHERE device_id=%s FOR UPDATE',(env.device,))
            first=pool.submit(service.apply,env.claims,request)
            wait_for_lock(env.admin,'owner_user_id=')
            next_one=pool.submit(service.apply,other_claims,second)
        receipts=[first.result(timeout=5),next_one.result(timeout=5)]
    assert receipts[0]['connection_version']==2
    if same_request: assert receipts[0]==receipts[1]
    else: assert receipts[1]['error_code']=='connection_version_conflict'
    assert env.store.list_connections(env.user)[0]['connection_version']==2


def test_migration_repeatable_and_receipts_stay_immutable(env):
    env.admin.migrate(); env.admin.migrate()
    with env.database.connect() as connection:
        assert connection.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()==(False,False)
        assert connection.execute("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid='pilot_connection_operations'::regclass").fetchone()==(True,True)
        assert connection.execute("SELECT has_table_privilege(current_user,'pilot_connection_operations','UPDATE'),has_table_privilege(current_user,'pilot_connection_operations','DELETE')").fetchone()==(False,False)


@pytest.mark.parametrize('verify_first',[False,True])
def test_verify_disconnect_lock_order_cannot_resurrect_connection(env,verify_first):
    service,original,request=registered(env)
    disconnect=operation(env,action='DISCONNECT',connection_id=original['connection_id'],
        expected_connection_version=2 if verify_first else 1,platform=None,account_public_id=None,session_ref=None)
    other_claims=verify_token_claims(issue_token(env.user,'synthetic-connection-test-secret'),'synthetic-connection-test-secret')
    with ThreadPoolExecutor(2) as pool:
        with env.admin.connect() as blocker:
            blocker.execute('SELECT 1 FROM pilot_platform_connections WHERE connection_id=%s FOR UPDATE',(original['connection_id'],))
            first=pool.submit(service.apply,env.claims,request if verify_first else disconnect)
            wait_for_lock(env.admin,'FROM pilot_platform_connections')
            second=pool.submit(service.apply,other_claims,disconnect if verify_first else request)
            wait_for_lock(env.admin,'FROM pilot_devices')
            assert not first.done() and not second.done()
        assert first.result(timeout=5)['state']=='SUCCEEDED'
        final=second.result(timeout=5)
    if verify_first: assert final['connection_status']=='DISCONNECTED' and final['state']=='SUCCEEDED'
    else: assert final['error_code']=='connection_unavailable'
    current=env.store.list_connections(env.user)[0]
    assert current['status']=='DISCONNECTED' and current['connection_version']==(3 if verify_first else 2)


def test_verify_expiry_after_device_lock_wait_rolls_back(env):
    service,original,request=registered(env)
    claims=replace(env.claims,expires_at=int(time.time())+2)
    with ThreadPoolExecutor(1) as pool:
        with env.admin.connect() as blocker:
            blocker.execute('SELECT 1 FROM pilot_devices WHERE device_id=%s FOR UPDATE',(env.device,))
            future=pool.submit(service.apply,claims,request)
            wait_for_lock(env.admin,'FROM pilot_devices')
            while time.time()<=claims.expires_at: time.sleep(0.01)
        with pytest.raises(ConnectionOperationError,match='invalid_session'): future.result(timeout=5)
    current=env.store.list_connections(env.user)[0]
    assert current['status']=='UNVERIFIED' and current['connection_version']==1
    with env.admin.connect() as connection:
        assert connection.execute('SELECT count(*) FROM pilot_connection_operations WHERE request_id=%s',(request.request_id,)).fetchone()[0]==0


def test_socket_https_verify_uses_normal_origin_session_and_restricted_pg(env,tmp_path):
    """A local self-signed CA is trusted explicitly; dev_login stays disabled."""
    import os,shutil,socket,ssl,subprocess,threading
    import httpx,uvicorn
    openssl=shutil.which('openssl')
    if not openssl: pytest.skip('OpenSSL needed for isolated local HTTPS certificate')
    cert,key=tmp_path/'local-cert.pem',tmp_path/'local-key.pem'
    subprocess.run([openssl,'req','-config',os.devnull,'-x509','-newkey','rsa:2048','-nodes','-days','1',
        '-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1',
        '-keyout',str(key),'-out',str(cert)],check=True,capture_output=True,timeout=20)
    app=build_app(env.store,auth_secret='synthetic-connection-test-secret')
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1',0)); listener.listen(32)
        base=f'https://127.0.0.1:{listener.getsockname()[1]}'
        server=uvicorn.Server(uvicorn.Config(app,log_level='critical',access_log=False,lifespan='off',
            ssl_certfile=str(cert),ssl_keyfile=str(key)))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True); thread.start()
        try:
            deadline=time.monotonic()+10
            while not server.started and thread.is_alive() and time.monotonic()<deadline: time.sleep(0.02)
            assert server.started
            with httpx.Client(base_url=base,verify=ssl.create_default_context(cafile=str(cert)),trust_env=False,timeout=10) as client:
                headers={'Authorization':'Bearer '+env.token,'Origin':base}
                first=client.post('/api/ui/connection-operations',json=operation(env).model_dump(),headers=headers)
                assert first.status_code==200 and first.json()['connection_status']=='UNVERIFIED'
                payload=verification(device_id=env.device,connection_id=first.json()['connection_id'],
                    platform='BILIBILI',account_public_id='synthetic-id',session_ref='vault://synthetic')
                verified=client.post('/api/ui/connection-operations',json=payload,headers=headers)
                assert verified.status_code==200 and verified.json()['connection_status']=='CONNECTED'
                assert verified.json()['connection_version']==2
                assert client.post('/api/ui/connection-operations',json=payload,headers=headers).json()==verified.json()
                assert client.post('/api/ui/connection-operations',json=payload,headers=headers|{'Origin':'https://evil.invalid'}).status_code==403
                env.store.sessions.revoke([env.claims])
                assert client.post('/api/ui/connection-operations',json=payload,headers=headers).status_code==401
        finally:
            server.should_exit=True; thread.join(timeout=10)
            assert not thread.is_alive()
