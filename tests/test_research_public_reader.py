import asyncio
from datetime import UTC, datetime, timedelta
import json

import httpx
import pytest

from pilot.execution_contract import ExecutionRuntimeError
from pilot.research_public_reader import read_public_index
from tests.test_research_resource_runner import MemoryEvents, kwargs

ENDPOINT = 'https://www.v2ex.com/api/topics/latest.json'


def topic(**changes):
    return {'id': 17, 'title': '示例公开话题', 'content': '合成读取测试，不是商机',
        'created': int(datetime.now(UTC).timestamp()) - 60, 'url': 'http://www.v2ex.com/t/17#reply2',
        'member': {'username': 'not-retained'}, **changes}


def binding():
    return {key: value for key, value in kwargs().items() if key in ('task_id', 'run_id', 'action_id')}


def network(monkeypatch, handler):
    original = httpx.AsyncClient
    def client(**kwargs):
        assert kwargs['follow_redirects'] is False
        assert kwargs['trust_env'] is False
        return original(**kwargs, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, 'AsyncClient', client)


def test_default_fixed_reader_runs_after_permit_then_records_digest(monkeypatch):
    store, calls, request = MemoryEvents(), [], binding()
    def handler(outbound):
        assert store.event['status'] == 'ISSUED'
        assert str(outbound.url) == ENDPOINT and outbound.method == 'GET'
        assert 'cookie' not in outbound.headers and 'authorization' not in outbound.headers
        calls.append(str(outbound.url))
        return httpx.Response(200, json=[topic()])
    network(monkeypatch, handler)
    result = read_public_index(store, None, **request)
    assert result['event']['status'] == 'SUCCEEDED'
    assert result['event']['resource'] == 'SOURCE_READ'
    assert result['result']['source_url'] == ENDPOINT
    assert result['result']['sample_kind'] == 'LATEST_TOPIC_INDEX'
    assert result['result']['observed_count'] == 1
    assert result['result']['topics'][0]['url'] == 'https://www.v2ex.com/t/17'
    assert 'member' not in result['result']['topics'][0]
    assert read_public_index(store, None, **request)['replayed'] is True
    assert calls == [ENDPOINT]


def test_denied_permit_never_calls_public_source():
    store, calls = MemoryEvents(), []
    store.fail_begin = True
    with pytest.raises(ExecutionRuntimeError, match='resource_limit_exceeded'):
        read_public_index(store, None, **binding(), fetcher=lambda _: calls.append(True))
    assert calls == []


def test_public_reader_forwards_validated_result_to_atomic_completion():
    store, calls = MemoryEvents(), []
    def complete(event, result, digest):
        assert result['topics'][0]['url'] == 'https://www.v2ex.com/t/17'
        assert 'member' not in result['topics'][0]
        calls.append(result['observed_count'])
        return store.finish(None, **{key: event[key] for key in
            ('task_id', 'run_id', 'action_id', 'permit_id')},
            status='SUCCEEDED', output_sha256=digest)
    result = read_public_index(store, None, **binding(), fetcher=lambda _: [topic()],
                               on_success=complete)
    assert result['event']['status'] == 'SUCCEEDED'
    assert calls == [1]


@pytest.mark.parametrize('status,headers,body', [
    (302, {'location': 'http://127.0.0.1/secret'}, b'[]'),
    (429, {'content-type': 'application/json'}, b'[]'),
    (200, {'content-type': 'text/html'}, b'<html>login</html>'),
    (200, {'content-type': 'application/json', 'content-length': '1048577'}, b'[]'),
    (200, {'content-type': 'application/json', 'content-length': 'invalid'}, b'[]'),
    (200, {'content-type': 'application/json', 'content-encoding': 'unknown'}, b'[]'),
    (200, {'content-type': 'application/json'}, b'\xff'),
    (200, {'content-type': 'application/json'}, b'[{"id":1,"id":2}]'),
    (200, {'content-type': 'application/json'}, b'[NaN]'),
])
def test_unsafe_transport_response_is_unknown_without_following_or_retry(monkeypatch, status, headers, body):
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(status, headers=headers, content=body)
    network(monkeypatch, handler)
    result = read_public_index(MemoryEvents(), None, **binding())
    assert result['event']['status'] == 'UNKNOWN'
    assert result['result'] is None
    assert calls == [ENDPOINT]


