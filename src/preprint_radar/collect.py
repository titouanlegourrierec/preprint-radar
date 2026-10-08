"""Update pipelines: listing -> store, enriching new papers along the way.

- :func:`update_category` follows the recent listing (the last few announcement days);
- :func:`backfill_category` collects past days from the catchup pages;
- :func:`update_citation_counts` gives the stored papers their citation counts.
"""

import logging
import math
import re
import time
import unicodedata
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from enum import StrEnum

from preprint_radar.config import DEFAULT_MAX_ROR_LOOKUPS, DEFAULT_SAVE_EVERY
from preprint_radar.exceptions import FetchError, ParseError
from preprint_radar.http import HttpClient
from preprint_radar.institutions import PLAIN_LETTERS, name_institutions
from preprint_radar.models import Institution, Listing, Paper, Provenance, ScholarRecord
from preprint_radar.sources.arxiv_api import fetch_metadata
from preprint_radar.sources.arxiv_html import (
    EXTRACTOR_VERSION,
    FrontMatter,
    PageCache,
    fetch_front_matter,
    name_key,
)
from preprint_radar.sources.arxiv_listing import fetch_catchup, fetch_listing
from preprint_radar.sources.arxiv_rss import fetch_rss_abstracts
from preprint_radar.sources.ror import match_institutions
from preprint_radar.sources.semantic_scholar import S2_SOURCE, fetch_citation_counts, fetch_scholar_records
from preprint_radar.store.paper_store import PaperStore

logger = logging.getLogger(__name__)


def today() -> date:
    """The day of a reading, in UTC, for the provenance of what it gives."""
    return datetime.now(tz=UTC).date()


# Reading HTML pages stops after this many failures in a row: arxiv.org is down for now, and
# each failing page costs minutes of retries.
MAX_CONSECUTIVE_HTML_FAILURES = 5
# A backfill stops asking for catchup pages after this many days in a row it could not read:
# arxiv.org is down, or their layout changed, and each failing day costs a minute of retries.
MAX_CONSECUTIVE_DAY_FAILURES = 3
# Past this many pages read, a share of pages without affiliations this high is a layout
# change (or HTML URLs that moved), not a bad day: 12 to 31% of the pages of a day give none.
DRIFT_MIN_PAGES = 40
DRIFT_EMPTY_SHARE = 0.9


class Stop(StrEnum):
    """Why the reading of HTML pages stopped before the end."""

    DEADLINE = "deadline"
    """Out of time: the pages left wait for the next run."""
    FAILURES = "failures"
    """arxiv.org failed page after page."""
    LAYOUT = "layout"
    """Nearly every page gave no affiliation: their papers wait for the next run."""


@dataclass(frozen=True, slots=True)
class HtmlReading:
    """How the HTML pages of a run are read.

    Attributes:
        limit: Pages to download at most (``None``: no limit, ``0``: none). Pages the
            cache holds are read from it, and do not count.
        save_every: Save progress after this many pages.
        deadline: ``time.monotonic()`` value after which no page is started (nor, in a
            backfill, a catchup page), so that the run ends cleanly before it is killed
            (``None``: no deadline).
        cache: Pages read before (their front matter); pages downloaded are added to it.
    """

    limit: int | None = None
    save_every: int = DEFAULT_SAVE_EVERY
    deadline: float | None = None
    cache: PageCache | None = None


@dataclass(frozen=True, slots=True)
class UpdateReport:
    """Summary of an update run for one category.

    Attributes:
        category: Updated category.
        listed: Papers found in the listing.
        new: Papers that were not in the store before.
        abstracts_fetched: Abstracts retrieved during this run.
        affiliations_fetched: Papers whose affiliations were retrieved during this run.
        pending: Papers still missing an abstract or affiliations after the run, which a
            later run can still read.
        no_page: Papers without affiliations nor an HTML rendering: no run reads them
            (DATA-4).
        empty: Of the HTML pages read, those that gave no affiliation.
        unreadable: HTML pages that could not be fetched (tried again next run).
        stopped: Why the reading of HTML pages stopped early, if it did.
        failed_days: Days of a backfill whose catchup page failed or came back incomplete:
            not saved, they are fetched again next run.
    """

    category: str
    listed: int
    new: int
    abstracts_fetched: int
    affiliations_fetched: int
    pending: int
    no_page: int = 0
    empty: int = 0
    unreadable: int = 0
    stopped: Stop | None = None
    failed_days: tuple[date, ...] = ()

    @property
    def html_failed(self) -> bool:
        """Whether the reading of HTML pages stopped on a failure (arXiv down, layout changed)."""
        return self.stopped in {Stop.FAILURES, Stop.LAYOUT}

    @property
    def failed(self) -> bool:
        """Whether the run should be red: HTML reading failed, or days could not be read."""
        return self.html_failed or bool(self.failed_days)


