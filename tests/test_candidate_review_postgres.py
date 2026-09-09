"""Signed synthetic raw -> real restricted PostgreSQL. Only model boundary replaced."""
import copy
import importlib.util
import json
from datetime import UTC, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from pathlib import Path
from uuid import uuid4

import pytest
import psycopg
from tests.test_candidate_ingestion_postgres import (
    execution_databases, execution_env, databases as raw_databases, env as raw_env,
    service as raw_service, payload, submit, claimed)
from tests.test_candidate_assessment_model import DESCRIPTION, CONTENT, assessment
from pilot.candidate_ingestion import CandidateIngestionError
from pilot.auth import issue_token, verify_token_claims
from tests.test_execution_runtime_postgres import SECRET, change_strategy, apply, operation

TABLES = ('pilot_candidate_reviews', 'pilot_candidate_source_verifications',
          'pilot_candidate_assessments', 'pilot_candidate_review_requests', 'pilot_candidate_call_quota')

@pytest.fixture(scope='module')
def databases(raw_databases):
    admin, db = raw_databases
    grant = Path(__file__).parents[1] / 'deploy/grant_candidate_review.sql'
    if grant.exists():
        with db.connect() as conn:
            role = conn.execute('SELECT current_user').fetchone()[0]
        with admin.connect() as conn:
            conn.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
            conn.execute(grant.read_text())
            conn.execute(grant.read_text())
    yield admin, db

@pytest.fixture
def env(raw_env):
    with raw_env.admin.connect() as conn:
        conn.execute("UPDATE business_profile_versions SET payload=payload || %s::jsonb WHERE profile_version_id=%s",
                     (json.dumps({'description': DESCRIPTION}), raw_env.profile))
    yield raw_env
    with raw_env.admin.connect() as conn:
        for table in TABLES + ('pilot_source_observations', 'pilot_opportunities', 'pilot_source_versions', 'pilot_sources'):
            if conn.execute('SELECT to_regclass(%s)', (table,)).fetchone()[0]:
                conn.execute(f'DELETE FROM {table} WHERE tenant_id=ANY(%s)', (raw_env.tenants,))

class BoundaryModel:
    provider, model = 'synthetic', 'boundary-only'
    rule_version, rule_sha256 = 'test-v1', 'a' * 64
    def __init__(self):
        self.calls = 0
    def assess(self, *, description, content):
        self.calls += 1
        self.last_input = (description, copy.deepcopy(content))
        return assessment(), None

def store(env, model=None):
    assert importlib.util.find_spec('pilot.candidate_review') is not None, 'candidate review service is missing'
    from pilot.candidate_review import CandidateReviewStore
    return CandidateReviewStore(env.db, model=model or BoundaryModel(), strategy_resolver=env.resolver)

