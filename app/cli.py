import argparse
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

import uvicorn

from app.collector import CollectionRequest, Collector
from app.config import Settings
from app.repository import Repository
from app.web import create_app


def web() -> None:
    settings = Settings.from_env()
    uvicorn.run(create_app(settings), host=settings.bind_host, port=settings.bind_port)


class _CollectorArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def _print_terminal(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def collector() -> None:
    collection_run_id = str(uuid4())
    terminal: dict[str, object] = {
        "schema_version": "DISCOVERY_COLLECTION_V1",
        "mvp_run_id": None,
        "collection_run_id": collection_run_id,
        "platform": None,
        "status": "FAILED",
        "raw_count": 0,
        "unique_count": 0,
        "error_code": "COLLECTION_REQUEST_INVALID",
    }
    parser = _CollectorArgumentParser(
        description="Run one authorized discovery collection."
    )
    parser.add_argument("command", choices=("collect",))
    parser.add_argument("--platform", choices=("bili", "dy", "douyin"), required=True)
    parser.add_argument("--mvp-run-id", required=True)
    parser.add_argument("--collection-run-id", default=None)
    parser.add_argument("--query-cluster", required=True)
    parser.add_argument("--query-text", required=True)
    parser.add_argument("--max-videos", "--max-contents", dest="max_contents", type=int, default=5)
    parser.add_argument(
        "--max-comments-per-video",
        "--max-comments-per-content",
        dest="max_comments_per_content",
        type=int,
        default=20,
    )
    parser.add_argument("--started-by", required=True)
    try:
        arguments = parser.parse_args()
        collection_run_id = arguments.collection_run_id or collection_run_id
        platform = "dy" if arguments.platform == "douyin" else arguments.platform
        terminal.update(
            mvp_run_id=arguments.mvp_run_id,
            collection_run_id=collection_run_id,
            platform=platform,
        )
        request = CollectionRequest(
            mvp_run_id=arguments.mvp_run_id,
            collection_run_id=collection_run_id,
            platform=platform,
            query_cluster=arguments.query_cluster,
            query_text=arguments.query_text,
            max_contents=arguments.max_contents,
            max_comments_per_content=arguments.max_comments_per_content,
            started_by=arguments.started_by,
        )
        Collector._validate_request(request)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        _print_terminal(terminal)
        raise SystemExit(2) from None

    repository = None
    try:
        settings = Settings.from_env()
        runtime_path = Path(
            os.getenv(
                "YIKE_MEDIACRAWLER_PATH", settings.runtime_dir / "mediacrawler"
            )
        )
        repository = Repository.from_settings(settings)
        result = Collector(
            repository=repository,
            runtime_path=runtime_path,
            work_root=settings.runtime_dir / "runs",
        ).collect(request)
    except Exception as error:
        print(str(error), file=sys.stderr)
        terminal["error_code"] = "COLLECTION_SETUP_FAILED"
        _print_terminal(terminal)
        raise SystemExit(1) from None
    finally:
        if repository is not None:
            repository.connection.close()

    terminal.update(
        status=result.status,
        raw_count=result.raw_count,
        unique_count=result.unique_count,
        error_code=result.error_code,
    )
    _print_terminal(terminal)
    if result.status not in ("SUCCEEDED", "SUCCEEDED_NO_DATA"):
        raise SystemExit(1)
