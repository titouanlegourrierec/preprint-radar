"""META-1: the published versions of stored papers, from Semantic Scholar (synthetic data)."""

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import httpx
import pytest

from preprint_radar.cli import main
from preprint_radar.collect import (
    ScholarReport,
    checked_author_ids,
    format_scholar_report,
    update_scholar_records,
)
from preprint_radar.exceptions import ParseError, StoreError
from preprint_radar.http import HttpClient
from preprint_radar.models import Paper, ScholarRecord
from preprint_radar.sources.semantic_scholar import (
    S2_RECORD_FIELDS,
    fetch_scholar_records,
    parse_records_response,
)
from preprint_radar.store.paper_store import PaperStore
from preprint_radar.store.stats import collect_archive_coverage, collect_coverage
from preprint_radar.store.validate import Level, validate_store
from preprint_radar.venue import published_venue

CVPR_2022 = {
    "externalIds": {"DOI": "10.1109/CVPR52688.2022.01234", "ArXiv": "2112.00001"},
    "publicationVenue": {
        "name": "Computer Vision and Pattern Recognition",
        "alternate_names": ["CVPR", "Comput Vis Pattern Recognit"],
    },
    "venue": "Computer Vision and Pattern Recognition",
    # The arXiv version's date: never the venue's year.
    "publicationDate": "2021-12-01",
    "journal": {"name": "2022 IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)"},
    "authors": [{"authorId": "11", "name": "A"}, {"authorId": None, "name": "B"}],
}


@pytest.mark.parametrize(
    ("name", "alternate", "venue", "year", "expected"),
    [
        ("Computer Vision and Pattern Recognition", ["CVPR"], None, 2018, "CVPR 2018"),
        (None, [], "2018 IEEE/CVF Conference on Computer Vision and Pattern Recognition", None, "CVPR 2018"),
        (None, [], "2020 IEEE/CVF Conference on Computer Vision and Pattern Recognition Workshops (CVPRW)",
         None, "CVPR 2020 Workshop"),
        (None, [], "ECCV Workshops", 2020, "ECCV 2020 Workshop"),
        ("IEEE Workshop/Winter Conference on Applications of Computer Vision", ["WACV"], None, 2020,
         "WACV 2020"),
        # Another venue sharing a known acronym keeps its own name.
        ("International Conference on Information Photonics", ["ICIP"], None, 2026,
         "International Conference on Information Photonics 2026"),
        ("ACM SIGGRAPH Conference in Asia", ["SIGGRAPH Asia"], None, 2023, "SIGGRAPH Asia 2023"),
        ("IEEE transactions on circuits and systems for video technology (Print)", [], None, 2024,
         "IEEE transactions on circuits and systems for video technology 2024"),
        ("Information Fusion", [], None, None, "Information Fusion"),
        ("arXiv.org", ["ArXiv"], "arXiv.org", 2023, None),
        # A bare venue string is often an abbreviation.
        (None, [], "Medical Image Anal.", 2020, None),
        (None, [], None, 2020, None),
    ],
)  # fmt: skip
def test_names_published_venues_as_the_table_does(
    name: str | None, alternate: list[str], venue: str | None, year: int | None, expected: str | None
) -> None:
    assert published_venue(name, alternate, venue, year) == expected


def test_parses_records_with_the_venue_year_and_a_published_doi() -> None:
    arxiv_only = {"externalIds": {"DOI": "10.48550/arXiv.2609.00002"}, "venue": "arXiv.org", "authors": []}
    journal = {
        "externalIds": {},
        "publicationVenue": {"name": "IEEE Transactions on Image Processing", "alternate_names": []},
        "journal": {"name": "IEEE Transactions on Image Processing", "volume": "2023"},
    }
    ieee = {
        "externalIds": {"DOI": "10.1109/ICCV51070.2023.00042"},
        "venue": "IEEE International Conference on Computer Vision",
    }
    # Only known as a preprint: "abs/2006.05929" is an arXiv identifier, not the year 2006.
    preprint = {
        "publicationVenue": {"name": "Neural Information Processing Systems", "alternate_names": ["NeurIPS"]},
        "journal": {"name": "ArXiv", "volume": "abs/2006.05929"},
    }
    text = json.dumps([CVPR_2022, arxiv_only, None, journal, ieee, preprint])

    records = parse_records_response(text, ("1", "2", "3", "4", "5", "6"))

    assert records == {
        "1": ScholarRecord(
            doi="10.1109/CVPR52688.2022.01234",
            venue="CVPR 2022",
            author_ids=("11", None),
            author_names=("A", "B"),
        ),
        "2": ScholarRecord(),
        "3": None,
        "4": ScholarRecord(venue="TIP 2023"),
        "5": ScholarRecord(doi="10.1109/ICCV51070.2023.00042", venue="ICCV 2023"),
        "6": ScholarRecord(venue="NeurIPS"),
    }
    with pytest.raises(ParseError):
        parse_records_response("[]", ("1",))
    with pytest.raises(ParseError):
        parse_records_response('[{"externalIds": [1]}]', ("1",))


