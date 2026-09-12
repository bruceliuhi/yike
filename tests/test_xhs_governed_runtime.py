"""Execute pinned, patched XHS methods with offline browser/transport boundaries.

Set YIKE_XHS_UPSTREAM_SOURCE to a local pinned upstream git repository on other
machines. No platform network, installed source mutations, or login is performed.
"""
import ast
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def source(tmp_path_factory):
    upstream = os.environ.get('YIKE_XHS_UPSTREAM_SOURCE',
        'C:/Users/bruce/AI/意客AI2026/.runtime/windows-installed-20260910-01')
    if not Path(upstream).exists():
        pytest.skip('Requires local pinned upstream checkout; never downloads')
    target = tmp_path_factory.mktemp('xhs') / 'source'
    subprocess.run(['git', 'clone', '-q', '--no-hardlinks', '--no-checkout', upstream, str(target)], check=True)
    def git(*args):
        return subprocess.check_output(['git', '-c', 'core.autocrlf=false', *args], cwd=target, stderr=subprocess.PIPE)
    lock = json.loads((ROOT / 'vendor/mediacrawler.lock').read_text())
    git('checkout', '-q', lock['commit'])
    patches = [ROOT / p['path'] for p in lock['patches']]
    extra = ROOT / 'vendor/patches/mediacrawler/0002-yike-xhs-runtime.patch'
    if extra.exists() and extra not in patches:
        patches.append(extra)
    for patch in patches:
        git('apply', '--index', '--unidiff-zero', str(patch))
    return target


@pytest.fixture
def runtime(source):
    g = {'__name__': 'offline_xhs', 'asyncio': asyncio, 'os': os, 'Path': Path, 'json': json}
    exec(compile((source / 'tools/yike_runtime.py').read_text(encoding='utf-8'), 'tools/yike_runtime.py', 'exec'), g)
    g.update(config=NS(XHS_INTERNATIONAL=False, CRAWLER_MAX_NOTES_COUNT=2, START_PAGE=1,
        KEYWORDS='原文', SORT_TYPE='', MAX_CONCURRENCY_NUM=1, CRAWLER_MAX_SLEEP_SEC=0,
        ENABLE_GET_SUB_COMMENTS=True, SAVE_LOGIN_STATE=True, PLATFORM='xhs',
        USER_DATA_DIR='%s_user_data_dir', SAVE_DATA_PATH='', CRAWLER_TYPE='search',
        ENABLE_IP_PROXY=True, ENABLE_CDP_MODE=True, HEADLESS=False, CDP_HEADLESS=False,
        LOGIN_TYPE='qrcode', COOKIES='', ENABLE_GET_COMMENTS=True),
        utils=NS(logger=NS(info=lambda *a: None, error=lambda *a: None, warning=lambda *a: None),
                 get_current_timestamp=lambda: 1789000000000),
        source_keyword_var=NS(set=lambda v: None, get=lambda: '原文'),
        crawler_type_var=NS(set=lambda v: None), get_search_id=lambda: 'offline',
        SearchSortType=NS(GENERAL='general'),
        anonymize_user_id=lambda v: None if v is None else 'anonymous-hash',
        mask_nickname=lambda v: None if v is None else 'masked')
    def load(path, cls=None, names=None):
        tree = ast.parse((source / path).read_text(encoding='utf-8'))
        nodes = next(n.body for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls) if cls else tree.body
        nodes = [n for n in nodes if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and (names is None or n.name in names)]
        # Imports are dependency boundaries only; production method bodies and decorators remain intact.
        out = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), *nodes], type_ignores=[])
        ns = dict(g)
        if any(n.decorator_list for n in nodes if any(isinstance(d, ast.Call) for d in n.decorator_list)):
            import tenacity
            for name in ('retry', 'stop_after_attempt', 'wait_fixed', 'retry_if_not_exception_type', 'retry_if_result', 'RetryError'):
                ns[name] = getattr(tenacity, name)
        exec(compile(ast.fix_missing_locations(out), path, 'exec'), ns)
        if cls:
            return type(cls, (), {n.name: ns[n.name] for n in nodes}), ns
        g.update({n.name: ns[n.name] for n in nodes})
        return ns
    for name in ('NoteNotFoundError', 'IPBlockError', 'PlatformAccessError', 'DataFetchError'):
        g[name] = type(name, (Exception,), {})
    return NS(g=g, load=load)


