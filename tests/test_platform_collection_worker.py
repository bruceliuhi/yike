"""Same-crawler account binding at real wrapper method boundaries; no network."""
import asyncio
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ACCOUNT = '66c01234abcdef0123456789'
OTHER = '66c11234abcdef0123456789'


def module():
    assert importlib.util.find_spec('app.platform_collection_worker'), 'same-browser collection worker missing'
    return importlib.import_module('app.platform_collection_worker')


@pytest.fixture
def source():
    events, raw = [], []
    state = SimpleNamespace(account=ACCOUNT, count=1, visible=True,
        url='https://www.xiaohongshu.com/explore', switch=None, failure=None)
    class AuthError(Exception): pass
    class RateLimit(Exception): pass
    class Locator:
        async def count(self): return state.count
        async def is_visible(self): return state.visible
        async def get_attribute(self, key): return '/user/profile/' + state.account
    class DescendantLocator(Locator):
        async def count(self): return getattr(state, 'descendant_count', state.count)
    class Page:
        @property
        def url(self): return state.url
        def locator(self, selector):
            assert '我' in selector and '/user/profile/' in selector
            events.append('guard')
            return DescendantLocator()
        def get_by_role(self, role, *, name, exact):
            assert role == 'link' and name == '我' and exact is True
            events.append('guard')
            return Locator()
    class Client:
        def __init__(self, page): self.playwright_page = page
        async def request(self, method, url, **kwargs):
            events.append('http')
            if state.failure: raise state.failure
            if state.switch == 'response': state.account = OTHER
            return {'original': ' 原文 é😀 '}
    class Crawler:
        def __init__(self):
            self.context_page = Page()
            self.xhs_client = Client(self.context_page)
        async def search(self):
            events.append('search')
            raw.append(await self.xhs_client.request('POST', 'controlled-search'))
            if state.switch == 'second-request':
                state.account = OTHER
                await self.xhs_client.request('GET', 'controlled-comment')
            if state.switch == 'completion': state.account = OTHER
            return raw
    return SimpleNamespace(Crawler=Crawler, Client=Client, AuthError=AuthError,
        RateLimit=RateLimit, state=state, events=events, raw=raw)


def run(source):
    with module().install_account_guard(source.Crawler, source.Client, source.AuthError, ACCOUNT):
        return asyncio.run(source.Crawler().search())


def test_same_crawler_page_checked_before_and_after_search_and_requests(source):
    assert run(source) == [{'original': ' 原文 é😀 '}]
    assert source.events.count('search') == 1 and source.events.count('http') == 1
    assert source.events.count('guard') >= 4


def test_unrelated_profile_descendant_does_not_reject_unique_self_navigation(source):
    # The login entry already uses the exact accessible self link. Another
    # author anchor can contain a span saying 我 without being that self link.
    source.state.descendant_count = 2
    assert run(source) == [{'original': ' 原文 é😀 '}]
    assert source.events.count('search') == 1 and source.events.count('http') == 1


def test_descendant_span_alone_is_not_proof_of_self_account(source):
    source.state.descendant_count = 1
    source.state.count = 0
    with pytest.raises(source.AuthError): run(source)
    assert 'search' not in source.events and 'http' not in source.events


@pytest.mark.parametrize('change', [dict(account=OTHER), dict(count=0), dict(count=2),
    dict(visible=False), dict(url='https://evil.example/'), dict(account=ACCOUNT + '?secret=token')])
def test_unverified_wrong_or_ambiguous_account_never_starts_search(source, change):
    for key, value in change.items(): setattr(source.state, key, value)
    with pytest.raises(source.AuthError): run(source)
    assert 'search' not in source.events and 'http' not in source.events


@pytest.mark.parametrize('switch', ['second-request', 'response', 'completion'])
def test_mid_run_switch_never_returns_success_or_sends_next_request(source, switch):
    source.state.switch = switch
    with pytest.raises(source.AuthError): run(source)
    assert source.events.count('http') == 1
    if switch != 'response': assert source.raw == [{'original': ' 原文 é😀 '}]


