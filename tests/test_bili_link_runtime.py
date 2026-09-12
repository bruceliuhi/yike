"""Offline behavior tests for the pinned, patched Bilibili link runtime.

The fixture reconstructs the governed source from the fixed upstream commit and
the repository patch chain. It never downloads dependencies, opens a browser,
or contacts Bilibili.
"""

import ast
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    upstream = Path(
        os.environ.get(
            "YIKE_BILI_UPSTREAM_SOURCE",
            "/tmp/yike-native-links-vendor.l75kHY/runtime",
        )
    )
    if not upstream.exists():
        pytest.skip("requires a local pinned MediaCrawler checkout; never downloads")

    lock = json.loads((ROOT / "vendor/mediacrawler.lock").read_text(encoding="utf-8"))
    assert (
        subprocess.check_output(
            ["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True
        ).strip()
        == lock["commit"]
    )

    target = tmp_path_factory.mktemp("bili-links") / "source"
    subprocess.run(
        ["git", "clone", "-q", "--no-hardlinks", "--no-checkout", str(upstream), str(target)],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(target), "-c", "core.autocrlf=false", "checkout", "-q", lock["commit"]],
        check=True,
    )
    for patch in lock["patches"]:
        subprocess.run(
            [
                "git",
                "-C",
                str(target),
                "-c",
                "core.autocrlf=false",
                "apply",
                "--unidiff-zero",
                str(ROOT / patch["path"]),
            ],
            check=True,
        )
    return target


@pytest.fixture
def runtime(source):
    namespace = {
        "__name__": "offline_bili_links",
        "asyncio": asyncio,
        "Path": Path,
        "json": json,
    }
    exec(
        compile(
            (source / "tools/yike_runtime.py").read_text(encoding="utf-8"),
            "tools/yike_runtime.py",
            "exec",
        ),
        namespace,
    )
    namespace.update(
        config=NS(
            CRAWLER_TYPE="detail",
            BILI_SPECIFIED_ID_LIST=["https://www.bilibili.com/video/BV1abc123xyz"],
            BILI_CREATOR_ID_LIST=["https://space.bilibili.com/42"],
            CRAWLER_MAX_NOTES_COUNT=3,
            CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES=2,
            ENABLE_GET_COMMENTS=True,
            ENABLE_GET_SUB_COMMENTS=True,
            CRAWLER_MAX_SLEEP_SEC=0,
            SAVE_DATA_PATH="",
            PLATFORM="bili",
        ),
        parse_video_info_from_url=lambda value: NS(
            video_id=value.rstrip("/").rsplit("/", 1)[-1]
        ),
        parse_creator_info_from_url=lambda value: NS(
            creator_id=value.rstrip("/").rsplit("/", 1)[-1]
        ),
        bilibili_store=NS(),
        source_keyword_var=NS(get=lambda: "offline-link"),
        anonymize_user_id=lambda value: "anonymous-hash",
        mask_nickname=lambda value: "masked",
        utils=NS(
            logger=NS(
                info=lambda *args: None,
                error=lambda *args: None,
                warning=lambda *args: None,
            ),
            get_current_timestamp=lambda: 1789000000000,
        ),
    )

    def load(path, *, cls=None, names=None):
        tree = ast.parse((source / path).read_text(encoding="utf-8"))
        nodes = (
            next(node.body for node in tree.body if isinstance(node, ast.ClassDef) and node.name == cls)
            if cls
            else tree.body
        )
        nodes = [
            node
            for node in nodes
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and (names is None or node.name in names)
        ]
        module = ast.Module(
            body=[
                ast.ImportFrom(
                    module="__future__",
                    names=[ast.alias(name="annotations")],
                    level=0,
                ),
                *nodes,
            ],
            type_ignores=[],
        )
        loaded = dict(namespace)
        exec(compile(ast.fix_missing_locations(module), path, "exec"), loaded)
        if cls:
            return type(cls, (), {node.name: loaded[node.name] for node in nodes})
        return loaded

    return NS(g=namespace, load=load)


def run(awaitable):
    return asyncio.run(awaitable)


def _view(bvid, aid, owner_mid=42):
    return {
        "View": {
            "bvid": bvid,
            "aid": aid,
            "owner": {"mid": owner_mid, "name": "masked-by-store"},
            "stat": {},
        }
    }


@pytest.mark.parametrize("mode", ["detail", "creator"])
def test_link_store_preserves_description_tail_beyond_search_preview(runtime, mode):
    critical_tail = "预算三十万，要求十月十五日前交付"
    description = "前置背景" * 130 + critical_tail
    item = _view("BV1abc123xyz", 101)
    item["View"].update(
        title="长视频说明",
        desc=description,
        pubdate=1789000000,
        pic="https://offline.invalid/cover",
    )
    sink = NS(store_content=AsyncMock())
    runtime.g["BiliStoreFactory"] = NS(create_store=lambda: sink)
    runtime.g["config"].CRAWLER_TYPE = mode
    loaded = runtime.load(
        "store/bilibili/__init__.py", names=["update_bilibili_video"]
    )

    run(loaded["update_bilibili_video"](item))

    saved = sink.store_content.await_args.kwargs["content_item"]
    assert saved["desc"] == description
    assert saved["desc"].endswith(critical_tail)


