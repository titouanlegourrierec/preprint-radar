"""Which older papers the archive keeps: a size budget, not a fixed citation threshold.

Every paper older than the rolling window (the last 12 months, kept in full) is ranked by
citations per year of age, the only score that compares a 2015 paper and a 2024 one
fairly: a raw threshold of 500 citations keeps 486 papers of 2018 but 64 of 2025. The
archive holds the ``budget`` best-ranked papers; as the category grows, the implied
threshold rises by itself. A paper already archived only leaves once it ranks beyond
``margin`` times the budget, so that papers near the limit do not come and go weekly.
And whatever the rule, the archive keeps the most cited tenth of each year at least three
years old (:func:`year_floor`, decision 22): the rule's threshold rises with the field while
a classic's citations slow down, and kept 8 papers of 2010.
"""

import math
from collections import defaultdict
from collections.abc import Iterable
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import date, timedelta

from preprint_radar.config import (
    ARCHIVE_SINCE,
    DEFAULT_MARGIN,
    RECENT_DAYS,
    TOP_RECENT_BUDGET,
    TOP_RECENT_MIN_MONTHS,
    YEAR_FLOOR_MIN_AGE,
    YEAR_FLOOR_SHARE,
)
from preprint_radar.models import Cohort

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
        floor: Of the papers kept, those only their year's floor keeps (:func:`year_floor`).
    """

    keep: frozenset[str]
    entered: frozenset[str]
    left: frozenset[str]
    threshold: float
    floor: frozenset[str] = frozenset()


def citation_rate(citations: int | None, first_seen: date, today: date) -> float:
    """Citations per year of age, counting at least one year.

    Args:
        citations: The paper's count; ``None``, unknown, counts as none.
        first_seen: Its first appearance.
        today: The day of the ranking.
    """
    age = (today - first_seen).days / DAYS_PER_YEAR
    return (citations or 0) / max(age, 1.0)


def monthly_rate(citations: int | None, first_seen: date, today: date, min_months: float) -> float:
    """Citations per month of age, counting at least ``min_months``.

    Args:
        citations: The paper's count; ``None``, unknown, counts as none.
        first_seen: Its first appearance.
        today: The day of the ranking.
        min_months: The fewest months of age it counts, so that a paper of days does not lead.
    """
    age = (today - first_seen).days / DAYS_PER_MONTH
    return (citations or 0) / max(age, min_months)


def is_recent(first_seen: date, today: date) -> bool:
    """Whether a paper is within the rolling window kept in full.

    Args:
        first_seen: The paper's first appearance.
        today: The day of the selection.
    """
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
        The selection: the papers the budget keeps, and the floor of each year. Papers never
        cited are never archived.
    """
    candidates = list(candidates)
    ranked = sorted(
        (
            (citation_rate(candidate.citations, candidate.first_seen, today), candidate.arxiv_id)
            for candidate in candidates
            if not is_recent(candidate.first_seen, today) and candidate.citations
        ),
        key=lambda item: (-item[0], item[1]),
    )
    stay_limit = int(budget * margin)
    by_rule = frozenset(
        arxiv_id
        for rank, (_, arxiv_id) in enumerate(ranked)
        if rank < budget or (arxiv_id in current and rank < stay_limit)
    )
    floor = year_floor(candidates, today) - by_rule
    keep = by_rule | floor
    threshold = ranked[budget - 1][0] if 0 < budget <= len(ranked) else 0.0
    return Selection(
        keep=keep,
        entered=keep - current,
        left=frozenset(current) - keep,
        threshold=threshold,
        floor=floor,
    )


def year_floor(
    candidates: Iterable[Candidate],
    today: date,
    *,
    share: float = YEAR_FLOOR_SHARE,
    min_age: int = YEAR_FLOOR_MIN_AGE,
) -> frozenset[str]:
    """The most cited ``share`` of each year at least ``min_age`` years old (decision 22).

    A year is the papers first seen in it, cited or not; of its most cited ``share``,
    rounded, those never cited are left out. Highly cited papers are compared with those
    of their year, as bibliometrics' "highly cited papers" are (the top 1% of their field
    and year, for Web of Science): of 2010's 291 papers, the 29 cited 97 times or more.

    Args:
        candidates: Every paper of the category.
        today: Day of the selection.
        share: The share of each year kept.
        min_age: Years younger than this many get none.
    """
    years: defaultdict[int, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        if candidate.first_seen.year <= today.year - min_age:
            years[candidate.first_seen.year].append(candidate)
    kept: set[str] = set()
    for papers in years.values():
        ranked = sorted(papers, key=lambda candidate: (-(candidate.citations or 0), candidate.arxiv_id))
        kept.update(
            candidate.arxiv_id for candidate in ranked[: round(len(papers) * share)] if candidate.citations
        )
    return frozenset(kept)


# The shares of a year the cohorts tell apart (:func:`year_cohorts`): the top 1%, 5% and 10%.
COHORT_SHARES = (0.01, 0.05, 0.10)


def year_cohorts(candidates: Iterable[Candidate], today: date) -> dict[int, Cohort]:
    """Each complete year's papers, as their citations rank them, for the site's badges.

    The year of a paper's first version is its cohort; a highly cited paper reads as "top
    1% of 2017" against it. For each year since ``ARCHIVE_SINCE`` and before ``today``'s:
    how many papers it has, and the citations of the last of its top 1%, 5% and 10%.

    Args:
        candidates: Every paper of the category.
        today: Day of the counts.
    """
    years: defaultdict[int, list[int]] = defaultdict(list)
    for candidate in candidates:
        if ARCHIVE_SINCE.year <= candidate.first_seen.year < today.year:
            years[candidate.first_seen.year].append(candidate.citations or 0)
    cohorts: dict[int, Cohort] = {}
    for year, counts in sorted(years.items()):
        counts.sort(reverse=True)
        cutoffs = (counts[max(math.ceil(len(counts) * share), 1) - 1] for share in COHORT_SHARES)
        top_1, top_5, top_10 = cutoffs
        cohorts[year] = Cohort(papers=len(counts), top_1=top_1, top_5=top_5, top_10=top_10)
    return cohorts