def run(value):
    return asyncio.run(value)


def test_profile_and_default_browser_contract(runtime, tmp_path, monkeypatch):
    C, _ = runtime.load('media_platform/xhs/core.py', 'XiaoHongShuCrawler', ['launch_browser'])
    chromium = NS(launch_persistent_context=AsyncMock(return_value='context'))
    monkeypatch.setenv('YIKE_PROFILE_PATH', str(tmp_path))
    assert run(C().launch_browser(chromium, {'server': 'forbidden'}, 'fake-ua', True)) == 'context'
    kwargs = chromium.launch_persistent_context.call_args.kwargs
    assert kwargs['user_data_dir'] == str(tmp_path)
    assert kwargs['headless'] is False
    assert not {'user_agent', 'channel', 'proxy', 'args'} & kwargs.keys()
    monkeypatch.setenv('YIKE_PROFILE_PATH', 'relative')
    with pytest.raises(Exception):
        run(C().launch_browser(chromium, None, None))
    assert chromium.launch_persistent_context.call_count == 1


@pytest.mark.parametrize('last_page,limit', [(False, 2), (True, 2), (True, 1), (True, 0)])
def test_search_last_page_and_strict_budget(runtime, last_page, limit):
    stored = AsyncMock()
    runtime.g['xhs_store'] = NS(update_xhs_note=stored)
    runtime.g['config'].CRAWLER_MAX_NOTES_COUNT = limit
    C, _ = runtime.load('media_platform/xhs/core.py', 'XiaoHongShuCrawler', ['search'])
    c = C()
    c.xhs_client = NS(get_note_by_keyword=AsyncMock(return_value={'has_more': not last_page,
        'items': [{'id': str(i), 'model_type': 'note', 'xsec_token': 'SECRET'} for i in range(3)]}))
    c.get_note_detail_async_task = AsyncMock(side_effect=lambda **k: {'note_id': k['note_id']})
    c.batch_get_note_comments = AsyncMock()
    c.get_notice_media = AsyncMock()
    run(c.search())
    assert stored.call_count == limit
    assert c.get_note_detail_async_task.call_count == limit
    assert runtime.g['config'].CRAWLER_MAX_NOTES_COUNT == limit
    assert c.xhs_client.get_note_by_keyword.call_count == int(limit > 0)


@pytest.mark.parametrize('response', [{}, {'items': {}, 'has_more': False},
    {'items': [None], 'has_more': False}, {'items': [], 'has_more': 'false'}])
def test_search_rejects_malformed_page(runtime, response):
    C, _ = runtime.load('media_platform/xhs/core.py', 'XiaoHongShuCrawler', ['search'])
    c = C(); c.xhs_client = NS(get_note_by_keyword=AsyncMock(return_value=response))
    with pytest.raises(runtime.g['YikePlatformResponseChanged']):
        run(c.search())


def test_search_failure_is_not_empty_success(runtime):
    C, _ = runtime.load('media_platform/xhs/core.py', 'XiaoHongShuCrawler', ['search'])
    c = C(); c.xhs_client = NS(get_note_by_keyword=AsyncMock(side_effect=runtime.g['DataFetchError']()))
    with pytest.raises(runtime.g['DataFetchError']):
        run(c.search())


