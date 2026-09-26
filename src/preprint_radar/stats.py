"""Coverage report over the paper store: what is enriched, what is still pending.

Used to keep an eye on the extraction heuristics: a drop in the share of papers with
affiliations after a change to ``paper_page.py`` shows up here first.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Self

from preprint_radar.models import Paper
from preprint_radar.store import PaperStore

_HEADERS = ("day", "papers", "abstracts", "affiliated", "none", "pending", "venues")


@dataclass(frozen=True, slots=True)
class Coverage:
    """How many papers of a set carry each piece of enrichment.

    Affiliations fall into three exclusive buckets: ``affiliations_found`` papers have at
    least one, ``affiliations_empty`` were searched without success, and
    ``affiliations_pending`` were not retrieved yet.
    """

    papers: int = 0
    abstracts: int = 0
    affiliations_found: int = 0
    affiliations_empty: int = 0
    affiliations_pending: int = 0
    venues: int = 0

    @classmethod
    def of(cls, papers: Iterable[Paper]) -> Self:
        """Count the enrichment of ``papers``."""
        counted = abstracts = found = empty = pending = venues = 0
        for paper in papers:
            counted += 1
            abstracts += paper.abstract is not None
            venues += paper.venue is not None
            if paper.affiliations is None:
                pending += 1
            elif paper.affiliations:
                found += 1
            else:
                empty += 1
        return cls(
            papers=counted,
            abstracts=abstracts,
            affiliations_found=found,
            affiliations_empty=empty,
            affiliations_pending=pending,
            venues=venues,
        )

    def __add__(self, other: "Coverage") -> "Coverage":
        return Coverage(
            papers=self.papers + other.papers,
            abstracts=self.abstracts + other.abstracts,
            affiliations_found=self.affiliations_found + other.affiliations_found,
            affiliations_empty=self.affiliations_empty + other.affiliations_empty,
            affiliations_pending=self.affiliations_pending + other.affiliations_pending,
            venues=self.venues + other.venues,
        )


@dataclass(frozen=True, slots=True)
class DayCoverage:
    """Coverage of the papers announced on one day."""

    day: date
    coverage: Coverage


def collect_coverage(store: PaperStore, category: str) -> list[DayCoverage]:
    """Coverage of each stored day of ``category``, most recent first."""
    return [DayCoverage(day, Coverage.of(store.load_day(category, day))) for day in store.days(category)]


def format_coverage(category: str, days: Sequence[DayCoverage]) -> str:
    """Render the coverage of one category as a table with one row per day and a total.

    Columns count papers: with an abstract, with at least one affiliation (affiliated),
    searched for affiliations without success (none), not searched yet (pending), and
    with a detected venue.
    """
    total = sum((entry.coverage for entry in days), Coverage())
    rows = [(entry.day.isoformat(), *_cells(entry.coverage)) for entry in days]
    rows.append(("total", *_cells(total)))
    widths = [max(len(header), *(len(row[column]) for row in rows)) for column, header in enumerate(_HEADERS)]
    lines = [
        f"{category}: {total.papers:,} paper{_s(total.papers)} over {len(days)} day{_s(len(days))}",
        _row(_HEADERS, widths),
        *(_row(row, widths) for row in rows),
        _summary(total),
    ]
    return "\n".join(lines)


def _cells(coverage: Coverage) -> tuple[str, ...]:
    counts = (
        coverage.papers,
        coverage.abstracts,
        coverage.affiliations_found,
        coverage.affiliations_empty,
        coverage.affiliations_pending,
        coverage.venues,
    )
    return tuple(f"{count:,}" for count in counts)


def _row(cells: Sequence[str], widths: Sequence[int]) -> str:
    first = f"{cells[0]:<{widths[0]}}"
    rest = (f"{cell:>{width}}" for cell, width in zip(cells[1:], widths[1:], strict=True))
    return "  ".join((first, *rest)).rstrip()


def _summary(total: Coverage) -> str:
    tried = total.affiliations_found + total.affiliations_empty
    return (
        f"abstracts {_percent(total.abstracts, total.papers)}, "
        f"affiliations {_percent(total.affiliations_found, tried)} of {tried:,} tried, "
        f"venues {_percent(total.venues, total.papers)}"
    )


def _percent(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "0%"


def _s(count: int) -> str:
    """Plural mark."""
    return "" if count == 1 else "s"
