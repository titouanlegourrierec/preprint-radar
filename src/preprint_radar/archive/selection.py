"""Which older papers the archive keeps: a size budget, not a fixed citation threshold.

Every paper older than the rolling window (the last 12 months, kept in full) is ranked by
citations per year of age, the only score that compares a 2015 paper and a 2024 one
fairly: a raw threshold of 500 citations keeps 486 papers of 2018 but 64 of 2025. The
archive holds the ``budget`` best-ranked papers; as the category grows, the implied
threshold rises by itself. A paper already archived only leaves once it ranks beyond
``margin`` times the budget, so that papers near the limit do not come and go weekly.
"""

from collections.abc import Iterable
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import date, timedelta

from preprint_radar.config import DEFAULT_MARGIN, RECENT_DAYS, TOP_RECENT_BUDGET, TOP_RECENT_MIN_MONTHS

DAYS_PER_YEAR = 365.25
DAYS_PER_MONTH = DAYS_PER_YEAR / 12


@dataclass(frozen=True, slots=True)
class Candidate:
    """A paper that may enter the archive."""

    arxiv_id: str
    first_seen: date
    #: ``None`` when the citation source does not know the paper.
    citations: int | None


@dataclass(frozen=True, slots=True)
class Selection:
    """Outcome of a weekly selection.

    Attributes:
        keep: Every paper the archive holds after the selection.
        entered: Papers new to the archive.
        left: Papers that leave it.
        threshold: Score of the last paper within the budget (citations per year).
    """

    keep: frozenset[str]
    entered: frozenset[str]
    left: frozenset[str]
    threshold: float


def citation_rate(citations: int | None, first_seen: date, today: date) -> float:
    """Citations per year of age, counting at least one year."""
    age = (today - first_seen).days / DAYS_PER_YEAR
    return (citations or 0) / max(age, 1.0)


def monthly_rate(citations: int | None, first_seen: date, today: date, min_months: float) -> float:
    """Citations per month of age, counting at least ``min_months``."""
    age = (today - first_seen).days / DAYS_PER_MONTH
    return (citations or 0) / max(age, min_months)


def is_recent(first_seen: date, today: date) -> bool:
    """Whether a paper is within the rolling window kept in full."""
    return (today - first_seen).days < RECENT_DAYS


def recent_since(today: date) -> date:
    """The first day of first appearance within the rolling window (:func:`is_recent`)."""
    return today - timedelta(days=RECENT_DAYS - 1)


def select_top_recent(
    candidates: Iterable[Candidate],
    *,
    budget: int = TOP_RECENT_BUDGET,
    today: date,
    min_months: float = TOP_RECENT_MIN_MONTHS,
) -> frozenset[str]:
    """Choose the most cited papers of the last 12 months (PROD-11).

    The archive's score, citations per year of age counting at least a year, would rank
    them by their raw counts, and keep the oldest months only (of 623 papers at its
    threshold in September 2026, 6 were from July and none from August). Per month of age,
    each month has its best papers; the list is rewritten as a whole every week.

    Args:
        candidates: Every paper of the category, older ones included (they are skipped).
        budget: Number of papers kept.
        today: Day of the selection.
        min_months: Age the citations are counted over, at least.

    Returns:
        The ``budget`` best-ranked papers. Papers never cited are never kept.
    """
    ranked = sorted(
        (
            (monthly_rate(candidate.citations, candidate.first_seen, today, min_months), candidate.arxiv_id)
            for candidate in candidates
            if is_recent(candidate.first_seen, today) and candidate.citations
        ),
        key=lambda item: (-item[0], item[1]),
    )
    return frozenset(arxiv_id for _, arxiv_id in ranked[:budget])


def select_archive(
    candidates: Iterable[Candidate],
    current: AbstractSet[str],
    *,
    budget: int,
    today: date,
    margin: float = DEFAULT_MARGIN,
) -> Selection:
    """Choose the papers of the archive.

    Args:
        candidates: Every paper of the category, recent ones included (they are skipped).
        current: Papers in the archive before this selection.
        budget: Number of papers a new paper must rank within to enter.
        today: Day of the selection.
        margin: An archived paper stays while it ranks within ``margin * budget``.

    Returns:
        The selection. Papers never cited are never archived.
    """
    ranked = sorted(
        (
            (citation_rate(candidate.citations, candidate.first_seen, today), candidate.arxiv_id)
            for candidate in candidates
            if not is_recent(candidate.first_seen, today) and candidate.citations
        ),
        key=lambda item: (-item[0], item[1]),
    )
    stay_limit = int(budget * margin)
    keep = frozenset(
        arxiv_id
        for rank, (_, arxiv_id) in enumerate(ranked)
        if rank < budget or (arxiv_id in current and rank < stay_limit)
    )
    threshold = ranked[budget - 1][0] if 0 < budget <= len(ranked) else 0.0
    return Selection(
        keep=keep,
        entered=keep - current,
        left=frozenset(current) - keep,
        threshold=threshold,
    )