def update_category(
    category: str,
    *,
    store: PaperStore,
    site_client: HttpClient,
    api_client: HttpClient,
    ror_client: HttpClient | None = None,
    max_ror_lookups: int | None = DEFAULT_MAX_ROR_LOOKUPS,
    html: HtmlReading | None = None,
) -> UpdateReport:
    """Fetch the recent listing of ``category``, enrich new papers and store them.

    Enrichment already performed in a previous run (in any category) is reused, so
    each paper is enriched once. Progress is saved regularly so that an interrupted
    run does not lose the pages already fetched.

    Args:
        category: arXiv category, e.g. ``"cs.CV"``.
        store: Destination store.
        site_client: Client for arxiv.org (listing and HTML pages).
        api_client: Client for the arXiv API.
        ror_client: Client for the Research Organization Registry, to name the
            institutions of the affiliations (``None``: skip).
        max_ror_lookups: Maximum number of affiliation strings to look up in ROR.
        html: How HTML pages are read (limit, saves, deadline, cache).

    Returns:
        A summary of the run.
    """
    listing = fetch_listing(site_client, category)
    known = {paper.arxiv_id: paper for paper in store.iter_papers()}
    papers = [_carry_over(paper, known.get(paper.arxiv_id)) for paper in listing.papers]
    new = sum(paper.arxiv_id not in known for paper in papers)
    logger.info("%s: %d papers listed, %d new", category, len(papers), new)

    papers, abstracts_fetched = _add_abstracts(
        papers, category, site_client=site_client, api_client=api_client
    )
    store.save(category, papers)
    # Let the web app show the new days while affiliations are being read, even if the run
    # is stopped before its end.
    store.write_index()

    read = _add_html_front_matter(
        papers,
        site_client,
        reading=html or HtmlReading(),
        checkpoint=lambda current: store.save(category, current),
    )
    return _name_and_report(
        category,
        read.papers,
        read,
        Ror(ror_client, max_ror_lookups),
        store=store,
        new=new,
        abstracts=abstracts_fetched,
    )


def backfill_category(
    category: str,
    days: Iterable[date],
    *,
    store: PaperStore,
    site_client: HttpClient,
    ror_client: HttpClient | None = None,
    max_ror_lookups: int | None = DEFAULT_MAX_ROR_LOOKUPS,
    html: HtmlReading | None = None,
) -> UpdateReport:
    """Collect past announcement days of ``category`` from the catchup pages.

    Catchup pages include abstracts, so each day is saved (and the index rewritten) as
    soon as it is fetched, before the slow part: reading affiliations from the HTML
    renderings, most recent day first. Days already stored with their abstracts are not
    fetched again. A day whose catchup page fails, or lists fewer entries than it
    announces, is not saved: the others are read, and the report names it (REL-4), for the
    next run to fetch it again. After ``MAX_CONSECUTIVE_DAY_FAILURES`` such days in a row,
    the remaining days are not asked for, and named too; past the reading's deadline, they
    are left for the next run, as its pages are (``Stop.DEADLINE``).
    As in :func:`update_category`, enrichment already in the store is reused and progress
    is saved regularly.

    Args:
        category: arXiv category, e.g. ``"cs.CV"``.
        days: Days to collect. Days without announcement (weekends, holidays) are empty.
        store: Destination store.
        site_client: Client for arxiv.org (catchup and HTML pages).
        ror_client: Client for the Research Organization Registry, to name the
            institutions of the affiliations (``None``: skip).
        max_ror_lookups: Maximum number of affiliation strings to look up in ROR.
        html: How HTML pages are read (limit, saves, deadline, cache).

    Returns:
        A summary of the run.
    """
    reading = html or HtmlReading()
    known = {paper.arxiv_id: paper for paper in store.iter_papers()}
    papers: list[Paper] = []
    failed: list[date] = []
    left: list[date] = []  # past the deadline: not asked for, and not failed
    failing = 0  # catchup pages that could not be read in a row
    for day in sorted(set(days), reverse=True):
        stored = store.load_day(category, day)
        if stored and all(paper.abstract is not None for paper in stored):
            # Past announcements never change: a day saved with its abstracts is reused, so
            # that resuming an interrupted backfill goes straight back to the HTML pages.
            listed = stored
        elif _past(reading.deadline):
            left.append(day)
            continue
        elif failing >= MAX_CONSECUTIVE_DAY_FAILURES:
            # Not asked for: left for the next run, like the days that failed.
            failed.append(day)
            continue
        else:
            catchup = _catchup_day(site_client, category, day)
            if catchup is None:
                failed.append(day)
                failing += 1
                if failing == MAX_CONSECUTIVE_DAY_FAILURES:
                    logger.error(
                        "%s: %d catchup pages in a row could not be read; the other days are "
                        "not asked for this run",
                        category,
                        failing,
                    )
                continue
            failing = 0
            listed = [_carry_over(paper, known.get(paper.arxiv_id)) for paper in catchup.papers]
            store.save(category, listed)
        logger.info("%s %s: %s papers", category, day.isoformat(), f"{len(listed):,}")
        papers.extend(listed)
    if left:
        logger.warning("Out of time: %d days left for the next run", len(left))
    # Let the web app show the new days while affiliations are being read.
    store.write_index()

    new = sum(paper.arxiv_id not in known for paper in papers)
    abstracts_fetched = sum(
        paper.abstract is not None and (paper.arxiv_id not in known or known[paper.arxiv_id].abstract is None)
        for paper in papers
    )
    logger.info("%s: %d papers listed, %d new", category, len(papers), new)

    read = _add_html_front_matter(
        papers,
        site_client,
        reading=reading,
        checkpoint=lambda current: store.save(category, current),
    )
    report = _name_and_report(
        category,
        read.papers,
        read,
        Ror(ror_client, max_ror_lookups),
        store=store,
        new=new,
        abstracts=abstracts_fetched,
    )
    # Days left at the deadline wait for the next run, as its pages do: out of time, not red.
    stopped = report.stopped or (Stop.DEADLINE if left else None)
    return replace(report, failed_days=tuple(failed), stopped=stopped)


