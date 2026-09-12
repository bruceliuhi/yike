"""Local protocol fixtures, not provider/buyer or customer-production evidence."""
from datetime import UTC, datetime
import hashlib
import json
import os
import sys

import httpx
import pytest

pytest.importorskip('mcp')
pytestmark = pytest.mark.skipif(os.name != 'posix', reason='POSIX host worker')

URL='https://buyer-fixture.example/project'
QUERY='示例 采购 需求'

# A fixture Codex executable uses the actual generated MCP env/config, speaks
# real stdio and HTTP, and emits real tool responses as the worker JSONL expects.
_CODEX_FIXTURE = r'''
import asyncio,json,os,sys
import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

config={}
for index,arg in enumerate(sys.argv[:-1]):
    if arg=='-c':
        key,value=sys.argv[index+1].split('=',1); config[key]=json.loads(value)

def emit(tool,args,value,index):
    print(json.dumps({'type':'item.completed','item':{'id':str(index),
        'type':'mcp_tool_call','server':'yike_public','tool':tool,
        'arguments':args,'status':'completed','error':None,
        'result':{'content':[],'structured_content':value}}}),flush=True)

async def main():
    base=config['model_providers.yike_domestic.base_url']
    token=os.environ['YIKE_BRIDGE_TOKEN']
    response=httpx.post(base+'/responses',headers={'Authorization':'Bearer '+token},
        json={'model':'ignored','stream':True,'input':[{'role':'user','content':'fixture request'}],'tools':[]},
        timeout=5,trust_env=False)
    assert response.status_code==200
    params=StdioServerParameters(command=config['mcp_servers.yike_public.command'],
        args=config['mcp_servers.yike_public.args'],env={})
    async with stdio_client(params) as (reader,writer):
        async with ClientSession(reader,writer) as session:
            await session.initialize()
            for index,(tool,args) in enumerate([
                ('read_public_page',{'url':'https://buyer-fixture.example/project'}),
                ('search_public_web',{'query':'示例 采购 需求'}),
                ('search_public_web',{'query':'示例 采购 需求'}),
                ('read_public_page',{'url':'https://buyer-fixture.example/project'}),
                ('read_public_page',{'url':'https://buyer-fixture.example/project'}),
            ]):
                result=await session.call_tool(tool,args)
                if index==0:
                    assert result.structuredContent['code']=='invalid_url'
                else:
                    emit(tool,args,result.structuredContent,index)
    print(json.dumps({'type':'turn.completed','usage':{'input_tokens':0,'output_tokens':0}}),flush=True)

asyncio.run(main())
'''


