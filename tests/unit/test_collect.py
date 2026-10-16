import gzip
import json
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from tests.conftest import FIXTURES_DIR

from preprint_radar.collect import (
    DRIFT_MIN_PAGES,
    MAX_CONSECUTIVE_DAY_FAILURES,
    MAX_CONSECUTIVE_HTML_FAILURES,
    ArchiveAffiliationsReport,
    CitationsReport,
    CodeReport,
    CountriesReport,
    HtmlReading,
    OpenAlexReport,
    Ror,
    Stop,
    UpdateReport,
    _about,
    _add_html_front_matter,
    add_institutions,
    backfill_category,
    catch_up_since,
    format_archive_affiliations_report,
    format_citations_report,
    format_code_report,
    format_countries_report,
    format_openalex_report,
    format_report,
    reextract_category,
    ror_answers,
    today,
    update_archive_affiliations,
    update_category,
    update_citation_counts,
    update_code_records,
    update_countries,
    update_openalex_affiliations,
)
from preprint_radar.exceptions import SchemaVersionError
from preprint_radar.http import HttpClient, RateLimiter
from preprint_radar.models import CodeRecord, Institution, Listing, Paper, Provenance, ScholarRecord
from preprint_radar.sources.arxiv_html import EXTRACTOR_VERSION, PageCache, parse_front_matter
from preprint_radar.sources.arxiv_listing import parse_catchup
from preprint_radar.store.paper_store import PaperStore

# The day the tests read pages and look up ROR: fixed, so that a run across midnight UTC
# cannot see two days.
READ_ON = date(2026, 9, 25)


# The function itself, before the fixture below pins the day of every test.
_TODAY = today


def test_a_run_is_dated_in_utc() -> None:
    assert _TODAY() == datetime.now(tz=UTC).date()


@pytest.fixture(autouse=True)
def _reading_day(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("preprint_radar.collect.today", lambda: READ_ON)


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
        self.ror_requests: list[str] = []
        # Catchup pages by path; other days have no announcement, but those that fail.
        self.catchup_pages: dict[str, str] = {}
        self.catchup_failing: set[str] = set()
        self.catchup_empty_html = ""

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        self.hits[url.path] += 1
        if url.path.startswith("/list/"):
            return httpx.Response(200, text=self.listing_html)
        if url.path.startswith("/catchup/"):
            return self.catchup_page(url.path)
        if url.host == "rss.arxiv.org":
            return httpx.Response(200, text=_rss_feed(RSS_DAY_IDS))
        if url.host == "api.ror.org":
            self.ror_requests.append(url.params["affiliation"])
            name = "peking" if "Peking" in url.params["affiliation"] else "meta"
            return httpx.Response(
                200, text=(FIXTURES_DIR / "ror" / f"{name}.json").read_text(encoding="utf-8")
            )
        if url.host == "export.arxiv.org":
            ids = url.params["id_list"].split(",")
            self.api_ids.extend(ids)
            # Simulate an entry the API could not return: its abstract must come from HTML.
            return httpx.Response(200, text=_atom_feed([i for i in ids if i != API_MISSING_ID]))
        return self.html_page(url.path)

    def catchup_page(self, path: str) -> httpx.Response:
        if path in self.catchup_failing:
            return httpx.Response(503)
        return httpx.Response(200, text=self.catchup_pages.get(path, self.catchup_empty_html))

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


def _catchup_page(ids: list[str], *, on: str = "Thu, 24 Sep 2026", total: int | None = None) -> str:
    """Catchup page of the day ``on`` announcing ``ids`` (of ``total`` entries), with abstracts."""
    entries = "".join(
        f'<dt><a href="/abs/{arxiv_id}" title="Abstract" id="{arxiv_id}">arXiv:{arxiv_id}</a></dt>'
        f"<dd><div class='meta'><div class='list-title mathjax'>Paper {arxiv_id}</div>"
        f"<p class='mathjax'>From catchup {arxiv_id}.</p></div></dd>"
        for arxiv_id in ids
    )
    return (
        f"<div id='dlpage'><h1>Catchup results for Computer Vision on {on}</h1>"
        f"<dl id='articles'><h3>New submissions (showing {len(ids)} of {total or len(ids)} entries)</h3>"
        f"{entries}</dl></div>"
    )


@pytest.fixture
def store(tmp_path: Path) -> PaperStore:
    return PaperStore(tmp_path / "data")


def _run(fake: FakeArxiv, store: PaperStore, max_html_fetches: int | None = None) -> Listing:
    with fake.client() as site, fake.client() as api:
        update_category(
            "cs.CV",
            store=store,
            site_client=site,
            api_client=api,
            html=HtmlReading(limit=max_html_fetches, save_every=1),
        )
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
    # The HTML also says who is where: the mapping is stored alongside.
    author_affiliations = stored["2609.30249"].author_affiliations
    assert author_affiliations is not None
    assert author_affiliations[0] == (0, 1)  # Yuyao Liu: MIT and NUS
    # 404: nothing to extract; 503: left pending for the next run.
    assert stored["2609.28836"].affiliations == ()
    assert stored["2609.30234"].affiliations is None
    # The version of the extraction is kept with what it gave, not with declared ones.
    assert stored["2609.30249"].extractor == stored["2609.28836"].extractor == EXTRACTOR_VERSION
    assert stored["2609.28466"].extractor is None
    assert stored["2609.30234"].extractor is None
    # Where the affiliations came from, and when; nothing for those not read yet.
    assert stored["2609.30249"].affiliations_provenance == Provenance("html", READ_ON)
    assert stored["2609.28466"].affiliations_provenance == Provenance("api", READ_ON)
    assert stored["2609.30234"].affiliations_provenance is None


def test_a_later_listing_keeps_the_extractor_version(fake: FakeArxiv, store: PaperStore) -> None:
    _run(fake, store)
    stored = {paper.arxiv_id: paper for paper in _run(fake, store).papers}

    assert stored["2609.30249"].extractor == EXTRACTOR_VERSION


def test_update_takes_older_abstracts_from_catchup_pages(fake: FakeArxiv, store: PaperStore) -> None:
    fake.catchup_pages = {"/catchup/cs.CV/2026-09-24": _catchup_page(["2609.28466", "2609.28473"])}

    stored = {paper.arxiv_id: paper for paper in _run(fake, store, max_html_fetches=0).papers}

    # The latest day comes from RSS, the day before from its catchup page: no API call.
    assert stored["2609.30245"].abstract == "From RSS 2609.30245."
    assert stored["2609.28466"].abstract == "From catchup 2609.28466."
    assert fake.hits["/catchup/cs.CV/2026-09-24"] == 1
    assert fake.api_ids == []


def _run_on(day: date, fake: FakeArxiv, store: PaperStore, monkeypatch: pytest.MonkeyPatch) -> UpdateReport:
    monkeypatch.setattr("preprint_radar.collect.today", lambda: day)
    with fake.client() as site, fake.client() as api:
        return update_category(
            "cs.CV", store=store, site_client=site, api_client=api, html=HtmlReading(limit=0)
        )


def test_update_takes_a_weekday_the_listing_lacks_from_its_catchup_page(
    fake: FakeArxiv, store: PaperStore, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # The listing ends on Friday 25 September; Monday's announcement came late, after the
    # page arXiv's cache served was taken. A cross-list of the 24th stays on its day.
    fake.catchup_pages = {
        "/catchup/cs.CV/2026-09-28": _catchup_page(
            ["2609.40001", "2609.40002", "2609.28466"], on="Mon, 28 Sep 2026"
        )
    }

    report = _run_on(date(2026, 9, 28), fake, store, monkeypatch)

    assert [paper.arxiv_id for paper in store.load_day("cs.CV", date(2026, 9, 28))] == [
        "2609.40001",
        "2609.40002",
    ]
    assert "2609.28466" in {paper.arxiv_id for paper in store.load_day("cs.CV", date(2026, 9, 24))}
    assert store.load_day("cs.CV", date(2026, 9, 28))[0].abstract == "From catchup 2609.40001."
    assert report.caught_up == (date(2026, 9, 28), 2)
    assert (report.listed, report.new) == (9, 9)
    assert "the listing lacked 2026-09-28: 2 papers from its catchup page" in format_report(report)
    assert "cs.CV: the listing lacks 2026-09-28: its 2 papers come from its catchup page" in caplog.text


@pytest.mark.parametrize(
    ("day", "page", "asked"),
    [
        pytest.param(date(2026, 9, 25), None, False, id="listed"),
        pytest.param(date(2026, 9, 26), None, False, id="saturday"),
        pytest.param(date(2026, 9, 28), None, True, id="holiday"),
        pytest.param(date(2026, 9, 28), "failing", True, id="failing"),
    ],
)
def test_update_reads_a_catchup_page_only_for_a_weekday_the_listing_lacks(
    fake: FakeArxiv,
    store: PaperStore,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    day: date,
    page: str | None,
    asked: bool,  # noqa: FBT001 - a pytest parameter
) -> None:
    path = f"/catchup/cs.CV/{day.isoformat()}"
    if page == "failing":
        fake.catchup_failing.add(path)

    report = _run_on(day, fake, store, monkeypatch)

    assert fake.hits[path] == asked
    assert report.caught_up is None
    assert report.listed == 7
    assert ("whose catchup page could not be read" in caplog.text) == (page == "failing")


RUN_DAY = date(2026, 10, 15)  # a Thursday


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        pytest.param({}, None, id="empty"),
        pytest.param({date(2026, 10, 14): True}, None, id="up-to-date"),
        # The listing still holds the four weekdays after a Friday.
        pytest.param({date(2026, 10, 9): True}, None, id="listing-covers"),
        pytest.param({date(2026, 10, 8): True}, date(2026, 10, 9), id="outage"),
        pytest.param({date(2026, 8, 3): True}, date(2026, 9, 15), id="outage-bounded"),
        # Papers still pending on a day the listing dropped, within 30 days.
        pytest.param({date(2026, 10, 14): True, date(2026, 10, 1): False}, date(2026, 10, 1), id="pending"),
        pytest.param({date(2026, 10, 14): True, date(2026, 10, 13): False}, None, id="pending-listed"),
        pytest.param({date(2026, 10, 14): True, date(2026, 9, 1): False}, None, id="pending-too-old"),
    ],
)
def test_update_catches_up_on_days_no_listing_holds(
    store: PaperStore, listing: Listing, stored: dict[date, bool], expected: date | None
) -> None:
    base = listing.papers[0]
    store.save(
        "cs.CV",
        [
            replace(
                base,
                arxiv_id=f"2610.{9000 + at}",
                announced=day,
                abstract="An abstract.",
                affiliations=("MIT",) if read else None,
                author_affiliations=None,
                html_url=f"https://arxiv.org/html/2610.{9000 + at}v1",
            )
            for at, (day, read) in enumerate(stored.items())
        ],
    )

    assert catch_up_since(store, "cs.CV", RUN_DAY) == expected