def seed(env, **record_changes):
    begun, lease = claimed(env)
    value = payload(env, begun, lease)
    value['records'][0].update(title=CONTENT['title'], body=CONTENT['body'],
                              observed_at=datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ'),
                              published_at=datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ'))
    value['records'][0].update(record_changes)
    item = submit(env, raw_service(env), value)['items'][0]
    return dict(candidateId=item['candidate_id'], candidateRevision=item['revision'],
                sourceVersionId=item['version_id'], profileId=env.profile, profileVersion=1)

def review_payload(binding, action='ASSESS', **changes):
    return binding | dict(requestId=str(uuid4()), action=action) | changes

def verification_payload(binding, **changes):
    return binding | dict(requestId=str(uuid4()), humanConfirmed=True, status='OPEN',
        openingMethod='DIRECT', locator='https://example.com/synthetic',
        excerpt='采购输送设备', contactMethod='COMMENT') | changes

def test_signed_raw_assess_verify_include_and_legacy_read(env):
    service = store(env)
    binding = seed(env)
    request = review_payload(binding)
    result = service.review(env.claims, request)
    assert result['kind'] == 'assessment'
    assert result['assessment']['candidateRevision'] == 1
    assert result['assessment']['intent']['level'] == 'HIGH'
    assert service.review(env.claims, request) == result
    check = service.verify_source(env.claims, verification_payload(binding))
    decision = review_payload(binding, 'INCLUDE', assessmentId=result['assessment']['id'],
        sourceVerificationId=check['id'], humanConfirmed=True, evidence=assessment()['evidence'], reason='人工确认当前线索')
    included = service.review(env.claims, decision)
    assert included['receipt']['outcome'] == 'IMPORTED'
    assert included['receipt']['reviewedBy'] == env.claims.user_id
    assert included['candidate']['status'] == 'IMPORTED'
    opportunity = env.store.get_opportunity(env.claims.user_id, included['receipt']['opportunityId'])
    assert opportunity['source_status'] == 'UNVERIFIED'
    assert opportunity['public_excerpt'] == CONTENT['body']
    assert store(env).get_request(env.claims, decision['requestId']) == included
    page = service.list_candidates(env.claims)
    assert page['total'] == 1 and page['items'][0]['lastReview'] == included['receipt']

def test_reject_forged_fields_and_conflicting_request(env):
    service = store(env)
    binding = seed(env)
    from pilot.candidate_ingestion import CandidateIngestionError
    with pytest.raises(CandidateIngestionError, match='invalid_request'):
        service.review(env.claims, review_payload(binding, reviewedBy='forged'))
    request = review_payload(binding)
    service.review(env.claims, request)
    with pytest.raises(CandidateIngestionError, match='request_conflict'):
        service.review(env.claims, request | {'candidateRevision': 2})

def prepared(env, **changes):
    service = store(env)
    b = seed(env, **changes)
    result = service.review(env.claims, review_payload(b))
    check = service.verify_source(env.claims, verification_payload(b))
    decision = review_payload(b,'INCLUDE',assessmentId=result['assessment']['id'],sourceVerificationId=check['id'],
                              humanConfirmed=True,evidence=assessment()['evidence'],reason='')
    return service,b,result,check,decision

def test_include_empty_reason_duplicate_preserves_shared_words_and_state(env):
    service,b,result,check,decision = prepared(env)
    first = service.review(env.claims,decision)
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_opportunities SET source_status='BLOCKED' WHERE opportunity_id=%s",(first['receipt']['opportunityId'],))
    again = service.review(env.claims,decision | {'requestId':str(uuid4()),'evidence':assessment()['evidence'] | {'matchReason':'本次不同私有判断'}})
    assert again['receipt']['outcome']=='ALREADY_IMPORTED'
    assert again['receipt']['review']['evidence']['matchReason']=='本次不同私有判断'
    old = env.store.get_opportunity(env.claims.user_id,first['receipt']['opportunityId'])
    assert old['source_status']=='BLOCKED' and old['match_reason']==assessment()['evidence']['matchReason']

@pytest.mark.parametrize('case', ['missing','blocked','unknown_date','expired','old_check','forged_check'])
def test_include_source_gates_but_expired_source_can_be_excluded(env,case):
    options = {'published_at':None} if case=='unknown_date' else {'published_at':(datetime.now(UTC)-timedelta(days=61)).strftime('%Y-%m-%dT%H:%M:%SZ')} if case=='expired' else {}
    service,b,result,check,decision = prepared(env,**options)
    if case=='missing': decision.pop('sourceVerificationId')
    if case=='forged_check': decision['sourceVerificationId']=str(uuid4())
    if case=='blocked': service.verify_source(env.claims,verification_payload(b,status='BLOCKED'))
    if case=='old_check':
        with env.admin.connect() as conn:
            conn.execute('ALTER TABLE pilot_candidate_source_verifications DISABLE TRIGGER candidate_review_immutable')
            conn.execute("UPDATE pilot_candidate_source_verifications SET checked_at=clock_timestamp()-interval '25 hours' WHERE tenant_id=%s",(env.tenant,))
            conn.execute('ALTER TABLE pilot_candidate_source_verifications ENABLE TRIGGER candidate_review_immutable')
    with pytest.raises(CandidateIngestionError,match='source_'):
        service.review(env.claims,decision)
    excluded = service.review(env.claims,review_payload(b,'EXCLUDE',assessmentId=result['assessment']['id'],humanConfirmed=True,
        evidence=assessment()['evidence'],reason='不适合纳入'))
    assert excluded['receipt']['outcome']=='EXCLUDED'

def test_same_snapshot_concurrent_alias_and_historical_cache(env):
    model = BoundaryModel()
    entered,release=Event(),Event()
    original=model.assess
    def slow(**kwargs):
        entered.set()
        assert release.wait(10)
        return original(**kwargs)
    model.assess=slow
    service=store(env,model)
    b=seed(env)
    first,second=review_payload(b),review_payload(b)
    claims2=verify_token_claims(issue_token(env.users[0],SECRET),SECRET)
    with ThreadPoolExecutor(2) as pool:
        f=pool.submit(service.review,env.claims,first)
        assert entered.wait(5)
        pending=service.review(claims2,second)
        assert pending['status']=='PROCESSING' and pending['invocationRequestId']==first['requestId']
        release.set()
        result=f.result(timeout=10)
    alias=service.get_request(env.claims,second['requestId'])
    assert alias['assessment']==result['assessment'] and model.calls==1
    third=review_payload(b)
    assert service.review(env.claims,third)['assessment']==result['assessment']
    change_strategy(env,max_records=7)
    assert service.get_request(env.claims,second['requestId'])==alias
    assert service.review(env.claims,third)['assessment']==result['assessment']
    current=service.list_candidates(env.claims)['items'][0]
    assert 'assessment' not in current and current['assessmentStale']

@pytest.mark.parametrize('change', ['description','profile','strategy','raw','session'])
def test_model_network_gap_rechecks_current_authority(env,change):
    model=BoundaryModel()
    service=store(env,model)
    old=(datetime.now(UTC)-timedelta(seconds=10)).strftime('%Y-%m-%dT%H:%M:%SZ')
    b=seed(env,published_at=old,observed_at=old)
    original=model.assess
    def changed(**kwargs):
        if change=='strategy': change_strategy(env,max_records=7)
        elif change=='raw': seed(env,body=CONTENT['body']+' 已取消')
        elif change=='session': service.sessions.revoke([env.claims])
        else:
            with env.admin.connect() as conn:
                if change=='profile': conn.execute("UPDATE business_profile_versions SET status='REVOKED' WHERE profile_version_id=%s",(env.profile,))
                else: conn.execute("UPDATE business_profile_versions SET payload=payload || '{\"description\":\"changed\"}'::jsonb WHERE profile_version_id=%s",(env.profile,))
        return original(**kwargs)
    model.assess=changed
    with pytest.raises(CandidateIngestionError): service.review(env.claims,review_payload(b))
    with env.admin.connect() as conn:
        assert conn.execute('SELECT count(*) FROM pilot_candidate_assessments WHERE tenant_id=%s',(env.tenant,)).fetchone()[0]==0

def test_unknown_explicit_retries_and_call_quota(env):
    model=BoundaryModel()
    def unknown(**kwargs):
        model.calls+=1
        raise RuntimeError('private provider error must never persist')
    model.assess=unknown
    service=store(env,model)
    b=seed(env)
    request=review_payload(b)
    result=service.review(env.claims,request)
    assert result['status']=='UNKNOWN'
    assert service.review(env.claims,request)==result and model.calls==1
    with pytest.raises(CandidateIngestionError,match='explicit_retry_required'):
        service.review(env.claims,review_payload(b))
    for _ in range(2):
        request=review_payload(b,retryOf=request['requestId'])
        assert service.review(env.claims,request)['status']=='UNKNOWN'
    with pytest.raises(CandidateIngestionError,match='attempts_exhausted'):
        service.review(env.claims,review_payload(b,retryOf=request['requestId']))
    assert model.calls==3
    with env.admin.connect() as conn:
        assert conn.execute('SELECT reserved_calls FROM pilot_candidate_call_quota WHERE tenant_id=%s',(env.tenant,)).fetchone()[0]==3
        assert 'private provider' not in str(conn.execute('SELECT result FROM pilot_candidate_review_requests WHERE tenant_id=%s',(env.tenant,)).fetchall())

def test_late_output_unknown_and_read_never_restarts(env):
    service=store(env)
    b=seed(env)
    request=review_payload(b)
    original=service.model.assess
    def late(**kwargs):
        with env.admin.connect() as conn:
            conn.execute('ALTER TABLE pilot_candidate_review_requests DISABLE TRIGGER candidate_review_immutable')
            conn.execute("UPDATE pilot_candidate_review_requests SET created_at=created_at-interval '91 seconds',deadline_at=deadline_at-interval '91 seconds' WHERE tenant_id=%s",(env.tenant,))
            conn.execute('ALTER TABLE pilot_candidate_review_requests ENABLE TRIGGER candidate_review_immutable')
        observed=service.get_request(env.claims,request['requestId'])
        assert observed['status']=='UNKNOWN'
        return original(**kwargs)
    service.model.assess=late
    assert service.review(env.claims,request)['status']=='UNKNOWN'
    assert service.model.calls==1

def test_comment_parent_title_not_own_intent_or_verification(env):
    service=store(env)
    b=seed(env,kind='COMMENT',external_source_id='parent',external_comment_id='comment',body='这个我自己做过',
           title='食品工厂采购输送设备，月底前找人报价')
    result=service.review(env.claims,review_payload(b))
    assert result['status']=='FAILED'
    content=service.model.last_input[1]
    assert content['title'] is None and content['parent']['title']=='食品工厂采购输送设备，月底前找人报价'
    with pytest.raises(CandidateIngestionError,match='source_excerpt_mismatch'):
        service.verify_source(env.claims,verification_payload(b,excerpt='采购输送设备'))

def test_owner_private_rls_immutable_and_no_delete(env):
    service,b,result,check,decision=prepared(env)
    for user in env.users[1:]:
        claims=verify_token_claims(issue_token(user,SECRET),SECRET)
        assert service.list_candidates(claims)['total']==0
        with pytest.raises(CandidateIngestionError,match='request_not_found'):
            service.get_request(claims,check['requestId'])
    with env.db.connect() as conn:
        for table in TABLES:
            assert conn.execute('SELECT row_security_active(%s::regclass)',(table,)).fetchone()[0]
            assert not conn.execute("SELECT has_table_privilege(current_user,%s,'DELETE')",(table,)).fetchone()[0]
            assert conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0]==0

