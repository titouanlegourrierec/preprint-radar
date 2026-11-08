#!/usr/bin/env bash
# The files only the weekly archive rewrites live on the orphan `data` branch, not on main
# (SCALE-8): GitHub stores their weekly versions as deltas on other years' files (2024.json
# as 2.4 MB on 2025.json, where its last version gives a few KB), which made archive/ 119 of
# the repository's 144 MB on 2026-11-08. The branch holds them at their paths under data/,
# and is squashed monthly (commit-data.sh), so that GitHub keeps a month of their history.
#
# The pipeline still reads and writes one data/: the branch is checked out in .data-branch/
# (git-ignored on main), its files copied into data/ before a run (assemble) and back after
# it (collect). Copies, not links: the store writes a file through a temporary one that it
# renames, which would replace a link.
#
# Usage: data-branch.sh COMMAND
#   assemble   copy the branch's files into data/ (the workflows, after their checkouts)
#   collect    copy data/'s files of the branch into .data-branch/ (commit-data.sh)
#   check      fail unless data/ holds every file of the branch (make's data commands)
#   pull       on a clone of yours: create .data-branch/ or bring it up to date, then
#              assemble; refuses while data/ holds changes not committed there (FORCE=1
#              drops them) or the branch commits not pushed
#   commit MESSAGE   on a clone of yours: collect, then commit data/ on both branches
#   push       on a clone of yours: push the data branch, then main; a push to the data
#              branch runs no workflow (it holds none), so Deploy site is dispatched when
#              main's push does not deploy (gh, else the command is printed)
set -euo pipefail

# Per category, under data/<category>/: keep .gitignore's list the same (test_data_branch.py).
PATHS=(archive top-recent.json scholar.json citation-gains.json topics.json trends.json cohorts.json)
BRANCH_DIR=.data-branch

# Every category either side holds.
categories() {
  local dir
  for dir in data/*/ "$BRANCH_DIR"/data/*/; do
    [ -d "$dir" ] && basename "$dir"
  done | sort -u
}

# Replace the branch's files under $2/data by those under $1/data.
copy() {
  local from=$1 to=$2 category path
  while IFS= read -r category; do
    for path in "${PATHS[@]}"; do
      rm -rf "${to:?}/data/$category/$path"
      if [ -e "$from/data/$category/$path" ]; then
        mkdir -p "$to/data/$category"
        cp -R "$from/data/$category/$path" "$to/data/$category/$path"
      fi
    done
  done < <(categories)
}

require_branch() {
  if [ ! -e "$BRANCH_DIR/.git" ]; then
    echo "::error::$BRANCH_DIR/ holds no checkout of the data branch (make data-pull)." >&2
    exit 1
  fi
}

case ${1:-} in
  assemble)
    require_branch
    copy "$BRANCH_DIR" .
    ;;
  collect)
    require_branch
    copy . "$BRANCH_DIR"
    ;;
  check)
    require_branch
    missing=$(cd "$BRANCH_DIR" && find . -path ./.git -prune -o -type f -path './data/*' -print | while IFS= read -r file; do
      [ -e "../$file" ] || echo "${file#./}"
    done)
    if [ -n "$missing" ]; then
      echo "data/ lacks files of the data branch, $(head -n 1 <<<"$missing") among them: run make data-pull." >&2
      exit 1
    fi
    ;;
  pull)
    if [ ! -d "$BRANCH_DIR" ]; then
      git fetch --quiet origin data
      git worktree add --quiet -B data "$BRANCH_DIR" origin/data
    else
      if [ "${FORCE:-}" != 1 ]; then
        copy . "$BRANCH_DIR"
        if [ -n "$(git -C "$BRANCH_DIR" status --porcelain)" ]; then
          echo "data/ holds changes to the data branch's files: commit them (make data-commit MSG=...)," >&2
          echo "or drop them (make data-pull FORCE=1)." >&2
          exit 1
        fi
      fi
      # Its last commit must be on GitHub: a squash replaces the branch's history, so it is
      # reset to GitHub's, never merged.
      known=$(git -C "$BRANCH_DIR" rev-parse --verify --quiet refs/remotes/origin/data || true)
      if [ "$(git -C "$BRANCH_DIR" rev-parse HEAD)" != "$known" ]; then
        echo "The data branch holds commits not pushed: make data-push first." >&2
        exit 1
      fi
      git -C "$BRANCH_DIR" fetch --quiet origin data
      git -C "$BRANCH_DIR" reset --quiet --hard origin/data
      git -C "$BRANCH_DIR" clean --quiet -fd
    fi
    copy "$BRANCH_DIR" .
    ;;
  commit)
    message=${2:?Usage: data-branch.sh commit MESSAGE}
    require_branch
    copy . "$BRANCH_DIR"
    git -C "$BRANCH_DIR" add -A data
    if ! git -C "$BRANCH_DIR" diff --cached --quiet; then
      git -C "$BRANCH_DIR" commit --quiet --message "$message"
      echo "Committed on the data branch."
    fi
    git add data
    if ! git diff --cached --quiet -- data; then
      git commit --quiet --message "$message" -- data
      echo "Committed on $(git branch --show-current)."
    fi
    ;;
  push)
    require_branch
    data_new=$(git -C "$BRANCH_DIR" rev-list --count origin/data..HEAD)
    # What main's push deploys by itself (deploy.yml's paths).
    main_deploys=$(git diff --name-only '@{upstream}' HEAD -- data web .github/workflows/deploy.yml 2>/dev/null || true)
    # The data branch first: main's index.json lists the archive years it holds.
    git -C "$BRANCH_DIR" push --quiet origin data
    git push --quiet
    if [ "$data_new" != 0 ] && [ -z "$main_deploys" ]; then
      if command -v gh >/dev/null; then
        gh workflow run deploy.yml --ref main
        echo "Deploy site dispatched."
      else
        echo "Deploy the site: gh workflow run deploy.yml --ref main"
      fi
    fi
    ;;
  *)
    sed -n '/^# Usage/,/^set /p' "$0" | sed '$d' | sed 's/^# \{0,1\}//' >&2
    exit 2
    ;;
esac
