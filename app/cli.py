import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

import uvicorn

from app.collector import CollectionRequest, Collector
from app.config import Settings
from app.repository import Repository
from app.web import create_app


def web() -> None:
    settings = Settings.from_env()
    uvicorn.run(create_app(settings), host=settings.bind_host, port=settings.bind_port)


def collector() -> None:
    parser = argparse.ArgumentParser(description="Run one authorized discovery collection.")
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
    parser.add_argument("--started-by", default=None)
    arguments = parser.parse_args()

    settings = Settings.from_env()
    runtime_path = Path(
        os.getenv("YIKE_MEDIACRAWLER_PATH", settings.runtime_dir / "mediacrawler")
    )
    repository = Repository.from_settings(settings)
    try:
        result = Collector(
            repository=repository,
            runtime_path=runtime_path,
            work_root=settings.runtime_dir / "runs",
        ).collect(
            CollectionRequest(
                mvp_run_id=arguments.mvp_run_id,
                collection_run_id=arguments.collection_run_id or str(uuid4()),
                platform="dy" if arguments.platform == "douyin" else arguments.platform,
                query_cluster=arguments.query_cluster,
                query_text=arguments.query_text,
                max_contents=arguments.max_contents,
                max_comments_per_content=arguments.max_comments_per_content,
                started_by=arguments.started_by,
            )
        )
    finally:
        repository.connection.close()

    print(
        json.dumps(
            {
                "schema_version": "DISCOVERY_COLLECTION_V1",
                "mvp_run_id": result.mvp_run_id,
                "collection_run_id": result.collection_run_id,
                "platform": result.platform,
                "status": result.status,
                "raw_count": result.raw_count,
                "unique_count": result.unique_count,
                "error_code": result.error_code,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
