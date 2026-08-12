import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from app.config import Settings
from app.repository import Repository


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FAKE_RUNTIME = PROJECT_ROOT / "tests" / "fixtures" / "fake_mediacrawler"
TERMINAL_FIELDS = {
    "schema_version",
    "mvp_run_id",
    "collection_run_id",
    "platform",
    "status",
    "raw_count",
    "unique_count",
    "error_code",
}


def test_collect_cli_returns_exactly_one_terminal_json(tmp_path):
    runtime_root = tmp_path / "runtime"
    settings = Settings(
        data_dir=runtime_root / "data",
        runtime_dir=runtime_root / "collector",
    )
    repository = Repository.from_settings(settings)
    run_id = repository.create_run(["bili", "dy"])
    repository.connection.close()
    collection_run_id = str(uuid4())

    process = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.cli import collector; collector()",
            "collect",
            "--platform",
            "bili",
            "--mvp-run-id",
            run_id,
            "--collection-run-id",
            collection_run_id,
            "--query-cluster",
            "acquisition",
            "--query-text",
            "__empty__",
            "--max-contents",
            "1",
            "--max-comments-per-content",
            "1",
        ],
        cwd=PROJECT_ROOT,
        env={
            **os.environ,
            "YIKE_MVP_ROOT": str(runtime_root),
            "YIKE_MEDIACRAWLER_PATH": str(FAKE_RUNTIME),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert process.returncode == 0, process.stderr
    assert process.stdout.count("\n") == 1
    payload = json.loads(process.stdout)
    assert set(payload) == TERMINAL_FIELDS
    assert payload == {
        "schema_version": "DISCOVERY_COLLECTION_V1",
        "mvp_run_id": run_id,
        "collection_run_id": collection_run_id,
        "platform": "bili",
        "status": "SUCCEEDED_NO_DATA",
        "raw_count": 0,
        "unique_count": 0,
        "error_code": None,
    }


def test_daily_limit_cli_returns_one_stable_terminal_without_new_db_rows(tmp_path):
    runtime_root = tmp_path / "runtime"
    settings = Settings(
        data_dir=runtime_root / "data",
        runtime_dir=runtime_root / "collector",
    )
    repository = Repository.from_settings(settings)
    run_id = repository.create_run(["bili", "dy"])
    for index in range(8):
        repository.begin_collection(
            run_id=run_id,
            collection_run_id=str(uuid4()),
            platform="bili",
            query_cluster="acquisition",
            query_text=f"query-{index}",
            max_contents=1,
            max_comments_per_content=1,
        )
        collection_run_id = repository.connection.execute(
            "SELECT collection_run_id FROM collection_runs WHERE state = 'RUNNING'"
        ).fetchone()[0]
        repository.finish_collection(
            collection_run_id,
            state="SUCCEEDED_NO_DATA",
            raw_count=0,
            unique_count=0,
            error_code=None,
        )
    repository.connection.close()
    rejected_collection_run_id = str(uuid4())

    process = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.cli import collector; collector()",
            "collect",
            "--platform",
            "bili",
            "--mvp-run-id",
            run_id,
            "--collection-run-id",
            rejected_collection_run_id,
            "--query-cluster",
            "acquisition",
            "--query-text",
            "rejected-query",
            "--max-contents",
            "1",
            "--max-comments-per-content",
            "1",
        ],
        cwd=PROJECT_ROOT,
        env={
            **os.environ,
            "YIKE_MVP_ROOT": str(runtime_root),
            "YIKE_MEDIACRAWLER_PATH": str(FAKE_RUNTIME),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert process.returncode == 1
    assert process.stdout.count("\n") == 1
    assert json.loads(process.stdout) == {
        "schema_version": "DISCOVERY_COLLECTION_V1",
        "mvp_run_id": run_id,
        "collection_run_id": rejected_collection_run_id,
        "platform": "bili",
        "status": "BLOCKED_INPUT",
        "raw_count": 0,
        "unique_count": 0,
        "error_code": "COLLECTION_DAILY_LIMIT_REACHED",
    }
    repository = Repository.from_settings(settings)
    assert repository.connection.execute(
        "SELECT count(*) FROM campaigns WHERE platform = 'bili'"
    ).fetchone()[0] == 8
    assert repository.connection.execute(
        "SELECT count(*) FROM collection_runs WHERE platform = 'bili'"
    ).fetchone()[0] == 8
    repository.connection.close()
