#!/usr/bin/env bash
set -euo pipefail

base_url="${1:-}"
if [[ -z "$base_url" || "$base_url" == -* ]]; then
  echo "usage: cp06_probe.sh https://pilot.example.com" >&2
  exit 2
fi
case "$base_url" in
  https://*) ;;
  *)
    echo "CP-06 probe requires an HTTPS base URL" >&2
    exit 2
    ;;
esac
base_url="${base_url%/}"

health="$(curl --fail --silent --show-error --location --max-time 10 "$base_url/healthz")"
ready="$(curl --fail --silent --show-error --location --max-time 10 "$base_url/readyz")"
if [[ "$health" != *'"status":"ok"'* || "$ready" != *'"status":"ready"'* ]]; then
  echo "CP-06 probe returned unexpected health/readiness payload" >&2
  exit 1
fi
printf 'healthz=%s\nreadyz=%s\n' "$health" "$ready"
