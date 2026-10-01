#!/usr/bin/env bash
# Print the section of CHANGELOG.md for one version: the notes of its GitHub release.
# Fails when the changelog has no section for it, so that no release goes out without notes.
# Usage: release-notes.sh VERSION [CHANGELOG]   (VERSION as 0.2.0 or v0.2.0)
set -euo pipefail

version=${1#v}
changelog=${2:-CHANGELOG.md}

# From the "## <version> ..." heading to the next "## " heading, without the heading itself
# (the release title gives the version), and without the blank lines around. GitHub keeps
# the line breaks of release notes, so each paragraph and list item is unwrapped into one line.
notes=$(awk -v version="$version" '
  /^## / { if (found) exit; found = ($2 == version); next }
  found { print }
' "$changelog" | sed -e '/./,$!d' | awk '
  /^[ \t]*$/ { if (line != "") print line; line = ""; print ""; next }
  /^ *(#|[-*] |[0-9]+\. )/ { if (line != "") print line; line = $0; next }
  { sub(/^[ \t]+/, ""); line = (line == "" ? $0 : line " " $0) }
  END { if (line != "") print line }
')

if [ -z "${notes//[[:space:]]/}" ]; then
  echo "::error::$changelog has no section for $version." >&2
  exit 1
fi
printf '%s\n' "$notes"
