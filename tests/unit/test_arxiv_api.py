import httpx
import pytest

from preprint_radar.exceptions import ParseError
from preprint_radar.http import HttpClient
from preprint_radar.sources.arxiv_api import API_URL, fetch_metadata, parse_feed


def test_parse_feed_extracts_abstracts(api_feed: str) -> None:
    entries = {meta.arxiv_id: meta for meta in parse_feed(api_feed)}

    assert set(entries) == {"2609.29048", "2609.29373"}
    abstract = entries["2609.29048"].abstract
    assert abstract
    assert "\n" not in abstract
    assert entries["2609.29048"].affiliations == ()


def test_parse_feed_deduplicates_affiliations(api_feed: str) -> None:
    affiliations = next(meta for meta in parse_feed(api_feed) if meta.arxiv_id == "2609.29373").affiliations

    assert (
        affiliations[0] == "Oxford Machine Learning in NeuroImaging Lab, University of Oxford, United Kingdom"
    )
    assert len(affiliations) == len(set(affiliations)) == 6


def test_parse_feed_skips_error_entries(api_feed: str, caplog: pytest.LogCaptureFixture) -> None:
    list(parse_feed(api_feed))
    assert "incorrect id format" in caplog.text


def test_parse_feed_rejects_invalid_xml() -> None:
    with pytest.raises(ParseError):
        list(parse_feed("<feed"))


def test_fetch_metadata_batches_ids(api_feed: str) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text=api_feed)

    ids = ["2609.29048", "2609.29373", "2609.00001"]
    with HttpClient(transport=httpx.MockTransport(handler)) as client:
        metadata = fetch_metadata(client, ids, batch_size=2)

    assert [request.url.params["id_list"] for request in requests] == [
        "2609.29048,2609.29373",
        "2609.00001",
    ]
    assert all(str(request.url).startswith(API_URL) for request in requests)
    assert b"id_list=2609.29048,2609.29373" in requests[0].url.query  # literal commas
    assert set(metadata) == {"2609.29048", "2609.29373"}


def test_fetch_metadata_stops_at_first_failure(api_feed: str) -> None:
    responses = iter([httpx.Response(200, text=api_feed), httpx.Response(400)])
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return next(responses)

    ids = ["2609.29048", "2609.29373", "2609.00001", "2609.00002", "2609.00003"]
    with HttpClient(transport=httpx.MockTransport(handler)) as client:
        metadata = fetch_metadata(client, ids, batch_size=2)

    assert len(calls) == 2
    assert set(metadata) == {"2609.29048", "2609.29373"}


def test_parse_feed_filters_notes_typed_as_affiliations() -> None:
    feed = (
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">'
        "<entry><id>http://arxiv.org/abs/2609.00001v1</id><summary>Text.</summary>"
        "<author><name>A</name><arxiv:affiliation>ECCV 2026. Corresponding author is B</arxiv:affiliation>"
        "<arxiv:affiliation>Wuhan University</arxiv:affiliation></author></entry></feed>"
    )
    [meta] = parse_feed(feed)
    assert meta.affiliations == ("Wuhan University",)