def test_search_store_keeps_existing_500_character_description_preview(runtime):
    critical_tail = "搜索模式尾部不应进入旧摘要"
    description = "搜索背景" * 130 + critical_tail
    item = _view("BV1abc123xyz", 101)
    item["View"].update(title="搜索结果", desc=description, pubdate=1789000000, pic="")
    sink = NS(store_content=AsyncMock())
    runtime.g["BiliStoreFactory"] = NS(create_store=lambda: sink)
    runtime.g["config"].CRAWLER_TYPE = "search"
    loaded = runtime.load(
        "store/bilibili/__init__.py", names=["update_bilibili_video"]
    )

    run(loaded["update_bilibili_video"](item))

    saved = sink.store_content.await_args.kwargs["content_item"]
    assert saved["desc"] == description[:500]
    assert len(saved["desc"]) == 500
    assert critical_tail not in saved["desc"]


def test_detail_saves_only_the_requested_view_and_zero_comments_make_no_request(runtime):
    stored = AsyncMock()
    runtime.g["bilibili_store"] = NS(
        update_bilibili_video=stored,
        batch_update_bilibili_video_comments=AsyncMock(),
    )
    runtime.g["config"].CRAWLER_TYPE = "detail"
    runtime.g["config"].CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES = 0
    crawler_class = runtime.load(
        "media_platform/bilibili/core.py", cls="BilibiliCrawler", names=["collect_links"]
    )
    crawler = crawler_class()
    crawler.bili_client = NS(
        get_video_info=AsyncMock(return_value=_view("BV1abc123xyz", 101)),
        get_video_all_comments=AsyncMock(),
    )

    run(crawler.collect_links())

    crawler.bili_client.get_video_info.assert_awaited_once_with(
        aid=0, bvid="BV1abc123xyz"
    )
    stored.assert_awaited_once_with(_view("BV1abc123xyz", 101))
    crawler.bili_client.get_video_all_comments.assert_not_called()


@pytest.mark.parametrize(
    "response",
    [
        _view("BV-wrong", 101),
        {"View": {"bvid": "BV1abc123xyz", "aid": 101}},
        {"View": {"bvid": "BV1abc123xyz", "aid": 0, "owner": {"mid": 42}}},
    ],
)
def test_detail_rejects_a_mismatched_or_malformed_actual_view(runtime, response):
    runtime.g["bilibili_store"] = NS(
        update_bilibili_video=AsyncMock(),
        batch_update_bilibili_video_comments=AsyncMock(),
    )
    runtime.g["config"].CRAWLER_TYPE = "detail"
    crawler_class = runtime.load(
        "media_platform/bilibili/core.py", cls="BilibiliCrawler", names=["collect_links"]
    )
    crawler = crawler_class()
    crawler.bili_client = NS(get_video_info=AsyncMock(return_value=response))

    with pytest.raises(runtime.g["YikePlatformResponseChanged"]):
        run(crawler.collect_links())


def test_creator_reads_one_bounded_page_then_saves_all_bodies_before_comments(runtime):
    events = []

    async def get_video_info(*, aid, bvid):
        events.append(("view", bvid))
        return _view(bvid, {"BV-a": 11, "BV-b": 12, "BV-c": 13}[bvid])

    async def store_body(item):
        events.append(("body", item["View"]["bvid"]))

    async def get_comments(*, video_id, crawl_interval, is_fetch_sub_comments, callback, max_count):
        events.append(("comments", video_id, max_count))
        await callback(video_id, [{"rpid": video_id * 10 + 1}])

    runtime.g["bilibili_store"] = NS(
        update_bilibili_video=store_body,
        batch_update_bilibili_video_comments=AsyncMock(),
    )
    runtime.g["config"].CRAWLER_TYPE = "creator"
    runtime.g["config"].CRAWLER_MAX_NOTES_COUNT = 3
    runtime.g["config"].CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES = 2
    crawler_class = runtime.load(
        "media_platform/bilibili/core.py", cls="BilibiliCrawler", names=["collect_links"]
    )
    crawler = crawler_class()
    crawler.bili_client = NS(
        get_creator_videos=AsyncMock(
            return_value={
                "list": {
                    "vlist": [
                        {"bvid": "BV-a"},
                        {"bvid": "BV-a"},
                        {"bvid": "BV-b"},
                        {"bvid": "BV-c"},
                        {"bvid": "BV-over-budget"},
                    ]
                }
            }
        ),
        get_video_info=AsyncMock(side_effect=get_video_info),
        get_video_all_comments=AsyncMock(side_effect=get_comments),
    )

    run(crawler.collect_links())

    crawler.bili_client.get_creator_videos.assert_awaited_once_with(42, 1, 3)
    assert [call.kwargs["bvid"] for call in crawler.bili_client.get_video_info.await_args_list] == [
        "BV-a",
        "BV-b",
        "BV-c",
    ]
    assert [event[0] for event in events] == [
        "view",
        "view",
        "view",
        "body",
        "body",
        "body",
        "comments",
        "comments",
        "comments",
    ]
    assert [call.kwargs["max_count"] for call in crawler.bili_client.get_video_all_comments.await_args_list] == [
        2,
        2,
        2,
    ]


