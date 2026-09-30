import gzip
import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
from tests.conftest import FIXTURES_DIR

from preprint_radar.archive.catalog import Catalog
from preprint_radar.archive.update import (
    ArchiveClients,
    ArchiveReport,
    format_archive_report,
    paper_from_catalog,
    update_archive,
)
from preprint_radar.http import HttpClient
from preprint_radar.models import Paper
from preprint_radar.sources.arxiv_oai import CatalogEntry
from preprint_radar.store.paper_store import PaperStore

WORKS = (FIXTURES_DIR / "openalex" / "works.json").read_text(encoding="utf-8")
NOTHING_NEW = '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><error code="noRecordsMatch"/></OAI-PMH>'
TODAY = date(2026, 9, 30)
STALE_DAY = TODAY - timedelta(days=400)
RECENT_DAY = TODAY - timedelta(days=10)


class FakeServices:
    """OAI-PMH (nothing new), Semantic Scholar (fixed counts) and OpenAlex (the fixture)."""

    def __init__(self, citations: dict[str, int], *, citations_down: bool = False) -> None:
        self.citations = citations
        self.citations_down = citations_down

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "oaipmh.arxiv.org":
            return httpx.Response(
                200,
                text=NOTHING_NEW,
            )
        if request.url.host == "api.semanticscholar.org":
            if self.citations_down:
                return httpx.Response(503)
            ids = [paper_id.removeprefix("ARXIV:") for paper_id in json.loads(request.content)["ids"]]
            return httpx.Response(200, json=[{"citationCount": self.citations.get(i)} for i in ids])
        return httpx.Response(200, text=WORKS)

    def clients(self) -> ArchiveClients:
        def client() -> HttpClient:
            return HttpClient(transport=httpx.MockTransport(self.handle), max_attempts=1)

        return ArchiveClients(oai=client(), citations=client(), openalex=client())


def _entry(arxiv_id: str, created: date, categories: tuple[str, ...] = ("cs.CV",)) -> CatalogEntry:
    return CatalogEntry(
        arxiv_id=arxiv_id,
        created=created,
        categories=categories,
        title=f"Paper {arxiv_id}",
        authors=("A One", "B Two", "C Three", "D Four"),
        abstract="An abstract.",
        comments="Accepted to CVPR 2016",
    )


@pytest.fixture
def catalog(tmp_path: Path) -> Catalog:
    entries = [
        _entry("1512.03385", date(2015, 12, 10)),
        _entry("2010.11929", date(2020, 10, 22), ("cs.LG", "cs.CV")),
        _entry("2209.00001", date(2022, 9, 1)),
        _entry("2508.00001", date(2025, 8, 20)),  # the stale day's paper
        _entry("2609.00001", date(2026, 9, 20)),  # recent
    ]
    catalog = Catalog(tmp_path / "catalog", "cs.CV")
    catalog.directory.mkdir(parents=True)
    with gzip.open(catalog.path, "wt", encoding="utf-8") as out:
        for entry in entries:
            out.write(json.dumps(entry.to_record()) + "\n")
    (catalog.directory / "cs.CV.state.json").write_text(
        json.dumps({"harvested": "2026-09-23", "token": None})
    )
    return catalog


@pytest.fixture
def store(tmp_path: Path) -> PaperStore:
    store = PaperStore(tmp_path / "data")
    stale = Paper(
        arxiv_id="2508.00001",
        announced=STALE_DAY,
        title="Graduating paper",
        authors=("A One",),
        subjects=("Machine Learning (cs.LG)",),
        affiliations=("Read from its HTML page",),
    )
    recent = Paper(
        arxiv_id="2609.00001",
        announced=RECENT_DAY,
        title="Recent paper",
        authors=("A One",),
        # Subject names are learned from the stored days; a subject without code names nothing.
        subjects=("Computer Vision and Pattern Recognition (cs.CV)", "Uncoded subject"),
    )
    store.save("cs.CV", [stale, recent])
    return store


CITATIONS = {"1512.03385": 240_000, "2010.11929": 70_000, "2209.00001": 1, "2508.00001": 500, "2609.00001": 3}


def _update(
    store: PaperStore,
    catalog: Catalog,
    services: FakeServices,
    *,
    budget: int = 3,
    prune: bool = True,
    dry_run: bool = False,
) -> ArchiveReport:
    return update_archive(
        "cs.CV",
        store=store,
        catalog=catalog,
        clients=services.clients(),
        budget=budget,
        today=TODAY,
        prune=prune,
        dry_run=dry_run,
    )


def test_update_archive_keeps_the_most_cited_and_prunes_old_days(store: PaperStore, catalog: Catalog) -> None:
    _update(store, catalog, FakeServices(CITATIONS))

    archived = {paper.arxiv_id: paper for paper in store.iter_archive("cs.CV")}
    assert set(archived) == {"1512.03385", "2010.11929", "2508.00001"}
    assert store.archive_years("cs.CV") == [2025, 2020, 2015]
    # From the catalog, with OpenAlex affiliations and the detected venue.
    resnet = archived["1512.03385"]
    assert resnet.affiliations == ("Microsoft",)
    assert resnet.institutions == ("Microsoft",)
    assert resnet.author_affiliations == ((0,), (0,), (0,), (0,))
    assert resnet.venue == "CVPR 2016"
    # A cross-list keeps its primary category.
    assert archived["2010.11929"].cross_list_from == "cs.LG"
    assert archived["2010.11929"].subjects == (
        "Machine Learning (cs.LG)",
        "Computer Vision and Pattern Recognition (cs.CV)",
    )
    # Graduating from the rolling year: its own enrichment is kept.
    assert archived["2508.00001"].affiliations == ("Read from its HTML page",)
    assert store.days("cs.CV") == [RECENT_DAY]
    assert store.load_citations("cs.CV") == {
        "1512.03385": 240_000,
        "2010.11929": 70_000,
        "2508.00001": 500,
        "2609.00001": 3,
    }
    index = json.loads((store.root / "index.json").read_text(encoding="utf-8"))
    assert [entry["year"] for entry in index["archives"]["cs.CV"]] == [2025, 2020, 2015]