def test_update_falls_back_to_the_api_when_a_catchup_page_fails(
    fake: FakeArxiv, store: PaperStore, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    handle = fake.handle

    def failing_catchup(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503) if request.url.path.startswith("/catchup/") else handle(request)

    monkeypatch.setattr(fake, "handle", failing_catchup)

    stored = {paper.arxiv_id: paper for paper in _run(fake, store, max_html_fetches=0).papers}

    assert "Could not read the cs.CV catchup page of 2026-09-24" in caplog.text
    assert stored["2609.28466"].abstract == "Abstract of 2609.28466."
    assert sorted(fake.api_ids) == ["2609.28466", "2609.28473"]


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
    stored = {paper.arxiv_id: paper for paper in store.iter_papers("cs.CV")}
    assert stored["2609.30249"].author_affiliations is not None  # carried over, not refetched


def _store_with_authors(store: PaperStore, authors: dict[str, tuple[str, ...]]) -> None:
    """Rewrite stored papers as if an earlier version had listed other authors."""
    stored = {paper.arxiv_id: paper for paper in store.iter_papers("cs.CV")}
    store.save("cs.CV", [replace(stored[arxiv_id], authors=names) for arxiv_id, names in authors.items()])


def test_a_changed_author_list_reads_the_html_again(
    fake: FakeArxiv, store: PaperStore, caplog: pytest.LogCaptureFixture
) -> None:
    listed = {paper.arxiv_id: paper for paper in _run(fake, store).papers}
    # The stored mapping is positional: under another author order it would credit the
    # wrong people. 2609.30234 had no affiliations yet (its page failed).
    _store_with_authors(
        store,
        {
            "2609.30249": tuple(reversed(listed["2609.30249"].authors)),
            "2609.30234": tuple(reversed(listed["2609.30234"].authors)),
        },
    )
    fake.hits.clear()
    caplog.set_level("INFO")

    stored = {paper.arxiv_id: paper for paper in _run(fake, store).papers}

    assert fake.hits["/html/2609.30249v1"] == 1
    assert stored["2609.30249"].authors == listed["2609.30249"].authors
    assert stored["2609.30249"].author_affiliations == listed["2609.30249"].author_affiliations
    assert "2609.30249 changed its author list" in caplog.text
    assert "2609.30234 changed its author list" not in caplog.text


def test_a_respelled_author_list_keeps_its_mapping(fake: FakeArxiv, store: PaperStore) -> None:
    listed = {paper.arxiv_id: paper for paper in _run(fake, store).papers}
    authors = listed["2609.30249"].authors
    _store_with_authors(store, {"2609.30249": ("Liu Yuyao", *authors[1:])})
    fake.hits.clear()

    stored = {paper.arxiv_id: paper for paper in _run(fake, store).papers}

    assert fake.hits["/html/2609.30249v1"] == 0
    assert stored["2609.30249"].authors == authors
    assert stored["2609.30249"].author_affiliations == listed["2609.30249"].author_affiliations


def test_a_changed_author_list_without_html_keeps_the_affiliations(
    fake: FakeArxiv, store: PaperStore
) -> None:
    listed = {paper.arxiv_id: paper for paper in _run(fake, store).papers}
    _store_with_authors(store, {"2609.30249": tuple(reversed(listed["2609.30249"].authors))})
    link = '<a href="https://arxiv.org/html/2609.30249v1" title="View HTML"'
    fake.listing_html = fake.listing_html.replace(link, '<a href="#" title="No HTML"')
    fake.hits.clear()

    stored = {paper.arxiv_id: paper for paper in _run(fake, store).papers}

    assert stored["2609.30249"].html_url is None
    assert fake.hits["/html/2609.30249v1"] == 0
    assert stored["2609.30249"].affiliations == listed["2609.30249"].affiliations
    assert stored["2609.30249"].author_affiliations is None


def test_declared_affiliations_reset_the_author_mapping(
    fake: FakeArxiv, store: PaperStore, listing: Listing
) -> None:
    paper = next(paper for paper in listing.papers if paper.arxiv_id == "2609.28466")
    store.save(
        "cs.CV",
        [
            replace(
                paper,
                affiliations=("Scraped Institute",),
                author_affiliations=((0,),) * len(paper.authors),
                institutions=("Scraped Institute",),
            )
        ],
    )

    stored = {paper.arxiv_id: paper for paper in _run(fake, store, max_html_fetches=0).papers}

    assert stored["2609.28466"].affiliations == ("Declared Institute",)
    assert stored["2609.28466"].author_affiliations is None
    assert stored["2609.28466"].institutions is None
    assert stored["2609.28466"].affiliations_provenance == Provenance("api", READ_ON)


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


def _backfill(fake: FakeArxiv, store: PaperStore, max_html_fetches: int | None = None) -> dict[str, Paper]:
    with fake.client() as site:
        backfill_category(
            "cs.CV",
            BACKFILL_DAYS,
            store=store,
            site_client=site,
            html=HtmlReading(limit=max_html_fetches, save_every=1),
        )
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


def test_backfill_goes_on_past_the_days_it_cannot_read(
    fake_catchup: FakeArxiv, store: PaperStore, caplog: pytest.LogCaptureFixture
) -> None:
    # 2026-09-02 fails; 2026-08-31 lists one of the two entries it announces.
    fake_catchup.catchup_failing = {"/catchup/cs.CV/2026-09-02"}
    incomplete = _catchup_page(["2608.20001"], on="Mon, 31 Aug 2026", total=2)
    fake_catchup.catchup_pages["/catchup/cs.CV/2026-08-31"] = incomplete

    with fake_catchup.client() as site:
        report = backfill_category(
            "cs.CV", BACKFILL_DAYS, store=store, site_client=site, html=HtmlReading(save_every=1)
        )

    # Neither is saved, and the day between them is read, its pages too.
    assert store.days("cs.CV") == [date(2026, 9, 1)]
    stored = {paper.arxiv_id: paper for paper in store.iter_papers("cs.CV")}
    assert "NVIDIA" in (stored["2608.28663"].affiliations or ())
    assert report.failed_days == (date(2026, 9, 2), date(2026, 8, 31))
    assert report.failed
    assert not report.html_failed
    assert format_report(report).endswith("; days not read: 2026-09-02, 2026-08-31")
    assert (
        "cs.CV 2026-09-02: the catchup page could not be read (HTTP 503 for "
        "https://arxiv.org/catchup/cs.CV/2026-09-02?abs=True); the day is left for the next run"
    ) in caplog.text
    assert "cs.CV 2026-08-31: the catchup page lists 1 of 2 entries; the day is left for the next run" in (
        caplog.text
    )

    # The next run fetches them again, and only them.
    fake_catchup.catchup_failing = set()
    fake_catchup.catchup_pages["/catchup/cs.CV/2026-08-31"] = _catchup_page(
        ["2608.20001", "2608.20002"], on="Mon, 31 Aug 2026"
    )
    fake_catchup.hits.clear()
    with fake_catchup.client() as site:
        report = backfill_category(
            "cs.CV", BACKFILL_DAYS, store=store, site_client=site, html=HtmlReading(limit=0)
        )

    assert [path for path in fake_catchup.hits if path.startswith("/catchup/")] == [
        "/catchup/cs.CV/2026-09-02",
        "/catchup/cs.CV/2026-08-31",
    ]
    assert store.days("cs.CV") == [date(2026, 9, 1), date(2026, 8, 31)]
    assert report.failed_days == ()
    assert not report.failed


def test_backfill_goes_on_past_a_catchup_page_it_cannot_parse(
    fake_catchup: FakeArxiv, store: PaperStore
) -> None:
    fake_catchup.catchup_pages["/catchup/cs.CV/2026-09-02"] = "<html>Not a catchup page</html>"

    with fake_catchup.client() as site:
        report = backfill_category("cs.CV", BACKFILL_DAYS, store=store, site_client=site)

    assert report.failed_days == (date(2026, 9, 2),)
    assert store.days("cs.CV") == [date(2026, 9, 1)]


def test_backfill_stops_asking_after_days_in_a_row_it_cannot_read(
    fake_catchup: FakeArxiv, store: PaperStore, caplog: pytest.LogCaptureFixture
) -> None:
    days = [date(2026, 8, 24) + timedelta(days=offset) for offset in range(10)]
    fake_catchup.catchup_failing = {f"/catchup/cs.CV/{day.isoformat()}" for day in days}

    with fake_catchup.client() as site:
        report = backfill_category("cs.CV", days, store=store, site_client=site, html=HtmlReading(limit=0))

    # arxiv.org is down: three days are tried, the seven others left for the next run.
    asked = {path for path in fake_catchup.hits if path.startswith("/catchup/")}
    assert len(asked) == MAX_CONSECUTIVE_DAY_FAILURES
    assert report.failed_days == tuple(sorted(days, reverse=True))
    assert "cs.CV: 3 catchup pages in a row could not be read; the other days are not asked for" in (
        caplog.text
    )


def test_backfill_asks_for_no_day_past_its_deadline(
    fake_catchup: FakeArxiv, store: PaperStore, caplog: pytest.LogCaptureFixture
) -> None:
    with fake_catchup.client() as site:
        report = backfill_category(
            "cs.CV", BACKFILL_DAYS, store=store, site_client=site, html=HtmlReading(deadline=0.0)
        )

    # Out of time, as for pages: the days wait for the next run, and the run is not red.
    assert not [path for path in fake_catchup.hits if path.startswith("/catchup/")]
    assert report.failed_days == ()
    assert report.stopped is Stop.DEADLINE
    assert not report.failed
    assert "Out of time: 3 days left for the next run" in caplog.text


def _paper(arxiv_id: str, affiliations: tuple[str, ...] | None) -> Paper:
    return Paper(
        arxiv_id=arxiv_id, announced=date(2026, 9, 25), title="T", authors=("A",), affiliations=affiliations
    )


def test_add_institutions_names_each_distinct_affiliation_once(fake: FakeArxiv) -> None:
    papers = [
        _paper("1", ("School of CS, Peking University", "Meta AI")),
        _paper("2", ("School of CS, Peking University",)),
        _paper("3", ()),
        _paper("4", None),
    ]

    with fake.client() as ror:
        named = add_institutions(papers, ror, limit=None)

    assert fake.ror_requests == ["School of CS, Peking University", "Meta AI"]
    # ROR names Peking University; the rules name the rest ("Meta AI" is the company).
    assert [paper.institutions for paper in named] == [
        ("Peking University", "Meta"),
        ("Peking University",),
        None,
        None,
    ]


def test_add_institutions_keeps_ror_ids(fake: FakeArxiv) -> None:
    papers = [
        _paper("1", ("School of CS, Peking University", "Meta AI")),
        # Named already, by ROR or the rules: nothing to ask for.
        replace(_paper("2", ("Lab",)), institutions=(None,)),
    ]

    with fake.client() as ror:
        named = add_institutions(papers, ror, limit=None)

    peking_id = named[0].institution_ids[0] if named[0].institution_ids else None
    assert peking_id
    # Only what ROR named has an id: "Meta" is the rules'.
    assert [paper.institution_ids for paper in named] == [(peking_id, None), None]
    assert named[0].institutions_provenance == Provenance("ror", READ_ON)
    assert fake.ror_requests == ["School of CS, Peking University", "Meta AI"]
    fake.ror_requests.clear()
    with fake.client() as ror:
        assert add_institutions(named, ror, limit=None) == named
    assert fake.ror_requests == []


def test_add_institutions_asks_ror_only_for_strings_it_never_answered(fake: FakeArxiv) -> None:
    with fake.client() as ror:
        earlier = add_institutions(
            [_paper("1", ("School of CS, Peking University", "Meta AI"))], ror, limit=None
        )
    fake.ror_requests.clear()
    papers = [_paper("2", ("School of CS, Peking University", "Meta AI", "Tencent ARC Lab"))]

    with fake.client() as ror:
        named = add_institutions(papers, ror, limit=None, known=ror_answers(earlier))

    # ROR's match and the rules' name come back as they were, the new string is asked (AFF-17).
    assert fake.ror_requests == ["Tencent ARC Lab"]
    assert named[0].institutions == ("Peking University", "Meta", "Tencent")
    peking_id = earlier[0].institution_ids[0] if earlier[0].institution_ids else None
    assert peking_id
    assert named[0].institution_ids == (peking_id, None, None)
    fake.ror_requests.clear()
    with fake.client() as ror:
        add_institutions(papers, ror, limit=None, known=ror_answers([*earlier, *named]))
    assert fake.ror_requests == []


def test_ror_answers_are_its_own_and_its_latest() -> None:
    def named(day: date, institution: str | None, ror_id: str | None, source: str = "ror") -> Paper:
        return replace(
            _paper(str(day.day), ("Lab of Things",)),
            institutions=(institution,),
            institution_ids=(ror_id,),
            institutions_provenance=Provenance(source, day),
        )

    assert ror_answers(
        [named(date(2026, 10, 1), "Old Name", "0abc"), named(date(2026, 10, 5), "New Name", "0abc")]
    ) == {"Lab of Things": Institution("New Name", "0abc")}
    # Whichever comes first.
    assert ror_answers(
        [named(date(2026, 10, 5), "New Name", "0abc"), named(date(2026, 10, 1), "Old Name", "0abc")]
    ) == {"Lab of Things": Institution("New Name", "0abc")}
    # The rules named it after ROR matched nothing: no institution to give.
    assert ror_answers([named(date(2026, 10, 1), "Lab of Things", None)]) == {"Lab of Things": None}
    # OpenAlex's names, and names without their ids, are not ROR's answers.
    assert ror_answers([named(date(2026, 10, 1), "Lab", "0abc", source="openalex")]) == {}
    assert ror_answers([replace(named(date(2026, 10, 1), "Lab", "0abc"), institution_ids=None)]) == {}


def test_add_institutions_leaves_the_rest_for_next_run(fake: FakeArxiv) -> None:
    papers = [_paper("1", ("Meta AI",)), _paper("2", ("Meta AI", "School of CS, Peking University"))]

    with fake.client() as ror:
        named = add_institutions(papers, ror, limit=1)

    # The second paper needs a string beyond the limit: none of its institutions is set.
    assert [paper.institutions for paper in named] == [("Meta",), None]


def test_update_names_institutions_and_keeps_them(fake: FakeArxiv, store: PaperStore) -> None:
    with fake.client() as site, fake.client() as api, fake.client() as ror:
        update_category("cs.CV", store=store, site_client=site, api_client=api, ror_client=ror)
    fake.ror_requests.clear()
    with fake.client() as site, fake.client() as api, fake.client() as ror:
        update_category("cs.CV", store=store, site_client=site, api_client=api, ror_client=ror)

    stored = {paper.arxiv_id: paper for paper in store.iter_papers("cs.CV")}
    paper = stored["2609.30249"]
    assert paper.institutions is not None
    assert len(paper.institutions) == len(paper.affiliations or ())
    # Carried over: only the retried page (2609.30234, 503 then 404) could need a lookup.
    assert all(request not in (paper.affiliations or ()) for request in fake.ror_requests)


class FakeSemanticScholar:
    """Answer batch requests from fixed counts; ``None`` for unknown papers, or refuse all."""

    def __init__(self, counts: dict[str, int | None], *, down: bool = False) -> None:
        self.counts = counts
        self.down = down
        self.asked: list[str] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            return httpx.Response(503)
        ids = [paper_id.removeprefix("ARXIV:") for paper_id in json.loads(request.content)["ids"]]
        self.asked += ids
        return httpx.Response(200, json=[{"citationCount": self.counts.get(i)} for i in ids])

    def client(self) -> HttpClient:
        return HttpClient(transport=httpx.MockTransport(self.handle), max_attempts=1)


@pytest.fixture
def cited_store(store: PaperStore) -> PaperStore:
    papers = [_paper(arxiv_id, None) for arxiv_id in ("2609.00001", "2609.00002", "2609.00003")]
    store.save("cs.CV", papers)
    store.write_archive("cs.CV", [replace(_paper("1512.03385", None), announced=date(2015, 12, 10))])
    store.write_citations("cs.CV", {"2609.00001": 5, "1512.03385": 200_000}, source="Semantic Scholar")
    return store


def test_update_citation_counts_asks_only_for_papers_without_one(cited_store: PaperStore) -> None:
    before = cited_store.load_citation_counts("cs.CV")
    fake = FakeSemanticScholar({"2609.00002": 0, "2609.00003": None})  # not known yet

    with fake.client() as client:
        report = update_citation_counts(cited_store, "cs.CV", client, key=None)

    assert fake.asked == ["2609.00002", "2609.00003"]
    assert report == CitationsReport(category="cs.CV", asked=2, found=1)
    after = cited_store.load_citation_counts("cs.CV")
    assert after is not None
    assert before is not None
    assert after.counts == {"2609.00001": 5, "2609.00002": 0, "1512.03385": 200_000}
    assert after.generated_at == before.generated_at
    assert (
        format_citations_report(report) == "cs.CV: citation counts for 1 of 2 papers, 1 left for the next run"
    )


def test_update_citation_counts_refreshes_every_stored_paper(cited_store: PaperStore) -> None:
    counts = {"2609.00001": 7, "2609.00002": 1, "2609.00003": 0, "1512.03385": 250_000}
    fake = FakeSemanticScholar(dict(counts))

    with fake.client() as client:
        report = update_citation_counts(cited_store, "cs.CV", client, key=None, refresh=True)

    assert sorted(fake.asked) == sorted(counts)
    assert cited_store.load_citations("cs.CV") == counts
    assert format_citations_report(report) == "cs.CV: citation counts for 4 of 4 papers"


def test_update_citation_counts_asks_for_the_most_cited_papers_of_the_last_12_months(
    cited_store: PaperStore,
) -> None:
    young = replace(_paper("2511.00001", None), announced=date(2025, 11, 3))
    cited_store.write_top_recent("cs.CV", [young], since=date(2025, 10, 1))
    fake = FakeSemanticScholar({"2511.00001": 40})

    with fake.client() as client:
        update_citation_counts(cited_store, "cs.CV", client, key=None)

    assert "2511.00001" in fake.asked
    assert cited_store.load_citations("cs.CV")["2511.00001"] == 40


def test_a_failing_refresh_keeps_the_counts(cited_store: PaperStore, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("preprint_radar.sources.semantic_scholar.S2_ANONYMOUS_RETRY_WAIT_SECONDS", 0)
    before = cited_store.load_citation_counts("cs.CV")

    with FakeSemanticScholar({}, down=True).client() as client:
        report = update_citation_counts(cited_store, "cs.CV", client, key=None, refresh=True)

    assert report.found == 0
    assert cited_store.load_citation_counts("cs.CV") == before


def test_nothing_to_ask_for(cited_store: PaperStore) -> None:
    cited_store.merge_citations("cs.CV", {"2609.00002": 0, "2609.00003": 1}, source="Semantic Scholar")
    fake = FakeSemanticScholar({})

    with fake.client() as client:
        report = update_citation_counts(cited_store, "cs.CV", client, key=None)

    assert fake.asked == []
    assert report.asked == 0


TODAY = date(2026, 10, 8)
TSINGHUA = {
    "doi": "https://doi.org/10.48550/arxiv.2609.00001",
    "authorships": [
        {
            "author_position": "first",
            "raw_author_name": "A",
            "institutions": [
                {
                    "id": "https://openalex.org/I99065089",
                    "display_name": "Tsinghua University",
                    "ror": "https://ror.org/03cve4549",
                    "type": "education",
                }
            ],
        }
    ],
}


def _without_page(arxiv_id: str, affiliations: tuple[str, ...] | None, looked_up: int | None = None) -> Paper:
    """A paper of the day files arXiv has no HTML rendering of, OpenAlex asked ``looked_up`` days ago."""
    return replace(
        _paper(arxiv_id, affiliations),
        affiliations_provenance=None
        if looked_up is None
        else Provenance("openalex", TODAY - timedelta(days=looked_up)),
    )


def test_openalex_gives_the_affiliations_of_papers_without_an_html_page(store: PaperStore) -> None:
    store.save(
        "cs.CV",
        [
            _without_page("2609.00001", None),
            _without_page("2609.00002", (), looked_up=40),  # nothing a month ago: asked again
            _without_page("2609.00003", (), looked_up=10),  # nothing ten days ago: not yet
            replace(_paper("2609.00004", None), html_url="https://arxiv.org/html/2609.00004v1"),  # its page
            replace(_paper("2609.00005", ("Read from the API",)), affiliations_provenance=Provenance("api")),
        ],
    )
    asked: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.params.get("filter") or request.url.path)
        if request.url.path == "/works":
            return httpx.Response(200, json={"results": [TSINGHUA]})
        return httpx.Response(404)  # the one-by-one lookup of a paper it does not know

    with HttpClient(transport=httpx.MockTransport(handle), max_attempts=1) as client:
        report = update_openalex_affiliations(store, "cs.CV", client, today=TODAY)

    assert asked[0] == "doi:10.48550/arxiv.2609.00001|10.48550/arxiv.2609.00002"
    assert report == OpenAlexReport(category="cs.CV", asked=2, found=1)
    assert format_openalex_report(report) == (
        "cs.CV: OpenAlex gave affiliations for 1 of 2 papers without an HTML page"
    )
    papers = {paper.arxiv_id: paper for paper in store.iter_papers("cs.CV")}
    found = papers["2609.00001"]
    assert (found.affiliations, found.institutions, found.institution_ids) == (
        ("Tsinghua University",),
        ("Tsinghua University",),
        ("03cve4549",),
    )
    assert found.author_affiliations == ((0,),)
    assert found.affiliations_provenance == found.institutions_provenance == Provenance("openalex", TODAY)
    assert found.affiliations_from_openalex
    # Nothing yet: asked again in 30 days.
    assert papers["2609.00002"].affiliations == ()
    assert papers["2609.00002"].affiliations_provenance == Provenance("openalex", TODAY)
    assert papers["2609.00003"].affiliations_provenance == Provenance("openalex", TODAY - timedelta(days=10))
    assert papers["2609.00004"].affiliations is None
    assert papers["2609.00005"].affiliations == ("Read from the API",)


def test_a_failing_openalex_leaves_the_papers_for_the_next_run(store: PaperStore) -> None:
    store.save("cs.CV", [_without_page("2609.00001", None)])

    with HttpClient(transport=httpx.MockTransport(lambda _: httpx.Response(503)), max_attempts=1) as client:
        report = update_openalex_affiliations(store, "cs.CV", client, today=TODAY)

    assert report == OpenAlexReport(category="cs.CV", asked=1, found=0)
    assert next(store.iter_papers("cs.CV")).affiliations is None


LOVELACE_TURING = ("Ada Lovelace", "Alan Turing")
GOOGLE_ETH = [
    {
        "author": {"display_name": "Ada Lovelace"},
        "institutions": [
            {"display_name": "Google (United States)", "ror": "https://ror.org/00njsd438", "type": "company"}
        ],
    },
    {
        "author": {"display_name": "Alan M. Turing"},
        "institutions": [{"display_name": "ETH Zurich", "ror": "https://ror.org/05a28rw58"}],
    },
]


def _archived(
    arxiv_id: str, affiliations: tuple[str, ...] = (), authors: tuple[str, ...] = LOVELACE_TURING
) -> Paper:
    """A paper built from the catalog, which OpenAlex gave ``affiliations`` by its arXiv DOI."""
    return Paper(
        arxiv_id=arxiv_id,
        announced=date(2000 + int(arxiv_id[:2]), int(arxiv_id[2:4]), 3),
        title="T",
        authors=authors,
        affiliations=affiliations,
        affiliations_provenance=Provenance("openalex", date(2026, 10, 4)),
    )


def test_archive_affiliations_from_the_published_versions(store: PaperStore) -> None:
    store.write_archive(
        "cs.CV",
        [
            _archived("2503.00001"),
            _archived("2503.00002"),  # arXiv's DOI only
            _archived("2503.00003", ("MIT",)),  # has some
            _archived("2503.00004"),  # its DOI is another paper's
            _archived("1703.00005"),  # no published version
        ],
    )
    in_day = replace(_paper("2609.00010", ()), html_url="https://arxiv.org/html/2609.00010v1")
    store.save("cs.CV", [in_day])
    store.write_top_recent("cs.CV", [in_day, _archived("2601.00011")], since=date(2025, 10, 9))
    dois = {
        "2503.00001": "10.1109/CVPR.2025.1",
        "2503.00002": "10.48550/arXiv.2503.00002",
        "2503.00003": "10.1/c",
        "2503.00004": "10.1/d",
        "2601.00011": "10.1/e",
        "2609.00010": "10.1/f",  # its day record: the daily update's
    }
    store.write_scholar("cs.CV", {key: ScholarRecord(doi=doi) for key, doi in dois.items()}, source="S2")
    works = [
        {"doi": "https://doi.org/10.1109/cvpr.2025.1", "authorships": GOOGLE_ETH},
        {"doi": "https://doi.org/10.1/d", "authorships": [{"author": {"display_name": "Someone Else"}}]},
        {"doi": "https://doi.org/10.1/e", "authorships": GOOGLE_ETH[:1]},
    ]
    asked: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.params["filter"])
        return httpx.Response(200, json={"results": works})

    with HttpClient(transport=httpx.MockTransport(handle), max_attempts=1) as client:
        report = update_archive_affiliations(store, "cs.CV", openalex_client=client, today=TODAY)

    assert asked == ["doi:10.1/d|10.1/e|10.1109/cvpr.2025.1"]
    assert report == ArchiveAffiliationsReport(category="cs.CV", without=5, from_published=2)
    assert format_archive_affiliations_report(report) == (
        "cs.CV: 2 of 5 highly cited papers without affiliations got some, "
        "2 from OpenAlex's published versions"
    )
    archived = {paper.arxiv_id: paper for paper in store.iter_archive("cs.CV")}
    found = archived["2503.00001"]
    assert (found.affiliations, found.institutions, found.institution_ids) == (
        ("Google", "ETH Zurich"),
        ("Google", "ETH Zurich"),
        ("00njsd438", "05a28rw58"),
    )
    assert found.author_affiliations == ((0,), (1,))
    assert found.affiliations_provenance == found.institutions_provenance == Provenance("openalex", TODAY)
    for unchanged in ("2503.00002", "2503.00003", "2503.00004", "1703.00005"):
        assert archived[unchanged] == _archived(unchanged, archived[unchanged].affiliations or ())
    top = store.load_top_recent("cs.CV")
    assert top is not None
    assert top.since == date(2025, 10, 9)
    recent = {paper.arxiv_id: paper for paper in top.papers}
    assert recent["2609.00010"] == in_day
    # Only Ada Lovelace is in the published version: Alan Turing is placed nowhere.
    assert recent["2601.00011"].affiliations == ("Google",)
    assert recent["2601.00011"].author_affiliations == ((0,), None)


