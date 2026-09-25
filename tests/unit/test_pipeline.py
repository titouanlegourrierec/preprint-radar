from collections import Counter
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from preprint_radar.http import HttpClient
from preprint_radar.models import Listing
from preprint_radar.pipeline import format_report, update_category
from preprint_radar.store import PaperStore

ATOM_ENTRY = """
  <entry>
    <id>http://arxiv.org/abs/{arxiv_id}v1</id>
    <summary>  Abstract of
      {arxiv_id}.  </summary>
    <author><name>Someone</name>{affiliation}</author>
  </entry>"""


def _atom_feed(ids: list[str]) -> str:
    entries = "".join(
        ATOM_ENTRY.format(
            arxiv_id=arxiv_id,
            affiliation="<arxiv:affiliation>Declared Institute</arxiv:affiliation>"
            if arxiv_id == "2609.28466"
            else "",
        )
        for arxiv_id in ids
    )
    return (
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">'
        f"{entries}</feed>"
    )


API_MISSING_ID = "2609.28473"
RSS_DAY_IDS = ["2609.30245", "2609.30234", "2609.28836", "2609.30249", "2609.29375"]


def _rss_feed(ids: list[str]) -> str:
    items = "".join(
        f"<item><link>https://arxiv.org/abs/{arxiv_id}</link>"
        f"<description>Announce Type: new\nAbstract: From RSS {arxiv_id}.</description></item>"
        for arxiv_id in ids
    )
    return f"<rss><channel>{items}</channel></rss>"


class FakeArxiv:
    """Route requests to canned responses and record which URLs were hit."""

    def __init__(self, listing_html: str, paper_html: Callable[[str], str]) -> None:
        self.listing_html = listing_html
        self.paper_html = paper_html
        self.hits: Counter[str] = Counter()
        self.api_ids: list[str] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        self.hits[url.path] += 1
        if url.path.startswith("/list/"):
            return httpx.Response(200, text=self.listing_html)
        if url.host == "rss.arxiv.org":
            return httpx.Response(200, text=_rss_feed(RSS_DAY_IDS))
        if url.host == "export.arxiv.org":
            ids = url.params["id_list"].split(",")
            self.api_ids.extend(ids)
            # Simulate an entry the API could not return: its abstract must come from HTML.
            return httpx.Response(200, text=_atom_feed([i for i in ids if i != API_MISSING_ID]))
        return self.html_page(url.path)

    def html_page(self, path: str) -> httpx.Response:
        pages = {
            f"/html/{API_MISSING_ID}v1": "2609.24787",
            "/html/2609.30249v1": "2609.30249",
        }
        if path == "/html/2609.30234v1":
            return httpx.Response(503)  # transient failure: retried on the next run
        if fixture := pages.get(path):
            return httpx.Response(200, text=self.paper_html(fixture))
        return httpx.Response(404)

    def client(self) -> HttpClient:
        return HttpClient(transport=httpx.MockTransport(self.handle), max_attempts=1)


@pytest.fixture
def fake(listing_html: str, paper_html: Callable[[str], str]) -> FakeArxiv:
    return FakeArxiv(listing_html, paper_html)


@pytest.fixture
def store(tmp_path: Path) -> PaperStore:
    return PaperStore(tmp_path / "data")


def _run(fake: FakeArxiv, store: PaperStore, **kwargs: int | None) -> Listing:
    with fake.client() as site, fake.client() as api:
        update_category("cs.CV", store=store, site_client=site, api_client=api, save_every=1, **kwargs)
    return Listing(papers=tuple(store.iter_papers("cs.CV")))


def test_update_enriches_and_stores_papers(fake: FakeArxiv, store: PaperStore) -> None:
    stored = {paper.arxiv_id: paper for paper in _run(fake, store).papers}

    assert len(stored) == 7
    # Abstracts of the latest day come from RSS, the API only fills the gaps.
    assert stored["2609.30245"].abstract == "From RSS 2609.30245."
    assert stored["2609.28466"].abstract == "Abstract of 2609.28466."
    # Missing from the API: the abstract is taken from the HTML rendering instead.
    abstract = stored["2609.28473"].abstract
    assert abstract is not None
    assert abstract.startswith("Forest inventories")
    assert sorted(fake.api_ids) == ["2609.28466", "2609.28473"]
    # Affiliations declared through the API win over HTML scraping.
    assert stored["2609.28466"].affiliations == ("Declared Institute",)
    assert stored["2609.30249"].affiliations is not None
    assert "NVIDIA" in stored["2609.30249"].affiliations
    # 404: nothing to extract; 503: left pending for the next run.
    assert stored["2609.28836"].affiliations == ()
    assert stored["2609.30234"].affiliations is None


def test_second_run_only_fetches_what_is_missing(fake: FakeArxiv, store: PaperStore) -> None:
    _run(fake, store)
    fake.hits.clear()

    with fake.client() as site, fake.client() as api:
        report = update_category("cs.CV", store=store, site_client=site, api_client=api)

    assert report.new == 0
    assert report.abstracts_fetched == 0
    assert fake.hits["/api/query"] == 0
    assert fake.hits["/rss/cs.CV"] == 0
    assert fake.hits["/html/2609.30249v1"] == 0
    assert fake.hits["/html/2609.30234v1"] == 1  # the one that failed is retried
    assert report.pending == 1


def test_max_html_fetches_limits_downloads(fake: FakeArxiv, store: PaperStore) -> None:
    _run(fake, store, max_html_fetches=0)

    assert not any(path.startswith("/html/") for path in fake.hits)


def test_format_report(fake: FakeArxiv, store: PaperStore) -> None:
    with fake.client() as site, fake.client() as api:
        report = update_category("cs.CV", store=store, site_client=site, api_client=api)

    assert format_report(report).startswith("cs.CV: 7 listed, 7 new, 7 abstracts")
