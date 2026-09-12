"""Human declarations remain separate from frozen source facts."""
from datetime import UTC, datetime
from uuid import uuid4
import pytest
from pilot.candidate_review_contract import validate_payload, CandidateReviewError


def evidence(**changes):
    return dict(schemaVersion='human-demand-evidence-v1', authorLocator='楼层 2 小王',
        authorExcerpt='小王', demandExcerpt='采购输送设备', publishedDate='2026-09-13',
        dateExcerpt='2026-09-13') | changes


def verification(**changes):
    return dict(candidateId=str(uuid4()), candidateRevision=1, sourceVersionId=str(uuid4()),
        profileId=str(uuid4()), profileVersion=1, requestId=str(uuid4()), humanConfirmed=True,
        status='OPEN', openingMethod='DIRECT', locator='原文', excerpt='采购输送设备',
        contactMethod='COMMENT', demandEvidence=evidence()) | changes


def test_six_field_verification_roundtrips_without_normalizing():
    value = verification(demandEvidence=evidence(authorLocator=' 楼层 2 '))
    assert validate_payload(value, verification=True).demandEvidence.model_dump() == value['demandEvidence']


@pytest.mark.parametrize('changes', [dict(publishedDate='2026-02-30'), dict(publishedDate='2026-9-13'),
    dict(publishedDate='2026-09-13T00:00:00Z'), dict(authorExcerpt=''), dict(authorLocator='x'*257),
    dict(demandExcerpt='x'*2001), dict(checkedBy='伪造')])
def test_bad_declarations_rejected(changes):
    with pytest.raises(CandidateReviewError):
        validate_payload(verification(demandEvidence=evidence(**changes)), verification=True)


def test_absent_extension_and_explicit_null_are_distinct():
    value = verification()
    value.pop('demandEvidence')
    assert 'demandEvidence' not in validate_payload(value, verification=True).model_dump(exclude_unset=True)
    with pytest.raises(CandidateReviewError):
        validate_payload(value | {'demandEvidence': None}, verification=True)


def test_legacy_projection_preserves_original_date_and_omits_only_extensions():
    from pilot.candidate_demand_evidence import legacy_projection
    value = {'publishedAt': '', 'sourceVerification': {'id': 'x', 'demandEvidence': evidence()},
        'assessment': {'id': 'a', 'demandEvidenceId': 'x'}}
    assert legacy_projection(value) == {'publishedAt': '', 'sourceVerification': {'id': 'x'}, 'assessment': {'id': 'a'}}
    assert 'demandEvidence' in value['sourceVerification']


def test_http_evidence_version_is_explicit_and_legacy_read_shape_preserved():
    from tests.test_candidate_review_api import client_for, headers, ReviewBoundary, source_body
    class Extended(ReviewBoundary):
        def _call(self, *args, **kwargs):
            return {'sourceVerification': {'id': 'v', 'demandEvidence': evidence()},
                'assessment': {'demandEvidenceId': 'v'}, 'publishedAt': ''}
    client = client_for(Extended())
    for path in ('/api/ui/candidates','/api/ui/candidate-review-requests/abc'):
        assert client.get(path,headers=headers()).json()['sourceVerification'] == {'id': 'v'}
        response = client.get(path+'?evidenceVersion=1',headers=headers())
        assert response.status_code == 200
        assert response.json()['sourceVerification']['demandEvidence'] == evidence()
        assert client.get(path+'?evidenceVersion=2',headers=headers()).status_code == 422
    response = client.post('/api/ui/candidate-source-verifications?evidenceVersion=1',
        headers=headers(),json=source_body() | {'demandEvidence': evidence()})
    assert response.status_code == 200 and 'demandEvidence' in response.json()['sourceVerification']


def test_human_opportunity_requires_explicit_upgrade_without_faking_evidence():
    from fastapi.testclient import TestClient
    from pilot.web import build_app
    from tests.test_ui_api import FakeStore
    from tests.test_candidate_review_api import headers, SECRET
    data = {'published_at': '2026-09-13T00:00:00+08:00', 'source_evidence': {
        'status':'CAPTURED','snapshot_sha256':'a'*64,'snapshot':{'verification':{'demandEvidence':evidence()}}}}
    store = FakeStore()
    store.get_opportunity = lambda *_: data
    store.list_followups = lambda *_: []
    client = TestClient(build_app(store,auth_secret=SECRET),base_url='https://pilot.example')
    path = '/api/ui/opportunities/one'
    assert client.get(path,headers=headers()).status_code == 409
    assert client.get(path,headers=headers()).json()['detail']['code'] == 'client_upgrade_required'
    response = client.get(path+'?evidenceVersion=1',headers=headers())
    assert response.status_code == 200 and response.json()['opportunity'] == data
    assert client.get(path+'?evidenceVersion=2',headers=headers()).status_code == 422