def test_archive_affiliations_from_the_html_pages(
    store: PaperStore, tmp_path: Path, paper_html: Callable[[str], str]
) -> None:
    authors = ("Yuyao Liu", "Jiayuan Mao", "David Hsu", "Leslie Pack Kaelbling", "Tomás Lozano-Pérez")
    store.write_archive(
        "cs.CV",
        [
            _archived("2501.00001", authors=authors),
            _archived("2501.00002"),  # no rendering
            _archived("2205.00003"),  # before arXiv rendered any
            _archived("2501.00004"),  # arxiv.org fails
        ],
    )
    store.write_citations("cs.CV", {"2501.00001": 5, "2501.00002": 50}, source="S2")
    requests: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.host + request.url.path)
        if request.url.host == "api.ror.org":
            return httpx.Response(200, text=(FIXTURES_DIR / "ror" / "meta.json").read_text(encoding="utf-8"))
        if request.url.path == "/html/2501.00001v1":
            return httpx.Response(200, text=paper_html("2609.30249"))
        if request.url.path == "/html/2501.00004v1":
            return httpx.Response(503)
        return httpx.Response(404)

    reading = HtmlReading(limit=10, save_every=1, cache=PageCache(tmp_path / "pages"))

    def run() -> ArchiveAffiliationsReport:
        with HttpClient(transport=httpx.MockTransport(handle), max_attempts=1) as client:
            return update_archive_affiliations(
                store,
                "cs.CV",
                openalex_client=client,
                today=TODAY,
                site_client=client,
                html=reading,
                ror=Ror(client, None),
            )

    report = run()

    # The most cited first; nothing asked of OpenAlex without a published version.
    assert [path for path in requests if path.startswith("arxiv.org")] == [
        "arxiv.org/html/2501.00002v1",
        "arxiv.org/html/2501.00001v1",
        "arxiv.org/html/2501.00004v1",
    ]
    assert report == ArchiveAffiliationsReport(
        category="cs.CV", without=4, from_published=0, pages=2, from_pages=1, unreadable=1
    )
    assert format_archive_affiliations_report(report) == (
        "cs.CV: 1 of 4 highly cited papers without affiliations got some, "
        "0 from OpenAlex's published versions, 1 from 2 HTML pages (1 unreadable)"
    )
    archived = {paper.arxiv_id: paper for paper in store.iter_archive("cs.CV")}
    read = archived["2501.00001"]
    expected = json.loads((FIXTURES_DIR / "html" / "expected.json").read_text(encoding="utf-8"))["2609.30249"]
    assert read.affiliations == tuple(expected["affiliations"])
    assert read.html_url == "https://arxiv.org/html/2501.00001v1"
    assert read.extractor == EXTRACTOR_VERSION
    assert read.affiliations_provenance == Provenance("html", READ_ON)
    assert read.institutions is not None
    assert read.institutions_provenance == Provenance("ror", READ_ON)
    for unchanged in ("2501.00002", "2205.00003", "2501.00004"):
        assert archived[unchanged] == _archived(unchanged)

    # Again: the page that does not exist is not asked for, the one read has affiliations.
    requests.clear()
    assert run().without == 3
    assert requests == ["arxiv.org/html/2501.00004v1"]


