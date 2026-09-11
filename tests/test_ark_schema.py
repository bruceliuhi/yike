"""Synthetic transport regressions; never real buyer or deployment evidence."""
from copy import deepcopy
import importlib
import json

import httpx
import pytest

from pilot.candidate_assessment_model import (
    AssessmentContent, AssessmentModelError, OpenAICompatibleCandidateAssessmentModel,
)
from pilot.search_suggestion_model import (
    OpenAICompatibleSearchSuggestionModel, SearchSuggestionError,
    _RequiredStrategySuggestionContent,
)
from test_candidate_assessment_model import DESCRIPTION as AD, CONTENT, assessment
from test_search_suggestion_model import DESCRIPTION as SD, adapter_content

ARK = "https://ark.cn-beijing.volces.com/api/v3"


def transform(value, base_url=ARK):
    module = importlib.import_module('pilot.provider_schema')
    return module.provider_json_schema(value, base_url=base_url)


def test_ark_schema_keeps_original_constraints_as_guidance_without_mutation():
    original = _RequiredStrategySuggestionContent.model_json_schema()
    before = deepcopy(original)
    converted = transform(original)
    assert original == before
    assert converted['required'] == original['required']
    term = converted['properties']['keywords']
    assert 'minItems' not in term and 'maxItems' not in term
    assert 'minItems=1' in term['description'] and 'maxItems=20' in term['description']
    assert 'maxLength' not in term['items']
    assert 'maxLength=80' in term['items']['description']
    role = converted['$defs']['RequiredIndustrySearchStrategy']['properties']['buyerRole']['anyOf'][0]
    assert 'maxLength' not in role
    assert 'maxLength=120' in role['description']
    assert converted['additionalProperties'] is False


@pytest.mark.parametrize('endpoint', [
    'https://model.example/v1', 'http://ark.cn-beijing.volces.com/api/v3',
    'https://ark.cn-beijing.volces.com.attacker.example/api/v3',
    'https://ark.cn-beijing.volces.com/api/v30',
    'https://ark.cn-beijing.volces.com:444/api/v3',
    'https://user@ark.cn-beijing.volces.com/api/v3',
    'https://ark.cn-beijing.volces.com/api/v3?other=1',
])
def test_other_endpoints_keep_original_schema(endpoint):
    original = AssessmentContent.model_json_schema()
    assert transform(original, endpoint) == original


def test_property_names_and_nonlength_constraints_are_not_removed():
    original = {'type': 'object', 'properties': {
        'maxLength': {'type': 'string', 'minLength': 1, 'maxLength': 2, 'description': 'Keep this.'},
        'minItems': {'type': 'integer', 'minimum': 1, 'maximum': 2},
        'enumValue': {'type': 'string', 'enum': ['maxItems', 'minLength']},
    }, 'required': ['maxLength', 'minItems'], 'additionalProperties': False}
    result = transform(original)
    assert set(result['properties']) == set(original['properties'])
    assert result['properties']['minItems'] == original['properties']['minItems']
    assert result['properties']['enumValue'] == original['properties']['enumValue']
    assert result['properties']['maxLength']['description'].startswith('Keep this.')
    assert result['required'] == original['required']


def envelope(value):
    return {'choices': [{'finish_reason': 'stop', 'message': {
        'role': 'assistant', 'content': json.dumps(value, ensure_ascii=False),
    }}]}


@pytest.mark.parametrize('kind', ['assessment', 'suggestion'])
@pytest.mark.parametrize('bad_result', [False, True])
def test_real_adapters_send_compatible_schema_and_keep_strict_local_limits(kind, bad_result):
    calls = []
    payload = assessment() if kind == 'assessment' else adapter_content()
    if bad_result:
        if kind == 'assessment': payload['draftDm'] = '长' * 121
        else: payload['strategy']['intentSignals'] = []

    def handle(request):
        body = json.loads(request.content)
        calls.append(body)
        sc = body['response_format']['json_schema']['schema']
        assert body['response_format']['json_schema']['strict'] is True
        assert sc == transform(AssessmentContent.model_json_schema() if kind == 'assessment'
                               else _RequiredStrategySuggestionContent.model_json_schema())
        return httpx.Response(200, json=envelope(payload))

    transport = httpx.MockTransport(handle)
    if kind == 'assessment':
        # The adapter owns this injected client's async lifecycle.
        client = httpx.AsyncClient(transport=transport)
        model = OpenAICompatibleCandidateAssessmentModel(
            base_url=ARK, api_key='synthetic-test-key', model='probe', http_client=client)
        call = lambda: model.assess(description=AD, content=CONTENT)
        error = AssessmentModelError
    else:
        client = httpx.Client(transport=transport)
        model = OpenAICompatibleSearchSuggestionModel(
            base_url=ARK, api_key='synthetic-test-key', model='probe', http_client=client)
        call = lambda: model.generate(description=SD)
        error = SearchSuggestionError
    try:
        if bad_result:
            with pytest.raises(error) as caught: call()
            assert caught.value.code == ('invalid_assessment_result' if kind == 'assessment'
                                         else 'invalid_suggestion_result')
        else:
            result, _ = call()
            assert result.model_dump() == payload
        assert len(calls) == 1
    finally:
        if kind == 'suggestion': client.close()
