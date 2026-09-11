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


@pytest.mark.parametrize('kind', ['assessment', 'suggestion', 'material', 'coach'])
@pytest.mark.parametrize('endpoint,model_id,expected', [
    (ARK, 'doubao-seed-2-1-turbo-260628', {'type': 'disabled'}),
    (ARK, 'unselected-model', None),
    ('https://model.example/v1', 'doubao-seed-2-1-turbo-260628', None),
])
def test_selected_ark_model_uses_bounded_nonthinking_requests(kind, endpoint, model_id, expected):
    from pilot.material_model import MaterialExtractionModel
    from pilot.short_coach_model import ShortCoachModel
    from test_material_model import TEXT, RESULT

    payload = (assessment() if kind == 'assessment' else adapter_content() if kind == 'suggestion'
               else RESULT if kind == 'material' else
               {'content': '请问预算？', 'question': '请问预算？', 'quote': '预算'})
    calls = []
    def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=envelope(payload))

    if kind == 'suggestion':
        with httpx.Client(transport=httpx.MockTransport(handle)) as client:
            result, _ = OpenAICompatibleSearchSuggestionModel(base_url=endpoint,
                api_key='synthetic', model=model_id, http_client=client).generate(description=SD)
            assert result.model_dump() == payload
    else:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        config = OpenAICompatibleCandidateAssessmentModel(base_url=endpoint,
            api_key='synthetic', model=model_id, http_client=client if kind == 'assessment' else None)
        if kind == 'assessment':
            result, _ = config.assess(description=AD, content=CONTENT)
            assert result.model_dump() == payload
        elif kind == 'material':
            assert MaterialExtractionModel(config, http_client=client).extract(TEXT) == payload
        else:
            assert ShortCoachModel(config, http_client=client).generate(sourceText='需要预算',
                content='', channel='comment', purpose='requirement') == payload
    assert len(calls) == 1
    assert calls[0].get('thinking') == expected
    assert calls[0]['max_tokens'] == {'assessment': 4096, 'suggestion': 2048,
                                    'material': 2048, 'coach': 512}[kind]
