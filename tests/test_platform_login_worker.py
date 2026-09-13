"""Real login orchestration with controlled browser/self-account HTTP boundaries."""
import asyncio
from datetime import datetime, timedelta, timezone
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest


ACCOUNT = '66c01234abcdef0123456789'


def module():
    assert importlib.util.find_spec('app.platform_login_worker'), 'login worker missing'
    return importlib.import_module('app.platform_login_worker')


@pytest.fixture
def runtime():
    events = []
    state = SimpleNamespace(href='/user/profile/' + ACCOUNT, count=1, broad_count=None, visible=True,
        pong=[True], url='https://www.xiaohongshu.com/', close_error=False, login_error=False, exit_error=False)
    class Locator:
        def __init__(self, broad=False): self.broad = broad
        async def count(self):
            return state.broad_count if self.broad and state.broad_count is not None else state.count
        async def is_visible(self): return state.visible
        async def get_attribute(self, name):
            assert name == 'href'
            return state.href
    class Page:
        @property
        def url(self): return state.url
        async def goto(self, url):
            assert url == 'https://www.xiaohongshu.com'
            events.append('home')
        def locator(self, selector):
            assert '我' in selector and 'span' in selector and '/user/profile/' in selector
            events.append('self-navigation')
            return Locator(broad=True)
        def get_by_role(self, role, *, name, exact):
            assert role == 'link' and name == '我' and exact is True
            events.append('self-navigation')
            return Locator()
    class Context:
        async def new_page(self): return Page()
    class Client:
        async def pong(self):
            events.append('self-account-read')
            return state.pong.pop(0)
        async def update_cookies(self, context, *, urls):
            assert urls == ['https://www.xiaohongshu.com']
            events.append('refresh')
    class Crawler:
        def __init__(self): self.cookie_urls = ['https://www.xiaohongshu.com']
        async def launch_browser(self, chromium, proxy, agent, headless):
            assert chromium == 'controlled' and proxy is None and agent is None and headless is False
            events.append('browser-open')
            return Context()
        async def create_xhs_client(self, proxy):
            assert proxy is None
            events.append('client-created')
            return Client()
        async def close(self):
            events.append('browser-close')
            if state.close_error: raise RuntimeError('secret close failure')
    class Login:
        def __init__(self, **kwargs): assert kwargs['login_type'] == 'qrcode'
        async def begin(self):
            events.append('user-login')
            if state.login_error: raise RuntimeError('private login details')
    class Playwright:
        async def __aenter__(self): return SimpleNamespace(chromium='controlled')
        async def __aexit__(self, *args):
            events.append('playwright-close')
            if state.exit_error: raise RuntimeError('secret playwright cleanup')
    return SimpleNamespace(api=SimpleNamespace(async_playwright=Playwright,
        XiaoHongShuCrawler=Crawler, XiaoHongShuLogin=Login,
        classify_error=lambda exc: ('COLLECTION_PROCESS_FAILED', 48)), state=state, events=events)


def run(tmp_path, runtime, monkeypatch):
    api = module()
    monkeypatch.setattr(api, '_load_runtime', lambda: runtime.api)
    result = asyncio.run(api.login_xhs(output_path=tmp_path))
    return result


def test_pong_authenticated_reads_only_unique_self_navigation_after_browser_open(tmp_path, runtime, monkeypatch):
    result = run(tmp_path, runtime, monkeypatch)
    assert result['state'] == 'AUTHENTICATED' and result['account_public_id'] == ACCOUNT
    assert result['checked_at'].endswith('Z')
    assert runtime.events == ['browser-open', 'home', 'self-navigation', 'client-created', 'self-account-read', 'self-navigation', 'browser-close', 'playwright-close']
    assert json.loads((tmp_path / '.yike-login-opened.json').read_text()) == {
        'schema_version': 'windows-platform-login-v1', 'state': 'OPENED'}
    assert 'secret' not in str(result)


