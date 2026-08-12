import json
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

import pytest

from app.collector import CollectionRequest, Collector
from app.collectors import normalize_bilibili, normalize_douyin
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
    ("normalizer", "content", "comment"),
    [
        (
            normalize_bilibili,
            {
                "video_id": "source-time-bili",
                "bvid": "BV1TIME",
                "title": "source",
                "creator_hash": "source-author",
                "create_time": 1000,
            },
            {
                "comment_id": "comment-time-bili",
                "content": "comment",
                "creator_hash": "comment-author",
                "create_time": 2000,
            },
        ),
        (
            normalize_douyin,
            {
                "aweme_id": "source-time-dy",
                "title": "source",
                "creator_hash": "source-author",
                "create_time": 1000,
            },
            {
                "comment_id": "comment-time-dy",
                "content": "comment",
                "creator_hash": "comment-author",
                "create_time": 2000,
            },
        ),
    ],
)
def test_source_and_comment_published_times_are_stored_separately(
    repository, run_id, normalizer, content, comment
):
    item = normalizer({"content": content, "comment": comment})

    imported = repository.import_signal(run_id, item)
    row = repository.connection.execute(
        """
        SELECT so.published_at, si.published_at
        FROM signals si JOIN sources so ON so.source_id = si.source_id
        WHERE si.signal_id = ?
        """,
        (imported.signal_id,),
    ).fetchone()

    assert tuple(row) == (
        "1970-01-01T00:16:40Z",
        "1970-01-01T00:33:20Z",
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
    ("field", "value"),
    [
        ("mvp_run_id", "../outside"),
        ("collection_run_id", "nested/escape"),
    ],
)
def test_run_identifiers_cannot_escape_output_root(collector, run_id, field, value):
    with pytest.raises(ValueError, match="identifier"):
        collector.collect(request(run_id, **{field: value}))

    assert not collector.work_root.exists()


def test_symlinked_run_ancestor_cannot_redirect_output(collector, repository, run_id):
    collector.work_root.mkdir(parents=True)
    real_run_dir = collector.work_root / "real-run"
    real_run_dir.mkdir()
    (collector.work_root / run_id).symlink_to(real_run_dir, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        collector.collect(request(run_id))

    assert repository.connection.execute(
        "SELECT COUNT(*) FROM collection_runs"
    ).fetchone()[0] == 0


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


def test_runtime_status_is_required_even_when_process_exits_zero(
    collector, run_id
):
    result = collector.collect(request(run_id, query_text="__missing_status__"))

    assert (result.status, result.error_code) == (
        "FAILED",
        "COLLECTION_PROCESS_FAILED",
    )


def test_fixture_exit_code_without_matching_structured_status_fails_closed(
    collector, run_id
):
    result = collector.collect(request(run_id, query_text="__exit_only_verification__"))

    assert (result.status, result.error_code) == (
        "FAILED",
        "COLLECTION_PROCESS_FAILED",
    )


def test_runtime_marker_spoof_without_git_checkout_is_rejected(
    repository, tmp_path, run_id
):
    runtime = tmp_path / "spoof-runtime"
    shutil.copytree(FAKE_RUNTIME, runtime)
    collector = Collector(
        repository=repository,
        runtime_path=runtime,
        work_root=tmp_path / "work",
        python_executable=sys.executable,
    )

    result = collector.collect(request(run_id))

    assert (result.status, result.error_code) == (
        "BLOCKED_INPUT",
        "COLLECTION_RUNTIME_MISMATCH",
    )


def test_output_directory_creation_failure_finishes_collection(
    collector, repository, run_id, monkeypatch
):
    original_mkdir = Path.mkdir

    def fail_collection_mkdir(path, *args, **kwargs):
        if collector.work_root in path.parents:
            raise OSError("read only")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_collection_mkdir)
    collection_request = request(run_id)

    result = collector.collect(collection_request)

    assert (result.status, result.error_code) == (
        "FAILED",
        "COLLECTION_OUTPUT_FAILED",
    )
    assert repository.connection.execute(
        "SELECT state FROM collection_runs WHERE collection_run_id = ?",
        (collection_request.collection_run_id,),
    ).fetchone()[0] == "FAILED"


