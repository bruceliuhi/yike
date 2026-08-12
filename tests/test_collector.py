import json
from dataclasses import replace
from pathlib import Path
import sys
from uuid import uuid4

import pytest

from app.collector import CollectionRequest, Collector
from app.db import connect, migrate
from app.repository import NormalizedSignal, Repository, SignalIdentityConflict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FAKE_RUNTIME = PROJECT_ROOT / "tests" / "fixtures" / "fake_mediacrawler"


@pytest.fixture
def repository(tmp_path):
    connection = connect(tmp_path / "facts.sqlite3")
    migrate(connection)
    repository = Repository(connection)
    yield repository
    connection.close()


@pytest.fixture
def run_id(repository):
    return repository.create_run(["bili", "dy"])


@pytest.fixture
def collector(repository, tmp_path):
    return Collector(
        repository=repository,
        runtime_path=FAKE_RUNTIME,
        work_root=tmp_path / "collector",
        python_executable=sys.executable,
    )


def request(run_id, *, platform="bili", query_text="销售获客", **changes):
    values = {
        "mvp_run_id": run_id,
        "collection_run_id": str(uuid4()),
        "platform": platform,
        "query_cluster": "sales-agent",
        "query_text": query_text,
        "max_contents": 5,
        "max_comments_per_content": 20,
    }
    values.update(changes)
    return CollectionRequest(**values)


def test_command_is_exact_visible_bounded_jsonl_and_secret_free(
    collector, run_id, tmp_path
):
    output = (tmp_path / "one-run").resolve()
    command = collector.command_for(request(run_id, platform="dy"), output)

    assert command == [
        sys.executable,
        str((FAKE_RUNTIME / "main.py").resolve()),
        "--platform",
        "dy",
        "--lt",
        "qrcode",
        "--type",
        "search",
        "--keywords",
        "销售获客",
        "--get_comment",
        "yes",
        "--get_sub_comment",
        "yes",
        "--headless",
        "no",
        "--save_data_option",
        "jsonl",
        "--save_data_path",
        str(output),
        "--crawler_max_notes_count",
        "5",
        "--max_comments_count_singlenotes",
        "20",
        "--max_concurrency_num",
        "1",
        "--enable_ip_proxy",
        "no",
    ]
    assert not any("cookie" in argument.lower() for argument in command)


@pytest.mark.parametrize(
    ("platform", "expected_source_url", "source_author", "comment_author"),
    [
        ("bili", "https://www.bilibili.com/video/BV1DISCOVERY", "up-bili", "lead-bili"),
        ("dy", "https://www.douyin.com/video/7123456789", "creator-dy", "lead-dy"),
    ],
)
def test_dual_platform_jsonl_rerun_reuses_signal_and_adds_observation(
    collector,
    repository,
    run_id,
    platform,
    expected_source_url,
    source_author,
    comment_author,
):
    first = collector.collect(request(run_id, platform=platform))
    second = collector.collect(request(run_id, platform=platform))

    assert first.status == second.status == "SUCCEEDED"
    assert first.raw_count == second.raw_count == 1
    assert first.unique_count == 1
    assert second.unique_count == 0
    assert repository.count_signals(run_id) == 1
    assert repository.count_observations(run_id) == 2
    row = repository.connection.execute(
        """
        SELECT so.canonical_url, so.author_public_id, si.author_public_id,
               si.parent_body
        FROM signals si JOIN sources so ON so.source_id = si.source_id
        WHERE si.platform = ?
        """,
        (platform,),
    ).fetchone()
    assert tuple(row) == (
        expected_source_url,
        source_author,
        comment_author,
        "我们团队获客成本越来越高",
    )


@pytest.mark.parametrize(
    "changes",
    [{"max_contents": 0}, {"max_comments_per_content": 51}],
)
def test_invalid_limits_fail_before_subprocess(collector, run_id, changes):
    with pytest.raises(ValueError, match="limit"):
        collector.collect(request(run_id, **changes))

    assert not collector.work_root.exists()


@pytest.mark.parametrize(
    ("query_text", "status", "error_code"),
    [
        ("__verification__", "BLOCKED_INPUT", "PLATFORM_VERIFICATION_REQUIRED"),
        ("__empty__", "SUCCEEDED_NO_DATA", None),
    ],
)
def test_verification_pauses_once_and_empty_is_explicit(
    collector, run_id, query_text, status, error_code
):
    result = collector.collect(request(run_id, query_text=query_text))

    assert (result.status, result.error_code, result.raw_count) == (
        status,
        error_code,
        0,
    )
    output_dir = collector.work_root / result.mvp_run_id / result.collection_run_id
    invocation = json.loads((output_dir / "invocation.json").read_text())
    assert invocation["count"] == 1


def test_batch_import_is_atomic_when_one_record_is_invalid(
    collector, repository, run_id
):
    result = collector.collect(request(run_id, query_text="__partial_invalid__"))

    assert result.status == "FAILED"
    assert result.error_code == "PLATFORM_RESPONSE_CHANGED"
    assert repository.count_signals(run_id) == 0
    assert repository.count_observations(run_id) == 0
    state = repository.connection.execute(
        "SELECT state FROM collection_runs WHERE collection_run_id = ?",
        (result.collection_run_id,),
    ).fetchone()[0]
    assert state == "FAILED"


@pytest.mark.parametrize(
    ("changes"),
    [
        {"source_url": "https://www.bilibili.com/video/BV-DIFFERENT"},
        {"source_author_public_id": "different-source-author"},
        {"external_source_id": "different-source"},
        {"author_public_id": "different-comment-author"},
        {"comment_url": "https://www.bilibili.com/video/BV1#reply-different"},
        {"body": "different body"},
    ],
)
def test_reused_external_identity_rejects_source_or_signal_drift(
    repository, run_id, changes
):
    original = NormalizedSignal(
        platform="bili",
        external_source_id="source-1",
        source_url="https://www.bilibili.com/video/BV1",
        source_author_public_id="source-author",
        external_comment_id="comment-1",
        comment_url="https://www.bilibili.com/video/BV1#reply-comment-1",
        author_public_id="comment-author",
        body="original body",
    )
    repository.import_signal(run_id, original)

    with pytest.raises(SignalIdentityConflict, match="SIGNAL_IDENTITY_CONFLICT"):
        repository.import_signal(run_id, replace(original, **changes))