def test_historical_review_snapshot_not_current_pairing(env):
    old=(datetime.now(UTC)-timedelta(seconds=10)).strftime('%Y-%m-%dT%H:%M:%SZ')
    service,b,result,check,decision=prepared(env,published_at=old,observed_at=old)
    included=service.review(env.claims,decision)
    seed(env,body=CONTENT['body']+' 已取消')
    page=service.list_candidates(env.claims)
    assert page['items'][0]['status']=='PENDING_REVIEW' and 'assessment' not in page['items'][0]
    historical=service.list_candidates(env.claims,ids=[b['candidateId']],review_request_id=decision['requestId'],page_size=1)['items'][0]
    assert historical['revision']==1 and historical['lastReview']==included['receipt']
    assert historical['historical'] and not historical['currentBindingValid']
    assert service.get_request(env.claims,decision['requestId'])==included

def test_provider_timeout_is_unknown_not_definitive_failure(env):
    from pilot.candidate_assessment_model import AssessmentModelError
    model=BoundaryModel()
    def timeout(**kwargs): raise AssessmentModelError('assessment_result_unknown',504)
    model.assess=timeout
    result=store(env,model).review(env.claims,review_payload(seed(env)))
    assert result['status']=='UNKNOWN'

def test_concurrent_include_creates_once_and_rolls_back_on_import_failure(env):
    service,b,result,check,decision=prepared(env)
    # A real database constraint fails after the legacy importer has inserted its source.
    with env.admin.connect() as conn:
        conn.execute("ALTER TABLE pilot_opportunities ADD CONSTRAINT synthetic_reject_review CHECK(title<>'食品工厂扩产') NOT VALID")
    try:
        with pytest.raises(CandidateIngestionError,match='review_outcome_unknown'):
            service.review(env.claims,decision)
        with env.admin.connect() as conn:
            for table in ('pilot_sources','pilot_source_versions','pilot_source_observations','pilot_opportunities','pilot_candidate_reviews'):
                assert conn.execute(f'SELECT count(*) FROM {table} WHERE tenant_id=%s',(env.tenant,)).fetchone()[0]==0
        with pytest.raises(CandidateIngestionError,match='request_not_found'):
            service.get_request(env.claims,decision['requestId'])
    finally:
        with env.admin.connect() as conn: conn.execute('ALTER TABLE pilot_opportunities DROP CONSTRAINT synthetic_reject_review')
    claims2=verify_token_claims(issue_token(env.users[0],SECRET),SECRET)
    with ThreadPoolExecutor(2) as pool:
        fs=[pool.submit(service.review,c,decision | {'requestId':str(uuid4())}) for c in (env.claims,claims2)]
        receipts=[f.result(timeout=10)['receipt'] for f in fs]
    assert {r['outcome'] for r in receipts}=={'IMPORTED','ALREADY_IMPORTED'}
    assert len({r['opportunityId'] for r in receipts})==1

