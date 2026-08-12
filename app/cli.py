import argparse

import uvicorn

from app.config import Settings
from app.web import create_app


def web() -> None:
    settings = Settings.from_env()
    uvicorn.run(create_app(settings), host=settings.bind_host, port=settings.bind_port)


def collector() -> None:
    parser = argparse.ArgumentParser(description="Collector bootstrap; collection is not implemented yet.")
    parser.add_argument("command", choices=("collect",))
    parser.parse_args()
    parser.error("collection is not implemented in the bootstrap task")
