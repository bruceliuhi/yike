"""Actual runtime/HTTP/restricted PG, synthetic source only; never platform sends."""
import copy
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.types.json import Jsonb

from pilot.auth import issue_token, verify_token_claims
from pilot.contact_drafts import ContactDraftStore
from pilot.sessions import PilotSessionRegistry
from pilot.opportunity_evidence import build_evidence, evidence_digest
from pilot.runtime import build_runtime_app
from pilot.store import PilotStore
from tests.test_execution_runtime_postgres import databases as execution_databases
from tests.test_opportunity_evidence import inputs

SECRET = 'synthetic-draft-test-secret'


def body(env, *, channel='dm', content='您好，项目现在还在找团队吗？', version=2,
         saved='', **snapshot_changes):
    snapshot = dict(draft=dict(opportunityId=env.opp, channel=channel, content=content,
        savedContent=saved, version=version, accountId='', recipient=''), accountScope=None,
        profileVersionId=env.profile, sourceEvidenceVersion=env.evidence_version)
    snapshot.update(snapshot_changes)
    return rehash(dict(binding=dict(opportunityId=env.opp, channel=channel,
        requestId=str(uuid4()), contentHash=''), snapshot=snapshot))


def rehash(value):
    s=value['snapshot']; d=s['draft']
    fields=[d['opportunityId'],d['channel'],d['version'],d['content'],d['accountId'],
            d['recipient'],s['profileVersionId'],s['sourceEvidenceVersion'],s['accountScope']]
    value['binding']['contentHash']=hashlib.sha256(json.dumps(fields,ensure_ascii=False,
        separators=(',',':')).encode()).hexdigest()
    return value


@pytest.fixture(scope='module')
def databases(execution_databases):
    admin, app = execution_databases
    with admin.connect() as conn:
        conn.execute('SELECT set_config(\'yike.app_role\',%s,true)',(app.role,))
        for name in ('grant_candidate_review.sql','grant_opportunity_evidence.sql','grant_contact_drafts.sql'):
            path=Path(__file__).parents[1]/'deploy'/name
            conn.execute(path.read_text())
    return admin,app


@pytest.fixture
def env(databases):
    admin,app=databases; store=PilotStore(admin)
    tenants=[store.provision_tenant('synthetic-drafts') for _ in range(2)]
    users=[store.provision_user(t,f'{uuid4()}@example.invalid') for t in (tenants[0],tenants[0],tenants[1])]
    profile=store.save_profile(users[0],{'description':'synthetic'})['version_id']
    store.confirm_profile(users[0],profile)
    opp,source=str(uuid4()),str(uuid4())
    raw,assessment,observation,verification=inputs()
    raw['binding']['profileId']=profile; assessment['profileId']=profile
    raw['raw']['profile_version_id']=profile
    verification['binding']['profileId']=profile
    evidence=build_evidence(opportunity_id=opp,snapshot=raw,assessment=assessment,
        observation=observation,verification=verification,captured_at=datetime.now(UTC))
    with admin.connect() as conn:
        conn.execute('INSERT INTO pilot_sources(source_id,tenant_id,platform,external_id,public_url,health) '
            'VALUES(%s,%s,\'BILIBILI\',%s,%s,\'OPEN\')',(source,tenants[0],source,evidence['source']['public_url']))
        conn.execute("INSERT INTO pilot_opportunities(opportunity_id,tenant_id,profile_version_id,source_id,import_key,title,buyer,summary,contact_path,draft_comment,draft_dm,source_status) "
            "VALUES(%s,%s,%s,%s,%s,'synthetic','synthetic','synthetic','comment','','','OPEN')",(opp,tenants[0],profile,source,opp))
        # Trusted synthetic prior inclusion; this batch tests saving, not ingestion.
        conn.execute("SET LOCAL session_replication_role='replica'")
        conn.execute('INSERT INTO pilot_opportunity_evidence(tenant_id,opportunity_id,included_by_user_id,include_request_id,payload,payload_sha256) VALUES(%s,%s,%s,%s,%s,%s)',
            (tenants[0],opp,users[0],str(uuid4()),Jsonb(evidence),evidence_digest(evidence)))
    client=TestClient(build_runtime_app(app,auth_secret=SECRET,environment={}),base_url='https://pilot.example')
    client.headers['Authorization']='Bearer '+issue_token(users[0],SECRET)
    # Fresh disposable database is removed by the external test runner.
    return SimpleNamespace(admin=admin,app=app,client=client,users=users,tenant=tenants[0],
        profile=profile,opp=opp,source=source,evidence_version=evidence['source']['version_id'])


def save(env,value): return env.client.post('/api/ui/contact-drafts',json=value)
def recover(env,value): return env.client.post('/api/ui/contact-drafts/operation',json=value['binding'])
def latest(env,channel='dm',**kw): return env.client.get(f'/api/ui/opportunities/{env.opp}/contact-drafts/{channel}',**kw)


def test_save_restart_replay_and_separate_channels(env):
    value=body(env); response=save(env,value)
    assert response.status_code==200,response.text
    receipt=response.json()
    assert receipt['status']=='SUCCEEDED' and receipt['confirmed'] is True
    assert receipt['snapshot']['draft']['savedContent']==value['snapshot']['draft']['content']
    assert save(env,value).json()==receipt and recover(env,value).json()==receipt
    assert latest(env).json()==receipt
    assert latest(env,'comment').status_code==404
    assert save(env,body(env,channel='comment',content='这里是评论')).status_code==200
    restarted=TestClient(build_runtime_app(env.app,auth_secret=SECRET,environment={}),base_url='https://pilot.example')
    restarted.headers.update(env.client.headers)
    assert restarted.post('/api/ui/contact-drafts/operation',json=value['binding']).json()==receipt
    assert env.client.get('/api/ui/capabilities').json()['capabilities']['outreach']=={'available':False}