def second_owner(env):
    from types import SimpleNamespace
    from nacl.signing import SigningKey
    from pilot.device_credentials import DeviceCredentialStore
    from tests.test_device_credentials_postgres import bind
    other=SimpleNamespace(**vars(env))
    other.claims=verify_token_claims(issue_token(env.users[1],SECRET),SECRET)
    other.device=env.store.register_device(env.users[1],'synthetic-second-owner')['device_id']
    other.key=SigningKey.generate()
    bind(SimpleNamespace(service=DeviceCredentialStore(env.db),claims=other.claims,device=other.device),other.key)
    return other

def test_tenant_quota_shared_across_private_owners_and_duplicates_shared(env):
    from pilot.candidate_review import CandidateReviewStore
    a=seed(env)
    other=second_owner(env)
    b=seed(other)
    model=BoundaryModel()
    service=CandidateReviewStore(env.db,model=model,strategy_resolver=env.resolver,max_daily_calls=1)
    with ThreadPoolExecutor(2) as pool:
        futures=[pool.submit(service.review,c,review_payload(binding)) for c,binding in ((env.claims,a),(other.claims,b))]
        results=[]
        for f in futures:
            try: results.append(f.result(timeout=10))
            except CandidateIngestionError as e: assert e.code=='assessment_quota_exhausted'
    assert len(results)==1 and model.calls==1
    service=store(env)
    receipts=[]
    for owner,binding in ((env,a),(other,b)):
        assessed=service.review(owner.claims,review_payload(binding))
        check=service.verify_source(owner.claims,verification_payload(binding))
        receipts.append(service.review(owner.claims,review_payload(binding,'INCLUDE',assessmentId=assessed['assessment']['id'],
            sourceVerificationId=check['id'],humanConfirmed=True,evidence=assessment()['evidence'],reason=''))['receipt'])
    assert [r['outcome'] for r in receipts]==['IMPORTED','ALREADY_IMPORTED']
    assert receipts[0]['opportunityId']==receipts[1]['opportunityId']