def test_fetches_records_with_their_fields() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[CVPR_2022])

    with HttpClient(transport=httpx.MockTransport(handle), max_attempts=1) as client:
        records = fetch_scholar_records(client, ["2112.00001"], key="secret")

    assert records["2112.00001"] == ScholarRecord(
        doi="10.1109/CVPR52688.2022.01234",
        venue="CVPR 2022",
        author_ids=("11", None),
        author_names=("A", "B"),
    )
    assert requests[0].url.params["fields"] == S2_RECORD_FIELDS


def _paper(
    arxiv_id: str, announced: date, *, authors: tuple[str, ...] = ("A", "B"), venue: str | None = None
) -> Paper:
    return Paper(arxiv_id=arxiv_id, announced=announced, title="T", authors=authors, venue=venue)


@pytest.fixture
def store(tmp_path: Path) -> PaperStore:
    store = PaperStore(tmp_path / "data")
    store.save(
        "cs.CV",
        [
            _paper("2609.00001", date(2026, 9, 24)),
            _paper("2609.00002", date(2026, 9, 24), authors=("A",)),
            _paper("2609.00003", date(2026, 9, 25), venue="ECCV 2026"),
        ],
    )
    store.write_archive("cs.CV", [_paper("2112.00001", date(2021, 12, 1))])
    # Last week's records: one of a paper no longer stored, one Semantic Scholar will not be asked for.
    store.write_scholar(
        "cs.CV",
        {"1001.00001": ScholarRecord(doi="10.1/x"), "2609.00003": ScholarRecord(doi="10.1/kept")},
        source="Semantic Scholar",
    )
    return store


class FakeScholar:
    """Answer record batches from fixed entries; ids it does not hold are unknown."""

    def __init__(self, entries: dict[str, object]) -> None:
        self.entries = entries

    def handle(self, request: httpx.Request) -> httpx.Response:
        ids = [paper_id.removeprefix("ARXIV:") for paper_id in json.loads(request.content)["ids"]]
        return httpx.Response(200, json=[self.entries.get(arxiv_id) for arxiv_id in ids])


def test_updates_the_records_of_every_stored_paper(store: PaperStore) -> None:
    two_authors = {
        "authors": [{"authorId": "1", "name": "A"}, {"authorId": "2", "name": "B"}],
        "venue": "ECCV Workshops",
    }
    fake = FakeScholar({"2112.00001": CVPR_2022, "2609.00001": two_authors, "2609.00002": two_authors})

    with HttpClient(transport=httpx.MockTransport(fake.handle), max_attempts=1) as client:
        report = update_scholar_records(store, "cs.CV", client, key=None)

    scholar = store.load_scholar("cs.CV")
    assert scholar is not None
    assert scholar.papers == {
        "2112.00001": ScholarRecord(
            doi="10.1109/CVPR52688.2022.01234", venue="CVPR 2022", author_ids=("11", None)
        ),
        # Ids by position: not for a paper whose author list differs.
        "2609.00001": ScholarRecord(venue="ECCV Workshop", author_ids=("1", "2")),
        "2609.00002": ScholarRecord(venue="ECCV Workshop"),
    }
    assert report == ScholarReport(category="cs.CV", asked=4, found=3, dois=1, venues=3, gained=3)
    assert format_scholar_report(report) == (
        "cs.CV: Semantic Scholar knows 3 of 4 papers: 1 DOI, 3 published venues "
        "(3 where the comments name none)"
    )


def test_asks_for_the_most_cited_papers_of_the_last_12_months_too(store: PaperStore) -> None:
    store.write_top_recent("cs.CV", [_paper("2511.00001", date(2025, 11, 3))], since=date(2025, 10, 1))
    fake = FakeScholar({"2511.00001": CVPR_2022})

    with HttpClient(transport=httpx.MockTransport(fake.handle), max_attempts=1) as client:
        report = update_scholar_records(store, "cs.CV", client, key=None)

    scholar = store.load_scholar("cs.CV")
    assert scholar is not None
    assert scholar.papers["2511.00001"].doi == "10.1109/CVPR52688.2022.01234"
    assert report.asked == 5


def test_keeps_the_records_of_papers_not_asked_for(store: PaperStore) -> None:
    with HttpClient(transport=httpx.MockTransport(lambda _: httpx.Response(503)), max_attempts=1) as client:
        report = update_scholar_records(store, "cs.CV", client, key=None, max_seconds=0)

    scholar = store.load_scholar("cs.CV")
    assert scholar is not None
    assert scholar.papers == {"2609.00003": ScholarRecord(doi="10.1/kept")}
    assert (report.asked, report.found) == (4, 0)


