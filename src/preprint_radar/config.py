"""The tunable defaults of Preprint Radar, in one place.

These are the values a maintainer may change: what to collect, where to keep it, and the
policy of the citation archive. Most can also be set per run, through the CLI options (and,
in CI, the repository variables the workflows pass to them).

Limits that external services impose are not settings, and stay next to the code that
talks to each service, with the reason for their value: arXiv's 15 s crawl delay, batch
sizes, URLs, timeouts and retry timings.
"""

from datetime import date
from pathlib import Path

# What to collect, and where to keep it.
DEFAULT_CATEGORY = "cs.CV"
DEFAULT_DATA_DIR = Path("data")
"""The data store, committed and published with the site."""
DEFAULT_CATALOG_DIR = Path(".cache/catalog")
"""The OAI catalog and the citation counts cache of the archive (git-ignored)."""
DEFAULT_EXPORT_DIR = Path("exports")

# Environment variables.
CONTACT_ENV_VAR = "PREPRINT_RADAR_CONTACT"
"""E-mail or URL sent in the User-Agent of arXiv requests (never to other services)."""
S2_API_KEY_ENV = "SEMANTIC_SCHOLAR_API_KEY"
"""Semantic Scholar API key: citation counts are much slower without one."""

# Collection (update and backfill).
DEFAULT_SAVE_EVERY = 20
"""Papers enriched from their HTML page between two saves of the store."""
DEFAULT_MAX_ROR_LOOKUPS = 1000
"""ROR lookups per run; a day of cs.CV brings about 400 distinct affiliation strings."""

# Citation archive.
RECENT_DAYS = 365
"""The rolling window kept in full, in day files; older papers must earn the archive."""
ARCHIVE_SINCE = date(2010, 1, 1)
"""Papers first seen before this day are never archived."""
DEFAULT_BUDGET = 22_000
"""Number of older papers the archive holds (about 20 citations a year in 2026)."""
DEFAULT_MARGIN = 1.15
"""An archived paper stays while it ranks within this multiple of the budget."""
MIN_COVERAGE = 0.95
"""Share of candidates with a citation count below which the archive stays as it is: with
counts missing (Semantic Scholar down), papers that deserve the archive would score nothing
and be lost."""
CITATIONS_CACHE_DAYS = 7
"""Counts fetched by a run started fewer days ago are reused: a run that failed or was
cancelled resumes where it stopped, and a weekly run starts afresh."""
