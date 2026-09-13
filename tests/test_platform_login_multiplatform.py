"""Synthetic public self-page/client boundaries; not real Windows login proof."""
import asyncio
from contextlib import nullcontext
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from app import platform_login_worker as worker
from app import windows_platform_login as host


@pytest.mark.parametrize('platform,account', [('BILIBILI', '123456'), ('DOUYIN', 'studio_2026.test')])
def test_host_selects_platform_and_validates_its_terminal(monkeypatch, platform, account):
    monkeypatch.setattr(host, '_paths', lambda *values: list(values))
    frame = dict(schema_version=host.SCHEMA, runtime_path='C:/runtime', profile_path='C:/profile',
        output_path='C:/output', platform=platform, timeout_seconds=60)
    assert host._request(io.BytesIO((json.dumps(frame) + '\n').encode()))['platform'] == platform
    terminal = dict(schema_version=host.SCHEMA, state='AUTHENTICATED',
        account_public_id=account, checked_at='2026-09-12T00:00:00Z')
    assert host._terminal(terminal, platform) == terminal
    with pytest.raises(ValueError):
        host._terminal(terminal | {'account_public_id': 'not a public id'}, platform)
    with pytest.raises(ValueError):
        host._terminal(terminal, 'WEIBO')


@pytest.mark.parametrize('platform', ['BILIBILI', 'DOUYIN'])
def test_fixed_video_login_identity_and_cleanup(tmp_path, monkeypatch, platform):
    events = []
    state = NS(pongs=[False, True], nav={'isLogin': True, 'mid': 123456},
        text='抖音号： studio_2026.test', count=1, visible=True, foreign=False, close_error=False, ready=False)
    class Clock:
        current = datetime(2026, 9, 12, tzinfo=timezone.utc)
        @classmethod
        def now(cls, tz): return cls.current
    monkeypatch.setattr(worker, 'datetime', Clock)
    class Locator:
        async def wait_for(self, *, state: str, timeout):
            assert state == 'visible' and 0 < timeout <= 10000
            await asyncio.sleep(0)
            mark_ready()
        async def count(self): return state.count if state.ready else 0
        async def is_visible(self): return state.visible
        async def inner_text(self): return state.text
    def mark_ready(): state.ready = True
    class Page:
        url = ''
        async def goto(self, url):
            self.url = 'https://evil.example/user/self' if state.foreign else url
            return NS(status=200)
        async def evaluate(self, script):
            assert 'navigator.userAgent' in script
            return 'synthetic-agent'
        def get_by_text(self, pattern):
            assert pattern.fullmatch(state.text)
            return Locator()
    class Context:
        async def new_page(self): return Page()
    class Client:
        async def pong(self, **kwargs):
            assert ('browser_context' in kwargs) == (platform == 'DOUYIN')
            return state.pongs.pop(0)
        async def update_cookies(self, context, *, urls): events.append('refresh')
        async def get(self, uri):
            assert uri == '/x/web-interface/nav'
            return state.nav
    class Crawler:
        cookie_urls = ['https://www.bilibili.com' if platform == 'BILIBILI' else 'https://www.douyin.com']
        async def launch_browser(self, chromium, proxy, *args, **kwargs):
            assert kwargs['headless'] is False
            return Context()
        async def create_bilibili_client(self, proxy): return Client()
        async def create_douyin_client(self, proxy): return Client()
        async def close(self):
            events.append('closed')
            Clock.current += timedelta(seconds=130)
            if state.close_error: raise RuntimeError('secret cleanup')
    class Login:
        def __init__(self, **kwargs): assert kwargs['login_type'] == 'qrcode'
        async def begin(self): events.append('login')
    class Playwright:
        async def __aenter__(self): return NS(chromium='controlled')
        async def __aexit__(self, *args): events.append('playwright-closed')
    runtime = NS(Crawler=Crawler, Login=Login, async_playwright=Playwright,
        classify_error=lambda exc: ('COLLECTION_PROCESS_FAILED', 48))
    monkeypatch.setattr(worker, '_load_video_runtime', lambda selected: runtime)
    def run():
        # Each attempt has a distinct private directory, as in the host.
        out = tmp_path / str(len(list(tmp_path.iterdir())))
        out.mkdir()
        state.pongs = [False, True]
        state.ready = False
        return asyncio.run(worker.login_platform(platform=platform, output_path=out))
    result = run()
    assert result['account_public_id'] == ('123456' if platform == 'BILIBILI' else 'studio_2026.test')
    assert result['checked_at'] == '2026-09-12T00:00:00Z'
    assert events == ['login', 'refresh', 'closed', 'playwright-closed']
    cases = ([{'nav': {'isLogin': False, 'mid': 123456}}, {'nav': {'isLogin': True, 'mid': True}},
        {'nav': {'isLogin': True, 'mid': 0}}] if platform == 'BILIBILI' else
        [{'count': 2}, {'visible': False}, {'foreign': True}])
    for case in cases + [{'close_error': True}]:
        before = {key: getattr(state, key) for key in case}
        for key, value in case.items(): setattr(state, key, value)
        failed = run()
        assert failed['state'] != 'AUTHENTICATED' and 'account_public_id' not in failed
        assert 'secret' not in str(failed)
        assert events[-2:] == ['closed', 'playwright-closed']
        for key, value in before.items(): setattr(state, key, value)


