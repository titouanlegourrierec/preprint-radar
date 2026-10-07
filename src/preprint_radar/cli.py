"""Command-line interface."""

import argparse
import logging
import os
import re
import signal
import time
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from rich.table import Table

from preprint_radar import __version__
from preprint_radar.archive.catalog import Catalog
from preprint_radar.archive.update import ArchiveClients, format_archive_report, update_archive
from preprint_radar.collect import (
    HtmlReading,
    Stop,
    UpdateReport,
    add_institutions,
    backfill_category,
    format_citations_report,
    format_report,
    format_scholar_report,
    reextract_category,
    update_category,
    update_citation_counts,
    update_scholar_records,
)
from preprint_radar.config import (
    CONTACT_ENV_VAR,
    DEFAULT_BUDGET,
    DEFAULT_CATALOG_DIR,
    DEFAULT_CATEGORY,
    DEFAULT_DATA_DIR,
    DEFAULT_EXPORT_DIR,
    DEFAULT_MAX_ROR_LOOKUPS,
    DEFAULT_PAGE_CACHE_DIR,
    MIN_COVERAGE,
    STALE_CITATIONS_DAYS,
    STALE_DATA_WEEKDAYS,
)
from preprint_radar.console import configure_logging, console, github_annotation, github_summary
from preprint_radar.exceptions import PreprintRadarError
from preprint_radar.http import (
    ARXIV_API_DELAY_SECONDS,
    ARXIV_CRAWL_DELAY_SECONDS,
    DEFAULT_USER_AGENT,
    HttpClient,
    build_user_agent,
)
from preprint_radar.models import Paper
from preprint_radar.sources.arxiv_html import EXTRACTOR_VERSION, PageCache
from preprint_radar.sources.arxiv_listing import MAX_LISTING_ENTRIES, fetch_listing, validate_category
from preprint_radar.sources.arxiv_oai import OAI_DELAY_SECONDS, OAI_TIMEOUT_SECONDS
from preprint_radar.sources.openalex import OPENALEX_DELAY_SECONDS
from preprint_radar.sources.ror import ROR_DELAY_SECONDS
from preprint_radar.sources.semantic_scholar import S2_ANONYMOUS_DELAY_SECONDS, S2_DELAY_SECONDS, api_key
from preprint_radar.store import filters
from preprint_radar.store.export import ExportFormat, export_papers
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

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="preprint-radar",
        description="Collect arXiv papers to support a literature review.",
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
        "--contact",
        default=os.environ.get(CONTACT_ENV_VAR),
        help=f"e-mail or URL sent in the User-Agent so arXiv can reach you (env: {CONTACT_ENV_VAR})",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    _add_fetch_parser(subparsers)
    _add_update_parser(subparsers)
    _add_backfill_parser(subparsers)
    _add_stats_parser(subparsers)
    _add_institutions_parser(subparsers)
    _add_archive_parser(subparsers)
    _add_citations_parser(subparsers)
    _add_index_parser(subparsers)
    _add_reclean_parser(subparsers)
    _add_scholar_parser(subparsers)
    _add_venues_parser(subparsers)
    _add_validate_parser(subparsers)
    _add_summary_parser(subparsers)
    _add_reextract_parser(subparsers)
    return parser


def _add_fetch_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    fetch = subparsers.add_parser(
        "fetch",
        help="export the recent listing of a category to JSON or CSV",
        description="Export the papers announced over the last few days in an arXiv category.",
    )
    fetch.add_argument(
        "-c",
        "--category",
        type=_category,
        default=DEFAULT_CATEGORY,
        help=f"arXiv category (default: {DEFAULT_CATEGORY})",
    )
    fetch.add_argument(
        "-o",
        "--output",
        type=Path,
        help=f"output file (default: {DEFAULT_EXPORT_DIR}/<category>_<latest date>.<format>)",
    )
    fetch.add_argument(
        "-f",
        "--format",
        type=ExportFormat,
        choices=list(ExportFormat),
        help="output format (default: inferred from --output, else json)",
    )
    fetch.add_argument("--latest-only", action="store_true", help="keep only the most recent day")
    fetch.add_argument(
        "--exclude-cross-lists",
        action="store_true",
        help="drop papers cross-listed from other categories",
    )
    fetch.add_argument(
        "--max-entries",
        type=int,
        default=MAX_LISTING_ENTRIES,
        help=f"maximum number of entries to request (default: {MAX_LISTING_ENTRIES})",
    )


def _add_update_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    update = subparsers.add_parser(
        "update",
        help="add recent papers to the data store, with abstracts and affiliations",
        description=(
            "Fetch the recent listing of each category, retrieve abstracts from the arXiv API "
            "and affiliations from the HTML renderings, and save everything to the data store "
            "used by the web app."
        ),
    )
    _add_store_arguments(update)


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
    _add_store_arguments(backfill)


