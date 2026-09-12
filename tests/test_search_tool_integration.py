import asyncio
from datetime import UTC, datetime
import hashlib
import subprocess
import sys
from time import monotonic

import httpx
import pytest

pytest.importorskip('mcp')
from mcp.shared.memory import create_connected_server_and_client_session
from pilot.responses_bridge import ResponsesBridge
from pilot.research_tools import build_server


def observation(query):
    return dict(status='SEARCHED',query=query,observed_at=datetime.now(UTC).isoformat(),
                read_scope='SEARCH_RESULTS',results=[dict(url='https://example.com/',
                title='示例',snippet='仅索引摘要',date_hint=None,rank=1)],omitted_count=0,replayed=False)


class SearchService:
    def __init__(self): self.calls=[]; self.closed=False
    def search(self,query):
        self.calls.append(query)
        return observation(query)
    def close(self): self.closed=True


def bridge(service=None,**kwargs):
    def no_model(_): pytest.fail('search route must not call model')
    return ResponsesBridge(api_key='synthetic-model-secret',model='fixture',max_requests=1,
        deadline=kwargs.pop('deadline',monotonic()+10),allowed_tools=(),
        transport=httpx.MockTransport(no_model),search_service=service,**kwargs)


def test_search_gateway_client_roundtrip_separate_model_quota_and_close():
    from pilot.search_tool_client import SearchToolClient
    service=SearchService()
    with bridge(service) as gateway:
        result=SearchToolClient(url=gateway.search_url,token=gateway.token).search('中文 需求')
        assert result['status']=='SEARCHED' and result['read_scope']=='SEARCH_RESULTS'
        assert result['results'][0]['snippet']=='仅索引摘要'
        assert gateway.records==[] and service.calls==['中文 需求']
    assert service.closed


def test_search_gateway_client_roundtrips_maximum_multilingual_result():
    from pilot.search_tool_client import SearchToolClient
    service=SearchService()
    title='求' * 1000
    snippet='🌏' * 2000
    date_hint='今' * 200
    service.search=lambda query:observation(query)|{'results':[
        dict(url=f'https://example.com/{index}',title=title,snippet=snippet,
             date_hint=date_hint,rank=index+1) for index in range(10)
    ]}
    with bridge(service) as gateway:
        result=SearchToolClient(url=gateway.search_url,token=gateway.token).search('中文 maximal')
        assert result['status']=='SEARCHED'
        assert len(result['results'])==10
        assert result['results'][-1]['title']==title
        assert result['results'][-1]['snippet']==snippet
        assert result['results'][-1]['date_hint']==date_hint


@pytest.mark.parametrize('case',['disabled','auth','fields','expired'])
def test_search_gateway_admission(case):
    service=SearchService()
    with bridge(None if case=='disabled' else service,
                deadline=monotonic()+(-1 if case=='expired' else 10)) as gateway:
        response=httpx.post(gateway.base_url+'/public-search',
            headers={'Authorization':'Bearer '+('wrong' if case=='auth' else gateway.token)},
            json={'query':'中文需求',**({'url':'https://forbidden.example/'} if case=='fields' else {})})
        assert response.status_code=={'disabled':404,'auth':401,'fields':400,'expired':408}[case]
    assert service.calls==[]


@pytest.mark.parametrize('url',[
    'https://example.com/v1/public-search','http://localhost:123/v1/public-search',
    'http://127.0.0.1:123/v1/public-search?x=1','http://user@127.0.0.1:123/v1/public-search',
    'http://127.0.0.1:123/other','http://127.0.0.1:0/v1/public-search',
])
def test_search_client_rejects_non_host_local_endpoint(url):
    from pilot.search_tool_client import SearchToolClient
    with pytest.raises(ValueError,match='invalid_search_configuration'):
        SearchToolClient(url=url,token='synthetic-token')


def test_search_client_bad_gateway_result_is_not_search_evidence():
    from pilot.search_tool_client import SearchToolClient
    service=SearchService()
    service.search=lambda query:observation(query)|{'secret':'PRIVATE_DIAGNOSTIC'}
    with bridge(service) as gateway:
        result=SearchToolClient(url=gateway.search_url,token=gateway.token).search('中文需求')
        assert result['status']=='FAILED' and 'PRIVATE_DIAGNOSTIC' not in str(result)


