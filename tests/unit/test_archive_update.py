import gzip
import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
from tests.conftest import FIXTURES_DIR

from preprint_radar.archive.catalog import Catalog
from preprint_radar.archive.subjects import ARXIV_SUBJECTS, SUBJECT_ALIASES, subject_name, subject_names
from preprint_radar.archive.update import (
    ArchiveClients,
    ArchiveReport,
    _needs_openalex,
    format_archive_report,
    paper_from_catalog,
    refreshed,
    update_archive,
)
from preprint_radar.http import HttpClient
from preprint_radar.models import Paper, Provenance
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
    today: date = TODAY,
) -> ArchiveReport:
    return update_archive(
        "cs.CV",
        store=store,
        catalog=catalog,
        clients=services.clients(),
        budget=budget,
        today=today,
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


def test_without_pruning_old_day_file_papers_compete_and_their_days_stay(
    store: PaperStore, catalog: Catalog
) -> None:
    _update(store, catalog, FakeServices(CITATIONS), prune=False)

    archived = {paper.arxiv_id: paper for paper in store.iter_archive("cs.CV")}
    # The 500-citation day-file paper, not the 1-citation catalog one.
    assert set(archived) == {"1512.03385", "2010.11929", "2508.00001"}
    assert archived["2508.00001"].affiliations == ("Read from its HTML page",)
    assert store.days("cs.CV") == [RECENT_DAY, STALE_DAY]
    assert set(store.load_citations("cs.CV")) == {"1512.03385", "2010.11929", "2508.00001", "2609.00001"}


def test_an_old_paper_cross_listed_lately_enters_under_its_own_year(
    store: PaperStore, catalog: Catalog
) -> None:
    cross_list = Paper(
        arxiv_id="2209.00001",
        announced=RECENT_DAY,
        title="An old paper, cross-listed into cs.CV",
        authors=("A One",),
        affiliations=("Read from its HTML page",),
    )
    store.save("cs.CV", [cross_list])

    _update(store, catalog, FakeServices({**CITATIONS, "2209.00001": 90_000}), prune=False)

    archived = {paper.arxiv_id: paper for paper in store.iter_archive("cs.CV")}
    assert archived["2209.00001"].announced == date(2022, 9, 1)
    assert archived["2209.00001"].affiliations == ("Read from its HTML page",)
    assert store.archive_years("cs.CV") == [2022, 2020, 2015]


def test_a_paper_the_catalog_dates_later_than_its_day_file_is_not_pruned_away(
    store: PaperStore, catalog: Catalog
) -> None:
    # Announced on 2025-10-08, but first dated 2025-10-20 by the catalog: 367 and 355 days
    # before the update.
    today = date(2026, 10, 10)
    with gzip.open(catalog.path, "at", encoding="utf-8") as out:
        out.write(json.dumps(_entry("2510.00036", date(2025, 10, 20)).to_record()) + "\n")
    late = Paper(arxiv_id="2510.00036", announced=date(2025, 10, 8), title="Late", authors=("A One",))
    store.save("cs.CV", [late])

    _update(store, catalog, FakeServices({**CITATIONS, "2510.00036": 900}), budget=4, today=today)

    archived = {paper.arxiv_id: paper for paper in store.iter_archive("cs.CV")}
    assert archived["2510.00036"].announced == date(2025, 10, 8)
    assert date(2025, 10, 8) not in store.days("cs.CV")


def test_an_archived_paper_missing_a_count_keeps_last_weeks(store: PaperStore, catalog: Catalog) -> None:
    _update(store, catalog, FakeServices(CITATIONS))
    (catalog.directory / "cs.CV.citations.jsonl").unlink()
    missing = {arxiv_id: count for arxiv_id, count in CITATIONS.items() if arxiv_id != "2010.11929"}

    report = _update(store, catalog, FakeServices(missing))

    assert {paper.arxiv_id for paper in store.iter_archive("cs.CV")} == {
        "1512.03385",
        "2010.11929",
        "2508.00001",
    }
    assert report.carried == 1
    assert report.left == 0
    assert store.load_citations("cs.CV")["2010.11929"] == 70_000


def test_archived_papers_without_affiliations_are_looked_up_again(
    store: PaperStore, catalog: Catalog
) -> None:
    _update(store, catalog, FakeServices(CITATIONS))
    papers = [
        replace(
            paper,
            affiliations=None,
            author_affiliations=None,
            institutions=None,
            institution_ids=None,
            affiliations_provenance=None,
            institutions_provenance=None,
        )
        if paper.arxiv_id == "1512.03385"
        else paper
        for paper in store.iter_archive("cs.CV")
    ]
    store.write_archive("cs.CV", papers)

    _update(store, catalog, FakeServices(CITATIONS))

    resnet = next(paper for paper in store.iter_archive("cs.CV") if paper.arxiv_id == "1512.03385")
    assert resnet.affiliations == ("Microsoft",)
    assert resnet.affiliations_provenance == resnet.institutions_provenance == Provenance("openalex", TODAY)


def test_young_archived_papers_without_affiliations_are_asked_again_every_month(
    store: PaperStore, catalog: Catalog
) -> None:
    _update(store, catalog, FakeServices(CITATIONS))
    # 2508.00001 is 400 days old, 2010.11929 six years: OpenAlex said nothing of either.
    store.write_archive(
        "cs.CV",
        [
            replace(
                paper,
                affiliations=(),
                author_affiliations=None,
                institutions=(),
                institution_ids=None,
                affiliations_provenance=None,
                institutions_provenance=None,
            )
            if paper.arxiv_id in {"2508.00001", "2010.11929"}
            else paper
            for paper in store.iter_archive("cs.CV")
        ],
    )

    _update(store, catalog, FakeServices(CITATIONS))

    archived = {paper.arxiv_id: paper for paper in store.iter_archive("cs.CV")}
    # Asked again, and still unknown to OpenAlex: the day of the lookup counts from now.
    assert archived["2508.00001"].affiliations == ()
    assert archived["2508.00001"].affiliations_provenance == Provenance("openalex", TODAY)
    # Too old to be asked again.
    assert archived["2010.11929"].affiliations_provenance is None


def test_openalex_affiliations_carry_no_html_extractor_version(store: PaperStore, catalog: Catalog) -> None:
    _update(store, catalog, FakeServices(CITATIONS))
    # Two papers of day files, read from their pages by extraction version 7: one not read
    # yet, one whose page gave nothing more than a month ago.
    read = Provenance("html", TODAY - timedelta(days=40))
    store.write_archive(
        "cs.CV",
        [
            replace(
                paper,
                affiliations=None if paper.arxiv_id == "1512.03385" else (),
                author_affiliations=None,
                institutions=None if paper.arxiv_id == "1512.03385" else (),
                institution_ids=None,
                extractor=7,
                affiliations_provenance=None if paper.arxiv_id == "1512.03385" else read,
                institutions_provenance=None,
            )
            if paper.arxiv_id in {"1512.03385", "2508.00001"}
            else paper
            for paper in store.iter_archive("cs.CV")
        ],
    )

    _update(store, catalog, FakeServices(CITATIONS))

    archived = {paper.arxiv_id: paper for paper in store.iter_archive("cs.CV")}
    # OpenAlex gave the affiliations: no HTML extraction stands for them.
    assert archived["1512.03385"].affiliations == ("Microsoft",)
    assert archived["1512.03385"].extractor is None
    # OpenAlex knows nothing yet either: the lookup is OpenAlex's, without a version.
    assert archived["2508.00001"].affiliations == ()
    assert archived["2508.00001"].affiliations_provenance == Provenance("openalex", TODAY)
    assert archived["2508.00001"].extractor is None


@pytest.mark.parametrize(
    ("age_days", "last_lookup_days", "asked"),
    [
        (400, None, True),
        (400, 30, True),
        (400, 29, False),
        (730, None, False),
    ],
    ids=["young-never-dated", "young-a-month-ago", "young-recently", "two-years-old"],
)
def test_an_empty_archived_paper_is_asked_again_while_young(
    age_days: int, last_lookup_days: int | None, *, asked: bool
) -> None:
    paper = Paper(
        arxiv_id="2508.00001",
        announced=TODAY - timedelta(days=age_days),
        title="A paper",
        authors=("A One",),
        affiliations=(),
        affiliations_provenance=Provenance(
            "openalex", None if last_lookup_days is None else TODAY - timedelta(days=last_lookup_days)
        ),
    )

    assert _needs_openalex(paper, TODAY) is asked


def test_archived_papers_get_the_ror_ids_of_their_institutions(store: PaperStore, catalog: Catalog) -> None:
    _update(store, catalog, FakeServices(CITATIONS))
    archived = {paper.arxiv_id: paper for paper in store.iter_archive("cs.CV")}
    assert archived["1512.03385"].institution_ids  # an entrant gets them
    # Archived before ids were kept: OpenAlex is asked again, once.
    store.write_archive(
        "cs.CV",
        [replace(paper, institution_ids=None) for paper in archived.values()],
    )

    _update(store, catalog, FakeServices(CITATIONS))

    again = {paper.arxiv_id: paper for paper in store.iter_archive("cs.CV")}
    assert again["1512.03385"].institution_ids == archived["1512.03385"].institution_ids
    assert again["1512.03385"].affiliations == ("Microsoft",)


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

    counts_before = store.load_citation_counts("cs.CV")

    report = _update(store, catalog, FakeServices(CITATIONS, citations_down=True), budget=1)

    assert {paper.arxiv_id for paper in store.iter_archive("cs.CV")} == before
    assert report.left == 0
    # The published counts stay, with the date of their last refresh.
    assert store.load_citation_counts("cs.CV") == counts_before


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


def test_stored_papers_take_the_comments_of_their_latest_version(store: PaperStore, catalog: Catalog) -> None:
    report = _update(store, catalog, FakeServices(CITATIONS), prune=False)

    # The catalog's entries say "Accepted to CVPR 2016"; the stored records said nothing.
    recent = next(paper for paper in store.iter_papers("cs.CV") if paper.arxiv_id == "2609.00001")
    assert (recent.comments, recent.venue) == ("Accepted to CVPR 2016", "CVPR 2016")
    assert recent.title == "Recent paper"  # nothing else changes
    assert report.refreshed == 2  # both day files' papers

    again = _update(store, catalog, FakeServices(CITATIONS), prune=False)
    assert again.refreshed == 0


def test_withdrawn_papers_leave_the_archive_and_never_enter_it(store: PaperStore, catalog: Catalog) -> None:
    _update(store, catalog, FakeServices(CITATIONS))
    assert {paper.arxiv_id for paper in store.iter_archive("cs.CV")} >= {"1512.03385", "2010.11929"}
    entries = [
        replace(entry, comments="This paper has been withdrawn by the authors")
        if entry.arxiv_id in {"1512.03385", "2209.00001"}
        else entry
        for entry in catalog.entries().values()
    ]
    with gzip.open(catalog.path, "wt", encoding="utf-8") as out:
        for entry in entries:
            out.write(json.dumps(entry.to_record()) + "\n")

    _update(store, catalog, FakeServices(CITATIONS), budget=4)

    archived = {paper.arxiv_id for paper in store.iter_archive("cs.CV")}
    assert "1512.03385" not in archived  # left, however cited
    assert "2209.00001" not in archived  # never entered, though within the budget


def test_refreshed_takes_what_the_catalog_adds_and_never_empties_a_field() -> None:
    paper = Paper(
        arxiv_id="2609.00001",
        announced=RECENT_DAY,
        title="Recent paper",
        authors=("A One",),
        comments="12 pages",
        venue=None,
    )
    entry = replace(_entry("2609.00001", RECENT_DAY), comments=None, journal_ref="IEEE TPAMI 2027")

    updated = refreshed(paper, entry)

    assert (updated.comments, updated.journal_ref, updated.venue) == (
        "12 pages",
        "IEEE TPAMI 2027",
        "TPAMI 2027",
    )
    assert refreshed(updated, entry) is updated
    assert refreshed(paper, None) is paper


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
        "citation counts for 98.7% of 1,000 papers, 0 papers' comments refreshed, 2 day files pruned"
    )
    assert format_archive_report(replace(report, carried=4, written=False)) == (
        "cs.CV: 500 archived papers (3 in, 1 out), threshold 19.5 citations a year, "
        "citation counts for 98.7% of 1,000 papers (4 archived papers on last week's count), "
        "0 papers' comments refreshed, 2 day files pruned (dry run: nothing written)"
    )


