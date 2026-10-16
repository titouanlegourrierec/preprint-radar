import json
import os
import re
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from preprint_radar.exceptions import SchemaVersionError, StoreError
from preprint_radar.models import CodeRecord, Listing, Paper, ScholarRecord
from preprint_radar.store.paper_store import SCHEMA_VERSION, CountriesFile, PaperStore


@pytest.fixture
def store(tmp_path: Path) -> PaperStore:
    return PaperStore(tmp_path / "data")


def test_empty_store(store: PaperStore) -> None:
    assert store.categories() == []
    assert store.days("cs.CV") == []
    assert store.load_day("cs.CV", date(2026, 9, 25)) == []


def test_save_groups_papers_by_day(store: PaperStore, listing: Listing) -> None:
    written = store.save("cs.CV", listing.papers)

    assert written == [date(2026, 9, 25), date(2026, 9, 24)]
    assert store.categories() == ["cs.CV"]
    assert store.days("cs.CV") == written
    assert len(store.load_day("cs.CV", date(2026, 9, 25))) == 5
    assert (store.root / "cs.CV" / "2026-09-25.json").is_file()


def test_save_merges_with_existing_papers(store: PaperStore, listing: Listing) -> None:
    store.save("cs.CV", listing.papers)
    updated = replace(listing.papers[0], abstract="Now with an abstract.")

    store.save("cs.CV", [updated])

    day = store.load_day("cs.CV", updated.announced)
    assert len(day) == 5
    assert day[0].abstract == "Now with an abstract."
    assert sum(1 for _ in store.iter_papers()) == 7


def test_a_paper_announced_again_stays_on_its_first_day(store: PaperStore, listing: Listing) -> None:
    first = listing.papers[0]
    store.save("cs.CV", [first])
    again = replace(first, announced=first.announced + timedelta(days=4), abstract="Updated.")

    written = store.save("cs.CV", [again])

    assert written == [first.announced]
    assert store.days("cs.CV") == [first.announced]
    (stored,) = store.load_day("cs.CV", first.announced)
    assert stored.abstract == "Updated."


def test_a_paper_found_on_an_earlier_day_moves_there(store: PaperStore, listing: Listing) -> None:
    later = listing.papers[0]
    other = replace(listing.papers[1], announced=later.announced)
    store.save("cs.CV", [later, other])
    earlier = replace(later, announced=later.announced - timedelta(days=3))

    written = store.save("cs.CV", [earlier, replace(earlier, title="Twice in one batch")])

    assert written == [later.announced, earlier.announced]
    assert [paper.arxiv_id for paper in store.load_day("cs.CV", later.announced)] == [other.arxiv_id]
    (moved,) = store.load_day("cs.CV", earlier.announced)
    assert moved.title == "Twice in one batch"


def test_saving_a_paper_stored_twice_keeps_its_first_day(store: PaperStore, listing: Listing) -> None:
    paper = listing.papers[0]
    store.save("cs.CV", [paper])
    later = paper.announced + timedelta(days=1)
    path = store.root / "cs.CV" / f"{later.isoformat()}.json"
    copy = replace(paper, announced=later).to_record()
    path.write_text(
        json.dumps({"schema_version": 1, "category": "cs.CV", "date": later.isoformat(), "papers": [copy]}),
        encoding="utf-8",
    )

    store.save("cs.CV", [replace(paper, announced=later)])

    assert store.load_day("cs.CV", later) == []
    assert [stored.arxiv_id for stored in store.load_day("cs.CV", paper.announced)] == [paper.arxiv_id]


def test_save_refuses_an_invalid_day_file(store: PaperStore, listing: Listing) -> None:
    path = store.root / "cs.CV" / "2026-09-01.json"
    path.parent.mkdir(parents=True)
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(StoreError, match="Invalid papers file"):
        store.save("cs.CV", listing.papers)


