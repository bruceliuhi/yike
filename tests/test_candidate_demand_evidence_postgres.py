"""Synthetic mixed page through real restricted PG, no provider or platform calls."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo
import pytest
from tests.test_candidate_review_postgres import (databases, env, execution_databases,
    execution_env, raw_databases, raw_env, seed, store, review_payload, verification_payload,
    BoundaryModel, assessment, CONTENT)
from tests.test_candidate_demand_evidence import evidence
from pilot.candidate_review_contract import CandidateReviewError
from tests.test_dynamic_research_candidates_postgres import (journal_env, context_env,
    real_strategy_env, successful_read, read_result, publish)


class PageModel(BoundaryModel):
    industry_strategy_version = 'industry-task-strategy-v1'
    def assess(self, **kwargs):
        kwargs.pop('industry_strategy', None)
        value, _ = super().assess(**kwargs)
        content = kwargs['content']
        for key in ('intent','urgency'):
            if content.get('source_read_scope') == 'UNATTRIBUTED_PAGE':
                value[key] = dict(level='UNKNOWN', reason='需要人工归属确认', citations=[])
            elif content.get('source_read_scope') == 'HUMAN_CONFIRMED_EXCERPT':
                value[key]['citations'] = [dict(field='author_updates.0', quote='采购输送设备')]
        return value, dict(prompt_tokens=2, completion_tokens=1, total_tokens=3)


def setup_page(env):
    day = datetime.now(UTC).date().isoformat()
    body = CONTENT['body'] + '\n小王 ' + day + '\n第三方：我已找到供应商'
    binding = seed(env, body=body, published_at=None, author_public_id=None,
        normalizer_version='dynamic-public-read-v1', collector_version='public-web-agent-v1')
    return binding, evidence(publishedDate=day, dateExcerpt=day), body


def include(binding, assessed, check):
    return review_payload(binding, 'INCLUDE', assessmentId=assessed['assessment']['id'],
        sourceVerificationId=check['id'], humanConfirmed=True, evidence=assessment()['evidence'], reason='人工归属和时间确认')


def test_mixed_page_supplement_reassess_include_preserves_raw_and_personal_evidence(env):
    b, declaration, body = setup_page(env)
    model = PageModel()
    service = store(env, model)
    before = service.review(env.claims, review_payload(b))
    assert before['assessment']['intent']['level'] == 'UNKNOWN'
    assert before['assessment']['decision'] == assessment()['decision']
    request = verification_payload(b, demandEvidence=declaration)
    check = service.verify_source(env.claims, request)
    assert service.verify_source(env.claims, request) == check
    assert check['demandEvidence'] == declaration and model.calls == 1
    assert service.list_candidates(env.claims)['items'][0]['assessmentStale']
    with pytest.raises(CandidateReviewError, match='assessment_conflict'):
        service.review(env.claims, include(b, before, check))
    after = service.review(env.claims, review_payload(b))
    assert after['assessment']['demandEvidenceId'] == check['id'] and model.calls == 2
    assert model.last_input[1]['author_updates'] == [declaration['demandExcerpt']]
    assert 'demandEvidenceId' not in str(model.last_input)
    result = service.review(env.claims, include(b, after, check))
    opportunity = env.store.get_opportunity(env.claims.user_id, result['receipt']['opportunityId'])
    assert opportunity['public_excerpt'] == declaration['demandExcerpt']
    assert opportunity['buyer'] == declaration['authorLocator']
    current = service.list_candidates(env.claims)['items'][0]
    assert current['publishedAt'] == '' and current['excerpt'] == body
    assert current['sourceVerification']['demandEvidence'] == declaration
    assert current['assessment']['demandEvidenceId'] == check['id']
    assert after['assessment']['sendingAuthorized'] is False
    with env.admin.connect() as conn:
        saved = conn.execute('SELECT payload FROM pilot_opportunity_evidence WHERE opportunity_id=%s',
            (result['receipt']['opportunityId'],)).fetchone()[0]
    assert saved['source']['body'] == body and saved['source']['published_at'] is None
    assert saved['verification']['demandEvidence'] == declaration
    assert saved['verification']['demandEvidenceId'] == check['id']


@pytest.mark.parametrize('field', ['authorExcerpt','demandExcerpt','dateExcerpt'])
def test_each_human_excerpt_must_match_frozen_page(env, field):
    b, declaration, _ = setup_page(env)
    with pytest.raises(CandidateReviewError, match='source_excerpt_mismatch'):
        store(env).verify_source(env.claims, verification_payload(b,
            demandEvidence=declaration | {field:'不在原文中的断言'}))


@pytest.mark.parametrize('status', ['BLOCKED','EXPIRED','UNVERIFIED'])
def test_negative_verification_cannot_declare_demand(env, status):
    b, declaration, _ = setup_page(env)
    with pytest.raises(CandidateReviewError, match='demand_evidence_unavailable'):
        store(env).verify_source(env.claims, verification_payload(b, status=status,demandEvidence=declaration))


def test_structured_source_cannot_refresh_date_with_supplement(env):
    b = seed(env)
    with pytest.raises(CandidateReviewError, match='demand_evidence_unavailable'):
        store(env).verify_source(env.claims, verification_payload(b,demandEvidence=evidence()))


def test_replacing_identical_excerpt_receipt_invalidates_assessment_and_cache(env):
    b, declaration, _ = setup_page(env)
    model, service = PageModel(), None
    service = store(env, model)
    first = service.verify_source(env.claims, verification_payload(b,demandEvidence=declaration))
    assessed = service.review(env.claims, review_payload(b))
    second = service.verify_source(env.claims, verification_payload(b,demandEvidence=declaration))
    assert second['id'] != first['id']
    with pytest.raises(CandidateReviewError, match='assessment_conflict'):
        service.review(env.claims, include(b,assessed,second))
    assert service.list_candidates(env.claims)['items'][0]['assessmentStale']
    fresh = service.review(env.claims,review_payload(b))
    assert fresh['assessment']['demandEvidenceId'] == second['id'] and model.calls == 2
    assert service.get_request(env.claims,assessed['requestId']) == assessed


@pytest.mark.parametrize('change', ['withdraw','expired','version'])
def test_obsolete_evidence_cannot_authorize_old_assessment(env,monkeypatch,change):
    import pilot.candidate_review as module
    b, declaration, body = setup_page(env)
    service = store(env,PageModel())
    check = service.verify_source(env.claims,verification_payload(b,demandEvidence=declaration))
    assessed = service.review(env.claims,review_payload(b))
    if change == 'withdraw':
        service.verify_source(env.claims,verification_payload(b,status='BLOCKED'))
    elif change == 'expired':
        clock = module._now
        monkeypatch.setattr(module,'_now',lambda cursor: clock(cursor)+timedelta(hours=25))
    else:
        seed(env,body=body+'新版',published_at=None,author_public_id=None,
            normalizer_version='dynamic-public-read-v1',collector_version='public-web-agent-v1')
    with pytest.raises(CandidateReviewError,match='assessment_conflict|candidate_conflict'):
        service.review(env.claims,include(b,assessed,check))
    page = service.list_candidates(env.claims)['items'][0]
    assert page['assessmentStale'] and 'assessment' not in page
    assert service.get_request(env.claims,assessed['requestId']) == assessed


@pytest.mark.parametrize('days', [-61, 1])
def test_expired_or_future_human_date_is_not_current_evidence(env,days):
    b, declaration, _ = setup_page(env)
    declaration['publishedDate'] = (datetime.now(ZoneInfo('Asia/Shanghai'))+timedelta(days=days)).date().isoformat()
    with pytest.raises(CandidateReviewError,match='source_expired'):
        store(env).verify_source(env.claims,verification_payload(b,demandEvidence=declaration))


@pytest.mark.parametrize('phase', ['before','after'])
def test_concurrent_replacement_blocks_disclosure_or_commit(env,phase):
    b, declaration, _ = setup_page(env)
    model = PageModel()
    service = store(env,model)
    first = service.verify_source(env.claims,verification_payload(b,demandEvidence=declaration))
    def replace():
        return service.verify_source(env.claims,verification_payload(b,demandEvidence=declaration))
    if phase == 'before':
        original = service._prepare_assessment_dispatch
        def racing(*args,**kwargs):
            replace()
            return original(*args,**kwargs)
        service._prepare_assessment_dispatch = racing
    else:
        original = model.assess
        def racing(**kwargs):
            value = original(**kwargs)
            replace()
            return value
        model.assess = racing
    with pytest.raises(CandidateReviewError,match='candidate_conflict'):
        service.review(env.claims,review_payload(b))
    assert model.calls == (0 if phase=='before' else 1)
    with env.admin.connect() as conn:
        assert conn.execute('SELECT count(*) FROM pilot_candidate_assessments WHERE tenant_id=%s',(env.tenant,)).fetchone()[0] == 0


def test_other_owner_cannot_read_verify_or_use_receipt(env):
    from pilot.auth import issue_token,verify_token_claims
    from tests.test_execution_runtime_postgres import SECRET
    b, declaration, _ = setup_page(env)
    service = store(env,PageModel())
    check = service.verify_source(env.claims,verification_payload(b,demandEvidence=declaration))
    other = verify_token_claims(issue_token(env.users[1],SECRET),SECRET)
    with pytest.raises(CandidateReviewError,match='request_not_found'):
        service.get_request(other,check['requestId'])
    with pytest.raises(CandidateReviewError,match='candidate_not_found'):
        service.verify_source(other,verification_payload(b,demandEvidence=declaration))
    assert service.list_candidates(other)['items'] == []


def test_finished_dynamic_research_human_assessment_uses_manual_usage_not_permit(journal_env):
    from pilot.candidate_review import CandidateReviewStore
    from pilot.research_assessment import ResearchAssessmentRunner
    from tests.test_execution_runtime_postgres import apply,operation
    env = journal_env
    day = datetime.now(UTC).date().isoformat()
    declaration = evidence(publishedDate=day,dateExcerpt=day)
    successful_read(env,value=read_result(text=CONTENT['body']+'\n小王 '+day,title=CONTENT['title']))
    item = publish(env)['items'][0]
    b = dict(candidateId=item['candidate_id'],candidateRevision=item['revision'],sourceVersionId=item['version_id'],
        profileId=env.profile,profileVersion=env.profile_number)
    class Both(PageModel):
        def assess_before(self,deadline,**kwargs):
            return self.assess(**kwargs)
    model = Both()
    service = CandidateReviewStore(env.db,model=model,strategy_resolver=env.strategies.resolve,
        strategy_snapshot_reader=env.strategies.read_snapshot,research_assessment=ResearchAssessmentRunner(env.resources))
    origin = dict(task_id=env.execution['task_id'],run_id=env.execution['run_id'],observation_id=item['observation_id'])
    research = service.assess_research(env.claims,review_payload(b),**origin)
    assert research['kind'] == 'assessment'
    assert service.get_model_usage(env.claims,research['requestId'])['state'] == 'NOT_RECORDED'
    apply(env,operation(env,'CANCEL',env.execution))
    check = service.verify_source(env.claims,verification_payload(b,demandEvidence=declaration))
    human = service.review(env.claims,review_payload(b))
    assert human['kind'] == 'assessment' and human['assessment']['demandEvidenceId'] == check['id']
    assert service.get_model_usage(env.claims,human['requestId'])['usage']['total_tokens'] == 3
    assert service.review(env.claims,include(b,human,check))['receipt']['outcome'] == 'IMPORTED'
    with env.admin.connect() as conn:
        assert conn.execute("SELECT count(*) FROM pilot_research_resource_events WHERE tenant_id=%s AND resource='MODEL_CALL'",(env.tenant,)).fetchone()[0] == 1


def test_withdrawal_does_not_revive_pre_supplement_cached_judgment(env):
    b,declaration,_ = setup_page(env)
    model = PageModel()
    service = store(env,model)
    before = service.review(env.claims,review_payload(b))
    service.verify_source(env.claims,verification_payload(b,demandEvidence=declaration))
    service.review(env.claims,review_payload(b))
    service.verify_source(env.claims,verification_payload(b,status='BLOCKED'))
    latest = service.review(env.claims,review_payload(b))
    assert latest['assessment']['id'] != before['assessment']['id'] and model.calls == 3
    assert 'demandEvidenceId' not in latest['assessment']


def test_http_pg_supplement_assess_include_and_old_shape_read(env):
    from fastapi import FastAPI,APIRouter
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from pilot.candidate_review_api import register_candidate_review_api
    b,declaration,_ = setup_page(env)
    service = store(env,PageModel())
    app,router = FastAPI(),APIRouter()
    register_candidate_review_api(router,service,lambda _:SimpleNamespace(claims=env.claims),lambda _:None)
    app.include_router(router)
    client = TestClient(app,base_url='https://pilot.example')
    check = client.post('/candidate-source-verifications?evidenceVersion=1',
        json=verification_payload(b,demandEvidence=declaration))
    assert check.status_code == 200
    assessed = client.post('/candidate-reviews?evidenceVersion=1',json=review_payload(b))
    assert assessed.status_code == 200
    decision = client.post('/candidate-reviews?evidenceVersion=1',json=include(b,assessed.json(),check.json()))
    assert decision.status_code == 200 and decision.json()['receipt']['outcome'] == 'IMPORTED'
    current = client.get('/candidates?evidenceVersion=1').json()['items'][0]
    assert current['sourceVerification']['demandEvidence'] == declaration
    assert current['assessment']['demandEvidenceId'] == check.json()['id']
    legacy = client.get('/candidates').json()['items'][0]
    assert 'demandEvidence' not in legacy['sourceVerification']
    assert 'demandEvidenceId' not in legacy['assessment'] and legacy['publishedAt'] == ''
    import json,os
    if os.environ.get('YIKE_DEMAND_WIRE_CAPTURE') == '1':
        opportunity = env.store.get_opportunity(env.claims.user_id,decision.json()['receipt']['opportunityId'])
        print('YIKE_DEMAND_WIRE='+json.dumps(dict(synthetic=True,
            description='Synthetic source and model boundary; actual restricted PostgreSQL and HTTP receipts.',
            check=check.json(),assessed=assessed.json(),decision=decision.json(),current=current,
            source_evidence=opportunity['source_evidence']),ensure_ascii=False))


def test_unknown_request_replay_never_becomes_new_human_model_call(env):
    from pilot.candidate_assessment_model import AssessmentModelError
    b,declaration,_ = setup_page(env)
    model = PageModel()
    def unknown(**kwargs):
        model.calls += 1
        raise AssessmentModelError('assessment_result_unknown',504)
    model.assess = unknown
    service = store(env,model)
    request = review_payload(b)
    original = service.review(env.claims,request)
    assert original['status'] == 'UNKNOWN'
    service.verify_source(env.claims,verification_payload(b,demandEvidence=declaration))
    assert service.review(env.claims,request) == original and model.calls == 1
    with pytest.raises(CandidateReviewError,match='retry_conflict'):
        service.review(env.claims,review_payload(b,retryOf=request['requestId']))