def _catchup_day(client: HttpClient, category: str, day: date) -> Listing | None:
    """The catchup page of ``day``, or ``None`` when it failed or came back incomplete.

    An incomplete day is not kept: saved with its abstracts, it would be reused as it is by
    every later backfill.
    """
    try:
        catchup = fetch_catchup(client, category, day)
    except (FetchError, ParseError) as exc:
        problem = f"could not be read ({exc})"
    else:
        if catchup.is_complete:
            return catchup
        problem = f"lists {len(catchup.papers):,} of {catchup.total:,} entries"
    logger.error(
        "%s %s: the catchup page %s; the day is left for the next run", category, day.isoformat(), problem
    )
    return None


def reextract_category(
    category: str,
    select: Callable[[Paper], bool],
    *,
    store: PaperStore,
    site_client: HttpClient,
    ror_client: HttpClient | None = None,
    max_ror_lookups: int | None = DEFAULT_MAX_ROR_LOOKUPS,
    html: HtmlReading | None = None,
) -> UpdateReport:
    """Read again the HTML pages of the stored papers that ``select`` picks.

    For extraction fixes to reach stored papers: pages the cache holds are read from it,
    the others downloaded within ``html.limit``, the most recent papers first. A paper whose
    page cannot be read again (a failure, the end of the budget, a layout breaker) keeps
    what it had; one whose affiliations come back the same keeps its institutions. A page
    kept before the cache kept the tables of author blocks that gives no affiliation to a
    paper that has some leaves it as it was, and leaves the cache: it is downloaded next
    time (2609.06629).

    Args:
        category: arXiv category, e.g. ``"cs.CV"``.
        select: Which stored papers (with an HTML rendering) to read again.
        store: The data store.
        site_client: Client for arxiv.org (HTML pages).
        ror_client: Client for the Research Organization Registry, to name the
            institutions of changed affiliations (``None``: skip).
        max_ror_lookups: Maximum number of affiliation strings to look up in ROR.
        html: How HTML pages are read (limit, saves, deadline, cache).

    Returns:
        A summary of the run: ``listed`` is the number of papers selected.
    """
    stored = [paper for paper in store.iter_papers(category) if paper.html_url and select(paper)]
    logger.info("%s: %s papers to extract again", category, f"{len(stored):,}")
    unread = [paper.without_affiliations() for paper in stored]
    reading = html or HtmlReading()
    read = _add_html_front_matter(
        unread,
        site_client,
        reading=reading,
        checkpoint=lambda current: store.save(category, _kept(current, stored, reading.cache)),
    )
    emptied = [
        old.html_url
        for new, old in zip(read.papers, stored, strict=True)
        if old.html_url and _emptied(new, old, reading.cache)
    ]
    papers = _kept(read.papers, stored, reading.cache)
    if emptied and reading.cache is not None:
        logger.warning(
            "%d cached pages gave no affiliation to papers that have some: kept as they were, "
            "their pages read again next time",
            len(emptied),
        )
        for url in emptied:
            reading.cache.discard(url)
    return _name_and_report(
        category, papers, read, Ror(ror_client, max_ror_lookups), store=store, new=0, abstracts=0
    )


@dataclass(frozen=True, slots=True)
class Ror:
    """How a run names the institutions of the affiliations it read: ``client`` ``None`` skips it."""

    client: HttpClient | None
    #: At most this many affiliation strings looked up, ``None`` for no limit.
    max_lookups: int | None


