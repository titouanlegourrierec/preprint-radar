#!/usr/bin/env bash
# Check data/ before it is committed (`preprint-radar validate`), and copy the report into
# the job summary. Exits 1 when a structural rule is broken; warnings never fail.
# Usage: validate-data.sh
set -uo pipefail

status=0
report=$(uv run --no-dev preprint-radar validate 2>&1) || status=$?
printf '%s\n' "$report"

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
  } >>"$GITHUB_STEP_SUMMARY"
fi
exit "$status"
