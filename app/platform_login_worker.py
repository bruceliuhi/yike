"""Fixed XHS browser login/self check only; launched by the private Windows host.

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
_SELF = "xpath=//a[contains(@href, '/user/profile/') and .//span[text()='我']]"
_HREF = re.compile(r'(?:https://www\.xiaohongshu\.com)?/user/profile/([A-Za-z0-9]{8,32})')
_CODES = {'PLATFORM_AUTH_REQUIRED', 'PLATFORM_PERMISSION_DENIED',
          'PLATFORM_VERIFICATION_REQUIRED', 'PLATFORM_RATE_LIMITED',
          'PLATFORM_RESPONSE_CHANGED', 'COLLECTION_NETWORK_FAILED',
          'COLLECTION_PARSE_FAILED', 'COLLECTION_PROCESS_FAILED'}


class _LoginError(Exception):
    def __init__(self, code): self.code = code


def _failure(code, state='FAILED'):
    return dict(schema_version=SCHEMA, state=state, error_code=code)


def _official_page(url):
    if not isinstance(url, str) or not url.isprintable() or '\\' in url: return False
    parsed = urlsplit(url)
    return parsed.scheme == 'https' and parsed.netloc == 'www.xiaohongshu.com'


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


async def login_xhs(*, output_path: Path) -> dict:
    runtime = None
    cleanup_failed = False
    try:
        runtime = _load_runtime()
        crawler = runtime.XiaoHongShuCrawler()
        async with runtime.async_playwright() as playwright:
            try:
                crawler.browser_context = await crawler.launch_browser(playwright.chromium, None, None, False)
                _write(output_path, '.yike-login-opened.json', dict(schema_version=SCHEMA, state='OPENED'))
                crawler.context_page = await crawler.browser_context.new_page()
                await crawler.context_page.goto(_HOME)
                if not _official_page(crawler.context_page.url):
                    raise _LoginError('PLATFORM_RESPONSE_CHANGED')
                crawler.xhs_client = await crawler.create_xhs_client(None)
                if not await crawler.xhs_client.pong():
                    login = runtime.XiaoHongShuLogin(login_type='qrcode',
                        browser_context=crawler.browser_context, context_page=crawler.context_page)
                    await login.begin()
                    await crawler.xhs_client.update_cookies(crawler.browser_context, urls=crawler.cookie_urls)
                    if not await crawler.xhs_client.pong():
                        raise _LoginError('PLATFORM_AUTH_REQUIRED')
                if not _official_page(crawler.context_page.url):
                    raise _LoginError('PLATFORM_RESPONSE_CHANGED')
                own_link = crawler.context_page.locator(_SELF)
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


def main() -> int:
    try:
        output = Path(os.environ['YIKE_LOGIN_OUTPUT_PATH'])
        profile = Path(os.environ['YIKE_PROFILE_PATH'])
        if not output.is_absolute() or not output.is_dir() or not profile.is_absolute() or not profile.is_dir():
            return 1
        result = asyncio.run(login_xhs(output_path=output))
        _write(output, '.yike-login-terminal.json', result)
        return 0
    except (Exception, KeyboardInterrupt):
        # No traceback or raw platform detail on any failure path.
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