def _add_stats_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    stats = subparsers.add_parser(
        "stats",
        help="show how much of the data store is enriched",
        description=(
            "Show, for each stored announcement day, then each archive year, how many papers "
            "have an abstract, affiliations, a detected venue and a citation count. "
            "Affiliation columns: at least one found (affiliated), searched without success "
            "(none), not retrieved yet (pending); of the affiliated papers, mapped to their "
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
    stats.add_argument(
        "-c",
        "--category",
        dest="categories",
        action="append",
        type=_category,
        help="arXiv category, repeatable (default: every category in the store)",
    )
    stats.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"data store directory (default: {DEFAULT_DATA_DIR})",
    )


def _add_institutions_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    institutions = subparsers.add_parser(
        "institutions",
        help="name the institutions of stored affiliations",
        description=(
            "Look up, in the Research Organization Registry, the stored affiliations whose "
            "institution is not named yet. Update and backfill do it for the papers they "
            "handle; this command catches up on the rest of the store."
        ),
    )
    institutions.add_argument(
        "-c",
        "--category",
        dest="categories",
        action="append",
        type=_category,
        help="arXiv category, repeatable (default: every category in the store)",
    )
    institutions.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"data store directory (default: {DEFAULT_DATA_DIR})",
    )
    institutions.add_argument(
        "--max-ror",
        type=int,
        default=None,
        help="maximum number of affiliations to look up (default: no limit)",
    )


def _add_archive_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    archive = subparsers.add_parser(
        "archive",
        help="keep the most cited older papers in the archive (weekly)",
        description=(
            "Refresh the category's catalog from OAI-PMH, fetch citation counts from "
            "Semantic Scholar (API key from SEMANTIC_SCHOLAR_API_KEY, else anonymously and "
            "slowly), keep the papers older than 12 months with the most citations per year "
            "within the budget, and write the archive and the citation counts."
        ),
    )
    archive.add_argument(
        "-c",
        "--category",
        dest="categories",
        action="append",
        type=_category,
        help=f"arXiv category, repeatable (default: {DEFAULT_CATEGORY})",
    )
    archive.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"data store directory (default: {DEFAULT_DATA_DIR})",
    )
    archive.add_argument(
        "--catalog-dir",
        type=Path,
        default=DEFAULT_CATALOG_DIR,
        help=f"where the harvested catalog is kept (default: {DEFAULT_CATALOG_DIR})",
    )
    archive.add_argument(
        "--budget",
        type=int,
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
            "SEMANTIC_SCHOLAR_API_KEY. A refusing Semantic Scholar never fails the command: "
            "the papers left are asked for again next time. A rejected key does."
        ),
    )
    citations.add_argument(
        "-c",
        "--category",
        dest="categories",
        action="append",
        type=_category,
        help="arXiv category, repeatable (default: every category in the store)",
    )
    citations.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"data store directory (default: {DEFAULT_DATA_DIR})",
    )
    citations.add_argument("--all", action="store_true", help="fetch the counts of every stored paper again")
    citations.add_argument(
        "--max-minutes",
        type=float,
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
            "workflow does. API key from SEMANTIC_SCHOLAR_API_KEY. Papers Semantic Scholar "
            "was not asked for, because it kept refusing, keep what they had. A rejected key "
            "fails the command."
        ),
    )
    scholar.add_argument(
        "-c",
        "--category",
        dest="categories",
        action="append",
        type=_category,
        help="arXiv category, repeatable (default: every category in the store)",
    )
    scholar.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"data store directory (default: {DEFAULT_DATA_DIR})",
    )
    scholar.add_argument(
        "--max-minutes",
        type=float,
        default=None,
        help="stop asking a refusing Semantic Scholar after this long (default: no limit)",
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
    index.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"data store directory (default: {DEFAULT_DATA_DIR})",
    )


def _add_reclean_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    reclean = subparsers.add_parser(
        "reclean",
        help="clean the stored affiliations again with the current rules",
        description=(
            "Apply the current affiliation cleaning to the stored day files, after a change "
            "to the heuristics: contact details, junk and author names are dropped, strings "
            "holding several affiliations are split, and the author mapping follows them. "
            "Changed affiliations lose their institutions, which `institutions` names again. "
            "Nothing is fetched, and the citation archive is left as it is."
        ),
    )
    reclean.add_argument(
        "-c",
        "--category",
        dest="categories",
        action="append",
        type=_category,
        help="arXiv category, repeatable (default: every category in the store)",
    )
    reclean.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"data store directory (default: {DEFAULT_DATA_DIR})",
    )


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
    venues.add_argument(
        "-c",
        "--category",
        dest="categories",
        action="append",
        type=_category,
        help="arXiv category, repeatable (default: every category in the store)",
    )
    venues.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"data store directory (default: {DEFAULT_DATA_DIR})",
    )


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
        "--match", type=re.compile, metavar="REGEX", help="papers with an affiliation that this regex finds"
    )
    _add_store_arguments(reextract)


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
    summary.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"data store directory (default: {DEFAULT_DATA_DIR})",
    )


