#!/usr/bin/env bash
# Commit what a data run wrote under data/, and push it onto main.
#
# A run lasts hours, so main may have moved meanwhile: the commit is rebased onto it.
# Conflicts on the two derived files are settled here instead of failing the run:
# index.json is written again from the files on disk, and citations.json keeps this
# run's counts (the daily citations step asks again for any count it lacks). A conflict
# on any other file stops without pushing, and so does a push refused three times: the
# commit is then saved as data-commit.bundle, which the workflow uploads. To recover it:
#   git fetch data-commit.bundle HEAD:recovered-data
#
# With --keep, the commit is only saved as data-commit.bundle, never pushed: for data that
# failed validation.
#
# Writes pushed=true or pushed=false to $GITHUB_OUTPUT.
# Usage: commit-data.sh [--keep] MESSAGE
set -euo pipefail

keep=false
if [ "$1" = "--keep" ]; then
  keep=true
  shift
fi
message=$1
output=${GITHUB_OUTPUT:-/dev/null}

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add data
if git diff --cached --quiet; then
  echo "No new data."
  echo "pushed=false" >>"$output"
  exit 0
fi
git commit --quiet --message "$message"

keep_commit() {
  git bundle create data-commit.bundle origin/main..HEAD
  echo "pushed=false" >>"$output"
}

if [ "$keep" = true ]; then
  keep_commit
  exit 0
fi

# Called while the rebase stops on this run's commit. Errexit does not apply inside a
# function called from a condition, hence the explicit returns.
settle_conflicts() {
  local path
  while IFS= read -r path; do
    case $path in
      data/index.json) ;;
      # During a rebase, "theirs" is the commit being replayed: this run's.
      data/*/citations.json) git checkout --theirs -- "$path" || return 1 ;;
      *)
        echo "::error::$path changed both in this run and on main; nothing was pushed."
        return 1
        ;;
    esac
  done < <(git diff --name-only --diff-filter=U)
  uv run --no-dev preprint-radar index || return 1
  git add data || return 1
  GIT_EDITOR=true git rebase --continue
}

for attempt in 1 2 3; do
  git fetch --quiet origin main
  if ! git rebase --quiet origin/main; then
    if ! settle_conflicts; then
      git rebase --abort
      keep_commit
      exit 1
    fi
  fi
  if git push --quiet origin HEAD:main; then
    echo "pushed=true" >>"$output"
    exit 0
  fi
  echo "::warning::The push was refused (attempt $attempt of 3)."
  if [ "$attempt" -lt 3 ]; then sleep $((attempt * 15)); fi
done
echo "::error::The data commit could not be pushed; nothing was pushed."
keep_commit
exit 1