def test_unique_accessible_self_link_ignores_other_profile_links_with_nested_me_text(tmp_path, runtime, monkeypatch):
    # Actual signed-in page: old XPath matches four anchors; exact accessible
    # self-navigation matches one. Arbitrary author/profile links are not self.
    runtime.state.broad_count = 4
    result = run(tmp_path, runtime, monkeypatch)
    assert result['state'] == 'AUTHENTICATED'
    assert result['account_public_id'] == ACCOUNT
    assert runtime.events.count('self-account-read') == 1
    assert 'user-login' not in runtime.events


def test_logged_out_uses_existing_user_login_refresh_then_rechecks_self(tmp_path, runtime, monkeypatch):
    runtime.state.count = 0
    runtime.state.pong = [True]
    async def user_login(self):
        assert 'client-created' not in runtime.events
        assert 'self-account-read' not in runtime.events
        runtime.events.append('user-login')
        runtime.state.count = 1
    monkeypatch.setattr(runtime.api.XiaoHongShuLogin, 'begin', user_login)
    assert run(tmp_path, runtime, monkeypatch)['state'] == 'AUTHENTICATED'
    assert runtime.events[2:7] == ['self-navigation', 'user-login', 'client-created', 'self-account-read', 'self-navigation']


def test_invisible_self_link_waits_for_user_before_requesting_account(tmp_path, runtime, monkeypatch):
    runtime.state.visible = False
    async def user_login(self):
        assert 'self-account-read' not in runtime.events
        runtime.events.append('user-login')
        runtime.state.visible = True
    monkeypatch.setattr(runtime.api.XiaoHongShuLogin, 'begin', user_login)
    assert run(tmp_path, runtime, monkeypatch)['state'] == 'AUTHENTICATED'
    assert runtime.events.index('user-login') < runtime.events.index('client-created')


@pytest.mark.parametrize('after_login', ['false-pong', 'foreign-page', 'missing-self', 'response-error'])
def test_user_wait_does_not_bypass_post_login_verification(tmp_path, runtime, monkeypatch, after_login):
    runtime.state.count = 0
    async def user_login(self):
        assert 'self-account-read' not in runtime.events
        runtime.events.append('user-login')
        runtime.state.count = 0 if after_login == 'missing-self' else 1
        if after_login == 'foreign-page': runtime.state.url = 'https://evil.example/'
        if after_login == 'false-pong': runtime.state.pong = [False]
    monkeypatch.setattr(runtime.api.XiaoHongShuLogin, 'begin', user_login)
    if after_login == 'response-error':
        create = runtime.api.XiaoHongShuCrawler.create_xhs_client
        async def client(self, proxy):
            value = await create(self, proxy)
            async def pong():
                raise module()._LoginError('PLATFORM_RESPONSE_CHANGED')
            value.pong = pong
            return value
        monkeypatch.setattr(runtime.api.XiaoHongShuCrawler, 'create_xhs_client', client)
    result = run(tmp_path, runtime, monkeypatch)
    assert result['state'] != 'AUTHENTICATED' and 'account_public_id' not in result
    assert 'user-login' in runtime.events
    assert runtime.events[-2:] == ['browser-close', 'playwright-close']
    if after_login == 'foreign-page': assert 'client-created' not in runtime.events
    if after_login == 'response-error': assert result['error_code'] == 'PLATFORM_RESPONSE_CHANGED'


def test_ambiguous_self_links_never_choose_an_account_or_start_login(tmp_path, runtime, monkeypatch):
    runtime.state.count = 2
    assert run(tmp_path, runtime, monkeypatch)['error_code'] == 'PLATFORM_ACCOUNT_UNVERIFIED'
    assert 'client-created' not in runtime.events and 'user-login' not in runtime.events


