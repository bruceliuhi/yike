import asyncio
from datetime import UTC, datetime, timedelta
import hashlib
import json
import threading
import time
import sys
import subprocess

import pytest
pytest.importorskip('mcp', reason='requires the optional research dependency group')
from mcp.shared.memory import create_connected_server_and_client_session


def page(url, **_):
    text = '正在寻找检测设备供应商，欢迎提供方案。'
    return dict(url=url, title='采购需求', text=text,
                observed_at=datetime.now(UTC).isoformat(),
                content_sha256=hashlib.sha256(text.encode()).hexdigest(),
                read_scope='PUBLIC_PAGE_TEXT')


def run(coro):
    return asyncio.run(coro)


def build(**kwargs):
    from pilot.research_tools import build_server
    return build_server(max_reads=kwargs.pop('max_reads', 3),
                        max_seconds=kwargs.pop('max_seconds', 60), **kwargs)


def test_protocol_read_unknown_domains_and_replay():
    calls = []
    def reader(url, *, deadline):
        assert datetime.now(UTC) < deadline <= datetime.now(UTC) + timedelta(seconds=20)
        calls.append(url)
        return page(url)
    async def scenario():
        async with create_connected_server_and_client_session(build(reader=reader)) as session:
            tools = (await session.list_tools()).tools
            assert [t.name for t in tools] == ['read_public_page']
            assert set(tools[0].inputSchema['properties']) == {'url'}
            first = await session.call_tool('read_public_page', {'url':'https://new-industry.example/need'})
            value = first.structuredContent
            assert value['status'] == 'READ' and value['review_status'] == 'UNREVIEWED'
            assert value['evidence'] == page(calls[0]) | {'observed_at': value['evidence']['observed_at']}
            assert 'published_at' not in value['evidence']
            again = await session.call_tool('read_public_page', {'url':'https://new-industry.example:443/need#reply1'})
            assert again.structuredContent == value | {'replayed':True}
            other = await session.call_tool('read_public_page', {'url':'https://another-industry.example/project'})
            assert other.structuredContent['status'] == 'READ'
            assert calls == ['https://new-industry.example/need', 'https://another-industry.example/project']
    run(scenario())


@pytest.mark.parametrize('arguments', [
    {}, {'url':8}, {'url':'https://public.example/', 'max_reads':100},
    {'url':'https://localhost/'}, {'url':'https://public.example/?api_key=PRIVATE'},
])
def test_bad_arguments_do_not_read_or_echo(arguments):
    def reader(*args, **kwargs):
        pytest.fail('invalid arguments must not reach reader')
    async def scenario():
        async with create_connected_server_and_client_session(build(reader=reader)) as session:
            result = await session.call_tool('read_public_page', arguments)
            assert result.isError
            assert result.structuredContent['status'] == 'FAILED'
            assert 'PRIVATE' not in result.model_dump_json()
    run(scenario())


def test_failed_read_is_replayed_and_counted_without_exception_leak():
    calls=[]
    def reader(url, **_):
        calls.append(url)
        raise RuntimeError('PRIVATE_provider_diagnostic')
    async def scenario():
        async with create_connected_server_and_client_session(build(max_reads=1, reader=reader)) as session:
            failed = await session.call_tool('read_public_page', {'url':'https://first.example/'})
            replay = await session.call_tool('read_public_page', {'url':'https://first.example/'})
            limited = await session.call_tool('read_public_page', {'url':'https://next.example/'})
            assert failed.structuredContent == {'status':'FAILED','code':'unavailable','replayed':False}
            assert replay.structuredContent == failed.structuredContent | {'replayed':True}
            assert limited.structuredContent['code'] == 'read_limit_reached'
            assert len(calls) == 1
    run(scenario())


def test_expired_session_and_late_result_cannot_start_or_claim_read(monkeypatch):
    import pilot.research_tools as module
    tick=[10.0]
    monkeypatch.setattr(module, 'monotonic', lambda:tick[0])
    calls=[]
    def reader(url, **_):
        calls.append(url)
        tick[0]=12.0
        return page(url)
    async def scenario():
        async with create_connected_server_and_client_session(build(max_seconds=1,reader=reader)) as session:
            late=await session.call_tool('read_public_page', {'url':'https://first.example/'})
            assert late.structuredContent['code'] == 'deadline_exceeded'
            expired=await session.call_tool('read_public_page', {'url':'https://second.example/'})
            assert expired.structuredContent['code'] == 'deadline_exceeded'
            assert len(calls)==1
    run(scenario())


