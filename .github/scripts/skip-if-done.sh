#!/usr/bin/env bash
# Tells a data workflow whether to go on. GitHub starts scheduled runs hours late, so an
# outside scheduler dispatches the workflows on time (docs/operations.md) and their
# schedule is the fallback: a scheduled run stops once a run of the same workflow has
# succeeded today (UTC). In a fork, every scheduled run stops: a fork that turns Actions on
# must not crawl arXiv daily under its own name. Dispatched and manual runs always go on.
# With a number of days, a scheduled run stops once a run succeeded since that many days
# ago: the archive's Saturday catch-up, which runs only when no run succeeded since
# Sunday (CI-8).
#
# Today's fallback goes on even after a success when that run took the day from a catchup
# page, which arXiv may still have been filling (its "Listing out of date" annotation,
# OPS-3: 26 of 2026-10-30's 233 papers); and one that goes on says so when the outside
# scheduler did not dispatch the workflow today, whose token expires (OPS-5).
#
# Usage: skip-if-done.sh <workflow file> [days back, 0 by default: today], with GH_TOKEN
# (actions: read), GITHUB_REPOSITORY, GITHUB_EVENT_NAME and GITHUB_EVENT_PATH (all set by
# Actions). Writes run=true or run=false to $GITHUB_OUTPUT.
set -euo pipefail

# Whether this repository is a fork: from the event's payload, else from the API, in case a
# scheduled run's payload lacks the repository. When neither says, it is not: a scheduled
# run in a fork costs minutes, a missed run of this repository a day of data.
is_fork() {
  local fork
  # Not `// empty`, which drops false too.
  fork=$(jq -r '.repository.fork | values' "${GITHUB_EVENT_PATH:-/dev/null}" 2>/dev/null) || fork=
  if [ -z "$fork" ]; then
    fork=$(gh api "repos/$GITHUB_REPOSITORY" --jq .fork 2>/dev/null) || fork=
  fi
  [ "$fork" = true ]
}

# The UTC day that many days ago, by GNU date (the runners') or BSD date (macOS).
days_ago() {
  local epoch=$(($(date -u +%s) - $1 * 86400))
  date -u -d "@$epoch" +%Y-%m-%d 2>/dev/null || date -u -r "$epoch" +%Y-%m-%d
}

# Whether that run took the day from a catchup page: one of its jobs has the annotation.
# Without an answer, it did not: the day is then read again by the next day's listing.
partial_day() {
  local job
  for job in $(gh api "repos/$GITHUB_REPOSITORY/actions/runs/$1/jobs" --jq '.jobs[].id' 2>/dev/null); do
    if gh api "repos/$GITHUB_REPOSITORY/check-runs/$job/annotations" --jq '.[].title' 2>/dev/null |
      grep -qx "Listing out of date"; then
      return 0
    fi
  done
  return 1
}

# Whether the workflow was dispatched since that day; unknown counts as dispatched.
dispatched_since() {
  local count
  count=$(gh run list --repo "$GITHUB_REPOSITORY" --workflow "$workflow" --event workflow_dispatch \
    --created ">=$1" --limit 1 --json databaseId --jq length 2>/dev/null) || return 0
  [ "$count" -gt 0 ]
}

workflow=$1
back=${2:-0}
run=true
if [ "${GITHUB_EVENT_NAME:-}" = schedule ]; then
  since=$(days_ago "$back")
  if is_fork; then
    run=false
    echo "::notice title=Fork::$GITHUB_REPOSITORY is a fork, so this scheduled run stops; run $workflow by hand to collect data"
  # A skipped run concludes success too, but only ever after a run that did the work.
  elif done=$(gh run list --repo "$GITHUB_REPOSITORY" --workflow "$workflow" \
    --created ">=$since" --status success --limit 1 --json databaseId --jq '.[0].databaseId // empty'); then
    # What the run history said, in the log: a run that went on after a success the search
    # missed (2026-10-22) left no trace of why (OPS-8).
    echo "Successful runs of $workflow since $since: ${done:-none}"
    if [ -n "$done" ] && [ "$back" -eq 0 ] && partial_day "$done"; then
      echo "::notice title=Day read again::Today's run of $workflow took the day from a catchup page arXiv may still have been filling, so this scheduled run reads it again"
    elif [ -n "$done" ]; then
      run=false
      if [ "$back" -eq 0 ]; then
        echo "::notice title=Already done today::A run of $workflow succeeded today, so this scheduled run stops"
      else
        echo "::notice title=Already done this week::A run of $workflow succeeded since $since, so this catch-up stops"
      fi
    fi
  else
    # Without the run history, run: a second run only costs minutes.
    echo "::warning title=Run history unavailable::Could not list today's runs of $workflow, so this scheduled run goes on"
  fi
fi
if [ "$run" = true ] && [ "${GITHUB_EVENT_NAME:-}" = schedule ] && [ "$back" -eq 0 ] && ! dispatched_since "$since"; then
  echo "::warning title=Dispatch missing::No dispatch of $workflow today: check cron-job.org and its token (docs/operations.md)"
fi
echo "run=$run" >>"$GITHUB_OUTPUT"
