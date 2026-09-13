"""Fixed three-platform login/self check only; launched by the private Windows host.

No search, collection, sending, cookie import/export or CAPTCHA automation.
The installed governed runtime is the working directory and import source.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace
from urllib.parse import urlsplit


SCHEMA = 'windows-platform-login-v1'
_HOME = 'https://www.xiaohongshu.com'
_HREF = re.compile(r'(?:https://www\.xiaohongshu\.com)?/user/profile/([A-Za-z0-9]{8,32})')
_ACCOUNTS = {'XIAOHONGSHU': r'[A-Za-z0-9]{8,32}',
    'BILIBILI': r'[1-9][0-9]{0,19}', 'DOUYIN': r'[A-Za-z0-9_.-]{1,64}',
    'ZHIHU': r'[1-9][0-9]{0,19}'}
_DY_SELF = 'https://www.douyin.com/user/self'
_DY_HANDLE = re.compile(r'^抖音号[：:]\s*([A-Za-z0-9_.-]{1,64})\s*$')
_CODES = {'PLATFORM_AUTH_REQUIRED', 'PLATFORM_PERMISSION_DENIED',
          'PLATFORM_VERIFICATION_REQUIRED', 'PLATFORM_RATE_LIMITED',
          'PLATFORM_RESPONSE_CHANGED', 'COLLECTION_NETWORK_FAILED',
          'COLLECTION_PARSE_FAILED', 'COLLECTION_PROCESS_FAILED'}


class _LoginError(Exception):
    def __init__(self, code): self.code = code


def _failure(code, state='FAILED'):
    return dict(schema_version=SCHEMA, state=state, error_code=code)


def valid_account(platform, value):
    return (isinstance(platform, str) and platform in _ACCOUNTS and isinstance(value, str)
        and re.fullmatch(_ACCOUNTS[platform], value) is not None)


def login_platform_supported(platform):
    return isinstance(platform, str) and platform in _ACCOUNTS


def _official_page(url, host='www.xiaohongshu.com'):
    if not isinstance(url, str) or not url.isprintable() or '\\' in url: return False
    parsed = urlsplit(url)
    return parsed.scheme == 'https' and parsed.netloc == host


def _write(output_path: Path, name: str, payload: dict) -> None:
    # The host created the private output directory. Never create/repair it here.
    temporary = output_path / (name + '.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')))
    os.replace(temporary, output_path / name)


def _load_runtime():
    sys.path.insert(0, str(Path.cwd()))
    from media_platform.xhs.core import XiaoHongShuCrawler, async_playwright
    from media_platform.xhs.login import XiaoHongShuLogin
    from tools.yike_runtime import classify_error
    return SimpleNamespace(XiaoHongShuCrawler=XiaoHongShuCrawler,
        XiaoHongShuLogin=XiaoHongShuLogin, async_playwright=async_playwright,
        classify_error=classify_error)


def _load_video_runtime(platform):
    sys.path.insert(0, str(Path.cwd()))
    # Fixed imports only; caller input never becomes an import path.
    if platform == 'BILIBILI':
        from media_platform.bilibili.core import BilibiliCrawler as Crawler, async_playwright
        from media_platform.bilibili.login import BilibiliLogin as Login
    elif platform == 'DOUYIN':
        from media_platform.douyin.core import DouYinCrawler as Crawler, async_playwright
        from media_platform.douyin.login import DouYinLogin as Login
    elif platform == 'ZHIHU':
        from media_platform.zhihu.core import ZhihuCrawler as Crawler, async_playwright
        from media_platform.zhihu.login import ZhiHuLogin as Login
    else:
        raise ValueError()
    from tools.yike_runtime import classify_error
    return SimpleNamespace(Crawler=Crawler, Login=Login,
        async_playwright=async_playwright, classify_error=classify_error)


def _classified_failure(error, runtime, cleanup_failed):
    if cleanup_failed:
        return _failure('SOURCE_HOST_FAILED')
    if isinstance(error, KeyboardInterrupt):
        return _failure('PLATFORM_LOGIN_CANCELLED', 'CANCELLED')
    if isinstance(error, _LoginError):
        code = error.code
    elif runtime is not None:
        code, _ = runtime.classify_error(error)
        if code not in _CODES: code = 'COLLECTION_PROCESS_FAILED'
    else:
        code = 'COLLECTION_PROCESS_FAILED'
    if code == 'COLLECTION_PROCESS_FAILED':
        return _failure('SOURCE_HOST_FAILED')
    state = 'BLOCKED_INPUT' if code in {'PLATFORM_AUTH_REQUIRED', 'PLATFORM_PERMISSION_DENIED',
        'PLATFORM_VERIFICATION_REQUIRED', 'PLATFORM_RATE_LIMITED', 'PLATFORM_ACCOUNT_UNVERIFIED'} else 'FAILED'
    return _failure(code, state)


async def read_douyin_self_account(page):
    """Read only the official self route. Caller owns this page/context."""
    try:
        response = await page.goto(_DY_SELF)
    except Exception:
        raise _LoginError('COLLECTION_NETWORK_FAILED') from None
    status = getattr(response, 'status', None)
    code = {401: 'PLATFORM_AUTH_REQUIRED', 403: 'PLATFORM_PERMISSION_DENIED',
        429: 'PLATFORM_RATE_LIMITED'}.get(status)
    if code:
        raise _LoginError(code)
    if type(status) is not int or not 200 <= status < 300:
        raise _LoginError('PLATFORM_RESPONSE_CHANGED')
    def self_url():
        url = urlsplit(page.url)
        return url.scheme == 'https' and url.netloc == 'www.douyin.com' and url.path == '/user/self'
    if not self_url():
        raise _LoginError('PLATFORM_ACCOUNT_UNVERIFIED')
    label = page.get_by_text(_DY_HANDLE)
    try:
        await label.wait_for(state='visible', timeout=10000)
    except Exception:
        raise _LoginError('PLATFORM_ACCOUNT_UNVERIFIED') from None
    if not self_url() or await label.count() != 1 or not await label.is_visible():
        raise _LoginError('PLATFORM_ACCOUNT_UNVERIFIED')
    match = _DY_HANDLE.fullmatch(await label.inner_text())
    if match is None:
        raise _LoginError('PLATFORM_ACCOUNT_UNVERIFIED')
    return match.group(1)


async def read_zhihu_self_account(page):
    """Only the current context's official self endpoint; never return its profile."""
    if not _official_page(page.url, 'www.zhihu.com'):
        raise _LoginError('PLATFORM_ACCOUNT_UNVERIFIED')
    try:
        response = await page.request.get('https://www.zhihu.com/api/v4/me', max_redirects=0, timeout=10000)
    except Exception:
        raise _LoginError('COLLECTION_NETWORK_FAILED') from None
    try:
        code = {401:'PLATFORM_AUTH_REQUIRED',403:'PLATFORM_PERMISSION_DENIED',429:'PLATFORM_RATE_LIMITED'}.get(response.status)
        if code: raise _LoginError(code)
        if response.status >= 500: raise _LoginError('COLLECTION_NETWORK_FAILED')
        if response.status != 200: raise _LoginError('PLATFORM_RESPONSE_CHANGED')
        raw = await response.body()
        if len(raw) > 65536: raise ValueError()
        def pairs(items):
            result = {}
            for key,value in items:
                if key in result: raise ValueError()
                result[key] = value
            return result
        data = json.loads(raw, object_pairs_hook=pairs)
        if not isinstance(data,dict) or data.get('error'): raise ValueError()
        uid = data.get('uid')
        if type(uid) not in (int,str) or not valid_account('ZHIHU',str(uid)):
            raise _LoginError('PLATFORM_ACCOUNT_UNVERIFIED')
        if not _official_page(page.url,'www.zhihu.com'):
            raise _LoginError('PLATFORM_ACCOUNT_UNVERIFIED')
        return str(uid)
    except (ValueError,TypeError,UnicodeError):
        raise _LoginError('PLATFORM_RESPONSE_CHANGED') from None
    finally:
        await response.dispose()


