import csv
import json
from pathlib import Path

import pytest

from preprint_radar.models import Listing
from preprint_radar.store.export import CSV_LIST_SEPARATOR, ExportFormat, export_papers


def test_json_export_round_trips(listing: Listing, tmp_path: Path) -> None:
    path = tmp_path / "nested" / "papers.json"
    export_papers(listing.papers, path, ExportFormat.JSON)

    records = json.loads(path.read_text(encoding="utf-8"))
    assert records == [paper.to_record() for paper in listing.papers]


def test_csv_export_leaves_out_the_author_affiliation_indices(listing: Listing, tmp_path: Path) -> None:
    path = tmp_path / "papers.csv"

    export_papers(listing.papers, path, ExportFormat.CSV)

    with path.open(encoding="utf-8", newline="") as file:
        assert "author_affiliations" not in (csv.DictReader(file).fieldnames or ())


def test_csv_export_joins_list_fields(listing: Listing, tmp_path: Path) -> None:
    path = tmp_path / "papers.csv"
    export_papers(listing.papers, path, ExportFormat.CSV)

    with path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == len(listing.papers)
    first = listing.papers[0]
    assert rows[0]["arxiv_id"] == first.arxiv_id
    assert rows[0]["authors"] == CSV_LIST_SEPARATOR.join(first.authors)
    assert rows[0]["pdf_url"] == first.pdf_url


@pytest.mark.parametrize(
    ("filename", "expected"),
    [("a.json", ExportFormat.JSON), ("a.CSV", ExportFormat.CSV), ("a.txt", None), ("a", None)],
)
def test_format_from_path(filename: str, expected: ExportFormat | None) -> None:
    assert ExportFormat.from_path(Path(filename)) is expected
