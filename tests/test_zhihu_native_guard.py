"""Synthetic same-context identity checks; not a live Zhihu acceptance."""
import asyncio
import io
import json
from types import SimpleNamespace as NS

import pytest

from app import platform_collection_worker as worker
from app import platform_login_worker as login
from app import windows_collection_host as host
from tests.test_platform_collection_worker import arguments
from tests.test_windows_collection_host import request, encoded
from pilot.foreground_collection import configured_collection_policy
from tests.test_foreground_collection import config


def test_zhihu_total_budget_is_not_divided_like_legacy_comment_budget():
    from app.windows_source_driver import _collection_limits
    assert _collection_limits('ZHIHU',20) == (5,20)
    assert _collection_limits('ZHIHU',1) == (1,1)
    assert _collection_limits('BILIBILI',20) == (5,4)


def test_zhihu_wire_requires_account_but_does_not_enable_three_platform_policy(tmp_path):
    payload = request(tmp_path) | {'platform':'ZHIHU','expected_account_public_id':'123456'}
    assert host._request(io.BytesIO(encoded(payload)))['platform'] == 'ZHIHU'
    args = arguments(tmp_path); args[1] = 'zhihu'
    worker._fixed_arguments(args, 'ZHIHU')
    for uid in ('bad id', '0', '01', True, None):
        with pytest.raises(ValueError):
            host._request(io.BytesIO(encoded(payload | {'expected_account_public_id':uid})))
    payload.pop('expected_account_public_id')
    with pytest.raises(ValueError): host._request(io.BytesIO(encoded(payload)))
    assert not configured_collection_policy({'YIKE_PILOT_COLLECTION_MODE':'three-platform-monitor-v1'})(
        'ZHIHU','PLATFORM_ACCOUNT',config())


@pytest.mark.parametrize('status,body,code', [
    (200, {'uid':'123456'}, None), (200, {'uid':123456}, None),
    (200, {'id':'hash','name':'someone'},'PLATFORM_ACCOUNT_UNVERIFIED'),
    (200, {'uid':True},'PLATFORM_ACCOUNT_UNVERIFIED'),
    (401, {},'PLATFORM_AUTH_REQUIRED'), (403, {},'PLATFORM_PERMISSION_DENIED'),
    (429, {},'PLATFORM_RATE_LIMITED'), (404, {},'PLATFORM_RESPONSE_CHANGED'),
    (503, {},'COLLECTION_NETWORK_FAILED'),
])
def test_self_request_only_returns_uid_and_disposes(status,body,code):
    events = []
    class Response:
        async def body(self): return json.dumps(body).encode()
        async def dispose(self): events.append('disposed')
    response = Response(); response.status = status
    async def get(url, **options):
        assert url == 'https://www.zhihu.com/api/v4/me'
        assert options == {'max_redirects':0,'timeout':10000}
        return response
    page = NS(url='https://www.zhihu.com/search?q=test',request=NS(get=get))
    if code:
        with pytest.raises(login._LoginError) as failure:
            asyncio.run(login.read_zhihu_self_account(page))
        assert failure.value.code == code
    else: assert asyncio.run(login.read_zhihu_self_account(page)) == '123456'
    assert events == ['disposed']


@pytest.mark.parametrize('switch', [None,'initial','response','completion','swallowed'])
def test_guard_binds_same_context_latches_failures_and_restores(monkeypatch,switch):
    state = NS(uid='999' if switch == 'initial' else '123456', calls=0)
    class AuthError(Exception): pass
    async def own(page): return state.uid
    monkeypatch.setattr(worker,'read_zhihu_self_account',own)
    class Client:
        def __init__(self,page): self.playwright_page = page
        async def request(self,*args,**kwargs):
            state.calls += 1
            if switch in ('response','swallowed'): state.uid = '999'
            return 'source'
    class Crawler:
        def __init__(self):
            self.context_page = object(); self.zhihu_client = Client(self.context_page)
        async def search(self):
            try: result = await self.zhihu_client.request('GET','search')
            except AuthError:
                if switch != 'swallowed': raise
                state.uid = '123456'; return 'hidden failure'
            if switch == 'completion': state.uid = '999'
            return result
    original = (Crawler.search,Client.request)
    with worker.install_zhihu_account_guard(Crawler,Client,AuthError,'123456'):
        if switch is None: assert asyncio.run(Crawler().search()) == 'source'
        else:
            with pytest.raises(AuthError): asyncio.run(Crawler().search())
    assert (Crawler.search,Client.request) == original
    assert state.calls == (0 if switch == 'initial' else 1)


@pytest.mark.parametrize('close_fails',[False,True])
def test_login_uses_fixed_zhihu_client_and_waits_for_cleanup(tmp_path,monkeypatch,close_fails):
    events=[]
    class Page:
        url=''
        async def goto(self,url): self.url=url
    class Context:
        async def new_page(self): return Page()
    class Client:
        async def pong(self): events.append('pong'); return True
    class Crawler:
        async def launch_browser(self,chromium,proxy,**options):
            assert options == {'headless':False,'user_agent':None}
            return Context()
        async def create_zhihu_client(self,proxy): return Client()
        async def close(self):
            events.append('closed')
            if close_fails: raise RuntimeError('do not disclose')
    class Playwright:
        async def __aenter__(self): return NS(chromium='fixed')
        async def __aexit__(self,*args): events.append('playwright closed')
    async def own(page):
        assert page.url == 'https://www.zhihu.com'
        events.append('own'); return '123456'
    monkeypatch.setattr(login,'read_zhihu_self_account',own)
    monkeypatch.setattr(login,'_load_video_runtime',lambda selected: NS(
        Crawler=Crawler,async_playwright=Playwright,classify_error=lambda error:('COLLECTION_PROCESS_FAILED',48)))
    result=asyncio.run(login.login_platform(platform='ZHIHU',output_path=tmp_path))
    assert events == ['pong','own','closed','playwright closed']
    assert result['state'] == ('FAILED' if close_fails else 'AUTHENTICATED')
    assert ('account_public_id' in result) is not close_fails
    assert 'do not disclose' not in json.dumps(result)


def test_rate_limit_is_preserved_by_guard_without_retry(monkeypatch):
    calls=[]
    class RateError(Exception): pass
    class AuthError(Exception): pass
    async def limited(page): calls.append('self'); raise login._LoginError('PLATFORM_RATE_LIMITED')
    monkeypatch.setattr(worker,'read_zhihu_self_account',limited)
    class Client:
        async def request(self,*args,**kwargs): raise AssertionError('must not search')
    class Crawler:
        def __init__(self):
            self.context_page=object(); self.zhihu_client=Client(); self.zhihu_client.playwright_page=self.context_page
        async def search(self): raise AssertionError('must not search')
    with worker.install_zhihu_account_guard(Crawler,Client,AuthError,'123456',error_types={'PLATFORM_RATE_LIMITED':RateError}):
        with pytest.raises(RateError): asyncio.run(Crawler().search())
    assert calls == ['self']