def _name_and_report(
    category: str,
    papers: list[Paper],
    read: "_HtmlRead",
    ror: Ror,
    *,
    store: PaperStore,
    new: int,
    abstracts: int,
) -> UpdateReport:
    """The end of every run (update, backfill, reextract): name the institutions, save, report.

    Args:
        category: arXiv category.
        papers: The papers of the run, with what their pages gave.
        read: How the reading of their pages went.
        ror: How their institutions are named.
        store: The data store.
        new: Papers new to the store.
        abstracts: Abstracts fetched before the pages, which add theirs.

    Returns:
        The run's report.
    """
    if ror.client is not None:
        papers = add_institutions(papers, ror.client, limit=ror.max_lookups)
    store.save(category, papers)
    return UpdateReport(
        category=category,
        listed=len(papers),
        new=new,
        abstracts_fetched=abstracts + read.abstracts,
        affiliations_fetched=read.pages,
        pending=sum(_still_pending(paper) for paper in papers),
        no_page=sum(_without_page(paper) for paper in papers),
        empty=read.empty,
        unreadable=read.unreadable,
        stopped=read.stopped,
    )


def _kept(read: Sequence[Paper], stored: Sequence[Paper], cache: PageCache | None = None) -> list[Paper]:
    """Re-extracted papers, or their stored version where nothing was read, or :func:`_emptied`.

    Affiliations that come back the same keep their institutions: no lookup is needed.
    """
    kept: list[Paper] = []
    for new, old in zip(read, stored, strict=True):
        if new.affiliations is None or _emptied(new, old, cache):
            kept.append(old)
        elif new.affiliations == old.affiliations:
            kept.append(
                replace(
                    new,
                    institutions=old.institutions,
                    institution_ids=old.institution_ids,
                    institutions_provenance=old.institutions_provenance,
                )
            )
        else:
            kept.append(new)
    return kept


def _emptied(new: Paper, old: Paper, cache: PageCache | None) -> bool:
    """Whether a stale cached page (:meth:`PageCache.stale`) gave no affiliation to a paper that has some."""
    return (
        new.affiliations == ()
        and bool(old.affiliations)
        and cache is not None
        and old.html_url is not None
        and cache.stale(old.html_url)
    )


def _carry_over(listed: Paper, stored: Paper | None) -> Paper:
    """Keep fresh listing metadata while reusing enrichment from the store.

    Listings and catchup pages never give affiliations: those always come from the store,
    unless a new version changed the author list. ``author_affiliations`` is positional,
    so the stored one would then credit authors with someone else's affiliations: the
    HTML rendering of the new version is read again, or, without one, the paper keeps its
    affiliations but no longer says who is where.
    """
    if stored is None:
        return listed
    abstract = listed.abstract if listed.abstract is not None else stored.abstract
    if _same_authors(listed.authors, stored.authors):
        return replace(
            listed,
            abstract=abstract,
            affiliations=stored.affiliations,
            author_affiliations=stored.author_affiliations,
            institutions=stored.institutions,
            institution_ids=stored.institution_ids,
            extractor=stored.extractor,
            affiliations_provenance=stored.affiliations_provenance,
            institutions_provenance=stored.institutions_provenance,
        )
    if listed.html_url is None:
        return replace(
            listed,
            abstract=abstract,
            affiliations=stored.affiliations,
            institutions=stored.institutions,
            institution_ids=stored.institution_ids,
            extractor=stored.extractor,
            affiliations_provenance=stored.affiliations_provenance,
            institutions_provenance=stored.institutions_provenance,
        )
    if stored.affiliations is not None:
        logger.info("%s changed its author list: reading its HTML again", listed.arxiv_id)
    return replace(listed, abstract=abstract)


def _same_authors(listed: Sequence[str], stored: Sequence[str]) -> bool:
    """Whether two author lists name the same people in the same order, however spelled."""
    return len(listed) == len(stored) and all(
        name_key(new) == name_key(old) for new, old in zip(listed, stored, strict=True)
    )


