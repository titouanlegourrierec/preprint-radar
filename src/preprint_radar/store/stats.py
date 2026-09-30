"""Coverage report over the paper store: what is enriched, what is still pending.

Used to keep an eye on the extraction heuristics: a drop in the share of papers with
affiliations after a change to ``sources/arxiv_html.py`` shows up here first. The archive gets
the same table, one row per year, and the citation counts a closing line.
"""

from collections.abc import Container, Iterable, Sequence
from dataclasses import dataclass
from typing import Self

from rich import box
from rich.table import Table

from preprint_radar.models import Paper
from preprint_radar.store.paper_store import CitationCounts, PaperStore

_COLUMNS = ("papers", "abstracts", "affiliated", "none", "pending", "mapped", "named", "venues", "cited")


@dataclass(frozen=True, slots=True)
class Coverage:
    """How many papers of a set carry each piece of enrichment.

    Affiliations fall into three exclusive buckets: ``affiliations_found`` papers have at
    least one, ``affiliations_empty`` were searched without success, and
    ``affiliations_pending`` were not retrieved yet. Among papers with affiliations,
    ``mapped`` say which author has which, ``institutions_found`` name at least one
    institution, and ``institutions_pending`` were not looked up yet.
    """

    papers: int = 0
    abstracts: int = 0
    affiliations_found: int = 0
    affiliations_empty: int = 0
    affiliations_pending: int = 0
    mapped: int = 0
    institutions_found: int = 0
    institutions_pending: int = 0
    venues: int = 0
    cited: int = 0

    @classmethod
    def of(cls, papers: Iterable[Paper], cited: Container[str] = frozenset()) -> Self:
        """Count the enrichment of ``papers``; ``cited`` holds the ids with a citation count."""
        counted = abstracts = found = empty = pending = mapped = named = unnamed = venues = with_count = 0
        for paper in papers:
            counted += 1
            abstracts += paper.abstract is not None
            venues += paper.venue is not None
            with_count += paper.arxiv_id in cited
            if paper.affiliations is None:
                pending += 1
            elif not paper.affiliations:
                empty += 1
            else:
                found += 1
                mapped += paper.author_affiliations is not None
                if paper.institutions is None:
                    unnamed += 1
                else:
                    named += any(name is not None for name in paper.institutions)
        return cls(
            papers=counted,
            abstracts=abstracts,
            affiliations_found=found,
            affiliations_empty=empty,
            affiliations_pending=pending,
            mapped=mapped,
            institutions_found=named,
            institutions_pending=unnamed,
            venues=venues,
            cited=with_count,
        )

    def __add__(self, other: "Coverage") -> "Coverage":
        return Coverage(
            papers=self.papers + other.papers,
            abstracts=self.abstracts + other.abstracts,
            affiliations_found=self.affiliations_found + other.affiliations_found,
            affiliations_empty=self.affiliations_empty + other.affiliations_empty,
            affiliations_pending=self.affiliations_pending + other.affiliations_pending,
            mapped=self.mapped + other.mapped,
            institutions_found=self.institutions_found + other.institutions_found,
            institutions_pending=self.institutions_pending + other.institutions_pending,
            venues=self.venues + other.venues,
            cited=self.cited + other.cited,
        )


@dataclass(frozen=True, slots=True)
class RowCoverage:
    """Coverage of one row of the report: the papers of a day, or of an archive year."""

    label: str
    coverage: Coverage


def collect_coverage(store: PaperStore, category: str) -> list[RowCoverage]:
    """Coverage of each stored day of ``category``, most recent first."""
    cited = store.load_citations(category)
    return [
        RowCoverage(day.isoformat(), Coverage.of(store.load_day(category, day), cited))
        for day in store.days(category)
    ]


def collect_archive_coverage(store: PaperStore, category: str) -> list[RowCoverage]:
    """Coverage of each archive year of ``category``, most recent first."""
    cited = store.load_citations(category)
    return [
        RowCoverage(str(year), Coverage.of(store.load_archive(category, year), cited))
        for year in store.archive_years(category)
    ]


def format_coverage(category: str, days: Sequence[RowCoverage]) -> str:
    """Render the coverage of the days of one category, one row per day and a total.

    Columns count papers: with an abstract, with at least one affiliation (affiliated),
    searched for affiliations without success (none), not searched yet (pending), with
    affiliations mapped to their authors (mapped), with at least one institution named
    (named), with a detected venue, and with a citation count (cited).
    """
    return _table(_days_title(category, days), "day", days)


