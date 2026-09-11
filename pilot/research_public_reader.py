"""One fixed public index read; not full-site discovery or qualified demand."""
import asyncio
from datetime import UTC, datetime
import hashlib
import json
import re
from urllib.parse import urlsplit

import httpx

from pilot.research_resource_runner import run_resource

ENDPOINT = 'https://www.v2ex.com/api/topics/latest.json'
_BYTE_LIMIT = 1_048_576
_INPUT_SHA = hashlib.sha256(('v2ex-latest-index-v1\0' + ENDPOINT).encode()).hexdigest()


def _invalid(*_):
    raise ValueError('public_source_invalid')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _invalid()
        result[key] = value
    return result


async def _fetch(deadline):
    remaining = min(20, (deadline - datetime.now(UTC)).total_seconds())
    if remaining <= 0:
        _invalid()

    async def read():
        async with httpx.AsyncClient(follow_redirects=False, trust_env=False, timeout=remaining) as client:
            async with client.stream('GET', ENDPOINT, headers={
                    'Accept': 'application/json', 'Accept-Encoding': 'identity',
                    'User-Agent': 'YikeAI/0.2 (public research reader)'}) as response:
                if (response.status_code != 200 or str(response.url) != ENDPOINT
                        or response.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json'
                        or response.headers.get('content-encoding', 'identity').lower() != 'identity'):
                    _invalid()
                length = response.headers.get('content-length')
                if length is not None and (not re.fullmatch(r'[0-9]+', length) or int(length) > _BYTE_LIMIT):
                    _invalid()
                raw = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    if len(raw) + len(chunk) > _BYTE_LIMIT:
                        _invalid()
                    raw.extend(chunk)
                return json.loads(raw.decode('utf-8', errors='strict'),
                                  parse_constant=_invalid, object_pairs_hook=_pairs)
    # One deadline covers DNS/connection/headers/body, not a fresh timeout per chunk.
    return await asyncio.wait_for(read(), timeout=remaining)


def _fetch_index(deadline):
    return asyncio.run(_fetch(deadline))


def _public_topics(payload):
    if type(payload) is not list or len(payload) > 100:
        _invalid()
    topics, seen = [], set()
    observed = datetime.now(UTC)
    for item in payload:
        if type(item) is not dict:
            _invalid()
        identity = item.get('id')
        if type(identity) is not int or not 1 <= identity <= 9_007_199_254_740_991 or identity in seen:
            _invalid()
        seen.add(identity)
        deleted = item.get('deleted', False)
        if type(deleted) not in (int, bool) or deleted not in (0, 1):
            _invalid()
        if deleted:
            continue
        title, content, created, source = (item.get(key) for key in ('title', 'content', 'created', 'url'))
        if (type(title) is not str or len(title) > 1000 or type(content) is not str or len(content) > 60000
                or type(created) is not int or not 0 < created <= observed.timestamp()
                or type(source) is not str or len(source) > 2048 or source != source.strip()):
            _invalid()
        url = urlsplit(source)
        if (url.scheme not in ('http', 'https') or url.hostname != 'www.v2ex.com'
                or url.username or url.password or url.port or url.query
                or url.path != f'/t/{identity}' or url.fragment and not re.fullmatch(r'reply[0-9]+', url.fragment)):
            _invalid()
        topics.append(dict(id=identity, title=title, content=content, created=created,
                           url=f'https://www.v2ex.com/t/{identity}'))
    return dict(source_url=ENDPOINT, sample_kind='LATEST_TOPIC_INDEX', observed_at=observed.isoformat(),
                observed_count=len(topics), topics=topics)


def read_public_index(store, claims, *, task_id, run_id, action_id, fetcher=None):
    fetcher = _fetch_index if fetcher is None else fetcher
    return run_resource(store, claims, task_id=task_id, run_id=run_id, action_id=action_id,
        resource='SOURCE_READ', input_sha256=_INPUT_SHA,
        action=lambda deadline: _public_topics(fetcher(deadline)))
