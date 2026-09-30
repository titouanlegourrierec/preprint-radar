"""Command-line interface."""

import argparse
import logging
import os
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from preprint_radar import __version__
from preprint_radar.archive.catalog import Catalog
from preprint_radar.archive.update import ArchiveClients, format_archive_report, update_archive
from preprint_radar.collect import (
    add_institutions,
    backfill_category,
    format_citations_report,
    format_report,
    update_category,
    update_citation_counts,
)
from preprint_radar.config import (
    CONTACT_ENV_VAR,
    DEFAULT_BUDGET,
    DEFAULT_CATALOG_DIR,
    DEFAULT_CATEGORY,
    DEFAULT_DATA_DIR,
    DEFAULT_EXPORT_DIR,
    DEFAULT_MAX_ROR_LOOKUPS,
)
from preprint_radar.console import configure_logging, console
from preprint_radar.exceptions import PreprintRadarError
from preprint_radar.http import (
    ARXIV_API_DELAY_SECONDS,
    ARXIV_CRAWL_DELAY_SECONDS,
    DEFAULT_USER_AGENT,
    HttpClient,
    build_user_agent,
)
from preprint_radar.sources.arxiv_listing import MAX_LISTING_ENTRIES, fetch_listing, validate_category
from preprint_radar.sources.arxiv_oai import OAI_DELAY_SECONDS, OAI_TIMEOUT_SECONDS
from preprint_radar.sources.openalex import OPENALEX_DELAY_SECONDS
from preprint_radar.sources.ror import ROR_DELAY_SECONDS
from preprint_radar.sources.semantic_scholar import S2_ANONYMOUS_DELAY_SECONDS, S2_DELAY_SECONDS, api_key
from preprint_radar.store import filters
from preprint_radar.store.export import ExportFormat, export_papers
from preprint_radar.store.paper_store import PaperStore
from preprint_radar.store.stats import (
    archive_coverage_table,
    collect_archive_coverage,
    collect_coverage,
    coverage_table,
    format_archive_coverage,
    format_citations,
    format_coverage,
)

if TYPE_CHECKING:
    from rich.table import Table

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
            "authors (mapped) and with at least one institution named (named)."
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
            "SEMANTIC_SCHOLAR_API_KEY. A failing Semantic Scholar never fails the command: "
            "the papers left are asked for again next time."
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

    with (
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
                max_html_fetches=args.max_html,
                max_ror_lookups=args.max_ror,
            )
            console.print(format_report(report))

    console.print(f"Index written to {store.write_index()}")
    return 0


def _run_backfill(args: argparse.Namespace) -> int:
    categories: list[str] = args.categories or [DEFAULT_CATEGORY]
    store = PaperStore(args.data_dir)
    until: date = args.until or datetime.now(tz=UTC).date()
    days = [args.since + timedelta(days=offset) for offset in range((until - args.since).days + 1)]
    if not args.contact:
        logger.warning("No contact given; consider setting %s so arXiv can reach you.", CONTACT_ENV_VAR)

    user_agent = build_user_agent(args.contact)
    with (
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
                max_html_fetches=args.max_html,
                max_ror_lookups=args.max_ror,
            )
            console.print(format_report(report))

    console.print(f"Index written to {store.write_index()}")
    return 0


def _run_stats(args: argparse.Namespace) -> int:
    store = PaperStore(args.data_dir)
    categories: list[str] = args.categories or store.categories()
    if not categories:
        logger.warning("The store %s is empty; run `preprint-radar update` first.", args.data_dir)
        return 1

    # A terminal gets rich tables; CI and pipes the plain text, one line per row.
    styled = console.is_terminal
    reports: list[str | Table] = []
    for category in categories:
        days = collect_coverage(store, category)
        years = collect_archive_coverage(store, category)
        if not days and not years:
            logger.warning("No stored papers for %s in %s.", category, args.data_dir)
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
            reports.append(format_citations(category, citations))
    for index, report in enumerate(reports):
        if index:
            console.print()
        console.print(report)
    return 0 if reports else 1


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
            report = update_citation_counts(store, category, client, key=key, refresh=args.all)
            console.print(format_citations_report(report))
    return 0


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
            console.print(format_archive_report(report))
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
}
