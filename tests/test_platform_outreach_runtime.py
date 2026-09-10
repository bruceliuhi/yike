"""Runtime lifetime tests; platform and Playwright boundaries are synthetic."""
import asyncio
import importlib
import importlib.util
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest


def api():
    assert importlib.util.find_spec('app.platform_outreach_runtime'), 'outreach runtime missing'
    return importlib.import_module('app.platform_outreach_runtime')


@pytest.fixture
def harness(monkeypatch):
    module = api()
    events = []
    state = SimpleNamespace(cancelled=False, fail_check=False, fail_close=False, missing_link=False)
    page = SimpleNamespace(url='about:blank')

    async def goto(url, **kwargs):
        events.append(('goto', url))
        assert kwargs['wait_until'] == 'domcontentloaded'
        page.url = url
    page.goto = goto

    class Link:
        async def wait_for(self, **kwargs):
            if state.missing_link:
                raise RuntimeError('private missing source detail')
        async def count(self): return 1
        async def click(self, **kwargs):
            events.append('open_original_note')
            page.url = 'https://www.xiaohongshu.com/explore/' + 'a' * 24
    def locator(selector):
        assert '#userPostedFeeds a.cover' in selector
        assert '/user/profile/' + 'b' * 24 + '/' + 'a' * 24 in selector
        return Link()
    page.locator = locator

    class Browser:
        async def new_page(self):
            events.append('new_page')
            return page

    class Crawler:
        async def create_xhs_client(self, proxy):
            assert proxy is None
            events.append('create_api')
            async def read(**kwargs):
                events.append(('read_sub_comments', kwargs))
                return {'comments': [], 'has_more': False, 'cursor': ''}
            return SimpleNamespace(get_note_sub_comments=read)
        async def launch_browser(self, chromium, proxy, agent, headless):
            assert (chromium, proxy, agent, headless) == ('chromium', None, None, False)
            events.append('launch')
            return Browser()
        async def close(self):
            events.append('close')
            if state.fail_close:
                raise RuntimeError('private platform detail')

    @asynccontextmanager
    async def playwright():
        events.append('playwright')
        try:
            yield SimpleNamespace(chromium='chromium')
        finally:
            events.append('playwright_close')

    class Channel:
        def __init__(self, own_page, *, cancelled, now=None, read_sub_comments=None):
            assert own_page is page
            self.page = own_page
            self.read_sub_comments = read_sub_comments
        async def check(self, context):
            events.append('check')
            if state.fail_check:
                raise RuntimeError('private account details')
            return {'status': 'AVAILABLE'}

    monkeypatch.setattr(module, '_load_runtime', lambda: SimpleNamespace(
        XiaoHongShuCrawler=Crawler, async_playwright=playwright))
    monkeypatch.setattr(module, 'XhsPostCommentChannel', Channel)
    context = {'source': {'platform': 'XIAOHONGSHU', 'kind': 'POST',
        'url': 'https://www.xiaohongshu.com/explore/' + 'a' * 24},
        'target': {'action': 'POST_COMMENT', 'postId': 'a' * 24, 'commentId': None,
            'authorPublicId': 'b' * 24}}
    return SimpleNamespace(module=module, events=events, state=state, context=context, page=page)


def test_runtime_reuses_governed_browser_and_checks_before_yield(harness):
    h = harness
    async def run():
        async with h.module.open_xhs_comment_channel(h.context, cancelled=lambda: False) as channel:
            assert channel.page is h.page
            assert h.events[-1] == 'check'
            assert 'close' not in h.events
    asyncio.run(run())
    assert h.events[-2:] == ['close', 'playwright_close']
    assert h.events.count('launch') == 1
    assert ('goto', 'https://www.xiaohongshu.com/user/profile/' + 'b' * 24) in h.events
    assert h.events.index('open_original_note') < h.events.index('check')


def test_reply_client_is_lazy_and_owned_by_same_runtime(harness):
    h = harness
    async def run():
        async with h.module.open_xhs_comment_channel(h.context, cancelled=lambda: False) as channel:
            assert 'create_api' not in h.events
            request = dict(note_id='a' * 24, root_comment_id='c' * 24, xsec_token='synthetic-transient', num=10, cursor='')
            assert await channel.read_sub_comments(**request) == {'comments': [], 'has_more': False, 'cursor': ''}
            await channel.read_sub_comments(**request)
        assert h.events.count('create_api') == 1
        assert h.events[-2:] == ['close', 'playwright_close']
    asyncio.run(run())


@pytest.mark.parametrize('failure', ['cancelled', 'check', 'close', 'unsafe_url', 'missing_link'])
def test_failures_are_closed_and_private_details_not_exposed(harness, failure):
    h = harness
    h.state.cancelled = failure == 'cancelled'
    h.state.fail_check = failure == 'check'
    h.state.fail_close = failure == 'close'
    h.state.missing_link = failure == 'missing_link'
    if failure == 'unsafe_url':
        h.context['source']['url'] += '?xsec_token=private'
    async def run():
        async with h.module.open_xhs_comment_channel(h.context,
                cancelled=lambda: h.state.cancelled):
            assert failure == 'close'
    with pytest.raises(RuntimeError, match='^OUTREACH_RUNTIME_[A-Z_]+$') as error:
        asyncio.run(run())
    assert 'private' not in str(error.value)
    if failure in ('cancelled', 'unsafe_url'):
        assert 'launch' not in h.events
    else:
        assert h.events[-2:] == ['close', 'playwright_close']
