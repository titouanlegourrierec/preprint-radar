"""Update pipelines: listing -> store, enriching new papers along the way.

- :func:`update_category` follows the recent listing (the last few announcement days);
- :func:`backfill_category` collects past days from the catchup pages;
- :func:`update_citation_counts` gives the stored papers their citation counts.
"""

import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date

from preprint_radar.config import DEFAULT_MAX_ROR_LOOKUPS, DEFAULT_SAVE_EVERY
from preprint_radar.exceptions import FetchError, ParseError
from preprint_radar.http import HttpClient
from preprint_radar.models import Paper
from preprint_radar.sources.arxiv_api import fetch_metadata
from preprint_radar.sources.arxiv_html import fetch_front_matter
from preprint_radar.sources.arxiv_listing import fetch_catchup, fetch_listing
from preprint_radar.sources.arxiv_rss import fetch_rss_abstracts
from preprint_radar.sources.ror import match_institutions
from preprint_radar.sources.semantic_scholar import S2_SOURCE, fetch_citation_counts
from preprint_radar.store.paper_store import PaperStore

logger = logging.getLogger(__name__)


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
    """

    category: str
    listed: int
    new: int
    abstracts_fetched: int
    affiliations_fetched: int
    pending: int


def update_category(
    category: str,
    *,
    store: PaperStore,
    site_client: HttpClient,
    api_client: HttpClient,
    ror_client: HttpClient | None = None,
    max_html_fetches: int | None = None,
    max_ror_lookups: int | None = DEFAULT_MAX_ROR_LOOKUPS,
    save_every: int = DEFAULT_SAVE_EVERY,
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
        max_html_fetches: Maximum number of HTML pages to download (``None``: no limit,
            ``0``: skip affiliation extraction from HTML).
        max_ror_lookups: Maximum number of affiliation strings to look up in ROR.
        save_every: Save progress after this many HTML downloads.

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

    papers, affiliations_fetched, html_abstracts = _add_html_front_matter(
        papers,
        site_client,
        limit=max_html_fetches,
        checkpoint=lambda current: store.save(category, current),
        save_every=save_every,
    )
    abstracts_fetched += html_abstracts
    if ror_client is not None:
        papers = add_institutions(papers, ror_client, limit=max_ror_lookups)
    store.save(category, papers)

    return UpdateReport(
        category=category,
        listed=len(papers),
        new=new,
        abstracts_fetched=abstracts_fetched,
        affiliations_fetched=affiliations_fetched,
        pending=sum(not paper.is_enriched for paper in papers),
    )


def backfill_category(
    category: str,
    days: Iterable[date],
    *,
    store: PaperStore,
    site_client: HttpClient,
    ror_client: HttpClient | None = None,
    max_html_fetches: int | None = None,
    max_ror_lookups: int | None = DEFAULT_MAX_ROR_LOOKUPS,
    save_every: int = DEFAULT_SAVE_EVERY,
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
        max_html_fetches: Maximum number of HTML pages to download (``None``: no limit,
            ``0``: skip affiliation extraction from HTML).
        max_ror_lookups: Maximum number of affiliation strings to look up in ROR.
        save_every: Save progress after this many HTML downloads.

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

    papers, affiliations_fetched, html_abstracts = _add_html_front_matter(
        papers,
        site_client,
        limit=max_html_fetches,
        checkpoint=lambda current: store.save(category, current),
        save_every=save_every,
    )
    if ror_client is not None:
        papers = add_institutions(papers, ror_client, limit=max_ror_lookups)
    store.save(category, papers)

    return UpdateReport(
        category=category,
        listed=len(papers),
        new=new,
        abstracts_fetched=abstracts_fetched + html_abstracts,
        affiliations_fetched=affiliations_fetched,
        pending=sum(not paper.is_enriched for paper in papers),
    )


def _carry_over(listed: Paper, stored: Paper | None) -> Paper:
    """Keep fresh listing metadata while reusing enrichment from the store.

    Listings and catchup pages never give affiliations: those always come from the store.
    """
    if stored is None:
        return listed
    return replace(
        listed,
        abstract=listed.abstract if listed.abstract is not None else stored.abstract,
        affiliations=stored.affiliations,
        author_affiliations=stored.author_affiliations,
        institutions=stored.institutions,
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
        # Submitter-declared affiliations are cleaner than those scraped from HTML.
        affiliations = meta.affiliations or paper.affiliations
        institutions = paper.institutions if affiliations == paper.affiliations else None
        enriched.append(
            replace(paper, abstract=meta.abstract, affiliations=affiliations, institutions=institutions)
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


def _add_html_front_matter(
    papers: Sequence[Paper],
    client: HttpClient,
    *,
    limit: int | None,
    checkpoint: Callable[[list[Paper]], object],
    save_every: int,
) -> tuple[list[Paper], int, int]:
    """Fill affiliations (and abstracts still missing) from the papers' HTML renderings.

    Returns:
        The updated papers, the number of pages processed and the number of abstracts added.
    """
    todo = [
        (index, url)
        for index, paper in enumerate(papers)
        if paper.affiliations is None and (url := paper.html_url)
    ]
    if limit is not None:
        todo = todo[:limit]
    if todo:
        logger.info("Reading %d HTML renderings (this is slow on purpose)", len(todo))

    current = list(papers)
    pages = abstracts = 0
    for done, (index, url) in enumerate(todo, start=1):
        paper = current[index]
        try:
            front = fetch_front_matter(client, url, authors=paper.authors)
        except FetchError as exc:
            logger.warning("Skipping HTML of %s, will retry next run: %s", paper.arxiv_id, exc)
            continue
        abstract = paper.abstract if paper.abstract is not None else front.abstract
        abstracts += paper.abstract is None and abstract is not None
        current[index] = replace(
            paper,
            affiliations=front.affiliations,
            author_affiliations=front.author_affiliations,
            institutions=None,
            abstract=abstract,
        )
        pages += 1
        logger.debug("[%d/%d] %s: %s", done, len(todo), paper.arxiv_id, front.affiliations)
        if done % save_every == 0:
            checkpoint(current)
            logger.info("%d/%d HTML renderings read, progress saved", done, len(todo))
    return current, pages, abstracts


def add_institutions(papers: Sequence[Paper], client: HttpClient, *, limit: int | None) -> list[Paper]:
    """Name the institution of each affiliation through the Research Organization Registry.

    Only papers with affiliations and no institutions yet are looked up, each distinct
    string once. A paper gets its institutions when all its strings were looked up; the
    others wait for the next run (lookup limit reached, or ROR unreachable), which never
    fails the run.

    Returns:
        The papers, with institutions where they could be named.
    """
    pending = [paper for paper in papers if paper.affiliations and paper.institutions is None]
    if not pending:
        return list(papers)
    strings = [affiliation for paper in pending for affiliation in paper.affiliations or ()]
    logger.info("Looking up %d distinct affiliations in ROR", len(set(strings)))
    matches = match_institutions(client, strings, limit=limit)
    named = sum(name is not None for name in matches.values())
    logger.info("ROR named %d of %d affiliations", named, len(matches))
    return [
        replace(paper, institutions=tuple(matches[affiliation] for affiliation in paper.affiliations))
        if paper.affiliations and paper.institutions is None and all(a in matches for a in paper.affiliations)
        else paper
        for paper in papers
    ]


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
    store: PaperStore, category: str, client: HttpClient, *, key: str | None, refresh: bool = False
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

    Returns:
        How many papers were asked for, and how many got a count. A failing Semantic
        Scholar leaves the rest for the next run: it never fails the update.
    """
    stored = [paper.arxiv_id for paper in (*store.iter_papers(category), *store.iter_archive(category))]
    known = {} if refresh else store.load_citations(category)
    wanted = [arxiv_id for arxiv_id in dict.fromkeys(stored) if arxiv_id not in known]
    fetched = fetch_citation_counts(client, wanted, key=key) if wanted else {}
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


def format_report(report: UpdateReport) -> str:
    """Render an :class:`UpdateReport` as a one-line human-readable summary."""
    return (
        f"{report.category}: {report.listed} listed, {report.new} new, "
        f"{report.abstracts_fetched} abstracts and {report.affiliations_fetched} affiliations fetched, "
        f"{report.pending} still pending"
    )
