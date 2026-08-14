from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import textwrap
import threading
import time
from uuid import uuid4

import pytest

from app.collector import CollectionRequest, Collector
from app.collectors import normalize_bilibili, normalize_douyin
from app.db import connect, migrate
from app.normalizer import PlatformResponseChanged, normalize_time
from app.repository import CollectionCompletionError, NormalizedSignal, Repository


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PATCH_PATH = (
    PROJECT_ROOT
    / "vendor"
    / "patches"
    / "mediacrawler"
    / "0001-yike-controlled-runtime.patch"
)


def _request(run_id: str, *, query_text: str = "sales-agent", **changes):
    values = {
        "mvp_run_id": run_id,
        "collection_run_id": str(uuid4()),
        "platform": "bili",
        "query_cluster": "sales-agent",
        "query_text": query_text,
        "started_by": "d03-remediation-test",
        "max_contents": 5,
        "max_comments_per_content": 20,
    }
    values.update(changes)
    return CollectionRequest(**values)


def _make_runtime(tmp_path: Path) -> Path:
    runtime = tmp_path / "controlled-runtime"
    runtime.mkdir(mode=0o700)
    (runtime / "main.py").write_text(
        textwrap.dedent(
            """
            import argparse
            import json
            import os
            from pathlib import Path
            import time

            parser = argparse.ArgumentParser()
            for name in (
                "platform", "lt", "type", "keywords", "get_comment",
                "get_sub_comment", "headless", "save_data_option",
                "save_data_path", "crawler_max_notes_count",
                "max_comments_count_singlenotes", "max_concurrency_num",
                "enable_ip_proxy",
            ):
                parser.add_argument(f"--{name}", required=True)
            args = parser.parse_args()
            output = Path(args.save_data_path)
            output.mkdir(parents=True, exist_ok=True)

            def atomic(name, payload):
                target = output / name
                temporary = target.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    encoding="utf-8",
                )
                temporary.replace(target)

            def progress(state, sequence, **changes):
                payload = {
                    "schema_version": "YIKE_MEDIACRAWLER_PROGRESS_V1",
                    "platform": args.platform,
                    "state": state,
                    "sequence": sequence,
                }
                payload.update(changes)
                atomic(".yike-collection-progress.json", payload)

            if args.keywords == "__early_network_terminal__":
                atomic(
                    ".yike-collection-status.json",
                    {
                        "schema_version": "YIKE_MEDIACRAWLER_STATUS_V1",
                        "platform": args.platform,
                        "status": "FAILED",
                        "error_code": "COLLECTION_NETWORK_FAILED",
                    },
                )
                raise SystemExit(45)
            if args.keywords == "__early_success_terminal__":
                atomic(
                    ".yike-collection-status.json",
                    {
                        "schema_version": "YIKE_MEDIACRAWLER_STATUS_V1",
                        "platform": args.platform,
                        "status": "SUCCEEDED_NO_DATA",
                        "error_code": None,
                    },
                )
                raise SystemExit(0)

            if args.keywords == "__malformed_progress__":
                progress("RUNNING", 1, unexpected="field")
                time.sleep(0.25)
            elif args.keywords == "__regressive_progress__":
                progress("RUNNING", 1)
                time.sleep(0.15)
                progress("WAITING_LOGIN", 2)
                time.sleep(0.25)
            elif args.keywords == "__fast_progress__":
                progress("WAITING_LOGIN", 1)
                progress("RUNNING", 2)
            else:
                progress("WAITING_LOGIN", 1)
                time.sleep(0.20)
                progress("RUNNING", 2)
                time.sleep(0.20)

            if args.keywords == "__environment__":
                atomic(
                    "environment.json",
                    {
                        "present": sorted(
                            key
                            for key in (
                                "OPENAI_API_KEY",
                                "YIKE_MODEL_TOKEN",
                                "HTTP_PROXY",
                                "HTTPS_PROXY",
                                "CUSTOM_COOKIE",
                            )
                            if key in os.environ
                        )
                    },
                )
                atomic(
                    ".yike-collection-status.json",
                    {
                        "schema_version": "YIKE_MEDIACRAWLER_STATUS_V1",
                        "platform": args.platform,
                        "status": "SUCCEEDED_NO_DATA",
                        "error_code": None,
                    },
                )
                raise SystemExit(0)

            data_dir = output / ("bili" if args.platform == "bili" else "douyin") / "jsonl"
            data_dir.mkdir(parents=True, exist_ok=True)
            if args.platform == "bili":
                contents = [{
                    "video_id": "987654",
                    "title": "销售团队如何筛选高意向线索",
                    "creator_hash": "source-author",
                    "create_time": 1786464000,
                }]
                comments = [{
                    "comment_id": "123456",
                    "video_id": "987654",
                    "parent_comment_id": "0",
                    "content": "想找能自动筛出高意向客户的工具",
                    "creator_hash": "comment-author",
                    "create_time": 1786464000,
                }]
                if args.keywords == "__two_items__":
                    comments.append({**comments[0], "comment_id": "123457", "content": "第二条真实结构评论"})
            else:
                contents = [{
                    "aweme_id": "7123456789",
                    "title": "企业销售线索跟进",
                    "creator_hash": "source-author",
                    "create_time": 1786464000,
                }]
                comments = [{
                    "comment_id": "8234567890",
                    "aweme_id": "7123456789",
                    "parent_comment_id": "0",
                    "content": "想找能自动筛出高意向客户的工具",
                    "creator_hash": "comment-author",
                    "create_time": 1786464000,
                }]
            for kind, rows in (("contents", contents), ("comments", comments)):
                path = data_dir / f"search_{kind}_fixture.jsonl"
                path.write_text(
                    "".join(json.dumps(row, ensure_ascii=False) + "\\n" for row in rows),
                    encoding="utf-8",
                )
            atomic(
                ".yike-collection-status.json",
                {
                    "schema_version": "YIKE_MEDIACRAWLER_STATUS_V1",
                    "platform": args.platform,
                    "status": "SUCCEEDED",
                    "error_code": None,
                },
            )
            """
        ),
        encoding="utf-8",
    )
    return runtime


def _controlled_collector(repository, tmp_path, monkeypatch, runtime=None):
    runtime = runtime or _make_runtime(tmp_path)
    collector = Collector(
        repository=repository,
        runtime_path=runtime,
        work_root=tmp_path / "runs",
        python_executable=sys.executable,
        timeout_seconds=5,
    )
    monkeypatch.setattr(collector, "_verified_patched_checkout", lambda lock: True)
    return collector


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


