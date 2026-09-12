"""Offline input contracts; URLs are test inputs, not verified buyer evidence."""
from copy import deepcopy
import importlib
import importlib.util
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pilot.candidate_contract import _validate_url
from pilot.foreground_collection import four_platform_collection_policy
from pilot.research_strategy_contract import PrepareStrategyRequest, ResearchStrategyConfiguration, _StrategySnapshot


CASES = json.loads((Path(__file__).parent / 'fixtures/native_collection_links.json').read_text())
UUID = '11111111-1111-4111-8111-111111111111'


@pytest.fixture
def links():
    assert importlib.util.find_spec('pilot.native_collection_links'), 'native link planner is not implemented'
    return importlib.import_module('pilot.native_collection_links')


def prepare(platforms=None, urls=None):
    return dict(schema_version='strategy-confirmation-v1', request_id=UUID,
                draft_id=UUID, draft_revision=1, profile_version_id=UUID,
                platforms=['BILIBILI'] if platforms is None else platforms,
                max_records=25, max_runtime_seconds=120,
                configuration=dict(schema_version='research-strategy-v1', name='指定内容',
                                   source='links', keywords=[], exclusions=[],
                                   links=[CASES['valid'][0]['url']] if urls is None else urls,
                                   mode='once', schedule=None, research=None))


@pytest.mark.parametrize('case', CASES['valid'], ids=lambda case: case['expected']['platform'] + '-' + case['expected']['external_id'])
def test_native_url_exact_output_and_idempotent_canonical(links, case):
    parsed = links.parse_native_collection_link(case['url'])
    assert parsed == case['expected']
    assert links.parse_native_collection_link(parsed['canonical_url']) == parsed


@pytest.mark.parametrize('value', CASES['invalid'] + [None, True, 42, {}, [], ''])
def test_rejects_ambiguous_or_unsafe_input_without_echo(links, value):
    with pytest.raises(ValueError, match='^INVALID_NATIVE_COLLECTION_LINK$'):
        links.parse_native_collection_link(value)


def test_multiplatform_plan_preserves_order_and_input(links):
    urls = [CASES['valid'][index]['url'] for index in (6, 1, 8, 2)]
    original = deepcopy(urls)
    result = links.plan_native_collection_links(['BILIBILI', 'DOUYIN', 'XIAOHONGSHU', 'ZHIHU'], urls)
    assert result == tuple(CASES['valid'][index]['expected'] for index in (6, 1, 8, 2))
    assert urls == original


@pytest.mark.parametrize('platforms,urls', [
    ([], [CASES['valid'][0]['url']]),
    (['PUBLIC_WEB'], [CASES['valid'][0]['url']]),
    (['BILIBILI', 'BILIBILI'], [CASES['valid'][0]['url']]),
    (['BILIBILI', 'DOUYIN'], [CASES['valid'][0]['url']]),
    (['DOUYIN'], [CASES['valid'][0]['url']]),
    ('BILIBILI', [CASES['valid'][0]['url']]),
    (['BILIBILI'], CASES['valid'][0]['url']),
    (['BILIBILI'], []),
    (['BILIBILI'], [CASES['valid'][0]['url'], CASES['valid'][0]['expected']['canonical_url']]),
    (['XIAOHONGSHU'], [CASES['valid'][4]['url'], CASES['valid'][5]['url']]),
    (['ZHIHU'], [CASES['valid'][8]['url'], CASES['valid'][9]['url']]),
    (['BILIBILI'], ['https://b23.tv/test']),
    ([None], [CASES['valid'][0]['url']]),
])
def test_rejects_scope_without_echo(links, platforms, urls):
    with pytest.raises(ValueError, match='^INVALID_NATIVE_LINK_SCOPE$'):
        links.plan_native_collection_links(platforms, urls)


def test_bounds(links):
    urls = [f'https://www.douyin.com/video/{index}' for index in range(1, 102)]
    assert len(links.plan_native_collection_links(['DOUYIN'], urls[:100])) == 100
    with pytest.raises(ValueError, match='^INVALID_NATIVE_LINK_SCOPE$'):
        links.plan_native_collection_links(['DOUYIN'], urls)
    for value in ('https://www.douyin.com/video/' + '1' * 21,
                  'https://www.douyin.com/user/' + 'a' * 129,
                  'https://www.douyin.com/video/1?x=' + 'a' * 2048,
                  CASES['valid'][4]['url'] + '?xsec_source=pc&xsec_token=' + 'a' * 1025,
                  CASES['valid'][4]['url'] + '?xsec_source=pc&xsec_token=' + '/' * 1024):
        with pytest.raises(ValueError, match='^INVALID_NATIVE_COLLECTION_LINK$'):
            links.parse_native_collection_link(value)


def test_prepare_rejects_scope_that_previous_generic_url_validation_accepted():
    with pytest.raises(ValidationError):
        PrepareStrategyRequest.model_validate(prepare(['DOUYIN']))


def test_prepare_accepts_xhs_public_parameters_without_rewriting_confirmed_input():
    request = prepare(['XIAOHONGSHU'], [CASES['valid'][5]['url']])
    assert PrepareStrategyRequest.model_validate(request).model_dump(mode='json') == request
    # Candidate evidence and other URL boundaries do not gain a token exception.
    with pytest.raises(ValueError):
        _validate_url(request['configuration']['links'][0], 'XIAOHONGSHU')


def test_keyword_and_research_snapshots_remain_exact_and_no_capability_is_opened():
    request = prepare()
    assert PrepareStrategyRequest.model_validate(request).model_dump(mode='json') == request
    assert not four_platform_collection_policy('BILIBILI', 'PLATFORM_ACCOUNT', request['configuration'])
    old = prepare(['DOUYIN'], ['https://example.com/old-but-valid-link'])
    snapshot = {key: value for key, value in old.items() if key in (
        'profile_version_id', 'configuration', 'platforms', 'max_records', 'max_runtime_seconds')}
    snapshot['strategy_version_id'] = UUID
    assert _StrategySnapshot.model_validate(snapshot).model_dump(mode='json') == snapshot
    old['configuration']['research'] = dict(version=1, demandTypes=['INQUIRY'], maxSoubei=100,
        limits=dict(sources=20, minutes=30, modelCalls=10), stopAtAnyLimit=True,
        evidenceOrder='SOURCE_MATCH_CONTEXT')
    assert PrepareStrategyRequest.model_validate(old).model_dump(mode='json') == old
    old['configuration'].update(source='search', keywords=['AI系统'], research=None)
    assert PrepareStrategyRequest.model_validate(old).model_dump(mode='json') == old


@pytest.mark.parametrize('url', [
    'https://example.com/post?xsec_token=TEST&xsec_source=pc_search',
    'https://www.xiaohongshu.com/login?xsec_token=TEST&xsec_source=pc_search',
    CASES['valid'][4]['url'] + '?access_token=TEST',
])
def test_xhs_exception_cannot_admit_secret_parameters_or_other_routes(url):
    with pytest.raises(ValidationError):
        ResearchStrategyConfiguration.model_validate(prepare(urls=[url])['configuration'])
