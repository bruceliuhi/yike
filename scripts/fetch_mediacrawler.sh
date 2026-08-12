#!/usr/bin/env bash
set -euo pipefail

readonly repository_url="https://github.com/NanmiCoder/MediaCrawler.git"
readonly pinned_commit="439509782cc2991c8ef7648e178d5847b0545798"
readonly destination="${1:?usage: fetch_mediacrawler.sh ABSOLUTE_DESTINATION}"

if [[ "${destination}" != /* ]]; then
  echo "destination must be absolute" >&2
  exit 2
fi
if [[ -e "${destination}" ]]; then
  echo "destination already exists" >&2
  exit 2
fi

git clone --filter=blob:none "${repository_url}" "${destination}"
git -C "${destination}" checkout --detach "${pinned_commit}"
test "$(git -C "${destination}" rev-parse HEAD)" = "${pinned_commit}"
printf '%s\n' "${pinned_commit}" > "${destination}/.mediacrawler-commit"