def test_success_terminal_failure_rolls_back_two_item_import_and_frees_slot(
    repository, run_id, tmp_path, monkeypatch
):
    repository.connection.execute(
        """
        CREATE TRIGGER reject_d03_success_terminal
        BEFORE UPDATE OF state ON collection_runs
        WHEN NEW.state IN ('SUCCEEDED', 'SUCCEEDED_NO_DATA')
        BEGIN SELECT RAISE(ABORT, 'AUDIT_SUCCESS_WRITE_FAILED'); END
        """
    )
    repository.connection.commit()
    collector = _controlled_collector(repository, tmp_path, monkeypatch)
    collection_request = _request(run_id, query_text="__two_items__")

    error = None
    result = None
    try:
        result = collector.collect(collection_request)
    except Exception as caught:  # the public API must close, not leak, this failure
        error = caught
    row = repository.connection.execute(
        "SELECT state FROM collection_runs WHERE collection_run_id = ?",
        (collection_request.collection_run_id,),
    ).fetchone()
    active = repository.connection.execute(
        "SELECT count(*) FROM collection_runs WHERE state IN ('WAITING_LOGIN','RUNNING','IMPORTING')"
    ).fetchone()[0]

    assert (
        type(error).__name__ if error else None,
        result.status if result else None,
        row["state"],
        repository.count_signals(run_id),
        repository.count_observations(run_id),
        active,
    ) == (None, "FAILED", "FAILED", 0, 0, 0)


def test_cutoff_rejects_atomic_success_without_facts_and_allows_failed_close(tmp_path):
    now = [datetime(2026, 8, 1, 0, 0, tzinfo=UTC)]
    connection = connect(tmp_path / "facts.sqlite3")
    migrate(connection)
    repository = Repository(connection, now=lambda: now[0])
    run_id = repository.create_run(["bili", "dy"])
    collection_run_id = str(uuid4())
    repository.begin_collection(
        run_id=run_id,
        collection_run_id=collection_run_id,
        platform="bili",
        query_cluster="sales-agent",
        query_text="销售获客",
        max_contents=5,
        max_comments_per_content=20,
        started_by="d03-remediation-test",
        runtime_lock_sha256="a" * 64,
        backend="MEDIACRAWLER_AUTHORIZED",
    )
    advance = getattr(repository, "advance_collection_state", None)
    complete = getattr(repository, "complete_collection_success", None)
    assert callable(advance) and callable(complete), "atomic collection completion API is missing"

    advance(collection_run_id, "RUNNING")
    advance(collection_run_id, "IMPORTING")
    now[0] = datetime(2026, 8, 15, 16, 0, tzinfo=UTC)
    item = NormalizedSignal(
        platform="bili",
        external_source_id="987654",
        source_url="https://www.bilibili.com/video/av987654",
        source_title="source",
        source_author_public_id="source-author",
        external_comment_id="123456",
        comment_url="https://www.bilibili.com/video/av987654#reply123456",
        author_public_id="comment-author",
        body="lead",
        collection_run_id=collection_run_id,
        query_cluster="sales-agent",
        query_text="销售获客",
        raw_sha256="b" * 64,
        envelope_sha256="c" * 64,
        normalizer_version="bili-v1",
        verifiable=True,
    )
    with pytest.raises(ValueError, match="Day 14"):
        complete(
            collection_run_id=collection_run_id,
            run_id=run_id,
            platform="bili",
            backend="MEDIACRAWLER_AUTHORIZED",
            query_cluster="sales-agent",
            query_text="销售获客",
            max_contents=5,
            max_comments_per_content=20,
            items=[item],
            raw_count=1,
            output_manifest_sha256="d" * 64,
        )
    repository.finish_collection(
        collection_run_id,
        state="FAILED",
        raw_count=0,
        unique_count=0,
        error_code="COLLECTION_PROCESS_FAILED",
    )
    assert repository.count_signals(run_id) == 0
    assert repository.count_observations(run_id) == 0
    assert repository.connection.execute(
        "SELECT state FROM collection_runs WHERE collection_run_id = ?",
        (collection_run_id,),
    ).fetchone()[0] == "FAILED"
    connection.close()


def test_atomic_success_reads_completion_time_inside_write_transaction(tmp_path):
    completion_clock_states: list[bool] = []
    record_completion_clock = [False]

    def now():
        if record_completion_clock[0]:
            completion_clock_states.append(connection.in_transaction)
        return datetime(2026, 8, 1, 0, 0, tzinfo=UTC)

    connection = connect(tmp_path / "facts.sqlite3")
    migrate(connection)
    repository = Repository(connection, now=now)
    run_id = repository.create_run(["bili", "dy"])
    collection_run_id = str(uuid4())
    repository.begin_collection(
        run_id=run_id,
        collection_run_id=collection_run_id,
        platform="bili",
        query_cluster="sales-agent",
        query_text="销售获客",
        max_contents=5,
        max_comments_per_content=20,
        started_by="d03-remediation-test",
        runtime_lock_sha256="a" * 64,
        backend="MEDIACRAWLER_AUTHORIZED",
    )
    repository.advance_collection_state(collection_run_id, "RUNNING")
    repository.advance_collection_state(collection_run_id, "IMPORTING")

    record_completion_clock[0] = True
    repository.complete_collection_success(
        collection_run_id=collection_run_id,
        run_id=run_id,
        platform="bili",
        backend="MEDIACRAWLER_AUTHORIZED",
        query_cluster="sales-agent",
        query_text="销售获客",
        max_contents=5,
        max_comments_per_content=20,
        items=[],
        raw_count=0,
        output_manifest_sha256="d" * 64,
    )

    assert completion_clock_states == [True]
    assert connection.execute(
        "SELECT state FROM collection_runs WHERE collection_run_id = ?",
        (collection_run_id,),
    ).fetchone()[0] == "SUCCEEDED_NO_DATA"
    connection.close()


@pytest.mark.parametrize(
    ("source_ids", "max_contents", "max_comments_per_content"),
    [
        (["source-1", "source-2"], 1, 2),
        (["source-1", "source-1"], 1, 1),
    ],
    ids=("distinct-source-limit", "per-source-comment-limit"),
)
def test_atomic_success_rejects_batches_outside_campaign_limits_and_rolls_back(
    repository,
    run_id,
    source_ids,
    max_contents,
    max_comments_per_content,
):
    collection_run_id = str(uuid4())
    repository.begin_collection(
        run_id=run_id,
        collection_run_id=collection_run_id,
        platform="bili",
        query_cluster="sales-agent",
        query_text="销售获客",
        max_contents=max_contents,
        max_comments_per_content=max_comments_per_content,
        started_by="d03-remediation-test",
        runtime_lock_sha256="a" * 64,
        backend="MEDIACRAWLER_AUTHORIZED",
    )
    repository.advance_collection_state(collection_run_id, "RUNNING")
    repository.advance_collection_state(collection_run_id, "IMPORTING")
    items = [
        NormalizedSignal(
            platform="bili",
            external_source_id=source_id,
            source_url=f"https://www.bilibili.com/video/{source_id}",
            source_title="source",
            source_author_public_id=f"author-{source_id}",
            external_comment_id=f"comment-{index}",
            comment_url=(
                f"https://www.bilibili.com/video/{source_id}#reply{index}"
            ),
            author_public_id=f"comment-author-{index}",
            body=f"lead-{index}",
            collection_run_id=collection_run_id,
            query_cluster="sales-agent",
            query_text="销售获客",
            raw_sha256="b" * 64,
            envelope_sha256="c" * 64,
            normalizer_version="bili-v1",
            verifiable=True,
        )
        for index, source_id in enumerate(source_ids)
    ]

    with pytest.raises(CollectionCompletionError, match="limit"):
        repository.complete_collection_success(
            collection_run_id=collection_run_id,
            run_id=run_id,
            platform="bili",
            backend="MEDIACRAWLER_AUTHORIZED",
            query_cluster="sales-agent",
            query_text="销售获客",
            max_contents=max_contents,
            max_comments_per_content=max_comments_per_content,
            items=items,
            raw_count=len(items),
            output_manifest_sha256="d" * 64,
        )

    assert repository.count_signals(run_id) == 0
    assert repository.count_observations(run_id) == 0
    assert repository.connection.execute(
        "SELECT state FROM collection_runs WHERE collection_run_id = ?",
        (collection_run_id,),
    ).fetchone()[0] == "IMPORTING"