def test_archive_affiliations_read_no_cached_page_again_that_gave_none(
    store: PaperStore, tmp_path: Path, paper_html: Callable[[str], str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    # A run before read their pages: read first again, they stopped the next as a layout change.
    read = [_archived(f"2501.{index:05d}", authors=("Yuyao Liu",)) for index in range(DRIFT_MIN_PAGES)]
    authors = ("Yuyao Liu", "Jiayuan Mao", "David Hsu", "Leslie Pack Kaelbling", "Tomás Lozano-Pérez")
    # Kept before the cache kept the tables of author blocks: read again.
    stale = _archived("2501.99999", authors=("Yuyao Liu",))
    store.write_archive("cs.CV", [*read, stale, _archived("2502.00001", authors=authors)])
    cache = PageCache(tmp_path / "pages")
    for paper in read:
        cache.put(f"https://arxiv.org/html/{paper.arxiv_id}v1", NO_AFFILIATION_PAGE)
    stale_page = tmp_path / "pages" / "2501" / "2501.99999v1.html.gz"
    stale_page.write_bytes(gzip.compress(NO_AFFILIATION_PAGE.encode()))
    requests: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        return httpx.Response(200, text=paper_html("2609.30249"))

    with HttpClient(transport=httpx.MockTransport(handle), max_attempts=1) as client:
        report = update_archive_affiliations(
            store,
            "cs.CV",
            openalex_client=client,
            today=TODAY,
            site_client=client,
            html=HtmlReading(limit=10, cache=cache),
        )

    assert requests == ["/html/2502.00001v1"]
    assert report == ArchiveAffiliationsReport(
        category="cs.CV", without=DRIFT_MIN_PAGES + 2, from_published=0, pages=2, from_pages=1
    )
    assert f"{DRIFT_MIN_PAGES} cached HTML renderings gave no affiliation: not read again" in caplog.text
    archived = {paper.arxiv_id: paper for paper in store.iter_archive("cs.CV")}
    assert archived["2502.00001"].affiliations
    assert archived["2501.99999"] == stale
    assert all(f"https://arxiv.org/html/{paper.arxiv_id}v1" in cache for paper in read)


def test_archive_affiliations_without_an_archive(store: PaperStore) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise AssertionError(request.url)

    with HttpClient(transport=httpx.MockTransport(handle), max_attempts=1) as client:
        report = update_archive_affiliations(
            store,
            "cs.CV",
            openalex_client=client,
            today=TODAY,
            site_client=client,
            html=HtmlReading(limit=10),
            ror=Ror(client, None),
        )

    assert report == ArchiveAffiliationsReport(category="cs.CV", without=0, from_published=0)
    assert not store.root.exists()


def test_format_archive_affiliations_report_says_why_the_pages_stopped() -> None:
    report = ArchiveAffiliationsReport(
        category="cs.CV", without=900, from_published=0, pages=40, stopped=Stop.LAYOUT
    )

    assert report.failed
    assert not replace(report, stopped=Stop.DEADLINE).failed
    assert format_archive_affiliations_report(report) == (
        "cs.CV: 0 of 900 highly cited papers without affiliations got some, 0 from OpenAlex's "
        "published versions, 0 from 40 HTML pages; stopped: nearly every page gave no affiliation"
    )


def _linking(arxiv_id: str, abstract: str, announced: date = date(2026, 9, 25)) -> Paper:
    return Paper(arxiv_id=arxiv_id, announced=announced, title="T", authors=("A",), abstract=abstract)


def test_the_stars_of_the_code_stored_papers_link(store: PaperStore) -> None:
    store.save(
        "cs.CV",
        [
            _linking("2609.00001", "Code: https://github.com/Lab/Fast-Net."),
            _linking("2609.00002", "Code: https://github.com/lab/zoo/tree/main/projects/x"),  # a folder
            _linking("2609.00003", "Code: https://github.com/lab/gone"),  # deleted
            _linking("2609.00004", "Code: https://github.com/lab/flaky"),  # gone too, its record with it
            _linking("2609.00005", "Weights: https://huggingface.co/lab/model"),
            _linking("2609.00006", "Code: https://gitlab.com/lab/net"),  # not asked
            _linking("2609.00007", "See https://huggingface.co/collections/lab/all"),  # not asked
            _linking("2609.00008", "No code."),
        ],
    )
    store.write_archive(
        "cs.CV", [_linking("2001.00009", "Code: https://github.com/lab/fast-net", date(2020, 1, 3))]
    )
    # A day file's paper among the last 12 months is counted once.
    store.write_top_recent(
        "cs.CV", [_linking("2609.00001", "Code: https://github.com/Lab/Fast-Net.")], since=date(2025, 10, 9)
    )
    flaky = CodeRecord("https://github.com/lab/flaky", stars=5)
    store.write_code(
        "cs.CV",
        {"2609.00004": flaky, "2609.00003": CodeRecord("https://github.com/lab/gone", stars=9)},
        source="GitHub",
    )
    queries: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.host == "huggingface.co":
            return httpx.Response(200, json={"likes": 12})
        query = json.loads(request.content)["query"]
        queries.append(query)
        # Sorted: lab/fast-net, lab/flaky, lab/gone, lab/zoo.
        assert (
            query.index('"fast-net"') < query.index('"flaky"') < query.index('"gone"') < query.index('"zoo"')
        )
        data = {
            "repo0": {"stargazerCount": 300},
            "repo1": None,
            "repo2": None,
            "repo3": {"stargazerCount": 9000},
        }
        errors = [
            {"type": "NOT_FOUND", "path": ["repo2"]},
            {"type": "NOT_FOUND", "path": ["repo1"]},
        ]
        return httpx.Response(200, json={"data": data, "errors": errors})

    with HttpClient(transport=httpx.MockTransport(handle), max_attempts=1) as client:
        report = update_code_records(store, "cs.CV", github=client, token="test-token", hub=client)

    assert len(queries) == 1
    code = store.load_code("cs.CV")
    assert code is not None
    assert code.papers == {
        # Two stored papers link it: its stars are not theirs alone.
        "2609.00001": CodeRecord("https://github.com/Lab/Fast-Net", stars=300, shared=True),
        "2001.00009": CodeRecord("https://github.com/lab/fast-net", stars=300, shared=True),
        "2609.00002": CodeRecord("https://github.com/lab/zoo/tree/main/projects/x", stars=9000, shared=True),
        "2609.00005": CodeRecord("https://huggingface.co/lab/model", likes=12),
    }
    assert report == CodeReport(
        category="cs.CV", linked=8, asked=6, stars=3, shared=3, likes=1, gone=2, kept=0
    )
    assert format_code_report(report) == (
        "cs.CV: 8 papers link their code, 6 asked: 3 with GitHub stars (3 shared), 1 with Hugging "
        "Face likes; 2 gone, 0 kept from last week"
    )


def test_the_daily_run_asks_only_for_the_papers_without_stars(store: PaperStore) -> None:
    refreshed = datetime(2026, 10, 4, 5, 41, tzinfo=UTC)
    store.save(
        "cs.CV",
        [
            _linking("2609.00001", "Code: https://github.com/lab/fast-net"),
            _linking("2609.00002", "Weights: https://huggingface.co/lab/model"),
            _linking("2609.00003", "Code: https://github.com/lab/moved"),  # its link changed
            _linking("2609.00004", "Code: https://github.com/lab/later"),  # not public yet
            _linking("2610.00005", "Code: https://github.com/lab/fast-net", date(2026, 10, 6)),
            _linking("2610.00006", "Code: https://github.com/lab/new-net", date(2026, 10, 6)),
            _linking("2610.00007", "Code: https://gitlab.com/lab/net", date(2026, 10, 6)),
        ],
    )
    fast = CodeRecord("https://github.com/lab/fast-net", stars=300, gained=12)
    model = CodeRecord("https://huggingface.co/lab/model", likes=7)
    old = CodeRecord("https://github.com/lab/old", stars=1)
    # Two weekly refreshes: the stars gained in the week between.
    for now, stars in ((refreshed - timedelta(days=7), 288), (refreshed, 300)):
        store.write_code(
            "cs.CV",
            {"2609.00001": replace(fast, stars=stars, gained=None), "2609.00002": model, "2609.00003": old},
            source="GitHub, Hugging Face",
            now=now,
        )
    before = store.load_code("cs.CV")
    assert before is not None
    asked: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.github.com"  # the Hub's page has its likes
        query = json.loads(request.content)["query"]
        names = re.findall(r'name: "([^"]+)"', query)
        asked.extend(names)
        stars = {"fast-net": 310, "moved": 40, "new-net": 2}
        data = {
            f"repo{index}": {"stargazerCount": stars[name]} if name in stars else None
            for index, name in enumerate(names)
        }
        errors = [{"type": "NOT_FOUND", "path": [f"repo{names.index('later')}"]}]
        return httpx.Response(200, json={"data": data, "errors": errors})

    with HttpClient(transport=httpx.MockTransport(handle), max_attempts=1) as client:
        report = update_code_records(
            store, "cs.CV", github=client, token="test-token", hub=client, new_only=True
        )

    assert sorted(asked) == ["fast-net", "later", "moved", "new-net"]
    code = store.load_code("cs.CV")
    assert code is not None
    # Dated by the weekly refresh still, which the next one counts the week's gains from.
    assert (code.generated_at, code.since) == (before.generated_at, before.since)
    assert code.papers == {
        # A new paper links it too: its stars are no longer its own alone.
        "2609.00001": replace(fast, shared=True),
        "2609.00002": model,
        "2609.00003": CodeRecord("https://github.com/lab/moved", stars=40),
        "2610.00005": CodeRecord("https://github.com/lab/fast-net", stars=310, shared=True),
        "2610.00006": CodeRecord("https://github.com/lab/new-net", stars=2),
    }
    assert report == CodeReport(
        category="cs.CV", linked=7, asked=4, stars=4, shared=2, likes=1, gone=1, kept=0
    )


def test_the_daily_run_without_a_code_file_asks_for_every_paper(store: PaperStore) -> None:
    store.save("cs.CV", [_linking("2609.00001", "Code: https://github.com/lab/fast-net")])
    answer = {"data": {"repo0": {"stargazerCount": 5}}}
    now = datetime(2026, 10, 6, 10, 17, tzinfo=UTC)

    with HttpClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=answer)), max_attempts=1
    ) as client:
        report = update_code_records(
            store, "cs.CV", github=client, token="test-token", hub=client, new_only=True, now=now
        )

    assert report.asked == 1
    code = store.load_code("cs.CV")
    assert code is not None
    assert code.generated_at == now
    assert code.papers == {"2609.00001": CodeRecord("https://github.com/lab/fast-net", stars=5)}


