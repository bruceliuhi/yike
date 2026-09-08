#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"

fail() {
  echo "cp06-preflight: $1" >&2
  exit 2
}

database_url="${YIKE_PILOT_DATABASE_URL:-}"
case "$database_url" in
  postgresql://*|postgres://*) ;;
  *) fail "database URL must use PostgreSQL" ;;
esac

image_ref="${YIKE_PILOT_IMAGE:-}"
[[ "$image_ref" =~ @sha256:[0-9a-fA-F]{64}$ ]] || fail "image reference must be digest-pinned"

auth_secret="${YIKE_PILOT_AUTH_SECRET:-}"
if [[ "${#auth_secret}" -lt 32 ]]; then
  fail "auth secret must be at least 32 characters"
fi

case "${YIKE_PILOT_DEV_LOGIN:-0}" in
  1|true|TRUE|yes|YES) fail "dev login must be disabled" ;;
esac

if [[ "${YIKE_PILOT_PROXY_HEADERS:-0}" == "1" ]]; then
  forwarded_allow_ips="${YIKE_PILOT_FORWARDED_ALLOW_IPS:-}"
  [[ -n "$forwarded_allow_ips" ]] || fail "forwarded IP allowlist is required when proxy headers are enabled"
  IFS=',' read -r -a allowlist <<< "$forwarded_allow_ips"
  for item in "${allowlist[@]}"; do
    [[ "${item//[[:space:]]/}" != "*" ]] || fail "forwarded IP allowlist must not contain wildcard"
  done
fi

passphrase_file="${YIKE_PILOT_BACKUP_PASSPHRASE_FILE:-}"
if [[ -z "$passphrase_file" || ! -f "$passphrase_file" || ! -r "$passphrase_file" || ! -s "$passphrase_file" ]] || ! LC_ALL=C grep -q '[^[:space:]]' "$passphrase_file"; then
  fail "backup passphrase file must be non-empty and readable"
fi
passphrase_realpath="$(cd -- "$(dirname -- "$passphrase_file")" && pwd)/$(basename -- "$passphrase_file")"
if command -v realpath >/dev/null 2>&1; then
  passphrase_realpath="$(realpath "$passphrase_file")"
fi
case "$passphrase_realpath" in
  "$repo_root"|"$repo_root"/*) fail "backup passphrase file must be outside the repository" ;;
esac
passphrase_mode="$(stat -f '%Lp' "$passphrase_realpath" 2>/dev/null || true)"
if [[ ! "$passphrase_mode" =~ ^[0-9]+$ ]]; then
  passphrase_mode="$(stat -c '%a' "$passphrase_realpath" 2>/dev/null || true)"
fi
if [[ ! "$passphrase_mode" =~ ^[0-9]+$ ]] || (( 10#$passphrase_mode % 100 != 0 )); then
  fail "backup passphrase file must not be readable by group or other users"
fi

echo "cp06-preflight: pass"
