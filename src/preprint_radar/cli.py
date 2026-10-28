"""Command-line interface."""

import argparse
import logging
import math
import os
import re
import signal
import time
from collections.abc import Callable, Generator, Iterable, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from rich.table import Table

from preprint_radar import __version__, collect
from preprint_radar.archive.catalog import Catalog
from preprint_radar.archive.update import (
    ArchiveClients,
    format_archive_report,
    read_citations_cache,
    update_archive,
)
from preprint_radar.collect import (
    HtmlReading,
    Ror,
    Stop,
    UpdateReport,
    add_institutions,
    backfill_category,
    catch_up_since,
    format_archive_affiliations_report,
    format_citations_report,
    format_code_report,
    format_countries_report,
    format_openalex_report,
    format_report,
    format_scholar_report,
    reextract_category,
    ror_answers,
    update_archive_affiliations,
    update_category,
    update_citation_counts,
    update_code_records,
    update_countries,
    update_openalex_affiliations,
    update_scholar_records,
)
from preprint_radar.config import (
    CONTACT_ENV_VAR,
    DEFAULT_BUDGET,
    DEFAULT_CATALOG_DIR,
    DEFAULT_CATEGORY,
    DEFAULT_DATA_DIR,
    DEFAULT_MAX_HTML,
    DEFAULT_MAX_ROR_LOOKUPS,
    DEFAULT_PAGE_CACHE_DIR,
    GITHUB_AUTH_ENV,
    MIN_COVERAGE,
    S2_API_KEY_ENV,
    STALE_CITATIONS_DAYS,
    STALE_DATA_WEEKDAYS,
)
from preprint_radar.console import configure_logging, console, github_annotation, github_summary
from preprint_radar.exceptions import ConfigurationError, PreprintRadarError, StoreError
from preprint_radar.http import (
    ARXIV_API_DELAY_SECONDS,
    ARXIV_CRAWL_DELAY_SECONDS,
    DEFAULT_USER_AGENT,
    HttpClient,
    build_user_agent,
)
from preprint_radar.models import Paper
from preprint_radar.sources.arxiv_html import EXTRACTOR_VERSION, PageCache
from preprint_radar.sources.arxiv_listing import validate_category
from preprint_radar.sources.arxiv_oai import OAI_DELAY_SECONDS, OAI_TIMEOUT_SECONDS
from preprint_radar.sources.github import GITHUB_DELAY_SECONDS
from preprint_radar.sources.huggingface import HUGGINGFACE_DELAY_SECONDS
from preprint_radar.sources.openalex import OPENALEX_DELAY_SECONDS
from preprint_radar.sources.ror import ROR_DELAY_SECONDS
from preprint_radar.sources.semantic_scholar import S2_ANONYMOUS_DELAY_SECONDS, S2_DELAY_SECONDS, api_key
from preprint_radar.steps import format_counts
from preprint_radar.store.naming import name_institutions_again
from preprint_radar.store.paper_store import PaperStore
from preprint_radar.store.quality import (
    affiliation_quality,
    extracted_again,
    extraction_changes,
    format_changes,
    format_quality,
    quality_table,
)
from preprint_radar.store.reclean import reclean_store
from preprint_radar.store.stats import (
    archive_coverage_table,
    collect_archive_coverage,
    collect_coverage,
    coverage_table,
    format_archive_coverage,
    format_citations,
    format_coverage,
    weekdays_since,
)
from preprint_radar.store.validate import validate_store
from preprint_radar.store.venues import detect_venues_again
from preprint_radar.trends import TITLES_SOURCE, TRENDS_SOURCE, count_trends, format_trends_report

logger = logging.getLogger(__name__)


def _count(text: str) -> int:
    """A number of things, 0 or more: a limit or a budget (DEBT-5)."""
    try:
        value = int(text)
    except ValueError:
        msg = f"not a whole number: {text!r}"
        raise argparse.ArgumentTypeError(msg) from None
    if value < 0:
        msg = f"must be 0 or more, got {value}"
        raise argparse.ArgumentTypeError(msg)
    return value


def _duration(text: str) -> float:
    """A length of time, 0 or more: minutes or seconds (DEBT-5)."""
    try:
        value = float(text)
    except ValueError:
        msg = f"not a number: {text!r}"
        raise argparse.ArgumentTypeError(msg) from None
    if not (math.isfinite(value) and value >= 0):  # nan and inf too
        msg = f"must be a number, 0 or more, got {text}"
        raise argparse.ArgumentTypeError(msg)
    return value


# A crawl delay is slept between requests: past an hour it is a typo, and past about 290
# years time.sleep overflows.
_MAX_CRAWL_DELAY_SECONDS = 3600


def _crawl_delay(text: str) -> float:
    """Seconds between two arxiv.org requests, up to an hour (DEBT-5)."""
    value = _duration(text)
    if value > _MAX_CRAWL_DELAY_SECONDS:
        msg = f"must be {_MAX_CRAWL_DELAY_SECONDS} seconds at most, got {text}"
        raise argparse.ArgumentTypeError(msg)
    return value


