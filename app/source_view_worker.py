"""Bounded, read-only original viewer in an existing governed XHS profile."""
from __future__ import annotations

import asyncio
from contextlib import redirect_stderr, redirect_stdout
import json
import os
from pathlib import Path
import re
import sys

# The portable runtime executes this fixed file directly with an isolated _pth.
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.platform_login_worker import _load_runtime, _official_page, _write
from app.xhs_source_navigation import navigate_xhs_source, XhsSourceNavigationError

SCHEMA = 'windows-source-view-v1'
CODES = {'SOURCE_HOST_FAILED'} | {'XHS_SOURCE_' + code for code in (
    'INVALID_INPUT', 'BUSY', 'CANCELLED', 'TIMED_OUT', 'ORIGIN_CHANGED', 'ACCOUNT_CHANGED',
    'PLATFORM_BLOCKED', 'NOT_FOUND', 'SEARCH_UNAVAILABLE', 'DETAIL_UNAVAILABLE', 'UNAVAILABLE')}


def failure(code='SOURCE_HOST_FAILED', state='FAILED'):
    return dict(schema_version=SCHEMA, state=state, error_code=code)


def valid_target(*, note_id, expected_account, author_id, original_query, timeout_seconds):
    return (isinstance(note_id, str) and re.fullmatch(r'[a-f0-9]{24}', note_id) is not None
        and isinstance(expected_account, str) and re.fullmatch(r'[A-Za-z0-9]{8,32}', expected_account) is not None
        and (author_id is None or isinstance(author_id, str) and re.fullmatch(r'[a-f0-9]{24}', author_id) is not None)
        and (original_query is None or isinstance(original_query, str) and 1 <= len(original_query) <= 200
            and bool(original_query.strip()) and original_query.isprintable())
        and (author_id is not None or original_query is not None)
        and type(timeout_seconds) is int and 1 <= timeout_seconds <= 300)


async def view_xhs_source(*, output_path, note_id, expected_account, author_id=None,
                          original_query=None, timeout_seconds=300, cancelled=lambda: False):
    if not valid_target(note_id=note_id, expected_account=expected_account, author_id=author_id,
            original_query=original_query, timeout_seconds=timeout_seconds) or not callable(cancelled):
        return failure('XHS_SOURCE_INVALID_INPUT')
    try:
        if cancelled(): return failure('XHS_SOURCE_CANCELLED', 'CANCELLED')
        runtime = _load_runtime()
        crawler = runtime.XiaoHongShuCrawler()
        async with runtime.async_playwright() as playwright:
            try:
                # Governed launcher owns persistent profile configuration; no clients/login/cookie calls.
                crawler.browser_context = await crawler.launch_browser(playwright.chromium, None, None, False)
                crawler.context_page = page = await crawler.browser_context.new_page()
                try:
                    async with asyncio.timeout(20):
                        await page.goto('https://www.xiaohongshu.com', wait_until='domcontentloaded', timeout=8000)
                        if not _official_page(page.url):
                            raise XhsSourceNavigationError('XHS_SOURCE_ORIGIN_CHANGED')
                        opened = await navigate_xhs_source(page, note_id=note_id, expected_account=expected_account,
                            author_id=author_id, original_query=original_query, cancelled=cancelled)
                    if opened != 'SOURCE_OPENED': raise RuntimeError()
                    _write(output_path, '.yike-source-opened.json', dict(schema_version=SCHEMA,state='SOURCE_OPENED'))
                    deadline = asyncio.get_running_loop().time() + timeout_seconds
                    while True:
                        if cancelled():
                            result = failure('XHS_SOURCE_CANCELLED', 'CANCELLED'); break
                        if page.is_closed():
                            result = dict(schema_version=SCHEMA,state='CLOSED'); break
                        if asyncio.get_running_loop().time() >= deadline:
                            result = failure('XHS_SOURCE_TIMED_OUT', 'TIMED_OUT'); break
                        await asyncio.sleep(0.1)
                except XhsSourceNavigationError as error:
                    code = str(error)
                    result = failure(code if code in CODES else 'SOURCE_HOST_FAILED',
                        'CANCELLED' if code == 'XHS_SOURCE_CANCELLED' else 'FAILED')
                except TimeoutError:
                    result = failure('XHS_SOURCE_UNAVAILABLE')
            finally:
                await crawler.close()
        return result
    except KeyboardInterrupt:
        # Host owns cancellation; arbitrary interrupts can occur during cleanup.
        return failure()
    except Exception:
        return failure()


def main():
    with open(os.devnull, 'w', encoding='utf-8') as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
        try:
            output = Path(os.environ['YIKE_SOURCE_OUTPUT_PATH'])
            profile = Path(os.environ['YIKE_PROFILE_PATH'])
            if not output.is_absolute() or not output.is_dir() or not profile.is_absolute() or not profile.is_dir(): return 1
            target = json.loads(os.environ['YIKE_SOURCE_TARGET'])
            result = asyncio.run(view_xhs_source(output_path=output, **target))
            _write(output, '.yike-source-terminal.json', result)
            return 0
        except (Exception, KeyboardInterrupt):
            return 1


if __name__ == '__main__':
    raise SystemExit(main())