def test_no_cross_owner_tenant_or_unauthenticated_reads(env):
    value=body(env); assert save(env,value).status_code==200
    for user in env.users[1:]:
        headers={'Authorization':'Bearer '+issue_token(user,SECRET)}
        assert latest(env,headers=headers).status_code==404
        assert env.client.post('/api/ui/contact-drafts/operation',json=value['binding'],headers=headers).status_code==404
    env.client.headers.pop('Authorization')
    assert save(env,value).status_code==401


def test_stale_window_and_changed_request_cannot_overwrite(env):
    first=body(env); assert save(env,first).status_code==200
    changed=copy.deepcopy(first); changed['snapshot']['draft']['content']='另一份'; rehash(changed)
    assert save(env,changed).status_code==409
    assert save(env,body(env,version=10)).status_code==409  # Wrong saved predecessor.
    second=body(env,version=3,saved=first['snapshot']['draft']['content'],content='只问一个问题')
    assert save(env,second).status_code==200
    assert latest(env).json()['snapshot']['draft']['content']=='只问一个问题'
    assert recover(env,first).json()['snapshot']['draft']['content']==first['snapshot']['draft']['content']


@pytest.mark.parametrize('change',['source','profile','evidence'])
def test_stale_facts_refuse_new_save_but_keep_original_receipt(env,change):
    first=body(env); assert save(env,first).status_code==200
    next_value=body(env,version=3,saved=first['snapshot']['draft']['content'])
    with env.admin.connect() as conn:
        if change=='source': conn.execute("UPDATE pilot_sources SET health='BLOCKED' WHERE source_id=%s",(env.source,))
        elif change=='profile': conn.execute("UPDATE business_profile_versions SET status='REVOKED' WHERE profile_version_id=%s",(env.profile,))
        else: next_value['snapshot']['sourceEvidenceVersion']=str(uuid4()); rehash(next_value)
    assert save(env,next_value).status_code==409
    assert recover(env,first).status_code==200
    assert save(env,first).status_code==200  # Historical replay is not a new action.


def test_invalid_hash_scope_sample_and_origin_are_rejected(env):
    value=body(env); value['binding']['contentHash']='0'*64
    assert save(env,value).status_code==422
    assert save(env,body(env,accountScope={'id':str(uuid4()),'version':1})).status_code==409
    value=body(env); value['binding']['opportunityId']='sample'
    assert save(env,value).status_code==422
    assert env.client.post('/api/ui/contact-drafts',json=body(env),headers={'Origin':'https://evil.invalid'}).status_code==403
    assert env.client.post('/api/ui/contact-drafts',content=b'x'*100000,headers={'Content-Type':'application/json'}).status_code==413


def test_direct_rls_and_append_only_grants(env):
    assert save(env,body(env)).status_code==200
    with env.app.connect() as conn:
        assert conn.execute('SELECT count(*) FROM pilot_contact_drafts').fetchone()==(0,)
        for privilege in ('UPDATE','DELETE','TRUNCATE'):
            assert conn.execute("SELECT has_table_privilege(current_user,'pilot_contact_drafts',%s)",(privilege,)).fetchone()==(False,)


def test_concurrent_same_request_has_one_original_receipt(env):
    value=body(env)
    sessions=[verify_token_claims(issue_token(env.users[0],SECRET),SECRET) for _ in range(3)]
    service=ContactDraftStore(env.app)
    with ThreadPoolExecutor(max_workers=3) as pool:
        replies=list(pool.map(lambda claims:service.save(claims,value),sessions))
    assert replies[0]==replies[1]==replies[2]
    with env.admin.connect() as conn:
        assert conn.execute('SELECT count(*) FROM pilot_contact_drafts WHERE opportunity_id=%s',(env.opp,)).fetchone()==(1,)


def test_revoked_session_cannot_save_or_recover(env):
    value=body(env); assert save(env,value).status_code==200
    claims=verify_token_claims(env.client.headers['Authorization'].removeprefix('Bearer '),SECRET)
    PilotSessionRegistry(env.app).revoke([claims])
    assert recover(env,value).status_code==401
    assert latest(env).status_code==401
    assert save(env,body(env,version=3,saved=value['snapshot']['draft']['content'])).status_code==401


def test_storage_error_rolls_back_and_same_request_can_be_saved(env):
    value=body(env)
    # Reproduce a failing INSERT with an isolated table constraint; no mock store.
    name='synthetic_reject_'+uuid4().hex
    with env.admin.connect() as conn:
        conn.execute(sql.SQL('ALTER TABLE pilot_contact_drafts ADD CONSTRAINT {} CHECK (opportunity_id <> {})')
            .format(sql.Identifier(name),sql.Literal(env.opp)))
    try:
        assert save(env,value).status_code==500
        assert recover(env,value).status_code==404  # Unknown to client, never FAILED.
    finally:
        with env.admin.connect() as conn:
            conn.execute(sql.SQL('ALTER TABLE pilot_contact_drafts DROP CONSTRAINT {}').format(sql.Identifier(name)))
    assert save(env,value).status_code==200
