"""Update pipelines: listing -> store, enriching new papers along the way.

- :func:`update_category` follows the recent listing (the last few announcement days);
- :func:`backfill_category` collects past days from the catchup pages;
- :func:`update_citation_counts` gives the stored papers their citation counts.
"""

import logging
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum

from preprint_radar.config import DEFAULT_MAX_ROR_LOOKUPS, DEFAULT_SAVE_EVERY
from preprint_radar.exceptions import FetchError, ParseError
from preprint_radar.http import HttpClient
from preprint_radar.models import Institution, Paper, ScholarRecord
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

# Reading HTML pages stops after this many failures in a row: arxiv.org is down for now, and
# each failing page costs minutes of retries.
MAX_CONSECUTIVE_HTML_FAILURES = 5
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
        deadline: ``time.monotonic()`` value after which no page is started, so that the
            run ends cleanly before it is killed (``None``: no deadline).
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
        pending: Papers still missing an abstract or affiliations after the run.
        empty: Of the HTML pages read, those that gave no affiliation.
        unreadable: HTML pages that could not be fetched (tried again next run).
        stopped: Why the reading of HTML pages stopped early, if it did.
    """

    category: str
    listed: int
    new: int
    abstracts_fetched: int
    affiliations_fetched: int
    pending: int
    empty: int = 0
    unreadable: int = 0
    stopped: Stop | None = None

    @property
    def failed(self) -> bool:
        """Whether the run stopped on a failure that should make it red."""
        return self.stopped in {Stop.FAILURES, Stop.LAYOUT}


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
    papers = read.papers
    abstracts_fetched += read.abstracts
    if ror_client is not None:
        papers = add_institutions(papers, ror_client, limit=max_ror_lookups)
    store.save(category, papers)

    return UpdateReport(
        category=category,
        listed=len(papers),
        new=new,
        abstracts_fetched=abstracts_fetched,
        affiliations_fetched=read.pages,
        pending=sum(not paper.is_enriched for paper in papers),
        empty=read.empty,
        unreadable=read.unreadable,
        stopped=read.stopped,
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
    fetched again. As in :func:`update_category`, enrichment already in the store is
    reused and progress is saved regularly.

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
    known = {paper.arxiv_id: paper for paper in store.iter_papers()}
    papers: list[Paper] = []
    for day in sorted(set(days), reverse=True):
        stored = store.load_day(category, day)
        if stored and all(paper.abstract is not None for paper in stored):
            # Past announcements never change: a day saved with its abstracts is reused, so
            # that resuming an interrupted backfill goes straight back to the HTML pages.
            listed = stored
        else:
            listed = [
                _carry_over(paper, known.get(paper.arxiv_id))
                for paper in fetch_catchup(site_client, category, day).papers
            ]
            store.save(category, listed)
        logger.info("%s %s: %d papers", category, day.isoformat(), len(listed))
        papers.extend(listed)
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
        reading=html or HtmlReading(),
        checkpoint=lambda current: store.save(category, current),
    )
    papers = read.papers
    if ror_client is not None:
        papers = add_institutions(papers, ror_client, limit=max_ror_lookups)
    store.save(category, papers)

    return UpdateReport(
        category=category,
        listed=len(papers),
        new=new,
        abstracts_fetched=abstracts_fetched + read.abstracts,
        affiliations_fetched=read.pages,
        pending=sum(not paper.is_enriched for paper in papers),
        empty=read.empty,
        unreadable=read.unreadable,
        stopped=read.stopped,
    )


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
    what it had; one whose affiliations come back the same keeps its institutions.

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
    logger.info("%s: %d papers to extract again", category, len(stored))
    unread = [
        replace(
            paper,
            affiliations=None,
            author_affiliations=None,
            institutions=None,
            institution_ids=None,
            extractor=None,
        )
        for paper in stored
    ]
    read = _add_html_front_matter(
        unread,
        site_client,
        reading=html or HtmlReading(),
        checkpoint=lambda current: store.save(category, _kept(current, stored)),
    )
    papers = _kept(read.papers, stored)
    if ror_client is not None:
        papers = add_institutions(papers, ror_client, limit=max_ror_lookups)
    store.save(category, papers)
    return UpdateReport(
        category=category,
        listed=len(stored),
        new=0,
        abstracts_fetched=read.abstracts,
        affiliations_fetched=read.pages,
        pending=sum(not paper.is_enriched for paper in papers),
        empty=read.empty,
        unreadable=read.unreadable,
        stopped=read.stopped,
    )


def _kept(read: Sequence[Paper], stored: Sequence[Paper]) -> list[Paper]:
    """Re-extracted papers, or their stored version where nothing was read.

    Affiliations that come back the same keep their institutions: no lookup is needed.
    """
    kept: list[Paper] = []
    for new, old in zip(read, stored, strict=True):
        if new.affiliations is None:
            kept.append(old)
        elif new.affiliations == old.affiliations:
            kept.append(replace(new, institutions=old.institutions, institution_ids=old.institution_ids))
        else:
            kept.append(new)
    return kept


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
        )
    if listed.html_url is None:
        return replace(
            listed,
            abstract=abstract,
            affiliations=stored.affiliations,
            institutions=stored.institutions,
            institution_ids=stored.institution_ids,
            extractor=stored.extractor,
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
                paper,
                abstract=meta.abstract,
                affiliations=meta.affiliations,
                author_affiliations=None,
                institutions=None,
                institution_ids=None,
                extractor=None,
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


def _html_todo(papers: Sequence[Paper], reading: HtmlReading) -> list[tuple[int, str]]:
    """The papers whose HTML page is to be read, as ``(position, url)``.

    The pages the cache holds come first, all of them; then at most ``reading.limit`` pages
    to download.
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
        logger.info("Reading %d HTML renderings from the page cache", len(cached))
    if to_download:
        logger.info("Reading %d HTML renderings (this is slow on purpose)", len(to_download))
    return cached + to_download


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
        paper,
        affiliations=front.affiliations,
        author_affiliations=front.author_affiliations,
        institutions=None,
        institution_ids=None,
        abstract=paper.abstract if paper.abstract is not None else front.abstract,
        extractor=EXTRACTOR_VERSION,
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
    todo = _html_todo(papers, reading)
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
                logger.info("%d/%d HTML renderings read, progress saved", done, len(todo))
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
    """Name the institution of each affiliation through the Research Organization Registry.

    Only papers with affiliations and no institutions yet are looked up, each distinct
    string once, and papers whose institutions were named before ROR ids were kept, to get
    them. A paper gets its institutions and their ids when all its strings were looked
    up; the others wait for the next run (lookup limit reached, or ROR unreachable), which
    never fails the run.

    Returns:
        The papers, with institutions where they could be named.
    """
    # Papers never named first: getting the ids of older ones must not delay them.
    pending = sorted(
        (paper for paper in papers if _needs_institutions(paper)),
        key=lambda paper: paper.institutions is not None,
    )
    if not pending:
        return list(papers)
    strings = [affiliation for paper in pending for affiliation in paper.affiliations or ()]
    logger.info("Looking up %d distinct affiliations in ROR", len(set(strings)))
    matches = match_institutions(client, strings, limit=limit)
    named = sum(match is not None for match in matches.values())
    logger.info("ROR named %d of %d affiliations", named, len(matches))
    return [
        _with_institutions(paper, [matches[affiliation] for affiliation in paper.affiliations or ()])
        if _needs_institutions(paper) and all(a in matches for a in paper.affiliations or ())
        else paper
        for paper in papers
    ]


