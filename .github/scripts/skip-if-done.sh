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
    --created ">=$since" --status success --limit 1 --json databaseId --jq length); then
    if [ "$done" -gt 0 ]; then
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
echo "run=$run" >>"$GITHUB_OUTPUT"