def test_unknown_platform_never_loads_a_browser(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, '_load_runtime', lambda: pytest.fail('must not load XHS'))
    assert asyncio.run(worker.login_platform(platform='WEIBO', output_path=tmp_path))['state'] == 'FAILED'


@pytest.mark.parametrize('platform,account', [('BILIBILI', '123456'), ('DOUYIN', 'studio_2026.test'), ('ZHIHU', '123456')])
@pytest.mark.parametrize('authenticated', [True, False])
def test_inspect_only_video_checks_headlessly_without_login(tmp_path, monkeypatch, platform, account, authenticated):
    events = []
    class Page:
        url = ''
        async def goto(self, url): self.url = url
        async def evaluate(self, script): return 'controlled-agent'
    class Context:
        async def new_page(self): return Page()
    class Client:
        async def pong(self, **kwargs): return authenticated
        async def get(self, uri):
            assert uri == '/x/web-interface/nav'
            return {'isLogin': True, 'mid': int(account)}
        async def update_cookies(self, *args, **kwargs): pytest.fail('must not refresh login cookies')
    class Crawler:
        async def launch_browser(self, chromium, proxy, **kwargs):
            assert kwargs['headless'] is True
            events.append('headless')
            return Context()
        async def create_bilibili_client(self, proxy): return Client()
        async def create_douyin_client(self, proxy): return Client()
        async def create_zhihu_client(self, proxy): return Client()
        async def close(self): events.append('closed')
    class Playwright:
        async def __aenter__(self): return NS(chromium='controlled')
        async def __aexit__(self, *args): events.append('playwright-closed')
    def forbidden(**kwargs): pytest.fail('inspect must never create QR login')
    async def self_account(page): return account
    monkeypatch.setattr(worker, 'read_douyin_self_account', self_account)
    monkeypatch.setattr(worker, 'read_zhihu_self_account', self_account)
    monkeypatch.setattr(worker, '_load_video_runtime', lambda _: NS(Crawler=Crawler, Login=forbidden,
        async_playwright=Playwright, classify_error=lambda exc: ('COLLECTION_PROCESS_FAILED', 48)))
    result = asyncio.run(worker.login_platform(platform=platform, output_path=tmp_path, inspect_only=True))
    assert events == ['headless', 'closed', 'playwright-closed']
    assert not (tmp_path / '.yike-login-opened.json').exists()
    if authenticated: assert result['account_public_id'] == account
    else: assert result['error_code'] == 'PLATFORM_AUTH_REQUIRED' and 'account_public_id' not in result


@pytest.mark.parametrize('status,expected', [(401, 'PLATFORM_AUTH_REQUIRED'),
    (403, 'PLATFORM_PERMISSION_DENIED'), (429, 'PLATFORM_RATE_LIMITED'),
    (500, 'PLATFORM_RESPONSE_CHANGED')])
def test_douyin_self_route_preserves_http_failure(status, expected):
    class Page:
        url = 'https://www.douyin.com/user/self'
        async def goto(self, url): return NS(status=status)
    with pytest.raises(worker._LoginError) as failure:
        asyncio.run(worker.read_douyin_self_account(Page()))
    assert failure.value.code == expected


def test_douyin_self_route_preserves_navigation_network_failure():
    class Page:
        url = ''
        async def goto(self, url): raise TimeoutError('private network detail')
    with pytest.raises(worker._LoginError) as failure:
        asyncio.run(worker.read_douyin_self_account(Page()))
    assert failure.value.code == 'COLLECTION_NETWORK_FAILED'


@pytest.mark.parametrize('platform,account', [('BILIBILI', '123456'), ('DOUYIN', 'studio_2026.test')])
def test_host_threads_platform_through_private_child_and_terminal(tmp_path, monkeypatch, platform, account):
    # OS/Job are explicit synthetic boundaries. Actual host dispatch/marker code runs.
    monkeypatch.setattr(host, 'sys', NS(platform='win32'))
    monkeypatch.setattr(host, '_paths', lambda *paths: [Path(path) for path in paths])
    monkeypatch.setattr(host, '_exclusive_paths', lambda paths: nullcontext())
    monkeypatch.setattr(host, 'verify_installed_runtime', lambda path: tmp_path / 'python')
    monkeypatch.setattr(host, 'verify_private_tree', lambda path: None)
    monkeypatch.setattr(host, 'verify_browser_profile_tree', lambda path: None)
    def private(path):
        path.mkdir()
        return path
    monkeypatch.setattr(host, 'create_private_directory', private)
    def process(command, **kwargs):
        assert kwargs['env']['YIKE_LOGIN_PLATFORM'] == platform
        assert command[-1].endswith('platform_login_worker.py')
        output = Path(kwargs['env']['YIKE_LOGIN_OUTPUT_PATH'])
        worker._write(output, '.yike-login-opened.json', dict(schema_version=host.SCHEMA, state='OPENED'))
        worker._write(output, '.yike-login-terminal.json', dict(schema_version=host.SCHEMA,
            state='AUTHENTICATED', account_public_id=account, checked_at='2026-09-12T00:00:00Z'))
        return NS(returncode=0, cancelled=False, timed_out=False)
    monkeypatch.setattr(host, 'run_supervised_process', process)
    opened = []
    result = host.login_windows_platform(runtime_path=tmp_path / 'runtime', profile_path=tmp_path / 'profile',
        output_path=tmp_path / 'output', platform=platform, timeout_seconds=60,
        on_opened=lambda: opened.append(True))
    assert opened == [True] and result['account_public_id'] == account