def _regex(text: str) -> re.Pattern[str]:
    """A regular expression (DEBT-5): argparse would let re.error through as a traceback."""
    try:
        return re.compile(text)
    except re.error as exc:
        msg = f"not a valid regular expression: {exc}"
        raise argparse.ArgumentTypeError(msg) from None


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="preprint-radar",
        description=(
            "Follow the papers announced on arXiv every weekday, with their affiliations, "
            "citations and the most cited older papers."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="increase log verbosity (-v: info, -vv: debug)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="warnings and errors only (the long commands log their progress otherwise)",
    )
    parser.add_argument(
        "--contact",
        default=os.environ.get(CONTACT_ENV_VAR),
        help=f"e-mail or URL sent in the User-Agent so arXiv can reach you (env: {CONTACT_ENV_VAR})",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    _add_update_parser(subparsers)
    _add_backfill_parser(subparsers)
    _add_stats_parser(subparsers)
    _add_institutions_parser(subparsers)
    _add_affiliations_parser(subparsers)
    _add_archive_affiliations_parser(subparsers)
    _add_archive_parser(subparsers)
    _add_citations_parser(subparsers)
    _add_index_parser(subparsers)
    _add_reclean_parser(subparsers)
    _add_scholar_parser(subparsers)
    _add_code_parser(subparsers)
    _add_countries_parser(subparsers)
    _add_trends_parser(subparsers)
    _add_venues_parser(subparsers)
    _add_validate_parser(subparsers)
    _add_summary_parser(subparsers)
    _add_reextract_parser(subparsers)
    # -v and -q after the command too ("stats -v"), which add to the ones before it (DOC-5).
    for command in subparsers.choices.values():
        command.add_argument(
            "-v",
            "--verbose",
            dest="verbose_after",
            action="count",
            default=0,
            help="increase log verbosity (-v: info, -vv: debug)",
        )
        command.add_argument(
            "-q",
            "--quiet",
            action="store_true",
            default=argparse.SUPPRESS,
            help="warnings and errors only",
        )
    return parser


# The commands that run for minutes or hours: they log their progress unless -q (DOC-5).
PROGRESS_COMMANDS = frozenset(
    {
        "update",
        "backfill",
        "reextract",
        "institutions",
        "affiliations",
        "archive-affiliations",
        "citations",
        "scholar",
        "code",
        "countries",
        "archive",
    }
)


def log_level(args: argparse.Namespace) -> int:
    """The logging level a command line asks for.

    Args:
        args: The parsed command line.

    Returns:
        WARNING by default, INFO with one -v (before and after the command add up), DEBUG
        with more; INFO at least for the long commands (`PROGRESS_COMMANDS`), unless -q,
        which asks for WARNING whatever else is given.
    """
    if args.quiet:
        return logging.WARNING
    verbosity = args.verbose + args.verbose_after
    if args.command in PROGRESS_COMMANDS:
        verbosity = max(verbosity, 1)
    return {0: logging.WARNING, 1: logging.INFO}.get(verbosity, logging.DEBUG)


def _add_update_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    update = subparsers.add_parser(
        "update",
        help="add recent papers to the data store, with abstracts and affiliations",
        description=(
            "Fetch the recent listing of each category, retrieve abstracts (from the RSS feed, "
            "then the catchup pages, then the arXiv API, then the HTML renderings) and "
            "affiliations from the HTML renderings, name their institutions, and save everything "
            "to the data store used by the web app."
        ),
    )
    _add_store_arguments(update, max_html=DEFAULT_MAX_HTML)


def _add_backfill_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    backfill = subparsers.add_parser(
        "backfill",
        help="add past announcement days to the data store",
        description=(
            "Collect every day announced between two dates from the arXiv catchup pages, "
            "abstracts included, then read affiliations from the HTML renderings. Days are "
            "saved as soon as they are fetched; re-running resumes where it stopped."
        ),
    )
    backfill.add_argument("--since", type=_day, required=True, help="first announcement day (YYYY-MM-DD)")
    backfill.add_argument("--until", type=_day, help="last announcement day (YYYY-MM-DD, default: today)")
    _add_store_arguments(backfill, max_html=DEFAULT_MAX_HTML)


def _add_stats_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    stats = subparsers.add_parser(
        "stats",
        help="show how much of the data store is enriched",
        description=(
            "Show, for each stored announcement day, then each archive year, how many papers "
            "have an abstract, affiliations, a detected venue and a citation count. "
            "Affiliation columns: at least one found (affiliated), searched without success "
            "(none), not retrieved yet (pending), never (no page: no HTML rendering to read); "
            "of the affiliated papers, mapped to their "
            "authors (mapped) and with at least one institution named (named). With "
            "--affiliations, count signs of wrong affiliations instead, with examples."
        ),
    )
    stats.add_argument(
        "--affiliations",
        action="store_true",
        help=(
            "count the signs of wrong affiliations in day files (names of authors, glued or cut "
            "off strings, units without their institution...), with examples"
        ),
    )
    stats.add_argument(
        "--page-cache-dir",
        type=Path,
        default=None,
        help=(
            "with --affiliations, also count them in what today's extraction gives for the pages "
            "cached in this directory, next to what is stored for those papers (nothing is written)"
        ),
    )
    stats.add_argument(
        "--changes",
        action="store_true",
        help=(
            "with --page-cache-dir, list the papers whose affiliations or mapping today's "
            "extraction changes instead, those that would lose words first"
        ),
    )
    _add_store_location(stats, every_category=True)


def _add_institutions_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    institutions = subparsers.add_parser(
        "institutions",
        help="name the institutions of stored affiliations",
        description=(
            "Look up, in the Research Organization Registry, the stored affiliations whose "
            "institution is not named yet; the site's rules name those it does not know. "
            "Update and backfill do it for the papers they handle; this command catches up "
            "on the rest of the store. With --again, name the stored institutions again with "
            "today's rules instead, day files and archive, without asking ROR."
        ),
    )
    institutions.add_argument(
        "--again",
        action="store_true",
        help="name the stored institutions again with today's rules, offline, archive included",
    )
    _add_store_location(institutions, every_category=True)
    institutions.add_argument(
        "--max-ror",
        type=_count,
        default=None,
        help="maximum number of affiliations to look up (default: no limit)",
    )


def _add_affiliations_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    affiliations = subparsers.add_parser(
        "affiliations",
        help="ask OpenAlex for the affiliations of stored papers no page gave them",
        description=(
            "Ask OpenAlex for the affiliations, and their institutions, of the stored papers "
            "that arXiv has no HTML rendering of (about 5%), which no page can give, and of "
            "those whose page gave none, a month after it was read: a few requests. A paper it "
            "knows nothing of yet is asked again every 30 days while under two years old; one "
            "with a page keeps its extraction version, read again by the next one. A failing "
            "OpenAlex never fails the command: the papers are asked for again next time."
        ),
    )
    _add_store_location(affiliations, every_category=True)


def _add_archive_affiliations_parser(
    subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]",
) -> None:
    archive_affiliations = subparsers.add_parser(
        "archive-affiliations",
        help="find affiliations for the highly cited papers without any",
        description=(
            "Find affiliations for the papers of the archive and the most cited of the last "
            "12 months that have none: first OpenAlex's record of their published version "
            "(the DOI of scholar.json), a few requests; then, with --max-html, their HTML "
            "rendering, arXiv's since December 2023 and ar5iv's before, the most cited first, "
            "at arxiv.org's crawl delay: hours for thousands of pages. Pages the cache "
            "holds are read from it, offline, and a page that does not exist is not asked for "
            "again. Ctrl-C saves what was read; running it again resumes. The institutions "
            "of the affiliations read are named through ROR."
        ),
    )
    _add_store_arguments(archive_affiliations, max_html=0, max_ror=None)