def test_update_archive_without_pruning_keeps_old_days_out_of_the_archive(
    store: PaperStore, catalog: Catalog
) -> None:
    _update(store, catalog, FakeServices(CITATIONS), prune=False)

    assert {paper.arxiv_id for paper in store.iter_archive("cs.CV")} == {
        "1512.03385",
        "2010.11929",
        "2209.00001",
    }
    assert store.days("cs.CV") == [RECENT_DAY, STALE_DAY]


def test_archived_papers_without_affiliations_are_looked_up_again(
    store: PaperStore, catalog: Catalog
) -> None:
    _update(store, catalog, FakeServices(CITATIONS))
    papers = [
        replace(paper, affiliations=None, author_affiliations=None, institutions=None)
        if paper.arxiv_id == "1512.03385"
        else paper
        for paper in store.iter_archive("cs.CV")
    ]
    store.write_archive("cs.CV", papers)

    _update(store, catalog, FakeServices(CITATIONS))

    resnet = next(paper for paper in store.iter_archive("cs.CV") if paper.arxiv_id == "1512.03385")
    assert resnet.affiliations == ("Microsoft",)


def test_dry_run_writes_nothing(store: PaperStore, catalog: Catalog) -> None:
    report = _update(store, catalog, FakeServices(CITATIONS), dry_run=True)

    assert report.entered == 3
    assert store.archive_years("cs.CV") == []
    assert store.days("cs.CV") == [RECENT_DAY, STALE_DAY]


def test_the_archive_stays_as_it_is_without_citation_counts(
    store: PaperStore, catalog: Catalog, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("preprint_radar.sources.semantic_scholar.S2_ANONYMOUS_RETRY_WAIT_SECONDS", 0)
    _update(store, catalog, FakeServices(CITATIONS))
    before = {paper.arxiv_id for paper in store.iter_archive("cs.CV")}
    # Without the counts cached by the first run.
    (catalog.directory / "cs.CV.citations.jsonl").unlink()

    report = _update(store, catalog, FakeServices(CITATIONS, citations_down=True), budget=1)

    assert {paper.arxiv_id for paper in store.iter_archive("cs.CV")} == before
    assert report.left == 0


@pytest.mark.parametrize(("age", "expected"), [(3, 3), (7, 42)], ids=["reused", "fetched-again"])
def test_citation_counts_cached_by_a_recent_run_are_reused(
    store: PaperStore, catalog: Catalog, age: int, expected: int
) -> None:
    _update(store, catalog, FakeServices(CITATIONS))
    cache = catalog.directory / "cs.CV.citations.jsonl"
    _, *batches = cache.read_text(encoding="utf-8").splitlines()
    started = json.dumps({"date": (TODAY - timedelta(days=age)).isoformat()})
    cache.write_text("\n".join([started, *batches]) + "\n", encoding="utf-8")

    _update(store, catalog, FakeServices({**CITATIONS, "2609.00001": 42}))

    assert store.load_citations("cs.CV")["2609.00001"] == expected


def test_a_cut_line_of_the_citations_cache_is_ignored(store: PaperStore, catalog: Catalog) -> None:
    cache = catalog.directory / "cs.CV.citations.jsonl"
    header = json.dumps({"date": TODAY.isoformat()})
    # A run killed while saving its second batch.
    cache.write_text(f'{header}\n{{"1512.03385": 7}}\n{{"2010.119', encoding="utf-8")

    _update(store, catalog, FakeServices(CITATIONS))

    assert store.load_citations("cs.CV")["1512.03385"] == 7  # reused
    assert store.load_citations("cs.CV")["2010.11929"] == 70_000  # fetched again
    lines = cache.read_text(encoding="utf-8").splitlines()
    assert all(json.loads(line) for line in lines)  # the cut line is gone


def test_format_archive_report() -> None:
    report = ArchiveReport(
        category="cs.CV",
        candidates=1000,
        coverage=0.987,
        threshold=19.54,
        archived=500,
        entered=3,
        left=1,
        pruned_days=2,
        written=True,
    )

    assert format_archive_report(report) == (
        "cs.CV: 500 archived papers (3 in, 1 out), threshold 19.5 citations a year, "
        "citation counts for 98.7% of 1000 papers, 2 day files pruned"
    )


def test_paper_from_catalog_names_subjects() -> None:
    entry = _entry("2010.11929", date(2020, 10, 22), ("cs.LG", "cs.CV", "cs.AI"))

    paper = paper_from_catalog(entry, "cs.CV", {"cs.LG": "Machine Learning (cs.LG)"})

    assert paper.primary_subject == "Machine Learning (cs.LG)"
    assert paper.subjects == ("Machine Learning (cs.LG)", "cs.CV", "cs.AI")
    assert paper.announced == date(2020, 10, 22)
    assert paper.affiliations is None
