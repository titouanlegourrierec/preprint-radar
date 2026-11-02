"""Removals and corrections made on request, which stay (PUB-1).

The site's About page invites the authors it names to ask for a correction of their
affiliations or for a paper's removal, and promises that it stays. Both are recorded in the
category's ``corrections.json``, with the day of the request and nothing of who asked:

- a removed paper leaves every file at once, and the store leaves it out of whatever it
  writes later (the listing, the archive, the counts), so no run brings it back;
- a corrected paper's affiliations, edited by hand in its files, take the ``manual``
  provenance, which no step reads again (no HTML page, no OpenAlex, no cleaning).

``validate`` fails when a file holds a removed paper again, or a pinned paper's affiliations
are no longer the maintainer's, so that a run that undid either pushes nothing.
"""

import logging
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from preprint_radar.exceptions import StoreError
from preprint_radar.models import Paper, Provenance
from preprint_radar.store.paper_store import PaperStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PinReport:
    """Summary of a pin: the records of the paper that now hold its corrected affiliations.

    Attributes:
        arxiv_id: The paper.
        records: Its records pinned: in a day file, the archive, the last 12 months.
    """

    arxiv_id: str
    records: int


def remove_paper(store: PaperStore, category: str, arxiv_id: str, today: date) -> list[Path]:
    """Remove a paper from every file of ``category``, for good, and rewrite the index.

    Args:
        store: The data store.
        category: arXiv category.
        arxiv_id: The paper, without its version.
        today: Day of the request, recorded.

    Returns:
        The files rewritten.
    """
    corrections = store.load_corrections(category)
    store.write_corrections(
        category,
        replace(
            corrections,
            removed={**corrections.removed, arxiv_id: corrections.removed.get(arxiv_id, today)},
            pinned={key: day for key, day in corrections.pinned.items() if key != arxiv_id},
        ),
    )
    written = store.purge_removed(category)
    store.write_index()
    return written


def pin_paper(store: PaperStore, category: str, arxiv_id: str, today: date) -> PinReport:
    """Keep a paper's affiliations as the maintainer corrected them in its files.

    Each of its records takes the ``manual`` provenance, dated ``today``, without an
    extraction version: no step reads them again. Their institutions are reset, since the
    strings may have changed: ``institutions`` names those of a day file again, the weekly
    archive those of the archive and the last 12 months.

    Args:
        store: The data store.
        category: arXiv category.
        arxiv_id: The paper, without its version.
        today: Day of the request, recorded.

    Returns:
        The records pinned.

    Raises:
        StoreError: If the paper is not stored, or one of its records has no affiliations
            (``null``: write the corrected ones first, ``[]`` when it has none).
    """
    in_days = [paper for day in store.days(category) for paper in store.load_day(category, day)]
    archive = list(store.iter_archive(category))
    top_recent = store.load_top_recent(category)
    recent = top_recent.papers if top_recent else []
    found = [paper for paper in (*in_days, *archive, *recent) if paper.arxiv_id == arxiv_id]
    if not found:
        msg = f"{arxiv_id} is not stored in {category}"
        raise StoreError(msg)
    if any(paper.affiliations is None for paper in found):
        msg = f"{arxiv_id} has no affiliations to pin: write the corrected ones first ([] for none)"
        raise StoreError(msg)
    provenance = Provenance("manual", today)

    def pinned(paper: Paper) -> Paper:
        if paper.arxiv_id != arxiv_id:
            return paper
        return paper.with_affiliations(paper.affiliations, paper.author_affiliations, provenance=provenance)

    if any(paper.arxiv_id == arxiv_id for paper in in_days):
        store.save(category, [pinned(paper) for paper in in_days if paper.arxiv_id == arxiv_id])
    if any(paper.arxiv_id == arxiv_id for paper in archive):
        store.write_archive(category, [pinned(paper) for paper in archive])
    if top_recent is not None and any(paper.arxiv_id == arxiv_id for paper in recent):
        store.write_top_recent(category, [pinned(paper) for paper in recent], since=top_recent.since)
    records = len(found)
    corrections = store.load_corrections(category)
    store.write_corrections(category, replace(corrections, pinned={**corrections.pinned, arxiv_id: today}))
    logger.info("%s: %d records pinned", arxiv_id, records)
    return PinReport(arxiv_id, records)
