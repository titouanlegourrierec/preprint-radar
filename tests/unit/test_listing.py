from datetime import date

import httpx
import pytest

from preprint_radar.exceptions import ParseError
from preprint_radar.http import HttpClient
from preprint_radar.listing import (
    fetch_catchup,
    fetch_listing,
    parse_catchup,
    parse_listing,
    validate_category,
)
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


def test_detects_venue(listing: Listing) -> None:
    assert _paper(listing, "2609.30234").venue == "SIGGRAPH Asia 2026"
    assert _paper(listing, "2609.29375").venue == "RA-L 2024"
    assert _paper(listing, "2609.30245").venue is None


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


@pytest.mark.parametrize(("old", "new"), [("Total of 7 entries", ""), ("class='paging'", "class='other'")])
def test_total_is_optional(listing_html: str, old: str, new: str) -> None:
    html = listing_html.replace(old, new)
    assert parse_listing(html).total is None


def test_keeps_the_text_of_other_links(listing_html: str) -> None:
    html = listing_html.replace("this https URL</a>", "the OmniFabric page</a>", 1)

    comments = _paper(parse_listing(html), "2609.30234").comments

    assert comments is not None
    assert comments.endswith("Project Page: the OmniFabric page")


@pytest.mark.parametrize(
    ("old", "new", "error"),
    [
        pytest.param("<dt>", "<dt></dt><dt>", "Mismatched <dt>/<dd> counts", id="term-without-details"),
        pytest.param(
            "class='list-title mathjax'", "class='list-other'", "Missing title for 2609.30245", id="no-title"
        ),
        pytest.param('href ="/abs/2609.30245"', 'href ="/elsewhere"', "a\\[href", id="no-identifier"),
    ],
)
def test_rejects_malformed_entries(listing_html: str, old: str, new: str, error: str) -> None:
    with pytest.raises(ParseError, match=error):
        parse_listing(listing_html.replace(old, new, 1))


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


def test_fetch_listing_warns_about_missing_entries(
    listing_html: str, caplog: pytest.LogCaptureFixture
) -> None:
    html = listing_html.replace("Total of 7 entries", "Total of 9 entries")
    with HttpClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=html))) as client:
        listing = fetch_listing(client, "cs.CV", max_entries=100)

    assert len(listing.papers) == 7
    assert "Parsed 7 papers but the cs.CV listing announces 9" in caplog.text


def test_listing_pages_have_no_abstracts(listing: Listing) -> None:
    assert all(paper.abstract is None for paper in listing.papers)


def test_catchup_keeps_new_submissions_and_cross_lists(catchup_html: str) -> None:
    catchup = parse_catchup(catchup_html)

    # The replacement (2406.00434, an older paper) is skipped, as in the recent listing.
    assert [paper.arxiv_id for paper in catchup.papers] == [
        "2608.28663",
        "2608.28674",
        "2608.28913",
        "2608.28693",
    ]
    assert catchup.total == 4
    assert catchup.is_complete


def test_catchup_takes_the_day_from_the_title(catchup_html: str) -> None:
    assert {paper.announced for paper in parse_catchup(catchup_html).papers} == {date(2026, 9, 1)}


def test_catchup_parses_abstracts_and_metadata(catchup_html: str) -> None:
    catchup = parse_catchup(catchup_html)

    first = _paper(catchup, "2608.28663")
    assert first.abstract is not None
    assert first.abstract.startswith(
        "Reliable individual cattle identification supports disease surveillance"
    )
    assert "  " not in first.abstract
    accepted = _paper(catchup, "2608.28913")
    assert accepted.venue == "ECCV 2026"
    assert accepted.comments is not None
    assert accepted.comments.endswith("Project page: https://mmwave-inverse-rendering.github.io/")
    cross_list = _paper(catchup, "2608.28693")
    assert cross_list.cross_list_from == "cs.RO"
    assert cross_list.html_url == "https://arxiv.org/html/2608.28693v1"
    assert _paper(catchup, "2608.28674").html_url is None


def test_catchup_of_a_day_without_announcement_is_empty(catchup_empty_html: str) -> None:
    catchup = parse_catchup(catchup_empty_html)

    assert catchup.papers == ()
    assert catchup.is_complete


def test_catchup_rejects_page_without_dated_title(catchup_html: str) -> None:
    html = catchup_html.replace("on Tue, 01 Sep 2026</h1>", "</h1>")
    with pytest.raises(ParseError, match="catchup"):
        parse_catchup(html)


def test_catchup_rejects_unknown_sections(catchup_html: str) -> None:
    html = catchup_html.replace("Cross submissions", "Withdrawn submissions")
    with pytest.raises(ParseError, match="Withdrawn submissions"):
        parse_catchup(html)


def test_fetch_catchup_requests_one_day_with_abstracts(catchup_html: str) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text=catchup_html)

    with HttpClient(transport=httpx.MockTransport(handler)) as client:
        catchup = fetch_catchup(client, "cs.CV", date(2026, 9, 1))

    assert len(catchup.papers) == 4
    [request] = requests
    assert request.url.path == "/catchup/cs.CV/2026-09-01"
    assert request.url.params["abs"] == "True"


def test_fetch_catchup_warns_about_missing_entries(
    catchup_html: str, caplog: pytest.LogCaptureFixture
) -> None:
    html = catchup_html.replace("showing 3 of 3 entries", "showing 5 of 5 entries")
    with HttpClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=html))) as client:
        catchup = fetch_catchup(client, "cs.CV", date(2026, 9, 1))

    assert len(catchup.papers) == 4
    assert "Parsed 4 papers but the cs.CV catchup page of 2026-09-01 announces 6" in caplog.text


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