def test_slow_runtime_exposes_waiting_running_importing_then_success(
    repository, run_id, tmp_path, monkeypatch
):
    repository.connection.create_function("d03_pause", 0, lambda: time.sleep(0.25))
    repository.connection.execute(
        """
        CREATE TRIGGER pause_d03_success
        BEFORE UPDATE OF state ON collection_runs
        WHEN NEW.state IN ('SUCCEEDED', 'SUCCEEDED_NO_DATA')
        BEGIN SELECT d03_pause(); END
        """
    )
    repository.connection.commit()
    collector = _controlled_collector(repository, tmp_path, monkeypatch)
    collection_request = _request(run_id)
    observed: list[str] = []
    stop = threading.Event()
    database_path = tmp_path / "facts.sqlite3"

    def monitor():
        connection = sqlite3.connect(database_path)
        try:
            while not stop.is_set():
                row = connection.execute(
                    "SELECT state FROM collection_runs WHERE collection_run_id = ?",
                    (collection_request.collection_run_id,),
                ).fetchone()
                if (
                    row is not None
                    and row[0] in {"WAITING_LOGIN", "RUNNING", "IMPORTING"}
                    and (not observed or observed[-1] != row[0])
                ):
                    observed.append(row[0])
                time.sleep(0.01)
        finally:
            connection.close()

    watcher = threading.Thread(target=monitor)
    watcher.start()
    try:
        result = collector.collect(collection_request)
    finally:
        stop.set()
        watcher.join(timeout=2)
    final_state = repository.connection.execute(
        "SELECT state FROM collection_runs WHERE collection_run_id = ?",
        (collection_request.collection_run_id,),
    ).fetchone()[0]

    assert result.status == final_state == "SUCCEEDED"
    assert observed == ["WAITING_LOGIN", "RUNNING", "IMPORTING"]


@pytest.mark.parametrize("query_text", ["__malformed_progress__", "__regressive_progress__"])
def test_invalid_runtime_progress_fails_closed(
    repository, run_id, tmp_path, monkeypatch, query_text
):
    collector = _controlled_collector(repository, tmp_path, monkeypatch)

    result = collector.collect(_request(run_id, query_text=query_text))

    assert (result.status, result.error_code) == (
        "FAILED",
        "COLLECTION_PROCESS_FAILED",
    )
    assert repository.count_signals(run_id) == 0
    assert repository.connection.execute(
        "SELECT count(*) FROM collection_runs WHERE state IN ('WAITING_LOGIN','RUNNING','IMPORTING')"
    ).fetchone()[0] == 0


def test_fast_atomic_progress_may_skip_an_unobserved_sequence(
    repository, run_id, tmp_path, monkeypatch
):
    collector = _controlled_collector(repository, tmp_path, monkeypatch)

    result = collector.collect(_request(run_id, query_text="__fast_progress__"))

    assert result.status == "SUCCEEDED"
    assert repository.connection.execute(
        "SELECT state FROM collection_runs WHERE collection_run_id = ?",
        (result.collection_run_id,),
    ).fetchone()[0] == "SUCCEEDED"


def _begin_and_block(repository: Repository, run_id: str, collection_run_id: str, query: str):
    repository.begin_collection(
        run_id=run_id,
        collection_run_id=collection_run_id,
        platform="bili",
        query_cluster=" sales-agent ",
        query_text=query,
        max_contents=5,
        max_comments_per_content=20,
        started_by="d03-remediation-test",
        runtime_lock_sha256="a" * 64,
        backend="MEDIACRAWLER_AUTHORIZED",
    )
    repository.finish_collection(
        collection_run_id,
        state="BLOCKED_INPUT",
        raw_count=0,
        unique_count=0,
        error_code="PLATFORM_AUTH_REQUIRED",
    )


def test_exact_rerun_reuses_campaign_and_increments_attempt(repository, run_id):
    _begin_and_block(repository, run_id, "attempt-1", " 销售获客 ")
    _begin_and_block(repository, run_id, "attempt-2", "销售获客")
    _begin_and_block(repository, run_id, "different-query", "销售 Agent")

    campaigns = repository.connection.execute(
        "SELECT campaign_id, query_cluster, query_text FROM campaigns ORDER BY rowid"
    ).fetchall()
    attempts = repository.connection.execute(
        "SELECT campaign_id, attempt FROM collection_runs ORDER BY rowid"
    ).fetchall()

    assert len(campaigns) == 2
    assert tuple(campaigns[0][1:]) == ("sales-agent", "销售获客")
    assert [(row[0], row[1]) for row in attempts[:2]] == [
        (campaigns[0][0], 1),
        (campaigns[0][0], 2),
    ]
    assert tuple(attempts[2]) == (campaigns[1][0], 1)


