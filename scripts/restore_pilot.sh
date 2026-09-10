#!/usr/bin/env bash
set -euo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"

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
mac_path="${backup_path}.mac"
if [[ ! -f "$mac_path" || ! -r "$mac_path" ]]; then
  echo "backup integrity sidecar is required: $mac_path" >&2
  exit 2
fi
if [[ -z "$passphrase_file" || ! -f "$passphrase_file" || ! -r "$passphrase_file" || ! -s "$passphrase_file" ]] || ! LC_ALL=C grep -q '[^[:space:]]' "$passphrase_file"; then
  echo "YIKE_PILOT_BACKUP_PASSPHRASE_FILE must point to a non-empty readable secret file outside the repository" >&2
  exit 2
fi
passphrase_realpath="$(cd -- "$(dirname -- "$passphrase_file")" && pwd)/$(basename -- "$passphrase_file")"
if command -v realpath >/dev/null 2>&1; then
  passphrase_realpath="$(realpath "$passphrase_file")"
fi
case "$passphrase_realpath" in
  "$repo_root"|"$repo_root"/*)
    echo "YIKE_PILOT_BACKUP_PASSPHRASE_FILE must be outside the repository" >&2
    exit 2
    ;;
esac
passphrase_mode="$(stat -f '%Lp' "$passphrase_realpath" 2>/dev/null || true)"
if [[ ! "$passphrase_mode" =~ ^[0-9]+$ ]]; then
  passphrase_mode="$(stat -c '%a' "$passphrase_realpath" 2>/dev/null || true)"
fi
if [[ ! "$passphrase_mode" =~ ^[0-9]+$ ]] || (( 10#$passphrase_mode % 100 != 0 )); then
  echo "YIKE_PILOT_BACKUP_PASSPHRASE_FILE must not be readable by group or other users" >&2
  exit 2
fi
temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/yike-pilot-restore.XXXXXX")"
trap 'rm -f -- "$temp_dir/backup.enc" "$temp_dir/pilot.dump"; rmdir -- "$temp_dir"' EXIT
# Authenticate and decrypt the same private snapshot, not a mutable source path.
cp -- "$backup_path" "$temp_dir/backup.enc"
python3 "$script_dir/backup_auth.py" verify "$temp_dir/backup.enc" "$passphrase_file" "$mac_path"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass "file:$passphrase_file" -in "$temp_dir/backup.enc" -out "$temp_dir/pilot.dump"
pg_restore --clean --if-exists --no-owner --dbname="$YIKE_PILOT_DATABASE_URL" "$temp_dir/pilot.dump"
echo "authenticated encrypted backup restored: $backup_path"