def _add_abstracts(
    papers: Sequence[Paper], category: str, *, site_client: HttpClient, api_client: HttpClient
) -> tuple[list[Paper], int]:
    """Fill missing abstracts: RSS feed, then catchup pages, then the API for the rest.

    The RSS feed covers the latest announcement in one request, and a catchup page any
    other day in one request (e.g. after a missed run). The API, which throttles
    aggressively, is only a last resort.
    """
    current = list(papers)
    missing = {paper.arxiv_id for paper in current if paper.abstract is None}
    if not missing:
        return current, 0

    try:
        current = _with_abstracts(current, fetch_rss_abstracts(site_client, category))
    except (FetchError, ParseError) as exc:
        logger.warning("Could not read the RSS feed of %s: %s", category, exc)

    for day in sorted({paper.announced for paper in current if paper.abstract is None}, reverse=True):
        try:
            catchup = fetch_catchup(site_client, category, day)
        except (FetchError, ParseError) as exc:
            logger.warning("Could not read the %s catchup page of %s: %s", category, day.isoformat(), exc)
            continue
        current = _with_abstracts(
            current, {paper.arxiv_id: paper.abstract for paper in catchup.papers if paper.abstract}
        )

    still_missing = [paper.arxiv_id for paper in current if paper.abstract is None]
    metadata = fetch_metadata(api_client, still_missing) if still_missing else {}
    if len(metadata) < len(still_missing):
        logger.warning(
            "%d abstracts could not be fetched; will retry next run.", len(still_missing) - len(metadata)
        )

    enriched: list[Paper] = []
    for paper in current:
        meta = metadata.get(paper.arxiv_id)
        if meta is None:
            enriched.append(paper)
            continue
        # Submitter-declared affiliations are cleaner than those scraped from HTML. The
        # institutions and the author mapping index the old list: they go with it.
        declared = bool(meta.affiliations) and meta.affiliations != paper.affiliations
        enriched.append(
            replace(
                paper.with_affiliations(meta.affiliations, None, provenance=Provenance("api", today())),
                abstract=meta.abstract,
            )
            if declared
            else replace(paper, abstract=meta.abstract)
        )
    return enriched, len(missing) - sum(paper.abstract is None for paper in enriched)


def _with_abstracts(papers: list[Paper], abstracts: Mapping[str, str]) -> list[Paper]:
    """Fill the missing abstracts found in ``abstracts`` (keyed by arXiv identifier)."""
    return [
        replace(paper, abstract=abstracts[paper.arxiv_id])
        if paper.abstract is None and paper.arxiv_id in abstracts
        else paper
        for paper in papers
    ]


def _html_todo(papers: Sequence[Paper], reading: HtmlReading) -> tuple[list[tuple[int, str]], int]:
    """The papers whose HTML page is to be read, as ``(position, url)``, and how many to download.

    The pages the cache holds come first, all of them; then at most ``reading.limit`` pages
    to download, which end the list.
    """
    todo = [
        (index, url)
        for index, paper in enumerate(papers)
        if paper.affiliations is None and (url := paper.html_url)
    ]
    cache = reading.cache
    cached = [(index, url) for index, url in todo if cache is not None and url in cache]
    to_download = [entry for entry in todo if entry not in cached]
    if reading.limit is not None:
        to_download = to_download[: reading.limit]
    if cached:
        logger.info("Reading %s HTML renderings from the page cache", f"{len(cached):,}")
    return cached + to_download, len(to_download)


def _about(seconds: float) -> str:
    """A duration as the logs give it: "a minute at most", "about 25 minutes", "about 3 h 05 min"."""
    hours, minutes = divmod(math.ceil(seconds / 60), 60)
    if hours:
        return f"about {hours} h {minutes:02d} min"
    return f"about {minutes} minutes" if minutes > 1 else "a minute at most"


def _front_matter(client: HttpClient, paper: Paper, url: str, cache: PageCache | None) -> FrontMatter | None:
    """The front matter of the paper's HTML page, or ``None`` if it could not be fetched."""
    try:
        return fetch_front_matter(client, url, authors=paper.authors, cache=cache)
    except FetchError as exc:
        logger.warning("Skipping HTML of %s, will retry next run: %s", paper.arxiv_id, exc)
        return None


def _with_front_matter(paper: Paper, front: FrontMatter) -> Paper:
    """The paper with what its HTML page gave: affiliations, and its abstract if it had none."""
    return replace(
        paper.with_affiliations(
            front.affiliations,
            front.author_affiliations,
            provenance=Provenance("html", today()),
            extractor=EXTRACTOR_VERSION,
        ),
        abstract=paper.abstract if paper.abstract is not None else front.abstract,
    )


def _past(deadline: float | None) -> bool:
    return deadline is not None and time.monotonic() >= deadline


def _layout_changed(pages: int, empty: int) -> bool:
    """Whether so many of the pages read gave no affiliation that the layout must have changed."""
    return pages >= DRIFT_MIN_PAGES and empty >= DRIFT_EMPTY_SHARE * pages


@dataclass(frozen=True, slots=True)
class _HtmlRead:
    """What :func:`_add_html_front_matter` read."""

    papers: list[Paper]
    pages: int
    abstracts: int
    empty: int
    unreadable: int
    stopped: Stop | None