def test_cli_fetches_the_records_of_each_category(
    store: PaperStore, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, str | None, float | None]] = []

    def update(
        _: PaperStore, category: str, __: HttpClient, *, key: str | None, max_seconds: float | None
    ) -> ScholarReport:
        calls.append((category, key, max_seconds))
        return ScholarReport(category=category, asked=4, found=3, dois=1, venues=2, gained=1)

    monkeypatch.setattr("preprint_radar.cli.update_scholar_records", update)
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "test-key")

    assert main(["scholar", "--data-dir", str(store.root), "--max-minutes", "20"]) == 0
    assert main(["scholar", "--data-dir", str(store.root), "-c", "cs.LG"]) == 0

    assert calls == [("cs.CV", "test-key", 1200), ("cs.LG", "test-key", None)]
    assert capsys.readouterr().out.count("Semantic Scholar knows 3 of 4 papers") == 2


def test_round_trips_and_refuses_bad_files(store: PaperStore) -> None:
    record = ScholarRecord(doi="10.1/x", venue="CVPR 2022", author_ids=("1", None))
    assert ScholarRecord.from_record(record.to_record()) == record
    assert ScholarRecord().to_record() == {}

    store.write_scholar("cs.CV", {"2609.00001": record, "2609.00002": ScholarRecord()}, source="S2")
    path = store.root / "cs.CV" / "scholar.json"
    assert json.loads(path.read_text())["papers"] == {"2609.00001": record.to_record()}
    assert store.load_scholar("cs.LG") is None

    payload = json.loads(path.read_text())
    payload["papers"] = {"2609.00001": {"doi": 3}}
    path.write_text(json.dumps(payload))
    with pytest.raises(StoreError, match="Invalid scholar file") as raised:
        store.load_scholar("cs.CV")
    assert "schema_version" not in str(raised.value)


def test_validate_accepts_up_to_date_records(store: PaperStore) -> None:
    store.write_scholar("cs.CV", {"2609.00001": ScholarRecord(author_ids=("1", "2"))}, source="S2")
    store.write_index()

    assert validate_store(store).findings == []


def test_validate_warns_on_stale_records_and_fails_on_a_bad_file(store: PaperStore) -> None:
    store.write_scholar(
        "cs.CV",
        {
            "1001.00001": ScholarRecord(doi="10.1/x"),
            "2609.00002": ScholarRecord(author_ids=("1", "2")),
            "2609.00001": ScholarRecord(author_ids=("1", "2")),
        },
        source="S2",
    )
    findings = [(finding.level, finding.message) for finding in validate_store(store).findings]
    assert (Level.WARNING, "1 records of papers that are not stored, e.g. 1001.00001") in findings
    assert (Level.WARNING, "1 author id lists that do not fit the authors, e.g. 2609.00002") in findings

    (store.root / "cs.CV" / "scholar.json").write_text("{}")
    assert any(
        finding.level is Level.ERROR and "Invalid scholar file" in finding.message
        for finding in validate_store(store).findings
    )


def test_stats_count_published_venues(store: PaperStore) -> None:
    store.write_scholar(
        "cs.CV",
        {"2112.00001": ScholarRecord(venue="CVPR 2022"), "2609.00001": ScholarRecord(doi="10.1/x")},
        source="S2",
    )

    assert [row.coverage.venues for row in collect_coverage(store, "cs.CV")] == [1, 0]
    assert [row.coverage.venues for row in collect_archive_coverage(store, "cs.CV")] == [1]
    store.write_scholar("cs.CV", {}, source="S2")
    (store.root / "cs.CV" / "scholar.json").unlink()
    assert [row.coverage.venues for row in collect_archive_coverage(store, "cs.CV")] == [0]
    assert replace(ScholarRecord(), venue="x").venue == "x"


@pytest.mark.parametrize(
    ("names", "ids"),
    [
        pytest.param(("Ada Lovelace", "Alan M. Turing"), ("1", "2"), id="same-people"),
        pytest.param(("A. Lovelace", "Turing Alan"), ("1", "2"), id="initials-and-order"),
        pytest.param(("Ada Lovelace", "Grace Hopper"), ("1", None), id="another-person"),
        pytest.param(("Ada Lovelace", None), ("1", None), id="a-name-missing"),
        pytest.param(("Ada Lovelace", "?"), ("1", None), id="a-name-without-letters"),
        pytest.param(("Ada Love-Lace", "Alan Turing"), ("1", "2"), id="a-hyphen"),
        pytest.param(
            ("Ada Lovelace", "Alan Tur\N{LATIN SMALL LETTER DOTLESS I}ng"), ("1", "2"), id="a-dotless-i"
        ),
    ],
)
def test_author_ids_are_kept_where_the_names_are_the_papers(
    names: tuple[str | None, ...], ids: tuple[str | None, ...]
) -> None:
    record = ScholarRecord(author_ids=("1", "2"), author_names=names)

    assert checked_author_ids(record, ("Ada Lovelace", "Alan Turing")) == ids


def test_author_ids_go_when_the_lists_differ() -> None:
    record = ScholarRecord(author_ids=("1", "2"), author_names=("Ada Lovelace", "Alan Turing"))

    assert checked_author_ids(record, ("Ada Lovelace",)) is None
    assert checked_author_ids(replace(record, author_names=None), ("A", "B")) == ("1", "2")
