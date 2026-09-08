from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import uvicorn

from pilot.db import MissingDatabaseConfiguration, PilotDatabase
from pilot.research_import import import_reviewed_bundle
from pilot.store import PilotStore
from pilot.web import build_app


def web():
    database = PilotDatabase.from_environment()
    database.migrate()
    secret = os.environ.get("YIKE_PILOT_AUTH_SECRET", "").strip()
    if not secret:
        raise RuntimeError("YIKE_PILOT_AUTH_SECRET is required")
    app = build_app(PilotStore(database), auth_secret=secret, dev_login=os.environ.get("YIKE_PILOT_DEV_LOGIN") == "1")
    uvicorn.run(app, host=os.environ.get("YIKE_PILOT_HOST", "127.0.0.1"), port=int(os.environ.get("YIKE_PILOT_PORT", "8787")))


def import_bundle(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导入已人工复核的意客 AI 商机研究包")
    parser.add_argument("--bundle", required=True, help="JSON 研究包路径")
    parser.add_argument("--user-id", required=True, help="已 provision 的试用用户 ID")
    parser.add_argument("--profile-version-id", required=True, help="已确认的业务画像版本 ID")
    args = parser.parse_args(argv)
    try:
        database = PilotDatabase.from_environment()
        database.migrate()
        bundle = json.loads(Path(args.bundle).read_text(encoding="utf-8"))
        results = import_reviewed_bundle(PilotStore(database), args.user_id, args.profile_version_id, bundle)
    except (MissingDatabaseConfiguration, OSError, json.JSONDecodeError, ValueError, KeyError) as error:
        print(f"yike-pilot-import: {error}", file=sys.stderr)
        return 2
    created = sum(1 for item in results if item.get("created"))
    print(json.dumps({"bundle_id": bundle["bundle_id"], "created": created, "duplicates": len(results) - created, "total": len(results)}, ensure_ascii=False))
    return 0