def test_composite_fks_reject_cross_owner_evidence_and_migration_repeat(env):
    service,b,result,check,decision=prepared(env)
    env.admin.migrate()
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with env.admin.connect() as conn:
            conn.execute('INSERT INTO pilot_candidate_assessments(tenant_id,owner_user_id,assessment_id,request_id,binding_hash,content) VALUES(%s,%s,%s,%s,%s,%s::jsonb)',
                (env.tenant,env.users[1],str(uuid4()),result['requestId'],'x','{}'))
    with pytest.raises(psycopg.errors.RaiseException,match='immutable'):
        with env.admin.connect() as conn:
            conn.execute("UPDATE pilot_candidate_assessments SET content='{}' WHERE tenant_id=%s",(env.tenant,))

@pytest.mark.parametrize('change', [{'page':True},{'page_size':True},{'query':' '},{'platform':'unknown'},{'status':'OPEN'},{'ids':[]}])
def test_read_contract_is_strict_without_http(env,change):
    with pytest.raises(CandidateIngestionError,match='invalid_request'):
        store(env).list_candidates(env.claims,**change)

@pytest.mark.parametrize('change',['description','strategy','profile'])
def test_historical_validity_includes_current_profile_and_strategy(env,change):
    service,b,result,check,decision=prepared(env)
    service.review(env.claims,decision)
    if change=='strategy': change_strategy(env,max_records=7)
    else:
        with env.admin.connect() as conn:
            if change=='profile': conn.execute("UPDATE business_profile_versions SET status='REVOKED' WHERE profile_version_id=%s",(env.profile,))
            else: conn.execute("UPDATE business_profile_versions SET payload=payload || '{\"description\":\"changed\"}'::jsonb WHERE profile_version_id=%s",(env.profile,))
    original=service.list_candidates(env.claims,ids=[b['candidateId']],review_request_id=decision['requestId'],page_size=1)['items'][0]
    assert not original['currentBindingValid'] and original['assessmentStale']

