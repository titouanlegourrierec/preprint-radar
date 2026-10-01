from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest
from rich.console import Console

from preprint_radar.models import Paper
from preprint_radar.store.paper_store import PaperStore
from preprint_radar.store.stats import (
    Coverage,
    RowCoverage,
    archive_coverage_table,
    collect_archive_coverage,
    collect_coverage,
    coverage_table,
    format_archive_coverage,
    format_citations,
    format_coverage,
    weekdays_since,
)

BASE = Paper(
    arxiv_id="2609.00000",
    announced=date(2026, 9, 25),
    title="A paper",
    authors=("Ada Lovelace",),
)

# One paper per affiliation bucket; two abstracts; one venue; the affiliated one is
# mapped to its author and its institution named.
PAPERS = (
    replace(
        BASE,
        arxiv_id="2609.00001",
        abstract="Done.",
        affiliations=("MIT",),
        author_affiliations=((0,),),
        institutions=("Massachusetts Institute of Technology",),
        venue="ECCV 2026",
    ),
    replace(BASE, arxiv_id="2609.00002", abstract="Done.", affiliations=()),
    replace(BASE, arxiv_id="2609.00003"),
)
ARCHIVED = (
    replace(
        BASE,
        arxiv_id="1512.03385",
        announced=date(2015, 12, 10),
        abstract="Residual learning.",
        affiliations=("Microsoft",),
        institutions=("Microsoft",),
    ),
    replace(
        BASE, arxiv_id="2010.11929", announced=date(2020, 10, 22), abstract="Transformers.", affiliations=()
    ),
)


@pytest.fixture
def store(tmp_path: Path) -> PaperStore:
    store = PaperStore(tmp_path / "data")
    store.save("cs.CV", PAPERS)
    store.save("cs.CV", [replace(BASE, arxiv_id="2609.00004", announced=date(2026, 9, 24))])
    return store


@pytest.fixture
def archived(store: PaperStore) -> PaperStore:
    store.write_archive("cs.CV", ARCHIVED)
    store.write_citations(
        "cs.CV", {"1512.03385": 240_000, "2010.11929": 70_000, "2609.00001": 3}, source="S2"
    )
    return store


def test_coverage_counts_each_affiliation_bucket_once() -> None:
    assert Coverage.of(PAPERS, cited={"2609.00002"}) == Coverage(
        papers=3,
        abstracts=2,
        affiliations_found=1,
        affiliations_empty=1,
        affiliations_pending=1,
        mapped=1,
        institutions_found=1,
        venues=1,
        cited=1,
    )


def test_coverage_of_institutions_counts_only_papers_with_affiliations() -> None:
    papers = (
        replace(BASE, arxiv_id="1", affiliations=("Somewhere",)),  # not looked up yet
        replace(BASE, arxiv_id="2", affiliations=("Somewhere",), institutions=(None,)),  # no match
        replace(BASE, arxiv_id="3", affiliations=()),  # nothing to look up
    )

    coverage = Coverage.of(papers)

    assert (coverage.institutions_found, coverage.institutions_pending) == (0, 1)


def test_coverage_adds_field_by_field() -> None:
    assert Coverage.of(PAPERS) + Coverage(papers=1, venues=2, institutions_pending=1, cited=1) == Coverage(
        papers=4,
        abstracts=2,
        affiliations_found=1,
        affiliations_empty=1,
        affiliations_pending=1,
        mapped=1,
        institutions_found=1,
        institutions_pending=1,
        venues=3,
        cited=1,
    )


def test_collect_coverage_reports_days_most_recent_first(archived: PaperStore) -> None:
    days = collect_coverage(archived, "cs.CV")

    assert [entry.label for entry in days] == ["2026-09-25", "2026-09-24"]
    assert days[0].coverage.papers == 3
    assert days[0].coverage.cited == 1
    assert days[1].coverage == Coverage(papers=1, affiliations_pending=1)


def test_collect_archive_coverage_reports_years_most_recent_first(archived: PaperStore) -> None:
    years = collect_archive_coverage(archived, "cs.CV")

    assert [entry.label for entry in years] == ["2020", "2015"]
    assert years[1].coverage == Coverage(
        papers=1, abstracts=1, affiliations_found=1, institutions_found=1, cited=1
    )


