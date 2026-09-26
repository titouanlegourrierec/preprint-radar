from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path

import httpx
import pytest

from preprint_radar.http import HttpClient
from preprint_radar.listing import parse_catchup
from preprint_radar.models import Listing, Paper
from preprint_radar.pipeline import backfill_category, format_report, update_category
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
        # Catchup pages by path; other days have no announcement.
        self.catchup_pages: dict[str, str] = {}
        self.catchup_empty_html = ""

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        self.hits[url.path] += 1
        if url.path.startswith("/list/"):
            return httpx.Response(200, text=self.listing_html)
        if url.path.startswith("/catchup/"):
            return httpx.Response(200, text=self.catchup_pages.get(url.path, self.catchup_empty_html))
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
            "/html/2608.28663v1": "2609.30249",  # any real front matter will do
        }
        if path == "/html/2609.30234v1":
            return httpx.Response(503)  # transient failure: retried on the next run
        if fixture := pages.get(path):
            return httpx.Response(200, text=self.paper_html(fixture))
        return httpx.Response(404)

    def client(self) -> HttpClient:
        return HttpClient(transport=httpx.MockTransport(self.handle), max_attempts=1)


@pytest.fixture
def fake(listing_html: str, paper_html: Callable[[str], str], catchup_empty_html: str) -> FakeArxiv:
    fake = FakeArxiv(listing_html, paper_html)
    fake.catchup_empty_html = catchup_empty_html
    return fake


def _catchup_page(ids: list[str]) -> str:
    """Catchup page of Thu, 24 Sep 2026 announcing ``ids``, with abstracts."""
    entries = "".join(
        f'<dt><a href="/abs/{arxiv_id}" title="Abstract" id="{arxiv_id}">arXiv:{arxiv_id}</a></dt>'
        f"<dd><div class='meta'><div class='list-title mathjax'>Paper {arxiv_id}</div>"
        f"<p class='mathjax'>From catchup {arxiv_id}.</p></div></dd>"
        for arxiv_id in ids
    )
    return (
        "<div id='dlpage'><h1>Catchup results for Computer Vision on Thu, 24 Sep 2026</h1>"
        f"<dl id='articles'><h3>New submissions (showing {len(ids)} of {len(ids)} entries)</h3>"
        f"{entries}</dl></div>"
    )


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


def test_update_takes_older_abstracts_from_catchup_pages(fake: FakeArxiv, store: PaperStore) -> None:
    fake.catchup_pages = {"/catchup/cs.CV/2026-09-24": _catchup_page(["2609.28466", "2609.28473"])}

    stored = {paper.arxiv_id: paper for paper in _run(fake, store, max_html_fetches=0).papers}

    # The latest day comes from RSS, the day before from its catchup page: no API call.
    assert stored["2609.30245"].abstract == "From RSS 2609.30245."
    assert stored["2609.28466"].abstract == "From catchup 2609.28466."
    assert fake.hits["/catchup/cs.CV/2026-09-24"] == 1
    assert fake.api_ids == []


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


BACKFILL_DAYS = [date(2026, 8, 31), date(2026, 9, 1), date(2026, 9, 2)]


@pytest.fixture
def fake_catchup(fake: FakeArxiv, catchup_html: str, catchup_empty_html: str) -> FakeArxiv:
    fake.catchup_pages = {"/catchup/cs.CV/2026-09-01": catchup_html}
    fake.catchup_empty_html = catchup_empty_html
    return fake


def _backfill(fake: FakeArxiv, store: PaperStore, **kwargs: int | None) -> dict[str, Paper]:
    with fake.client() as site:
        backfill_category("cs.CV", BACKFILL_DAYS, store=store, site_client=site, save_every=1, **kwargs)
    return {paper.arxiv_id: paper for paper in store.iter_papers("cs.CV")}


def test_backfill_stores_each_day_with_abstracts(fake_catchup: FakeArxiv, store: PaperStore) -> None:
    stored = _backfill(fake_catchup, store)

    assert set(stored) == {"2608.28663", "2608.28674", "2608.28913", "2608.28693"}
    assert store.days("cs.CV") == [date(2026, 9, 1)]
    assert all(paper.abstract for paper in stored.values())
    assert [path for path in fake_catchup.hits if path.startswith("/catchup/")] == [
        "/catchup/cs.CV/2026-09-02",
        "/catchup/cs.CV/2026-09-01",
        "/catchup/cs.CV/2026-08-31",
    ]
    # Abstracts come with the catchup pages: neither RSS nor the API is needed.
    assert fake_catchup.hits["/rss/cs.CV"] == fake_catchup.hits["/api/query"] == 0
    assert (store.root / "index.json").is_file()


def test_backfill_reads_affiliations_from_html(fake_catchup: FakeArxiv, store: PaperStore) -> None:
    stored = _backfill(fake_catchup, store)

    affiliations = stored["2608.28663"].affiliations
    assert affiliations is not None
    assert "NVIDIA" in affiliations
    assert stored["2608.28913"].affiliations == ()  # no HTML front matter (404)
    assert stored["2608.28674"].affiliations is None  # no HTML rendering at all


def test_backfill_reuses_stored_enrichment(
    fake_catchup: FakeArxiv, store: PaperStore, catchup_html: str
) -> None:
    known = next(paper for paper in parse_catchup(catchup_html).papers if paper.arxiv_id == "2608.28913")
    store.save("cs.CV", [replace(known, abstract=None, affiliations=("Stored Lab",))])

    with fake_catchup.client() as site:
        report = backfill_category("cs.CV", BACKFILL_DAYS, store=store, site_client=site)

    stored = {paper.arxiv_id: paper for paper in store.iter_papers("cs.CV")}
    assert stored["2608.28913"].affiliations == ("Stored Lab",)
    assert stored["2608.28913"].abstract is not None
    assert fake_catchup.hits["/html/2608.28913v1"] == 0
    assert (report.listed, report.new, report.abstracts_fetched) == (4, 3, 4)


def test_backfill_max_html_fetches_limits_downloads(fake_catchup: FakeArxiv, store: PaperStore) -> None:
    _backfill(fake_catchup, store, max_html_fetches=0)

    assert not any(path.startswith("/html/") for path in fake_catchup.hits)


def test_backfill_reuses_days_already_stored(fake_catchup: FakeArxiv, store: PaperStore) -> None:
    _backfill(fake_catchup, store, max_html_fetches=0)
    fake_catchup.hits.clear()

    _backfill(fake_catchup, store, max_html_fetches=0)

    # Only the days without papers (no announcement) are asked for again.
    assert [path for path in fake_catchup.hits if path.startswith("/catchup/")] == [
        "/catchup/cs.CV/2026-09-02",
        "/catchup/cs.CV/2026-08-31",
    ]
