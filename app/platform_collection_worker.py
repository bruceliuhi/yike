"""Fixed three-platform adapter: expected account checked in the source browser.

Keeps the governed normal CLI, terminal/progress writing and cleanup. Never
performs a separate browser preflight or modifies the installed runtime files.
"""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
import json
import os
from pathlib import Path
import re
import runpy
import sys
from urllib.parse import urlsplit

if __package__:
    from .bili_search_progress import install_bili_search_progress
    from .platform_login_worker import valid_account, read_douyin_self_account, read_zhihu_self_account
    from pilot.native_collection_links import parse_native_collection_link, validate_bili_collection_target
else:
    # Direct script/spec loading must not put app/config.py ahead of runtime config.
    from importlib.util import spec_from_file_location, module_from_spec
    _login_spec = spec_from_file_location('yike_collection_login', Path(__file__).with_name('platform_login_worker.py'))
    _login = module_from_spec(_login_spec)
    _login_spec.loader.exec_module(_login)
    valid_account, read_douyin_self_account = _login.valid_account, _login.read_douyin_self_account
    read_zhihu_self_account = _login.read_zhihu_self_account
    _links_spec = spec_from_file_location('yike_collection_links', Path(__file__).resolve().parent.parent / 'pilot' / 'native_collection_links.py')
    _links = module_from_spec(_links_spec)
    _links_spec.loader.exec_module(_links)
    parse_native_collection_link = _links.parse_native_collection_link
    validate_bili_collection_target = _links.validate_bili_collection_target
    _progress_spec = spec_from_file_location('yike_bili_search_progress', Path(__file__).with_name('bili_search_progress.py'))
    _progress = module_from_spec(_progress_spec)
    _progress_spec.loader.exec_module(_progress)
    install_bili_search_progress = _progress.install_bili_search_progress

_ACCOUNT = re.compile(r'[A-Za-z0-9]{8,32}')
_HREF = re.compile(r'(?:https://www\.xiaohongshu\.com)?/user/profile/([A-Za-z0-9]{8,32})')


async def _check_account(page, expected, auth_error):
    try:
        url = page.url
        if not isinstance(url, str) or not url.isprintable() or '\\' in url: raise ValueError()
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.netloc != 'www.xiaohongshu.com': raise ValueError()
        # Use the same exact self navigation as login, not an author's nested
        # span that happens to say 我. All URL, uniqueness and account checks stay.
        own = page.get_by_role('link', name='我', exact=True)
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
def install_video_account_guard(crawler_type, client_type, auth_error, expected, platform, *, error_types=None, entry_method='search'):
    if platform not in ('BILIBILI', 'DOUYIN', 'ZHIHU') or not valid_account(platform, expected): raise ValueError()
    if entry_method not in ('search', 'collect_links') or (entry_method != 'search' and platform != 'BILIBILI'): raise ValueError()
    original_search, original_request = getattr(crawler_type, entry_method), client_type.request
    marker = '_yike_collection_account_guard'

    async def request(client, *args, **kwargs):
        guard = getattr(client, marker, None)
        if guard is not None: await guard()
        try:
            result = await original_request(client, *args, **kwargs)
        except Exception as error:
            if guard is not None: guard.remember_failure(error)
            raise
        if guard is not None: await guard()
        return result

    async def search(crawler, *args, **kwargs):
        client = getattr(crawler, {'BILIBILI':'bili_client','DOUYIN':'dy_client','ZHIHU':'zhihu_client'}[platform])
        if client.playwright_page is not crawler.context_page or hasattr(client, marker): raise auth_error()
        own_page = None
        failed = None
        def remember_failure(error):
            nonlocal failed
            for kind in (auth_error, *(error_types or {}).values()):
                if isinstance(error, kind):
                    failed = failed or kind
                    break
        async def guard():
            nonlocal failed
            if failed: raise failed()
            try:
                account = (await _bilibili_self_account(crawler.context_page) if platform == 'BILIBILI'
                    else await read_zhihu_self_account(crawler.context_page) if platform == 'ZHIHU'
                    else await read_douyin_self_account(own_page))
                if account != expected: raise ValueError()
            except Exception as error:
                # A crawler may catch request exceptions; never erase a mismatch.
                failed = (error_types or {}).get(getattr(error, 'code', None), auth_error)
                raise failed() from None
        guard.remember_failure = remember_failure
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

    setattr(crawler_type, entry_method, search)
    client_type.request = request
    try:
        yield
    finally:
        setattr(crawler_type, entry_method, original_search)
        client_type.request = original_request


def install_zhihu_account_guard(crawler_type, client_type, auth_error, expected, *, error_types=None):
    return install_video_account_guard(crawler_type,client_type,auth_error,expected,'ZHIHU',error_types=error_types)


