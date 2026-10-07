import gzip
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path

import httpx
import pytest
from tests.conftest import FIXTURES_DIR

from preprint_radar.collect import (
    DRIFT_MIN_PAGES,
    MAX_CONSECUTIVE_HTML_FAILURES,
    CitationsReport,
    HtmlReading,
    Stop,
    UpdateReport,
    _add_html_front_matter,
    add_institutions,
    backfill_category,
    format_citations_report,
    format_report,
    reextract_category,
    today,
    update_category,
    update_citation_counts,
)
from preprint_radar.http import HttpClient
from preprint_radar.models import Listing, Paper, Provenance
from preprint_radar.sources.arxiv_html import EXTRACTOR_VERSION, PageCache, parse_front_matter
from preprint_radar.sources.arxiv_listing import parse_catchup
from preprint_radar.store.paper_store import PaperStore

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
    assert stored["2609.30249"].affiliations_provenance == Provenance("html", today())
    assert stored["2609.28466"].affiliations_provenance == Provenance("api", today())
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
    assert stored["2609.28466"].affiliations_provenance == Provenance("api", today())


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
    assert named[0].institutions_provenance == Provenance("ror", today())
    assert fake.ror_requests == ["School of CS, Peking University", "Meta AI"]
    fake.ror_requests.clear()
    with fake.client() as ror:
        assert add_institutions(named, ror, limit=None) == named
    assert fake.ror_requests == []


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
