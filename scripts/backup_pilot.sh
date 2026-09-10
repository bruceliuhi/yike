#!/usr/bin/env bash
set -euo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"

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
backup_realpath="$(cd -- "$(dirname -- "$backup_path")" && pwd -P)/$(basename -- "$backup_path")"
case "$backup_realpath" in
  "$repo_root"|"$repo_root"/*)
    echo "backup destination must be outside the repository" >&2
    exit 2
    ;;
esac
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
if [[ -e "$backup_path" ]]; then
  echo "refusing to overwrite existing backup: $backup_path" >&2
  exit 2
fi
mac_path="${backup_path}.mac"
if [[ -e "$mac_path" ]]; then
  echo "refusing to overwrite existing backup MAC: $mac_path" >&2
  exit 2
fi
temp_dir=""
secret_temp_dir=""
secret_snapshot=""
published_backup=0
complete=0
cleanup() {
  if (( ! complete && published_backup )) && [[ -n "$temp_dir" && "$backup_path" -ef "$temp_dir/pilot.dump.enc" ]]; then
    rm -f -- "$backup_path"
  fi
  if [[ -n "$temp_dir" ]]; then
    rm -f -- "$temp_dir/pilot.dump.enc" "$temp_dir/pilot.dump.enc.mac"
    rmdir -- "$temp_dir"
  fi
  if [[ -n "$secret_temp_dir" ]]; then
    rm -f -- "$secret_snapshot"
    rmdir -- "$secret_temp_dir"
  fi
}
trap cleanup EXIT
temp_dir="$(mktemp -d "$(dirname -- "$backup_path")/.yike-backup.XXXXXX")"
secret_temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/yike-pilot-secret.XXXXXX")"
secret_snapshot="$secret_temp_dir/passphrase.snapshot"
python3 "$script_dir/backup_auth.py" snapshot "$passphrase_file" "$secret_snapshot"
pg_dump --format=custom --no-owner "$YIKE_PILOT_DATABASE_URL" \
  | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass "file:$secret_snapshot" -out "$temp_dir/pilot.dump.enc"
python3 "$script_dir/backup_auth.py" create "$temp_dir/pilot.dump.enc" "$secret_snapshot" "$temp_dir/pilot.dump.enc.mac"
# Link publication is no-clobber even if a target appeared after the precheck.
python3 "$script_dir/backup_auth.py" publish "$temp_dir/pilot.dump.enc" "$backup_path"
published_backup=1
python3 "$script_dir/backup_auth.py" publish "$temp_dir/pilot.dump.enc.mac" "$mac_path"
complete=1
echo "authenticated encrypted backup created: $backup_path (MAC: $mac_path)"
