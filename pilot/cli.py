from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import uvicorn
import psycopg

from pilot.db import MissingDatabaseConfiguration, PilotDatabase
from pilot.auth import issue_token
from pilot.research_import import import_reviewed_bundle
from pilot.store import PilotStore
from pilot.web import build_app


def web():
    database = PilotDatabase.from_environment()
    secret = os.environ.get("YIKE_PILOT_AUTH_SECRET", "").strip()
    if not secret:
        raise RuntimeError("YIKE_PILOT_AUTH_SECRET is required")
    app = build_app(PilotStore(database), auth_secret=secret, dev_login=os.environ.get("YIKE_PILOT_DEV_LOGIN") == "1")
    proxy_headers = os.environ.get("YIKE_PILOT_PROXY_HEADERS", "0") == "1"
    forwarded_allow_ips = os.environ.get("YIKE_PILOT_FORWARDED_ALLOW_IPS", "").strip()
    if proxy_headers and not forwarded_allow_ips:
        raise RuntimeError("YIKE_PILOT_FORWARDED_ALLOW_IPS is required when proxy headers are enabled")
    if any(item.strip() == "*" or item.strip().endswith("/0") for item in forwarded_allow_ips.split(",")):
        raise RuntimeError("YIKE_PILOT_FORWARDED_ALLOW_IPS must not contain wildcard or /0 network")
    uvicorn.run(
        app,
        host=os.environ.get("YIKE_PILOT_HOST", "127.0.0.1"),
        port=int(os.environ.get("YIKE_PILOT_PORT", "8787")),
        access_log=False,
        proxy_headers=proxy_headers,
        forwarded_allow_ips=forwarded_allow_ips,
    )


def migrate(argv: list[str] | None = None) -> int:
    """Run privileged schema migrations from a trusted admin environment."""
    parser = argparse.ArgumentParser(description="意客 AI 客户试用数据库迁移（仅管理员执行）")
    parser.parse_args(argv)
    try:
        database = PilotDatabase.from_admin_environment()
        database.migrate()
        print(json.dumps({"status": "migrated"}, ensure_ascii=False))
        return 0
    except (MissingDatabaseConfiguration, OSError, psycopg.Error, RuntimeError) as error:
        print(f"yike-pilot-migrate: {error}", file=sys.stderr)
        return 2


def import_bundle(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导入已人工复核的意客 AI 商机研究包")
    parser.add_argument("--bundle", required=True, help="JSON 研究包路径")
    parser.add_argument("--user-id", required=True, help="已 provision 的试用用户 ID")
    parser.add_argument("--profile-version-id", required=True, help="已确认的业务画像版本 ID")
    args = parser.parse_args(argv)
    try:
        database = PilotDatabase.from_admin_environment()
        bundle = json.loads(Path(args.bundle).read_text(encoding="utf-8"))
        results = import_reviewed_bundle(PilotStore(database), args.user_id, args.profile_version_id, bundle)
    except (MissingDatabaseConfiguration, OSError, json.JSONDecodeError, ValueError, KeyError, psycopg.Error, RuntimeError) as error:
        print(f"yike-pilot-import: {error}", file=sys.stderr)
        return 2
    created = sum(1 for item in results if item.get("created"))
    print(json.dumps({"bundle_id": bundle["bundle_id"], "created": created, "duplicates": len(results) - created, "total": len(results)}, ensure_ascii=False))
    return 0


def provision(argv: list[str] | None = None) -> int:
    """Trusted-admin provisioning; intentionally not exposed as an HTTP route."""
    parser = argparse.ArgumentParser(description="意客 AI 受信试用账号 provisioning（仅管理员本机执行）")
    subparsers = parser.add_subparsers(dest="command", required=True)
    tenant_parser = subparsers.add_parser("tenant")
    tenant_parser.add_argument("--name", required=True)
    user_parser = subparsers.add_parser("user")
    user_parser.add_argument("--tenant-id", required=True)
    user_parser.add_argument("--email", required=True)
    token_parser = subparsers.add_parser("token")
    token_parser.add_argument("--user-id", required=True)
    token_parser.add_argument("--ttl-seconds", type=int, default=3600)
    args = parser.parse_args(argv)
    try:
        secret = os.environ.get("YIKE_PILOT_AUTH_SECRET", "").strip()
        if args.command == "token":
            if not secret:
                raise RuntimeError("YIKE_PILOT_AUTH_SECRET is required")
            if not 60 <= args.ttl_seconds <= 86_400:
                raise ValueError("ttl-seconds must be between 60 and 86400")
            print(json.dumps({"user_id": args.user_id, "token": issue_token(args.user_id, secret, ttl_seconds=args.ttl_seconds)}, ensure_ascii=False))
            return 0
        database = PilotDatabase.from_admin_environment()
        database.migrate()
        store = PilotStore(database)
        if args.command == "tenant":
            print(json.dumps({"tenant_id": store.provision_tenant(args.name)}, ensure_ascii=False))
        else:
            print(json.dumps({"user_id": store.provision_user(args.tenant_id, args.email), "tenant_id": args.tenant_id}, ensure_ascii=False))
        return 0
    except (MissingDatabaseConfiguration, OSError, ValueError, KeyError, psycopg.Error, RuntimeError) as error:
        print(f"yike-pilot-provision: {error}", file=sys.stderr)
        return 2