def test_creator_caps_the_single_page_at_five_distinct_contents(runtime):
    runtime.g["bilibili_store"] = NS(
        update_bilibili_video=AsyncMock(),
        batch_update_bilibili_video_comments=AsyncMock(),
    )
    runtime.g["config"].CRAWLER_TYPE = "creator"
    runtime.g["config"].CRAWLER_MAX_NOTES_COUNT = 99
    runtime.g["config"].CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES = 0
    bvids = [f"BV-{index}" for index in range(8)]
    crawler_class = runtime.load(
        "media_platform/bilibili/core.py", cls="BilibiliCrawler", names=["collect_links"]
    )
    crawler = crawler_class()
    crawler.bili_client = NS(
        get_creator_videos=AsyncMock(
            return_value={"list": {"vlist": [{"bvid": bvid} for bvid in bvids]}}
        ),
        get_video_info=AsyncMock(
            side_effect=lambda *, aid, bvid: _view(bvid, bvids.index(bvid) + 1)
        ),
        get_video_all_comments=AsyncMock(),
    )

    run(crawler.collect_links())

    crawler.bili_client.get_creator_videos.assert_awaited_once_with(42, 1, 5)
    assert crawler.bili_client.get_video_info.await_count == 5


def test_creator_rejects_actual_view_owned_by_another_creator(runtime):
    stored = AsyncMock()
    runtime.g["bilibili_store"] = NS(
        update_bilibili_video=stored,
        batch_update_bilibili_video_comments=AsyncMock(),
    )
    runtime.g["config"].CRAWLER_TYPE = "creator"
    crawler_class = runtime.load(
        "media_platform/bilibili/core.py", cls="BilibiliCrawler", names=["collect_links"]
    )
    crawler = crawler_class()
    crawler.bili_client = NS(
        get_creator_videos=AsyncMock(
            return_value={"list": {"vlist": [{"bvid": "BV-a"}]}}
        ),
        get_video_info=AsyncMock(return_value=_view("BV-a", 11, owner_mid=99)),
    )

    with pytest.raises(runtime.g["YikePlatformResponseChanged"]):
        run(crawler.collect_links())
    stored.assert_not_called()


def test_link_detail_failure_is_not_swallowed_as_empty_success(runtime):
    runtime.g["bilibili_store"] = NS(
        update_bilibili_video=AsyncMock(),
        batch_update_bilibili_video_comments=AsyncMock(),
    )
    runtime.g["config"].CRAWLER_TYPE = "detail"
    expected = RuntimeError("offline failure")
    crawler_class = runtime.load(
        "media_platform/bilibili/core.py", cls="BilibiliCrawler", names=["collect_links"]
    )
    crawler = crawler_class()
    crawler.bili_client = NS(get_video_info=AsyncMock(side_effect=expected))

    with pytest.raises(RuntimeError) as caught:
        run(crawler.collect_links())
    assert caught.value is expected


@pytest.mark.parametrize("mode", ["detail", "creator"])
def test_main_terminal_detection_uses_only_the_matching_bili_contents_prefix(runtime, tmp_path, mode):
    runtime.g["config"].SAVE_DATA_PATH = str(tmp_path)
    runtime.g["config"].PLATFORM = "bili"
    runtime.g["config"].CRAWLER_TYPE = mode
    loaded = runtime.load("main.py", names=["_has_candidate_output"])
    data_dir = tmp_path / "bili" / "jsonl"
    data_dir.mkdir(parents=True)
    (data_dir / "search_comments_fixture.jsonl").write_text(
        '{"comment_id":"old-search"}\n', encoding="utf-8"
    )
    assert loaded["_has_candidate_output"]() is False
    (data_dir / f"{mode}_contents_fixture.jsonl").write_text(
        '{"video_id":"101"}\n', encoding="utf-8"
    )
    assert loaded["_has_candidate_output"]() is True


def test_patch_chain_and_applied_file_hashes_match_lock(source):
    lock = json.loads((ROOT / "vendor/mediacrawler.lock").read_text(encoding="utf-8"))
    assert lock["commit"] == "439509782cc2991c8ef7648e178d5847b0545798"
    assert lock["patches"][-1]["path"] == (
        "vendor/patches/mediacrawler/0004-yike-bili-links.patch"
    )
    for relative, digest in lock["patched_files"].items():
        assert hashlib.sha256((source / relative).read_bytes()).hexdigest() == digest