@pytest.mark.parametrize('status,error', [(401,'YikePlatformAuthRequired'), (403,'YikePlatformPermissionDenied'),
    (429,'YikePlatformRateLimited'), (461,'YikePlatformVerificationRequired'),
    (471,'YikePlatformVerificationRequired'), (500,'YikeNetworkFailed')])
def test_request_safe_terminal_no_retry(runtime, status, error):
    import httpx
    calls = []
    class Transport:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def request(self, *args, **kwargs):
            calls.append(1)
            return httpx.Response(status, json={'success': False, 'msg': 'SECRET'}, headers={'Verifyuuid': 'SECRET'})
    runtime.g.update(httpx=httpx, make_async_client=lambda **k: Transport())
    C, _ = runtime.load('media_platform/xhs/client.py', 'XiaoHongShuClient', ['request'])
    c = C(); c.proxy=None; c.timeout=1; c._refresh_proxy_if_expired=AsyncMock()
    with pytest.raises(runtime.g[error]) as caught:
        run(c.request('GET', 'https://offline.invalid'))
    assert str(caught.value) == ''
    assert len(calls) == 1
    c._refresh_proxy_if_expired.assert_not_called()


def test_shared_parent_inline_and_fetched_reply_budget(runtime):
    C, _ = runtime.load('media_platform/xhs/client.py', 'XiaoHongShuClient',
        ['get_note_all_comments', 'get_comments_all_sub_comments'])
    c = C(); cb = AsyncMock()
    c.get_note_comments = AsyncMock(return_value={'has_more': False, 'cursor': '', 'comments': [
        {'id':'parent','note_id':'note','sub_comments':[{'id':'inline','content':'原文'}],
         'sub_comment_has_more':True,'sub_comment_cursor':'one'}]})
    c.get_note_sub_comments = AsyncMock(return_value={'has_more':False,'cursor':'two',
        'comments':[{'id':'fetched'},{'id':'over-budget'}]})
    result = run(c.get_note_all_comments('note','SECRET',0,cb,3))
    assert [item['id'] for item in result] == ['parent','inline','fetched']
    assert sum(len(call.args[1]) for call in cb.call_args_list) == 3
    assert c.get_note_sub_comments.call_count == 1
    assert result[1]['target_comment']['id'] == 'parent'


def test_reply_failure_propagates(runtime):
    C, _ = runtime.load('media_platform/xhs/client.py', 'XiaoHongShuClient',
        ['get_note_all_comments', 'get_comments_all_sub_comments'])
    c=C(); c.get_note_comments=AsyncMock(return_value={'has_more':False,'cursor':'','comments':[
        {'id':'p','note_id':'n','sub_comments':[],'sub_comment_has_more':True,'sub_comment_cursor':'c'}]})
    c.get_note_sub_comments=AsyncMock(side_effect=runtime.g['DataFetchError']())
    with pytest.raises(runtime.g['DataFetchError']):
        run(c.get_note_all_comments('n','SECRET',0,None,3))


@pytest.mark.parametrize('kind', ['parent', 'reply'])
@pytest.mark.parametrize('cross_page', [False, True])
@pytest.mark.parametrize('change', [None, {'content':'changed 原文'}, {'note_id':'other-note'},
    {'target_comment':{'id':'other-parent'}}, {'create_time':True}, {'user_info':{'user_id':'other'}}])