def test_concurrent_rerun_admission_never_allocates_duplicate_attempt(tmp_path):
    database_path = tmp_path / "facts.sqlite3"
    connection = connect(database_path)
    migrate(connection)
    repository = Repository(connection)
    run_id = repository.create_run(["bili", "dy"])
    _begin_and_block(repository, run_id, "attempt-1", "销售获客")
    connection.close()
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def admit(index: int):
        local = connect(database_path)
        try:
            local_repository = Repository(local)
            barrier.wait(timeout=2)
            local_repository.begin_collection(
                run_id=run_id,
                collection_run_id=f"concurrent-{index}",
                platform="bili",
                query_cluster="sales-agent",
                query_text="销售获客",
                max_contents=5,
                max_comments_per_content=20,
                started_by="d03-remediation-test",
                runtime_lock_sha256="a" * 64,
                backend="MEDIACRAWLER_AUTHORIZED",
            )
            outcomes.append("started")
        except Exception as error:
            outcomes.append(type(error).__name__)
        finally:
            local.close()

    threads = [threading.Thread(target=admit, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    inspection = connect(database_path)
    rows = inspection.execute(
        "SELECT campaign_id, attempt FROM collection_runs ORDER BY attempt, collection_run_id"
    ).fetchall()
    inspection.close()
    assert outcomes.count("started") == 1
    assert len({row[0] for row in rows}) == 1
    assert [row[1] for row in rows] == [1, 2]


def test_collector_child_receives_no_parent_secrets(
    repository, run_id, tmp_path, monkeypatch
):
    for name in (
        "OPENAI_API_KEY",
        "YIKE_MODEL_TOKEN",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "CUSTOM_COOKIE",
    ):
        monkeypatch.setenv(name, f"SECRET-{name}")
    collector = _controlled_collector(repository, tmp_path, monkeypatch)

    result = collector.collect(_request(run_id, query_text="__environment__"))
    payload = json.loads((Path(result.output_dir) / "environment.json").read_text())

    assert result.status == "SUCCEEDED_NO_DATA"
    assert payload == {"present": []}


def test_fetch_and_preflight_define_private_minimal_environments():
    script = (PROJECT_ROOT / "scripts" / "fetch_mediacrawler.sh").read_text()
    collector_source = (PROJECT_ROOT / "app" / "collector.py").read_text()

    assert "umask 077" in script
    assert "YIKE_ENV_ALLOWLIST" in script
    assert "{**os.environ" not in script
    assert "{**os.environ" not in collector_source


def test_cli_setup_failure_redacts_lower_level_path_and_prints_one_terminal(tmp_path):
    secret_path = tmp_path / "SECRET-TOKEN-runtime-root"
    secret_path.write_text("not a directory", encoding="utf-8")
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.cli import collector; collector()",
            "collect",
            "--platform",
            "bili",
            "--mvp-run-id",
            "valid-run",
            "--query-cluster",
            "sales-agent",
            "--query-text",
            "销售获客",
            "--started-by",
            "d03-remediation-test",
        ],
        cwd=PROJECT_ROOT,
        env={**os.environ, "YIKE_MVP_ROOT": str(secret_path)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert process.returncode == 1
    assert process.stderr.strip() == "COLLECTION_SETUP_FAILED"
    assert str(secret_path) not in process.stdout + process.stderr
    assert process.stdout.count("\n") == 1
    assert json.loads(process.stdout)["error_code"] == "COLLECTION_SETUP_FAILED"


def test_runtime_profile_output_and_raw_files_are_private(
    repository, run_id, tmp_path, monkeypatch
):
    runtime = _make_runtime(tmp_path)
    collector = _controlled_collector(
        repository, tmp_path, monkeypatch, runtime=runtime
    )

    result = collector.collect(_request(run_id))
    output = Path(result.output_dir)
    profile = runtime / "browser_data" / "bili_user_data_dir"
    jsonl = output / "bili" / "jsonl" / "search_comments_fixture.jsonl"

    assert result.status == "SUCCEEDED"
    assert profile.is_dir()
    assert [
        runtime.stat().st_mode & 0o777,
        profile.stat().st_mode & 0o777,
        collector.work_root.stat().st_mode & 0o777,
        output.parent.stat().st_mode & 0o777,
        output.stat().st_mode & 0o777,
    ] == [0o700] * 5
    assert [
        (output / ".yike-collection-progress.json").stat().st_mode & 0o777,
        (output / ".yike-collection-status.json").stat().st_mode & 0o777,
        jsonl.stat().st_mode & 0o777,
    ] == [0o600] * 3


def test_governed_patch_removes_extra_qr_viewer_and_qr_url_logging():
    patch = PATCH_PATH.read_text(encoding="utf-8")
    removals = "\n".join(line[1:] for line in patch.splitlines() if line.startswith("-"))
    additions = "\n".join(line[1:] for line in patch.splitlines() if line.startswith("+"))

    assert removals.count("utils.show_qrcode") >= 2
    assert "get qrcode by url" in removals
    assert "utils.show_qrcode" not in additions
    assert "get qrcode by url" not in additions


@pytest.mark.parametrize(
    "value",
    [
        True,
        1.5,
        "1786464000",
        "2026-08-12T08:00:00+00:00",
        "2026-08-12T00:00:00.123Z",
        "not-a-time",
        10**30,
        {"time": 1},
    ],
)
def test_normalize_time_rejects_noncanonical_or_noninteger_values(value):
    with pytest.raises(PlatformResponseChanged):
        normalize_time(value)


def test_normalize_time_accepts_epoch_and_canonical_utc():
    assert normalize_time(1786464000) == "2026-08-11T16:00:00Z"
    assert normalize_time("2026-08-12T00:00:00Z") == "2026-08-12T00:00:00Z"
    assert normalize_time(None) is None


@pytest.mark.parametrize(
    ("normalizer", "record"),
    [
        (
            normalize_bilibili,
            {
                "content": {"video_id": {"nested": "id"}, "title": "t", "creator_hash": "a"},
                "comment": {"comment_id": "123", "content": "b", "creator_hash": "c"},
            },
        ),
        (
            normalize_bilibili,
            {
                "content": {"video_id": "987654", "title": ["nested"], "creator_hash": "a"},
                "comment": {"comment_id": "123", "content": {"text": "b"}, "creator_hash": "c"},
            },
        ),
        (
            normalize_bilibili,
            {
                "content": {"video_id": "../bad", "title": "t", "creator_hash": "a"},
                "comment": {"comment_id": "123", "content": "b", "creator_hash": "c"},
            },
        ),
        (
            normalize_bilibili,
            {
                "content": {"video_id": "987654", "title": "t", "creator_hash": "a"},
                "comment": {
                    "comment_id": "123",
                    "content": "b",
                    "creator_hash": "c",
                    "comment_url": "javascript:alert(1)",
                },
            },
        ),
        (
            normalize_douyin,
            {
                "content": {"aweme_id": ["nested"], "title": "t", "creator_hash": "a"},
                "comment": {"comment_id": "123", "content": "b", "creator_hash": "c"},
            },
        ),
        (
            normalize_douyin,
            {
                "content": {"aweme_id": "7123456789", "title": "t", "creator_hash": "a"},
                "comment": {
                    "comment_id": "8234567890",
                    "content": "b",
                    "creator_hash": "c",
                    "comment_url": "https://example.com/video/7123456789",
                },
            },
        ),
    ],
)
def test_adapters_fail_closed_on_nested_invalid_id_or_unsafe_url(normalizer, record):
    with pytest.raises(PlatformResponseChanged):
        normalizer(record)


@pytest.mark.parametrize(
    ("normalizer", "record"),
    [
        (
            normalize_bilibili,
            {
                "content": {
                    "video_id": "987654",
                    "title": "source",
                    "creator_hash": "source-author",
                    "video_url": "https://WWW.BILIBILI.COM/video/av987654",
                },
                "comment": {
                    "comment_id": "123456",
                    "content": "lead",
                    "creator_hash": "comment-author",
                },
            },
        ),
        (
            normalize_douyin,
            {
                "content": {
                    "aweme_id": "7123456789",
                    "title": "source",
                    "creator_hash": "source-author",
                },
                "comment": {
                    "comment_id": "8234567890",
                    "content": "lead",
                    "creator_hash": "comment-author",
                    "comment_url": (
                        "https://www.douyin.com/video/7123456789"
                        "?comment_id=%38%32%33%34%35%36%37%38%39%30"
                    ),
                },
            },
        ),
    ],
)
def test_adapters_reject_noncanonical_url_spellings(normalizer, record):
    with pytest.raises(PlatformResponseChanged):
        normalizer(record)


@pytest.mark.parametrize(
    ("normalizer", "identity_field", "identity"),
    [
        (normalize_bilibili, "video_id", "1٢٣"),
        (normalize_bilibili, "video_id", "1" * 21),
        (normalize_douyin, "aweme_id", "1٢٣"),
        (normalize_douyin, "aweme_id", "1" * 21),
    ],
)
def test_adapters_reject_non_ascii_or_overlong_platform_ids(
    normalizer, identity_field, identity
):
    content = {
        identity_field: identity,
        "title": "source",
        "creator_hash": "source-author",
    }
    comment = {
        "comment_id": "123456",
        "content": "lead",
        "creator_hash": "comment-author",
    }
    with pytest.raises(PlatformResponseChanged):
        normalizer({"content": content, "comment": comment})


@pytest.mark.parametrize("normalizer", [normalize_bilibili, normalize_douyin])
@pytest.mark.parametrize("comment_id", ["1٢٣", "1" * 21])
def test_adapters_reject_non_ascii_or_overlong_comment_ids(
    normalizer, comment_id
):
    source_key = "video_id" if normalizer is normalize_bilibili else "aweme_id"
    with pytest.raises(PlatformResponseChanged):
        normalizer(
            {
                "content": {
                    source_key: "987654",
                    "title": "source",
                    "creator_hash": "source-author",
                },
                "comment": {
                    "comment_id": comment_id,
                    source_key: "987654",
                    "content": "lead",
                    "creator_hash": "comment-author",
                },
            }
        )


def test_bilibili_rejects_structurally_invalid_bvid():
    with pytest.raises(PlatformResponseChanged):
        normalize_bilibili(
            {
                "content": {
                    "video_id": "987654",
                    "bvid": "BVaaaaaaaaaa",
                    "title": "source",
                    "creator_hash": "source-author",
                },
                "comment": {
                    "comment_id": "123456",
                    "video_id": "987654",
                    "content": "lead",
                    "creator_hash": "comment-author",
                },
            }
        )


@pytest.mark.parametrize("normalizer", [normalize_bilibili, normalize_douyin])
def test_adapters_reject_invalid_platform_timestamps(normalizer):
    source_key = "video_id" if normalizer is normalize_bilibili else "aweme_id"
    with pytest.raises(PlatformResponseChanged):
        normalizer(
            {
                "content": {
                    source_key: "987654",
                    "title": "source",
                    "creator_hash": "source-author",
                    "create_time": "2026-01-01T24:59:59Z",
                },
                "comment": {
                    "comment_id": "123456",
                    source_key: "987654",
                    "content": "lead",
                    "creator_hash": "comment-author",
                },
            }
        )


def test_bilibili_bvid_is_canonical_source_when_video_url_is_absent():
    item = normalize_bilibili(
        {
            "content": {
                "video_id": "987654",
                "bvid": "BV1xx411c7mD",
                "title": "Bilibili source",
                "creator_hash": "source-author",
            },
            "comment": {
                "comment_id": "123456",
                "video_id": "987654",
                "content": "Bilibili lead",
                "creator_hash": "comment-author",
            },
        }
    )

    assert item.source_url == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert item.comment_url == (
        "https://www.bilibili.com/video/BV1xx411c7mD#reply123456"
    )


def test_adapters_accept_representative_exact_pinned_runtime_records():
    bili = normalize_bilibili(
        {
            "content": {
                "video_id": "987654",
                "title": "Bilibili source",
                "creator_hash": "source-author",
                "create_time": 1786464000,
                "video_url": "https://www.bilibili.com/video/av987654",
            },
            "comment": {
                "comment_id": "123456",
                "video_id": "987654",
                "parent_comment_id": "0",
                "content": "Bilibili lead",
                "creator_hash": "comment-author",
                "create_time": 1786464000,
            },
        }
    )
    douyin = normalize_douyin(
        {
            "content": {
                "aweme_id": "7123456789",
                "title": "Douyin source",
                "creator_hash": "source-author",
                "create_time": 1786464000,
                "aweme_url": "https://www.douyin.com/video/7123456789",
            },
            "comment": {
                "comment_id": "8234567890",
                "aweme_id": "7123456789",
                "parent_comment_id": "0",
                "content": "Douyin lead",
                "creator_hash": "comment-author",
                "create_time": 1786464000,
            },
        }
    )

    assert bili.source_url == "https://www.bilibili.com/video/av987654"
    assert bili.comment_url == "https://www.bilibili.com/video/av987654#reply123456"
    assert douyin.source_url == "https://www.douyin.com/video/7123456789"
    assert douyin.comment_url == "https://www.douyin.com/video/7123456789"


def test_source_rejects_noncanonical_published_time_and_rolls_back(repository):
    with pytest.raises(sqlite3.IntegrityError):
        repository.connection.execute(
            """
            INSERT INTO sources (
                source_id, platform, external_source_id, title, canonical_url,
                author_public_id, published_at
            ) VALUES (
                'bad-time-source', 'bili', '987654', 'source',
                'https://www.bilibili.com/video/av987654', 'source-author', 'not-a-time'
            )
            """
        )
    repository.connection.rollback()
    assert repository.connection.execute(
        "SELECT count(*) FROM sources WHERE source_id = 'bad-time-source'"
    ).fetchone()[0] == 0


def test_verifiable_signal_rejects_noncanonical_published_time_and_rolls_back(repository):
    repository.connection.execute(
        """
        INSERT INTO sources (
            source_id, platform, external_source_id, title, canonical_url,
            author_public_id, published_at
        ) VALUES (
            'valid-time-source', 'bili', '987654', 'source',
            'https://www.bilibili.com/video/av987654',
            'source-author', '2026-08-12T00:00:00Z'
        )
        """
    )
    repository.connection.commit()
    with pytest.raises(sqlite3.IntegrityError):
        repository.connection.execute(
            """
            INSERT INTO signals (
                signal_id, source_id, platform, external_comment_id,
                normalized_comment_url, author_public_id, body, body_sha256,
                published_at, verifiable, normalizer_version
            ) VALUES (
                'bad-time-signal', 'valid-time-source', 'bili', '123456',
                'https://www.bilibili.com/video/av987654#reply123456',
                'comment-author', 'lead', yike_sha256_text('lead'),
                'also-bad', 1, 'bili-v1'
            )
            """
        )
    repository.connection.rollback()
    assert repository.connection.execute(
        "SELECT count(*) FROM signals WHERE signal_id = 'bad-time-signal'"
    ).fetchone()[0] == 0


@pytest.mark.parametrize(
    "published_at",
    ["2026-01-01T24:59:59Z", "0000-01-01T00:00:00Z"],
)
def test_source_rejects_calendar_invalid_canonical_shaped_time(
    repository, published_at
):
    with pytest.raises(sqlite3.IntegrityError):
        repository.connection.execute(
            """
            INSERT INTO sources (
                source_id, platform, external_source_id, title, canonical_url,
                author_public_id, published_at
            ) VALUES (?, 'bili', '987654', 'source',
                      'https://www.bilibili.com/video/av987654',
                      'source-author', ?)
            """,
            (f"bad-calendar-{published_at}", published_at),
        )
    repository.connection.rollback()


def test_v16_schema_marker_is_not_silently_upgraded(tmp_path):
    database_path = tmp_path / "v16-marker.sqlite3"
    connection = connect(database_path)
    migrate(connection)
    connection.execute(
        "UPDATE schema_meta SET version = 'DISCOVERY_FACT_STORE_V16' "
        "WHERE schema_key = 'discovery'"
    )
    connection.commit()
    before = connection.total_changes

    from app.db import UnsupportedSchemaError

    with pytest.raises(UnsupportedSchemaError, match="UNSUPPORTED_SCHEMA"):
        migrate(connection)

    assert connection.total_changes == before
    assert connection.execute(
        "SELECT version FROM schema_meta WHERE schema_key = 'discovery'"
    ).fetchone()[0] == "DISCOVERY_FACT_STORE_V16"
    connection.close()


def _new_file_added_by_patch(patch: str, relative_path: str) -> str | None:
    lines = patch.splitlines()
    header = f"diff --git a/{relative_path} b/{relative_path}"
    try:
        start = lines.index(header) + 1
    except ValueError:
        return None
    added: list[str] = []
    in_hunk = False
    for line in lines[start:]:
        if line.startswith("diff --git "):
            break
        if line.startswith("@@"):
            in_hunk = True
            continue
        if in_hunk and line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
    return "\n".join(added) + "\n"


def _function_added_by_patch(
    patch: str, relative_path: str, function_name: str
) -> str | None:
    header = f"diff --git a/{relative_path} b/{relative_path}"
    try:
        file_patch = patch[patch.index(header) + len(header) :]
    except ValueError:
        return None
    next_file = file_patch.find("\ndiff --git ")
    if next_file >= 0:
        file_patch = file_patch[:next_file]
    lines = file_patch.splitlines()
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if line.startswith(f"+def {function_name}(")
        ),
        None,
    )
    if start is None:
        return None
    added: list[str] = []
    for line in lines[start:]:
        if not line.startswith("+") or line.startswith("+++"):
            break
        added.append(line[1:])
    return "\n".join(added).rstrip() + "\n"


