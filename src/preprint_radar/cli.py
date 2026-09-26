"""Command-line interface."""

import argparse
import logging
import os
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from preprint_radar import __version__, filters
from preprint_radar.exceptions import PreprintRadarError
from preprint_radar.export import ExportFormat, export_papers
from preprint_radar.http import (
    ARXIV_API_DELAY_SECONDS,
    ARXIV_CRAWL_DELAY_SECONDS,
    HttpClient,
    build_user_agent,
)
from preprint_radar.listing import MAX_LISTING_ENTRIES, fetch_listing, validate_category
from preprint_radar.pipeline import backfill_category, format_report, update_category
from preprint_radar.stats import collect_coverage, format_coverage
from preprint_radar.store import PaperStore

logger = logging.getLogger(__name__)

DEFAULT_CATEGORY = "cs.CV"
DEFAULT_EXPORT_DIR = Path("exports")
DEFAULT_DATA_DIR = Path("data")
CONTACT_ENV_VAR = "PREPRINT_RADAR_CONTACT"


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
            "Show, for each stored announcement day, how many papers have an abstract, "
            "affiliations and a detected venue. Affiliation columns: at least one found "
            "(affiliated), searched without success (none), not retrieved yet (pending)."
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
        match args.command:
            case "fetch":
                return _run_fetch(args)
            case "update":
                return _run_update(args)
            case "backfill":
                return _run_backfill(args)
            case "stats":
                return _run_stats(args)
            case _:  # pragma: no cover - argparse rejects unknown commands
                msg = f"Unknown command: {args.command}"
                raise AssertionError(msg)
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
        print(f"{day.isoformat()}: {count} papers")  # noqa: T201 - user-facing CLI output
    print(f"Total: {len(papers)} papers written to {output}")  # noqa: T201
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
    ):
        for category in categories:
            report = update_category(
                category,
                store=store,
                site_client=site_client,
                api_client=api_client,
                max_html_fetches=args.max_html,
            )
            print(format_report(report))  # noqa: T201 - user-facing CLI output

    print(f"Index written to {store.write_index()}")  # noqa: T201
    return 0


def _run_backfill(args: argparse.Namespace) -> int:
    categories: list[str] = args.categories or [DEFAULT_CATEGORY]
    store = PaperStore(args.data_dir)
    until: date = args.until or datetime.now(tz=UTC).date()
    days = [args.since + timedelta(days=offset) for offset in range((until - args.since).days + 1)]
    if not args.contact:
        logger.warning("No contact given; consider setting %s so arXiv can reach you.", CONTACT_ENV_VAR)

    with HttpClient(user_agent=build_user_agent(args.contact), min_interval=args.crawl_delay) as site_client:
        for category in categories:
            report = backfill_category(
                category, days, store=store, site_client=site_client, max_html_fetches=args.max_html
            )
            print(format_report(report))  # noqa: T201 - user-facing CLI output

    print(f"Index written to {store.write_index()}")  # noqa: T201
    return 0


def _run_stats(args: argparse.Namespace) -> int:
    store = PaperStore(args.data_dir)
    categories: list[str] = args.categories or store.categories()
    if not categories:
        logger.warning("The store %s is empty; run `preprint-radar update` first.", args.data_dir)
        return 1

    reports = []
    for category in categories:
        if days := collect_coverage(store, category):
            reports.append(format_coverage(category, days))
        else:
            logger.warning("No stored papers for %s in %s.", category, args.data_dir)
    print("\n\n".join(reports))  # noqa: T201 - user-facing CLI output
    return 0 if reports else 1


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
    level = {0: logging.WARNING, 1: logging.INFO}.get(verbosity, logging.DEBUG)
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")
    # httpx logs every request at INFO level; only show it in debug mode.
    logging.getLogger("httpx").setLevel(logging.DEBUG if verbosity > 1 else logging.WARNING)