def _fixed_arguments(arguments, platform='XIAOHONGSHU'):
    code = {'XIAOHONGSHU': 'xhs', 'BILIBILI': 'bili', 'DOUYIN': 'dy', 'ZHIHU':'zhihu'}.get(platform)
    if code is None: raise ValueError()
    fixed = {'--platform': code, '--lt': 'qrcode',
        '--get_comment': 'yes', '--get_sub_comment': 'yes', '--headless': 'no',
        '--save_data_option': 'jsonl', '--max_concurrency_num': '1', '--enable_ip_proxy': 'no'}
    common = set(fixed) | {'--type', '--save_data_path', '--crawler_max_notes_count', '--max_comments_count_singlenotes'}
    allowed = common | {'--keywords', '--specified_id', '--creator_id'}
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
    mode = values.get('--type')
    selector = {'search': '--keywords', 'detail': '--specified_id', 'creator': '--creator_id'}.get(mode)
    if selector is None or set(values) != common | {selector} or any(values[key] != value for key, value in fixed.items()): raise ValueError()
    if mode == 'search':
        query = values[selector]
        if not query.isprintable() or query != query.strip() or ',' in query or not 1 <= len(query) <= 80: raise ValueError()
    else:
        target = validate_bili_collection_target(parse_native_collection_link(values[selector]))
        if platform != 'BILIBILI' or target['kind'] != mode or target['canonical_url'] != values[selector]: raise ValueError()
    output = Path(values['--save_data_path'])
    if not output.is_absolute() or not output.is_dir(): raise ValueError()
    for key, maximum in (('--crawler_max_notes_count', 5), ('--max_comments_count_singlenotes', 100)):
        pattern = r'(?:0|[1-9][0-9]*)' if (mode != 'search' or platform == 'XIAOHONGSHU') and key == '--max_comments_count_singlenotes' else r'[1-9][0-9]*'
        if not re.fullmatch(pattern, values[key]) or int(values[key]) > maximum: raise ValueError()
    if mode != 'search' or platform == 'XIAOHONGSHU':
        contents = int(values['--crawler_max_notes_count'])
        comments = int(values['--max_comments_count_singlenotes'])
        if (mode == 'detail' and contents != 1) or contents * (1 + comments) > 100: raise ValueError()
    return mode


def main():
    try:
        expected = os.environ.get('YIKE_EXPECTED_ACCOUNT_PUBLIC_ID', '')
        platform = os.environ.get('YIKE_COLLECTION_PLATFORM', 'XIAOHONGSHU')
        if not valid_account(platform, expected): raise ValueError()
        mode = _fixed_arguments(sys.argv[1:], platform)
        progress = os.environ.get('YIKE_NATIVE_SEARCH_PROGRESS')
        if progress is not None and (platform != 'BILIBILI' or mode != 'search' or len(progress.encode('utf-8')) > 4096): raise ValueError()
        runtime = Path.cwd()
        sys.path.insert(0, str(runtime))
        from tools.yike_runtime import YikePlatformAuthRequired, _EXPLICIT_TERMINALS
        error_types = {code: kind for kind, (code, _) in _EXPLICIT_TERMINALS}
        if platform == 'XIAOHONGSHU':
            import config
            from media_platform.xhs.field import SearchSortType
            from media_platform.xhs.core import XiaoHongShuCrawler
            from media_platform.xhs.client import XiaoHongShuClient
            # This worker process searches fresh demand; leave the pinned
            # runtime files and other platform defaults unchanged.
            config.SORT_TYPE = SearchSortType.LATEST.value
            guard = install_account_guard(XiaoHongShuCrawler, XiaoHongShuClient, YikePlatformAuthRequired, expected)
        elif platform == 'BILIBILI':
            from media_platform.bilibili.core import BilibiliCrawler
            from media_platform.bilibili.client import BilibiliClient
            guard = install_video_account_guard(BilibiliCrawler, BilibiliClient, YikePlatformAuthRequired, expected, platform, error_types=error_types,
                entry_method='search' if mode == 'search' else 'collect_links')
        elif platform == 'ZHIHU':
            from media_platform.zhihu.core import ZhihuCrawler
            from media_platform.zhihu.client import ZhiHuClient
            guard = install_zhihu_account_guard(ZhihuCrawler,ZhiHuClient,YikePlatformAuthRequired,expected,error_types=error_types)
        else:
            from media_platform.douyin.core import DouYinCrawler
            from media_platform.douyin.client import DouYinClient
            guard = install_video_account_guard(DouYinCrawler, DouYinClient, YikePlatformAuthRequired, expected, platform, error_types=error_types)
        with ExitStack() as stack:
            if progress is not None:
                from media_platform.bilibili import core
                from tools.yike_runtime import YikePlatformResponseChanged
                # Install first: the account guard must wrap the new search too.
                stack.enter_context(install_bili_search_progress(core,json.loads(progress),YikePlatformResponseChanged))
            stack.enter_context(guard)
            runpy.run_path(str(runtime / 'main.py'), run_name='__main__')
        return 0
    except Exception:
        # Normal CLI SystemExit retains governed status/exit pairing. Bootstrap
        # failures never run a fallback collector or disclose import/path details.
        return 48


if __name__ == '__main__':
    raise SystemExit(main())