def test_a_failed_star_lookup_keeps_last_weeks(store: PaperStore) -> None:
    store.save("cs.CV", [_linking("2609.00004", "Code: https://github.com/lab/flaky")])
    flaky = CodeRecord("https://github.com/lab/flaky", stars=5)
    store.write_code("cs.CV", {"2609.00004": flaky}, source="GitHub")

    with HttpClient(transport=httpx.MockTransport(lambda _: httpx.Response(502)), max_attempts=1) as client:
        report = update_code_records(store, "cs.CV", github=client, token="test-token", hub=client)

    assert report.kept == 1
    code = store.load_code("cs.CV")
    assert code is not None
    assert code.papers == {"2609.00004": flaky}


def test_a_broken_code_file_keeps_nothing(store: PaperStore, caplog: pytest.LogCaptureFixture) -> None:
    store.save("cs.CV", [_linking("2609.00004", "Code: https://github.com/lab/flaky")])
    (store.root / "cs.CV" / "code.json").write_text("{not json", encoding="utf-8")

    with HttpClient(transport=httpx.MockTransport(lambda _: httpx.Response(502)), max_attempts=1) as client:
        report = update_code_records(store, "cs.CV", github=client, token="test-token", hub=client)

    assert report.kept == 0
    assert "Last week's code.json does not load" in caplog.text


