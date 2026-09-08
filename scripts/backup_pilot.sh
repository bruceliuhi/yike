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
created=1
mac_tmp="${mac_path}.tmp.$$"
trap 'if (( created )); then rm -f -- "$backup_path" "$mac_tmp" "$mac_path"; fi' EXIT
pg_dump --format=custom --no-owner "$YIKE_PILOT_DATABASE_URL" \
  | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass "file:$passphrase_file" -out "$backup_path"
openssl dgst -sha256 -mac HMAC -macopt "key:file:$passphrase_file" -binary "$backup_path" > "$mac_tmp"
mv -- "$mac_tmp" "$mac_path"
chmod 600 "$mac_path"
created=0
trap - EXIT
echo "authenticated encrypted backup created: $backup_path (MAC: $mac_path)"