def test_exact_patched_bilibili_client_rejects_changed_response_shapes():
    patch = PATCH_PATH.read_text(encoding="utf-8")
    runtime_source = _new_file_added_by_patch(patch, "tools/yike_runtime.py")
    guard_source = _function_added_by_patch(
        patch,
        "media_platform/bilibili/client.py",
        "_yike_bilibili_platform_code",
    )
    assert runtime_source is not None
    assert guard_source is not None, "patched Bilibili response guard is missing"
    namespace: dict[str, object] = {}
    exec(compile(runtime_source, "tools/yike_runtime.py", "exec"), namespace)
    exec(
        compile(guard_source, "media_platform/bilibili/client.py", "exec"),
        namespace,
    )
    platform_code = namespace["_yike_bilibili_platform_code"]
    response_changed = namespace["YikePlatformResponseChanged"]

    for payload in ([], "", 0, None, {"code": False}, {"code": "0"}, {}):
        with pytest.raises(response_changed):
            platform_code(payload)
    assert platform_code({"code": 0}) == 0
    assert platform_code({"code": -101}) == -101
    assert "platform_code = _yike_bilibili_platform_code(data)" in patch


def test_exact_patched_runtime_classifier_uses_explicit_types_only():
    source = _new_file_added_by_patch(
        PATCH_PATH.read_text(encoding="utf-8"), "tools/yike_runtime.py"
    )
    assert source is not None, "governed explicit runtime classifier is missing"
    namespace: dict[str, object] = {}
    exec(compile(source, "tools/yike_runtime.py", "exec"), namespace)
    classify = namespace["classify_error"]

    expected = {
        "YikePlatformAuthRequired": ("PLATFORM_AUTH_REQUIRED", 40),
        "YikePlatformPermissionDenied": ("PLATFORM_PERMISSION_DENIED", 41),
        "YikePlatformVerificationRequired": ("PLATFORM_VERIFICATION_REQUIRED", 42),
        "YikePlatformRateLimited": ("PLATFORM_RATE_LIMITED", 43),
        "YikePlatformResponseChanged": ("PLATFORM_RESPONSE_CHANGED", 44),
        "YikeNetworkFailed": ("COLLECTION_NETWORK_FAILED", 45),
        "YikeCollectionParseFailed": ("COLLECTION_PARSE_FAILED", 46),
    }
    for class_name, terminal in expected.items():
        assert classify(namespace[class_name]()) == terminal
    assert classify(TimeoutError()) == ("COLLECTION_NETWORK_FAILED", 45)
    for text in (
        "登录失效",
        "Forbidden",
        "Expecting value: line 1 column 1",
        "unrelated entity blocked by local policy",
        "429 merely appeared in arbitrary prose",
    ):
        assert classify(Exception(text)) == ("COLLECTION_PROCESS_FAILED", 48)


