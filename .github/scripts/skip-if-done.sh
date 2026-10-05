#!/usr/bin/env bash
# Tells a data workflow whether to go on. GitHub starts scheduled runs hours late, so an
# outside scheduler dispatches the workflows on time (docs/operations.md) and their
# schedule is the fallback: a scheduled run stops once a run of the same workflow has
# succeeded today (UTC). Dispatched and manual runs always go on.
#
# Usage: skip-if-done.sh <workflow file>, with GH_TOKEN (actions: read), GITHUB_REPOSITORY
# and GITHUB_EVENT_NAME (both set by Actions). Writes run=true or run=false to
# $GITHUB_OUTPUT.
set -euo pipefail

workflow=$1
run=true
if [ "${GITHUB_EVENT_NAME:-}" = schedule ]; then
  today=$(date -u +%Y-%m-%d)
  # A skipped run concludes success too, but only ever after a run that did the work.
  if done=$(gh run list --repo "$GITHUB_REPOSITORY" --workflow "$workflow" \
    --created ">=$today" --status success --limit 1 --json databaseId --jq length); then
    if [ "$done" -gt 0 ]; then
      run=false
      echo "::notice title=Already done today::A run of $workflow succeeded today, so this scheduled run stops"
    fi
  else
    # Without the run history, run: a second run only costs minutes.
    echo "::warning title=Run history unavailable::Could not list today's runs of $workflow, so this scheduled run goes on"
  fi
fi
echo "run=$run" >>"$GITHUB_OUTPUT"