def _add_validate_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    validate = subparsers.add_parser(
        "validate",
        help="check the data store against its contract",
        description=(
            "Check every file of the data store before it is committed: day files, archive "
            "years, citation counts and the index. Structural rules (a record that does not "
            "load, a paper stored twice, an index that disagrees with the files, a contact "
            "detail in an affiliation) are errors and make the command fail; heuristic rules "
            "(an affiliation that only names authors, a paper `reclean` would still change) "
            "are warnings. Nothing is fetched or written."
        ),
    )
    validate.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"data store directory (default: {DEFAULT_DATA_DIR})",
    )


def _add_store_arguments(parser: argparse.ArgumentParser) -> None:
    """Options shared by the commands that write to the data store."""
    parser.add_argument(
        "-c",
        "--category",
        dest="categories",
        action="append",
        type=_category,
        help=f"arXiv category, repeatable (default: {DEFAULT_CATEGORY})",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"data store directory (default: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--max-html",
        type=int,
        default=None,
        help="maximum number of HTML pages to download per category (default: no limit; 0 disables)",
    )
    parser.add_argument(
        "--max-ror",
        type=int,
        default=DEFAULT_MAX_ROR_LOOKUPS,
        help=(
            "maximum number of affiliations to look up in the Research Organization Registry "
            f"(default: {DEFAULT_MAX_ROR_LOOKUPS}; 0 disables)"
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
        type=float,
        default=None,
        help=(
            "start no HTML page after this many minutes, so that the run ends cleanly before "
            "a time limit; the pages left wait for the next run (default: no deadline)"
        ),
    )
    parser.add_argument(
        "--crawl-delay",
        type=float,
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
    _configure_logging(args.verbose)
    try:
        return _COMMANDS[args.command](args)
    except PreprintRadarError as exc:
        logger.error("%s", exc)  # noqa: TRY400 - the message is enough, no traceback for users
        # On the run's page, which otherwise only says that the step exited with 1.
        github_annotation("error", f"preprint-radar {args.command} failed", str(exc))
        return 1


def _run_fetch(args: argparse.Namespace) -> int:
    with HttpClient(user_agent=build_user_agent(args.contact)) as client:
        listing = fetch_listing(client, args.category, max_entries=args.max_entries)

    papers = list(listing.papers)
    if args.latest_only:
        papers = filters.latest_day(papers)
    if args.exclude_cross_lists:
        papers = filters.exclude_cross_lists(papers)
    if not papers:
        logger.warning("No papers left to export.")
        return 0

    fmt: ExportFormat = (
        args.format or (args.output and ExportFormat.from_path(args.output)) or ExportFormat.JSON
    )
    latest = max(paper.announced for paper in papers)
    output: Path = args.output or DEFAULT_EXPORT_DIR / f"{args.category}_{latest.isoformat()}.{fmt}"
    export_papers(papers, output, fmt)

    for day, count in sorted(Counter(paper.announced for paper in papers).items(), reverse=True):
        console.print(f"{day.isoformat()}: {count} papers")
    console.print(f"Total: {len(papers)} papers written to {output}")
    return 0


def _run_update(args: argparse.Namespace) -> int:
    categories: list[str] = args.categories or [DEFAULT_CATEGORY]
    store = PaperStore(args.data_dir)
    user_agent = build_user_agent(args.contact)
    if not args.contact:
        logger.warning("No contact given; consider setting %s so arXiv can reach you.", CONTACT_ENV_VAR)

    reading = _html_reading(args)
    reports: list[UpdateReport] = []
    # The index is written even after a failure, so that the days saved meanwhile show.
    try:
        with (
            _terminate_as_interrupt(),
            HttpClient(user_agent=user_agent, min_interval=args.crawl_delay) as site_client,
            HttpClient(user_agent=user_agent, min_interval=ARXIV_API_DELAY_SECONDS) as api_client,
            # The contact is for arXiv only: other services get the bare User-Agent.
            HttpClient(user_agent=DEFAULT_USER_AGENT, min_interval=ROR_DELAY_SECONDS) as ror_client,
        ):
            for category in categories:
                report = update_category(
                    category,
                    store=store,
                    site_client=site_client,
                    api_client=api_client,
                    ror_client=ror_client if args.max_ror else None,
                    max_ror_lookups=args.max_ror,
                    html=reading,
                )
                _publish_update(report)
                reports.append(report)
    finally:
        console.print(f"Index written to {store.write_index()}")
    return _exit_code(reports)


def _run_backfill(args: argparse.Namespace) -> int:
    categories: list[str] = args.categories or [DEFAULT_CATEGORY]
    store = PaperStore(args.data_dir)
    until: date = args.until or datetime.now(tz=UTC).date()
    days = [args.since + timedelta(days=offset) for offset in range((until - args.since).days + 1)]
    if not args.contact:
        logger.warning("No contact given; consider setting %s so arXiv can reach you.", CONTACT_ENV_VAR)

    user_agent = build_user_agent(args.contact)
    reading = _html_reading(args)
    reports: list[UpdateReport] = []
    # The index is written even after a failure, so that the days saved meanwhile show.
    try:
        with (
            _terminate_as_interrupt(),
            HttpClient(user_agent=user_agent, min_interval=args.crawl_delay) as site_client,
            # The contact is for arXiv only: other services get the bare User-Agent.
            HttpClient(user_agent=DEFAULT_USER_AGENT, min_interval=ROR_DELAY_SECONDS) as ror_client,
        ):
            for category in categories:
                report = backfill_category(
                    category,
                    days,
                    store=store,
                    site_client=site_client,
                    ror_client=ror_client if args.max_ror else None,
                    max_ror_lookups=args.max_ror,
                    html=reading,
                )
                _publish_update(report)
                reports.append(report)
    finally:
        console.print(f"Index written to {store.write_index()}")
    return _exit_code(reports)


def _publish_update(report: UpdateReport) -> None:
    """Print an update report, and put it on the run's page in GitHub Actions."""
    line = format_report(report)
    console.print(line)
    github_summary(f"**Papers.** {line}")
    if report.stopped is Stop.DEADLINE:
        github_annotation("warning", "Out of time", line)
    elif report.failed:
        github_annotation("error", "Reading HTML pages failed", line)


def _run_reextract(args: argparse.Namespace) -> int:
    categories: list[str] = args.categories or [DEFAULT_CATEGORY]
    store = PaperStore(args.data_dir)
    select = _reextract_selection(args)
    reading = _html_reading(args)
    reports: list[UpdateReport] = []
    user_agent = build_user_agent(args.contact)
    try:
        with (
            _terminate_as_interrupt(),
            HttpClient(user_agent=user_agent, min_interval=args.crawl_delay) as site_client,
            # The contact is for arXiv only: other services get the bare User-Agent.
            HttpClient(user_agent=DEFAULT_USER_AGENT, min_interval=ROR_DELAY_SECONDS) as ror_client,
        ):
            for category in categories:
                report = reextract_category(
                    category,
                    select,
                    store=store,
                    site_client=site_client,
                    ror_client=ror_client if args.max_ror else None,
                    max_ror_lookups=args.max_ror,
                    html=reading,
                )
                _publish_update(report)
                reports.append(report)
    finally:
        console.print(f"Index written to {store.write_index()}")
    return _exit_code(reports)


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
    """1 when the reading of HTML pages stopped on a failure (arXiv down, layout changed)."""
    failed = [report.category for report in reports if report.failed]
    if failed:
        logger.error("Reading HTML pages failed for %s: see above", ", ".join(failed))
        return 1
    return 0


@contextmanager
def _terminate_as_interrupt() -> Iterator[None]:
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
    with HttpClient(user_agent=DEFAULT_USER_AGENT, min_interval=ROR_DELAY_SECONDS) as client:
        for category in categories:
            papers = list(store.iter_papers(category))
            named = add_institutions(papers, client, limit=args.max_ror)
            changed = [new for old, new in zip(papers, named, strict=True) if new is not old]
            store.save(category, changed)
            pending = sum(bool(paper.affiliations) and paper.institutions is None for paper in named)
            console.print(
                f"{category}: institutions named for {len(changed)} papers, {pending} still pending"
            )
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
        console.print(
            f"{category}: {report.changed} of {report.papers} affiliated papers changed, "
            f"in {report.days} day files"
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
        HttpClient(
            user_agent=DEFAULT_USER_AGENT, min_interval=OAI_DELAY_SECONDS, timeout=OAI_TIMEOUT_SECONDS
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


def _configure_logging(verbosity: int) -> None:
    configure_logging({0: logging.WARNING, 1: logging.INFO}.get(verbosity, logging.DEBUG))
    # httpx logs every request at INFO level; only show it in debug mode.
    logging.getLogger("httpx").setLevel(logging.DEBUG if verbosity > 1 else logging.WARNING)


_COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "fetch": _run_fetch,
    "update": _run_update,
    "backfill": _run_backfill,
    "stats": _run_stats,
    "institutions": _run_institutions,
    "archive": _run_archive,
    "citations": _run_citations,
    "index": _run_index,
    "reclean": _run_reclean,
    "venues": _run_venues,
    "scholar": _run_scholar,
    "validate": _run_validate,
    "summary": _run_summary,
    "reextract": _run_reextract,
}