@pytest.mark.parametrize(
    "changes",
    [
        {"max_contents": True},
        {"max_contents": 1.5},
        {"max_comments_per_content": True},
        {"max_comments_per_content": 1.5},
    ],
)
def test_programmatic_noninteger_limits_fail_before_database_or_spawn(
    repository, run_id, tmp_path, monkeypatch, changes
):
    collector = _controlled_collector(repository, tmp_path, monkeypatch)
    monkeypatch.setattr(
        repository,
        "begin_collection",
        lambda *args, **kwargs: pytest.fail("invalid request reached repository"),
    )
    monkeypatch.setattr(
        "app.collector.run_supervised_process",
        lambda *args, **kwargs: pytest.fail("invalid request must not spawn"),
    )

    with pytest.raises(ValueError, match="limit"):
        collector.collect(_request(run_id, **changes))

    assert repository.connection.execute("SELECT count(*) FROM campaigns").fetchone()[0] == 0
    assert not collector.work_root.exists()


def test_keyboard_interrupt_during_atomic_completion_cancels_and_frees_slot(
    repository, run_id, tmp_path, monkeypatch
):
    collector = _controlled_collector(repository, tmp_path, monkeypatch)
    transaction_states: list[bool] = []

    def interrupt_prepare(*args, **kwargs):
        transaction_states.append(repository.connection.in_transaction)
        raise KeyboardInterrupt("operator cancelled during import")

    monkeypatch.setattr(repository, "_prepare_signal", interrupt_prepare)
    caught = None
    result = None
    request = _request(run_id, query_text="__fast_progress__")
    try:
        result = collector.collect(request)
    except BaseException as error:  # RED records the leaked KeyboardInterrupt safely.
        caught = error

    row = repository.connection.execute(
        "SELECT state, error_code FROM collection_runs WHERE collection_run_id = ?",
        (request.collection_run_id,),
    ).fetchone()
    active = repository.connection.execute(
        "SELECT count(*) FROM collection_runs "
        "WHERE state IN ('WAITING_LOGIN','RUNNING','IMPORTING')"
    ).fetchone()[0]

    assert transaction_states == [True]
    assert caught is None
    assert result is not None
    assert result.collection_run_id == request.collection_run_id
    assert (result.status, result.error_code) == (
        "CANCELLED",
        "COLLECTION_CANCELLED",
    )
    assert tuple(row) == ("CANCELLED", "COLLECTION_CANCELLED")
    assert repository.count_signals(run_id) == 0
    assert repository.count_observations(run_id) == 0
    assert active == 0


