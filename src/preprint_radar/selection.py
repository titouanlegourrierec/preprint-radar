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
from datetime import date

DEFAULT_BUDGET = 22_000
DEFAULT_MARGIN = 1.15
RECENT_DAYS = 365
DAYS_PER_YEAR = 365.25


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


def is_recent(first_seen: date, today: date) -> bool:
    """Whether a paper is within the rolling window kept in full."""
    return (today - first_seen).days < RECENT_DAYS


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
