import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from preprint_radar.exceptions import StoreError
from preprint_radar.models import Listing
from preprint_radar.store import PaperStore


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