def test_initial_login_self_request_remains_available_but_collection_never_uses_another_page(source):
    with module().install_account_guard(source.Crawler, source.Client, source.AuthError, ACCOUNT):
        crawler = source.Crawler()
        source.state.account = OTHER
        asyncio.run(crawler.xhs_client.request('GET', 'controlled-selfinfo'))
        assert source.events == ['http']
        source.state.account = ACCOUNT
        crawler.context_page = object()
        with pytest.raises(source.AuthError): asyncio.run(crawler.search())


def test_original_rate_limit_propagates_without_retry_or_empty_success(source):
    source.state.failure = source.RateLimit('controlled')
    with pytest.raises(source.RateLimit): run(source)
    assert source.events.count('http') == 1 and not source.raw


def test_class_adapters_are_restored_after_completion(source):
    search, request = source.Crawler.search, source.Client.request
    run(source)
    assert source.Crawler.search is search and source.Client.request is request


def arguments(output):
    return ['--platform', 'xhs', '--lt', 'qrcode', '--type', 'search', '--keywords', '咖啡',
        '--get_comment', 'yes', '--get_sub_comment', 'yes', '--headless', 'no',
        '--save_data_option', 'jsonl', '--max_concurrency_num', '1', '--enable_ip_proxy', 'no',
        '--save_data_path', str(output), '--crawler_max_notes_count', '1',
        '--max_comments_count_singlenotes', '2']


@pytest.mark.parametrize('extra', [['--init_db', 'sqlite'], ['--platform', 'dy'],
    ['--cookies', 'private'], ['--keywords', 'second'], ['--unknown=secret']])
def test_fixed_cli_never_accepts_other_platform_database_cookie_or_duplicate(tmp_path, extra):
    module()._fixed_arguments(arguments(tmp_path))
    with pytest.raises(ValueError): module()._fixed_arguments(arguments(tmp_path) + extra)