def test_cli_validation_error_emits_one_terminal_json(tmp_path):
    environment = {
        **dict(os.environ),
        "YIKE_MVP_ROOT": str(tmp_path / "runtime"),
        "YIKE_MEDIACRAWLER_PATH": str(FAKE_RUNTIME),
    }
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.cli import collector; collector()",
            "collect",
            "--platform",
            "bili",
            "--mvp-run-id",
            "../bad-run",
            "--query-cluster",
            "sales",
            "--query-text",
            "query",
            "--max-videos",
            "0",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    payload = json.loads(process.stdout)
    assert process.returncode != 0
    assert payload["status"] == "FAILED"
    assert payload["error_code"] == "COLLECTION_REQUEST_INVALID"
    assert process.stdout.count("\n") == 1


def test_cli_setup_error_emits_one_terminal_json(tmp_path):
    invalid_root = tmp_path / "not-a-directory"
    invalid_root.write_text("file", encoding="utf-8")
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.cli import collector; collector()",
            "collect",
            "--platform",
            "bili",
            "--mvp-run-id",
            str(uuid4()),
            "--query-cluster",
            "sales",
            "--query-text",
            "query",
        ],
        cwd=PROJECT_ROOT,
        env={**dict(os.environ), "YIKE_MVP_ROOT": str(invalid_root)},
        capture_output=True,
        text=True,
        check=False,
    )

    payload = json.loads(process.stdout)
    assert process.returncode != 0
    assert payload["status"] == "FAILED"
    assert payload["error_code"] == "COLLECTION_SETUP_FAILED"
    assert process.stdout.count("\n") == 1


def test_lock_declares_hashed_ordered_governance_patchset():
    lock = json.loads((PROJECT_ROOT / "vendor" / "mediacrawler.lock").read_text())

    assert [patch["path"] for patch in lock["patches"]] == [
        "vendor/patches/mediacrawler/0001-yike-controlled-runtime.patch",
    ]
    for patch in lock["patches"]:
        payload = (PROJECT_ROOT / patch["path"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == patch["sha256"]
    assert lock["patchset_sha256"]
    assert lock["patched_tree_sha256"]


def test_lock_and_fetch_script_define_a_frozen_playwright_runtime():
    lock = json.loads((PROJECT_ROOT / "vendor" / "mediacrawler.lock").read_text())
    environment = lock["runtime_environment"]
    script = (PROJECT_ROOT / "scripts" / "fetch_mediacrawler.sh").read_text()

    assert environment == {
        "uv_version": "0.11.6",
        "lock_path": "uv.lock",
        "lock_sha256": "16034a88f3981a63f9667b202e348372b4f1571cbd5aeb03530c7027622d22d6",
        "manifest_path": "pyproject.toml",
        "manifest_sha256": "d9dca06609bbc55d649d10bc243bf8c304042584e2b9bb168c8dd1d301b4b549",
        "python_path": ".venv/bin/python",
        "playwright_path": ".venv/bin/playwright",
        "browser_path": ".venv/playwright-browsers",
    }
    assert all(
        token in script
        for token in ('"uv", "sync"', '"--frozen"', '"--no-dev"', '"--no-install-project"')
    )
    assert '"install", "chromium"' in script
    assert 'runtime / "main.py"), "--help"' in script


def test_production_runtime_defaults_to_its_frozen_python(repository, tmp_path):
    runtime = tmp_path / "production-runtime"
    runtime.mkdir()

    governed = Collector(
        repository=repository,
        runtime_path=runtime,
        work_root=tmp_path / "output",
    )

    assert governed.python_executable == str(runtime / ".venv" / "bin" / "python")


def test_governed_fake_runtime_uses_current_test_python(repository, tmp_path):
    governed = Collector(
        repository=repository,
        runtime_path=FAKE_RUNTIME,
        work_root=tmp_path / "output",
    )

    assert governed.python_executable == sys.executable


def test_patchset_removes_bypass_and_bounds_real_upstream_behavior():
    patches = "\n".join(
        (PROJECT_ROOT / patch).read_text()
        for patch in (
            "vendor/patches/mediacrawler/0001-yike-controlled-runtime.patch",
        )
    )

    assert "-                await self.browser_context.add_init_script" in patches
    assert "-            await self.cdp_manager.add_stealth_script()" in patches
    assert "-SAVE_LOGIN_STATE = True" in patches
    assert "+SAVE_LOGIN_STATE = False" in patches
    assert "-CDP_CONNECT_EXISTING = True" in patches
    assert "+CDP_CONNECT_EXISTING = False" in patches
    assert "-        await self.check_page_display_slider(move_step=10" in patches
    assert "+        await self.check_page_display_slider" not in patches
    assert "-        max_retries = 3" in patches
    assert "-    @retry(stop=stop_after_attempt(600)" in patches
    assert "remaining_content_count" in patches
    assert "remaining_comment_count" in patches
    assert ".yike-collection-status.json" in patches


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
