"""Affiliations from OpenAlex, for the papers no page of ours gives them (AFF-3, AFF-20, AFF-27).

The weekly archive asks it for the papers it builds from the catalog, and the daily
``affiliations`` step for the papers of the day files without an HTML rendering, or whose
page gave none (AFF-31). OpenAlex's
institutions are registry entries, with their ROR ids, so they are the papers' institutions
too. It learns those of recent papers over months: a paper it knows nothing of is asked
again every ``OPENALEX_RETRY_EVERY_DAYS`` while young. It knows those of nearly every
published version, which the highly cited papers without any are asked for weekly
(:func:`with_published_affiliations`).
"""

import logging
from collections.abc import Mapping
from dataclasses import replace
from datetime import date

from preprint_radar.config import OPENALEX_RETRY_AGE_DAYS, OPENALEX_RETRY_EVERY_DAYS
from preprint_radar.console import progress
from preprint_radar.http import HttpClient
from preprint_radar.institutions import ids_where_named, name_institutions
from preprint_radar.models import Paper, Provenance
from preprint_radar.sources.openalex import (
    PaperAffiliations,
    fetch_affiliations,
    fetch_published_authors,
    published_affiliations,
)

logger = logging.getLogger(__name__)

# arXiv's DOIs of its own records, by which OpenAlex is asked for the preprints already.
_ARXIV_DOI_PREFIX = "10.48550/"


def with_openalex_affiliations(
    papers: list[Paper], client: HttpClient, today: date, *, pages_kept: bool = False
) -> list[Paper]:
    """Fill the affiliations of papers that need them from OpenAlex (:func:`needs_openalex`).

    Papers whose affiliations came from OpenAlex before ROR ids were kept (their
    institutions are their affiliations, OpenAlex's registry names) are asked for again,
    once, for the ids: their affiliations are replaced by OpenAlex's current ones, unless
    it now gives none. A paper it still knows nothing of keeps what it had, with the day of
    this lookup, from which the next one is counted.

    With ``pages_kept`` (the day files, AFF-31), a paper whose page gave nothing, which
    OpenAlex knows nothing of either, keeps that page's provenance and extraction version,
    only its day the lookup's: ``reextract`` reads it again at the next version, which an
    OpenAlex provenance would keep it from (META-9). The archive's are never read again.

    Args:
        papers: The papers; only those :func:`needs_openalex` picks are asked for.
        client: HTTP client for OpenAlex.
        today: Day of the lookup.
        pages_kept: Whether a page's paper OpenAlex knows nothing of keeps its page's provenance.
    """
    pending = {paper.arxiv_id: len(paper.authors) for paper in papers if needs_openalex(paper, today)}
    if not pending:
        return papers
    with progress("OpenAlex affiliations", len(pending)) as advance:
        found = fetch_affiliations(client, pending, progress=advance)
    read = Provenance("openalex", today)
    retried = [paper for paper in papers if paper.affiliations == () and paper.arxiv_id in found]
    logger.info(
        "OpenAlex asked again for %d papers without affiliations: %d have some now",
        len(retried),
        sum(bool(found[paper.arxiv_id].affiliations) for paper in retried),
    )

    def updated(paper: Paper) -> Paper:
        result = found.get(paper.arxiv_id)
        if result is None:  # not asked, or the lookup failed: asked again next run
            return paper
        if paper.affiliations is None or result.affiliations:
            return _with_openalex(paper, result, read)
        # A paper whose page gave none: OpenAlex has none either, today.
        if pages_kept and paper.extractor is not None:
            return replace(paper, affiliations_provenance=Provenance("html", today))
        # In the archive, its `extractor`, an HTML extraction's, stands for this lookup no longer.
        return replace(paper, extractor=None, affiliations_provenance=read)

    return [updated(paper) for paper in papers]


def with_published_affiliations(
    papers: list[Paper], client: HttpClient, today: date, dois: Mapping[str, str]
) -> list[Paper]:
    """Fill the papers without affiliations from OpenAlex's record of their published version (AFF-20).

    OpenAlex knows the institutions of few preprints of the last two years (those of 16%
    of 2025's highly cited papers), but those of nearly every published version: 46 of 49
    such papers had some there. Each arXiv author takes the institutions of the published
    author of the same name (:func:`~preprint_radar.sources.openalex.published_affiliations`).
    A paper keeps what it had when OpenAlex does not know its version, places none of its
    authors, or names other authors (a wrong DOI): it is asked for again next time.

    Args:
        papers: The papers; those with affiliations are left as they are.
        client: HTTP client for OpenAlex.
        today: Day of the lookup.
        dois: Semantic Scholar's DOI of each paper's published version (``scholar.json``);
            arXiv's own DOIs (``10.48550/arXiv.<id>``) are not published versions.

    Returns:
        The papers, those OpenAlex placed with its affiliations and institutions.
    """
    wanted = {
        paper.arxiv_id: doi.lower()
        for paper in papers
        if not paper.affiliations
        and (doi := dois.get(paper.arxiv_id))
        and not doi.lower().startswith(_ARXIV_DOI_PREFIX)
    }
    if not wanted:
        return papers
    with progress("OpenAlex, published versions", len(set(wanted.values()))) as advance:
        works = fetch_published_authors(client, wanted.values(), progress=advance)
    read = Provenance("openalex", today)
    results = {
        paper.arxiv_id: published_affiliations(paper.authors, works[doi])
        for paper in papers
        if (doi := wanted.get(paper.arxiv_id)) is not None and doi in works
    }
    logger.info(
        "OpenAlex knows %s of %s published versions: %s place the authors, %s name others",
        f"{len(results):,}",
        f"{len(wanted):,}",
        f"{sum(result is not None and bool(result.affiliations) for result in results.values()):,}",
        f"{sum(result is None for result in results.values()):,}",
    )
    return [
        _with_openalex(paper, result, read)
        if (result := results.get(paper.arxiv_id)) is not None and result.affiliations
        else paper
        for paper in papers
    ]


def _with_openalex(paper: Paper, result: PaperAffiliations, read: Provenance) -> Paper:
    """The paper with OpenAlex's affiliations, which are their own institutions.

    OpenAlex's institutions are registry entries: a company's subsidiaries are named as the
    company (AFF-13).
    """
    names = name_institutions(result.affiliations, result.affiliations, paper.authors)
    return replace(
        paper.with_affiliations(result.affiliations, result.author_affiliations, provenance=read),
        institutions=names,
        institution_ids=ids_where_named(result.institution_ids, names),
        institutions_provenance=read,
    )


def needs_openalex(paper: Paper, today: date) -> bool:
    """Whether to ask OpenAlex for a paper's affiliations (AFF-3).

    Those not looked up yet; OpenAlex's, without their ROR ids; and none, while the paper
    is young (``OPENALEX_RETRY_AGE_DAYS``), once ``OPENALEX_RETRY_EVERY_DAYS`` have passed
    since the last lookup (or when its day is unknown): OpenAlex learns the institutions of
    recent papers over months, so an early "nothing" is not final.

    Args:
        paper: A stored paper.
        today: Day of the lookup.
    """
    if paper.affiliations is None:
        return True
    if not paper.affiliations:
        last = paper.affiliations_provenance.at if paper.affiliations_provenance else None
        return (today - paper.announced).days < OPENALEX_RETRY_AGE_DAYS and (
            last is None or (today - last).days >= OPENALEX_RETRY_EVERY_DAYS
        )
    return paper.institution_ids is None and paper.institutions == tuple(
        name_institutions(paper.affiliations, paper.affiliations, paper.authors)
    )
