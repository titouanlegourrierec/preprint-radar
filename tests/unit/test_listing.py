from datetime import date

import httpx
import pytest

from preprint_radar.exceptions import ParseError
from preprint_radar.http import HttpClient
from preprint_radar.listing import fetch_listing, parse_listing, validate_category
from preprint_radar.models import Listing, Paper


def _paper(listing: Listing, arxiv_id: str) -> Paper:
    return next(paper for paper in listing.papers if paper.arxiv_id == arxiv_id)


def test_parses_every_entry(listing: Listing) -> None:
    assert len(listing.papers) == 7
    assert listing.total == 7
    assert listing.is_complete


def test_assigns_announcement_day_from_section_header(listing: Listing) -> None:
    days = [paper.announced for paper in listing.papers]
    assert days == [date(2026, 9, 25)] * 5 + [date(2026, 9, 24)] * 2


def test_parses_basic_fields(listing: Listing) -> None:
    paper = _paper(listing, "2609.30245")
    assert paper.title == "Towards Practical Compression of 3D Gaussian Splatting"
    assert paper.authors == (
        "Pengpeng Yu",
        "Yueru Chen",
        "Fei Song",
        "Tai Qin",
        "Qi Zhang",
        "Jing Wang",
        "Yulan Guo",
    )
    assert paper.primary_subject == "Computer Vision and Pattern Recognition (cs.CV)"
    assert paper.subjects == ("Computer Vision and Pattern Recognition (cs.CV)",)
    assert paper.comments is None
    assert paper.journal_ref is None
    assert not paper.is_cross_list


def test_replaces_placeholder_links_in_comments(listing: Listing) -> None:
    paper = _paper(listing, "2609.30234")
    assert paper.comments == (
        "Accepted to SIGGRAPH Asia 2026. Project Page: https://humansensinglab.github.io/OmniFabric/"
    )


def test_parses_journal_reference(listing: Listing) -> None:
    journal_ref = _paper(listing, "2609.29375").journal_ref
    assert journal_ref is not None
    assert journal_ref.startswith('M. Zhao et al., "Free-Init:')
    assert journal_ref.endswith("Dec. 2024")


def test_parses_cross_list(listing: Listing) -> None:
    paper = _paper(listing, "2609.30249")
    assert paper.cross_list_from == "cs.RO"
    assert paper.primary_subject == "Robotics (cs.RO)"
    assert paper.subjects == (
        "Robotics (cs.RO)",
        "Artificial Intelligence (cs.AI)",
        "Computer Vision and Pattern Recognition (cs.CV)",
    )
    assert "Tomás Lozano-Pérez" in paper.authors


def test_parses_html_url_when_available(listing: Listing) -> None:
    assert _paper(listing, "2609.30245").html_url == "https://arxiv.org/html/2609.30245v1"


def test_html_url_is_optional(listing_html: str) -> None:
    html = listing_html.replace('title="View HTML"', 'title="Something else"')
    assert all(paper.html_url is None for paper in parse_listing(html).papers)


def test_keeps_latex_in_titles(listing: Listing) -> None:
    assert _paper(listing, "2609.28836").title.startswith("M$^2$PFN:")


def test_total_is_optional(listing_html: str) -> None:
    html = listing_html.replace("Total of 7 entries", "")
    assert parse_listing(html).total is None


def test_rejects_page_without_articles() -> None:
    with pytest.raises(ParseError, match="dl#articles"):
        parse_listing("<html><body><p>Nothing here</p></body></html>")


def test_rejects_unknown_date_format(listing_html: str) -> None:
    html = listing_html.replace("Fri, 25 Sep 2026", "25/09/2026")
    with pytest.raises(ParseError, match="25/09/2026"):
        parse_listing(html)


def test_fetch_listing_requests_recent_page(listing_html: str) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text=listing_html)

    with HttpClient(transport=httpx.MockTransport(handler)) as client:
        listing = fetch_listing(client, "cs.CV", max_entries=100)

    assert len(listing.papers) == 7
    [request] = requests
    assert request.url.path == "/list/cs.CV/recent"
    assert request.url.params["show"] == "100"


def test_fetch_listing_rejects_out_of_range_max_entries() -> None:
    with HttpClient() as client, pytest.raises(ValueError, match="max_entries"):
        fetch_listing(client, "cs.CV", max_entries=0)


@pytest.mark.parametrize("category", ["cs.CV", "cs.LG", "astro-ph.CO", "hep-th", "q-bio.NC", "math.AG"])
def test_validate_category_accepts_known_formats(category: str) -> None:
    assert validate_category(category) == category


@pytest.mark.parametrize("category", ["", "CV", "cs.", "cs/CV", "../etc", "cs.CV?show=1"])
def test_validate_category_rejects_malformed_values(category: str) -> None:
    with pytest.raises(ValueError, match="Invalid arXiv category"):
        validate_category(category)