def test_a_code_file_of_another_schema_version_stops_the_stars(store: PaperStore) -> None:
    store.save("cs.CV", [_linking("2609.00004", "Code: https://github.com/lab/flaky")])
    (store.root / "cs.CV" / "code.json").write_text('{"schema_version": 99, "papers": {}}', encoding="utf-8")

    with (
        HttpClient(transport=httpx.MockTransport(lambda _: httpx.Response(502)), max_attempts=1) as client,
        pytest.raises(SchemaVersionError),
    ):
        update_code_records(store, "cs.CV", github=client, token="test-token", hub=client)


def test_update_writes_the_index_before_reading_html_pages(
    fake: FakeArxiv, store: PaperStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def stopped(*_: object, **__: object) -> None:
        # A run killed while reading pages: the days saved so far are in the index.
        index = json.loads((store.root / "index.json").read_text(encoding="utf-8"))
        assert [day["count"] for day in index["categories"]["cs.CV"]] == [5, 2]
        raise KeyboardInterrupt

    monkeypatch.setattr("preprint_radar.collect._add_html_front_matter", stopped)

    with pytest.raises(KeyboardInterrupt):
        _run(fake, store)


def _pending(count: int) -> list[Paper]:
    return [
        Paper(
            arxiv_id=f"2609.{index:05d}",
            announced=date(2026, 9, 25),
            title="T",
            authors=("Ada Lovelace",),
            html_url=f"https://arxiv.org/html/2609.{index:05d}v1",
        )
        for index in range(count)
    ]


def _read_html(
    papers: list[Paper],
    respond: Callable[[int], httpx.Response],
    *,
    deadline: float | None = None,
    saved: list[list[Paper]] | None = None,
) -> tuple[list[Paper], list[list[Paper]], list[int], Stop | None, int]:
    """Read the pages of ``papers`` through ``respond(page number)``: what came back and was saved."""
    requested: list[int] = []
    saved = [] if saved is None else saved

    def handle(_: httpx.Request) -> httpx.Response:
        requested.append(len(requested))
        return respond(len(requested))

    def checkpoint(current: list[Paper]) -> None:
        saved.append(list(current))

    with HttpClient(transport=httpx.MockTransport(handle), max_attempts=1) as client:
        read = _add_html_front_matter(
            papers, client, reading=HtmlReading(save_every=10, deadline=deadline), checkpoint=checkpoint
        )
    return read.papers, saved, requested, read.stopped, read.empty


def test_html_reading_stops_when_arxiv_keeps_failing() -> None:
    papers, _, requested, stopped, _ = _read_html(_pending(20), lambda _: httpx.Response(503))

    assert stopped is Stop.FAILURES
    assert len(requested) == MAX_CONSECUTIVE_HTML_FAILURES
    assert all(paper.affiliations is None for paper in papers)


def test_a_page_read_resets_the_failure_streak(paper_html: Callable[[str], str]) -> None:
    page = paper_html("2609.30249")

    def respond(number: int) -> httpx.Response:
        return (
            httpx.Response(200, text=page)
            if number % MAX_CONSECUTIVE_HTML_FAILURES == 0
            else httpx.Response(503)
        )

    _, _, requested, stopped, _ = _read_html(_pending(12), respond)

    assert stopped is None
    assert len(requested) == 12


def test_html_reading_stops_when_nearly_every_page_is_empty() -> None:
    papers, saved, requested, stopped, empty = _read_html(
        _pending(DRIFT_MIN_PAGES + 10), lambda _: httpx.Response(200, text="<html></html>")
    )

    assert stopped is Stop.LAYOUT
    assert len(requested) == empty == DRIFT_MIN_PAGES
    # Saved as "nothing found" at the checkpoints, then set back to pending.
    assert saved[-1][0].affiliations == ()
    assert all(paper.affiliations is None for paper in papers)


def test_a_day_of_empty_pages_is_not_a_layout_change(paper_html: Callable[[str], str]) -> None:
    page = paper_html("2609.30249")

    def respond(number: int) -> httpx.Response:
        return httpx.Response(200, text=page if number % 5 == 0 else "<html></html>")

    _, _, requested, stopped, empty = _read_html(_pending(DRIFT_MIN_PAGES + 10), respond)

    assert stopped is None
    assert len(requested) == DRIFT_MIN_PAGES + 10
    assert empty == 40


def test_html_reading_stops_at_the_deadline() -> None:
    papers, _, requested, stopped, _ = _read_html(_pending(3), lambda _: httpx.Response(404), deadline=0)

    assert stopped is Stop.DEADLINE
    assert requested == []
    assert papers == _pending(3)


@pytest.mark.parametrize(
    ("seconds", "said"),
    [
        (0, "a minute at most"),
        (60, "a minute at most"),
        (61, "about 2 minutes"),
        (59 * 60, "about 59 minutes"),
        (60 * 60, "about 1 h 00 min"),
        (11 * 3600 + 5 * 60, "about 11 h 05 min"),
    ],
)
def test_durations_in_the_logs(seconds: float, said: str) -> None:
    assert _about(seconds) == said


def test_html_reading_logs_the_time_it_takes(
    paper_html: Callable[[str], str], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    page = paper_html("2609.30249")
    papers = _pending(25)
    cache = PageCache(tmp_path / "pages")
    for paper in papers[:5]:
        assert paper.html_url is not None
        cache.put(paper.html_url, page)
    # 15 s between requests, as for arxiv.org, without waiting for them.
    limiter = RateLimiter(15.0, sleep=lambda _: None)
    caplog.set_level("INFO")

    with HttpClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text=page)), rate_limiter=limiter
    ) as client:
        _add_html_front_matter(
            papers, client, reading=HtmlReading(save_every=5, cache=cache), checkpoint=lambda _: None
        )

    lines = [record.getMessage() for record in caplog.records if "HTML renderings" in record.getMessage()]
    # The cached pages come first, and cost no time.
    assert lines == [
        "Reading 5 HTML renderings from the page cache",
        "Reading 20 HTML renderings at one every 15 s: about 5 minutes (this is slow on purpose)",
        "5/25 HTML renderings read, progress saved; time left: about 5 minutes",
        "10/25 HTML renderings read, progress saved; time left: about 4 minutes",
        "15/25 HTML renderings read, progress saved; time left: about 3 minutes",
        "20/25 HTML renderings read, progress saved; time left: about 2 minutes",
        "25/25 HTML renderings read, progress saved",
    ]


