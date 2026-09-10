"""Synthetic same-browser source/identity boundaries, not live platform proof."""
import asyncio
import io
import json
from types import SimpleNamespace as NS

import pytest

from app import platform_collection_worker as worker
from app import windows_collection_host as host
from pilot.foreground_collection import configured_collection_policy
from tests.test_platform_collection_worker import arguments
from tests.test_windows_collection_host import request, encoded
from tests.test_foreground_collection import config as search_config


@pytest.mark.parametrize('platform,account,code', [('BILIBILI', '123456', 'bili'), ('DOUYIN', 'studio_2026', 'dy')])
def test_platform_wire_cli_and_opt_in_policy(tmp_path, platform, account, code):
    payload = request(tmp_path) | {'platform': platform, 'expected_account_public_id': account}
    assert host._request(io.BytesIO(encoded(payload)))['expected_account_public_id'] == account
    args = arguments(tmp_path)
    args[1] = code
    worker._fixed_arguments(args, platform)
    with pytest.raises(ValueError): worker._fixed_arguments(args, 'XIAOHONGSHU')
    with pytest.raises(ValueError): host._request(io.BytesIO(encoded(payload | {'expected_account_public_id': 'bad id'})))
    config = search_config()
    policy = configured_collection_policy({'YIKE_PILOT_COLLECTION_MODE': 'three-platform-foreground-v1'})
    assert policy(platform, 'PLATFORM_ACCOUNT', config)
    assert not configured_collection_policy({'YIKE_PILOT_COLLECTION_MODE': 'xhs-foreground-v1'})(platform, 'PLATFORM_ACCOUNT', config)
    assert not policy(platform, 'PUBLIC', config)
    assert not policy('ZHIHU', 'PLATFORM_ACCOUNT', config)


@pytest.mark.parametrize('platform', ['BILIBILI', 'DOUYIN'])
@pytest.mark.parametrize('switch', [None, 'initial', 'response', 'completion', 'swallowed'])
def test_guard_enforces_account_before_after_source_and_restores_classes(platform, switch):
    expected = '123456' if platform == 'BILIBILI' else 'studio_2026'
    state = NS(account='999999' if switch == 'initial' else expected, search_calls=0, requests=0, closed=0)
    class AuthError(Exception): pass
    class Locator:
        async def wait_for(self, **kwargs): pass
        async def count(self): return 1
        async def is_visible(self): return True
        async def inner_text(self): return '抖音号： ' + state.account
    class Response:
        status = 200
        async def body(self):
            return json.dumps({'code': 0, 'data': {'isLogin': True, 'mid': int(state.account)}}).encode()
        async def dispose(self): pass
    class Request:
        async def get(self, url, **kwargs):
            assert url == 'https://api.bilibili.com/x/web-interface/nav'
            assert kwargs['max_redirects'] == 0 and kwargs['timeout'] <= 10000
            return Response()
    class Page:
        request = Request()
        url = 'https://www.douyin.com/' if platform == 'DOUYIN' else 'https://www.bilibili.com/'
        async def goto(self, url):
            assert url == 'https://www.douyin.com/user/self'
            self.url = url
            return NS(status=200)
        def get_by_text(self, pattern): return Locator()
        async def close(self): state.closed += 1
    class Context:
        async def new_page(self): return Page()
    class Client:
        def __init__(self, page): self.playwright_page = page
        async def request(self, *args, **kwargs):
            state.requests += 1
            if switch in ('response', 'swallowed'): state.account = '999999'
            return {'text': '原文'}
    class Crawler:
        def __init__(self):
            self.context_page = Page()
            self.browser_context = Context()
            self.bili_client = self.dy_client = Client(self.context_page)
        async def search(self):
            state.search_calls += 1
            try:
                result = await self.bili_client.request('GET', 'controlled')
            except AuthError:
                if switch != 'swallowed': raise
                state.account = expected
                return {}
            if switch == 'completion': state.account = '999999'
            return result
    original = (Crawler.search, Client.request)
    with worker.install_video_account_guard(Crawler, Client, AuthError, expected, platform):
        if switch is None:
            assert asyncio.run(Crawler().search()) == {'text': '原文'}
        else:
            with pytest.raises(AuthError): asyncio.run(Crawler().search())
    assert (Crawler.search, Client.request) == original
    assert state.search_calls == (0 if switch == 'initial' else 1)
    assert state.requests == (0 if switch == 'initial' else 1)
    assert state.closed == (1 if platform == 'DOUYIN' else 0)


@pytest.mark.parametrize('status,code,expected', [(429, 0, 'PLATFORM_RATE_LIMITED'),
    (403, 0, 'PLATFORM_PERMISSION_DENIED'), (200, -352, 'PLATFORM_VERIFICATION_REQUIRED')])
def test_bilibili_guard_preserves_known_limit_permission_challenge(status, code, expected):
    class Response:
        async def body(self): return json.dumps({'code': code}).encode()
        async def dispose(self): pass
    response = Response()
    response.status = status
    async def get(*args, **kwargs): return response
    with pytest.raises(worker._GuardFailure) as failure:
        asyncio.run(worker._bilibili_self_account(NS(request=NS(get=get))))
    assert failure.value.code == expected


@pytest.mark.parametrize('status,expected', [(403, 'Permission'), (429, 'Rate'), (500, 'Changed')])
def test_douyin_guard_maps_and_latches_structured_self_route_failure(status, expected):
    events = []
    code = {'Permission': 'PLATFORM_PERMISSION_DENIED', 'Rate': 'PLATFORM_RATE_LIMITED',
        'Changed': 'PLATFORM_RESPONSE_CHANGED'}[expected]
    error_types = {code: type(expected, (Exception,), {})}
    class AuthError(Exception): pass
    class Page:
        url = 'https://www.douyin.com/user/self'
        async def goto(self, url): events.append('guard'); return NS(status=status)
        async def close(self): events.append('close')
    class Context:
        async def new_page(self): return Page()
    class Client:
        def __init__(self, page): self.playwright_page = page
        async def request(self, *args, **kwargs): pytest.fail('source request must not start')
    class Crawler:
        def __init__(self):
            self.context_page = Page(); self.browser_context = Context(); self.dy_client = Client(self.context_page)
        async def search(self): await self.dy_client.request()
    with worker.install_video_account_guard(Crawler, Client, AuthError, 'studio_2026', 'DOUYIN', error_types=error_types):
        with pytest.raises(error_types[code]): asyncio.run(Crawler().search())
    assert events == ['guard', 'close']
