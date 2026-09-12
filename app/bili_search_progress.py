"""Fixed Bilibili search adapter; private output is tentative until batch commit."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import re

# Loaded by a direct script without putting app/config.py before vendor config.
_spec = spec_from_file_location('yike_native_cursor', Path(__file__).resolve().parents[1] / 'pilot/native_search_cursor.py')
_cursor = module_from_spec(_spec)
_spec.loader.exec_module(_cursor)
checked_cursor, advance_cursor = _cursor.checked_cursor, _cursor.advance_cursor
MARKER = '.yike-native-search-progress.json'
_META = {'query', 'revision', 'base_batch_request_id'}


def checked_input(value, query):
    if type(value) is not dict or set(value) != _META | {'schema_version','adapter_version','cursor'}:
        raise ValueError()
    if value['schema_version'] != 'native-search-progress-v1' or value['adapter_version'] != 'bili-search-items-v1':
        raise ValueError()
    if (type(query) is not str or not 1 <= len(query) <= 80 or not query.isprintable()
            or query != query.strip() or ',' in query or value['query'] != query):
        raise ValueError()
    revision, base = value['revision'], value['base_batch_request_id']
    if type(revision) is not int or not 0 <= revision <= 2147483647:
        raise ValueError()
    if (revision == 0) != (base is None) or (base is not None and (type(base) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',base))):
        raise ValueError()
    return value | {'cursor': checked_cursor(value['cursor'])}


def checked_delta(value, state, max_contents):
    state = checked_input(state, state['query'])
    if type(value) is not dict or set(value) != _META | {'before','after','page_ids','processed_ids','has_more','comments_scope'}:
        raise ValueError()
    if any(value[k] != state[k] for k in _META) or value['before'] != state['cursor'] or value['comments_scope'] != 'BOUNDED_SAMPLE':
        raise ValueError()
    checked_input({k:state[k] for k in ('schema_version','adapter_version')} | {k:value[k] for k in _META} | {'cursor':value['before']},state['query'])
    after = advance_cursor(value['before'],value['page_ids'],value['processed_ids'],value['has_more'])
    if checked_cursor(value['after']) != after or len(value['processed_ids']) > min(5,max_contents):
        raise ValueError()
    return value


@contextmanager
def install_bili_search_progress(module, value, response_error):
    state = checked_input(value, value['query'])
    crawler_type = module.BilibiliCrawler
    original = crawler_type.search

    async def search(crawler):
        config = module.config
        budget = config.CRAWLER_MAX_NOTES_COUNT
        if config.KEYWORDS != state['query'] or type(budget) is not int or not 1 <= budget <= 5 or config.MAX_CONCURRENCY_NUM != 1:
            raise response_error()
        before = state['cursor']
        page = 1 if before['refresh_next'] else before['page']
        module.source_keyword_var.set(state['query'])
        response = await crawler.bili_client.search_video_by_keyword(keyword=state['query'],page=page,page_size=20,
            order=module.SearchOrderType.DEFAULT,pubtime_begin_s=0,pubtime_end_s=0)
        try:
            rows, pages = response['result'], response['numPages']
            if type(rows) is not list or len(rows) > 20 or type(pages) is not int or pages < 0:
                raise ValueError()
            if (rows and page > pages) or (not rows and page < pages): raise ValueError()
            if any(type(row) is not dict or type(row.get('aid')) is not int or row['aid'] <= 0 for row in rows): raise ValueError()
            ids = [str(row['aid']) for row in rows]
            # Validate the complete page even when some items are already consumed.
            checked_cursor(dict(page=page,consumed_ids=ids,refresh_next=False))
        except (KeyError,TypeError,ValueError):
            raise response_error() from None
        selected = [aid for aid in ids if before['refresh_next'] or aid not in before['consumed_ids']][:budget]
        semaphore = asyncio.Semaphore(1)
        for aid in selected:
            video = await crawler.get_video_info_task(aid=int(aid),bvid='',semaphore=semaphore)
            if not isinstance(video,dict) or not isinstance(video.get('View'),dict) or type(video['View'].get('aid')) is not int or video['View']['aid'] != int(aid):
                raise response_error()
            await module.bilibili_store.update_bilibili_video(video)
            await module.bilibili_store.update_up_info(video)
            await crawler.get_bilibili_video(video,semaphore)
        if selected:
            await crawler.batch_get_video_comments([int(aid) for aid in selected])
        delta = {k: state[k] for k in _META} | dict(before=before,
            after=advance_cursor(before,ids,selected,page < pages),page_ids=ids,processed_ids=selected,
            has_more=page < pages,comments_scope='BOUNDED_SAMPLE')
        checked_delta(delta,state,budget)
        (Path(config.SAVE_DATA_PATH) / MARKER).write_text(json.dumps(delta,ensure_ascii=False,separators=(',',':')),encoding='utf-8')

    crawler_type.search = search
    try:
        yield
    finally:
        crawler_type.search = original