def _add_html_front_matter(
    papers: Sequence[Paper],
    client: HttpClient,
    *,
    reading: HtmlReading,
    checkpoint: Callable[[list[Paper]], object],
) -> _HtmlRead:
    """Fill affiliations (and abstracts still missing) from the papers' HTML renderings.

    Reading stops early at the deadline, after ``MAX_CONSECUTIVE_HTML_FAILURES`` failed
    pages in a row, or when nearly every page gives no affiliation: the papers of this run
    then stay pending rather than be stored as having none, which is final, and their pages
    leave the cache, to be downloaded again. An interrupted run (Ctrl-C, or a CI job
    cancelled or timed out) saves what it read.

    Returns:
        The updated papers, the pages read, the abstracts added, the pages without
        affiliations, and why reading stopped early, if it did.
    """
    todo, downloads = _html_todo(papers, reading)
    # A page takes at least the client's interval (arxiv.org's crawl delay): the time to expect.
    interval = client.min_interval
    if downloads:
        logger.info(
            "Reading %s HTML renderings at one every %s s: %s (this is slow on purpose)",
            f"{downloads:,}",
            f"{interval:g}",
            _about(downloads * interval),
        )
    current = list(papers)
    pages = abstracts = failures = unreadable = 0
    empty: list[int] = []
    stopped: Stop | None = None
    try:
        for done, (index, url) in enumerate(todo, start=1):
            if _past(reading.deadline):
                logger.warning("Out of time: %d HTML renderings left for the next run", len(todo) - done + 1)
                stopped = Stop.DEADLINE
                break
            paper = current[index]
            front = _front_matter(client, paper, url, reading.cache)
            if front is None:
                failures += 1
                unreadable += 1
                if failures < MAX_CONSECUTIVE_HTML_FAILURES:
                    continue
                logger.error("arxiv.org failed %d HTML renderings in a row: stopping", failures)
                stopped = Stop.FAILURES
                break
            failures = 0
            current[index] = _with_front_matter(paper, front)
            abstracts += paper.abstract is None and current[index].abstract is not None
            pages += 1
            logger.debug("[%d/%d] %s: %s", done, len(todo), paper.arxiv_id, front.affiliations)
            if not front.affiliations:
                empty.append(index)
                if _layout_changed(pages, len(empty)):
                    logger.error(
                        "%d of %d HTML renderings gave no affiliation: has arXiv's layout changed? "
                        "Their papers wait for the next run",
                        len(empty),
                        pages,
                    )
                    _set_back(current, papers, empty, reading.cache)
                    stopped = Stop.LAYOUT
                    break
            if done % reading.save_every == 0:
                checkpoint(current)
                # The cached pages come first: those left are downloads, but at most all of them.
                left = min(downloads, len(todo) - done)
                logger.info(
                    "%s/%s HTML renderings read, progress saved%s",
                    f"{done:,}",
                    f"{len(todo):,}",
                    f"; time left: {_about(left * interval)}" if left else "",
                )
    except KeyboardInterrupt:
        logger.warning("Interrupted: saving the %d HTML renderings read", pages)
        checkpoint(current)
        raise
    return _HtmlRead(current, pages, abstracts, len(empty), unreadable, stopped)


def _set_back(
    current: list[Paper], papers: Sequence[Paper], empty: Iterable[int], cache: PageCache | None
) -> None:
    """Set the papers of pages without affiliation back to pending, and forget their pages.

    The pages may not show a new layout but an error page served with a 200: kept in the
    cache, they would stop every run after this one too.
    """
    for position in empty:
        current[position] = papers[position]
        if cache is not None and (url := papers[position].html_url):
            cache.discard(url)


def add_institutions(papers: Sequence[Paper], client: HttpClient, *, limit: int | None) -> list[Paper]:
    """Name the institution of each affiliation: ROR first, then the rules (AFF-13).

    Only papers with affiliations and no institutions yet are looked up, each distinct
    string once. A paper gets its institutions, with the ROR id of those ROR named, when
    all its strings were looked up: :func:`institutions.name_institutions` names the rest.
    The others wait for the next run (lookup limit reached, or ROR unreachable), which
    never fails the run.

    Returns:
        The papers, with institutions where they could be named.
    """
    pending = [paper for paper in papers if _needs_institutions(paper)]
    if not pending:
        return list(papers)
    strings = [affiliation for paper in pending for affiliation in paper.affiliations or ()]
    logger.info("Looking up %s distinct affiliations in ROR", f"{len(set(strings)):,}")
    matches = match_institutions(client, strings, limit=limit)
    named = sum(match is not None for match in matches.values())
    logger.info("ROR named %s of %s affiliations", f"{named:,}", f"{len(matches):,}")
    return [
        _with_institutions(paper, [matches[affiliation] for affiliation in paper.affiliations or ()])
        if _needs_institutions(paper) and all(a in matches for a in paper.affiliations or ())
        else paper
        for paper in papers
    ]


def _needs_institutions(paper: Paper) -> bool:
    return bool(paper.affiliations) and paper.institutions is None


def _with_institutions(paper: Paper, matches: Sequence[Institution | None]) -> Paper:
    """The paper with the institutions ROR matched, the rules' for the rest, and ROR's ids."""
    names = name_institutions(
        paper.affiliations or (), [match.name if match else None for match in matches], paper.authors
    )
    return replace(
        paper,
        institutions=names,
        institution_ids=tuple(
            match.ror_id if match is not None and name is not None else None
            for match, name in zip(matches, names, strict=True)
        ),
        institutions_provenance=Provenance("ror", today()),
    )