class Chunks(httpx.AsyncByteStream):
    async def __aiter__(self):
        for _ in range(17):
            yield b'x' * 65536


def test_stream_byte_limit_is_enforced_without_content_length(monkeypatch):
    network(monkeypatch, lambda _: httpx.Response(200, headers={'content-type': 'application/json'}, stream=Chunks()))
    assert read_public_index(MemoryEvents(), None, **binding())['event']['status'] == 'UNKNOWN'


def test_total_deadline_includes_slow_connection_or_response(monkeypatch):
    called = []
    async def handler(_):
        try:
            await asyncio.sleep(2)
            called.append('finished')
            return httpx.Response(200, json=[])
        finally:
            called.append('stopped')
    network(monkeypatch, handler)
    store = MemoryEvents()
    store.deadline = datetime.now(UTC) + timedelta(milliseconds=50)
    assert read_public_index(store, None, **binding())['event']['status'] == 'UNKNOWN'
    assert called == ['stopped']


@pytest.mark.parametrize('payload', [{}, [topic()] * 101, [topic(id=True)],
    [topic(created=253402300799)], [topic(url='https://evil.test/t/17')],
    [topic(content={'private': 'not-text'})], [topic(), topic()],
    [topic(url='https://www.v2ex.com/t/18')]])
def test_public_payload_cannot_smuggle_other_sources_or_invalid_content(payload):
    result = read_public_index(MemoryEvents(), None, **binding(), fetcher=lambda _: payload)
    assert result['event']['status'] == 'UNKNOWN'
    assert result['result'] is None


@pytest.mark.parametrize('source,node', [('v2ex-qna-v1', 'qna'),
    ('v2ex-outsourcing-authors-v1', 'outsourcing')])
def test_fixed_node_routing_and_mismatched_node_rejection(monkeypatch, source, node):
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=[topic(node={'name': node})])
    network(monkeypatch, handler)
    result = read_public_index(MemoryEvents(), None, **binding(), source_id=source)
    assert result['event']['status'] == 'SUCCEEDED'
    assert calls == ['https://www.v2ex.com/api/topics/show.json?node_name=' + node]
    for supplied in ({'name': 'outsourcing' if node == 'qna' else 'qna'}, None, {'name': node, 'url': 'ignored'}):
        result = read_public_index(MemoryEvents(), None, **binding(), source_id=source,
            fetcher=lambda _: [topic(node=supplied)])
        assert result['event']['status'] == ('SUCCEEDED' if supplied and supplied['name'] == node else 'UNKNOWN')
    invalid_url = read_public_index(MemoryEvents(), None, **binding(), source_id=source,
        fetcher=lambda _: [topic(node={'name': node}, url='https://evil.example/t/17')])
    assert invalid_url['event']['status'] == 'UNKNOWN'


def test_catalog_is_closed_immutable_and_keeps_legacy_digest():
    from dataclasses import FrozenInstanceError
    from pilot.research_source_catalog import research_source
    from pilot.research_public_reader import _INPUT_SHA
    latest = research_source('v2ex-latest-v1')
    assert latest.endpoint == ENDPOINT and latest.input_sha == _INPUT_SHA
    assert latest.collector == 'v2ex-latest-v1' and latest.version == 1
    assert len({research_source(x).input_sha for x in
        ('v2ex-latest-v1', 'v2ex-qna-v1', 'v2ex-outsourcing-authors-v1')}) == 3
    with pytest.raises(FrozenInstanceError):
        latest.endpoint = 'https://evil.example'
    for invalid in ('https://www.v2ex.com/api/topics/latest.json', 'qna', None, [], True):
        with pytest.raises(ExecutionRuntimeError, match='invalid_request'):
            research_source(invalid)
