import asyncio
import importlib
import importlib.util
import json
from types import SimpleNamespace

import pytest


def module():
    assert importlib.util.find_spec('app.source_view_worker'), 'source viewer missing'
    return importlib.import_module('app.source_view_worker')


def args(tmp_path):
    return dict(output_path=tmp_path, note_id='a' * 24, expected_account='b' * 24,
        author_id='c' * 24, original_query=None, timeout_seconds=1)


@pytest.mark.parametrize('change', [dict(note_id='https://secret'), dict(expected_account=''),
    dict(author_id=None), dict(original_query='\n'), dict(timeout_seconds=301), dict(timeout_seconds=True)])
def test_invalid_target_never_loads_runtime(tmp_path, monkeypatch, change):
    api = module()
    monkeypatch.setattr(api, '_load_runtime', lambda: pytest.fail('runtime loaded'))
    assert asyncio.run(api.view_xhs_source(**(args(tmp_path) | change)))['error_code'] == 'XHS_SOURCE_INVALID_INPUT'


@pytest.mark.parametrize('outcome', ['closed', 'cancel', 'timeout', 'navigation', 'cleanup', 'cleanup-interrupt', 'unverified'])
def test_verified_open_stays_alive_and_terminal_follows_cleanup(tmp_path, monkeypatch, outcome):
    api = module()
    events = []
    class Page:
        url = 'https://www.xiaohongshu.com'
        async def goto(self, url, **kw): events.append('home')
        def is_closed(self):
            events.append('view')
            return outcome == 'closed'
    class Context:
        async def new_page(self): return Page()
    class Crawler:
        async def launch_browser(self, chromium, proxy, agent, headless):
            assert headless is False
            events.append('launch')
            return Context()
        async def close(self):
            events.append('close')
            if outcome == 'cleanup': raise RuntimeError('secret')
            if outcome == 'cleanup-interrupt': raise KeyboardInterrupt()
    class Playwright:
        async def __aenter__(self): return SimpleNamespace(chromium=True)
        async def __aexit__(self, *a): events.append('playwright-close')
    async def navigate(page, **kw):
        assert kw['note_id'] == 'a' * 24 and kw['expected_account'] == 'b' * 24
        events.append('navigate')
        assert not (tmp_path / '.yike-source-opened.json').exists()
        if outcome == 'navigation': raise api.XhsSourceNavigationError('XHS_SOURCE_NOT_FOUND')
        return 'SOURCE_OPENED' if outcome != 'unverified' else 'OPENED'
    monkeypatch.setattr(api, '_load_runtime', lambda: SimpleNamespace(XiaoHongShuCrawler=Crawler, async_playwright=Playwright))
    monkeypatch.setattr(api, 'navigate_xhs_source', navigate)
    result = asyncio.run(api.view_xhs_source(**args(tmp_path), cancelled=lambda: 'navigate' in events and outcome in ('cancel', 'cleanup', 'cleanup-interrupt')))
    assert events[-2:] == ['close', 'playwright-close']
    assert result['state'] == {'closed':'CLOSED','cancel':'CANCELLED','timeout':'TIMED_OUT',
        'navigation':'FAILED','cleanup':'FAILED','cleanup-interrupt':'FAILED','unverified':'FAILED'}[outcome]
    marker = tmp_path / '.yike-source-opened.json'
    assert marker.exists() == (outcome not in ('navigation', 'unverified'))
    if marker.exists(): assert json.loads(marker.read_text()) == dict(schema_version=api.SCHEMA,state='SOURCE_OPENED')
    assert 'secret' not in str(result)