def test_an_interrupted_reading_saves_what_it_read(paper_html: Callable[[str], str]) -> None:
    page = paper_html("2609.30249")

    def respond(number: int) -> httpx.Response:
        if number == 3:
            raise KeyboardInterrupt
        return httpx.Response(200, text=page)

    saved: list[list[Paper]] = []
    with pytest.raises(KeyboardInterrupt):
        _read_html(_pending(5), respond, saved=saved)

    assert [paper.affiliations is not None for paper in saved[-1]] == [True, True, False, False, False]


def test_format_report_says_why_html_reading_stopped() -> None:
    report = UpdateReport(
        category="cs.CV",
        listed=10,
        new=2,
        abstracts_fetched=2,
        affiliations_fetched=45,
        pending=8,
        empty=40,
        stopped=Stop.LAYOUT,
    )

    assert format_report(report) == (
        "cs.CV: 10 listed, 2 new, 2 abstracts and 45 affiliations fetched (40 pages without any), "
        "8 still pending; HTML reading stopped: nearly every page gave no affiliation"
    )
    assert report.failed
    assert not replace(report, stopped=Stop.DEADLINE).failed


def test_format_report_counts_papers_without_a_page_apart() -> None:
    report = UpdateReport(
        category="cs.CV", listed=10, new=2, abstracts_fetched=2, affiliations_fetched=8, pending=1, no_page=1
    )

    assert format_report(report) == (
        "cs.CV: 10 listed, 2 new, 2 abstracts and 8 affiliations fetched, "
        "1 without an HTML page, 1 still pending"
    )


def test_a_paper_without_a_page_is_not_pending(fake: FakeArxiv, store: PaperStore) -> None:
    # 2609.30245 without its HTML rendering: no run can read its affiliations.
    fake.listing_html = fake.listing_html.replace('href="https://arxiv.org/html/2609.30245v1"', "")
    with fake.client() as site, fake.client() as api:
        report = update_category("cs.CV", store=store, site_client=site, api_client=api)
    stored = {paper.arxiv_id: paper for paper in store.iter_papers("cs.CV")}

    assert stored["2609.30245"].html_url is None
    assert stored["2609.30245"].affiliations is None
    assert report.no_page == 1
    # Pending: the paper whose page could not be read this time, which a later run reads.
    unread = [arxiv_id for arxiv_id, paper in stored.items() if paper.affiliations is None and paper.html_url]
    assert report.unreadable == len(unread) == report.pending == 1


STORED = Paper(
    arxiv_id="2609.00000",
    announced=date(2026, 9, 25),
    title="T",
    authors=("Yuyao Liu",),
    abstract="Stored.",
    affiliations=("Old Institute",),
    author_affiliations=((0,),),
    institutions=("Old Institute",),
    extractor=0,
)


def _stored(arxiv_id: str, version: str, **fields: object) -> Paper:
    """A stored paper, extracted by version 0 unless told otherwise."""
    return replace(
        STORED, arxiv_id=arxiv_id, html_url=f"https://arxiv.org/html/{arxiv_id}v{version}", **fields
    )


def _outdated(paper: Paper) -> bool:
    return paper.extractor is not None and paper.extractor < EXTRACTOR_VERSION


def _reextract(
    fake: FakeArxiv, store: PaperStore, html: HtmlReading | None = None, *, ror: bool = False
) -> UpdateReport:
    with fake.client() as site, fake.client() as ror_client:
        return reextract_category(
            "cs.CV",
            _outdated,
            store=store,
            site_client=site,
            ror_client=ror_client if ror else None,
            html=html or HtmlReading(save_every=1),
        )


