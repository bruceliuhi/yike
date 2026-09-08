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
passphrase_file="${YIKE_PILOT_BACKUP_PASSPHRASE_FILE:-}"
if [[ -z "$backup_path" || ! -f "$backup_path" || "$backup_path" != *.enc ]]; then
  echo "usage: CONFIRM_RESTORE=YES YIKE_PILOT_BACKUP_PASSPHRASE_FILE=/secure/passphrase restore_pilot.sh /explicit/path/pilot.dump.enc" >&2
  exit 2
fi
if [[ -z "$passphrase_file" || ! -r "$passphrase_file" ]]; then
  echo "YIKE_PILOT_BACKUP_PASSPHRASE_FILE must point to a readable secret outside the repository" >&2
  exit 2
fi
temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/yike-pilot-restore.XXXXXX")"
trap 'rm -rf "$temp_dir"' EXIT
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass "file:$passphrase_file" -in "$backup_path" -out "$temp_dir/pilot.dump"
pg_restore --clean --if-exists --no-owner --dbname="$YIKE_PILOT_DATABASE_URL" "$temp_dir/pilot.dump"
echo "encrypted backup restored: $backup_path"
