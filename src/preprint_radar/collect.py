"""Update pipelines: listing -> store, enriching new papers along the way.

- :func:`update_category` follows the recent listing (the last few announcement days);
- :func:`backfill_category` collects past days from the catchup pages;
- :func:`update_citation_counts` gives the stored papers their citation counts.
"""

import logging
import math
import time
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum

from preprint_radar.code import CodeLink, code_link
from preprint_radar.config import (
    CATCH_UP_DAYS,
    CATCH_UP_WEEKDAYS,
    DEFAULT_MAX_ROR_LOOKUPS,
    DEFAULT_SAVE_EVERY,
)
from preprint_radar.console import progress
from preprint_radar.exceptions import FetchError, ParseError, SchemaVersionError, StoreError
from preprint_radar.http import HttpClient
from preprint_radar.institutions import name_institutions
from preprint_radar.models import CodeRecord, Institution, Listing, Paper, Provenance, ScholarRecord
from preprint_radar.names import same_person
from preprint_radar.openalex_affiliations import (
    needs_openalex,
    with_openalex_affiliations,
    with_published_affiliations,
)
from preprint_radar.sources.arxiv_api import fetch_metadata
from preprint_radar.sources.arxiv_html import (
    EXTRACTOR_VERSION,
    FrontMatter,
    PageCache,
    fetch_front_matter,
    first_version_url,
    name_key,
    parse_front_matter,
)
from preprint_radar.sources.arxiv_listing import fetch_catchup, fetch_listing
from preprint_radar.sources.arxiv_rss import fetch_rss_abstracts
from preprint_radar.sources.github import fetch_stars
from preprint_radar.sources.huggingface import fetch_likes
from preprint_radar.sources.openalex import fetch_countries
from preprint_radar.sources.ror import match_institutions
from preprint_radar.sources.semantic_scholar import S2_SOURCE, fetch_citation_counts, fetch_scholar_records
from preprint_radar.steps import StepCount, enrich
from preprint_radar.store.paper_store import PaperStore
from preprint_radar.store.stats import weekdays_since

logger = logging.getLogger(__name__)


def today() -> date:
    """The day of a run, in UTC: the provenance of what it reads, and the day it expects."""
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
        caught_up: The day the recent listing lacked, and the papers of it taken from its
            catchup page (:func:`_missing_day`): arXiv served a listing out of date.
        steps: What each enrichment step of the run did (:func:`steps.enrich`).
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
    caught_up: tuple[date, int] | None = None
    steps: tuple[StepCount, ...] = ()

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
    day = today()
    caught_up = _missing_day(site_client, category, listing, day)
    known = {paper.arxiv_id: paper for paper in store.iter_papers()}
    papers = [_carry_over(paper, known.get(paper.arxiv_id)) for paper in (*caught_up, *listing.papers)]
    new = sum(paper.arxiv_id not in known for paper in papers)
    logger.info("%s: %d papers listed, %d new", category, len(papers), new)

    def saved_and_shown(current: list[Paper]) -> None:
        store.save(category, current)
        # Let the web app show the new days while affiliations are being read, even if the
        # run is stopped before its end.
        store.write_index()

    papers, counts = enrich(
        papers, [Abstracts(category, site_client, api_client)], checkpoint=saved_and_shown
    )
    pages = Pages(
        site_client, html or HtmlReading(), checkpoint=lambda current: store.save(category, current)
    )
    papers, read = enrich(papers, [pages])
    report = _name_and_report(
        category,
        papers,
        pages.read,
        Ror(ror_client, max_ror_lookups),
        store=store,
        new=new,
        abstracts=counts[0].done,
        counts=(*counts, *read),
    )
    return replace(report, caught_up=(day, len(caught_up))) if caught_up else report


def _missing_day(client: HttpClient, category: str, listing: Listing, day: date) -> tuple[Paper, ...]:
    """The papers announced on ``day`` from its catchup page, when the listing has none of them.

    arXiv's cache served the listing page hours old on 2026-10-15: the runs of 06:17 and
    06:43 UTC got one without that day, announced late, which its catchup page held whole.
    Asked for on a weekday the listing lacks only; a day without announcement (a holiday)
    gives an empty page. Papers listed on an earlier day too stay there.
    """
    if day.weekday() >= _SATURDAY or any(paper.announced >= day for paper in listing.papers):
        return ()
    try:
        catchup = fetch_catchup(client, category, day)
    except (FetchError, ParseError) as exc:
        logger.warning(
            "%s: the listing lacks %s, whose catchup page could not be read (%s)",
            category,
            day.isoformat(),
            exc,
        )
        return ()
    listed = {paper.arxiv_id for paper in listing.papers}
    papers = tuple(paper for paper in catchup.papers if paper.arxiv_id not in listed)
    if papers:
        logger.warning(
            "%s: the listing lacks %s: its %s papers come from its catchup page",
            category,
            day.isoformat(),
            f"{len(papers):,}",
        )
    return papers