def test_completed_collection_needs_no_live_lease_and_same_content_reuses_assessment(env):
    service=store(env)
    old=(datetime.now(UTC)-timedelta(seconds=10)).strftime('%Y-%m-%dT%H:%M:%SZ')
    b=seed(env,published_at=old,observed_at=old)
    with env.admin.connect() as conn:
        conn.execute("UPDATE pilot_collection_tasks SET status='CANCELED' WHERE tenant_id=%s",(env.tenant,))
    result=service.review(env.claims,review_payload(b))
    fresh=seed(env,published_at=old)
    assert fresh==b
    assert service.review(env.claims,review_payload(fresh))['assessment']==result['assessment']
    assert service.model.calls==1

def test_same_author_different_comments_do_not_collapse_opportunities(env):
    service=store(env)
    def comment_model(**kwargs):
        value=assessment()
        value['businessMatch']['citations']=[{'field':'body','quote':'我们工厂'}]
        return value,None
    service.model.assess=comment_model
    opportunities=[]
    for comment_id in ('one','two'):
        b=seed(env,kind='COMMENT',external_source_id='one-parent',external_comment_id=comment_id,author_public_id='same-author')
        assessed=service.review(env.claims,review_payload(b))
        check=service.verify_source(env.claims,verification_payload(b))
        result=service.review(env.claims,review_payload(b,'INCLUDE',assessmentId=assessed['assessment']['id'],sourceVerificationId=check['id'],
            humanConfirmed=True,evidence=assessment()['evidence'],reason=''))
        opportunities.append(result['receipt']['opportunityId'])
    assert len(set(opportunities))==2

def test_model_cannot_mutate_server_grounding(env):
    model=BoundaryModel()
    def malicious(*,description,content):
        content['body']=CONTENT['body']
        return assessment(),None
    model.assess=malicious
    result=store(env,model).review(env.claims,review_payload(seed(env,body='普通闲聊，无采购')))
    assert result['status']=='FAILED'

def test_unverified_source_caps_send_ready_without_rewriting_model_output(env):
    model=BoundaryModel()
    def ready(**kwargs): return assessment() | {'decision':'SEND_READY'},None
    model.assess=ready
    result=store(env,model).review(env.claims,review_payload(seed(env,published_at=None)))
    assert result['assessment']['decision']=='SEND_READY'
    assert result['assessment']['effectiveDecision']=='REVIEW'
    assert result['assessment']['sendingAuthorized'] is False
