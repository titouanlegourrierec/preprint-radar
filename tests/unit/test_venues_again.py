from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from preprint_radar.cli import main
from preprint_radar.models import Paper
from preprint_radar.store.paper_store import PaperStore
from preprint_radar.store.venues import VenuesReport, detect_venues_again


def _paper(arxiv_id: str, announced: date, comments: str | None, venue: str | None) -> Paper:
    return Paper(
        arxiv_id=arxiv_id,
        announced=announced,
        title="T",
        authors=("Ada Lovelace",),
        comments=comments,
        venue=venue,
    )


def _store(tmp_path: Path) -> PaperStore:
    store = PaperStore(tmp_path / "data")
    store.save(
        "cs.CV",
        [
            # Read wrongly by an older detection, and right already.
            _paper("2609.00001", date(2026, 9, 24), "Comparison with CVPR 2025 methods", "CVPR 2025"),
            _paper("2609.00002", date(2026, 9, 25), "Accepted to ECCV 2026", "ECCV 2026"),
        ],
    )
    store.save("cs.CV", [_paper("2609.00003", date(2026, 9, 28), "10 pages", None)])
    store.write_archive("cs.CV", [_paper("1511.00001", date(2015, 11, 2), "accepted by CVPR16", "CVPR")])
    return store


def test_detects_the_venues_of_day_files_and_archive_again(tmp_path: Path) -> None:
    store = _store(tmp_path)

    report = detect_venues_again(store, "cs.CV")

    assert report == VenuesReport(
        category="cs.CV", papers=4, before=3, after=2, changed=2, days=1, archive=True
    )
    assert [paper.venue for paper in store.load_day("cs.CV", date(2026, 9, 24))] == [None]
    assert [paper.venue for paper in store.iter_archive("cs.CV")] == ["CVPR 2016"]
    # Nothing more the second time, and nothing written.
    again = detect_venues_again(store, "cs.CV")
    assert (again.changed, again.days, again.archive) == (0, 0, False)


def test_leaves_an_up_to_date_archive_unwritten(tmp_path: Path) -> None:
    store = PaperStore(tmp_path / "data")
    paper = _paper("1511.00001", date(2015, 11, 2), "accepted by CVPR16", "CVPR 2016")
    store.write_archive("cs.CV", [paper])
    path = tmp_path / "data" / "cs.CV" / "archive" / "2015.json"
    path.write_text(path.read_text() + "\n")  # a mark that a rewrite would drop

    assert detect_venues_again(store, "cs.CV").archive is False
    assert path.read_text().endswith("\n\n")
    assert replace(paper) == next(store.iter_archive("cs.CV"))


def test_cli_reports_each_category(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _store(tmp_path)

    assert main(["venues", "--data-dir", str(tmp_path / "data")]) == 0

    assert (
        "cs.CV: 2 of 4 papers changed, in 1 day files and the archive; venues 3 -> 2"
        in capsys.readouterr().out
    )


def test_marks_the_papers_their_comments_say_were_withdrawn(tmp_path: Path) -> None:
    store = PaperStore(tmp_path / "data")
    store.save(
        "cs.CV",
        [_paper("2609.00004", date(2026, 9, 24), "Withdrawn by the authors to fix an error", None)],
    )

    detect_venues_again(store, "cs.CV")

    [paper] = store.iter_papers("cs.CV")
    assert paper.withdrawn
