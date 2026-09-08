from __future__ import annotations

import os

import uvicorn

from pilot.db import PilotDatabase
from pilot.store import PilotStore
from pilot.web import build_app


def web():
    database = PilotDatabase.from_environment()
    database.migrate()
    secret = os.environ.get("YIKE_PILOT_AUTH_SECRET", "").strip()
    if not secret:
        raise RuntimeError("YIKE_PILOT_AUTH_SECRET is required")
    app = build_app(PilotStore(database), auth_secret=secret)
    uvicorn.run(app, host=os.environ.get("YIKE_PILOT_HOST", "127.0.0.1"), port=int(os.environ.get("YIKE_PILOT_PORT", "8787")))
