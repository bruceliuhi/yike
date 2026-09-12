"""Synthetic navigation contracts, not evidence of real buyer supply."""
import asyncio
import copy
import time

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from pilot import open_web_reader as reader_module
from pilot import open_web_reader_worker as html_worker
from pilot.codex_research_worker import _ReadEvents, _InvalidOutput
from pilot.public_read_session import PublicReadSession
from pilot.research_tools import build_server
from tests.test_open_web_reader import install_transport, response
from tests.test_public_read_session import Reader, dispatcher, evidence
from tests.test_codex_research_worker import search_event, read_event

INDEX = 'https://new-source.example/project'
POST = 'https://new-source.example/t/BuyerCase'


def test_visible_html_links_and_parent_sanitization(monkeypatch):
    html = b'''<base href="https://evil.example/"><a href="/t/BuyerCase#reply">Buyer</a>
        <div hidden><a href="/hidden">Hidden</a></div>
        <a href="/t/BuyerCase">duplicate</a><a href="/?token=PRIVATE">private</a>
        <a href="http://public.example/">http</a><a href="https://127.0.0.1/">local</a>
        <script><a href="/script">script</a></script>'''
    install_transport(monkeypatch, response(html))
    raw = html_worker.read_request({'url': INDEX, 'timeout_seconds': 2})
    assert POST + '#reply' in raw.get('links', [])
    assert not any('/hidden' in url or '/script' in url for url in raw['links'])
    clean = reader_module._sanitize_page_links(raw)
    assert clean['links'] == [POST]
    assert 'PRIVATE' not in str(clean)
    assert reader_module.valid_page_evidence(clean, INDEX)


def test_optional_links_exact_canonical_bounded_contract():
    original = evidence(INDEX)
    assert reader_module.valid_page_evidence(original, INDEX)
    assert reader_module.valid_page_evidence(original | {'links': [POST]}, INDEX)
    for links in ([POST, POST], ['https://localhost/'], ['https://public.example/?token=x'],
                  [POST + '#reply'], ['http://public.example/'], [1], 'bad',
                  [f'https://public.example/{i}' for i in range(51)]):
        assert not reader_module.valid_page_evidence(original | {'links': links}, INDEX)
    assert not reader_module.valid_page_evidence(original | {'links': [], 'unknown': True}, INDEX)


def test_mcp_host_read_chain_and_replay_keep_mission_bounds():
    class LinkedReader(Reader):
        def read(self, url, *, deadline):
            result = super().read(url, deadline=deadline)
            return result | {'links': [POST]} if url == INDEX else result
    reader = LinkedReader()
    host = PublicReadSession(max_reads=2, deadline=time.monotonic()+60,
        allowed_url=lambda url: url == INDEX, effect_dispatcher=dispatcher, reader=reader)
    def read(url, *, deadline):
        result = host.read(url, deadline=time.monotonic()+20)
        assert result['status'] == 'READ'
        return result['evidence']
    def search(query):
        result = copy.deepcopy(search_event()['item']['result']['structured_content'])
        result['query'] = query
        return result
    async def scenario():
        server = build_server(max_reads=2, max_seconds=60, reader=read, searcher=search)
        async with create_connected_server_and_client_session(server) as session:
            await session.call_tool('search_public_web', {'query': '买方需求'})
            before = await session.call_tool('read_public_page', {'url': POST})
            assert before.structuredContent['code'] == 'invalid_url'
            first = await session.call_tool('read_public_page', {'url': INDEX})
            assert first.structuredContent['status'] == 'READ'
            second = await session.call_tool('read_public_page', {'url': POST})
            assert second.structuredContent['status'] == 'READ'
            again = await session.call_tool('read_public_page', {'url': POST})
            assert again.structuredContent['replayed'] is True
            unknown = await session.call_tool('read_public_page', {'url': 'https://other.example/'})
            assert unknown.structuredContent['code'] == 'invalid_url'
    try:
        asyncio.run(scenario())
        assert [url for url, _ in reader.calls] == [INDEX, POST]
    finally:
        host.close()


def test_failed_page_cannot_grant_navigation():
    class InvalidReader(Reader):
        def read(self, url, *, deadline):
            return evidence(url) | {'links': [POST], 'content_sha256': 'bad'}
    host = PublicReadSession(max_reads=2, deadline=time.monotonic()+60,
        allowed_url=lambda url: url == INDEX, effect_dispatcher=dispatcher, reader=InvalidReader())
    try:
        assert host.read(INDEX, deadline=time.monotonic()+20)['status'] == 'FAILED'
        assert host.read(POST, deadline=time.monotonic()+20)['code'] == 'invalid_url'
    finally:
        host.close()


def test_codex_event_acceptance_follows_only_verified_page_links():
    events = _ReadEvents(search_enabled=True)
    events.accept(search_event())
    index = read_event()
    index['item']['result']['structured_content']['evidence']['links'] = [POST]
    events.accept(index)
    post = read_event('post')
    post['item']['arguments']['url'] = POST
    post['item']['result']['structured_content']['evidence']['url'] = POST
    events.accept(post)
    assert len(events.reads) == 2
    unknown = copy.deepcopy(post)
    unknown['item']['id'] = 'unknown'
    unknown['item']['arguments']['url'] = 'https://other.example/'
    with pytest.raises(_InvalidOutput):
        events.accept(unknown)


@pytest.mark.parametrize('sources,expected', [(2,(1,1)), (3,(2,2)), (8,(7,7)), (100,(10,99))])
def test_customer_source_budget_reserves_original_reads(sources, expected):
    from pilot import dynamic_research_runtime
    allocation = getattr(dynamic_research_runtime, '_discovery_limits', None)
    assert callable(allocation), 'missing search/read budget allocation'
    assert allocation(sources) == expected


@pytest.mark.parametrize('read_after', [2, 7])
def test_read_then_community_search_can_use_remaining_shared_allowance(read_after):
    from pilot.dynamic_research_runtime import _discovery_limits
    from pilot.public_search import PublicSearchSession
    from pilot.research_effects import EffectDispatchError
    searches, reads = _discovery_limits(8)
    actions = []
    def bounded(kind, payload, deadline, perform):
        if len(actions) >= 8:
            raise EffectDispatchError()
        actions.append(kind)
        return perform(deadline)
    search = PublicSearchSession(api_key='synthetic-navigation', max_searches=searches,
        deadline=time.monotonic()+60, effect_dispatcher=bounded)
    search._run = lambda query, **kwargs: (
        copy.deepcopy(search_event()['item']['result']['structured_content']) | {'query': query})
    host = PublicReadSession(max_reads=reads, deadline=time.monotonic()+60,
        allowed_url=lambda url: True, effect_dispatcher=bounded, reader=Reader())
    try:
        for i in range(7):
            if i == read_after:
                assert host.read(INDEX, deadline=time.monotonic()+20)['status'] == 'READ'
            assert search.search(f'community {i}')['status'] == 'SEARCHED'
        if read_after == 7:
            assert host.read(INDEX, deadline=time.monotonic()+20)['status'] == 'READ'
        assert len(actions) == 8 and actions.count('READ') == 1
        assert host.read(POST, deadline=time.monotonic()+20)['status'] == 'FAILED'
        assert search.search('ninth source')['status'] == 'FAILED'
        assert len(actions) == 8
    finally:
        search.close()
        host.close()