def _add_archive_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    archive = subparsers.add_parser(
        "archive",
        help="keep the most cited older papers in the archive (weekly)",
        description=(
            "Refresh the category's catalog from OAI-PMH, fetch citation counts from "
            f"Semantic Scholar (API key from {S2_API_KEY_ENV}, else anonymously and "
            "slowly), keep the papers older than 12 months with the most citations per year "
            "within the budget, fill their affiliations from OpenAlex, and write the archive, "
            "the citation counts and what each paper gained since the last week's. Stored days "
            "take the comments, venues and withdrawals of their papers' latest versions; with "
            "--prune, days older than 12 months are deleted."
        ),
    )
    _add_store_location(archive, every_category=False)
    archive.add_argument(
        "--catalog-dir",
        type=Path,
        default=DEFAULT_CATALOG_DIR,
        help=f"where the harvested catalog is kept (default: {DEFAULT_CATALOG_DIR})",
    )
    archive.add_argument(
        "--budget",
        type=_count,
        default=DEFAULT_BUDGET,
        help=f"number of older papers the archive holds (default: {DEFAULT_BUDGET})",
    )
    archive.add_argument(
        "--prune",
        action="store_true",
        help="delete the day files older than 12 months (their archived papers are kept)",
    )
    archive.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")


def _add_citations_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    citations = subparsers.add_parser(
        "citations",
        help="fetch the citation counts of stored papers",
        description=(
            "Fetch from Semantic Scholar the citation counts of the stored papers that have "
            "none yet (the papers announced since the last full refresh), or of every stored "
            "paper with --all, as the weekly archive does. API key from "
            f"{S2_API_KEY_ENV}. A refusing Semantic Scholar never fails the command: "
            "the papers left are asked for again next time. A rejected key does."
        ),
    )
    _add_store_location(citations, every_category=True)
    citations.add_argument("--all", action="store_true", help="fetch the counts of every stored paper again")
    citations.add_argument(
        "--max-minutes",
        type=_duration,
        default=None,
        help="stop asking a refusing Semantic Scholar after this long (default: no limit)",
    )


def _add_scholar_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    scholar = subparsers.add_parser(
        "scholar",
        help="fetch the DOI, published venue and author ids of stored papers",
        description=(
            "Fetch from Semantic Scholar the DOI, published venue and author ids of every "
            "stored paper (day files and archive) into scholar.json, as the weekly archive "
            f"workflow does. API key from {S2_API_KEY_ENV}. Papers Semantic Scholar "
            "was not asked for, because it kept refusing, keep what they had. A rejected key "
            "fails the command."
        ),
    )
    _add_store_location(scholar, every_category=True)
    scholar.add_argument(
        "--max-minutes",
        type=_duration,
        default=None,
        help="stop asking a refusing Semantic Scholar after this long (default: no limit)",
    )


def _add_trends_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    trends = subparsers.add_parser(
        "trends",
        help="count the topics of the papers' titles: rising, cooling and new (offline)",
        description=(
            "Count, month by month since 2010, the phrases of the titles of the category's "
            "catalog, which archive harvests, and write the topics rising, cooling and new into "
            "trends.json, and every topic's months into topics.json (PROD-20): the site's Trends "
            "view. Offline, under a minute. Each topic's impact and key papers need the citation "
            "counts archive cached within the week: without them, they are left out."
        ),
    )
    _add_store_location(trends, every_category=False)
    trends.add_argument(
        "--catalog-dir",
        type=Path,
        default=DEFAULT_CATALOG_DIR,
        help=f"where the harvested catalog is kept (default: {DEFAULT_CATALOG_DIR})",
    )


def _add_countries_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    countries = subparsers.add_parser(
        "countries",
        help="place the institutions of stored papers in their country",
        description=(
            "Ask OpenAlex for the country of the institutions of every stored paper, by their "
            "ROR id, into countries.json (UX-40), for the site's map: 50 a request, seconds. "
            "Only those without a country yet are asked for, unless --all; a lookup that "
            "fails is asked for again next time."
        ),
    )
    _add_store_location(countries, every_category=True)
    countries.add_argument("--all", action="store_true", help="ask for every institution again")


def _add_code_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    code = subparsers.add_parser(
        "code",
        help="fetch the GitHub stars of the code stored papers link",
        description=(
            "Fetch the GitHub stars of the repository each stored paper links (the link its "
            "card shows), or the Hugging Face likes of its models, data or demo, into "
            "code.json: 100 repositories a request, one every 3 s, about 5 minutes. GitHub's "
            f"API needs a token, from {GITHUB_AUTH_ENV}: any token, since it reads public data "
            "only. A lookup "
            "that fails keeps last week's record. With --new, the daily run, only the papers "
            "without a record: those announced since the weekly refresh, which alone counts "
            "the stars gained in the week."
        ),
    )
    _add_store_location(code, every_category=True)
    code.add_argument(
        "--new",
        action="store_true",
        help="ask only for the papers without a record, keeping the others and the week's gains",
    )


def _add_index_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    index = subparsers.add_parser(
        "index",
        help="write data/index.json again from the stored files",
        description=(
            "Write the index the web app reads (the stored days and archive years, with "
            "their paper counts) from the files in the data store, e.g. after a merge of "
            "data commits. Nothing is fetched."
        ),
    )
    _add_data_dir(index)


