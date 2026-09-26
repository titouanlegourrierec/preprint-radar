from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from preprint_radar.models import Paper
from preprint_radar.stats import Coverage, collect_coverage, format_coverage
from preprint_radar.store import PaperStore

BASE = Paper(
    arxiv_id="2609.00000",
    announced=date(2026, 9, 25),
    title="A paper",
    authors=("Ada Lovelace",),
)

# One paper per affiliation bucket; two abstracts; one venue.
PAPERS = (
    replace(BASE, arxiv_id="2609.00001", abstract="Done.", affiliations=("MIT",), venue="ECCV 2026"),
    replace(BASE, arxiv_id="2609.00002", abstract="Done.", affiliations=()),
    replace(BASE, arxiv_id="2609.00003"),
)


@pytest.fixture
def store(tmp_path: Path) -> PaperStore:
    store = PaperStore(tmp_path / "data")
    store.save("cs.CV", PAPERS)
    store.save("cs.CV", [replace(BASE, arxiv_id="2609.00004", announced=date(2026, 9, 24))])
    return store


def test_coverage_counts_each_affiliation_bucket_once() -> None:
    assert Coverage.of(PAPERS) == Coverage(
        papers=3,
        abstracts=2,
        affiliations_found=1,
        affiliations_empty=1,
        affiliations_pending=1,
        venues=1,
    )


def test_coverage_adds_field_by_field() -> None:
    assert Coverage.of(PAPERS) + Coverage(papers=1, venues=2) == Coverage(
        papers=4,
        abstracts=2,
        affiliations_found=1,
        affiliations_empty=1,
        affiliations_pending=1,
        venues=3,
    )


def test_collect_coverage_reports_days_most_recent_first(store: PaperStore) -> None:
    days = collect_coverage(store, "cs.CV")

    assert [entry.day for entry in days] == [date(2026, 9, 25), date(2026, 9, 24)]
    assert days[0].coverage.papers == 3
    assert days[1].coverage == Coverage(papers=1, affiliations_pending=1)


def test_collect_coverage_of_unknown_category_is_empty(store: PaperStore) -> None:
    assert collect_coverage(store, "cs.LG") == []


def test_format_coverage_lists_days_totals_and_percentages(store: PaperStore) -> None:
    report = format_coverage("cs.CV", collect_coverage(store, "cs.CV"))

    lines = report.splitlines()
    assert lines[0] == "cs.CV: 4 papers over 2 days"
    assert lines[1].split() == ["day", "papers", "abstracts", "affiliated", "none", "pending", "venues"]
    assert lines[2].split() == ["2026-09-25", "3", "2", "1", "1", "1", "1"]
    assert lines[3].split() == ["2026-09-24", "1", "0", "0", "0", "1", "0"]
    assert lines[4].split() == ["total", "4", "2", "1", "1", "2", "1"]
    assert lines[5] == "abstracts 50%, affiliations 50% of 2 tried, venues 25%"


def test_format_coverage_of_an_empty_category() -> None:
    report = format_coverage("cs.CV", [])

    assert report.startswith("cs.CV: 0 papers over 0 days")
    assert "affiliations 0% of 0 tried" in report