async def login_platform(*, platform, output_path: Path, inspect_only=False) -> dict:
    if type(inspect_only) is not bool:
        return _failure('SOURCE_HOST_FAILED')
    if platform == 'XIAOHONGSHU':
        return await login_xhs(output_path=output_path, inspect_only=inspect_only)
    if not login_platform_supported(platform):
        return _failure('SOURCE_HOST_FAILED')
    runtime = None
    cleanup_failed = False
    try:
        runtime = _load_video_runtime(platform)
        crawler = runtime.Crawler()
        home = {'BILIBILI':'https://www.bilibili.com','DOUYIN':'https://www.douyin.com',
            'ZHIHU':'https://www.zhihu.com'}[platform]
        async with runtime.async_playwright() as playwright:
            try:
                options = {} if platform == 'BILIBILI' else {'user_agent': None}
                crawler.browser_context = await crawler.launch_browser(playwright.chromium, None,
                    headless=inspect_only, **options)
                if not inspect_only:
                    _write(output_path, '.yike-login-opened.json', dict(schema_version=SCHEMA, state='OPENED'))
                crawler.context_page = await crawler.browser_context.new_page()
                await crawler.context_page.goto(home)
                if not _official_page(crawler.context_page.url, urlsplit(home).netloc):
                    raise _LoginError('PLATFORM_RESPONSE_CHANGED')
                if platform == 'BILIBILI':
                    crawler.user_agent = await crawler.context_page.evaluate('navigator.userAgent')
                    client = crawler.bili_client = await crawler.create_bilibili_client(None)
                    pong_args = {}
                elif platform == 'ZHIHU':
                    client = crawler.zhihu_client = await crawler.create_zhihu_client(None)
                    pong_args = {}
                else:
                    client = crawler.dy_client = await crawler.create_douyin_client(None)
                    pong_args = {'browser_context': crawler.browser_context}
                if not await client.pong(**pong_args):
                    if inspect_only:
                        raise _LoginError('PLATFORM_AUTH_REQUIRED')
                    login = runtime.Login(login_type='qrcode', browser_context=crawler.browser_context,
                        context_page=crawler.context_page)
                    await login.begin()
                    await client.update_cookies(crawler.browser_context, urls=crawler.cookie_urls)
                    if not await client.pong(**pong_args):
                        raise _LoginError('PLATFORM_AUTH_REQUIRED')
                if platform == 'BILIBILI':
                    own = await client.get('/x/web-interface/nav')
                    mid = own.get('mid') if isinstance(own, dict) else None
                    if not isinstance(own, dict) or own.get('isLogin') is not True or type(mid) not in (str, int):
                        raise _LoginError('PLATFORM_ACCOUNT_UNVERIFIED')
                    account = str(mid)
                elif platform == 'ZHIHU':
                    account = await read_zhihu_self_account(crawler.context_page)
                else:
                    # Only the signed-in self route; never arbitrary creator URLs.
                    account = await read_douyin_self_account(crawler.context_page)
                if not valid_account(platform, account):
                    raise _LoginError('PLATFORM_ACCOUNT_UNVERIFIED')
                checked_at = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
            finally:
                try:
                    await crawler.close()
                except BaseException:
                    cleanup_failed = True
                    raise
        return dict(schema_version=SCHEMA, state='AUTHENTICATED', account_public_id=account,
            checked_at=checked_at)
    except (Exception, KeyboardInterrupt) as error:
        return _classified_failure(error, runtime, cleanup_failed)