def _add_reclean_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    reclean = subparsers.add_parser(
        "reclean",
        help="clean the stored affiliations again with the current rules",
        description=(
            "Apply the current affiliation cleaning to the stored day files, after a change "
            "to the heuristics: contact details, junk and author names are dropped, strings "
            "holding several affiliations are split, and the author mapping follows them. "
            "Changed affiliations lose their institutions, which `institutions` names again "
            "(`archive-affiliations` in the archive). Nothing is fetched. In the citation "
            "archive, only the papers whose affiliations a page gave are cleaned: the others' "
            "are OpenAlex's names."
        ),
    )
    _add_store_location(reclean, every_category=True)


def _add_venues_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    venues = subparsers.add_parser(
        "venues",
        help="detect the venues of the stored papers again with the current rules",
        description=(
            "Detect the venue and withdrawal of every stored paper again, from its comments "
            "and journal reference, and make its abstract plain text again, after a change to "
            "these rules: day files and archive alike. Nothing is fetched."
        ),
    )
    _add_store_location(venues, every_category=True)


def _add_reextract_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    reextract = subparsers.add_parser(
        "reextract",
        help="read the HTML pages of stored papers again, after a change to the extraction",
        description=(
            "Read again the HTML pages of the stored papers extracted by an older version of "
            f"the extraction (below {EXTRACTOR_VERSION} by default), or of the papers given by "
            "--ids or --match. Pages the cache holds are read from it, offline; the others are "
            "downloaded within --max-html, the most recent papers first. A paper whose page "
            "cannot be read again keeps what it had. Papers read before versions were kept "
            "have none: they are only read again through --ids or --match."
        ),
    )
    selection = reextract.add_mutually_exclusive_group()
    selection.add_argument(
        "--below-version",
        type=int,
        default=EXTRACTOR_VERSION,
        help=f"papers extracted by an older version than this (default: {EXTRACTOR_VERSION}, today's)",
    )
    selection.add_argument("--ids", nargs="+", metavar="ARXIV_ID", help="these papers")
    selection.add_argument(
        "--match", type=_regex, metavar="REGEX", help="papers with an affiliation that this regex finds"
    )
    _add_store_arguments(reextract, max_html=None)


def _add_summary_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    summary = subparsers.add_parser(
        "summary",
        help="report how fresh and how complete the data store is",
        description=(
            "Print the newest announcement day of each category and its age, the date of the "
            "citation counts, the coverage tables of `stats` and the counts of `stats "
            "--affiliations`, in plain text. In GitHub "
            "Actions, also write them to the job summary, and warn when the data or the "
            "counts are stale. Nothing is fetched or written."
        ),
    )
    _add_data_dir(summary)


def _add_validate_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    validate = subparsers.add_parser(
        "validate",
        help="check the data store against its contract",
        description=(
            "Check every file of the data store before it is committed: day files, archive years, "
            "citation counts and gains, scholar.json and the index. Structural rules (a record "
            "that does not load, a paper stored twice, an index that disagrees with the files, a "
            "contact detail in an affiliation) are errors and make the command fail; heuristic "
            "rules (an affiliation that only names authors, a paper `reclean` would still change) "
            "are warnings. Nothing is fetched or written."
        ),
    )
    _add_data_dir(validate)


def _add_store_location(parser: argparse.ArgumentParser, *, every_category: bool) -> None:
    """``-c`` and ``--data-dir``, as every command over the store takes them (DEBT-5).

    Args:
        parser: The command's parser.
        every_category: Whether no ``-c`` means every category of the store, as for the
            steps over stored papers, rather than ``DEFAULT_CATEGORY``, as for those that
            read arXiv.
    """
    default = "every category in the store" if every_category else DEFAULT_CATEGORY
    parser.add_argument(
        "-c",
        "--category",
        dest="categories",
        action="append",
        type=_category,
        help=f"arXiv category, repeatable (default: {default})",
    )
    _add_data_dir(parser)


def _add_data_dir(parser: argparse.ArgumentParser) -> None:
    """``--data-dir``, the data store's directory."""
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"data store directory (default: {DEFAULT_DATA_DIR})",
    )


