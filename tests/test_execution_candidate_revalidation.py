"""Execution's raw revalidation must preserve the candidate wire contract."""
import pytest

from pilot.candidate_contract import CandidateContractError, batch_fingerprint, validate_candidate_batch
from pilot.execution_runtime import _raw_model
from tests.test_candidate_contract import NOW, batch, record
from tests.test_public_author_context_backend import public_batch, public_record


@pytest.mark.parametrize('platform,url', [
    ('BILIBILI', 'https://www.bilibili.com/video/BV1abc'),
    ('XIAOHONGSHU', 'https://www.xiaohongshu.com/explore/66c01234abcdef0123456789'),
    ('DOUYIN', 'https://www.douyin.com/video/7123456789'),
    ('ZHIHU', 'https://www.zhihu.com/question/123/answer/456'),
])
def test_execution_revalidates_ordinary_candidate_without_inventing_context(platform, url):
    payload = batch(platform=platform, records=[record(public_url=url)])
    original = validate_candidate_batch(payload, now=NOW)
    raw = _raw_model(original)
    assert raw == payload
    checked = validate_candidate_batch(raw, now=NOW)
    assert batch_fingerprint(checked) == batch_fingerprint(original)


def test_execution_retains_real_author_context_and_its_signature_binding():
    payload = public_batch(public_record())
    original = validate_candidate_batch(payload, now=NOW)
    raw = _raw_model(original)
    assert raw == payload
    assert batch_fingerprint(validate_candidate_batch(raw, now=NOW)) == batch_fingerprint(original)


@pytest.mark.parametrize('change', ['explicit_null', 'boolean_credential', 'future_observation'])
def test_raw_revalidation_still_rejects_forged_model_copy(change):
    original = validate_candidate_batch(batch(), now=NOW)
    if change == 'boolean_credential':
        forged = original.model_copy(update={'execution':
            original.execution.model_copy(update={'credential_version': True})})
    else:
        fields = {'source_context': None} if change == 'explicit_null' else {
            'observed_at': '2099-01-01T00:00:00Z'}
        forged = original.model_copy(update={'records':
            (original.records[0].model_copy(update=fields),)})
    with pytest.raises(CandidateContractError):
        validate_candidate_batch(_raw_model(forged), now=NOW)
