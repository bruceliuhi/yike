#!/usr/bin/env bash
set -euo pipefail

base_url="${1:-}"
expected_revision="${2:-${YIKE_EXPECTED_RELEASE_REVISION:-}}"
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
case "$base_url" in
  *'@'*|*'?'*|*'#'*)
    echo "CP-06 probe URL must not contain userinfo, query, or fragment" >&2
    exit 2
    ;;
esac
base_url="${base_url%/}"

curl_https=(curl --fail --silent --show-error --location --max-time 10 --proto '=https' --proto-redir '=https')
health="$("${curl_https[@]}" "$base_url/healthz")"
ready="$("${curl_https[@]}" "$base_url/readyz")"
if [[ "$health" != *'"status":"ok"'* || "$ready" != *'"status":"ready"'* ]]; then
  echo "CP-06 probe returned unexpected health/readiness payload" >&2
  exit 1
fi
release_headers="$("${curl_https[@]}" --dump-header - --output /dev/null "$base_url/healthz")"
release_revision="$(printf '%s\n' "$release_headers" | awk 'tolower($1)=="x-yike-release-revision:" {print $2; exit}' | tr -d '\r')"
if [[ -n "$expected_revision" && "$release_revision" != "$expected_revision" ]]; then
  echo "CP-06 probe revision mismatch: expected $expected_revision, got ${release_revision:-missing}" >&2
  exit 1
fi
if [[ -n "$expected_revision" && -z "$release_revision" ]]; then
  echo "CP-06 probe did not return x-yike-release-revision" >&2
  exit 1
fi
printf 'healthz=%s\nreadyz=%s\nrelease_revision=%s\n' "$health" "$ready" "${release_revision:-unknown}"
