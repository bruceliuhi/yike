#!/usr/bin/env bash
set -euo pipefail

readonly project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${project_root}"

uv sync --frozen --extra dev
uv run --frozen pytest -q
uv run --frozen python -m compileall -q app tests
node --check static/app.js
git diff --check
