"""Fixed installed-XHS adapter: expected account is checked in the source browser.

Keeps the governed normal CLI, terminal/progress writing and cleanup. Never
performs a separate browser preflight or modifies the installed runtime files.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import re
import runpy
import sys
from urllib.parse import urlsplit


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


def _fixed_arguments(arguments):
    fixed = {'--platform': 'xhs', '--lt': 'qrcode', '--type': 'search',
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
        if not _ACCOUNT.fullmatch(expected): raise ValueError()
        _fixed_arguments(sys.argv[1:])
        runtime = Path.cwd()
        sys.path.insert(0, str(runtime))
        from media_platform.xhs.core import XiaoHongShuCrawler
        from media_platform.xhs.client import XiaoHongShuClient
        from tools.yike_runtime import YikePlatformAuthRequired
        with install_account_guard(XiaoHongShuCrawler, XiaoHongShuClient, YikePlatformAuthRequired, expected):
            runpy.run_path(str(runtime / 'main.py'), run_name='__main__')
        return 0
    except Exception:
        # Normal CLI SystemExit retains governed status/exit pairing. Bootstrap
        # failures never run a fallback collector or disclose import/path details.
        return 48


if __name__ == '__main__':
    raise SystemExit(main())
