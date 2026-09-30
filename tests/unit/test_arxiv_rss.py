from pathlib import Path

import httpx
import pytest

from preprint_radar.exceptions import ParseError
from preprint_radar.http import HttpClient
from preprint_radar.sources.arxiv_rss import fetch_rss_abstracts, parse_rss_abstracts

RSS_FEED = (Path(__file__).parents[1] / "fixtures" / "rss_cs_cv.xml").read_text(encoding="utf-8")


def test_parse_rss_abstracts() -> None:
    abstracts = parse_rss_abstracts(RSS_FEED)

    assert set(abstracts) == {"2609.28539", "2609.28476", "2004.09073"}
    abstract = abstracts["2609.28539"]
    assert abstract.startswith("Gaussian head avatars typically model")
    assert "Announce Type" not in abstract
    assert "\n" not in abstract


def test_parse_rss_rejects_invalid_xml() -> None:
    with pytest.raises(ParseError):
        parse_rss_abstracts("<rss")


def test_items_without_abstract_are_skipped() -> None:
    feed = "<rss><channel><item><link>https://arxiv.org/abs/1</link><description>x</description></item></channel></rss>"
    assert parse_rss_abstracts(feed) == {}


def test_fetch_rss_abstracts_requests_category_feed() -> None:
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, text=RSS_FEED)

    with HttpClient(transport=httpx.MockTransport(handler)) as client:
        assert len(fetch_rss_abstracts(client, "cs.CV")) == 3
    assert urls == ["https://rss.arxiv.org/rss/cs.CV"]