def test_paper_from_catalog_names_subjects() -> None:
    entry = _entry("2010.11929", date(2020, 10, 22), ("cs.LG", "cs.CV", "cs.AI"))

    # The name the stored days give comes first, arXiv's taxonomy names the others.
    paper = paper_from_catalog(entry, "cs.CV", {"cs.LG": "Learned name (cs.LG)"})

    assert paper.primary_subject == "Learned name (cs.LG)"
    assert paper.subjects == (
        "Learned name (cs.LG)",
        "Computer Vision and Pattern Recognition (cs.CV)",
        "Artificial Intelligence (cs.AI)",
    )
    assert paper.announced == date(2020, 10, 22)
    assert paper.affiliations is None


def test_paper_from_catalog_names_an_alias_as_its_canonical_subject_once() -> None:
    # OAI lists an alias next to its canonical code; the listings print the latter once.
    entry = _entry("1203.00001", date(2012, 3, 1), ("cs.SY", "eess.SY", "cs.CV", "math.IT", "cs.XX"))

    paper = paper_from_catalog(entry, "cs.CV", {"cs.IT": "Learned name (cs.IT)"})

    assert paper.primary_subject == "Systems and Control (eess.SY)"
    assert paper.subjects == (
        "Systems and Control (eess.SY)",
        "Computer Vision and Pattern Recognition (cs.CV)",
        "Learned name (cs.IT)",
        "cs.XX",  # a code arXiv's taxonomy does not know stays as it is
    )
    assert paper.cross_list_from == "eess.SY"


def test_every_alias_names_a_subject_of_the_taxonomy() -> None:
    assert set(SUBJECT_ALIASES).isdisjoint(ARXIV_SUBJECTS)
    assert set(SUBJECT_ALIASES.values()) <= set(ARXIV_SUBJECTS)
    assert subject_name("stat.TH", {}) == "Statistics Theory (math.ST)"
    assert subject_names(("math-ph", "math.MP"), {}) == ("Mathematical Physics (math-ph)",)
