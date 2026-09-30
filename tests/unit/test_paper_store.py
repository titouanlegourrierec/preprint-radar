import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from preprint_radar.exceptions import StoreError
from preprint_radar.models import Listing, Paper
from preprint_radar.store.paper_store import PaperStore


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


@pytest.mark.parametrize(
    "payload", ["{not json", '{"counts": {}}', '{"counts": {}, "source": "S2", "generated_at": "soon"}']
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


def test_index_lists_archive_years(store: PaperStore, listing: Listing) -> None:
    store.save("cs.CV", listing.papers)
    store.write_archive("cs.CV", [_archived(listing, 2015), _archived(listing, 2015, 1)])

    index = json.loads(store.write_index().read_text(encoding="utf-8"))

    assert index["archives"] == {"cs.CV": [{"year": 2015, "count": 2}]}


def test_remove_days(store: PaperStore, listing: Listing) -> None:
    store.save("cs.CV", listing.papers)

    store.remove_days("cs.CV", [date(2026, 9, 24)])

    assert store.days("cs.CV") == [date(2026, 9, 25)]