def _add_store_arguments(
    parser: argparse.ArgumentParser, *, max_html: int | None, max_ror: int | None = DEFAULT_MAX_ROR_LOOKUPS
) -> None:
    """Options shared by the commands that write to the data store.

    Args:
        parser: The command's parser.
        max_html: The command's default ``--max-html`` (``None``: no limit).
        max_ror: The command's default ``--max-ror`` (``None``: no limit).
    """
    _add_store_location(parser, every_category=False)
    parser.add_argument(
        "--max-html",
        type=_count,
        default=max_html,
        help=(
            "maximum number of HTML pages to download per category "
            f"(default: {'no limit' if max_html is None else max_html}; 0 disables)"
        ),
    )
    parser.add_argument(
        "--max-ror",
        type=_count,
        default=max_ror,
        help=(
            "maximum number of affiliations to look up in the Research Organization Registry "
            f"(default: {'no limit' if max_ror is None else max_ror}; 0 disables)"
        ),
    )
    parser.add_argument(
        "--page-cache-dir",
        type=Path,
        default=DEFAULT_PAGE_CACHE_DIR,
        help=f"front matter of the HTML pages read, for `reextract` (default: {DEFAULT_PAGE_CACHE_DIR})",
    )
    parser.add_argument(
        "--deadline-minutes",
        type=_duration,
        default=None,
        help=(
            "start no HTML page (nor, for backfill, catchup page) after this many minutes, so "
            "that the run ends cleanly before a time limit; what is left waits for the next "
            "run (default: no deadline)"
        ),
    )
    parser.add_argument(
        "--crawl-delay",
        type=_crawl_delay,
        default=ARXIV_CRAWL_DELAY_SECONDS,
        help=f"seconds between arxiv.org requests (default: {ARXIV_CRAWL_DELAY_SECONDS:g}, from robots.txt)",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface.

    Args:
        argv: Command-line arguments, without the program name. Defaults to ``sys.argv[1:]``.

    Returns:
        The process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "backfill" and args.until is not None and args.since > args.until:
        parser.error("--since must not be after --until")
    if args.command == "stats" and args.changes and args.page_cache_dir is None:
        parser.error("--changes needs --page-cache-dir: the pages to extract again")
    if args.command == "stats" and args.page_cache_dir is not None and not args.affiliations:
        parser.error("--page-cache-dir goes with --affiliations")
    _configure_logging(log_level(args))
    try:
        return _COMMANDS[args.command](args)
    except PreprintRadarError as exc:
        logger.error("%s", exc)  # noqa: TRY400 - the message is enough, no traceback for users
        # On the run's page, which otherwise only says that the step exited with 1.
        github_annotation("error", f"preprint-radar {args.command} failed", str(exc))
        return 1


def _run_update(args: argparse.Namespace) -> int:
    categories: list[str] = args.categories or [DEFAULT_CATEGORY]
    store = PaperStore(args.data_dir)
    user_agent = build_user_agent(args.contact)
    if not args.contact:
        logger.warning("No contact given; consider setting %s so arXiv can reach you.", CONTACT_ENV_VAR)

    reading = _html_reading(args)
    # The index is written even after a failure, so that the days saved meanwhile show.
    try:
        with (
            _terminate_as_interrupt(),
            HttpClient(user_agent=user_agent, min_interval=args.crawl_delay) as site_client,
            HttpClient(user_agent=user_agent, min_interval=ARXIV_API_DELAY_SECONDS) as api_client,
            # The contact is for arXiv only: other services get the bare User-Agent.
            HttpClient(user_agent=DEFAULT_USER_AGENT, min_interval=ROR_DELAY_SECONDS) as ror_client,
        ):

            def update(category: str) -> UpdateReport:
                day = collect.today()
                if since := catch_up_since(store, category, day):
                    # Days the listing no longer holds, or with papers it dropped (CI-7).
                    line = f"{category}: reading every day since {since.isoformat()} from catchup pages"
                    logger.warning("%s", line)
                    github_annotation("warning", "Catching up", line)
                    return backfill_category(
                        category,
                        [since + timedelta(days=offset) for offset in range((day - since).days + 1)],
                        store=store,
                        site_client=site_client,
                        ror_client=ror_client if args.max_ror else None,
                        max_ror_lookups=args.max_ror,
                        html=reading,
                    )
                return update_category(
                    category,
                    store=store,
                    site_client=site_client,
                    api_client=api_client,
                    ror_client=ror_client if args.max_ror else None,
                    max_ror_lookups=args.max_ror,
                    html=reading,
                )

            return _per_category(args.command, categories, update)
    finally:
        console.print(f"Index written to {store.write_index()}")


def _run_backfill(args: argparse.Namespace) -> int:
    categories: list[str] = args.categories or [DEFAULT_CATEGORY]
    store = PaperStore(args.data_dir)
    until: date = args.until or datetime.now(tz=UTC).date()
    days = [args.since + timedelta(days=offset) for offset in range((until - args.since).days + 1)]
    if not args.contact:
        logger.warning("No contact given; consider setting %s so arXiv can reach you.", CONTACT_ENV_VAR)

    user_agent = build_user_agent(args.contact)
    reading = _html_reading(args)
    # The index is written even after a failure, so that the days saved meanwhile show.
    try:
        with (
            _terminate_as_interrupt(),
            HttpClient(user_agent=user_agent, min_interval=args.crawl_delay) as site_client,
            # The contact is for arXiv only: other services get the bare User-Agent.
            HttpClient(user_agent=DEFAULT_USER_AGENT, min_interval=ROR_DELAY_SECONDS) as ror_client,
        ):
            return _per_category(
                args.command,
                categories,
                lambda category: backfill_category(
                    category,
                    days,
                    store=store,
                    site_client=site_client,
                    ror_client=ror_client if args.max_ror else None,
                    max_ror_lookups=args.max_ror,
                    html=reading,
                ),
            )
    finally:
        console.print(f"Index written to {store.write_index()}")


def _per_category(command: str, categories: Sequence[str], run: Callable[[str], UpdateReport]) -> int:
    """Run ``run`` on each category and publish its report, one failing leaving the others (REL-5).

    Returns:
        The exit code: 1 when a category failed, or a report says so (:func:`_exit_code`).
    """
    reports: list[UpdateReport] = []
    failed = False
    for category in categories:
        try:
            report = run(category)
        except PreprintRadarError as exc:
            logger.error("%s: %s", category, exc)  # noqa: TRY400 - the message is enough
            github_annotation("error", f"preprint-radar {command} failed", str(exc))
            failed = True
            continue
        _publish_update(report)
        reports.append(report)
    return max(_exit_code(reports), int(failed))


def _publish_update(report: UpdateReport) -> None:
    """Print an update report, and put it on the run's page in GitHub Actions."""
    line = format_report(report)
    console.print(line)
    github_summary(f"**Papers.** {line}")
    if steps := format_counts(report.steps):
        github_summary(f"**Steps.** {steps}")
    if report.failed_days:
        github_annotation("error", "Catchup pages failed", line)
    if report.caught_up:
        github_annotation("warning", "Listing out of date", line)
    if report.stopped is Stop.DEADLINE:
        github_annotation("warning", "Out of time", line)
    elif report.html_failed:
        github_annotation("error", "Reading HTML pages failed", line)


def _run_reextract(args: argparse.Namespace) -> int:
    categories: list[str] = args.categories or [DEFAULT_CATEGORY]
    store = PaperStore(args.data_dir)
    select = _reextract_selection(args)
    reading = _html_reading(args)
    user_agent = build_user_agent(args.contact)
    try:
        with (
            _terminate_as_interrupt(),
            HttpClient(user_agent=user_agent, min_interval=args.crawl_delay) as site_client,
            # The contact is for arXiv only: other services get the bare User-Agent.
            HttpClient(user_agent=DEFAULT_USER_AGENT, min_interval=ROR_DELAY_SECONDS) as ror_client,
        ):
            return _per_category(
                args.command,
                categories,
                lambda category: reextract_category(
                    category,
                    select,
                    store=store,
                    site_client=site_client,
                    ror_client=ror_client if args.max_ror else None,
                    max_ror_lookups=args.max_ror,
                    html=reading,
                ),
            )
    finally:
        console.print(f"Index written to {store.write_index()}")


def _reextract_selection(args: argparse.Namespace) -> Callable[[Paper], bool]:
    """Which stored papers ``reextract`` reads again, from its options."""
    if args.ids:
        ids = set(args.ids)
        return lambda paper: paper.arxiv_id in ids
    if args.match:
        pattern: re.Pattern[str] = args.match
        return lambda paper: any(pattern.search(affiliation) for affiliation in paper.affiliations or ())
    below: int = args.below_version
    return lambda paper: paper.extractor is not None and paper.extractor < below


def _html_reading(args: argparse.Namespace) -> HtmlReading:
    """How the command reads HTML pages: ``--max-html``, ``--deadline-minutes``, the page cache."""
    minutes: float | None = args.deadline_minutes
    return HtmlReading(
        limit=args.max_html,
        deadline=None if minutes is None else time.monotonic() + 60 * minutes,
        cache=PageCache(args.page_cache_dir),
    )


def _exit_code(reports: Sequence[UpdateReport]) -> int:
    """1 when a run failed: HTML pages, or days of a backfill, could not be read.

    The reading of HTML pages stopped on a failure (arXiv down, layout changed), or the
    catchup page of a day failed or came back incomplete.
    """
    html = [report.category for report in reports if report.html_failed]
    if html:
        logger.error("Reading HTML pages failed for %s: see above", ", ".join(html))
    days = [report.category for report in reports if report.failed_days]
    if days:
        logger.error("Catchup pages failed for %s: see above", ", ".join(days))
    return 1 if any(report.failed for report in reports) else 0


@contextmanager
def _terminate_as_interrupt() -> Generator[None]:
    """Turn SIGTERM into KeyboardInterrupt, so that a cancelled or timed-out job saves its progress."""

    def interrupt(*_: object) -> None:
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, interrupt)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def _run_stats(args: argparse.Namespace) -> int:
    store = PaperStore(args.data_dir)
    categories: list[str] = args.categories or store.categories()
    if not categories:
        logger.warning("The store %s is empty; run `preprint-radar update` first.", args.data_dir)
        return 1

    # A terminal gets rich tables; CI and pipes the plain text, one line per row.
    styled = console.is_terminal
    reports = (
        _affiliation_quality(store, categories, args.page_cache_dir, styled=styled, changes=args.changes)
        if args.affiliations
        else _coverage(store, categories, styled=styled)
    )
    for index, report in enumerate(reports):
        if index:
            console.print()
        console.print(report)
    return 0 if reports else 1


