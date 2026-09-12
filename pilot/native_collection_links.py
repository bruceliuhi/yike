"""Offline native-link planning. Recognition grants no collection authority."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote, unquote_plus


_PLATFORMS = ('BILIBILI', 'DOUYIN', 'XIAOHONGSHU', 'ZHIHU')
_URL = re.compile(r'https://([a-z.]+)(/[^?#]*)(?:\?([^#]*))?')
_NUMBER = r'[1-9][0-9]{0,19}'
_SLUG = r'[A-Za-z0-9_-]{1,128}'
_XHS_ID = r'[0-9a-f]{24}'
_SENSITIVE = ('token', 'cookie', 'session', 'authorization', 'signature', 'password', 'secret')
# Route matching is performed on the raw path, before any URL normalization.
_ROUTES = (
    ('www.bilibili.com', rf'/video/(BV[A-Za-z0-9]{{10}})', 'BILIBILI', 'detail', ''),
    ('space.bilibili.com', rf'/({_NUMBER})', 'BILIBILI', 'creator', ''),
    ('www.douyin.com', rf'/video/({_NUMBER})', 'DOUYIN', 'detail', ''),
    ('www.douyin.com', rf'/user/({_SLUG})', 'DOUYIN', 'creator', ''),
    ('www.xiaohongshu.com', rf'/explore/({_XHS_ID})', 'XIAOHONGSHU', 'detail', ''),
    ('www.xiaohongshu.com', rf'/user/profile/({_XHS_ID})', 'XIAOHONGSHU', 'creator', ''),
    ('www.zhihu.com', rf'/question/{_NUMBER}/answer/({_NUMBER})', 'ZHIHU', 'detail', 'answer:'),
    ('www.zhihu.com', rf'/p/({_NUMBER})', 'ZHIHU', 'detail', 'article:'),
    ('zhuanlan.zhihu.com', rf'/p/({_NUMBER})', 'ZHIHU', 'detail', 'article:'),
    ('www.zhihu.com', rf'/zvideo/({_NUMBER})', 'ZHIHU', 'detail', 'zvideo:'),
    ('www.zhihu.com', rf'/people/({_SLUG})', 'ZHIHU', 'creator', ''),
)


def _invalid():
    raise ValueError('INVALID_NATIVE_COLLECTION_LINK')


def _decode_query(value: str) -> str:
    if re.search(r'%(?![0-9a-fA-F]{2})', value):
        _invalid()
    try:
        decoded = unquote_plus(value, encoding='utf-8', errors='strict')
    except UnicodeError:
        _invalid()
    if any(ch.isspace() or ch == '\\' or unicodedata.category(ch) in ('Cc', 'Cf', 'Cs', 'Zl', 'Zp')
           for ch in decoded):
        _invalid()
    return decoded


def parse_native_collection_link(value: object) -> dict:
    """Return a fixed target descriptor, or a sanitized error without input data."""
    if type(value) is not str or not 1 <= len(value) <= 2048 or any(
            not 33 <= ord(ch) <= 126 or ch == '\\' for ch in value):
        _invalid()
    match = _URL.fullmatch(value)
    if not match:
        _invalid()
    host, path, raw_query = match.groups()
    target = None
    for domain, pattern, platform, kind, prefix in _ROUTES:
        route = re.fullmatch(pattern + '/?', path) if host == domain else None
        if route:
            target = dict(platform=platform, kind=kind, external_id=prefix + route[1])
            if prefix == 'article:':
                host = 'zhuanlan.zhihu.com'
            break
    if target is None:
        _invalid()
    query = {}
    for pair in raw_query.split('&') if raw_query else ():
        if not pair or '=' not in pair:
            _invalid()
        key, parameter = (_decode_query(part) for part in pair.split('=', 1))
        lowered = key.lower()
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', key) or lowered in query or lowered == 'modal_id':
            _invalid()
        if any(marker in lowered for marker in _SENSITIVE) and not (
                target['platform'] == 'XIAOHONGSHU' and key == 'xsec_token'):
            _invalid()
        # The key's exact spelling is required for the public XHS pair.
        if lowered == 'xsec_source' and (key != lowered or target['platform'] != 'XIAOHONGSHU'):
            _invalid()
        query[lowered] = parameter
    token, source = query.get('xsec_token'), query.get('xsec_source')
    canonical = f'https://{host}{path.rstrip("/")}'
    if token is not None or source is not None:
        if (token is None or source is None or not re.fullmatch(r'[A-Za-z0-9_+/=-]{1,1024}', token)
                or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', source)):
            _invalid()
        canonical += '?xsec_token=' + quote(token, safe='') + '&xsec_source=' + source
    return target | {'canonical_url': canonical}


def plan_native_collection_links(platforms: object, links: object) -> tuple[dict, ...]:
    """Plan every selected platform, rejecting duplicates rather than truncating."""
    try:
        if (type(platforms) not in (list, tuple) or not 1 <= len(platforms) <= 4
                or any(type(platform) is not str or platform not in _PLATFORMS for platform in platforms)
                or len(set(platforms)) != len(platforms)
                or type(links) not in (list, tuple) or not 1 <= len(links) <= 100):
            raise ValueError()
        targets = tuple(parse_native_collection_link(value) for value in links)
        if set(target['platform'] for target in targets) != set(platforms):
            raise ValueError()
        identities = {(target['platform'], target['kind'], target['external_id']) for target in targets}
        if len(identities) != len(targets):
            raise ValueError()
        return targets
    except ValueError:
        raise ValueError('INVALID_NATIVE_LINK_SCOPE') from None
