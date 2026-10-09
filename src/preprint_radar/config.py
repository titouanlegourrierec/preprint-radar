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
DEFAULT_PAGE_CACHE_DIR = Path(".cache/front-matter")
"""The front matter of every HTML page read, for `reextract` (git-ignored)."""
DEFAULT_EXPORT_DIR = Path("exports")

# Environment variables.
CONTACT_ENV_VAR = "PREPRINT_RADAR_CONTACT"
"""E-mail or URL sent in the User-Agent of arXiv requests (never to other services)."""
S2_API_KEY_ENV = "SEMANTIC_SCHOLAR_API_KEY"
"""Semantic Scholar API key: citation counts are much slower without one."""
GITHUB_AUTH_ENV = "GITHUB_TOKEN"
"""A GitHub token, which GitHub's GraphQL API needs for the stars of the papers' code (any
token: it reads public data only; a workflow's own in CI)."""

# Collection (update and backfill).
DEFAULT_MAX_HTML = 600
"""HTML pages `update` and `backfill` download per category at most: at arXiv's 15 s crawl
delay, 600 pages take 150 minutes, inside the 175-minute deadline of the daily workflow's
fetch step (update.yml), and the pages left wait for the next run. `reextract` has no
default limit (the workflow gives it 50)."""
DEFAULT_SAVE_EVERY = 20
"""Papers enriched from their HTML page between two saves of the store."""
DEFAULT_MAX_ROR_LOOKUPS = 1000
"""ROR lookups per run; a day of cs.CV brings about 400 distinct affiliation strings."""

# Citation archive.
RECENT_DAYS = 365
"""The rolling window kept in full, in day files. Papers first seen earlier must earn the
archive; their day files are deleted only with ``--prune``."""
ARCHIVE_SINCE = date(2010, 1, 1)
"""Papers first seen before this day are never archived."""
DEFAULT_BUDGET = 22_000
"""Number of older papers the archive holds (about 20 citations a year in 2026)."""
DEFAULT_MARGIN = 1.15
"""An archived paper stays while it ranks within this multiple of the budget."""
TOP_RECENT_BUDGET = 1_000
"""Papers of the last 12 months the weekly archive keeps as the most cited (PROD-11), out of
about 40,000: from 80 to 180 a month, but fewer for the last two (see below)."""
TOP_RECENT_MIN_MONTHS = 2
"""Age a young paper's citations per month are counted over, at least (PROD-11): with one
month, two citations in its first weeks (often its authors' next paper) would rank a paper
with the best of the year, and 50 papers of the last month would enter on 2 or 3 citations."""
MIN_COVERAGE = 0.95
"""Share of candidates with a citation count below which the archive stays as it is: with
counts missing (Semantic Scholar down), papers that deserve the archive would score nothing
and be lost."""
OPENALEX_RETRY_AGE_DAYS = 730
"""An archived paper OpenAlex gave no affiliations for is asked again until this old (by its
first appearance): OpenAlex learns the institutions of recent papers over months (AFF-3)."""
OPENALEX_RETRY_EVERY_DAYS = 30
"""Days between two lookups of such a paper."""
CITATIONS_CACHE_DAYS = 7
"""Counts fetched by a run started fewer days ago are reused: a run that failed or was
cancelled resumes where it stopped, and a weekly run starts afresh."""
GAINS_MIN_DAYS = 6
"""A full refresh of the counts writes what each paper gained since the counts it replaces
only when these are at least this old (CIT-9): counts are refreshed weekly, and a refresh run
again within the week keeps the week's gains, which a day's interval would bring to nothing."""
STALE_DATA_WEEKDAYS = 3
"""A store whose newest announcement day is more weekdays old than this is reported as stale:
arXiv announces every weekday, and runs missed (one may be a holiday)."""
STALE_CITATIONS_DAYS = 14
"""Counts refreshed longer ago than this are reported as stale: two weekly runs missed."""
