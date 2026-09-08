#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ -z "${YIKE_PILOT_DATABASE_URL:-}" ]]; then
  echo "YIKE_PILOT_DATABASE_URL is required" >&2
  exit 2
fi
backup_path="${1:-}"
passphrase_file="${YIKE_PILOT_BACKUP_PASSPHRASE_FILE:-}"
if [[ -z "$backup_path" || "$backup_path" == -* || "$backup_path" != *.enc ]]; then
  echo "usage: YIKE_PILOT_BACKUP_PASSPHRASE_FILE=/secure/passphrase backup_pilot.sh /explicit/path/pilot-YYYYMMDD.dump.enc" >&2
  exit 2
fi
if [[ -z "$passphrase_file" || ! -r "$passphrase_file" ]]; then
  echo "YIKE_PILOT_BACKUP_PASSPHRASE_FILE must point to a readable secret outside the repository" >&2
  exit 2
fi
if [[ -e "$backup_path" ]]; then
  echo "refusing to overwrite existing backup: $backup_path" >&2
  exit 2
fi
pg_dump --format=custom --no-owner --file=- "$YIKE_PILOT_DATABASE_URL" \
  | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass "file:$passphrase_file" -out "$backup_path"
echo "encrypted backup created: $backup_path"
