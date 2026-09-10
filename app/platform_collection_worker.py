"""Fixed three-platform adapter: expected account checked in the source browser.

Keeps the governed normal CLI, terminal/progress writing and cleanup. Never
performs a separate browser preflight or modifies the installed runtime files.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import runpy
import sys
from urllib.parse import urlsplit

if __package__:
    from .platform_login_worker import valid_account, read_douyin_self_account
else:
    # Direct script/spec loading must not put app/config.py ahead of runtime config.
    from importlib.util import spec_from_file_location, module_from_spec
    _login_spec = spec_from_file_location('yike_collection_login', Path(__file__).with_name('platform_login_worker.py'))
    _login = module_from_spec(_login_spec)
    _login_spec.loader.exec_module(_login)
    valid_account, read_douyin_self_account = _login.valid_account, _login.read_douyin_self_account

_ACCOUNT = re.compile(r'[A-Za-z0-9]{8,32}')
_HREF = re.compile(r'(?:https://www\.xiaohongshu\.com)?/user/profile/([A-Za-z0-9]{8,32})')
_SELF = "xpath=//a[contains(@href, '/user/profile/') and .//span[text()='我']]"


async def _check_account(page, expected, auth_error):
    try:
        url = page.url
        if not isinstance(url, str) or not url.isprintable() or '\\' in url: raise ValueError()
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.netloc != 'www.xiaohongshu.com': raise ValueError()
        own = page.locator(_SELF)
        if await own.count() != 1 or not await own.is_visible(): raise ValueError()
        href = await own.get_attribute('href')
        match = _HREF.fullmatch(href) if isinstance(href, str) else None
        if match is None or match.group(1) != expected: raise ValueError()
    except Exception:
        raise auth_error() from None


@contextmanager
def install_account_guard(crawler_type, client_type, auth_error, expected):
    """Wrap only the fixed governed classes; account checks use the same page."""
    if not isinstance(expected, str) or not _ACCOUNT.fullmatch(expected): raise ValueError()
    original_search, original_request = crawler_type.search, client_type.request
    marker = '_yike_expected_collection_account'

    async def request(client, *args, **kwargs):
        account = getattr(client, marker, None)
        if account is not None: await _check_account(client.playwright_page, account, auth_error)
        result = await original_request(client, *args, **kwargs)
        if account is not None: await _check_account(client.playwright_page, account, auth_error)
        return result

    async def search(crawler, *args, **kwargs):
        client = crawler.xhs_client
        if client.playwright_page is not crawler.context_page: raise auth_error()
        await _check_account(crawler.context_page, expected, auth_error)
        if hasattr(client, marker): raise auth_error()
        setattr(client, marker, expected)
        try:
            result = await original_search(crawler, *args, **kwargs)
            # Runs while core.start still owns the open browser context.
            await _check_account(crawler.context_page, expected, auth_error)
            return result
        finally:
            delattr(client, marker)

    crawler_type.search, client_type.request = search, request
    try:
        yield
    finally:
        crawler_type.search, client_type.request = original_search, original_request


class _GuardFailure(Exception):
    def __init__(self, code): self.code = code


async def _bilibili_self_account(page):
    try:
        response = await page.request.get('https://api.bilibili.com/x/web-interface/nav',
            max_redirects=0, timeout=10000)
    except Exception:
        raise _GuardFailure('COLLECTION_NETWORK_FAILED') from None
    try:
        code = {401: 'PLATFORM_AUTH_REQUIRED', 403: 'PLATFORM_PERMISSION_DENIED',
            429: 'PLATFORM_RATE_LIMITED'}.get(response.status)
        if code: raise _GuardFailure(code)
        if response.status != 200: raise ValueError()
        raw = await response.body()
        if len(raw) > 65536: raise ValueError()
        body = json.loads(raw)
        if not isinstance(body, dict) or type(body.get('code')) is not int: raise ValueError()
        code = {-101: 'PLATFORM_AUTH_REQUIRED', -403: 'PLATFORM_PERMISSION_DENIED',
            -352: 'PLATFORM_VERIFICATION_REQUIRED', -412: 'PLATFORM_RATE_LIMITED'}.get(body['code'])
        if code: raise _GuardFailure(code)
        if body['code'] != 0: raise ValueError()
        own = body.get('data')
        mid = own.get('mid') if isinstance(own, dict) else None
        if isinstance(own, dict) and own.get('isLogin') is False:
            raise _GuardFailure('PLATFORM_AUTH_REQUIRED')
        if not isinstance(own, dict) or own.get('isLogin') is not True or type(mid) not in (int, str): raise ValueError()
        account = str(mid)
        if not valid_account('BILIBILI', account): raise ValueError()
        return account
    except ValueError:
        raise _GuardFailure('PLATFORM_RESPONSE_CHANGED') from None
    finally:
        await response.dispose()


@contextmanager
def install_video_account_guard(crawler_type, client_type, auth_error, expected, platform, *, error_types=None):
    if platform not in ('BILIBILI', 'DOUYIN') or not valid_account(platform, expected): raise ValueError()
    original_search, original_request = crawler_type.search, client_type.request
    marker = '_yike_collection_account_guard'

    async def request(client, *args, **kwargs):
        guard = getattr(client, marker, None)
        if guard is not None: await guard()
        result = await original_request(client, *args, **kwargs)
        if guard is not None: await guard()
        return result

    async def search(crawler, *args, **kwargs):
        client = crawler.bili_client if platform == 'BILIBILI' else crawler.dy_client
        if client.playwright_page is not crawler.context_page or hasattr(client, marker): raise auth_error()
        own_page = None
        failed = None
        async def guard():
            nonlocal failed
            if failed: raise failed()
            try:
                account = (await _bilibili_self_account(crawler.context_page) if platform == 'BILIBILI'
                    else await read_douyin_self_account(own_page))
                if account != expected: raise ValueError()
            except Exception as error:
                # A crawler may catch request exceptions; never erase a mismatch.
                failed = (error_types or {}).get(error.code, auth_error) if isinstance(error, _GuardFailure) else auth_error
                raise failed() from None
        try:
            if platform == 'DOUYIN': own_page = await crawler.browser_context.new_page()
            await guard()
            setattr(client, marker, guard)
            result = await original_search(crawler, *args, **kwargs)
            await guard()
            return result
        finally:
            if hasattr(client, marker): delattr(client, marker)
            if own_page is not None: await own_page.close()

    crawler_type.search, client_type.request = search, request
    try:
        yield
    finally:
        crawler_type.search, client_type.request = original_search, original_request


def _fixed_arguments(arguments, platform='XIAOHONGSHU'):
    code = {'XIAOHONGSHU': 'xhs', 'BILIBILI': 'bili', 'DOUYIN': 'dy'}.get(platform)
    if code is None: raise ValueError()
    fixed = {'--platform': code, '--lt': 'qrcode', '--type': 'search',
        '--get_comment': 'yes', '--get_sub_comment': 'yes', '--headless': 'no',
        '--save_data_option': 'jsonl', '--max_concurrency_num': '1', '--enable_ip_proxy': 'no'}
    allowed = set(fixed) | {'--keywords', '--save_data_path', '--crawler_max_notes_count', '--max_comments_count_singlenotes'}
    values = {}
    index = 0
    while index < len(arguments):
        option = arguments[index]
        if '=' in option:
            key, value = option.split('=', 1)
        else:
            key = option
            index += 1
            if index >= len(arguments): raise ValueError()
            value = arguments[index]
        if key not in allowed or key in values: raise ValueError()
        values[key] = value
        index += 1
    if set(values) != allowed or any(values[key] != value for key, value in fixed.items()): raise ValueError()
    query = values['--keywords']
    if not query.isprintable() or query != query.strip() or ',' in query or not 1 <= len(query) <= 80: raise ValueError()
    output = Path(values['--save_data_path'])
    if not output.is_absolute() or not output.is_dir(): raise ValueError()
    for key, maximum in (('--crawler_max_notes_count', 5), ('--max_comments_count_singlenotes', 100)):
        if not re.fullmatch(r'[1-9][0-9]*', values[key]) or int(values[key]) > maximum: raise ValueError()


def main():
    try:
        expected = os.environ.get('YIKE_EXPECTED_ACCOUNT_PUBLIC_ID', '')
        platform = os.environ.get('YIKE_COLLECTION_PLATFORM', 'XIAOHONGSHU')
        if not valid_account(platform, expected): raise ValueError()
        _fixed_arguments(sys.argv[1:], platform)
        runtime = Path.cwd()
        sys.path.insert(0, str(runtime))
        from tools.yike_runtime import YikePlatformAuthRequired, _EXPLICIT_TERMINALS
        error_types = {code: kind for kind, (code, _) in _EXPLICIT_TERMINALS}
        if platform == 'XIAOHONGSHU':
            from media_platform.xhs.core import XiaoHongShuCrawler
            from media_platform.xhs.client import XiaoHongShuClient
            guard = install_account_guard(XiaoHongShuCrawler, XiaoHongShuClient, YikePlatformAuthRequired, expected)
        elif platform == 'BILIBILI':
            from media_platform.bilibili.core import BilibiliCrawler
            from media_platform.bilibili.client import BilibiliClient
            guard = install_video_account_guard(BilibiliCrawler, BilibiliClient, YikePlatformAuthRequired, expected, platform, error_types=error_types)
        else:
            from media_platform.douyin.core import DouYinCrawler
            from media_platform.douyin.client import DouYinClient
            guard = install_video_account_guard(DouYinCrawler, DouYinClient, YikePlatformAuthRequired, expected, platform, error_types=error_types)
        with guard:
            runpy.run_path(str(runtime / 'main.py'), run_name='__main__')
        return 0
    except Exception:
        # Normal CLI SystemExit retains governed status/exit pairing. Bootstrap
        # failures never run a fallback collector or disclose import/path details.
        return 48


if __name__ == '__main__':
    raise SystemExit(main())