def _needs_institutions(paper: Paper) -> bool:
    """Affiliations without institutions, or with institutions named before ids were kept."""
    if not paper.affiliations:
        return False
    return paper.institutions is None or (
        paper.institution_ids is None and any(name is not None for name in paper.institutions)
    )


def _with_institutions(paper: Paper, matches: Sequence[Institution | None]) -> Paper:
    """The paper with the institutions ROR matched, and their ids.

    Institutions named before ids were kept stay as they were: each only gets the id of
    the institution ROR names again, so that a change at ROR never loses a name.
    """
    if paper.institutions is None:
        return replace(
            paper,
            institutions=tuple(match.name if match else None for match in matches),
            institution_ids=tuple(match.ror_id if match else None for match in matches),
        )
    ids = tuple(
        match.ror_id if match is not None and match.name == name else None
        for name, match in zip(paper.institutions, matches, strict=True)
    )
    return replace(paper, institution_ids=ids)


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
    one or two requests a day. With ``refresh``, every stored paper (day files and archive),
    as the weekly archive does. Semantic Scholar learns new arXiv papers within days: the
    ones it does not know yet stay without a count and are asked for again next time.

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
    stored = [paper.arxiv_id for paper in (*store.iter_papers(category), *store.iter_archive(category))]
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
    return f"{report.category}: citation counts for {report.found} of {report.asked} papers" + (
        f", {missing} left for the next run" if missing else ""
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

    Every stored paper (day files and archive) is asked for: about 52 requests for 26,000
    papers, a few minutes with a key. A paper keeps its previous record when Semantic
    Scholar was not asked (it kept refusing), and papers no longer stored are dropped. The
    author ids are kept only when Semantic Scholar lists as many authors as the paper,
    since they are matched by position.

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
    for paper in (*store.iter_papers(category), *store.iter_archive(category)):
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
        if record.author_ids is not None and len(record.author_ids) != len(paper.authors):
            record = replace(record, author_ids=None)
        records[arxiv_id] = record
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


def format_scholar_report(report: ScholarReport) -> str:
    """Render a :class:`ScholarReport` as one line."""
    return (
        f"{report.category}: Semantic Scholar knows {report.found} of {report.asked} papers: "
        f"{_count(report.dois, 'DOI')}, {_count(report.venues, 'published venue')} "
        f"({report.gained} where the comments name none)"
    )


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"


_STOPS = {
    Stop.DEADLINE: "out of time",
    Stop.FAILURES: "arxiv.org kept failing",
    Stop.LAYOUT: "nearly every page gave no affiliation",
}


def format_report(report: UpdateReport) -> str:
    """Render an :class:`UpdateReport` as a one-line human-readable summary."""
    return (
        f"{report.category}: {report.listed} listed, {report.new} new, "
        f"{report.abstracts_fetched} abstracts and {report.affiliations_fetched} affiliations fetched"
        + (f" ({report.empty} pages without any)" if report.empty else "")
        + (f", {report.unreadable} pages unreadable" if report.unreadable else "")
        + f", {report.pending} still pending"
        + (f"; HTML reading stopped: {_STOPS[report.stopped]}" if report.stopped else "")
    )