def test_write_index(store: PaperStore, listing: Listing) -> None:
    store.save("cs.CV", listing.papers)

    index = json.loads(store.write_index().read_text(encoding="utf-8"))

    assert index["schema_version"] == 1
    assert index["categories"] == {
        "cs.CV": [{"date": "2026-09-25", "count": 5}, {"date": "2026-09-24", "count": 2}],
    }


def test_invalid_day_file_raises(store: PaperStore) -> None:
    path = store.root / "cs.CV" / "2026-09-25.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(StoreError, match="2026-09-25"):
        store.load_day("cs.CV", date(2026, 9, 25))


def _archived(listing: Listing, year: int, index: int = 0) -> Paper:
    paper = listing.papers[index]
    return replace(paper, arxiv_id=f"{year % 100:02d}01.{index:05d}", announced=date(year, 1, 1))


def test_citations_file_is_not_a_day(store: PaperStore, listing: Listing) -> None:
    store.save("cs.CV", listing.papers)
    store.write_citations("cs.CV", {"2609.30245": 3}, source="Semantic Scholar")

    assert store.days("cs.CV") == [date(2026, 9, 25), date(2026, 9, 24)]
    assert store.load_citations("cs.CV") == {"2609.30245": 3}
    assert store.load_citations("cs.LG") == {}
    citations = store.load_citation_counts("cs.CV")
    assert citations is not None
    assert citations.source == "Semantic Scholar"
    assert citations.generated_at.tzinfo is not None
    assert store.load_citation_counts("cs.LG") is None


def test_merged_citations_keep_the_date_of_the_last_refresh(store: PaperStore) -> None:
    store.merge_citations("cs.CV", {"2609.00001": 1}, source="Semantic Scholar")  # no file yet
    first = store.load_citation_counts("cs.CV")
    assert first is not None
    path = store.root / "cs.CV" / "citations.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**payload, "generated_at": "2026-09-27T05:41:00+00:00"}), encoding="utf-8")

    store.merge_citations("cs.CV", {"2609.00001": 4, "2609.00002": 0}, source="Other")

    merged = store.load_citation_counts("cs.CV")
    assert merged is not None
    assert merged.counts == {"2609.00001": 4, "2609.00002": 0}
    assert merged.generated_at.isoformat() == "2026-09-27T05:41:00+00:00"
    assert merged.source == "Semantic Scholar"


def test_a_weekly_refresh_keeps_what_each_paper_gained(store: PaperStore) -> None:
    week_ago = datetime(2026, 10, 4, 5, 41, tzinfo=UTC)
    store.write_citations("cs.CV", {"a": 10, "b": 5, "c": 7}, source="S2", now=week_ago)
    assert store.load_citation_gains("cs.CV") is None  # nothing to count from yet

    # A paper counted since, by the daily update, gains from its first count.
    store.merge_citations("cs.CV", {"d": 1}, source="S2")
    store.write_citations(
        "cs.CV", {"a": 14, "b": 5, "c": 6, "d": 3, "e": 2}, source="S2", now=week_ago + timedelta(days=7)
    )

    gains = store.load_citation_gains("cs.CV")
    assert gains is not None
    # Not b (no change), c (Semantic Scholar's count went down) or e (no count before).
    assert gains.gains == {"a": 4, "d": 2}
    assert gains.since == week_ago
    assert gains.generated_at == week_ago + timedelta(days=7)


def test_a_refresh_run_again_within_the_week_keeps_the_gains(store: PaperStore) -> None:
    week_ago = datetime(2026, 10, 4, 5, 41, tzinfo=UTC)
    store.write_citations("cs.CV", {"a": 10}, source="S2", now=week_ago)
    store.write_citations("cs.CV", {"a": 14}, source="S2", now=week_ago + timedelta(days=7))
    store.write_citations("cs.CV", {"a": 15}, source="S2", now=week_ago + timedelta(days=8))

    gains = store.load_citation_gains("cs.CV")
    assert gains is not None
    assert gains.gains == {"a": 4}
    assert store.load_citations("cs.CV") == {"a": 15}