def _coverage(store: PaperStore, categories: Iterable[str], *, styled: bool) -> list[str | Table]:
    """The coverage reports of ``stats``: days, archive years, then citation counts."""
    reports: list[str | Table] = []
    for category in categories:
        days = collect_coverage(store, category)
        years = collect_archive_coverage(store, category)
        if not days and not years:
            logger.warning("No stored papers for %s in %s.", category, store.root)
            continue
        if days:
            reports.append(coverage_table(category, days) if styled else format_coverage(category, days))
        if years:
            reports.append(
                archive_coverage_table(category, years)
                if styled
                else format_archive_coverage(category, years)
            )
        if citations := store.load_citation_counts(category):
            reports.append(format_citations(category, citations, today=datetime.now(tz=UTC).date()))
    return reports


def _affiliation_quality(
    store: PaperStore,
    categories: Iterable[str],
    page_cache_dir: Path | None,
    *,
    styled: bool,
    changes: bool = False,
) -> list[str | Table]:
    """The quality reports of ``stats --affiliations``: stored, then extracted again from the cache.

    With ``changes``, the papers the extraction changes, instead of the counts.
    """
    reports: list[str | Table] = []

    def add(title: str, papers: Iterable[Paper]) -> None:
        quality = affiliation_quality(papers)
        reports.append(quality_table(title, quality) if styled else format_quality(title, quality))

    for category in categories:
        papers = list(store.iter_papers(category))
        if not papers:
            logger.warning("No stored papers for %s in %s.", category, store.root)
            continue
        if not changes:
            add(f"{category}: affiliations of the day files", papers)
        if page_cache_dir is None:
            continue
        pairs = extracted_again(papers, PageCache(page_cache_dir))
        if not pairs:
            logger.warning("The page cache %s holds no page of %s.", page_cache_dir, category)
            continue
        if changes:
            title = f"{category}, version {EXTRACTOR_VERSION}"
            reports.append(format_changes(title, len(pairs), extraction_changes(pairs)))
            continue
        add(f"{category}: the papers with a cached page, as stored", (old for old, _ in pairs))
        add(
            f"{category}: the same papers, as extracted today (version {EXTRACTOR_VERSION})",
            (new for _, new in pairs),
        )
    return reports


def _run_institutions(args: argparse.Namespace) -> int:
    store = PaperStore(args.data_dir)
    categories: list[str] = args.categories or store.categories()
    if args.again:
        for category in categories:
            report = name_institutions_again(store, category)
            written = f"{report.days} day files" + (" and the archive" if report.archive else "")
            console.print(
                f"{category}: {report.changed} of {report.papers} papers changed, in {written}; "
                f"affiliations without an institution {report.unnamed_before} -> {report.unnamed_after}"
            )
        return 0
    with HttpClient(user_agent=DEFAULT_USER_AGENT, min_interval=ROR_DELAY_SECONDS) as client:
        for category in categories:
            papers = list(store.iter_papers(category))
            named = add_institutions(papers, client, limit=args.max_ror, known=ror_answers(papers))
            changed = [new for old, new in zip(papers, named, strict=True) if new is not old]
            store.save(category, changed)
            pending = sum(bool(paper.affiliations) and paper.institutions is None for paper in named)
            console.print(
                f"{category}: institutions named for {len(changed)} papers, {pending} still pending"
            )
    return 0


