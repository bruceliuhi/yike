#!/usr/bin/env bash
set -euo pipefail

if [[ "${CONFIRM_RESTORE:-}" != "YES" ]]; then
  echo "set CONFIRM_RESTORE=YES only after selecting an isolated restore target" >&2
  exit 2
fi
if [[ -z "${YIKE_PILOT_DATABASE_URL:-}" ]]; then
  echo "YIKE_PILOT_DATABASE_URL is required" >&2
  exit 2
fi
backup_path="${1:-}"
if [[ -z "$backup_path" || ! -f "$backup_path" ]]; then
  echo "usage: CONFIRM_RESTORE=YES restore_pilot.sh /explicit/path/pilot.dump" >&2
  exit 2
fi
pg_restore --clean --if-exists --no-owner --dbname="$YIKE_PILOT_DATABASE_URL" "$backup_path"
echo "restore completed: $backup_path"