async def login_xhs(*, output_path: Path, inspect_only=False) -> dict:
    if type(inspect_only) is not bool:
        return _failure('SOURCE_HOST_FAILED')
    runtime = None
    cleanup_failed = False
    try:
        runtime = _load_runtime()
        crawler = runtime.XiaoHongShuCrawler()
        async with runtime.async_playwright() as playwright:
            try:
                crawler.browser_context = await crawler.launch_browser(playwright.chromium, None, None, inspect_only)
                if not inspect_only:
                    _write(output_path, '.yike-login-opened.json', dict(schema_version=SCHEMA, state='OPENED'))
                crawler.context_page = await crawler.browser_context.new_page()
                await crawler.context_page.goto(_HOME)
                if not _official_page(crawler.context_page.url):
                    raise _LoginError('PLATFORM_RESPONSE_CHANGED')
                # Anonymous selfinfo responses are not a prerequisite to showing
                # the user's normal login UI. A visible self link is only a hint;
                # strict API and unique-account checks still follow below.
                # A descendant span saying "我" also appears inside unrelated
                # profile anchors. Match the self link's exact accessible name.
                own_link = crawler.context_page.get_by_role('link', name='我', exact=True)
                count = await own_link.count()
                if count > 1:
                    raise _LoginError('PLATFORM_ACCOUNT_UNVERIFIED')
                if count == 0 or not await own_link.is_visible():
                    if inspect_only:
                        raise _LoginError('PLATFORM_AUTH_REQUIRED')
                    login = runtime.XiaoHongShuLogin(login_type='qrcode',
                        browser_context=crawler.browser_context, context_page=crawler.context_page)
                    await login.begin()
                if not _official_page(crawler.context_page.url):
                    raise _LoginError('PLATFORM_RESPONSE_CHANGED')
                # Create only now so headers use the current post-login context.
                crawler.xhs_client = await crawler.create_xhs_client(None)
                if not await crawler.xhs_client.pong():
                    raise _LoginError('PLATFORM_AUTH_REQUIRED')
                if not _official_page(crawler.context_page.url):
                    raise _LoginError('PLATFORM_RESPONSE_CHANGED')
                own_link = crawler.context_page.get_by_role('link', name='我', exact=True)
                if await own_link.count() != 1 or not await own_link.is_visible():
                    raise _LoginError('PLATFORM_ACCOUNT_UNVERIFIED')
                href = await own_link.get_attribute('href')
                match = _HREF.fullmatch(href) if isinstance(href, str) else None
                if match is None:
                    raise _LoginError('PLATFORM_ACCOUNT_UNVERIFIED')
                account = match.group(1)
                checked_at = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
            finally:
                try:
                    await crawler.close()
                except BaseException:
                    cleanup_failed = True
                    raise
        # Account success cannot be written until both browser and Playwright close.
        return dict(schema_version=SCHEMA, state='AUTHENTICATED', account_public_id=account,
            checked_at=checked_at)
    except (Exception, KeyboardInterrupt) as error:
        return _classified_failure(error, runtime, cleanup_failed)


def main() -> int:
    try:
        inspect = os.environ.get('YIKE_LOGIN_INSPECT_ONLY', '0')
        if inspect not in ('0', '1'): return 1
        output = Path(os.environ['YIKE_LOGIN_OUTPUT_PATH'])
        profile = Path(os.environ['YIKE_PROFILE_PATH'])
        if not output.is_absolute() or not output.is_dir() or not profile.is_absolute() or not profile.is_dir():
            return 1
        result = asyncio.run(login_platform(platform=os.environ.get('YIKE_LOGIN_PLATFORM', 'XIAOHONGSHU'),
            output_path=output, inspect_only=inspect == '1'))
        _write(output, '.yike-login-terminal.json', result)
        return 0
    except (Exception, KeyboardInterrupt):
        # No traceback or raw platform detail on any failure path.
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
