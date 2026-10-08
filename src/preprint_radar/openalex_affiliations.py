"""Affiliations from OpenAlex, for the papers no page of ours gives them (AFF-3, AFF-27).

The weekly archive asks it for the papers it builds from the catalog, and the daily
``affiliations`` step for the papers of the day files without an HTML rendering. OpenAlex's
institutions are registry entries, with their ROR ids, so they are the papers' institutions
too. It learns those of recent papers over months: a paper it knows nothing of is asked
again every ``OPENALEX_RETRY_EVERY_DAYS`` while young.
"""

import logging
from dataclasses import replace
from datetime import date

from preprint_radar.config import OPENALEX_RETRY_AGE_DAYS, OPENALEX_RETRY_EVERY_DAYS
from preprint_radar.http import HttpClient
from preprint_radar.institutions import ids_where_named, name_institutions
from preprint_radar.models import Paper, Provenance
from preprint_radar.sources.openalex import fetch_affiliations

logger = logging.getLogger(__name__)


def with_openalex_affiliations(papers: list[Paper], client: HttpClient, today: date) -> list[Paper]:
    """Fill the affiliations of papers that need them from OpenAlex (:func:`needs_openalex`).

    Papers whose affiliations came from OpenAlex before ROR ids were kept (their
    institutions are their affiliations, OpenAlex's registry names) are asked for again,
    once, for the ids: their affiliations are replaced by OpenAlex's current ones, unless
    it now gives none. A paper it still knows nothing of keeps what it had, with the day of
    this lookup, from which the next one is counted.
    """
    pending = {paper.arxiv_id: len(paper.authors) for paper in papers if needs_openalex(paper, today)}
    if not pending:
        return papers
    found = fetch_affiliations(client, pending)
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
            # OpenAlex's institutions are registry entries: they are their own institutions,
            # a company's subsidiaries named as the company (AFF-13).
            names = name_institutions(result.affiliations, result.affiliations, paper.authors)
            return replace(
                paper.with_affiliations(result.affiliations, result.author_affiliations, provenance=read),
                institutions=names,
                institution_ids=ids_where_named(result.institution_ids, names),
                institutions_provenance=read,
            )
        # A day file's paper whose page gave none: OpenAlex has none either, today. Its
        # `extractor` is an HTML extraction's, which this lookup now stands for no longer.
        return replace(paper, extractor=None, affiliations_provenance=read)

    return [updated(paper) for paper in papers]


def needs_openalex(paper: Paper, today: date) -> bool:
    """Whether to ask OpenAlex for a paper's affiliations (AFF-3).

    Those not looked up yet; OpenAlex's, without their ROR ids; and none, while the paper
    is young (``OPENALEX_RETRY_AGE_DAYS``), once ``OPENALEX_RETRY_EVERY_DAYS`` have passed
    since the last lookup (or when its day is unknown): OpenAlex learns the institutions of
    recent papers over months, so an early "nothing" is not final.
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