def test_the_stars_each_paper_gained_in_a_week(store: PaperStore) -> None:
    week_ago = datetime(2026, 10, 11, 5, 41, tzinfo=UTC)
    url = "https://github.com/lab/{}"
    store.write_code(
        "cs.CV",
        {
            "a": CodeRecord(url.format("a"), stars=10),
            "b": CodeRecord(url.format("b"), stars=5),
            "c": CodeRecord(url.format("c"), stars=7),
            "e": CodeRecord("https://huggingface.co/lab/e", likes=2),
        },
        source="GitHub",
        now=week_ago,
    )
    first = store.load_code("cs.CV")
    assert first is not None
    assert first.since is None  # nothing to count from yet
    assert all(record.gained is None for record in first.papers.values())

    store.write_code(
        "cs.CV",
        {
            "a": CodeRecord(url.format("a"), stars=14, shared=True),
            "b": CodeRecord(url.format("b"), stars=4),
            "c": CodeRecord(url.format("other"), stars=70),  # another link: nothing gained yet
            "d": CodeRecord(url.format("d"), stars=3),  # new
            "e": CodeRecord("https://huggingface.co/lab/e", likes=5),
        },
        source="GitHub",
        now=week_ago + timedelta(days=7),
    )

    code = store.load_code("cs.CV")
    assert code is not None
    assert code.since == week_ago
    assert code.generated_at == week_ago + timedelta(days=7)
    assert code.source == "GitHub"
    assert {arxiv_id: record.gained for arxiv_id, record in code.papers.items()} == {
        "a": 4,
        "b": None,
        "c": None,
        "d": None,
        "e": None,
    }
    assert code.papers["a"] == CodeRecord(url.format("a"), stars=14, gained=4, shared=True)

    # Again within the week: the week's gains stay.
    store.write_code(
        "cs.CV",
        {"a": CodeRecord(url.format("a"), stars=15)},
        source="GitHub",
        now=week_ago + timedelta(days=8),
    )
    again = store.load_code("cs.CV")
    assert again is not None
    assert again.since == week_ago
    assert again.papers == {"a": CodeRecord(url.format("a"), stars=15, gained=4)}


def test_added_stars_keep_the_refresh_its_date_and_gains(store: PaperStore) -> None:
    week_ago = datetime(2026, 10, 4, 5, 41, tzinfo=UTC)
    url = "https://github.com/lab/{}"
    store.write_code("cs.CV", {"a": CodeRecord(url.format("a"), stars=10)}, source="GitHub", now=week_ago)
    refreshed = week_ago + timedelta(days=7)
    store.write_code("cs.CV", {"a": CodeRecord(url.format("a"), stars=14)}, source="GitHub", now=refreshed)

    store.add_code(
        "cs.CV",
        {
            "a": CodeRecord(url.format("a"), stars=14, shared=True),
            "b": CodeRecord(url.format("b"), stars=3),  # announced since
        },
    )

    code = store.load_code("cs.CV")
    assert code is not None
    # The next refresh counts the week's gains from this one.
    assert (code.generated_at, code.since, code.source) == (refreshed, week_ago, "GitHub")
    assert code.papers == {
        "a": CodeRecord(url.format("a"), stars=14, gained=4, shared=True),
        "b": CodeRecord(url.format("b"), stars=3),
    }


def test_stars_are_added_to_a_code_file_only(store: PaperStore) -> None:
    with pytest.raises(StoreError, match=r"No code\.json of cs\.CV to add stars to"):
        store.add_code("cs.CV", {"a": CodeRecord("https://github.com/lab/a", stars=1)})


def test_stars_over_a_broken_code_file_gain_nothing(
    store: PaperStore, caplog: pytest.LogCaptureFixture
) -> None:
    path = store.root / "cs.CV" / "code.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")

    store.write_code("cs.CV", {"a": CodeRecord("https://github.com/lab/a", stars=1)}, source="GitHub")

    code = store.load_code("cs.CV")
    assert code is not None
    assert code.papers["a"].gained is None
    assert "No stars gained: the former code.json of cs.CV does not load" in caplog.text