def test_duplicate_comments_require_identical_evidence(runtime,kind,cross_page,change):
    C,_=runtime.load('media_platform/xhs/client.py','XiaoHongShuClient',
        ['get_note_all_comments','get_comments_all_sub_comments'])
    c=C(); callback=AsyncMock()
    original={'id':'same','content':' 原文\ne\u0301😀 ','note_id':'note',
        'create_time':1,'user_info':{'user_id':'original'}}
    if kind=='reply':
        original['target_comment']={'id':'parent'}
    duplicate={**original,**(change or {})}
    if kind=='parent':
        pages=([{'comments':[original],'has_more':True,'cursor':'second'},
                {'comments':[duplicate],'has_more':False,'cursor':''}] if cross_page else
               [{'comments':[original,duplicate],'has_more':False,'cursor':''}])
        c.get_note_comments=AsyncMock(side_effect=pages)
    else:
        parent={'id':'parent','note_id':'note','sub_comments':[original] if cross_page else [original,duplicate],
            'sub_comment_has_more':cross_page,'sub_comment_cursor':'second' if cross_page else ''}
        c.get_note_comments=AsyncMock(return_value={'comments':[parent],'has_more':False,'cursor':''})
        c.get_note_sub_comments=AsyncMock(return_value={'comments':[duplicate],'has_more':False,'cursor':''})
    if change:
        with pytest.raises(runtime.g['YikePlatformResponseChanged']):
            run(c.get_note_all_comments('note','SECRET',0,callback,10))
    else:
        result=run(c.get_note_all_comments('note','SECRET',0,callback,10))
        expected=['same'] if kind=='parent' else ['parent','same']
        assert [item['id'] for item in result]==expected
        assert sum(len(call.args[1]) for call in callback.call_args_list)==len(expected)


def test_raw_store_unicode_null_timestamp_and_no_tokens(runtime):
    from datetime import datetime, timezone
    sink=NS(store_content=AsyncMock(), store_comment=AsyncMock())
    runtime.g.update(datetime=datetime, timezone=timezone, XhsStoreFactory=NS(create_store=lambda: sink))
    ns=runtime.load('store/xhs/__init__.py', names=['update_xhs_note','update_xhs_note_comment','get_video_url_arr','_xhs_time'])
    text='  原文\ne\u0301😀\t'
    run(ns['update_xhs_note']({'note_id':'a1','title':None,'desc':text,'time':1789000000123,'xsec_token':'SECRET'}))
    run(ns['update_xhs_note_comment']('a1',{'id':'c1','content':text,'create_time':1789000000123}))
    post=sink.store_content.call_args.args[0]; comment=sink.store_comment.call_args.args[0]
    assert post['title'] is None and post['desc'] == text and comment['content'] == text
    assert post['time'] == comment['create_time'] == '2026-09-10T00:26:40Z'
    assert post['note_url'] == 'https://www.xiaohongshu.com/explore/a1'
    assert 'xsec_token' not in post and 'SECRET' not in json.dumps(post)
    assert comment['parent_comment_id'] in (None, 0)
    assert comment['creator_hash'] is None and 'user_id' not in comment
    assert comment['last_modify_ts'] == 1789000000000
    run(ns['update_xhs_note_comment']('a1',{'id':'c2','content':None,'create_time':None}))
    assert sink.store_comment.call_args.args[0]['create_time'] is None


def test_no_data_uses_xhs_directory(runtime, tmp_path):
    runtime.g['config'].SAVE_DATA_PATH=str(tmp_path)
    ns=runtime.load('main.py', names=['_has_candidate_output'])
    assert ns['_has_candidate_output']() is False
    d=tmp_path/'xhs/jsonl'; d.mkdir(parents=True)
    (d/'search_comments_fixture.jsonl').write_text('{"comment_id":"c"}\n')
    assert ns['_has_candidate_output']() is True


def test_applied_patch_hashes_match_lock(source):
    lock=json.loads((ROOT/'vendor/mediacrawler.lock').read_text())
    assert [patch['path'] for patch in lock['patches']] == [
        'vendor/patches/mediacrawler/0001-yike-controlled-runtime.patch',
        'vendor/patches/mediacrawler/0002-yike-xhs-runtime.patch',
        'vendor/patches/mediacrawler/0003-yike-zhihu-runtime.patch',
        'vendor/patches/mediacrawler/0004-yike-bili-links.patch',
    ]
    for path,digest in lock['patched_files'].items():
        assert hashlib.sha256((source/path).read_bytes()).hexdigest() == digest, path