@pytest.mark.parametrize('change', [dict(count=0), dict(count=2), dict(visible=False),
    dict(href='/user/profile/昵称'), dict(href='/user/profile/' + ACCOUNT + '?token=private'),
    dict(href='https://evil.example/user/profile/' + ACCOUNT),
    dict(href='https://www.xiaohongshu.com.evil/user/profile/' + ACCOUNT),
    dict(href='/user/profile/%36' + ACCOUNT), dict(url='https://evil.example/')])
def test_no_arbitrary_profile_nickname_cookie_or_ambiguous_self_identity(tmp_path, runtime, monkeypatch, change):
    for name, value in change.items(): setattr(runtime.state, name, value)
    result = run(tmp_path, runtime, monkeypatch)
    assert result['state'] != 'AUTHENTICATED' and 'account_public_id' not in result
    assert runtime.events[-2:] == ['browser-close', 'playwright-close']
    assert 'private' not in str(result)


def test_canonical_official_absolute_self_href_is_accepted(tmp_path, runtime, monkeypatch):
    runtime.state.href = 'https://www.xiaohongshu.com/user/profile/' + ACCOUNT
    assert run(tmp_path, runtime, monkeypatch)['account_public_id'] == ACCOUNT


@pytest.mark.parametrize('kind', ['close', 'login', 'pong-false'])
def test_failed_login_or_cleanup_never_authenticates(tmp_path, runtime, monkeypatch, kind):
    if kind == 'close': runtime.state.close_error = True
    elif kind == 'login': runtime.state.count = 0; runtime.state.login_error = True
    else: runtime.state.pong = [False]
    result = run(tmp_path, runtime, monkeypatch)
    assert result['state'] != 'AUTHENTICATED' and 'account_public_id' not in result
    if kind == 'close': assert result['error_code'] == 'SOURCE_HOST_FAILED'
    assert 'private' not in str(result) and 'secret' not in str(result)


def test_playwright_exit_failure_is_unknown_cleanup_not_safe_failure(tmp_path, runtime, monkeypatch):
    runtime.state.exit_error = True
    result = run(tmp_path, runtime, monkeypatch)
    assert result == dict(schema_version='windows-platform-login-v1', state='FAILED', error_code='SOURCE_HOST_FAILED')


def test_official_home_route_query_does_not_replace_canonical_self_identity(tmp_path, runtime, monkeypatch):
    runtime.state.url = 'https://www.xiaohongshu.com/explore?channel_id=homefeed_recommend'
    assert run(tmp_path, runtime, monkeypatch)['account_public_id'] == ACCOUNT


def test_slow_cleanup_does_not_refresh_self_identity_observation_time(tmp_path, runtime, monkeypatch):
    class Clock:
        current = datetime(2026, 9, 10, 0, tzinfo=timezone.utc)
        @classmethod
        def now(cls, tz): return cls.current
    monkeypatch.setattr(module(), 'datetime', Clock)
    close = runtime.api.XiaoHongShuCrawler.close
    async def slow_close(self):
        await close(self)
        Clock.current += timedelta(seconds=130)
    monkeypatch.setattr(runtime.api.XiaoHongShuCrawler, 'close', slow_close)
    result = run(tmp_path, runtime, monkeypatch)
    assert result['state'] == 'AUTHENTICATED'
    assert result['checked_at'] == '2026-09-10T00:00:00Z'