def test_official_mcp_search_then_read_discovered_only():
    from pilot.search_tool_client import SearchToolClient
    service=SearchService(); reads=[]
    def reader(url,**kwargs):
        reads.append(url); text='原始正文，不是索引摘要'
        return dict(url=url,title='原文',text=text,observed_at=datetime.now(UTC).isoformat(),
                    content_sha256=hashlib.sha256(text.encode()).hexdigest(),read_scope='PUBLIC_PAGE_TEXT')
    with bridge(service) as gateway:
        client=SearchToolClient(url=gateway.search_url,token=gateway.token)
        async def scenario():
            server=build_server(max_reads=2,max_seconds=10,reader=reader,searcher=client.search)
            async with create_connected_server_and_client_session(server) as session:
                assert {t.name for t in (await session.list_tools()).tools}=={'read_public_page','search_public_web'}
                blocked=await session.call_tool('read_public_page',{'url':'https://example.com/'})
                assert blocked.isError and reads==[]
                found=await session.call_tool('search_public_web',{'query':'中文需求'})
                assert found.structuredContent['status']=='SEARCHED' and not found.isError
                result=await session.call_tool('read_public_page',{'url':'https://example.com/'})
                assert result.structuredContent['evidence']['text']=='原始正文，不是索引摘要'
                foreign=await session.call_tool('read_public_page',{'url':'https://other.example/'})
                assert foreign.isError and reads==['https://example.com/']
        asyncio.run(scenario())


@pytest.mark.parametrize('bad',[{'query':'x','max_searches':99},{'query':8}])
def test_mcp_search_invalid_input_does_not_dispatch(bad):
    def forbidden(_): pytest.fail('must not search')
    async def scenario():
        async with create_connected_server_and_client_session(
                build_server(max_reads=1,max_seconds=10,searcher=forbidden)) as session:
            result=await session.call_tool('search_public_web',bad)
            assert result.isError and result.structuredContent['code']=='invalid_query'
    asyncio.run(scenario())


@pytest.mark.parametrize('mode',['empty','failure','malformed'])
def test_mcp_empty_search_and_failure_remain_distinct(mode):
    def searcher(query):
        if mode=='failure': return dict(status='FAILED',code='rate_limited',replayed=False)
        if mode=='malformed': return observation(query)|{'review_status':'APPROVED'}
        return observation(query)|{'results':[]}
    async def scenario():
        async with create_connected_server_and_client_session(
                build_server(max_reads=1,max_seconds=10,searcher=searcher)) as session:
            result=await session.call_tool('search_public_web',{'query':'中文需求'})
            assert result.isError==(mode!='empty')
            if mode=='empty': assert result.structuredContent['results']==[]
            else: assert result.structuredContent['code']==('rate_limited' if mode=='failure' else 'invalid_search_result')
    asyncio.run(scenario())


def test_real_stdio_search_uses_only_temporary_host_configuration():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    service=SearchService()
    with bridge(service) as gateway:
        async def scenario():
            params=StdioServerParameters(command='/usr/bin/env',args=['-i',
                'YIKE_PUBLIC_SEARCH_URL='+gateway.search_url,'YIKE_PUBLIC_SEARCH_TOKEN='+gateway.token,
                sys.executable,'-I','-m','pilot.research_tools','--max-reads','1','--max-seconds','10'])
            async with stdio_client(params) as (r,w):
                async with ClientSession(r,w) as session:
                    await session.initialize()
                    result=await session.call_tool('search_public_web',{'query':'中文需求'})
                    assert result.structuredContent['status']=='SEARCHED'
        asyncio.run(scenario())
    assert service.calls==['中文需求']


def test_bad_stdio_search_configuration_does_not_fall_back_or_echo():
    result=subprocess.run([sys.executable,'-I','-m','pilot.research_tools','--max-reads','1','--max-seconds','10'],
        env={'YIKE_PUBLIC_SEARCH_URL':'https://remote.example/','YIKE_PUBLIC_SEARCH_TOKEN':'PRIVATE_MARKER'},
        capture_output=True,text=True,timeout=5)
    assert result.returncode!=0 and 'PRIVATE_MARKER' not in result.stderr+result.stdout