def _run_affiliations(args: argparse.Namespace) -> int:
    store = PaperStore(args.data_dir)
    categories: list[str] = args.categories or store.categories()
    today = datetime.now(tz=UTC).date()
    # Only arXiv gets the contact; the other services get the bare User-Agent.
    with HttpClient(user_agent=DEFAULT_USER_AGENT, min_interval=OPENALEX_DELAY_SECONDS) as client:
        for category in categories:
            line = format_openalex_report(update_openalex_affiliations(store, category, client, today=today))
            console.print(line)
            github_summary(f"**Affiliations from OpenAlex.** {line}")
    return 0


def _run_archive_affiliations(args: argparse.Namespace) -> int:
    categories: list[str] = args.categories or [DEFAULT_CATEGORY]
    store = PaperStore(args.data_dir)
    today = datetime.now(tz=UTC).date()
    reading = _html_reading(args)
    if args.max_html != 0 and not args.contact:
        logger.warning("No contact given; consider setting %s so arXiv can reach you.", CONTACT_ENV_VAR)
    failed = False
    with (
        _terminate_as_interrupt(),
        HttpClient(user_agent=build_user_agent(args.contact), min_interval=args.crawl_delay) as site_client,
        # The contact is for arXiv only: other services get the bare User-Agent.
        HttpClient(user_agent=DEFAULT_USER_AGENT, min_interval=OPENALEX_DELAY_SECONDS) as openalex_client,
        HttpClient(user_agent=DEFAULT_USER_AGENT, min_interval=ROR_DELAY_SECONDS) as ror_client,
    ):
        for category in categories:
            report = update_archive_affiliations(
                store,
                category,
                openalex_client=openalex_client,
                today=today,
                site_client=site_client if args.max_html != 0 else None,
                html=reading,
                ror=Ror(ror_client if args.max_ror != 0 else None, args.max_ror),
            )
            line = format_archive_affiliations_report(report)
            console.print(line)
            github_summary(f"**Affiliations of the highly cited papers.** {line}")
            if report.failed:
                github_annotation("error", "Reading HTML pages failed", line)
            failed |= report.failed
    return 1 if failed else 0


def _run_code(args: argparse.Namespace) -> int:
    token = os.environ.get(GITHUB_AUTH_ENV)
    if not token:
        msg = f"No GitHub token: set {GITHUB_AUTH_ENV} (any token: it reads public data only)"
        raise ConfigurationError(msg)
    store = PaperStore(args.data_dir)
    categories: list[str] = args.categories or store.categories()
    # Only arXiv gets the contact; the other services get the bare User-Agent.
    with (
        HttpClient(user_agent=DEFAULT_USER_AGENT, min_interval=GITHUB_DELAY_SECONDS) as github,
        HttpClient(user_agent=DEFAULT_USER_AGENT, min_interval=HUGGINGFACE_DELAY_SECONDS) as hub,
    ):
        for category in categories:
            report = update_code_records(
                store, category, github=github, token=token, hub=hub, new_only=args.new
            )
            line = format_code_report(report)
            console.print(line)
            github_summary(f"**Stars of the code.** {line}")
    return 0


def _run_countries(args: argparse.Namespace) -> int:
    store = PaperStore(args.data_dir)
    categories: list[str] = args.categories or store.categories()
    # Only arXiv gets the contact; the other services get the bare User-Agent.
    with HttpClient(user_agent=DEFAULT_USER_AGENT, min_interval=OPENALEX_DELAY_SECONDS) as client:
        for category in categories:
            report = update_countries(store, category, client, refresh=args.all)
            line = format_countries_report(report)
            console.print(line)
            github_summary(f"**Countries of institutions.** {line}")
    return 0


def _run_trends(args: argparse.Namespace) -> int:
    categories: list[str] = args.categories or [DEFAULT_CATEGORY]
    store = PaperStore(args.data_dir)
    today = datetime.now(tz=UTC).date()
    for category in categories:
        catalog = Catalog(args.catalog_dir, category)
        _, citations = read_citations_cache(catalog.directory / f"{category}.citations.jsonl", today)
        try:
            trends = count_trends(catalog.entries().values(), citations)
        except ValueError as exc:  # no catalog yet, or one without a paper since 2010
            msg = (
                f"The catalog of {category} in {args.catalog_dir} holds no paper since 2010: "
                "archive harvests it"
            )
            raise StoreError(msg) from exc
        if not citations:
            logger.warning(
                "No citation counts of the week in %s: the topics' impact and key papers are left out",
                args.catalog_dir,
            )
        store.write_trends(category, trends, source=TRENDS_SOURCE if citations else TITLES_SOURCE)
        line = format_trends_report(category, trends)
        console.print(line)
        github_summary(f"**Trends.** {line}")
    return 0


def _semantic_scholar() -> tuple[HttpClient, str | None]:
    """A client for Semantic Scholar, and the API key it is used with (if any)."""
    key = api_key()
    if key:
        logger.info("Semantic Scholar: requests with an API key")
    else:
        logger.warning("No Semantic Scholar API key: citation counts will be slow to fetch.")
    # Only arXiv gets the contact; the other services get the bare User-Agent.
    client = HttpClient(
        user_agent=DEFAULT_USER_AGENT,
        min_interval=S2_DELAY_SECONDS if key else S2_ANONYMOUS_DELAY_SECONDS,
        max_attempts=1,  # fetch_citation_counts tries refused batches again
    )
    return client, key


def _run_citations(args: argparse.Namespace) -> int:
    store = PaperStore(args.data_dir)
    categories: list[str] = args.categories or store.categories()
    client, key = _semantic_scholar()
    with client:
        for category in categories:
            report = update_citation_counts(
                store,
                category,
                client,
                key=key,
                refresh=args.all,
                max_seconds=None if args.max_minutes is None else 60 * args.max_minutes,
            )
            line = format_citations_report(report)
            console.print(line)
            github_summary(f"**Citation counts.** {line}")
    return 0


