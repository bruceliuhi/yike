"""Revalidation preserves absence, but never trusts copied model fields."""
import pytest

from pilot.candidate_contract import CandidateContractError, validate_candidate_batch
from pilot.execution_runtime import _raw_model
from tests.test_candidate_contract import NOW, batch


def test_execution_raw_candidate_preserves_absent_source_context():
    original = validate_candidate_batch(batch(), now=NOW)
    raw = _raw_model(original)
    assert 'source_context' not in raw['records'][0]
    assert validate_candidate_batch(raw, now=NOW) == original


def test_execution_raw_candidate_keeps_explicit_null_for_rejection():
    original = validate_candidate_batch(batch(), now=NOW)
    forged = original.model_copy(update={'records': (
        original.records[0].model_copy(update={'source_context': None}),)})
    with pytest.raises(CandidateContractError):
        validate_candidate_batch(_raw_model(forged), now=NOW)


def test_execution_raw_candidate_does_not_coerce_forged_boolean_version():
    original = validate_candidate_batch(batch(), now=NOW)
    forged = original.model_copy(update={'execution':
        original.execution.model_copy(update={'credential_version': True})})
    raw = _raw_model(forged)
    assert raw['execution']['credential_version'] is True
    with pytest.raises(CandidateContractError):
        validate_candidate_batch(raw, now=NOW)
