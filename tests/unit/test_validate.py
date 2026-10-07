import json
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from preprint_radar.models import Paper
from preprint_radar.store.paper_store import PaperStore
from preprint_radar.store.validate import Finding, Level, validate_store

DAY = date(2026, 9, 25)


BASE = Paper(
    arxiv_id="2609.00000",
    announced=DAY,
    title="T",
    authors=("Ada Lovelace", "Bob Smith"),
    affiliations=("MIT", "Stanford University"),
    author_affiliations=((0,), (1,)),
)


def _paper(arxiv_id: str, **fields: object) -> Paper:
    return replace(BASE, arxiv_id=arxiv_id, **fields)


@pytest.fixture
def store(tmp_path: Path) -> PaperStore:
    """A valid store: two days, one archive year, citation counts and the index."""
    store = PaperStore(tmp_path / "data")
    store.save("cs.CV", [_paper("2609.00001"), _paper("2609.00002", announced=date(2026, 9, 24))])
    store.write_archive(
        "cs.CV", [_paper("1706.03762", announced=date(2017, 6, 12), affiliations=("IIT@MIT", "Google"))]
    )
    store.write_citations("cs.CV", {"2609.00001": 3, "1706.03762": 100_000}, source="test")
    store.write_index()
    return store


def _day_file(store: PaperStore, day: date = DAY) -> Path:
    return store.root / "cs.CV" / f"{day.isoformat()}.json"


def _edit(path: Path, change: Callable[[Any], None]) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    change(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _messages(store: PaperStore, level: Level = Level.ERROR) -> list[str]:
    return [
        f"{finding.path}: {finding.message}"
        for finding in validate_store(store).findings
        if finding.level is level
    ]


def test_a_valid_store_has_no_findings(store: PaperStore) -> None:
    report = validate_store(store)

    assert report.findings == []
    assert report.summary() == "3 papers in 5 files: 0 errors, 0 warnings"


def test_files_that_do_not_load(store: PaperStore) -> None:
    _day_file(store).write_text("{", encoding="utf-8")
    _day_file(store, date(2026, 9, 24)).write_text("[]", encoding="utf-8")

    messages = _messages(store)

    assert messages[0].startswith("data/cs.CV/2026-09-25.json: not valid JSON: Expecting property name")
    assert messages[1:] == [
        "data/cs.CV/2026-09-24.json: no 'papers' list",
        "data/cs.CV/citations.json: 1 counts of papers that are not stored, e.g. 2609.00001",
        "data/index.json: days or counts differ from the day files",
    ]


def test_headers_records_and_days(store: PaperStore) -> None:
    def change(payload: dict[str, Any]) -> None:
        payload.update(schema_version=2, category="cs.LG", date="2026-09-26")
        payload["papers"][0]["author_affiliations"] = [[0]]
        payload["papers"].append({"title": "no id"})
        payload["papers"].append(_paper("2609.00003", announced=date(2026, 9, 26)).to_record())

    _edit(_day_file(store), change)

    assert _messages(store) == [
        "data/cs.CV/2026-09-25.json: 'schema_version' is 2, expected 1",
        "data/cs.CV/2026-09-25.json: 'category' is 'cs.LG', expected 'cs.CV'",
        "data/cs.CV/2026-09-25.json: 'date' is '2026-09-26', expected '2026-09-25'",
        (
            "data/cs.CV/2026-09-25.json: Invalid paper record '2609.00001': "
            "'author_affiliations' must have one entry per author"
        ),
        "data/cs.CV/2026-09-25.json: Invalid paper record None: 'arxiv_id'",
        "data/cs.CV/2026-09-25.json: 2609.00003: announced 2026-09-26",
        "data/cs.CV/citations.json: 1 counts of papers that are not stored, e.g. 2609.00001",
        "data/index.json: days or counts differ from the day files",
    ]


def test_a_paper_stored_on_two_days(store: PaperStore) -> None:
    # Written by hand: the store itself keeps a paper on its first day.
    copy = _paper("2609.00001", announced=date(2026, 9, 24)).to_record()
    _edit(_day_file(store, date(2026, 9, 24)), lambda payload: payload["papers"].append(copy))
    store.write_index()

    assert _messages(store) == ["data/cs.CV/2026-09-24.json: 2609.00001: stored on 2026-09-25 too"]


@pytest.mark.parametrize(
    "affiliation",
    ["MIT, jane.doe@mit.edu", "https://mit.edu", "MIT, lab (at) mit.edu", "MIT{jane.doe, john.roe}"],
)
def test_contact_details_in_affiliations(store: PaperStore, affiliation: str) -> None:
    store.save("cs.CV", [_paper("2609.00001", affiliations=(affiliation, "Stanford University"))])

    assert _messages(store) == [
        f"data/cs.CV/2026-09-25.json: 2609.00001: contact details in affiliation {affiliation!r}"
    ]


def test_archive_years(store: PaperStore) -> None:
    def change(payload: dict[str, Any]) -> None:
        payload["papers"].append(payload["papers"][0])
        payload["papers"].append(
            _paper(
                "1706.00001",
                announced=date(2018, 1, 1),
                affiliations=("www.example.org",),
                author_affiliations=None,
            ).to_record()
        )

    _edit(store.root / "cs.CV" / "archive" / "2017.json", change)

    assert _messages(store) == [
        "data/cs.CV/archive/2017.json: 1706.03762: archived twice",
        "data/cs.CV/archive/2017.json: 1706.00001: announced 2018-01-01",
        "data/cs.CV/archive/2017.json: 1706.00001: contact details in affiliation 'www.example.org'",
        "data/index.json: years or counts differ from the archive files",
    ]


def test_citation_counts(store: PaperStore) -> None:
    store.write_citations("cs.CV", {"2609.00001": 3, "2609.99999": 1}, source="test")
    assert _messages(store) == [
        "data/cs.CV/citations.json: 1 counts of papers that are not stored, e.g. 2609.99999"
    ]

    (store.root / "cs.CV" / "citations.json").write_text("{}", encoding="utf-8")
    assert _messages(store)[0].startswith("data/cs.CV/citations.json: Invalid citations file")


def test_citation_gains(store: PaperStore) -> None:
    path = store.root / "cs.CV" / "citation-gains.json"
    payload = {
        "schema_version": 1,
        "since": "2026-10-04T05:41:00+00:00",
        "generated_at": "2026-10-11T05:41:00+00:00",
    }
    path.write_text(json.dumps({**payload, "gains": {"2609.00001": 2}}), encoding="utf-8")
    assert validate_store(store).findings == []

    path.write_text(json.dumps({**payload, "gains": {"2609.00001": 2, "2609.99999": 1}}), encoding="utf-8")
    assert _messages(store) == []
    assert _messages(store, Level.WARNING) == [
        "data/cs.CV/citation-gains.json: 1 gains of papers that are not stored, e.g. 2609.99999"
    ]

    path.write_text("{}", encoding="utf-8")
    assert _messages(store)[0].startswith("data/cs.CV/citation-gains.json: Invalid citation gains file")


@pytest.mark.parametrize("name", ["citations.json", "citation-gains.json", "scholar.json"])
def test_a_file_of_another_schema_version(store: PaperStore, name: str) -> None:
    path = store.root / "cs.CV" / name
    path.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")

    [message] = _messages(store)

    assert message.startswith(f"data/cs.CV/{name}: Invalid ")
    assert message.endswith(f"{path}: schema_version is 2, expected 1")


def test_without_citation_counts(store: PaperStore) -> None:
    (store.root / "cs.CV" / "citations.json").unlink()

    assert validate_store(store).findings == []


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (None, "data/index.json: missing"),
        ("{", "data/index.json: not valid JSON: Expecting property name enclosed in double quotes"),
        ("[]", "data/index.json: not a JSON object"),
    ],
)
def test_an_unreadable_index(store: PaperStore, content: str | None, expected: str) -> None:
    index = store.root / "index.json"
    if content is None:
        index.unlink()
    else:
        index.write_text(content, encoding="utf-8")

    (message,) = _messages(store)
    assert message.startswith(expected)


