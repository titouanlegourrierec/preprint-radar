from datetime import date

import pytest

from preprint_radar.archive.selection import (
    Candidate,
    citation_rate,
    is_recent,
    monthly_rate,
    recent_since,
    select_archive,
    select_top_recent,
)

TODAY = date(2026, 9, 30)


def _old(arxiv_id: str, citations: int | None, years: int = 4) -> Candidate:
    return Candidate(arxiv_id, date(TODAY.year - years, TODAY.month, 1), citations)


def test_citation_rate_counts_at_least_one_year() -> None:
    assert citation_rate(40, date(2022, 9, 30), TODAY) == pytest.approx(10, rel=0.01)
    assert citation_rate(40, date(2026, 3, 1), TODAY) == 40
    assert citation_rate(None, date(2020, 1, 1), TODAY) == 0


def test_recent_papers_are_not_candidates() -> None:
    assert is_recent(date(2026, 1, 1), TODAY)
    assert not is_recent(date(2025, 9, 1), TODAY)
    selection = select_archive(
        [Candidate("2608.00001", date(2026, 8, 1), 500)], set(), budget=10, today=TODAY
    )

    assert selection.keep == frozenset()


def test_the_budget_keeps_the_best_rates_whatever_the_age() -> None:
    candidates = [
        _old("1512.00001", 1000, years=10),  # 100/year
        _old("2209.00001", 240, years=4),  # 60/year
        _old("1805.00001", 300, years=8),  # 37.5/year
        _old("2309.00001", 0),
        _old("2209.00002", None),
    ]

    selection = select_archive(candidates, set(), budget=2, today=TODAY)

    assert selection.keep == {"1512.00001", "2209.00001"}
    assert selection.entered == selection.keep
    assert selection.threshold == pytest.approx(60, rel=0.05)


def test_never_cited_papers_stay_out_even_under_budget() -> None:
    selection = select_archive(
        [_old("2309.00001", 0), _old("2209.00002", None)], set(), budget=10, today=TODAY
    )

    assert selection.keep == frozenset()


def test_archived_papers_stay_within_the_margin() -> None:
    # Ranks: a (100), b (90), c (80), d (70); budget 2, margin 1.5: stay while rank < 3.
    candidates = [_old("a", 400), _old("b", 360), _old("c", 320), _old("d", 280)]

    selection = select_archive(candidates, {"c", "d"}, budget=2, today=TODAY, margin=1.5)

    assert selection.keep == {"a", "b", "c"}
    assert selection.entered == {"a", "b"}
    assert selection.left == {"d"}


def test_ties_are_broken_by_identifier() -> None:
    selection = select_archive([_old("b", 100), _old("a", 100)], set(), budget=1, today=TODAY)

    assert selection.keep == {"a"}


def test_monthly_rate_counts_at_least_the_minimum_age() -> None:
    assert monthly_rate(60, date(2026, 3, 31), TODAY, 2) == pytest.approx(10, rel=0.02)
    # A week old: counted over two months.
    assert monthly_rate(6, date(2026, 9, 23), TODAY, 2) == 3
    assert monthly_rate(None, date(2026, 3, 31), TODAY, 2) == 0


def test_the_window_starts_364_days_before_today() -> None:
    since = recent_since(TODAY)
    assert since == date(2025, 10, 1)
    assert is_recent(since, TODAY)
    assert not is_recent(date(2025, 9, 30), TODAY)


def test_the_most_cited_papers_of_the_last_12_months_by_citations_per_month() -> None:
    candidates = [
        Candidate("2510.00001", date(2025, 10, 1), 120),  # 12 months: 10 a month
        Candidate("2604.00001", date(2026, 3, 31), 90),  # 6 months: 15 a month
        Candidate("2609.00001", date(2026, 9, 23), 24),  # a week, counted over two months: 12
        Candidate("2609.00002", date(2026, 9, 29), 2),  # 1 a month
        Candidate("2609.00003", date(2026, 9, 29), 0),
        Candidate("2609.00004", date(2026, 9, 29), None),
        Candidate("2509.00001", date(2025, 9, 30), 5000),  # the archive's
    ]

    assert select_top_recent(candidates, budget=3, today=TODAY) == {"2604.00001", "2609.00001", "2510.00001"}
    # Never cited, they never enter, even under the budget.
    assert select_top_recent(candidates, budget=10, today=TODAY) == {
        "2510.00001",
        "2604.00001",
        "2609.00001",
        "2609.00002",
    }
    # Counted over their real age, the week-old papers would come first.
    assert select_top_recent(candidates, budget=2, today=TODAY, min_months=0.1) == {
        "2609.00001",
        "2609.00002",
    }
