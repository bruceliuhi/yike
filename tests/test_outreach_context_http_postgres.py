"""Real HTTP/restricted PG target resolution, synthetic prior platform facts."""
import copy
from uuid import uuid4

import pytest

from pilot.auth import issue_token
from pilot.store import PilotStore
from tests.test_contact_drafts_http_postgres import (
    SECRET, body, databases, env, execution_databases, rehash, save,
)


def connected(env, user=None):
    store=PilotStore(env.app)
    user=user or env.users[0]
    device=store.register_device(user,'synthetic-contact-device')['device_id']
    connection=store.connect_platform(user,'BILIBILI',device,'our-account','vault://synthetic-private-profile')
    # Synthetic trusted local observation, not an actual platform login.
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_platform_connections SET status='CONNECTED' WHERE connection_id=%s",(connection['connection_id'],))
        version=conn.execute('SELECT connection_version FROM pilot_platform_connections WHERE connection_id=%s',(connection['connection_id'],)).fetchone()[0]
    return dict(deviceId=device,connectionId=connection['connection_id'],connectionVersion=version)


def prepared(env,channel='dm',user=None):
    connection=connected(env,user)
    value=body(env,channel=channel)
    value['snapshot']['draft'].update(accountId=connection['connectionId'],recipient='comment-author')
    rehash(value)
    assert save(env,value).status_code==200
    return dict(binding=value['binding'],**connection),value


def context(env,request,**kw): return env.client.post('/api/ui/outreach/context',json=request,**kw)


@pytest.mark.parametrize('channel,action',[('comment','COMMENT_REPLY'),('dm','DIRECT_MESSAGE')])
def test_resolves_demand_author_not_parent_or_blogger_without_granting_send(env,channel,action):
    request,value=prepared(env,channel)
    response=context(env,request)
    assert response.status_code==200,response.text
    result=response.json()
    assert result['target']['action']==action
    assert result['target']['authorPublicId']=='comment-author'
    assert result['target']['commentId']=='comment-8'
    assert result['target']['postId']=='BV1public'
    assert result['draft']['content']==value['snapshot']['draft']['content']
    assert result['binding']==request['binding']
    assert result['authorization']=='NOT_GRANTED'
    assert result['channelCapability']['status']=='UNVERIFIED'
    assert 'vault://' not in response.text and 'session_ref' not in response.text
    assert 'confirmationToken' not in result
    assert len(result['contextSha256'])==64
    assert context(env,request).json()==result
    with env.admin.connect() as conn:
        assert conn.execute('SELECT count(*) FROM pilot_outreach_confirmations WHERE opportunity_id=%s',(env.opp,)).fetchone()==(0,)


@pytest.mark.parametrize('change',['connection-version','connection','device','source','profile','recipient','draft'])
def test_changed_facts_and_wrong_recipient_fail_closed(env,change):
    request,value=prepared(env)
    with env.admin.connect() as conn:
        if change=='connection-version': request['connectionVersion']+=1
        elif change=='connection': conn.execute("UPDATE pilot_platform_connections SET status='DISCONNECTED' WHERE connection_id=%s",(request['connectionId'],))
        elif change=='device': conn.execute("UPDATE pilot_devices SET status='REVOKED' WHERE device_id=%s",(request['deviceId'],))
        elif change=='source': conn.execute("UPDATE pilot_sources SET health='BLOCKED' WHERE source_id=%s",(env.source,))
        elif change=='profile': conn.execute("UPDATE business_profile_versions SET status='REVOKED' WHERE profile_version_id=%s",(env.profile,))
    if change in ('recipient','draft'):
        updated=copy.deepcopy(value)
        updated['previousRequestId']=value['binding']['requestId']
        updated['binding']['requestId']=str(uuid4())
        updated['snapshot']['draft'].update(version=3,savedContent=value['snapshot']['draft']['content'])
        if change=='recipient': updated['snapshot']['draft']['recipient']='parent-author'
        rehash(updated); assert save(env,updated).status_code==200
        if change=='recipient': request['binding']=updated['binding']
    assert context(env,request).status_code==409


def test_cannot_use_other_owner_connection_or_private_draft(env):
    request,_=prepared(env,user=env.users[1])
    assert context(env,request).status_code==409
    for user in env.users[1:]:
        assert context(env,request,headers={'Authorization':'Bearer '+issue_token(user,SECRET)}).status_code==404
    env.client.headers.pop('Authorization')
    assert context(env,request).status_code==401


def test_rejects_unsaved_client_target_or_secret_in_input(env):
    request,_=prepared(env)
    assert context(env,request|{'authorPublicId':'parent-author','session_ref':'vault://private'}).status_code==422


@pytest.mark.parametrize('env',['POST','PAGE'],indirect=True)
def test_post_comments_target_post_and_unmapped_pages_are_not_invented(env):
    request,_=prepared(env,channel='comment')
    with env.admin.connect() as conn:
        kind=conn.execute("SELECT payload#>>'{source,kind}' FROM pilot_opportunity_evidence WHERE opportunity_id=%s",(env.opp,)).fetchone()[0]
    response=context(env,request)
    if kind=='PAGE':
        assert response.status_code==409
    else:
        assert response.status_code==200,response.text
        assert response.json()['target']==dict(action='POST_COMMENT',authorPublicId='comment-author',
            postId='BV1public',commentId=None)