@pytest.mark.parametrize(
    "payload",
    [
        "{not json",
        '{"schema_version": 1, "papers": {}}',
        '{"schema_version": 1, "papers": {"a": {"stars": 3}}, "source": "G", "generated_at": "2026-10-11"}',
        '{"schema_version": 1, "papers": {"a": {"url": "u", "stars": "3"}}, "generated_at": "2026-10-11"}',
    ],
)
def test_invalid_code_file_raises(store: PaperStore, payload: str) -> None:
    path = store.root / "cs.CV" / "code.json"
    path.parent.mkdir(parents=True)
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(StoreError, match="Invalid code file"):
        store.load_code("cs.CV")


def test_a_code_file_of_another_schema_version_is_refused(store: PaperStore) -> None:
    path = store.root / "cs.CV" / "code.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema_version": SCHEMA_VERSION + 1, "papers": {}}), encoding="utf-8")

    with pytest.raises(SchemaVersionError):
        store.load_code("cs.CV")
    # Nor is it replaced: a newer pipeline wrote it.
    with pytest.raises(SchemaVersionError):
        store.write_code("cs.CV", {}, source="GitHub")


def test_a_refresh_over_broken_counts_writes_no_gains(
    store: PaperStore, caplog: pytest.LogCaptureFixture
) -> None:
    path = store.root / "cs.CV" / "citations.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")

    store.write_citations("cs.CV", {"a": 1}, source="S2")

    assert store.load_citations("cs.CV") == {"a": 1}
    assert store.load_citation_gains("cs.CV") is None
    assert "No citation gains: the former counts of cs.CV do not load" in caplog.text


@pytest.mark.parametrize(
    "payload",
    [
        "{not json",
        '{"schema_version": 1, "gains": {}}',
        '{"schema_version": 1, "gains": [], "since": "x", "generated_at": "y"}',
    ],
)
def test_invalid_citation_gains_file_raises(store: PaperStore, payload: str) -> None:
    path = store.root / "cs.CV" / "citation-gains.json"
    path.parent.mkdir(parents=True)
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(StoreError, match="Invalid citation gains file"):
        store.load_citation_gains("cs.CV")


@pytest.mark.parametrize(
    "payload",
    [
        "{not json",
        '{"schema_version": 1, "counts": {}}',
        '{"schema_version": 1, "counts": {}, "source": "S2", "generated_at": "soon"}',
    ],
)
def test_invalid_citations_file_raises(store: PaperStore, payload: str) -> None:
    path = store.root / "cs.CV" / "citations.json"
    path.parent.mkdir(parents=True)
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(StoreError, match="Invalid citations file"):
        store.load_citations("cs.CV")


def test_archive_is_written_by_year_and_replaced_as_a_whole(store: PaperStore, listing: Listing) -> None:
    store.write_archive(
        "cs.CV", [_archived(listing, 2015), _archived(listing, 2015, 1), _archived(listing, 2017)]
    )

    assert store.archive_years("cs.CV") == [2017, 2015]
    assert [paper.arxiv_id for paper in store.load_archive("cs.CV", 2015)] == ["1501.00001", "1501.00000"]
    assert store.days("cs.CV") == []  # archived papers never land in day files

    store.write_archive("cs.CV", [_archived(listing, 2017)])

    assert store.archive_years("cs.CV") == [2017]
    assert [paper.arxiv_id for paper in store.iter_archive("cs.CV")] == ["1701.00000"]


def test_a_file_that_would_not_change_is_not_written(store: PaperStore, listing: Listing) -> None:
    store.write_archive("cs.CV", [_archived(listing, 2015), _archived(listing, 2017)])
    unchanged = store.root / "cs.CV" / "archive" / "2015.json"
    changed = store.root / "cs.CV" / "archive" / "2017.json"
    for path in (unchanged, changed):
        os.utime(path, ns=(0, 0))

    store.write_archive("cs.CV", [_archived(listing, 2015), _archived(listing, 2017, 1)])

    # Its year unchanged, 2015's file is left as it was (CI-12); 2017's is written.
    assert unchanged.stat().st_mtime_ns == 0
    assert changed.stat().st_mtime_ns > 0
    assert [paper.arxiv_id for paper in store.load_archive("cs.CV", 2017)] == ["1701.00001"]


