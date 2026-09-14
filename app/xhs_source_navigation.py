"""Read-only, same-page XHS navigation; caller owns the governed browser.

No runtime/profile creation, API reads, credential exports, or persistent output.
Selectors are fail-closed UI contracts, not a claim of live platform support.
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urlsplit


_ORIGIN = 'https://www.xiaohongshu.com'
_ID = re.compile(r'[a-f0-9]{24}')
_ACCOUNT = re.compile(r'[A-Za-z0-9]{8,32}')
_BLOCKED = re.compile(
    r'^\s*(?:扫码登录|登录后查看|请先登录|安全验证|验证码|验证失败|访问受限|访问频繁|'
    r'操作频繁|账号异常|页面不存在|内容不存在|笔记不存在|笔记已删除|'
    r'暂时无法访问|无法展示|网络异常|404|当前笔记暂时无法浏览|'
    r'请打开小红书App扫码查看)\s*$', re.IGNORECASE)
_SOURCE_ANCESTOR = (
    'xpath=ancestor::*[@id="noteContainer" or @id="userPostedFeeds" or '
    'contains(concat(" ", normalize-space(@class), " "), " note-item ")]')


class XhsSourceNavigationError(RuntimeError):
    """Only fixed public codes may leave this module."""


def _fail(code):
    raise XhsSourceNavigationError('XHS_SOURCE_' + code) from None


def _path(value, *, relative=False):
    if not isinstance(value, str) or not value.isprintable() or '\\' in value:
        return None
    try:
        parsed = urlsplit(value)
        if relative and value.startswith('/') and not value.startswith('//'):
            if parsed.scheme or parsed.netloc:
                return None
        elif parsed.scheme != 'https' or parsed.netloc != 'www.xiaohongshu.com':
            return None
        return parsed.path
    except ValueError:
        return None


def _profile(value):
    path = _path(value, relative=True)
    match = re.fullmatch(r'/user/profile/([A-Za-z0-9]{8,32})', path or '')
    return match.group(1) if match else None


def _note(value, note_id, *, author_id=None):
    path = _path(value, relative=True)
    if author_id is not None:
        return path == '/user/profile/' + author_id + '/' + note_id
    return (path in ('/explore/' + note_id, '/search_result/' + note_id)
        or re.fullmatch(r'/user/profile/[a-f0-9]{24}/' + note_id, path or '') is not None)


async def navigate_xhs_source(page, *, note_id, expected_account, author_id=None,
                              original_query=None, cancelled=lambda: False):
    """Open the exact original note using its existing visible platform link.

    ``author_id`` must identify the ORIGINAL POST author, never a commenter.
    Unknown authors require the saved original query; no keyword substitution,
    pagination, scrolling or API fallback is attempted. Returns SOURCE_OPENED
    only after a visible detail/author check, otherwise raises a sanitized code.
    The caller must never print browser URLs or raw exception tracebacks/locals.
    """
    if (not isinstance(note_id, str) or not _ID.fullmatch(note_id)
            or not isinstance(expected_account, str) or not _ACCOUNT.fullmatch(expected_account)
            or (author_id is not None and (not isinstance(author_id, str) or not _ID.fullmatch(author_id)))
            or (original_query is not None and (not isinstance(original_query, str)
                or not 1 <= len(original_query) <= 200 or not original_query.strip()
                or not original_query.isprintable()))
            or (author_id is None and original_query is None) or not callable(cancelled)):
        _fail('INVALID_INPUT')

    def cancellation():
        if cancelled():
            _fail('CANCELLED')

    async def guard():
        cancellation()
        if _path(page.url) is None:
            _fail('ORIGIN_CHANGED')
        own = page.get_by_role('link', name='我', exact=True)
        try:
            await own.wait_for(state='visible', timeout=3000)
        except Exception:
            _fail('ACCOUNT_CHANGED')
        cancellation()
        if _path(page.url) is None:
            _fail('ORIGIN_CHANGED')
        if (await own.count() != 1 or not await own.is_visible(timeout=500)
                or _profile(await own.get_attribute('href', timeout=500)) != expected_account):
            _fail('ACCOUNT_CHANGED')
        blocked = page.get_by_text(_BLOCKED)
        count = await blocked.count()
        if count > 100:
            _fail('PLATFORM_BLOCKED')
        for index in range(count):
            message = blocked.nth(index)
            # Exact UI messages outside the source body/feed, not words in a post.
            if (await message.is_visible(timeout=500)
                    and await message.locator(_SOURCE_ANCESTOR).count() == 0):
                _fail('PLATFORM_BLOCKED')
        cancellation()
        if _path(page.url) is None:
            _fail('ORIGIN_CHANGED')

    try:
        async with asyncio.timeout(20):
            await guard()
            destination = (_ORIGIN + '/user/profile/' + author_id if author_id else _ORIGIN + '/explore')
            await page.goto(destination, wait_until='domcontentloaded', timeout=8000)
            await guard()
            if _path(page.url) != _path(destination):
                _fail('NOT_FOUND')
            if author_id is None:
                # Candidate UI contract, not yet verified against live XHS DOM.
                # It must actually exist; never guess a substitute control.
                search = page.locator('input#search-input')
                try:
                    await search.wait_for(state='visible', timeout=3000)
                except Exception:
                    _fail('SEARCH_UNAVAILABLE')
                await guard()
                if await search.count() != 1 or not await search.is_visible(timeout=500):
                    _fail('SEARCH_UNAVAILABLE')
                await guard()
                await search.fill(original_query, timeout=3000)
                await guard()
                await search.press('Enter', timeout=3000)
                await guard()

            links = page.locator('#userPostedFeeds a.cover' if author_id else 'a[href]')
            matches = []
            # Allow bounded SPA rendering; never scroll or retry the search.
            for attempt in range(6):
                await guard()
                count = await links.count()
                if count > 500:
                    _fail('NOT_FOUND')
                matches = []
                for index in range(count):
                    cancellation()
                    link = links.nth(index)
                    if (await link.is_visible(timeout=500)
                            and _note(await link.get_attribute('href', timeout=500), note_id, author_id=author_id)):
                        matches.append(link)
                        if len(matches) > 1:
                            _fail('NOT_FOUND')
                if matches:
                    break
                if attempt < 5:
                    await asyncio.sleep(0.2)
            if len(matches) != 1:
                _fail('NOT_FOUND')
            await guard()
            # Recheck href on the same locator immediately before the real click.
            link = matches[0]
            if (not await link.is_visible(timeout=500)
                    or not _note(await link.get_attribute('href', timeout=500), note_id, author_id=author_id)):
                _fail('NOT_FOUND')
            await guard()
            await link.click(timeout=4000)
            await guard()
            for attempt in range(6):
                await guard()
                detail = page.locator('#noteContainer')
                author = page.locator('#noteContainer .author-container a.name')
                if (_note(page.url, note_id) and await detail.count() == 1
                        and await detail.is_visible(timeout=500) and await author.count() == 1
                        and await author.is_visible(timeout=500)):
                    actual_author = _profile(await author.get_attribute('href', timeout=500))
                    if actual_author and _ID.fullmatch(actual_author) and (author_id is None or actual_author == author_id):
                        await guard()
                        if not _note(page.url, note_id):
                            _fail('DETAIL_UNAVAILABLE')
                        return 'SOURCE_OPENED'
                if attempt < 5:
                    await asyncio.sleep(0.2)
            _fail('DETAIL_UNAVAILABLE')
    except XhsSourceNavigationError:
        raise
    except Exception:
        _fail('UNAVAILABLE')