def format_archive_coverage(category: str, years: Sequence[RowCoverage]) -> str:
    """Render the coverage of the archive of one category, one row per year and a total."""
    return _table(_years_title(category, years), "year", years)


def coverage_table(category: str, days: Sequence[RowCoverage]) -> Table:
    """:func:`format_coverage` as a rich table, for a terminal."""
    return _rich_table(_days_title(category, days), "day", days)


def archive_coverage_table(category: str, years: Sequence[RowCoverage]) -> Table:
    """:func:`format_archive_coverage` as a rich table, for a terminal."""
    return _rich_table(_years_title(category, years), "year", years)


def _days_title(category: str, days: Sequence[RowCoverage]) -> str:
    papers = sum(entry.coverage.papers for entry in days)
    return f"{category}: {_count(papers, 'paper')} over {_count(len(days), 'day')}"


def _years_title(category: str, years: Sequence[RowCoverage]) -> str:
    papers = sum(entry.coverage.papers for entry in years)
    return f"{category} archive: {_count(papers, 'paper')} over {_count(len(years), 'year')}"


def format_citations(category: str, citations: CitationCounts) -> str:
    """One line on the citation counts of a category: how many, from where, and when."""
    return (
        f"{category} citation counts: {len(citations.counts):,} from {citations.source}, "
        f"{citations.generated_at.date().isoformat()}"
    )


def _table(title: str, label: str, entries: Sequence[RowCoverage]) -> str:
    total = sum((entry.coverage for entry in entries), Coverage())
    headers = (label, *_COLUMNS)
    rows = [(entry.label, *_cells(entry.coverage)) for entry in entries]
    rows.append(("total", *_cells(total)))
    widths = [max(len(header), *(len(row[column]) for row in rows)) for column, header in enumerate(headers)]
    return "\n".join(
        (
            title,
            _row(headers, widths),
            *(_row(row, widths) for row in rows),
            *_summary(total),
        )
    )


def _rich_table(title: str, label: str, entries: Sequence[RowCoverage]) -> Table:
    total = sum((entry.coverage for entry in entries), Coverage())
    table = Table(
        title=title,
        title_justify="left",
        title_style="bold",
        caption="\n".join(_summary(total)),
        caption_justify="left",
        header_style="bold cyan",
        box=box.SIMPLE_HEAD,
    )
    table.add_column(label, style="dim")
    for column in _COLUMNS:
        table.add_column(column, justify="right")
    for entry in entries:
        table.add_row(entry.label, *_cells(entry.coverage))
    table.add_section()
    table.add_row("total", *_cells(total), style="bold")
    return table


def _cells(coverage: Coverage) -> tuple[str, ...]:
    counts = (
        coverage.papers,
        coverage.abstracts,
        coverage.affiliations_found,
        coverage.affiliations_empty,
        coverage.affiliations_pending,
        coverage.mapped,
        coverage.institutions_found,
        coverage.venues,
        coverage.cited,
    )
    return tuple(f"{count:,}" for count in counts)


def _row(cells: Sequence[str], widths: Sequence[int]) -> str:
    first = f"{cells[0]:<{widths[0]}}"
    rest = (f"{cell:>{width}}" for cell, width in zip(cells[1:], widths[1:], strict=True))
    return "  ".join((first, *rest)).rstrip()


def _summary(total: Coverage) -> tuple[str, str]:
    tried = total.affiliations_found + total.affiliations_empty
    found = total.affiliations_found
    not_looked_up = (
        f", {total.institutions_pending:,} not looked up yet" if total.institutions_pending else ""
    )
    enrichment = (
        f"abstracts {_percent(total.abstracts, total.papers)}, "
        f"affiliations {_percent(found, tried)} of {tried:,} tried, "
        f"venues {_percent(total.venues, total.papers)}, "
        f"citation counts {_percent(total.cited, total.papers)}"
    )
    affiliated = (
        f"of the papers with affiliations: authors mapped {_percent(total.mapped, found)}, "
        f"institutions named {_percent(total.institutions_found, found)}{not_looked_up}"
    )
    return enrichment, affiliated


def _percent(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "0%"


def _count(count: int, noun: str) -> str:
    """``count`` and ``noun``, plural when needed."""
    return f"{count:,} {noun}{'' if count == 1 else 's'}"