_SATURDAY = 5


def catch_up_since(store: PaperStore, category: str, day: date) -> date | None:
    """The first day ``update`` should read from catchup pages, ``None`` when the listing suffices.

    The recent listing holds the last five announcement days (CI-7). After an outage longer
    than that, the days between the newest stored one and the listing's are in no listing:
    every day since the newest stored one is read, as a backfill does. And papers still
    pending on a day the listing no longer holds (pages past a run's budget, after such an
    outage) are read from their stored day. Never further back than ``CATCH_UP_DAYS``, nor
    for an empty store.

    Args:
        store: Data store.
        category: arXiv category.
        day: The day of the run.

    Returns:
        The day to catch up from, or ``None``.
    """
    days = store.days(category)
    if not days:
        return None
    oldest = day - timedelta(days=CATCH_UP_DAYS)
    candidates: list[date] = []
    if weekdays_since(days[0], day) > CATCH_UP_WEEKDAYS:
        candidates.append(days[0] + timedelta(days=1))
    candidates.extend(
        stored
        for stored in days
        if oldest <= stored
        and weekdays_since(stored, day) > CATCH_UP_WEEKDAYS
        and any(_still_pending(paper) for paper in store.load_day(category, stored))
    )
    return max(min(candidates), oldest) if candidates else None


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

    pages = Pages(site_client, reading, checkpoint=lambda current: store.save(category, current))
    papers, read = enrich(papers, [pages])
    report = _name_and_report(
        category,
        papers,
        pages.read,
        Ror(ror_client, max_ror_lookups),
        store=store,
        new=new,
        abstracts=abstracts_fetched,
        counts=read,
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
    pages = Pages(
        site_client,
        reading,
        checkpoint=lambda current: store.save(category, _kept(current, stored, reading.cache)),
    )
    read_papers, read = enrich(unread, [pages])
    emptied = [
        old.html_url
        for new, old in zip(read_papers, stored, strict=True)
        if old.html_url and _emptied(new, old, reading.cache)
    ]
    papers = _kept(read_papers, stored, reading.cache)
    if emptied and reading.cache is not None:
        logger.warning(
            "%d cached pages gave no affiliation to papers that have some: kept as they were, "
            "their pages read again next time",
            len(emptied),
        )
        for url in emptied:
            reading.cache.discard(url)
    return _name_and_report(
        category,
        papers,
        pages.read,
        Ror(ror_client, max_ror_lookups),
        store=store,
        new=0,
        abstracts=0,
        counts=read,
    )


@dataclass(frozen=True, slots=True)
class Ror:
    """How a run names the institutions of the affiliations it read: ``client`` ``None`` skips it."""

    client: HttpClient | None
    #: At most this many affiliation strings looked up, ``None`` for no limit.
    max_lookups: int | None


# The enrichment steps of the day files' papers (:mod:`preprint_radar.steps`), each over the
# function that does it: a paper needs what it lacks and a run can still give it.


@dataclass(frozen=True, slots=True)
class Abstracts:
    """The abstracts the listing lacks: RSS, then catchup pages, then the API (:func:`_add_abstracts`)."""

    category: str
    site_client: HttpClient
    api_client: HttpClient
    name = "Abstracts"

    def needs(self, paper: Paper) -> bool:
        """Whether the paper has no abstract yet."""
        return paper.abstract is None

    def run(self, papers: list[Paper]) -> list[Paper]:
        """The papers, with the abstracts the services gave."""
        return _add_abstracts(
            papers, self.category, site_client=self.site_client, api_client=self.api_client
        )[0]


@dataclass(slots=True)
class Pages:
    """The affiliations of the HTML pages, within the reading's budget (:func:`_add_html_front_matter`).

    Attributes:
        client: Client for arxiv.org.
        reading: How the pages are read: limit, saves, deadline, cache.
        checkpoint: Saves the papers every ``reading.save_every`` pages, and on Ctrl-C.
        read: How the last run of the step went: pages read, empty, unreadable, why it stopped.
    """

    client: HttpClient
    reading: HtmlReading
    checkpoint: Callable[[list[Paper]], object]
    read: "_HtmlRead" = field(default_factory=lambda: _HtmlRead([], 0, 0, 0, 0, None))
    name = "HTML pages"

    def needs(self, paper: Paper) -> bool:
        """Whether the paper has a page and no affiliations from it yet."""
        return paper.affiliations is None and paper.html_url is not None

    def run(self, papers: list[Paper]) -> list[Paper]:
        """The papers, with what their pages gave, until the budget, deadline or a stop."""
        self.read = _add_html_front_matter(
            papers, self.client, reading=self.reading, checkpoint=self.checkpoint
        )
        return self.read.papers


@dataclass(frozen=True, slots=True)
class Institutions:
    """The institutions of the affiliations: ROR, then the rules (:func:`add_institutions`)."""

    client: HttpClient
    limit: int | None
    #: ROR's answers of earlier runs, not asked again (:func:`ror_answers`).
    known: Mapping[str, Institution | None]
    name = "ROR institutions"

    def needs(self, paper: Paper) -> bool:
        """Whether the paper has affiliations whose institutions are not named yet."""
        return _needs_institutions(paper)

    def run(self, papers: list[Paper]) -> list[Paper]:
        """The papers, with the institutions of those whose strings were all looked up."""
        return add_institutions(papers, self.client, limit=self.limit, known=self.known)


@dataclass(frozen=True, slots=True)
class OpenAlexAffiliations:
    """OpenAlex's affiliations for the papers no page gave any (:func:`update_openalex_affiliations`)."""

    client: HttpClient
    today: date
    name = "OpenAlex affiliations"

    def needs(self, paper: Paper) -> bool:
        """Whether no page gave the paper affiliations, and OpenAlex is due to be asked (AFF-27, AFF-31)."""
        return (
            paper.affiliations == () or (paper.html_url is None and paper.affiliations is None)
        ) and needs_openalex(paper, self.today)

    def run(self, papers: list[Paper]) -> list[Paper]:
        """The papers, with what OpenAlex knows of those that need it."""
        wanted = [index for index, paper in enumerate(papers) if self.needs(paper)]
        looked_up = with_openalex_affiliations(
            [papers[index] for index in wanted], self.client, self.today, pages_kept=True
        )
        current = list(papers)
        for index, paper in zip(wanted, looked_up, strict=True):
            current[index] = paper
        return current


def _name_and_report(
    category: str,
    papers: list[Paper],
    read: "_HtmlRead",
    ror: Ror,
    *,
    store: PaperStore,
    new: int,
    abstracts: int,
    counts: tuple[StepCount, ...] = (),
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
        counts: What the run's steps before this one did.

    Returns:
        The run's report.
    """
    named: tuple[StepCount, ...] = ()
    if ror.client is not None:
        institutions = Institutions(ror.client, ror.max_lookups, ror_answers(store.iter_papers(category)))
        papers, named = enrich(papers, [institutions])
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
        steps=(*counts, *named),
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
    # A bar in a terminal, closed however the reading ends.
    bar = ExitStack()
    advance = bar.enter_context(progress("HTML pages", len(todo)))
    try:
        for done, (index, url) in enumerate(todo, start=1):
            if _past(reading.deadline):
                logger.warning("Out of time: %d HTML renderings left for the next run", len(todo) - done + 1)
                stopped = Stop.DEADLINE
                break
            paper = current[index]
            front = _front_matter(client, paper, url, reading.cache)
            advance(1)
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
    finally:
        bar.close()
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


def add_institutions(
    papers: Sequence[Paper],
    client: HttpClient,
    *,
    limit: int | None,
    known: Mapping[str, Institution | None] | None = None,
) -> list[Paper]:
    """Name the institution of each affiliation: ROR first, then the rules (AFF-13).

    Only papers with affiliations and no institutions yet are looked up, each distinct
    string once, but those ROR answered for in an earlier run (``known``, :func:`ror_answers`,
    AFF-17). A paper gets its institutions, with the ROR id of those ROR named, when all its
    strings were looked up: :func:`institutions.name_institutions` names the rest. The
    others wait for the next run (lookup limit reached, or ROR unreachable), which never
    fails the run.

    Args:
        papers: The papers to name.
        client: HTTP client for the ROR API.
        limit: Most strings to ask ROR for (``None``: no limit).
        known: ROR's answers of earlier runs, by string (:func:`ror_answers`), not asked again.

    Returns:
        The papers, with institutions where they could be named.
    """
    pending = [paper for paper in papers if _needs_institutions(paper)]
    if not pending:
        return list(papers)
    known = known or {}
    strings = dict.fromkeys(affiliation for paper in pending for affiliation in paper.affiliations or ())
    asked = [affiliation for affiliation in strings if affiliation not in known]
    matches = {affiliation: known[affiliation] for affiliation in strings if affiliation in known}
    reused = f" ({len(matches):,} more known from earlier runs)" if matches else ""
    logger.info("Looking up %s distinct affiliations in ROR%s", f"{len(asked):,}", reused)
    if asked:
        with progress("ROR institutions", len(asked) if limit is None else min(len(asked), limit)) as advance:
            looked_up = match_institutions(client, asked, limit=limit, progress=advance)
        named = sum(match is not None for match in looked_up.values())
        logger.info("ROR named %s of %s affiliations", f"{named:,}", f"{len(looked_up):,}")
        matches |= looked_up
    return [
        _with_institutions(paper, [matches[affiliation] for affiliation in paper.affiliations or ()])
        if _needs_institutions(paper) and all(a in matches for a in paper.affiliations or ())
        else paper
        for paper in papers
    ]


def ror_answers(papers: Iterable[Paper]) -> dict[str, Institution | None]:
    """What ROR answered for the affiliation strings of papers it named, to ask it no more (AFF-17).

    An institution with an id is ROR's match; one without, or none, what the rules gave
    when ROR matched nothing or a match named no institution: either way, the same string
    gets the same names again (all but 4 of 4,237 papers on 2026-10-15, which ROR answered
    differently on other days: the latest answer wins). Only papers named with their ids,
    by ROR: before ids were kept, its names and the rules' look alike, and OpenAlex's are
    not its answers.
    """
    answers: dict[str, tuple[date, Institution | None]] = {}
    for paper in papers:
        provenance = paper.institutions_provenance
        if provenance is None or provenance.source != "ror" or paper.institution_ids is None:
            continue
        day = provenance.at or date.min
        for affiliation, name, ror_id in zip(
            paper.affiliations or (), paper.institutions or (), paper.institution_ids, strict=True
        ):
            if affiliation not in answers or answers[affiliation][0] <= day:
                answers[affiliation] = (day, Institution(name, ror_id) if name and ror_id else None)
    return {affiliation: answer for affiliation, (_, answer) in answers.items()}


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
    with progress("Citation counts", len(wanted)) as advance:
        fetched = (
            fetch_citation_counts(client, wanted, key=key, max_seconds=max_seconds, progress=advance)
            if wanted
            else {}
        )
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
    with progress("Published versions", len(stored)) as advance:
        fetched = fetch_scholar_records(client, stored, key=key, max_seconds=max_seconds, progress=advance)
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
        author_id if name is not None and same_person(author, name) else None
        for author_id, name, author in zip(ids, names, authors, strict=True)
    )


def format_scholar_report(report: ScholarReport) -> str:
    """Render a :class:`ScholarReport` as one line."""
    return (
        f"{report.category}: Semantic Scholar knows {report.found:,} of {report.asked:,} papers: "
        f"{_count(report.dois, 'DOI')}, {_count(report.venues, 'published venue')} "
        f"({report.gained:,} where the comments name none)"
    )


@dataclass(frozen=True, slots=True)
class OpenAlexReport:
    """Outcome of :func:`update_openalex_affiliations`.

    Attributes:
        category: Category of the papers.
        asked: Papers asked for: without an HTML page, or whose page gave none.
        found: Of those, papers with affiliations now.
    """

    category: str
    asked: int
    found: int


def update_openalex_affiliations(
    store: PaperStore, category: str, client: HttpClient, *, today: date
) -> OpenAlexReport:
    """Ask OpenAlex for the affiliations of the stored papers no page gave them (AFF-27, AFF-31).

    Those without an HTML page (about 5% of the papers: arXiv could not convert their
    LaTeX), and those whose page gave none, read by an extraction: about one in five, from
    a month after the page was read. OpenAlex knows those of about two papers in five a
    month after their announcement, more once they are published: one it knows nothing of
    keeps an empty list, with the day of the lookup, and is asked again every 30 days while
    under two years old (:func:`needs_openalex`); a page's keeps its extraction version, so
    that the next one reads it again. A failing OpenAlex leaves the papers for the next run.

    Args:
        store: Data store.
        category: arXiv category.
        client: HTTP client for OpenAlex.
        today: Day of the lookup.

    Returns:
        How many papers were asked for, and how many have affiliations now.
    """
    step = OpenAlexAffiliations(client, today)
    wanted = [paper for paper in store.iter_papers(category) if step.needs(paper)]
    looked_up, _ = enrich(wanted, [step])
    store.save(category, [new for old, new in zip(wanted, looked_up, strict=True) if new is not old])
    return OpenAlexReport(
        category=category, asked=len(wanted), found=sum(bool(paper.affiliations) for paper in looked_up)
    )


def format_openalex_report(report: OpenAlexReport) -> str:
    """Render an :class:`OpenAlexReport` as one line."""
    return (
        f"{report.category}: OpenAlex gave affiliations for {report.found:,} of "
        f"{_count(report.asked, 'paper')} without any from a page"
    )


@dataclass(frozen=True, slots=True)
class ArchiveAffiliationsReport:
    """Outcome of :func:`update_archive_affiliations`.

    Attributes:
        category: Category of the papers.
        without: Highly cited papers without affiliations before the run.
        from_published: Of those, papers placed by OpenAlex's record of their published version.
        pages: HTML pages read, from the cache or downloaded (a page that does not exist included).
        from_pages: Papers that got affiliations from their page.
        unreadable: Pages that could not be fetched, read next time.
        stopped: Why the reading of pages stopped early, if it did.
    """

    category: str
    without: int
    from_published: int
    pages: int = 0
    from_pages: int = 0
    unreadable: int = 0
    stopped: Stop | None = None

    @property
    def failed(self) -> bool:
        """Whether the reading of pages stopped on a failure (arXiv down, layout changed)."""
        return self.stopped in {Stop.FAILURES, Stop.LAYOUT}


def update_archive_affiliations(
    store: PaperStore,
    category: str,
    *,
    openalex_client: HttpClient,
    today: date,
    site_client: HttpClient | None = None,
    html: HtmlReading | None = None,
    ror: Ror | None = None,
) -> ArchiveAffiliationsReport:
    """Affiliations for the highly cited papers without any (AFF-20, AFF-28).

    The papers of the archive and the most cited of the last 12 months, but those of the
    day files, whose records there are their day records, which the daily update enriches.
    First OpenAlex's record of their published version (:func:`with_published_affiliations`,
    seconds). Then, with a ``site_client``, the HTML rendering of the first version of
    those still without that arXiv renders (:func:`first_version_url`), the most cited
    first: the pages the cache holds, offline, then downloads within ``html.limit``, at
    arxiv.org's crawl delay, a page that does not exist remembered in the cache. A paper
    whose page gives affiliations takes them, with the page's link; the others keep what
    they had. Progress is saved every ``html.save_every`` pages and on Ctrl-C; the reading
    stops early as the update's does (:class:`Stop`). Last, the institutions of the
    affiliations read are named through ROR, with those an interrupted run left unnamed.

    Args:
        store: Data store.
        category: arXiv category.
        openalex_client: HTTP client for OpenAlex.
        today: Day of the lookups.
        site_client: Client for arxiv.org (HTML pages); ``None`` reads none.
        html: How the pages are read (limit, saves, deadline, cache).
        ror: How the institutions are named (``None``: not named).

    Returns:
        A summary of the run.
    """
    archive = list(store.iter_archive(category))
    top = store.load_top_recent(category)
    in_days = {paper.arxiv_id for paper in store.iter_papers(category)}
    own = [*archive, *(paper for paper in (top.papers if top else ()) if paper.arxiv_id not in in_days)]
    changed: dict[str, Paper] = {}

    def save(updated: Mapping[str, Paper]) -> None:
        store.write_archive(category, [updated.get(paper.arxiv_id, paper) for paper in archive])
        if top is not None:
            papers = [updated.get(paper.arxiv_id, paper) for paper in top.papers]
            store.write_top_recent(category, papers, since=top.since)

    without = [paper for paper in own if not paper.affiliations]
    scholar = store.load_scholar(category)
    dois = {
        arxiv_id: record.doi for arxiv_id, record in (scholar.papers if scholar else {}).items() if record.doi
    }
    looked_up = with_published_affiliations(without, openalex_client, today, dois)
    changed |= {new.arxiv_id: new for old, new in zip(without, looked_up, strict=True) if new is not old}
    from_published = len(changed)
    if changed:  # saved before the pages, which can take a night
        save(changed)

    reading = html or HtmlReading(limit=0)
    read: _HtmlRead | None = None
    from_pages: dict[str, Paper] = {}
    if site_client is not None and reading.limit != 0:
        todo = _archive_pages(looked_up, reading.cache, store.load_citations(category))
        unread = [replace(paper.without_affiliations(), html_url=url) for paper, url in todo]
        pages = Pages(
            site_client, reading, checkpoint=lambda current: save(changed | _with_affiliations(current))
        )
        read_papers, _ = enrich(unread, [pages])
        read = pages.read
        from_pages = _with_affiliations(read_papers)
        if from_pages:
            changed |= from_pages
            save(changed)

    if ror is not None and ror.client is not None:
        unnamed = [paper for paper in (changed.get(p.arxiv_id, p) for p in own) if _needs_institutions(paper)]
        institutions = Institutions(ror.client, ror.max_lookups, ror_answers(store.iter_papers(category)))
        named, _ = enrich(unnamed, [institutions])
        renamed = {new.arxiv_id: new for old, new in zip(unnamed, named, strict=True) if new is not old}
        if renamed:
            save(changed | renamed)
    return ArchiveAffiliationsReport(
        category=category,
        without=len(without),
        from_published=from_published,
        pages=read.pages if read else 0,
        from_pages=len(from_pages),
        unreadable=read.unreadable if read else 0,
        stopped=read.stopped if read else None,
    )


def _archive_pages(
    papers: Iterable[Paper], cache: PageCache | None, citations: Mapping[str, int]
) -> list[tuple[Paper, str]]:
    """The papers without affiliations whose page to read, with its URL, the most cited first.

    Those arXiv renders, but for the pages it answered do not exist and those a run before
    read that give no affiliation today: their papers keep what they had, so each run would
    read them again, first since cached, and their share of empty pages would stop it as a
    layout change.
    """
    todo = [
        (paper, url)
        for paper in papers
        if not paper.affiliations
        and (url := first_version_url(paper.arxiv_id)) is not None
        and not (cache is not None and cache.missing(url))
    ]
    if cache is not None:
        read = [(paper, url) for paper, url in todo if _gives_nothing(cache, url, paper.authors)]
        if read:
            logger.info("%s cached HTML renderings gave no affiliation: not read again", f"{len(read):,}")
            todo = [entry for entry in todo if entry not in read]
    return sorted(todo, key=lambda entry: (-citations.get(entry[0].arxiv_id, 0), entry[0].arxiv_id))


def _gives_nothing(cache: PageCache, url: str, authors: Sequence[str]) -> bool:
    """Whether the cache holds the page at ``url`` and today's extraction finds no affiliation in it.

    A stale page (:meth:`PageCache.stale`) may have lost the affiliations of its tables: it
    is read again, and gives what it gives.
    """
    html = cache.get(url)
    return (
        html is not None
        and not cache.stale(url)
        and not parse_front_matter(html, authors=authors).affiliations
    )


def _with_affiliations(papers: Iterable[Paper]) -> dict[str, Paper]:
    """The papers their pages gave affiliations, by arXiv id."""
    return {paper.arxiv_id: paper for paper in papers if paper.affiliations}


def format_archive_affiliations_report(report: ArchiveAffiliationsReport) -> str:
    """Render an :class:`ArchiveAffiliationsReport` as one line."""
    line = (
        f"{report.category}: {report.from_published + report.from_pages:,} of "
        f"{_count(report.without, 'highly cited paper')} without affiliations got some, "
        f"{report.from_published:,} from OpenAlex's published versions"
    )
    if report.pages or report.unreadable or report.stopped:
        line += f", {report.from_pages:,} from {_count(report.pages, 'HTML page')}"
    if report.unreadable:
        line += f" ({report.unreadable:,} unreadable)"
    if report.stopped:
        line += f"; stopped: {_STOPS[report.stopped]}"
    return line


CODE_SOURCE = "GitHub, Hugging Face"
"""The services of ``code.json``."""


@dataclass(frozen=True, slots=True)
class CodeReport:
    """Outcome of :func:`update_code_records`.

    Attributes:
        category: Category of the papers.
        linked: Stored papers whose abstract or comments link their code.
        asked: Of those, papers whose code was asked for: every one GitHub or the Hub can
            count, or only those without a record with ``new_only``.
        stars: Papers of ``code.json`` with their repository's GitHub stars.
        shared: Of those, papers whose stars are not theirs alone.
        likes: Papers of ``code.json`` with their Hugging Face page's likes.
        gone: Papers asked for whose repository or page no longer exists, or never did.
        kept: Papers whose lookup failed, keeping last week's record.
    """

    category: str
    linked: int
    asked: int
    stars: int
    shared: int
    likes: int
    gone: int
    kept: int


def update_code_records(
    store: PaperStore,
    category: str,
    *,
    github: HttpClient,
    token: str,
    hub: HttpClient,
    new_only: bool = False,
    now: datetime | None = None,
) -> CodeReport:
    """The stars of the code every stored paper links, into ``code.json`` (PROD-18).

    The link is the one its card shows (:func:`code.code_link`): a repository on GitHub,
    whose stars GitHub's GraphQL API gives, 100 a request; else a page of the Hugging Face
    Hub, whose likes its API gives, one a request; GitLab's (6 papers) are not asked for.
    A repository that several stored papers link, or a folder of one, is marked shared:
    its stars are not the paper's alone (``google-research/google-research``, 19 papers).
    A lookup that failed keeps last week's record; a repository GitHub no longer knows
    loses its own. The stars gained since the last refresh are the store's to count
    (:meth:`PaperStore.write_code`).

    With ``new_only``, the daily run, only the papers without a record of their link are
    asked for: those announced since the weekly refresh, and those whose repository GitHub
    did not know yet (code announced before it is public), a query or two. The others keep
    their record, and the file its date and gains, which the weekly refresh counts the
    week's gains from (:meth:`PaperStore.add_code`); only whether their stars are shared is
    worked out again, since a new paper may link the same repository. Without a
    ``code.json`` yet, every paper is asked for.

    Args:
        store: Data store.
        category: arXiv category.
        github: HTTP client for GitHub.
        token: A GitHub token (any: public data only).
        hub: HTTP client for the Hugging Face Hub.
        new_only: Ask only for the papers without a record of their link.
        now: Date of the refresh (default: now).

    Returns:
        How many papers link their code, and what each service said of it.

    Raises:
        FetchError: If GitHub rejects the token.
    """
    papers: dict[str, Paper] = {}
    for paper in _every_stored_paper(store, category):
        papers.setdefault(paper.arxiv_id, paper)
    links = {
        arxiv_id: link
        for arxiv_id, paper in papers.items()
        if (link := code_link(paper.abstract, paper.comments)) is not None
    }
    repositories = Counter(link.key for link in links.values() if link.host == "github" and link.key)
    previous = _previous_code(store, category)
    adding = new_only and bool(previous)
    asked = {
        arxiv_id: link
        for arxiv_id, link in links.items()
        # GitLab, or a Hub page that is no model, dataset or demo, has nothing to count.
        if link.key is not None and not (adding and _recorded(previous.get(arxiv_id), link))
    }
    wanted = list(dict.fromkeys(link.key for link in asked.values() if link.host == "github" and link.key))
    with progress("GitHub stars", len(wanted)) as advance:
        stars = fetch_stars(github, wanted, token=token, progress=advance)
    pages = {link.key for link in asked.values() if link.host == "huggingface" and link.key}
    with progress("Hugging Face likes", len(pages)) as advance:
        likes = fetch_likes(hub, pages, progress=advance)
    records: dict[str, CodeRecord] = {}
    gone = kept = 0
    for arxiv_id, link in links.items():
        if link.key is None:
            continue
        if arxiv_id not in asked:  # recorded, for the daily run
            before = previous[arxiv_id]
            shared = before.stars is not None and (repositories[link.key] > 1 or link.folder)
            records[arxiv_id] = replace(before, shared=shared)
            continue
        on_github = link.host == "github"
        counts = stars.stars if on_github else likes.likes
        missing = stars.missing if on_github else likes.missing
        if link.key in counts:
            records[arxiv_id] = _code_record(link, counts[link.key], shared=repositories[link.key] > 1)
        elif link.key in missing:
            gone += 1
        elif (before := previous.get(arxiv_id)) is not None and before.url == link.url:
            records[arxiv_id] = before
            kept += 1
    if adding:
        store.add_code(category, records)
    else:
        store.write_code(category, records, source=CODE_SOURCE, now=now)
    return CodeReport(
        category=category,
        linked=len(links),
        asked=len(asked),
        stars=sum(record.stars is not None for record in records.values()),
        shared=sum(record.shared for record in records.values()),
        likes=sum(record.likes is not None for record in records.values()),
        gone=gone,
        kept=kept,
    )


def _recorded(record: CodeRecord | None, link: CodeLink) -> bool:
    """Whether a paper's record is that of its link: none when its abstract changed it."""
    return record is not None and record.url == link.url


def _code_record(link: CodeLink, count: int, *, shared: bool) -> CodeRecord:
    """The record of a paper's code: GitHub's stars, or the Hub's likes."""
    if link.host == "github":
        return CodeRecord(link.url, stars=count, shared=shared or link.folder)
    return CodeRecord(link.url, likes=count)


def _previous_code(store: PaperStore, category: str) -> dict[str, CodeRecord]:
    """Last week's records, to keep where a lookup fails; none when they do not load."""
    try:
        code = store.load_code(category)
    except SchemaVersionError:
        raise
    except StoreError as exc:
        logger.warning("Last week's code.json does not load, none of it kept: %s", exc)
        return {}
    return code.papers if code else {}


def format_code_report(report: CodeReport) -> str:
    """Render a :class:`CodeReport` as one line."""
    return (
        f"{report.category}: {_count(report.linked, 'paper')} link their code, "
        f"{report.asked:,} asked: {report.stars:,} with GitHub stars ({report.shared:,} shared), "
        f"{report.likes:,} with Hugging Face likes; {report.gone:,} gone, "
        f"{report.kept:,} kept from last week"
    )


COUNTRIES_SOURCE = "OpenAlex"
"""The service of ``countries.json``."""


@dataclass(frozen=True, slots=True)
class CountriesReport:
    """Outcome of :func:`update_countries`.

    Attributes:
        category: Category of the papers.
        institutions: Distinct ROR ids of the stored papers' institutions.
        asked: Of those, the ones asked for: those without a country yet, or all.
        placed: Institutions of ``countries.json`` placed in a country.
        nowhere: Institutions the source places in no country.
        failed: Institutions whose lookup failed, asked for again next time.
        papers: Stored papers.
        papers_placed: Of those, papers with an institution placed in a country.
    """

    category: str
    institutions: int
    asked: int
    placed: int
    nowhere: int
    failed: int
    papers: int
    papers_placed: int


def update_countries(
    store: PaperStore,
    category: str,
    client: HttpClient,
    *,
    refresh: bool = False,
    now: datetime | None = None,
) -> CountriesReport:
    """The country of every stored paper's institutions, into ``countries.json`` (UX-40).

    The site's map of where the papers come from places each paper in the countries of its
    institutions, by their ROR ids, which OpenAlex places, 50 a request: those of the day
    files, the archive and the most cited of the last 12 months. Only the institutions the
    file lacks are asked for, unless ``refresh``; one OpenAlex places nowhere is kept so,
    and not asked again; one whose lookup failed is left out, to be asked next time. The
    institutions of no stored paper leave the file.

    Args:
        store: Data store.
        category: arXiv category.
        client: HTTP client for OpenAlex.
        refresh: Ask for every institution again.
        now: Date of the refresh (default: now).

    Returns:
        How many institutions were asked for, and placed.
    """
    papers: dict[str, Paper] = {}
    for paper in _every_stored_paper(store, category):
        papers.setdefault(paper.arxiv_id, paper)
    ids = sorted({ror for paper in papers.values() for ror in paper.institution_ids or () if ror})
    previous = _previous_countries(store, category)
    asked = ids if refresh else [ror for ror in ids if ror not in previous]
    with progress("Countries of institutions", len(asked)) as advance:
        fetched = fetch_countries(client, asked, progress=advance)
    countries = {
        ror: fetched[ror] if ror in fetched else previous[ror]
        for ror in ids
        if ror in fetched or ror in previous
    }
    store.write_countries(category, countries, source=COUNTRIES_SOURCE, now=now)
    placed = {ror for ror, country in countries.items() if country is not None}
    return CountriesReport(
        category=category,
        institutions=len(ids),
        asked=len(asked),
        placed=len(placed),
        nowhere=len(countries) - len(placed),
        failed=len(ids) - len(countries),
        papers=len(papers),
        papers_placed=sum(
            any(ror in placed for ror in paper.institution_ids or ()) for paper in papers.values()
        ),
    )


def _previous_countries(store: PaperStore, category: str) -> dict[str, str | None]:
    """The countries known already; none when the file does not load, asked for again."""
    try:
        countries = store.load_countries(category)
    except SchemaVersionError:
        raise
    except StoreError as exc:
        logger.warning("The former countries.json does not load, every institution asked for: %s", exc)
        return {}
    return countries.institutions if countries else {}


def format_countries_report(report: CountriesReport) -> str:
    """Render a :class:`CountriesReport` as one line."""
    share = round(100 * report.papers_placed / report.papers) if report.papers else 0
    return (
        f"{report.category}: {_count(report.institutions, 'institution')}, {report.asked:,} asked: "
        f"{report.placed:,} placed in a country, {report.nowhere:,} nowhere, {report.failed:,} failed; "
        f"a country for {report.papers_placed:,} of {_count(report.papers, 'paper')} ({share}%)"
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
        + (
            f"; the listing lacked {report.caught_up[0].isoformat()}: "
            f"{report.caught_up[1]:,} papers from its catchup page"
            if report.caught_up
            else ""
        )
    )
