"""Private runtime lifetime for a confirmed XHS post-comment channel.

The supervised host must already own the verified runtime cwd/profile lease.
No CLI, login flow, credential export or independent sending entry is installed.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import re
from urllib.parse import urlsplit

from app.platform_login_worker import _load_runtime
from app.xhs_comment_channel import XhsPostCommentChannel


class _RuntimeFailure(RuntimeError):
    pass


def _fail(code):
    raise _RuntimeFailure('OUTREACH_RUNTIME_' + code)


@asynccontextmanager
async def open_xhs_comment_channel(context, *, cancelled, now=None):
    """Yield only after the same governed page passes the actual channel check.

    Caller retains execute's result before leaving the context: a cleanup error
    does not prove non-delivery and must never authorize another click.
    """
    try:
        snapshot = deepcopy(context)
        source, target = snapshot['source'], snapshot['target']
        post_id, author_id, url = target['postId'], target['authorPublicId'], source['url']
        if (source['platform'] != 'XIAOHONGSHU' or source['kind'] != 'POST'
                or target['action'] != 'POST_COMMENT' or target['commentId'] is not None
                or not isinstance(post_id, str) or not re.fullmatch('[a-f0-9]{24}', post_id)
                or not isinstance(author_id, str) or not re.fullmatch('[a-f0-9]{24}', author_id)
                or not isinstance(url, str) or not url.isprintable() or '\\' in url):
            raise ValueError()
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.netloc != 'www.xiaohongshu.com'
                or parsed.path != '/explore/' + post_id or parsed.query or parsed.fragment):
            raise ValueError()
    except Exception:
        _fail('INVALID_CONTEXT')

    def guard():
        if cancelled():
            _fail('CANCELLED')

    guard()
    crawler = manager = None
    entered = False
    try:
        try:
            async with asyncio.timeout(20):
                runtime = _load_runtime()
                guard()
                crawler = runtime.XiaoHongShuCrawler()
                manager = runtime.async_playwright()
                playwright = await manager.__aenter__()
                entered = True
                guard()
                crawler.browser_context = await crawler.launch_browser(
                    playwright.chromium, None, None, False)
                guard()
                crawler.context_page = await crawler.browser_context.new_page()
                guard()
                profile_url = 'https://www.xiaohongshu.com/user/profile/' + author_id
                await crawler.context_page.goto(profile_url, wait_until='domcontentloaded', timeout=15000)
                guard()
                current = urlsplit(crawler.context_page.url)
                if (current.scheme != 'https' or current.netloc != 'www.xiaohongshu.com'
                        or current.path != '/user/profile/' + author_id):
                    _fail('SOURCE_UNAVAILABLE')
                note_path = '/user/profile/' + author_id + '/' + post_id
                # Use the platform's visible link; never export its ephemeral query.
                link = crawler.context_page.locator(
                    f'#userPostedFeeds a.cover[href="{note_path}"], '
                    f'#userPostedFeeds a.cover[href^="{note_path}?"]')
                await link.wait_for(state='visible', timeout=5000)
                guard()
                if await link.count() != 1:
                    _fail('SOURCE_UNAVAILABLE')
                guard()
                await link.click(timeout=5000)
                guard()
                options = {'cancelled': cancelled}
                if now is not None:
                    options['now'] = now
                channel = XhsPostCommentChannel(crawler.context_page, **options)
                await channel.check(snapshot)
                guard()
        except _RuntimeFailure:
            raise
        except Exception:
            _fail('START_FAILED')
        yield channel
    finally:
        cleanup_failed = False
        if crawler is not None:
            try:
                async with asyncio.timeout(10):
                    await crawler.close()
            except BaseException:
                cleanup_failed = True
        if entered:
            try:
                async with asyncio.timeout(10):
                    await manager.__aexit__(None, None, None)
            except BaseException:
                cleanup_failed = True
        if cleanup_failed:
            _fail('CLEANUP_FAILED')