def test_valid_typed_terminal_before_first_progress_is_preserved(
    repository, run_id, tmp_path, monkeypatch
):
    collector = _controlled_collector(repository, tmp_path, monkeypatch)
    request = _request(run_id, query_text="__early_network_terminal__")

    result = collector.collect(request)

    assert (result.status, result.error_code) == (
        "FAILED",
        "COLLECTION_NETWORK_FAILED",
    )
    row = repository.connection.execute(
        "SELECT state, error_code FROM collection_runs WHERE collection_run_id = ?",
        (request.collection_run_id,),
    ).fetchone()
    assert tuple(row) == ("FAILED", "COLLECTION_NETWORK_FAILED")


def test_success_terminal_without_running_progress_still_fails_closed(
    repository, run_id, tmp_path, monkeypatch
):
    collector = _controlled_collector(repository, tmp_path, monkeypatch)

    result = collector.collect(
        _request(run_id, query_text="__early_success_terminal__")
    )

    assert (result.status, result.error_code) == (
        "FAILED",
        "COLLECTION_PROCESS_FAILED",
    )


def test_exact_patch_requires_endpoint_specific_response_shapes(monkeypatch):
    patch = PATCH_PATH.read_text(encoding="utf-8")
    runtime_source = _new_file_added_by_patch(patch, "tools/yike_runtime.py")
    login_guard_source = _function_added_by_patch(
        patch,
        "media_platform/bilibili/client.py",
        "_yike_bilibili_login_state",
    )
    detail_guard_source = _function_added_by_patch(
        patch,
        "media_platform/bilibili/client.py",
        "_yike_bilibili_video_detail",
    )
    assert runtime_source is not None
    assert login_guard_source is not None
    assert detail_guard_source is not None
    from types import ModuleType

    class PlaywrightTimeoutError(Exception):
        pass

    playwright = ModuleType("playwright")
    async_api = ModuleType("playwright.async_api")
    async_api.TimeoutError = PlaywrightTimeoutError
    playwright.async_api = async_api
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.async_api", async_api)
    namespace: dict[str, object] = {}
    exec(compile(runtime_source, "tools/yike_runtime.py", "exec"), namespace)
    exec(
        compile(login_guard_source, "media_platform/bilibili/client.py", "exec"),
        namespace,
    )
    exec(
        compile(detail_guard_source, "media_platform/bilibili/client.py", "exec"),
        namespace,
    )
    response_changed = namespace["YikePlatformResponseChanged"]
    bilibili_login_state = namespace["_yike_bilibili_login_state"]
    bilibili_video_detail = namespace["_yike_bilibili_video_detail"]
    require_mapping_field = namespace.get("require_mapping_field")
    require_list_field = namespace.get("require_list_field")
    require_mapping_list_field = namespace.get("require_mapping_list_field")
    require_int_field = namespace.get("require_int_field")
    require_bool_field = namespace.get("require_bool_field")
    require_nonempty_string_field = namespace.get("require_nonempty_string_field")
    require_bilibili_comment_list = namespace.get("require_bilibili_comment_list")
    require_douyin_comment_list = namespace.get("require_douyin_comment_list")
    assert callable(require_mapping_field)
    assert callable(require_list_field)
    assert callable(require_mapping_list_field)
    assert callable(require_int_field)
    assert callable(require_bool_field)
    assert callable(require_nonempty_string_field)
    assert callable(require_bilibili_comment_list)
    assert callable(require_douyin_comment_list)

    assert require_mapping_field({"data": {}}, "data") == {}
    assert require_list_field({"data": []}, "data") == []
    assert require_mapping_list_field({"data": []}, "data") == []
    assert require_int_field({"status_code": 0}, "status_code") == 0
    assert require_bool_field({"is_end": False}, "is_end") is False
    assert require_nonempty_string_field({"logid": "search-id"}, "logid") == "search-id"
    assert require_bilibili_comment_list({"replies": []}, "replies") == []
    assert require_douyin_comment_list({"comments": []}, "comments") == []
    assert bilibili_login_state({"isLogin": True}) is True
    assert bilibili_login_state({"isLogin": False}) is False
    assert bilibili_video_detail({"View": {"aid": 123}}) == {
        "View": {"aid": 123}
    }
    for payload in ({}, {"isLogin": "false"}, {"isLogin": 0}):
        with pytest.raises(response_changed):
            bilibili_login_state(payload)
    for payload in (
        {},
        {"View": None},
        {"View": {}},
        {"View": {"aid": "123"}},
        {"View": {"aid": 0}},
    ):
        with pytest.raises(response_changed):
            bilibili_video_detail(payload)
    for helper, payload, field in (
        (require_mapping_field, {}, "data"),
        (require_mapping_field, {"data": None}, "data"),
        (require_mapping_field, {"data": []}, "data"),
        (require_list_field, {}, "data"),
        (require_list_field, {"data": None}, "data"),
        (require_list_field, {"data": {}}, "data"),
        (require_int_field, {}, "status_code"),
        (require_int_field, {"status_code": False}, "status_code"),
        (require_int_field, {"status_code": "0"}, "status_code"),
        (require_bool_field, {}, "is_end"),
        (require_bool_field, {"is_end": 0}, "is_end"),
    ):
        with pytest.raises(response_changed):
            helper(payload, field)

    for payload in ({}, {"data": None}, {"data": {}}, {"data": ["bad"]}):
        with pytest.raises(response_changed):
            require_mapping_list_field(payload, "data")
    for payload in ({}, {"logid": None}, {"logid": 1}, {"logid": ""}):
        with pytest.raises(response_changed):
            require_nonempty_string_field(payload, "logid")
    assert require_bilibili_comment_list(
        {"replies": [{"rpid": 1}, {"rpid": 2, "rcount": 0}]}, "replies"
    ) == [{"rpid": 1}, {"rpid": 2, "rcount": 0}]
    for payload in (
        {"replies": [{}]},
        {"replies": [{"rpid": "1"}]},
        {"replies": [{"rpid": 1, "rcount": "1"}]},
        {"replies": [{"rpid": 1, "rcount": -1}]},
    ):
        with pytest.raises(response_changed):
            require_bilibili_comment_list(payload, "replies")
    assert require_douyin_comment_list(
        {
            "comments": [
                {"cid": "1"},
                {"cid": "2", "reply_comment_total": 0},
            ]
        },
        "comments",
    ) == [{"cid": "1"}, {"cid": "2", "reply_comment_total": 0}]
    for payload in (
        {"comments": [{}]},
        {"comments": [{"cid": 1}]},
        {"comments": [{"cid": "1", "reply_comment_total": "1"}]},
        {"comments": [{"cid": "1", "reply_comment_total": -1}]},
    ):
        with pytest.raises(response_changed):
            require_douyin_comment_list(payload, "comments")

    assert 'require_mapping_field(data, "data")' in patch
    assert 'require_mapping_list_field(videos_res, "result")' in patch
    assert 'require_mapping_field(comments_res, "cursor")' in patch
    assert 'require_bilibili_comment_list(comments_res, "replies")' in patch
    assert (
        'require_bilibili_comment_list({"replies": pinned_comments}, "replies")'
        in patch
    )
    assert "_yike_bilibili_login_state(response)" in patch
    assert "_yike_bilibili_video_detail(" in patch
    assert 'require_int_field(data, "status_code")' in patch
    assert "require_douyin_search_page(posts_res)" in patch
    assert 'require_douyin_comment_list(comments_res, "comments")' in patch
    assert "def require_douyin_search_page(" in patch


