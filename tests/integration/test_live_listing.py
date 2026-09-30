"""Smoke tests against the real arXiv, to detect layout changes.

Deselected by default; run them with ``uv run pytest -m network``.
"""

import pytest

from preprint_radar.http import ARXIV_API_DELAY_SECONDS, ARXIV_CRAWL_DELAY_SECONDS, HttpClient
from preprint_radar.sources.arxiv_api import fetch_metadata
from preprint_radar.sources.arxiv_html import fetch_front_matter
from preprint_radar.sources.arxiv_listing import fetch_listing

pytestmark = pytest.mark.network


def test_recent_listing_is_fully_parsed_and_enrichable() -> None:
    with (
        HttpClient(min_interval=ARXIV_CRAWL_DELAY_SECONDS) as site,
        HttpClient(min_interval=ARXIV_API_DELAY_SECONDS) as api,
    ):
        listing = fetch_listing(site, "cs.CV")
        assert listing.papers
        assert listing.is_complete
        assert all(paper.title and paper.authors for paper in listing.papers)

        sample = listing.papers[:5]
        metadata = fetch_metadata(api, [paper.arxiv_id for paper in sample])
        assert set(metadata) == {paper.arxiv_id for paper in sample}

        with_html = next(paper for paper in listing.papers if paper.html_url)
        assert with_html.html_url is not None
        assert fetch_front_matter(site, with_html.html_url).abstract