def _run_scholar(args: argparse.Namespace) -> int:
    store = PaperStore(args.data_dir)
    categories: list[str] = args.categories or store.categories()
    client, key = _semantic_scholar()
    with client:
        for category in categories:
            report = update_scholar_records(
                store,
                category,
                client,
                key=key,
                max_seconds=None if args.max_minutes is None else 60 * args.max_minutes,
            )
            line = format_scholar_report(report)
            console.print(line)
            github_summary(f"**Published versions.** {line}")
    return 0


def _run_summary(args: argparse.Namespace) -> int:
    store = PaperStore(args.data_dir)
    today = datetime.now(tz=UTC).date()
    lines: list[str] = []
    tables: list[str] = []
    quality: list[str] = []
    for category in store.categories():
        if days := collect_coverage(store, category):
            newest = store.days(category)[0]
            late = weekdays_since(newest, today)
            lines.append(f"{category}: newest announcement day {newest.isoformat()}, {late} weekdays ago")
            if late > STALE_DATA_WEEKDAYS:
                github_annotation("warning", "Stale data", f"{category}: no new day for {late} weekdays")
            tables.append(format_coverage(category, days))
            quality.append(
                format_quality(
                    f"{category}: signs of wrong affiliations",
                    affiliation_quality(store.iter_papers(category)),
                    examples=False,
                )
            )
        if years := collect_archive_coverage(store, category):
            tables.append(format_archive_coverage(category, years))
        if citations := store.load_citation_counts(category):
            lines.append(format_citations(category, citations, today=today))
            if (today - citations.generated_at.date()).days > STALE_CITATIONS_DAYS:
                github_annotation("warning", "Stale citation counts", lines[-1])
    console.print("\n".join(lines))
    console.print()
    console.print("\n\n".join([*tables, *quality]))
    github_summary(
        "### Data\n\n"
        + "".join(f"- {line}\n" for line in lines)
        + _details("Coverage by day and by archive year", tables)
        + _details("Signs of wrong affiliations (`stats --affiliations` lists examples)", quality)
    )
    return 0


def _details(title: str, blocks: Sequence[str]) -> str:
    """Plain-text blocks folded under ``title`` in the job summary, or nothing without blocks."""
    if not blocks:
        return ""
    return f"\n<details><summary>{title}</summary>\n\n```\n" + "\n\n".join(blocks) + "\n```\n\n</details>\n"


def _run_index(args: argparse.Namespace) -> int:
    console.print(f"Index written to {PaperStore(args.data_dir).write_index()}")
    return 0


def _run_reclean(args: argparse.Namespace) -> int:
    store = PaperStore(args.data_dir)
    for category in args.categories or store.categories():
        report = reclean_store(store, category)
        written = f"{report.days} day files" + (" and the archive" if report.archive else "")
        console.print(
            f"{category}: {report.changed} of {report.papers} affiliated papers changed, in {written}"
        )
    return 0


def _run_venues(args: argparse.Namespace) -> int:
    store = PaperStore(args.data_dir)
    for category in args.categories or store.categories():
        report = detect_venues_again(store, category)
        written = f"{report.days} day files" + (" and the archive" if report.archive else "")
        console.print(
            f"{category}: {report.changed} of {report.papers} papers changed, in {written}; "
            f"venues {report.before} -> {report.after}, {report.abstracts} abstracts made plain"
        )
    return 0


def _run_validate(args: argparse.Namespace) -> int:
    report = validate_store(PaperStore(args.data_dir))
    for finding in report.findings:
        console.print(str(finding))
    console.print(report.summary())
    return 1 if report.errors else 0


def _run_archive(args: argparse.Namespace) -> int:
    categories: list[str] = args.categories or [DEFAULT_CATEGORY]
    store = PaperStore(args.data_dir)
    citations, key = _semantic_scholar()
    today = datetime.now(tz=UTC).date()
    with (
        # OAI-PMH is arXiv's: the harvest gets the contact, Semantic Scholar and OpenAlex do not.
        HttpClient(
            user_agent=build_user_agent(args.contact),
            min_interval=OAI_DELAY_SECONDS,
            timeout=OAI_TIMEOUT_SECONDS,
        ) as oai,
        citations,
        HttpClient(user_agent=DEFAULT_USER_AGENT, min_interval=OPENALEX_DELAY_SECONDS) as openalex,
    ):
        clients = ArchiveClients(oai=oai, citations=citations, openalex=openalex, citations_key=key)
        gated: list[str] = []
        for category in categories:
            report = update_archive(
                category,
                store=store,
                catalog=Catalog(args.catalog_dir, category),
                clients=clients,
                budget=args.budget,
                today=today,
                prune=args.prune,
                dry_run=args.dry_run,
            )
            line = format_archive_report(report)
            console.print(line)
            github_summary(f"**Archive.** {line}")
            if report.coverage < MIN_COVERAGE:
                gated.append(category)
                github_annotation("error", "Archive not updated", f"Too few citation counts. {line}")
    if gated:
        # The archive was left as it is, and the counts merged: a red run, after the commit.
        logger.error("Too few citation counts: the archive of %s was not updated", ", ".join(gated))
        return 1
    return 0


def _category(value: str) -> str:
    try:
        return validate_category(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        msg = f"Invalid date: {value!r} (expected YYYY-MM-DD)."
        raise argparse.ArgumentTypeError(msg) from exc


def _configure_logging(level: int) -> None:
    configure_logging(level)
    # httpx logs every request at INFO level; only show it in debug mode.
    logging.getLogger("httpx").setLevel(logging.DEBUG if level <= logging.DEBUG else logging.WARNING)


_COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "update": _run_update,
    "backfill": _run_backfill,
    "stats": _run_stats,
    "institutions": _run_institutions,
    "affiliations": _run_affiliations,
    "archive-affiliations": _run_archive_affiliations,
    "archive": _run_archive,
    "citations": _run_citations,
    "index": _run_index,
    "reclean": _run_reclean,
    "venues": _run_venues,
    "scholar": _run_scholar,
    "code": _run_code,
    "countries": _run_countries,
    "trends": _run_trends,
    "validate": _run_validate,
    "summary": _run_summary,
    "reextract": _run_reextract,
}