def test_douyin_empty_search_validates_required_metadata_before_no_data():
    patch = PATCH_PATH.read_text(encoding="utf-8")
    runtime_source = _new_file_added_by_patch(patch, "tools/yike_runtime.py")
    assert runtime_source is not None
    namespace: dict[str, object] = {}
    exec(compile(runtime_source, "tools/yike_runtime.py", "exec"), namespace)
    response_changed = namespace["YikePlatformResponseChanged"]
    require_search_page = namespace.get("require_douyin_search_page")
    assert callable(require_search_page)

    assert require_search_page(
        {"data": [], "extra": {"logid": "empty-page-id"}}
    ) == ([], "empty-page-id")
    for payload in (
        {"data": []},
        {"data": [], "extra": None},
        {"data": [], "extra": {}},
        {"data": [], "extra": {"logid": ""}},
    ):
        with pytest.raises(response_changed):
            require_search_page(payload)

    section_start = patch.index(
        "diff --git a/media_platform/douyin/core.py "
        "b/media_platform/douyin/core.py"
    )
    section_end = patch.find("\ndiff --git ", section_start + 1)
    section = patch[section_start : section_end if section_end >= 0 else None]

    page_check = section.index(
        "post_list, dy_search_id = require_douyin_search_page(posts_res)"
    )
    empty_branch = section.index("if not post_list:")

    assert page_check < empty_branch


def test_exact_patch_maps_transport_and_playwright_network_errors_explicitly(
    monkeypatch,
):
    patch = PATCH_PATH.read_text(encoding="utf-8")
    runtime_source = _new_file_added_by_patch(patch, "tools/yike_runtime.py")
    assert runtime_source is not None
    from types import ModuleType

    class PlaywrightTimeoutError(Exception):
        pass

    playwright = ModuleType("playwright")
    async_api = ModuleType("playwright.async_api")
    async_api.TimeoutError = PlaywrightTimeoutError
    playwright.async_api = async_api
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.async_api", async_api)
    namespace: dict[str, object] = {}
    exec(compile(runtime_source, "tools/yike_runtime.py", "exec"), namespace)
    classify = namespace["classify_error"]

    assert classify(PlaywrightTimeoutError("navigation timeout")) == (
        "COLLECTION_NETWORK_FAILED",
        45,
    )
    assert classify(Exception("net::ERR_TIMED_OUT")) == (
        "COLLECTION_PROCESS_FAILED",
        48,
    )
    assert patch.count("except httpx.RequestError as error:") >= 3
    assert patch.count("except PlaywrightError as error:") >= 2
    assert "raise YikeNetworkFailed() from error" in patch


@pytest.mark.parametrize(
    "query_text",
    [
        "keyword,second",
        "keyword\nsecond",
        "keyword\tsecond",
        "keyword\x00second",
        "x" * 201,
    ],
)
def test_invalid_single_keyword_fails_before_database_or_spawn(
    repository, run_id, tmp_path, monkeypatch, query_text
):
    collector = _controlled_collector(repository, tmp_path, monkeypatch)
    monkeypatch.setattr(
        repository,
        "begin_collection",
        lambda *args, **kwargs: pytest.fail("invalid query reached repository"),
    )
    monkeypatch.setattr(
        "app.collector.run_supervised_process",
        lambda *args, **kwargs: pytest.fail("invalid query must not spawn"),
    )

    with pytest.raises(ValueError, match="query"):
        collector.collect(_request(run_id, query_text=query_text))

    assert repository.connection.execute("SELECT count(*) FROM campaigns").fetchone()[0] == 0
    assert not collector.work_root.exists()


@pytest.mark.parametrize(
    "query_text",
    [
        "keyword,second",
        "keyword\nsecond",
        "keyword\tsecond",
        "keyword\x00second",
        "x" * 201,
    ],
)
def test_repository_rejects_invalid_single_keyword_identity(
    repository, run_id, query_text
):
    with pytest.raises(ValueError, match="query"):
        repository.begin_collection(
            run_id=run_id,
            collection_run_id=str(uuid4()),
            platform="bili",
            query_cluster="sales-agent",
            query_text=query_text,
            max_contents=5,
            max_comments_per_content=20,
            started_by="d03-remediation-test",
            runtime_lock_sha256="a" * 64,
            backend="MEDIACRAWLER_AUTHORIZED",
        )

    assert repository.connection.execute("SELECT count(*) FROM campaigns").fetchone()[0] == 0
    assert repository.connection.execute("SELECT count(*) FROM collection_runs").fetchone()[0] == 0
