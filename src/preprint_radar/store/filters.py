"""Functions to narrow down a collection of papers."""

from collections.abc import Iterable

from preprint_radar.models import Paper


def latest_day(papers: Iterable[Paper]) -> list[Paper]:
    """Keep only the papers announced on the most recent day.

    Args:
        papers: Papers to filter.

    Returns:
        Papers announced on the latest date, in their original order.
    """
    papers = list(papers)
    if not papers:
        return []
    latest = max(paper.announced for paper in papers)
    return [paper for paper in papers if paper.announced == latest]


def exclude_cross_lists(papers: Iterable[Paper]) -> list[Paper]:
    """Drop papers cross-listed from another category.

    Args:
        papers: Papers to filter.

    Returns:
        Papers whose primary category is the listed one, in their original order.
    """
    return [paper for paper in papers if not paper.is_cross_list]