def test_index_lists_archive_years(store: PaperStore, listing: Listing) -> None:
    store.save("cs.CV", listing.papers)
    store.write_archive("cs.CV", [_archived(listing, 2015), _archived(listing, 2015, 1)])

    index = json.loads(store.write_index().read_text(encoding="utf-8"))

    assert index["archives"] == {"cs.CV": [{"year": 2015, "count": 2}]}


def test_the_most_cited_papers_of_the_last_12_months_are_written_apart(
    store: PaperStore, listing: Listing
) -> None:
    assert store.load_top_recent("cs.CV") is None
    assert list(store.iter_top_recent("cs.CV")) == []
    store.save("cs.CV", listing.papers)
    young = [replace(_archived(listing, 2025), announced=date(2025, 11, 3)), listing.papers[0]]

    store.write_top_recent("cs.CV", young, since=date(2025, 10, 1))

    top_recent = store.load_top_recent("cs.CV")
    assert top_recent is not None
    assert top_recent.since == date(2025, 10, 1)
    # Newest first, as the archive's years; neither an archive year nor a day file.
    assert [paper.arxiv_id for paper in top_recent.papers] == [listing.papers[0].arxiv_id, "2501.00000"]
    assert list(store.iter_top_recent("cs.CV")) == top_recent.papers
    assert store.archive_years("cs.CV") == []
    assert store.days("cs.CV") == [date(2026, 9, 25), date(2026, 9, 24)]
    index = json.loads(store.write_index().read_text(encoding="utf-8"))
    assert index["top_recent"] == {"cs.CV": {"since": "2025-10-01", "count": 2}}


@pytest.mark.parametrize(
    "payload",
    [
        "{not json",
        '{"schema_version": 1, "papers": []}',
        '{"schema_version": 1, "since": "last year", "papers": []}',
        '{"schema_version": 1, "since": "2025-10-01"}',
        '{"schema_version": 1, "since": "2025-10-01", "papers": [{"arxiv_id": 1}]}',
    ],
)
def test_invalid_top_recent_file_raises(store: PaperStore, payload: str) -> None:
    path = store.root / "cs.CV" / "top-recent.json"
    path.parent.mkdir(parents=True)
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(StoreError, match=r"Invalid (top-recent file|paper record)"):
        store.load_top_recent("cs.CV")


def test_remove_days(store: PaperStore, listing: Listing) -> None:
    store.save("cs.CV", listing.papers)

    store.remove_days("cs.CV", [date(2026, 9, 24)])

    assert store.days("cs.CV") == [date(2026, 9, 25)]


def _every_file(store: PaperStore, listing: Listing) -> None:
    """A store with a file of each kind: days, an archive year, counts, gains, ``scholar.json``."""
    week_ago = datetime(2026, 10, 4, 5, 41, tzinfo=UTC)
    store.save("cs.CV", listing.papers)
    store.write_archive("cs.CV", [_archived(listing, 2015)])
    store.write_citations("cs.CV", {"2609.30245": 1}, source="S2", now=week_ago)
    store.write_citations("cs.CV", {"2609.30245": 3}, source="S2", now=week_ago + timedelta(days=7))
    store.write_scholar("cs.CV", {"2609.30245": ScholarRecord(doi="10.1/x")}, source="S2")
    store.write_top_recent("cs.CV", listing.papers[:1], since=date(2025, 10, 1))


