#!/usr/bin/env bash
# Restore the page cache from its weekly copy when the Actions cache had no entry (OPS-1,
# SCALE-4). The cache is its only other copy, and a run that starts without it saves what
# it read alone as the newest entry, which every later run restores: the front matter of a
# year of papers, which `reextract` reads again offline, would be downloaded again at 50
# pages a day. *Update data* uploads the copy on Mondays, kept 90 days.
#
# Usage: restore-page-cache.sh, with GH_TOKEN (actions: read), GITHUB_REPOSITORY and
# RUNNER_TEMP (set by Actions); restores into .cache/front-matter.
set -euo pipefail

copy=$(gh api "repos/$GITHUB_REPOSITORY/actions/artifacts?name=front-matter&per_page=1" \
  --jq '.artifacts[] | select(.expired | not) | "\(.id) \(.created_at)"' 2>/dev/null) || copy=
if [ -z "$copy" ]; then
  echo "::warning title=Page cache not restored::No cache entry nor weekly copy: the pages are downloaded again, 50 a day"
  exit 0
fi
read -r id created <<<"$copy"
gh api "repos/$GITHUB_REPOSITORY/actions/artifacts/$id/zip" >"$RUNNER_TEMP/front-matter.zip"
mkdir -p .cache/front-matter
unzip -q -o "$RUNNER_TEMP/front-matter.zip" -d .cache/front-matter
echo "::warning title=Page cache not restored::No cache entry: restored from its weekly copy of ${created%%T*}"
