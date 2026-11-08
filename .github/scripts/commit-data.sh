#!/usr/bin/env bash
# Commit what a data run wrote under data/, and push it: the files of the data branch to
# that branch, checked out in .data-branch/ (data-branch.sh, SCALE-8), the others to main.
#
# A run lasts hours, so either branch may have moved meanwhile: each commit is rebased onto
# it. Conflicts on the derived files are settled here instead of failing the run: index.json
# is written again from the files on disk, and citations.json keeps this run's counts (the
# daily citations step asks again for any count it lacks), citation-gains.json the gains
# written with them. A conflict
# on any other file stops without pushing, and so does a push refused three times: the
# commits are then saved as data-commit.bundle (main's) and data-branch.bundle, which the
# workflow uploads. To recover them:
#   git fetch data-commit.bundle HEAD:recovered-data
#   git fetch data-branch.bundle HEAD:recovered-data-branch
# The data branch is pushed first, main's index.json listing the archive years it holds.
#
# With --keep, the commits are only saved as bundles, never pushed: for data that failed
# validation. With --squash-monthly (the weekly archive), the data branch becomes a single
# commit of its tree when its first commit is older than this month, so that GitHub keeps
# a month of its history at most; a squash refused leaves it for the next run.
#
# The checkouts keep no credentials (PUB-2): a token that can push is given to this step
# only, as GH_TOKEN, and to git's fetch and push only, never written to .git/config.
#
# Writes pushed=true (either branch pushed) or pushed=false to $GITHUB_OUTPUT.
# Usage: commit-data.sh [--keep] [--squash-monthly] MESSAGE
set -euo pipefail

keep=false
squash=false
while [ $# -gt 1 ]; do
  case $1 in
    --keep) keep=true ;;
    --squash-monthly) squash=true ;;
    *) break ;;
  esac
  shift
done
message=$1
output=${GITHUB_OUTPUT:-/dev/null}
branch=.data-branch
data_branch_sh="$(dirname "$0")/data-branch.sh"

for repo in . "$branch"; do
  if [ ! -d "$repo" ]; then
    echo "::error::$branch/ holds no checkout of the data branch; nothing was pushed."
    exit 1
  fi
  git -C "$repo" config user.name "github-actions[bot]"
  git -C "$repo" config user.email "41898282+github-actions[bot]@users.noreply.github.com"
done

bash "$data_branch_sh" collect
data_commit=false
git -C "$branch" add -A data
if ! git -C "$branch" diff --cached --quiet; then
  git -C "$branch" commit --quiet --message "$message"
  data_commit=true
fi
main_commit=false
git add data
if ! git diff --cached --quiet; then
  git commit --quiet --message "$message"
  main_commit=true
fi

# git with the token for github.com, when there is one (local runs and tests have none).
remote() {
  if [ -n "${GH_TOKEN:-}" ]; then
    local basic
    basic=$(printf 'x-access-token:%s' "$GH_TOKEN" | base64 | tr -d '\n')
    git -c "http.https://github.com/.extraheader=AUTHORIZATION: basic $basic" "$@"
  else
    git "$@"
  fi
}

pushed=false
data_pushed=false
main_pushed=false

# The commits not pushed, as bundles.
keep_commits() {
  if [ "$main_commit" = true ] && [ "$main_pushed" = false ]; then
    git bundle create data-commit.bundle origin/main..HEAD
  fi
  if [ "$data_commit" = true ] && [ "$data_pushed" = false ]; then
    git -C "$branch" bundle create "$PWD/data-branch.bundle" origin/data..HEAD
  fi
  echo "pushed=$pushed" >>"$output"
}

if [ "$keep" = true ]; then
  keep_commits
  exit 0
fi

# Called while the rebase stops on this run's commit, in repository $1 (. for main) with
# upstream $2. Errexit does not apply inside a function called from a condition, hence the
# explicit returns.
settle_conflicts() {
  local repo=$1 upstream=$2 path
  while IFS= read -r path; do
    case $path in
      data/index.json) ;;
      # During a rebase, "theirs" is the commit being replayed: this run's.
      data/*/citations.json | data/*/citation-gains.json) git -C "$repo" checkout --theirs -- "$path" || return 1 ;;
      *)
        echo "::error::$path changed both in this run and on $upstream; nothing was pushed."
        return 1
        ;;
    esac
  done < <(git -C "$repo" diff --name-only --diff-filter=U)
  if [ "$repo" = . ]; then
    env -u GH_TOKEN uv run --no-dev preprint-radar index || return 1
  fi
  git -C "$repo" add data || return 1
  GIT_EDITOR=true git -C "$repo" rebase --continue
}

