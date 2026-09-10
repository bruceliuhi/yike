"""Bounded provider protocol tests; synthetic material, no external provider."""
import asyncio
import json

import httpx
import pytest

from pilot.candidate_assessment_model import OpenAICompatibleCandidateAssessmentModel
from pilot.material_model import MaterialExtractionModel, MaterialModelError


TEXT = '我们为华东工厂开发质量检测系统。'
RESULT = {'fields': {'service': '质量检测系统'},
          'evidence': [{'field': 'service', 'quote': '质量检测系统'}]}


def envelope(value=RESULT, **message):
    return {'choices': [{'finish_reason': 'stop', 'message': {
        'role': 'assistant', 'content': json.dumps(value, ensure_ascii=False), **message}}]}


def model(handler, timeout=20):
    config = OpenAICompatibleCandidateAssessmentModel(
        base_url='https://synthetic.invalid/v1', api_key='synthetic-secret', model='synthetic')
    return MaterialExtractionModel(config, timeout_seconds=timeout,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_extract_is_grounded_separate_prompt_and_single_request():
    calls = []
    def respond(request):
        calls.append(request)
        body = json.loads(request.content)
        assert body['messages'][0]['role'] == 'system'
        assert '不可信' in body['messages'][0]['content']
        assert json.loads(body['messages'][1]['content']) == {'text': TEXT}
        assert 'candidate_assessment' not in request.content.decode()
        return httpx.Response(200, json=envelope())
    adapter = model(respond)
    assert adapter.extract(TEXT) == RESULT
    assert len(calls) == 1
    assert 'synthetic-secret' not in repr(adapter)


@pytest.mark.parametrize('reply', [
    envelope({'fields': {'service': '系统'}, 'evidence': [{'field': 'service', 'quote': '虚构原文'}]}),
    envelope({'fields': {'unknown': '不允许'}, 'evidence': [{'field': 'service', 'quote': '系统'}]}),
    envelope(tool_calls=[{'name': 'external_tool'}]),
    {'choices': []},
])
def test_malformed_or_ungrounded_result_is_fixed_failure(reply):
    adapter = model(lambda _: httpx.Response(200, json=reply))
    with pytest.raises(MaterialModelError) as error:
        adapter.extract(TEXT)
    assert str(error.value) == 'material_extraction_failed'
    assert error.value.__context__ is None


def test_redirect_oversize_and_stalled_provider_do_not_retry():
    for response in (httpx.Response(302, headers={'location': 'https://other.invalid'}),
                     httpx.Response(200, content=b'x' * (64 * 1024 + 1))):
        seen = []
        def respond(request):
            seen.append(request)
            return response
        with pytest.raises(MaterialModelError):
            model(respond).extract(TEXT)
        assert len(seen) == 1
    async def stall(_):
        await asyncio.sleep(1)
        return httpx.Response(200, json=envelope())
    with pytest.raises(MaterialModelError):
        model(stall, timeout=.02).extract(TEXT)


def test_untrusted_input_is_rejected_before_network():
    def forbidden(_):
        raise AssertionError('must not call provider')
    for value in ('', 'a' * 2001, 'private\0text'):
        with pytest.raises(MaterialModelError):
            model(forbidden).extract(value)