def test_collect_coverage_of_unknown_category_is_empty(store: PaperStore) -> None:
    assert collect_coverage(store, "cs.LG") == []
    assert collect_archive_coverage(store, "cs.CV") == []


def test_format_coverage_lists_days_totals_and_percentages(archived: PaperStore) -> None:
    report = format_coverage("cs.CV", collect_coverage(archived, "cs.CV"))

    lines = report.splitlines()
    assert lines[0] == "cs.CV: 4 papers over 2 days"
    assert lines[1].split() == [
        "day",
        "papers",
        "abstracts",
        "affiliated",
        "none",
        "pending",
        "mapped",
        "named",
        "venues",
        "cited",
    ]
    assert lines[2].split() == ["2026-09-25", "3", "2", "1", "1", "1", "1", "1", "1", "1"]
    assert lines[3].split() == ["2026-09-24", "1", "0", "0", "0", "1", "0", "0", "0", "0"]
    assert lines[4].split() == ["total", "4", "2", "1", "1", "2", "1", "1", "1", "1"]
    assert lines[5] == "abstracts 50%, affiliations 50% of 2 tried, venues 25%, citation counts 25%"
    assert lines[6] == "of the papers with affiliations: authors mapped 100%, institutions named 100%"


def test_format_coverage_mentions_institutions_not_looked_up() -> None:
    pending = replace(BASE, affiliations=("Somewhere",))
    report = format_coverage("cs.CV", [RowCoverage("2026-09-25", Coverage.of([pending]))])

    assert report.endswith("institutions named 0%, 1 not looked up yet")


def test_format_archive_coverage_lists_years(archived: PaperStore) -> None:
    report = format_archive_coverage("cs.CV", collect_archive_coverage(archived, "cs.CV"))

    lines = report.splitlines()
    assert lines[0] == "cs.CV archive: 2 papers over 2 years"
    assert lines[1].split()[0] == "year"
    assert lines[3].split() == ["2015", "1", "1", "1", "0", "0", "0", "1", "0", "1"]
    assert lines[4].split() == ["total", "2", "2", "1", "1", "0", "0", "1", "0", "2"]


def test_format_citations_gives_source_and_date(archived: PaperStore) -> None:
    citations = archived.load_citation_counts("cs.CV")
    assert citations is not None

    refreshed = citations.generated_at.date()
    line = format_citations("cs.CV", citations, today=refreshed + timedelta(days=14))

    assert line.startswith("cs.CV citation counts: 3 from S2, ")
    assert line.endswith(refreshed.isoformat())
    assert format_citations("cs.CV", citations, today=refreshed + timedelta(days=15)).endswith(
        f"{refreshed.isoformat()} (stale: 15 days old)"
    )


def test_format_coverage_of_an_empty_category() -> None:
    report = format_coverage("cs.CV", [])

    assert report.startswith("cs.CV: 0 papers over 0 days")
    assert "affiliations 0% of 0 tried" in report


def test_rich_tables_hold_the_same_rows(archived: PaperStore) -> None:
    console = Console(record=True, width=120)
    console.print(coverage_table("cs.CV", collect_coverage(archived, "cs.CV")))
    console.print(archive_coverage_table("cs.CV", collect_archive_coverage(archived, "cs.CV")))

    text = console.export_text()
    assert "cs.CV: 4 papers over 2 days" in text
    assert "cs.CV archive: 2 papers over 2 years" in text
    assert any(
        line.split() == ["total", "4", "2", "1", "1", "2", "1", "1", "1", "1"] for line in text.splitlines()
    )
    assert "abstracts 50%, affiliations 50% of 2 tried" in text


@pytest.mark.parametrize(
    ("day", "today", "expected"),
    [
        (date(2026, 10, 1), date(2026, 10, 1), 0),
        # Friday to Monday: one announcement day missed, not three.
        (date(2026, 10, 2), date(2026, 10, 5), 1),
        (date(2026, 9, 28), date(2026, 10, 5), 5),
    ],
)
def test_weekdays_since(day: date, today: date, expected: int) -> None:
    assert weekdays_since(day, today) == expected