# Replays this run's commit in repository $1 on its upstream branch $2; moved=true when the
# branch had moved.
replay() {
  local repo=$1 upstream=$2
  remote -C "$repo" fetch --quiet origin "$upstream"
  if [ "$(git -C "$repo" rev-parse HEAD~1)" != "$(git -C "$repo" rev-parse "origin/$upstream")" ]; then
    moved=true
  fi
  if ! git -C "$repo" rebase --quiet "origin/$upstream"; then
    if ! settle_conflicts "$repo" "$([ "$repo" = . ] && echo main || echo "the data branch")"; then
      git -C "$repo" rebase --abort
      keep_commits
      exit 1
    fi
  fi
}

if [ "$data_commit" = false ] && [ "$main_commit" = false ]; then
  echo "No new data."
else
  for attempt in 1 2 3; do
    moved=false
    if [ "$data_commit" = true ] && [ "$data_pushed" = false ]; then
      replay "$branch" data
      # What main's tree is validated with below.
      if [ "$moved" = true ]; then bash "$data_branch_sh" assemble; fi
    fi
    if [ "$main_commit" = true ] && [ "$main_pushed" = false ]; then replay . main; fi
    # The tree validated before was this run's alone: the one replayed on a branch that
    # moved is validated again before it is pushed, since bot pushes skip CI (OPS-4).
    if [ "$moved" = true ] && ! env -u GH_TOKEN uv run --no-dev preprint-radar validate; then
      echo "::error::The data commit replayed on main does not validate; nothing was pushed."
      keep_commits
      exit 1
    fi
    if [ "$data_commit" = true ] && [ "$data_pushed" = false ]; then
      if remote -C "$branch" push --quiet origin HEAD:data; then
        data_pushed=true
        pushed=true
      fi
    fi
    if [ "$data_pushed" = "$data_commit" ] && [ "$main_commit" = true ] && [ "$main_pushed" = false ]; then
      if remote push --quiet origin HEAD:main; then
        main_pushed=true
        pushed=true
      fi
    fi
    if [ "$data_pushed" = "$data_commit" ] && [ "$main_pushed" = "$main_commit" ]; then break; fi
    echo "::warning::The push was refused (attempt $attempt of 3)."
    if [ "$attempt" -lt 3 ]; then sleep $((attempt * 15)); fi
  done
  if [ "$data_pushed" != "$data_commit" ] || [ "$main_pushed" != "$main_commit" ]; then
    echo "::error::The data commit could not be pushed; nothing was pushed."
    keep_commits
    exit 1
  fi
fi

# A month of history at most: a squash replaces the branch by a commit of the same tree.
# Its first commit's date needs the whole branch, which the workflows fetch.
if [ "$squash" = true ]; then
  if [ "$(git -C "$branch" rev-parse --is-shallow-repository)" = true ]; then
    remote -C "$branch" fetch --quiet --unshallow origin data
  fi
  first=$(git -C "$branch" log --max-parents=0 --format=%cs HEAD | sort | head -n 1)
  if [[ $first < $(date -u +%Y-%m-01) ]]; then
    remote -C "$branch" fetch --quiet origin data
    tip=$(git -C "$branch" rev-parse origin/data)
    root=$(git -C "$branch" commit-tree "$tip^{tree}" -m "chore(data): the data branch squashed, $(date -u +%Y-%m-%d) (SCALE-8)")
    if remote -C "$branch" push --quiet --force-with-lease="data:$tip" origin "$root:refs/heads/data"; then
      echo "The data branch is one commit again, its history since $first dropped."
    else
      echo "::warning::The data branch could not be squashed; the next archive tries again."
    fi
  fi
fi
echo "pushed=$pushed" >>"$output"
