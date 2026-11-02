#!/usr/bin/env bash
# Check data/ before it is committed (`preprint-radar validate`), and copy the report into
# the job summary. Exits 1 when a structural rule is broken; warnings never fail.
# Usage: validate-data.sh [--set-aside], which the data workflows pass: a paper holding a
# contact detail is set back to pending, with a warning, instead of stopping the push (OPS-2).
# With KNOWN_WARNINGS, the report of `validate` before the run changed data/: the summary
# shows only the warnings that are new, with a count of the others (OPS-11), which the
# log keeps.
set -uo pipefail

status=0
report=$(uv run --no-dev preprint-radar validate "$@" 2>&1) || status=$?
printf '%s\n' "$report"

known=0
if [ -n "${KNOWN_WARNINGS:-}" ] && [ -f "$KNOWN_WARNINGS" ]; then
  # A warning line seen before the run is known; errors and the counts always show.
  shown=$(printf '%s\n' "$report" | grep -vxF -f <(grep '^WARNING ' "$KNOWN_WARNINGS") || true)
  known=$(($(printf '%s\n' "$report" | wc -l) - $(printf '%s\n' "$shown" | wc -l)))
  report=$shown
fi

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  # The summary is capped (1 MiB): the first findings, then the counts. The log has them all.
  lines=$(printf '%s\n' "$report" | wc -l)
  {
    echo "### Data validation"
    echo
    echo '```'
    if [ "$lines" -le 100 ]; then
      printf '%s\n' "$report"
    else
      printf '%s\n' "$report" | head -n 99
      echo "... $((lines - 100)) more findings in the step log"
      printf '%s\n' "$report" | tail -n 1
    fi
    echo '```'
    if [ "$known" -gt 0 ]; then
      echo
      echo "And ${known} warnings known before this run, in the step log."
    fi
  } >>"$GITHUB_STEP_SUMMARY"
fi
exit "$status"