@pytest.mark.parametrize('mode', ['matched', 'wrong', 'switch'])
def test_installed_main_status_cleanup_with_controlled_source_and_http(tmp_path, mode):
    """Real installed start/client/main, fixture browser and search body; no external network."""
    installed = Path(os.environ.get('YIKE_SOURCE_INSTALLED_CHECK',
        'C:/Users/bruce/AI/意客AI2026/.runtime/windows-installed-xhs-20260910-02'))
    python = installed / ('.venv/Scripts/python.exe' if sys.platform == 'win32' else '.venv/bin/python')
    if not python.is_file(): pytest.skip('Operator installed runtime unavailable; never downloads')
    worker = Path(module().__file__).resolve()
    script = '''import importlib.util, json, os, socket, sys
from pathlib import Path
from types import SimpleNamespace as NS
original_connect = socket.socket.connect
def forbidden(self, address):
    if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
        return original_connect(self, address)
    raise AssertionError('External network forbidden')
socket.socket.connect = forbidden
spec = importlib.util.spec_from_file_location('product_collection_worker', sys.argv[1])
worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)
mode = sys.argv[2]
sys.argv = [sys.argv[1]] + sys.argv[3:]
from media_platform.xhs import core, client
import httpx
events = []
account = '66c11234abcdef0123456789' if mode == 'wrong' else '66c01234abcdef0123456789'
class Locator:
    async def count(self): return 1
    async def is_visible(self): return True
    async def get_attribute(self, key): return '/user/profile/' + account
class Page:
    url = 'https://www.xiaohongshu.com/explore'
    async def goto(self, url): events.append('home')
    async def evaluate(self, value):
        assert value == 'navigator.userAgent'
        return 'controlled-browser'
    def get_by_role(self, role, *, name, exact):
        assert role == 'link' and name == '我' and exact is True
        return Locator()
class Context:
    async def new_page(self): return Page()
    async def cookies(self, *, urls):
        assert urls == ['https://www.xiaohongshu.com']
        return [{'name': 'a1', 'value': 'fixture-secret'}]
    async def close(self): events.append('context-closed')
class Chromium:
    async def launch_persistent_context(self, **kw):
        assert kw['headless'] is False and kw['accept_downloads'] is False
        assert kw['user_data_dir'] == os.environ['YIKE_PROFILE_PATH']
        events.append('persistent-browser'); return Context()
class Playwright:
    async def __aenter__(self): return NS(chromium=Chromium())
    async def __aexit__(self, *a): events.append('playwright-closed')
class Transport:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass
    async def request(self, method, url, **kw):
        assert method == 'GET' and url == 'https://edith.xiaohongshu.com/api/sns/web/v1/user/selfinfo'
        events.append('http')
        return httpx.Response(200, json={'success': True, 'code': 0, 'data': {'result': {'success': True}}})
client.make_async_client = lambda **kw: Transport()
client.sign_with_xhshow = lambda **kw: {'x-s':'fixture', 'x-t':'fixture', 'x-s-common':'fixture', 'x-b3-traceid':'fixture'}
core.async_playwright = Playwright
async def controlled_search(self):
    global account
    events.append('search')
    await self.xhs_client.request('GET', 'https://edith.xiaohongshu.com/api/sns/web/v1/user/selfinfo')
    import config
    raw = Path(config.SAVE_DATA_PATH) / 'xhs/jsonl/search_comments_fixture.jsonl'
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text('{"content":"原文 unchanged"}\\n', encoding='utf-8')
    if mode == 'switch': account = '66c11234abcdef0123456789'
core.XiaoHongShuCrawler.search = controlled_search
try: code = worker.main()
except SystemExit as exc: code = exc.code
print(json.dumps({'exit': code, 'events': events}))
'''
    from app.collector import _minimal_child_environment
    environment = _minimal_child_environment(YIKE_PROFILE_PATH=str(tmp_path),
        YIKE_EXPECTED_ACCOUNT_PUBLIC_ID=ACCOUNT, PYTHONDONTWRITEBYTECODE='1',
        TEMP=str(tmp_path), TMP=str(tmp_path), MPLCONFIGDIR=str(tmp_path))
    measured = ['main.py', 'media_platform/xhs/core.py', 'media_platform/xhs/client.py']
    # POSIX exercises the pinned source only, never Windows installation proof.
    if sys.platform == 'win32': measured.append('.yike-windows-install.json')
    before = {name: (installed / name).read_bytes() for name in measured}
    proc = subprocess.run([str(python), '-X', 'utf8', '-c', script, str(worker), mode, *arguments(tmp_path)],
        cwd=installed, env=environment, capture_output=True, timeout=30)
    assert proc.returncode == 0, proc.stderr.decode('utf-8', errors='replace')
    result = json.loads(proc.stdout)
    assert result['events'][-1] == 'context-closed'
    assert result['events'].count('persistent-browser') == 1
    assert result['events'].count('search') == (0 if mode == 'wrong' else 1)
    status = json.loads((tmp_path / '.yike-collection-status.json').read_text(encoding='utf-8'))
    assert result['exit'] == (0 if mode == 'matched' else 40)
    assert status['status'] == ('SUCCEEDED' if mode == 'matched' else 'BLOCKED_INPUT')
    if mode != 'matched': assert status['error_code'] == 'PLATFORM_AUTH_REQUIRED'
    raw = tmp_path / 'xhs/jsonl/search_comments_fixture.jsonl'
    assert raw.exists() == (mode != 'wrong')
    if raw.exists(): assert raw.read_text(encoding='utf-8') == '{"content":"原文 unchanged"}\n'
    assert 'fixture-secret' not in proc.stdout.decode()
    assert before == {name: (installed / name).read_bytes() for name in measured}
