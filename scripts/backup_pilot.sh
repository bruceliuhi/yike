#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ -z "${YIKE_PILOT_DATABASE_URL:-}" ]]; then
  echo "YIKE_PILOT_DATABASE_URL is required" >&2
  exit 2
fi
backup_path="${1:-}"
if [[ -z "$backup_path" || "$backup_path" == -* ]]; then
  echo "usage: backup_pilot.sh /explicit/path/pilot-YYYYMMDD.dump" >&2
  exit 2
fi
if [[ -e "$backup_path" ]]; then
  echo "refusing to overwrite existing backup: $backup_path" >&2
  exit 2
fi
pg_dump --format=custom --no-owner --file="$backup_path" "$YIKE_PILOT_DATABASE_URL"
echo "backup created: $backup_path"
