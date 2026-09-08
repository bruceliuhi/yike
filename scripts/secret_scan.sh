#!/usr/bin/env bash
set -euo pipefail

# Scan tracked content for credential *values*, not harmless field names in docs.
patterns='(xsec_token=[A-Za-z0-9_-]{12,}|cookie=[A-Za-z0-9%+/=._-]{20,}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|(^|[^[:alnum:]])sk-[A-Za-z0-9]{20,})'
if matches=$(git grep -nEI "$patterns" -- ':!uv.lock' ':!docs/SKILL_VALIDATION_CP05.md' ':!docs/SKILL_OFFLINE_REVIEW_CP05.md' ':!tests/test_research_import.py' 2>/dev/null); then
  printf '%s\n' "$matches" >&2
  echo "secret-scan: potential credential value found" >&2
  exit 1
fi
echo "secret-scan: clean"