@dataclass(frozen=True, slots=True)
class CitationsReport:
    """Outcome of :func:`update_citation_counts`.

    Attributes:
        category: Category of the papers.
        asked: Papers whose count was asked for.
        found: Papers that got one.
    """

    category: str
    asked: int
    found: int


def _every_stored_paper(store: PaperStore, category: str) -> Iterator[Paper]:
    """The papers of the day files, the archive and the most cited of the last 12 months."""
    yield from store.iter_papers(category)
    yield from store.iter_archive(category)
    yield from store.iter_top_recent(category)


def update_citation_counts(
    store: PaperStore,
    category: str,
    client: HttpClient,
    *,
    key: str | None,
    refresh: bool = False,
    max_seconds: float | None = None,
) -> CitationsReport:
    """Fetch the citation counts of the stored papers of ``category`` into ``citations.json``.

    By default only the papers without a count, announced since the last full refresh:
    one or two requests a day. With ``refresh``, every stored paper (day files, archive and
    the most cited of the last 12 months), as the weekly archive does. Semantic Scholar
    learns new arXiv papers within days: the ones it does not know yet stay without a count
    and are asked for again next time.

    Args:
        store: Data store.
        category: arXiv category.
        client: HTTP client for Semantic Scholar (see :func:`fetch_citation_counts`).
        key: Semantic Scholar API key, ``None`` for anonymous requests.
        refresh: Ask for every stored paper, and date the counts of today.
        max_seconds: Time budget for the requests (see :func:`fetch_citation_counts`).

    Returns:
        How many papers were asked for, and how many got a count. A refusing Semantic
        Scholar leaves the rest for the next run: it never fails the update.

    Raises:
        FetchError: If Semantic Scholar rejects the API key.
    """
    stored = [paper.arxiv_id for paper in _every_stored_paper(store, category)]
    known = {} if refresh else store.load_citations(category)
    wanted = [arxiv_id for arxiv_id in dict.fromkeys(stored) if arxiv_id not in known]
    fetched = fetch_citation_counts(client, wanted, key=key, max_seconds=max_seconds) if wanted else {}
    counts = {arxiv_id: count for arxiv_id, count in fetched.items() if count is not None}
    if refresh and len(fetched) == len(wanted):
        store.write_citations(category, counts, source=S2_SOURCE)
    elif counts:
        store.merge_citations(category, counts, source=S2_SOURCE)
    return CitationsReport(category=category, asked=len(wanted), found=len(counts))


def format_citations_report(report: CitationsReport) -> str:
    """Render a :class:`CitationsReport` as one line."""
    missing = report.asked - report.found
    return f"{report.category}: citation counts for {report.found:,} of {report.asked:,} papers" + (
        f", {missing:,} left for the next run" if missing else ""
    )


@dataclass(frozen=True, slots=True)
class ScholarReport:
    """Outcome of :func:`update_scholar_records`.

    Attributes:
        category: Category of the papers.
        asked: Stored papers asked for.
        found: Papers Semantic Scholar knows.
        dois: Papers with the DOI of a published version.
        venues: Papers with a published venue.
        gained: Of those, papers whose comments name no venue.
    """

    category: str
    asked: int
    found: int
    dois: int
    venues: int
    gained: int


def update_scholar_records(
    store: PaperStore,
    category: str,
    client: HttpClient,
    *,
    key: str | None,
    max_seconds: float | None = None,
) -> ScholarReport:
    """Fetch the DOI, published venue and author ids of every stored paper into ``scholar.json``.

    Every stored paper (day files, archive and the most cited of the last 12 months) is asked
    for: about 54 requests for 27,000 papers, a few minutes with a key. A paper keeps its
    previous record when Semantic Scholar was not asked (it kept refusing), and papers no
    longer stored are dropped. The author ids are kept only when Semantic Scholar lists as
    many authors as the paper, since they are matched by position.

    Args:
        store: Data store.
        category: arXiv category.
        client: HTTP client for Semantic Scholar (see :func:`fetch_scholar_records`).
        key: Semantic Scholar API key, ``None`` for anonymous requests.
        max_seconds: Time budget for the requests (see :func:`fetch_citation_counts`).

    Returns:
        How many papers were asked for, and what was found.

    Raises:
        FetchError: If Semantic Scholar rejects the API key.
    """
    stored: dict[str, Paper] = {}
    for paper in _every_stored_paper(store, category):
        stored.setdefault(paper.arxiv_id, paper)
    previous = store.load_scholar(category)
    fetched = fetch_scholar_records(client, stored, key=key, max_seconds=max_seconds)
    records: dict[str, ScholarRecord] = {}
    for arxiv_id, paper in stored.items():
        if arxiv_id not in fetched:
            if previous is not None and arxiv_id in previous.papers:
                records[arxiv_id] = previous.papers[arxiv_id]
            continue
        record = fetched[arxiv_id]
        if record is None:
            continue
        author_ids = checked_author_ids(record, paper.authors)
        records[arxiv_id] = replace(record, author_ids=author_ids, author_names=None)
    store.write_scholar(category, records, source=S2_SOURCE)
    found = [records[arxiv_id] for arxiv_id in fetched if arxiv_id in records]
    return ScholarReport(
        category=category,
        asked=len(stored),
        found=sum(record is not None for record in fetched.values()),
        dois=sum(record.doi is not None for record in found),
        venues=sum(record.venue is not None for record in found),
        gained=sum(
            records[arxiv_id].venue is not None and stored[arxiv_id].venue is None
            for arxiv_id in fetched
            if arxiv_id in records
        ),
    )


