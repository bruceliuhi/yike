"""Fixed Xiaohongshu search adapter with a committed page cursor.

The cursor is deliberately separate from the normal crawler configuration:
the service owns the search id and page, while this adapter only proves that
the returned page and the bounded detail reads advance that exact cursor.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import re

_spec = spec_from_file_location(
    "yike_native_cursor",
    Path(__file__).resolve().parents[1] / "pilot/native_search_cursor.py",
)
_cursor = module_from_spec(_spec)
_spec.loader.exec_module(_cursor)
checked_cursor, advance_cursor = _cursor.checked_cursor, _cursor.advance_cursor

MARKER = ".yike-native-search-progress.json"
_META = {"query", "revision", "base_batch_request_id"}
_ID = re.compile(r"[A-Za-z0-9_-]{1,64}", re.ASCII)
_BASE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", re.ASCII)


def checked_input(value, query):
    if type(value) is not dict or set(value) != _META | {
        "schema_version", "adapter_version", "cursor"
    }:
        raise ValueError()
    if value["schema_version"] != "native-search-progress-v1" or value[
        "adapter_version"
    ] != "xhs-search-items-v1":
        raise ValueError()
    if (
        type(query) is not str
        or not 1 <= len(query) <= 80
        or query != query.strip()
        or not query.isprintable()
        or "," in query
        or value["query"] != query
    ):
        raise ValueError()
    revision, base = value["revision"], value["base_batch_request_id"]
    if type(revision) is not int or not 0 <= revision <= 2_147_483_647:
        raise ValueError()
    if (revision == 0) != (base is None) or (
        base is not None and (type(base) is not str or _BASE.fullmatch(base) is None)
    ):
        raise ValueError()
    cursor = checked_cursor(value["cursor"])
    if set(cursor) != {"page", "search_id", "consumed_ids", "refresh_next"}:
        raise ValueError()
    return value | {"cursor": cursor}


def checked_delta(value, state, max_contents):
    state = checked_input(state, state["query"])
    if type(value) is not dict or set(value) != _META | {
        "before", "after", "page_ids", "processed_ids", "has_more", "comments_scope"
    }:
        raise ValueError()
    if (
        any(value[key] != state[key] for key in _META)
        or value["before"] != state["cursor"]
        or value["comments_scope"] != "BOUNDED_SAMPLE"
    ):
        raise ValueError()
    checked_input(
        {key: state[key] for key in ("schema_version", "adapter_version")}
        | {key: value[key] for key in _META}
        | {"cursor": value["before"]},
        state["query"],
    )
    after = advance_cursor(
        value["before"], value["page_ids"], value["processed_ids"], value["has_more"]
    )
    if checked_cursor(value["after"]) != after or len(value["processed_ids"]) > min(
        5, max_contents
    ):
        raise ValueError()
    return value


@contextmanager
def install_xhs_search_progress(module, value, response_error):
    state = checked_input(value, value["query"])
    crawler_type = module.XiaoHongShuCrawler
    original = crawler_type.search

    async def search(crawler):
        config = module.config
        budget = config.CRAWLER_MAX_NOTES_COUNT
        if (
            config.KEYWORDS != state["query"]
            or type(budget) is not int
            or not 1 <= budget <= 5
            or config.MAX_CONCURRENCY_NUM != 1
        ):
            raise response_error()
        before = state["cursor"]
        page = before["page"]
        search_id = before["search_id"]
        module.source_keyword_var.set(state["query"])
        try:
            from media_platform.xhs.field import SearchSortType

            sort = SearchSortType(config.SORT_TYPE) if config.SORT_TYPE else SearchSortType.GENERAL
            response = await crawler.xhs_client.get_note_by_keyword(
                keyword=state["query"],
                search_id=search_id,
                page=page,
                page_size=20,
                sort=sort,
            )
            if (
                type(response) is not dict
                or type(response.get("items")) is not list
                or len(response["items"]) > 20
                or type(response.get("has_more")) is not bool
            ):
                raise ValueError()
            ids, selected = [], []
            for item in response["items"]:
                if type(item) is not dict:
                    raise ValueError()
                if item.get("model_type") in {"rec_query", "hot_query"}:
                    continue
                note_id = item.get("id")
                if type(note_id) is not str or _ID.fullmatch(note_id) is None or note_id in ids:
                    raise ValueError()
                ids.append(note_id)
                if (before["refresh_next"] or note_id not in before["consumed_ids"]) and len(selected) < budget:
                    selected.append(item)
            note_ids, tokens = [], []
            for item in selected:
                note_id = item["id"]
                detail = await crawler.get_note_detail_async_task(
                    note_id=note_id,
                    xsec_source=item.get("xsec_source", "pc_search"),
                    xsec_token=item.get("xsec_token", ""),
                    semaphore=asyncio.Semaphore(1),
                )
                if type(detail) is not dict or detail.get("note_id") != note_id:
                    raise ValueError()
                await module.xhs_store.update_xhs_note(detail)
                await crawler.get_notice_media(detail)
                note_ids.append(note_id)
                tokens.append(item.get("xsec_token", ""))
            await crawler.batch_get_note_comments(note_ids, tokens)
            delta = {
                key: state[key] for key in _META
            } | {
                "before": before,
                "after": advance_cursor(before, ids, [item["id"] for item in selected], response["has_more"]),
                "page_ids": ids,
                "processed_ids": [item["id"] for item in selected],
                "has_more": response["has_more"],
                "comments_scope": "BOUNDED_SAMPLE",
            }
            checked_delta(delta, state, budget)
            (Path(config.SAVE_DATA_PATH) / MARKER).write_text(
                json.dumps(delta, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
        except response_error:
            raise
        except Exception:
            raise response_error() from None

    crawler_type.search = search
    try:
        yield
    finally:
        crawler_type.search = original


__all__ = ["MARKER", "checked_input", "checked_delta", "install_xhs_search_progress"]