@pytest.mark.parametrize('data,error', [
    ({'success':False,'code':-100}, 'YikePlatformAuthRequired'),
    ({'success':False,'code':300011}, 'YikePlatformVerificationRequired'),
    ({'success':False,'code':300012}, 'YikePlatformRateLimited'),
    ({'success':False,'code':-510000}, 'YikePlatformPermissionDenied'),
    ({'success':False,'code':123,'msg':'SECRET'}, 'YikePlatformResponseChanged'),
    ({'success':True,'data':[]}, 'YikePlatformResponseChanged'),
    ({'success':True}, 'YikePlatformResponseChanged'),
    ([], 'YikePlatformResponseChanged'),
    ('malformed-json', 'YikePlatformResponseChanged'),
    ('network', 'YikeNetworkFailed'),
])
def test_request_api_and_transport_failures_are_safe(runtime, data, error):
    import httpx
    calls=[]
    class Transport:
        async def __aenter__(self): return self
        async def __aexit__(self,*a): pass
        async def request(self,*a,**k):
            calls.append(1)
            if data == 'network':
                raise httpx.ConnectError('SECRET token in URL')
            if data == 'malformed-json':
                return httpx.Response(200, content=b'not json SECRET')
            return httpx.Response(200, json=data)
    def factory(**kwargs):
        assert kwargs == {'trust_env':False,'verify':True}
        return Transport()
    runtime.g.update(httpx=httpx,make_async_client=factory)
    C,_=runtime.load('media_platform/xhs/client.py','XiaoHongShuClient',['request'])
    c=C(); c.timeout=1
    with pytest.raises(runtime.g[error]) as caught:
        run(c.request('GET','https://offline.invalid'))
    assert str(caught.value) == '' and len(calls) == 1


@pytest.mark.parametrize('second_check', [True,False])
def test_start_waits_for_normal_login_then_revalidates(runtime, second_check):
    progress=[]
    client=NS(pong=AsyncMock(side_effect=[False,second_check]), update_cookies=AsyncMock())
    login=NS(begin=AsyncMock())
    browser=NS(new_page=AsyncMock(return_value=NS(goto=AsyncMock())))
    class Playwright:
        async def __aenter__(self): return NS(chromium='bundled')
        async def __aexit__(self,*a): pass
    runtime.g.update(async_playwright=Playwright, XiaoHongShuLogin=lambda **k: login,
        write_progress=lambda out,platform,state: progress.append((platform,state)))
    C,_=runtime.load('media_platform/xhs/core.py','XiaoHongShuCrawler',['__init__','start'])
    c=C(); c.launch_browser=AsyncMock(return_value=browser)
    c.create_xhs_client=AsyncMock(return_value=client); c.search=AsyncMock()
    if second_check:
        run(c.start())
        assert progress == [('xhs','WAITING_LOGIN'),('xhs','RUNNING')]
        c.search.assert_awaited_once()
    else:
        with pytest.raises(runtime.g['YikePlatformAuthRequired']): run(c.start())
        assert progress == [('xhs','WAITING_LOGIN')]
        c.search.assert_not_called()
    c.launch_browser.assert_awaited_once_with('bundled',None,None,False)
    assert client.pong.call_count == 2 and login.begin.call_count == 1


def test_login_challenge_stops_before_ui_success_without_retry(runtime):
    C,_=runtime.load('media_platform/xhs/login.py','XiaoHongShuLogin',['__init__','check_login_state','begin'])
    page=NS(content=AsyncMock(return_value='请通过验证 SECRET'),is_visible=AsyncMock(return_value=True))
    login=C('qrcode',None,page)
    with pytest.raises(runtime.g['YikePlatformVerificationRequired']): run(login.begin())
    page.content.assert_awaited_once(); page.is_visible.assert_not_called()