@pytest.mark.parametrize('deny_read',[False,True,'known','access_restricted','rate_limited'])
def test_actual_worker_bridge_and_mcp_stdio_share_host_gate(tmp_path,monkeypatch,deny_read):
    from pilot import codex_research_worker as worker
    from pilot.open_web_reader import PublicPageReader, PublicReadError
    from pilot.durable_research_dispatch import DurableResearchDispatcher
    from tests.test_durable_research_dispatch import Journal, TASK, RUN, OWNER, BINDING
    from pilot.public_search import PublicSearchSession
    from pilot.responses_bridge import ResponsesBridge
    from pilot.research_effect_contract import effect_input, effect_result
    from tests.test_research_effect_contract import binding
    effects=[]; io=[]
    def provider(request):
        io.append('MODEL')
        return httpx.Response(200,headers={'content-type':'text/event-stream'},content=(
            'event: response.completed\ndata: '+json.dumps({'type':'response.completed',
                'response':{'status':'completed','output':[]}})+'\n\n').encode())
    def bridge(**kwargs):
        return ResponsesBridge(**kwargs,transport=httpx.MockTransport(provider))
    def search(self,query,*,deadline=None):
        io.append('SEARCH')
        urls = [URL, URL+'/other'] if isinstance(deny_read,str) else [URL]
        return dict(status='SEARCHED',query=query,observed_at=datetime.now(UTC).isoformat(),
            read_scope='SEARCH_RESULTS',results=[dict(url=url,title='测试索引',snippet=None,
            date_hint=None,rank=i) for i,url in enumerate(urls,1)],omitted_count=0,replayed=False)
    def read(self,url,*,deadline):
        io.append('READ'); text='仅用于协议测试的文本，不是真实商机。'
        if deny_read == 'known' and url == URL:
            raise PublicReadError('not_found')
        if deny_read in ('access_restricted','rate_limited') and url == URL:
            raise PublicReadError(deny_read)
        return dict(url=url,title='测试原文',text=text,observed_at=datetime.now(UTC).isoformat(),
            content_sha256=hashlib.sha256(text.encode()).hexdigest(),read_scope='PUBLIC_PAGE_TEXT')
    journal = Journal()
    durable = DurableResearchDispatcher(journal, object(), task_id=TASK, run_id=RUN,
        generation=3, coordinator_owner=OWNER, context_binding=BINDING)
    def dispatch(kind,payload,deadline,perform):
        effects.append(kind)
        if kind=='READ' and deny_read is True: raise RuntimeError('private-denial')
        return durable(kind,payload,deadline,perform)
    monkeypatch.setattr(worker,'ResponsesBridge',bridge)
    monkeypatch.setattr(PublicSearchSession,'_run',search)
    monkeypatch.setattr(PublicPageReader,'read',read)
    executable=tmp_path/'codex-fixture'
    script = _CODEX_FIXTURE
    if isinstance(deny_read,str):
        script = script.replace("            ]):", "                ('read_public_page',{'url':'https://buyer-fixture.example/project/other'}),\n            ]):")
    executable.write_text('#!'+sys.executable+'\n'+script)
    executable.chmod(0o700)
    result=worker.run_public_research_mission('本地协议验证，不是真实买方研究',
        codex_binary=str(executable),python_binary=sys.executable,
        api_key='synthetic-provider-key',search_api_key='synthetic-search-key',
        model='test-model',max_seconds=15,effect_dispatcher=dispatch)
    assert effects==(['MODEL','SEARCH','READ','READ'] if isinstance(deny_read,str) else ['MODEL','SEARCH','READ'])
    expected_io = ['MODEL','SEARCH'] if deny_read is True else ['MODEL','SEARCH','READ'] if deny_read in ('access_restricted','rate_limited') else effects
    assert io==expected_io
    assert len(result)==9
    assert len(result['searches'])==1 and result['searches'][0]['query']==QUERY
    assert 'private-denial' not in json.dumps(result)
    if deny_read is True or deny_read in ('access_restricted','rate_limited'):
        assert result['status']=='FAILED' and result['code']=='no_verified_reads'
        assert result['reads']==[]
        if isinstance(deny_read,str):
            assert result['read_failures'][0]['code']==deny_read
            assert [e[1]['status'] for e in journal.events if e[0]=='finish']==['SUCCEEDED','SUCCEEDED','UNKNOWN']
    else:
        assert result['status']=='COMPLETED' and len(result['reads'])==1
        assert result['reads'][0]['review_status']=='UNREVIEWED'
        if deny_read == 'known':
            assert result['reads'][0]['evidence']['url'] == URL+'/other'
            assert result['read_failures'] == [{'url': URL, 'code': 'not_found'}]*2
            assert [e[1]['status'] for e in journal.events if e[0]=='finish'] == ['SUCCEEDED','SUCCEEDED','FAILED','SUCCEEDED']


def test_host_read_denies_url_before_successful_search(monkeypatch):
    from pilot.public_search import PublicSearchSession
    from pilot.public_read_session import PublicReadSession
    from time import monotonic
    effects=[]
    def dispatch(*args): effects.append(args[0]); raise RuntimeError('denied')
    search=PublicSearchSession(api_key='synthetic',max_searches=1,deadline=monotonic()+5,
                               effect_dispatcher=dispatch)
    read=PublicReadSession(max_reads=1,deadline=monotonic()+5,allowed_url=search.allows_read,
                          effect_dispatcher=dispatch)
    try:
        assert read.read(URL,deadline=monotonic()+2)['code']=='invalid_url'
        assert effects==[]
        assert search.search(QUERY)['status']=='FAILED'
        assert read.read(URL,deadline=monotonic()+2)['code']=='invalid_url'
        assert effects==['SEARCH']
    finally:
        search.close(); read.close()
