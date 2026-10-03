"""Detect the venues of the stored papers again with today's rules, without fetching anything.

The venue is detected once, when a paper is first stored, from its comments and journal
reference (``venue.extract_venue``). After a change to the detection, ``venues`` applies
it to the stored papers, the archive's included: their comments come from arXiv's catalog
as the day files' come from the listing.
"""

from dataclasses import dataclass, replace

from preprint_radar.models import Paper
from preprint_radar.store.paper_store import PaperStore
from preprint_radar.venue import extract_venue


@dataclass(frozen=True, slots=True)
class VenuesReport:
    """What :func:`detect_venues_again` changed in one category.

    Attributes:
        category: The arXiv category.
        papers: Papers looked at, day files and archive.
        before: Papers with a venue before.
        after: Papers with a venue after.
        changed: Papers whose venue changed (found, lost or another one).
        days: Day files written again.
        archive: Whether the archive was written again.
    """

    category: str
    papers: int
    before: int
    after: int
    changed: int
    days: int
    archive: bool


def detect_venues_again(store: PaperStore, category: str) -> VenuesReport:
    """Detect the venue of every stored paper of a category again.

    Only the day files holding a changed paper are written, and the archive only when one
    of its papers changed.

    Args:
        store: The data store.
        category: The arXiv category.

    Returns:
        What was looked at and changed.
    """
    papers = before = after = changed = days = 0
    for day in store.days(category):
        stored = store.load_day(category, day)
        detected = [_with_venue(paper) for paper in stored]
        updated = [new for old, new in zip(stored, detected, strict=True) if new != old]
        papers += len(stored)
        before += sum(paper.venue is not None for paper in stored)
        after += sum(paper.venue is not None for paper in detected)
        if updated:
            store.save(category, updated)
            changed += len(updated)
            days += 1
    archived = list(store.iter_archive(category))
    detected = [_with_venue(paper) for paper in archived]
    archive_changed = sum(new != old for old, new in zip(archived, detected, strict=True))
    if archive_changed:
        store.write_archive(category, detected)
    return VenuesReport(
        category=category,
        papers=papers + len(archived),
        before=before + sum(paper.venue is not None for paper in archived),
        after=after + sum(paper.venue is not None for paper in detected),
        changed=changed + archive_changed,
        days=days,
        archive=archive_changed > 0,
    )


def _with_venue(paper: Paper) -> Paper:
    venue = extract_venue(paper.comments, paper.journal_ref)
    return paper if venue == paper.venue else replace(paper, venue=venue)
