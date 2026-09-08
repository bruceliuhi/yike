#!/usr/bin/env bash
set -euo pipefail

: "${YIKE_PILOT_DATABASE_URL:?set YIKE_PILOT_DATABASE_URL to an isolated PostgreSQL test database}"

uv run --frozen pytest -q \
  tests/test_pilot_contracts.py \
  tests/test_pilot_web.py \
  tests/test_research_import.py \
  tests/test_pilot_import_cli.py \
  tests/test_pilot_provision_cli.py \
  tests/test_backup_scripts.py
uv run --frozen python -m compileall -q pilot tests
git diff --check
scripts/secret_scan.sh