def test_parallel_calls_are_serial_and_same_url_not_reread():
    state={'active':0,'peak':0,'calls':0}
    lock=threading.Lock()
    def reader(url, **_):
        with lock:
            state['active']+=1; state['calls']+=1
            state['peak']=max(state['peak'],state['active'])
        time.sleep(.01)
        with lock: state['active']-=1
        return page(url)
    async def scenario():
        async with create_connected_server_and_client_session(build(reader=reader)) as session:
            results=await asyncio.gather(*(session.call_tool('read_public_page', {'url':url}) for url in
                ['https://first.example/','https://first.example/','https://second.example/']))
            assert all(x.structuredContent['status']=='READ' for x in results)
            assert state['peak']==1 and state['calls']==2
    run(scenario())


@pytest.mark.parametrize('bad', [{'text':''}, {'content_sha256':'0'*64}, {'url':'https://different.example/'},
                                  {'review_status':'APPROVED'}, {'observed_at':'yesterday'}])
def test_reader_output_checked_before_tool_evidence(bad):
    def reader(url, **_): return page(url) | bad
    async def scenario():
        async with create_connected_server_and_client_session(build(reader=reader)) as session:
            result=await session.call_tool('read_public_page', {'url':'https://first.example/'})
            assert result.isError and result.structuredContent['code']=='invalid_read_result'
    run(scenario())


def test_unknown_tool_returns_fixed_error():
    async def scenario():
        async with create_connected_server_and_client_session(build(reader=page)) as session:
            result=await session.call_tool('send_message', {'body':'PRIVATE'})
            assert result.isError and result.structuredContent['code']=='unknown_tool'
            assert 'PRIVATE' not in result.model_dump_json()
    run(scenario())


@pytest.mark.parametrize('limits', [{'max_reads':True},{'max_reads':101},{'max_reads':0},
                                  {'max_seconds':0},{'max_seconds':1801}])
def test_invalid_host_limits(limits):
    with pytest.raises(ValueError,match='invalid_tool_limits'):
        build(**limits)


def test_real_stdio_process_advertises_tool_and_rejects_private_url():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    async def scenario():
        params = StdioServerParameters(command=sys.executable,
            args=['-I','-m','pilot.research_tools','--max-reads','1','--max-seconds','10'])
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream,
                                     read_timeout_seconds=timedelta(seconds=10)) as session:
                await session.initialize()
                assert [x.name for x in (await session.list_tools()).tools] == ['read_public_page']
                result=await session.call_tool('read_public_page', {'url':'https://127.0.0.1/'})
                assert result.structuredContent['code']=='invalid_url'
    run(scenario())


def test_real_stdio_malformed_arguments_do_not_echo_to_stderr():
    marker = 'REVIEW_SYNTHETIC_SECRET'
    messages = [
        {'jsonrpc':'2.0','id':1,'method':'initialize','params':{
            'protocolVersion':'2025-06-18','capabilities':{},
            'clientInfo':{'name':'test','version':'1'}}},
        {'jsonrpc':'2.0','method':'notifications/initialized'},
        {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{
            'name':'read_public_page','arguments':marker}},
    ]
    process = subprocess.run(
        [sys.executable, '-I', '-m', 'pilot.research_tools', '--max-reads', '1', '--max-seconds', '5'],
        input=''.join(json.dumps(item, separators=(',',':')) + '\n' for item in messages),
        text=True, capture_output=True, timeout=10, check=False)
    assert process.returncode == 0
    assert marker not in process.stdout and marker not in process.stderr
    assert '"id":2' in process.stdout and '"error"' in process.stdout


def test_real_stdio_idle_session_exits_at_max_seconds():
    process = subprocess.Popen(
        [sys.executable, '-I', '-m', 'pilot.research_tools', '--max-reads', '1', '--max-seconds', '1'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        process.stdin.write(json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{
            'protocolVersion':'2025-06-18','capabilities':{},
            'clientInfo':{'name':'test','version':'1'}}}) + '\n')
        process.stdin.flush()
        process.wait(timeout=3)
        assert process.returncode == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_serve_timeout_cancels_active_reader(monkeypatch):
    import pilot.research_tools as module
    events = []

    class Server:
        def create_initialization_options(self): return None
        async def run(self, *_):
            await asyncio.Event().wait()

    class Context:
        async def __aenter__(self): return object(), object()
        async def __aexit__(self, *_): return None

    monkeypatch.setattr(module, 'stdio_server', lambda: Context())
    monkeypatch.setattr(module, 'cancel_active_reads', lambda: events.append('cancel'))
    run(module._serve(Server(), max_seconds=0.01))
    assert events == ['cancel']