@pytest.mark.parametrize('value,error', [
    ({'result':{'success':True}},None), ({'result':{'success':False}},None),
    ({},'YikePlatformResponseChanged'), ({'result':{'success':1}},'YikePlatformResponseChanged'),
    ('YikePlatformAuthRequired',None), ('YikeNetworkFailed','YikeNetworkFailed'),
    ('YikePlatformVerificationRequired','YikePlatformVerificationRequired'),
])
def test_pong_only_treats_explicit_auth_as_login_needed(runtime,value,error):
    C,_=runtime.load('media_platform/xhs/client.py','XiaoHongShuClient',['pong'])
    c=C(); c.query_self=AsyncMock(**({'side_effect':runtime.g[value]()} if isinstance(value,str) else {'return_value':value}))
    if error:
        with pytest.raises(runtime.g[error]): run(c.pong())
    else:
        assert run(c.pong()) is (value == {'result':{'success':True}})


@pytest.mark.parametrize('response', [{}, {'items':[]}, {'items':[{'note_card':{'note_id':'wrong'}}]}])
def test_detail_missing_or_mismatched_is_not_skipped(runtime,response):
    C,_=runtime.load('media_platform/xhs/client.py','XiaoHongShuClient',['get_note_by_id'])
    c=C(); c.post=AsyncMock(return_value=response)
    with pytest.raises(runtime.g['YikePlatformResponseChanged']):
        run(c.get_note_by_id('note','pc_search','SECRET'))


def test_detail_failure_not_swallowed(runtime):
    C,_=runtime.load('media_platform/xhs/core.py','XiaoHongShuCrawler',['get_note_detail_async_task'])
    c=C(); c.xhs_client=NS(get_note_by_id=AsyncMock(side_effect=runtime.g['YikePlatformPermissionDenied']()))
    with pytest.raises(runtime.g['YikePlatformPermissionDenied']):
        run(c.get_note_detail_async_task('note','pc_search','SECRET',asyncio.Semaphore(1)))


def test_successful_empty_search_is_valid_no_data(runtime):
    C,_=runtime.load('media_platform/xhs/core.py','XiaoHongShuCrawler',['search'])
    c=C(); c.xhs_client=NS(get_note_by_keyword=AsyncMock(return_value={'items':[],'has_more':False}))
    c.batch_get_note_comments=AsyncMock()
    run(c.search())
    c.batch_get_note_comments.assert_awaited_once_with([],[])


@pytest.mark.parametrize('scenario,terminal', [('success','SUCCEEDED'),
    ('empty','SUCCEEDED_NO_DATA'), ('denied','BLOCKED_INPUT')])