def test_installed_core_client_login_methods_with_controlled_browser_http_only(tmp_path):
    """Read installed product imports, but forbid socket network and browser launch."""
    installed = Path(os.environ.get('YIKE_LOGIN_INSTALLED_RUNTIME',
        'C:/Users/bruce/AI/意客AI2026/.runtime/windows-installed-xhs-20260910-02'))
    python = installed / '.venv/Scripts/python.exe'
    if not python.is_file(): pytest.skip('Local governed installed runtime is unavailable; never downloads')
    worker = Path(module().__file__).resolve()
    script = '''import asyncio, importlib.util, json, os, socket, sys
from pathlib import Path
from types import SimpleNamespace as NS
original_connect = socket.socket.connect
def forbidden(self, address):
    # Windows asyncio implements its own wakeup socketpair through loopback.
    if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
        return original_connect(self, address)
    raise AssertionError('External network is forbidden in this fixture')
socket.socket.connect = forbidden
spec = importlib.util.spec_from_file_location('product_login_worker', sys.argv[1])
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
runtime = worker._load_runtime()
from media_platform.xhs import client as client_module
import httpx
events = []
class Locator:
    async def count(self): return 1 if 'user-login' in events else 0
    async def is_visible(self): return True
    async def get_attribute(self, key): return '/user/profile/66c01234abcdef0123456789'
class Page:
    url = 'https://www.xiaohongshu.com/explore'
    async def goto(self, url): events.append('home')
    async def evaluate(self, value):
        assert value == 'navigator.userAgent'
        return 'controlled-browser'
    async def content(self): return '<normal user page>'
    async def is_visible(self, selector, timeout):
        assert "我" in selector
        events.append('user-login')
        return True
    def get_by_role(self, role, *, name, exact):
        assert role == 'link' and name == '我' and exact is True
        return Locator()
class Context:
    async def new_page(self): return Page()
    async def cookies(self, *, urls):
        assert urls == ['https://www.xiaohongshu.com']
        events.append('cookies-in-memory')
        return [{'name': 'a1', 'value': 'fixture-secret'}]
    async def close(self): events.append('context-closed')
class Chromium:
    async def launch_persistent_context(self, **kw):
        assert kw['headless'] is False and kw['accept_downloads'] is False
        assert kw['user_data_dir'] == os.environ['YIKE_PROFILE_PATH']
        events.append('persistent-browser')
        return Context()
class Playwright:
    async def __aenter__(self): return NS(chromium=Chromium())
    async def __aexit__(self, *a): events.append('playwright-closed')
class Transport:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass
    async def request(self, method, url, **kw):
        assert method == 'GET' and url == 'https://edith.xiaohongshu.com/api/sns/web/v1/user/selfinfo'
        events.append('self-http')
        assert 'user-login' in events
        return httpx.Response(200, json={'success': True, 'code': 0, 'data': {'result': {'success': True}}})
client_module.make_async_client = lambda **kw: Transport()
client_module.sign_with_xhshow = lambda **kw: {'x-s':'fixture', 'x-t':'fixture', 'x-s-common':'fixture', 'x-b3-traceid':'fixture'}
runtime.async_playwright = Playwright
worker._load_runtime = lambda: runtime
result = asyncio.run(worker.login_xhs(output_path=Path(sys.argv[2])))
assert result['state'] == 'AUTHENTICATED', result
assert result['account_public_id'] == '66c01234abcdef0123456789'
assert events.count('self-http') == 1 and events.count('user-login') == 1
assert events.count('cookies-in-memory') == 1
assert events[-2:] == ['context-closed', 'playwright-closed']
print(json.dumps({'state': result['state'], 'events': events}))
'''
    from app.collector import _minimal_child_environment
    environment = _minimal_child_environment(YIKE_PROFILE_PATH=str(tmp_path),
        PYTHONDONTWRITEBYTECODE='1', TEMP=str(tmp_path), TMP=str(tmp_path), MPLCONFIGDIR=str(tmp_path))
    measured = ['.yike-windows-install.json', 'media_platform/xhs/core.py',
        'media_platform/xhs/client.py', 'media_platform/xhs/login.py']
    before = {name: (installed / name).read_bytes() for name in measured}
    proc = subprocess.run([str(python), '-X', 'utf8', '-c', script, str(worker), str(tmp_path)],
        cwd=installed, env=environment, capture_output=True, timeout=30)
    assert proc.returncode == 0, proc.stderr.decode('utf-8', errors='replace')
    result = json.loads(proc.stdout)
    assert result['state'] == 'AUTHENTICATED' and 'fixture-secret' not in proc.stdout.decode()
    assert before == {name: (installed / name).read_bytes() for name in measured}