def checked_author_ids(record: ScholarRecord, authors: Sequence[str]) -> tuple[str | None, ...] | None:
    """Semantic Scholar's author ids, each kept only where its name is the paper's author's.

    Ids are given in Semantic Scholar's order, which is arXiv's but for papers it merged
    with another version or another paper: a wrong id would credit a paper to someone else,
    worse than a name shared by two people (AFF-H). None at all when the lists differ in
    length; a name is the author's when one spelling holds the other's words ("Mahdi
    Hosseini", "Mahdi S. Hosseini"), or the same surname and first initial ("M. Hosseini").

    Args:
        record: What Semantic Scholar knows of the paper, with its authors' names.
        authors: The paper's authors, as arXiv lists them.

    Returns:
        One id or ``None`` per author, or ``None``.
    """
    ids, names = record.author_ids, record.author_names
    if ids is None or len(ids) != len(authors):
        return None
    if names is None or len(names) != len(ids):
        return ids
    return tuple(
        author_id if name is not None and _same_person(author, name) else None
        for author_id, name, author in zip(ids, names, authors, strict=True)
    )


def _same_person(listed: str, named: str) -> bool:
    words, other = _name_words(listed), _name_words(named)
    if not words or not other:
        return False
    if set(words) <= set(other) or set(other) <= set(words):
        return True
    # Initials: the same surname, and given names that start alike ("D. Gopinath").
    return words[-1] == other[-1] and words[0][0] == other[0][0]


_NAME_JOINER_RE = re.compile("[-'\N{RIGHT SINGLE QUOTATION MARK}.]")
_NAME_WORD_RE = re.compile(r"[^\W_]+")


def _name_words(name: str) -> list[str]:
    """A name's words, folded, a hyphenated given name as one: "Jin-Chao" is "jinchao"."""
    # In the order of ``institutions.search_key``: marks first, so that "ǿ" is "o" too.
    decomposed = unicodedata.normalize("NFD", name)
    folded = "".join(char for char in decomposed if not unicodedata.combining(char))
    folded = folded.lower().translate(PLAIN_LETTERS)
    return _NAME_WORD_RE.findall(_NAME_JOINER_RE.sub("", folded.replace(". ", " ")))


def format_scholar_report(report: ScholarReport) -> str:
    """Render a :class:`ScholarReport` as one line."""
    return (
        f"{report.category}: Semantic Scholar knows {report.found:,} of {report.asked:,} papers: "
        f"{_count(report.dois, 'DOI')}, {_count(report.venues, 'published venue')} "
        f"({report.gained:,} where the comments name none)"
    )


def _count(number: int, noun: str) -> str:
    return f"{number:,} {noun}{'' if number == 1 else 's'}"


_STOPS = {
    Stop.DEADLINE: "out of time",
    Stop.FAILURES: "arxiv.org kept failing",
    Stop.LAYOUT: "nearly every page gave no affiliation",
}


def _without_page(paper: Paper) -> bool:
    """Whether no run can read the paper's affiliations: none yet, and no HTML rendering."""
    return paper.affiliations is None and paper.html_url is None


def _still_pending(paper: Paper) -> bool:
    """Whether a later run can still enrich the paper: an abstract, or a page to read."""
    return paper.abstract is None or (paper.affiliations is None and paper.html_url is not None)


def format_report(report: UpdateReport) -> str:
    """Render an :class:`UpdateReport` as a one-line human-readable summary."""
    return (
        f"{report.category}: {report.listed:,} listed, {report.new:,} new, "
        f"{report.abstracts_fetched:,} abstracts and {report.affiliations_fetched:,} affiliations fetched"
        + (f" ({report.empty:,} pages without any)" if report.empty else "")
        + (f", {report.unreadable:,} pages unreadable" if report.unreadable else "")
        + (f", {report.no_page:,} without an HTML page" if report.no_page else "")
        + f", {report.pending:,} still pending"
        + (f"; HTML reading stopped: {_STOPS[report.stopped]}" if report.stopped else "")
        + (
            f"; days not read: {', '.join(day.isoformat() for day in report.failed_days)}"
            if report.failed_days
            else ""
        )
    )