def test_imported_runtime_main_to_raw_jsonl_offline(source,tmp_path,scenario,terminal):
    """Real imports and real main/client/core/store; only browser/HTTP are fixtures."""
    python=Path(os.environ.get('YIKE_XHS_RUNTIME_PYTHON',
        'C:/Users/bruce/AI/意客AI2026/.runtime/windows-installed-20260910-01/.venv/Scripts/python.exe'))
    if not python.exists():
        pytest.skip('Requires governed runtime dependencies; never installs/downloads')
    script=r'''
import asyncio,json,sys
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import httpx
import config,main
from media_platform.xhs import core,client
from store import xhs
out=Path(sys.argv[1]); scenario=sys.argv[2]
config.PLATFORM='xhs'; config.XHS_INTERNATIONAL=False; config.CRAWLER_TYPE='search'
config.SAVE_DATA_OPTION='jsonl'; config.SAVE_DATA_PATH=str(out)
config.KEYWORDS='原文'; config.SORT_TYPE=''; config.START_PAGE=1
config.CRAWLER_MAX_NOTES_COUNT=1; config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES=2
config.ENABLE_GET_COMMENTS=True; config.ENABLE_GET_SUB_COMMENTS=True
config.CRAWLER_MAX_SLEEP_SEC=0
calls=[]; raw=[]
page=NS(goto=AsyncMock(),evaluate=AsyncMock(return_value='bundled-default-UA'))
browser=NS(new_page=AsyncMock(return_value=page),cookies=AsyncMock(return_value=[]))
class Playwright:
    async def __aenter__(self):
        return NS(chromium=NS(launch_persistent_context=AsyncMock(return_value=browser)))
    async def __aexit__(self,*a): pass
class Transport:
    async def __aenter__(self): return self
    async def __aexit__(self,*a): pass
    async def request(self,method,url,**kw):
        calls.append(url.split('?')[0])
        assert kw['headers']['user-agent']=='bundled-default-UA'
        if url.endswith('/selfinfo'):
            data={'result':{'success':True}}
        elif url.endswith('/search/notes'):
            if scenario=='denied': return httpx.Response(403,json={'msg':'SECRET'})
            data={'has_more':False,'items':[] if scenario=='empty' else [
                {'id':'abc1','model_type':'note','xsec_token':'SECRET'}]}
        elif url.endswith('/feed'):
            data={'items':[{'note_card':{'note_id':'abc1','title':None,'desc':' 原文\ne\u0301😀 ',
                'time':1789000000123,'user':{},'interact_info':{}}}]}
        elif '/comment/page?' in url:
            data={'has_more':False,'cursor':'','comments':[{'id':'comment1',
                'content':' 原文\ne\u0301😀 ','create_time':1789000000123,
                'sub_comments':[],'sub_comment_has_more':False}]}
        else: raise AssertionError('Unexpected transport call')
        return httpx.Response(200,json={'code':0,'success':True,'data':data})
class Sink:
    async def store_content(self,item): raw.append(item)
    async def store_comment(self,item):
        raw.append(item)
        d=out/'xhs/jsonl'; d.mkdir(parents=True,exist_ok=True)
        (d/'search_comments_offline.jsonl').write_text(json.dumps(item,ensure_ascii=False)+'\n',encoding='utf-8')
core.async_playwright=Playwright
client.make_async_client=lambda **kw: Transport()
client.sign_with_xhshow=lambda **kw: {'x-s':'fixture','x-t':'fixture','x-s-common':'fixture','x-b3-traceid':'fixture'}
xhs.XhsStoreFactory.create_store=lambda: Sink()
main.cmd_arg.parse_cmd=AsyncMock(return_value=NS(init_db=False))
main._generate_wordcloud_if_needed=AsyncMock()
try: asyncio.run(main.main())
except SystemExit: pass
status=json.loads((out/'.yike-collection-status.json').read_text())
print('OFFLINE_RESULT='+json.dumps({'status':status,'raw':raw,'requests':len(calls)},ensure_ascii=False))
'''
    profile=tmp_path/'profile'; profile.mkdir()
    env={**os.environ,'YIKE_PROFILE_PATH':str(profile),'PYTHONIOENCODING':'utf-8'}
    result=subprocess.run([str(python),'-X','utf8','-c',script,str(tmp_path/'output'),scenario],
        cwd=source,env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert result.returncode == 0, result.stderr
    payload=json.loads(next(line.removeprefix('OFFLINE_RESULT=') for line in result.stdout.splitlines()
        if line.startswith('OFFLINE_RESULT=')))
    assert payload['status']['status'] == terminal
    assert 'SECRET' not in json.dumps(payload) and 'SECRET' not in result.stderr
    if scenario=='success':
        post,comment=payload['raw']
        assert post['title'] is None and post['desc']==comment['content']==' 原文\ne\u0301😀 '
        assert comment['create_time']=='2026-09-10T00:26:40Z'
        assert comment['parent_comment_id'] is None
        assert post['note_url']=='https://www.xiaohongshu.com/explore/abc1'
        assert payload['requests']==4
    else:
        assert payload['raw']==[] and payload['requests']==2
    if scenario=='denied':
        assert payload['status']['error_code']=='PLATFORM_PERMISSION_DENIED'