def test_reextract_reads_the_selected_papers_again_and_keeps_what_fails(
    fake: FakeArxiv, store: PaperStore
) -> None:
    store.save(
        "cs.CV",
        [
            _stored("2609.30249", "1"),
            _stored("2609.30234", "1", affiliations=("Kept",), institutions=("Kept",)),  # a 503
            _stored("2609.11111", "1", extractor=EXTRACTOR_VERSION),  # current
            _stored("2609.22222", "1", extractor=None),  # read before versions were kept
        ],
    )

    report = _reextract(fake, store, ror=True)

    stored = {paper.arxiv_id: paper for paper in store.iter_papers("cs.CV")}
    affiliations = stored["2609.30249"].affiliations or ()
    assert "NVIDIA" in affiliations
    assert stored["2609.30249"].extractor == EXTRACTOR_VERSION
    # Changed: named again through ROR.
    assert len(stored["2609.30249"].institutions or ()) == len(affiliations)
    assert stored["2609.30249"].abstract == "Stored."
    # Kept as it was: its page could not be read, and its institutions are named.
    assert stored["2609.30234"] == _stored("2609.30234", "1", affiliations=("Kept",), institutions=("Kept",))
    assert stored["2609.11111"] == _stored("2609.11111", "1", extractor=EXTRACTOR_VERSION)
    assert stored["2609.22222"].extractor is None
    assert (report.listed, report.affiliations_fetched, report.unreadable) == (2, 1, 1)
    assert fake.hits["/html/2609.11111v1"] == fake.hits["/html/2609.22222v1"] == 0


def test_reextract_keeps_the_institutions_of_unchanged_affiliations(
    fake: FakeArxiv, store: PaperStore, paper_html: Callable[[str], str]
) -> None:
    front = parse_front_matter(paper_html("2609.30249"), authors=("Yuyao Liu",))
    institutions = tuple(f"Named {index}" for index in range(len(front.affiliations)))
    store.save(
        "cs.CV",
        [
            _stored(
                "2609.30249",
                "1",
                affiliations=front.affiliations,
                author_affiliations=None,
                institutions=institutions,
            )
        ],
    )

    _reextract(fake, store)

    (stored,) = store.iter_papers("cs.CV")
    assert stored.institutions == institutions
    assert stored.extractor == EXTRACTOR_VERSION


def test_reextract_reads_cached_pages_without_counting_them(
    fake: FakeArxiv, store: PaperStore, paper_html: Callable[[str], str], tmp_path: Path
) -> None:
    cache = PageCache(tmp_path / "pages")
    cache.put("https://arxiv.org/html/2609.30249v1", paper_html("2609.30249"))
    store.save("cs.CV", [_stored("2609.30249", "1"), _stored("2609.30234", "1")])

    report = _reextract(fake, store, HtmlReading(limit=0, cache=cache))

    assert report.affiliations_fetched == 1
    assert sum(count for path, count in fake.hits.items() if path.startswith("/html/")) == 0
    stored = {paper.arxiv_id: paper for paper in store.iter_papers("cs.CV")}
    assert "NVIDIA" in (stored["2609.30249"].affiliations or ())
    assert stored["2609.30234"].affiliations == ("Old Institute",)


NO_AFFILIATION_PAGE = (
    '<html><body><article class="ltx_document"><div class="ltx_authors">'
    '<span class="ltx_creator ltx_role_author"><span class="ltx_personname">Yuyao Liu</span></span>'
    "</div></article></body></html>"
)


def test_reextract_never_empties_a_paper_from_a_page_kept_before_tables(
    fake: FakeArxiv, store: PaperStore, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    cache = PageCache(tmp_path / "pages")
    # Kept the way the cache did before it kept the tables of author blocks: unmarked.
    stale = tmp_path / "pages" / "2609" / "2609.00001v1.html.gz"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(gzip.compress(NO_AFFILIATION_PAGE.encode()))
    cache.put("https://arxiv.org/html/2609.00002v1", NO_AFFILIATION_PAGE)
    store.save("cs.CV", [_stored("2609.00001", "1"), _stored("2609.00002", "1")])

    _reextract(fake, store, HtmlReading(limit=0, cache=cache))

    stored = {paper.arxiv_id: paper for paper in store.iter_papers("cs.CV")}
    assert stored["2609.00001"] == _stored("2609.00001", "1")
    assert "https://arxiv.org/html/2609.00001v1" not in cache
    assert "1 cached pages gave no affiliation to papers that have some" in caplog.text
    # A page kept today that gives nothing is what the page says.
    assert stored["2609.00002"].affiliations == ()


def test_reextract_keeps_everything_when_the_layout_seems_changed(store: PaperStore) -> None:
    papers = [_stored(f"2609.{index:05d}", "1") for index in range(DRIFT_MIN_PAGES + 5)]
    store.save("cs.CV", papers)
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text="<html></html>"))

    with HttpClient(transport=transport, max_attempts=1) as site:
        report = reextract_category("cs.CV", lambda _: True, store=store, site_client=site)

    assert report.stopped is Stop.LAYOUT
    assert sorted(store.iter_papers("cs.CV"), key=lambda paper: paper.arxiv_id) == papers


def _placed(arxiv_id: str, *ids: str | None, announced: date = date(2026, 9, 25)) -> Paper:
    """A paper at institutions with these ROR ids (or none)."""
    names = tuple(f"Institution {number}" for number in range(len(ids)))
    return Paper(
        arxiv_id=arxiv_id,
        announced=announced,
        title="T",
        authors=("Ada",),
        affiliations=names,
        institutions=names,
        institution_ids=ids,
    )


def test_the_countries_of_the_stored_papers_institutions(store: PaperStore) -> None:
    store.save(
        "cs.CV",
        [_placed("2609.00001", "03vek6s52", None), _placed("2609.00002", "0220mzb33"), _placed("2609.00003")],
    )
    store.write_archive("cs.CV", [_placed("2001.00004", "0000000aa", announced=date(2020, 1, 3))])
    # A day file's paper among the last 12 months is counted once.
    store.write_top_recent("cs.CV", [_placed("2609.00001", "03vek6s52")], since=date(2025, 10, 9))
    # One known already, which is not asked again; one of no stored paper, which leaves.
    store.write_countries("cs.CV", {"0220mzb33": "GB", "0stale000": "FR"}, source="OpenAlex")
    asked: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.params["filter"])
        return httpx.Response(
            200, json={"results": [{"ror": "https://ror.org/03vek6s52", "country_code": "US"}]}
        )

    now = datetime(2026, 10, 16, 5, tzinfo=UTC)
    with HttpClient(transport=httpx.MockTransport(handle), max_attempts=1) as client:
        report = update_countries(store, "cs.CV", client, now=now)

    assert asked == ["ror:0000000aa|03vek6s52"]
    countries = store.load_countries("cs.CV")
    assert countries is not None
    assert countries.institutions == {"0000000aa": None, "0220mzb33": "GB", "03vek6s52": "US"}
    assert countries.generated_at == now
    assert report == CountriesReport(
        category="cs.CV",
        institutions=3,
        asked=2,
        placed=2,
        nowhere=1,
        failed=0,
        papers=4,
        papers_placed=2,
    )
    assert format_countries_report(report) == (
        "cs.CV: 3 institutions, 2 asked: 2 placed in a country, 1 nowhere, 0 failed; "
        "a country for 2 of 4 papers (50%)"
    )

    # Asked again, all of them: a failing OpenAlex keeps what was known, and leaves out a
    # new institution, asked for next time.
    store.save("cs.CV", [_placed("2609.00005", "0new00000")])
    with HttpClient(transport=httpx.MockTransport(lambda _: httpx.Response(503)), max_attempts=1) as client:
        report = update_countries(store, "cs.CV", client, refresh=True)

    assert (report.asked, report.failed, report.placed) == (4, 1, 2)
    countries = store.load_countries("cs.CV")
    assert countries is not None
    assert "0new00000" not in countries.institutions


def test_without_papers_the_countries_report_says_none(store: PaperStore) -> None:
    with HttpClient(transport=httpx.MockTransport(lambda _: httpx.Response(503)), max_attempts=1) as client:
        report = update_countries(store, "cs.CV", client)

    assert format_countries_report(report).endswith("a country for 0 of 0 papers (0%)")


def test_a_broken_countries_file_asks_for_every_institution(
    store: PaperStore, caplog: pytest.LogCaptureFixture
) -> None:
    store.save("cs.CV", [_placed("2609.00002", "0220mzb33")])
    (store.root / "cs.CV" / "countries.json").write_text("{not json", encoding="utf-8")

    with HttpClient(transport=httpx.MockTransport(lambda _: httpx.Response(503)), max_attempts=1) as client:
        report = update_countries(store, "cs.CV", client)

    assert report.asked == 1
    assert "The former countries.json does not load" in caplog.text


def test_a_countries_file_of_another_schema_version_stops_the_countries(store: PaperStore) -> None:
    store.save("cs.CV", [_placed("2609.00002", "0220mzb33")])
    (store.root / "cs.CV" / "countries.json").write_text('{"schema_version": 99}', encoding="utf-8")

    with (
        HttpClient(transport=httpx.MockTransport(lambda _: httpx.Response(503)), max_attempts=1) as client,
        pytest.raises(SchemaVersionError),
    ):
        update_countries(store, "cs.CV", client)
