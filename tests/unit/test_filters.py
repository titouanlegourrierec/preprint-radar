from datetime import date

from preprint_radar import filters
from preprint_radar.models import Listing


def test_latest_day(listing: Listing) -> None:
    papers = filters.latest_day(listing.papers)
    assert len(papers) == 5
    assert {paper.announced for paper in papers} == {date(2026, 9, 25)}


def test_latest_day_of_nothing_is_empty() -> None:
    assert filters.latest_day([]) == []


def test_exclude_cross_lists(listing: Listing) -> None:
    papers = filters.exclude_cross_lists(listing.papers)
    assert len(papers) == 5
    assert all(paper.cross_list_from is None for paper in papers)
