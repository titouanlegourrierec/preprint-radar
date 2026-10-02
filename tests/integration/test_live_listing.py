"""Smoke tests against the real arXiv, to detect layout changes.

Deselected by default; run them with ``uv run pytest -m network``. The weekly canary
workflow runs them, so that a change shows up before it reaches the data.
"""

import os

import pytest

from preprint_radar.config import CONTACT_ENV_VAR
from preprint_radar.http import (
    ARXIV_API_DELAY_SECONDS,
    ARXIV_CRAWL_DELAY_SECONDS,
    HttpClient,
    build_user_agent,
)
from preprint_radar.sources.arxiv_api import fetch_metadata
from preprint_radar.sources.arxiv_html import front_matter_html, parse_front_matter
from preprint_radar.sources.arxiv_listing import fetch_listing

pytestmark = pytest.mark.network

# Read at import, before the autouse fixture of conftest.py hides it from every test.
USER_AGENT = build_user_agent(os.environ.get(CONTACT_ENV_VAR))
# HTML pages read: most papers name affiliations, so a few pages all without any mean that
# the extraction no longer matches the layout.
HTML_SAMPLE = 6


def test_recent_listing_is_fully_parsed_and_enrichable() -> None:
    with HttpClient(user_agent=USER_AGENT, min_interval=ARXIV_CRAWL_DELAY_SECONDS) as site:
        listing = fetch_listing(site, "cs.CV")
        assert listing.papers
        assert listing.is_complete
        assert all(paper.title and paper.authors for paper in listing.papers)

        with_html = [paper for paper in listing.papers if paper.html_url][:HTML_SAMPLE]
        pages = [(paper, site.get_text(paper.html_url)) for paper in with_html if paper.html_url]
        fronts = [parse_front_matter(html, authors=paper.authors) for paper, html in pages]
        # The page cache keeps only the front matter: it must extract as the whole page.
        for (paper, html), front in zip(pages, fronts, strict=True):
            assert parse_front_matter(front_matter_html(html), authors=paper.authors) == front
        # At most one page without an abstract: some classes put it where LaTeXML drops it.
        assert sum(not front.abstract for front in fronts) <= 1
        assert any(front.affiliations for front in fronts)
        assert any(front.author_affiliations for front in fronts)


def test_the_api_returns_recent_papers() -> None:
    # Apart: the API throttles after a couple of requests, and is only a fallback.
    with (
        HttpClient(user_agent=USER_AGENT, min_interval=ARXIV_CRAWL_DELAY_SECONDS) as site,
        HttpClient(user_agent=USER_AGENT, min_interval=ARXIV_API_DELAY_SECONDS) as api,
    ):
        sample = fetch_listing(site, "cs.CV").papers[:5]
        metadata = fetch_metadata(api, [paper.arxiv_id for paper in sample])

    assert set(metadata) == {paper.arxiv_id for paper in sample}