@pytest.mark.parametrize(
    ("name", "kind", "load"),
    [
        ("2026-09-25.json", "papers", lambda store: store.load_day("cs.CV", date(2026, 9, 25))),
        ("archive/2015.json", "papers", lambda store: store.load_archive("cs.CV", 2015)),
        ("citations.json", "citations", lambda store: store.load_citation_counts("cs.CV")),
        ("citation-gains.json", "citation gains", lambda store: store.load_citation_gains("cs.CV")),
        ("scholar.json", "scholar", lambda store: store.load_scholar("cs.CV")),
        ("top-recent.json", "top-recent", lambda store: store.load_top_recent("cs.CV")),
    ],
)
@pytest.mark.parametrize("version", [SCHEMA_VERSION + 1, None])
def test_a_file_of_another_schema_version_is_refused(
    store: PaperStore,
    listing: Listing,
    name: str,
    kind: str,
    load: Callable[[PaperStore], object],
    version: int | None,
) -> None:
    _every_file(store, listing)
    assert load(store)
    path = store.root / "cs.CV" / name
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = version
    path.write_text(json.dumps(payload), encoding="utf-8")

    expected = f"Invalid {kind} file {path}: schema_version is {version!r}, expected {SCHEMA_VERSION}"
    with pytest.raises(StoreError, match=re.escape(expected)):
        load(store)


def test_a_refresh_never_replaces_counts_of_another_schema_version(store: PaperStore) -> None:
    store.write_citations("cs.CV", {"a": 1}, source="S2")
    path = store.root / "cs.CV" / "citations.json"
    newer = path.read_text(encoding="utf-8").replace('"schema_version": 1', '"schema_version": 2')
    path.write_text(newer, encoding="utf-8")

    with pytest.raises(SchemaVersionError, match="schema_version is 2, expected 1"):
        store.write_citations("cs.CV", {"a": 2}, source="S2")

    assert path.read_text(encoding="utf-8") == newer


def test_save_never_relabels_a_store_of_another_schema_version(store: PaperStore, listing: Listing) -> None:
    store.save("cs.CV", listing.papers)
    path = store.root / "cs.CV" / "2026-09-24.json"
    newer = path.read_text(encoding="utf-8").replace('"schema_version": 1', '"schema_version": 2')
    path.write_text(newer, encoding="utf-8")

    with pytest.raises(StoreError, match="schema_version is 2, expected 1"):
        store.save("cs.CV", [replace(listing.papers[0], abstract="Rewritten.")])

    assert path.read_text(encoding="utf-8") == newer


def test_countries_are_written_sorted_and_read_back(store: PaperStore) -> None:
    now = datetime(2026, 10, 16, 5, tzinfo=UTC)
    store.write_countries("cs.CV", {"0b0000000": "US", "0a0000000": None}, source="OpenAlex", now=now)

    payload = json.loads((store.root / "cs.CV" / "countries.json").read_text(encoding="utf-8"))
    assert list(payload["institutions"]) == ["0a0000000", "0b0000000"]
    assert store.load_countries("cs.CV") == CountriesFile(
        {"0a0000000": None, "0b0000000": "US"}, "OpenAlex", now
    )
    assert store.load_countries("cs.RO") is None


@pytest.mark.parametrize(
    "payload",
    [
        "{not json",
        '{"schema_version": 1, "institutions": {}}',
        '{"schema_version": 1, "source": "O", "generated_at": "2026-10-16", "institutions": {"a": "usa"}}',
        '{"schema_version": 1, "source": "O", "generated_at": "2026-10-16", "institutions": {"a": 3}}',
    ],
)
def test_invalid_countries_file_raises(store: PaperStore, payload: str) -> None:
    path = store.root / "cs.CV" / "countries.json"
    path.parent.mkdir(parents=True)
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(StoreError, match="Invalid countries file"):
        store.load_countries("cs.CV")


def test_a_countries_file_of_another_schema_version_is_refused(store: PaperStore) -> None:
    path = store.root / "cs.CV" / "countries.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema_version": SCHEMA_VERSION + 1}), encoding="utf-8")

    with pytest.raises(SchemaVersionError):
        store.load_countries("cs.CV")
