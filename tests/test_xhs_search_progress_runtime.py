import asyncio
import json
import sys
import types
from pathlib import Path

from app.xhs_search_progress import MARKER, checked_delta, checked_input, install_xhs_search_progress


def state(**overrides):
    value = {
        "schema_version": "native-search-progress-v1",
        "adapter_version": "xhs-search-items-v1",
        "query": "采购线索",
        "revision": 0,
        "base_batch_request_id": None,
        "cursor": {"page": 1, "search_id": "search-1", "consumed_ids": [], "refresh_next": False},
    }
    value.update(overrides)
    return value


def test_xhs_progress_contract_rejects_missing_search_id():
    with __import__("pytest").raises(ValueError):
        checked_input(state(cursor={"page": 1, "consumed_ids": [], "refresh_next": False}), "采购线索")


def test_xhs_adapter_replays_page_and_writes_verified_delta(tmp_path, monkeypatch):
    field = types.ModuleType("media_platform.xhs.field")
    class Sort:
        GENERAL = "general"
    field.SearchSortType = Sort
    monkeypatch.setitem(sys.modules, "media_platform", types.ModuleType("media_platform"))
    monkeypatch.setitem(sys.modules, "media_platform.xhs", types.ModuleType("media_platform.xhs"))
    monkeypatch.setitem(sys.modules, "media_platform.xhs.field", field)

    class Config:
        KEYWORDS = "采购线索"
        CRAWLER_MAX_NOTES_COUNT = 2
        MAX_CONCURRENCY_NUM = 1
        SORT_TYPE = ""
        SAVE_DATA_PATH = str(tmp_path)

    class Store:
        def __init__(self): self.notes = []
        async def update_xhs_note(self, note): self.notes.append(note)

    class Client:
        async def get_note_by_keyword(self, **kwargs):
            assert kwargs["search_id"] == "search-1" and kwargs["page"] == 1
            return {"items": [
                {"id": "note-1", "xsec_source": "pc_search", "xsec_token": "token-1"},
                {"id": "note-2", "xsec_source": "pc_search", "xsec_token": "token-2"},
            ], "has_more": True}

    class Crawler:
        def __init__(self): self.xhs_client = Client(); self.comments = []
        async def get_note_detail_async_task(self, *, note_id, xsec_source, xsec_token, semaphore):
            return {"note_id": note_id}
        async def get_notice_media(self, detail): return None
        async def batch_get_note_comments(self, note_ids, tokens): self.comments.append((note_ids, tokens))
    async def original_search(self): return None
    Crawler.search = original_search

    module = types.SimpleNamespace(
        XiaoHongShuCrawler=Crawler, config=Config, xhs_store=Store(),
        source_keyword_var=types.SimpleNamespace(set=lambda value: None),
    )
    input_state = state()
    with install_xhs_search_progress(module, input_state, RuntimeError):
        crawler = Crawler()
        asyncio.run(crawler.search())
    marker = json.loads(Path(tmp_path, MARKER).read_text())
    assert marker["query"] == "采购线索"
    assert marker["page_ids"] == ["note-1", "note-2"]
    assert marker["processed_ids"] == ["note-1", "note-2"]
    assert marker["after"] == {"page": 2, "search_id": "search-1", "consumed_ids": [], "refresh_next": True}


def test_xhs_delta_cannot_change_search_id():
    before = state()
    delta = {
        "schema_version": before["schema_version"], "adapter_version": before["adapter_version"],
        "query": before["query"], "revision": before["revision"],
        "base_batch_request_id": before["base_batch_request_id"], "before": before["cursor"],
        "after": {"page": 1, "search_id": "other", "consumed_ids": [], "refresh_next": True},
        "page_ids": ["note-1"], "processed_ids": ["note-1"], "has_more": False,
        "comments_scope": "BOUNDED_SAMPLE",
    }
    try:
        checked_delta(delta, before, 2)
    except ValueError:
        return
    raise AssertionError("search id mutation must be rejected")