def test_an_index_out_of_date(store: PaperStore) -> None:
    def change(index: dict[str, Any]) -> None:
        index["schema_version"] = 0
        index["categories"]["cs.CV"][0]["count"] = 5
        del index["archives"]

    _edit(store.root / "index.json", change)

    assert _messages(store) == [
        "data/index.json: 'schema_version' is 0, expected 1",
        "data/index.json: days or counts differ from the day files",
        "data/index.json: years or counts differ from the archive files",
    ]


def test_heuristic_rules_only_warn(store: PaperStore) -> None:
    store.save(
        "cs.CV",
        [
            _paper("2609.00001", affiliations=("Bob Smith", "MIT")),
            _paper("2609.00003", author_affiliations=(None, (0, 1))),
            _paper("2609.00004", affiliations=("MIT", "Code")),
            # Named by the registry: a collective that signs as an author.
            _paper("2609.00005", affiliations=("Bob Smith", "MIT"), institutions=("Bob Smith", None)),
        ],
    )
    store.write_index()

    report = validate_store(store)

    assert report.errors == []
    assert _messages(store, Level.WARNING) == [
        "data/cs.CV/2026-09-25.json: 2609.00001: affiliation 'Bob Smith' only names authors",
        "data/cs.CV/2026-09-25.json: 2609.00003: only the last author is placed, at every affiliation",
        "data/cs.CV/2026-09-25.json: 2609.00004: `reclean` would change its affiliations",
    ]
    assert str(report.warnings[0]) == (
        "WARNING data/cs.CV/2026-09-25.json: 2609.00001: affiliation 'Bob Smith' only names authors"
    )


def test_finding_line() -> None:
    assert str(Finding(Level.ERROR, "data/index.json", "missing")) == "ERROR data/index.json: missing"
