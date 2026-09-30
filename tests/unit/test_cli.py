import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path

import pytest

from preprint_radar.cli import main
from preprint_radar.exceptions import FetchError, NotFoundError
from preprint_radar.http import HttpClient
from preprint_radar.models import Paper
from preprint_radar.store import PaperStore


@pytest.fixture
def offline(
    monkeypatch: pytest.MonkeyPatch,
    listing_html: str,
    catchup_html: str,
    catchup_empty_html: str,
    api_feed: str,
) -> None:
    """Serve fixtures instead of hitting arxiv.org."""

    def get_text(_: HttpClient, url: str, *, params: Mapping[str, str | int] | None = None) -> str:
        del params
        if "/list/" in url:
            return listing_html
        if "/catchup/" in url:
            return catchup_html if url.endswith("/2026-09-01") else catchup_empty_html
        if "export.arxiv.org" in url:
            return api_feed
        if "api.ror.org" in url:
            return '{"items": []}'
        raise NotFoundError(url)

    monkeypatch.setattr(HttpClient, "get_text", get_text)
    monkeypatch.setattr("preprint_radar.cli.ROR_DELAY_SECONDS", 0)


@pytest.mark.usefixtures("offline")
def test_fetch_writes_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "papers.json"

    assert main(["fetch", "--output", str(output)]) == 0

    assert len(json.loads(output.read_text(encoding="utf-8"))) == 7
    stdout = capsys.readouterr().out
    assert "2026-09-25: 5 papers" in stdout
    assert "2026-09-24: 2 papers" in stdout


@pytest.mark.usefixtures("offline")
def test_fetch_defaults_to_dated_file_in_exports_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["fetch", "--format", "csv"]) == 0

    assert (tmp_path / "exports" / "cs.CV_2026-09-25.csv").is_file()


@pytest.mark.usefixtures("offline")
def test_fetch_applies_filters(tmp_path: Path) -> None:
    output = tmp_path / "papers.json"

    assert main(["fetch", "-o", str(output), "--latest-only", "--exclude-cross-lists"]) == 0

    records = json.loads(output.read_text(encoding="utf-8"))
    assert len(records) == 3
    assert {record["announced"] for record in records} == {"2026-09-25"}


@pytest.mark.usefixtures("offline")
def test_update_populates_store(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data_dir = tmp_path / "data"

    assert main(["update", "--data-dir", str(data_dir), "--crawl-delay", "0"]) == 0

    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    assert [day["count"] for day in index["categories"]["cs.CV"]] == [5, 2]
    assert "cs.CV: 7 listed, 7 new" in capsys.readouterr().out


@pytest.mark.usefixtures("offline")
def test_backfill_populates_store(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data_dir = tmp_path / "data"

    args = ["--since", "2026-08-31", "--until", "2026-09-02", "--max-html", "0", "--crawl-delay", "0"]
    assert main(["backfill", "--data-dir", str(data_dir), *args]) == 0

    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    assert index["categories"]["cs.CV"] == [{"date": "2026-09-01", "count": 4}]
    assert "cs.CV: 4 listed, 4 new, 4 abstracts" in capsys.readouterr().out


def test_backfill_rejects_reversed_dates(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["backfill", "--since", "2026-09-02", "--until", "2026-09-01"])

    assert exc_info.value.code == 2
    assert "--since must not be after --until" in capsys.readouterr().err


def test_backfill_rejects_malformed_dates(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["backfill", "--since", "01/09/2026"])

    assert "expected YYYY-MM-DD" in capsys.readouterr().err


@pytest.mark.usefixtures("offline")
def test_stats_reports_coverage(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data_dir = tmp_path / "data"
    assert main(["update", "--data-dir", str(data_dir), "--crawl-delay", "0", "--max-html", "0"]) == 0
    capsys.readouterr()

    assert main(["stats", "--data-dir", str(data_dir)]) == 0

    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0] == "cs.CV: 7 papers over 2 days"
    assert lines[2].split() == ["2026-09-25", "5", "0", "0", "0", "5", "0", "0", "2", "0"]
    assert lines[-3].startswith("total")
    assert lines[-2].startswith("abstracts ")
    assert "archive" not in out  # no archive, no citation counts
    assert "citation counts:" not in out


def test_stats_reports_the_archive_and_citation_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = PaperStore(tmp_path / "data")
    resnet = Paper(
        arxiv_id="1512.03385", announced=date(2015, 12, 10), title="ResNet", authors=("Kaiming He",)
    )
    store.write_archive("cs.CV", [resnet])
    store.write_citations("cs.CV", {"1512.03385": 240_000}, source="Semantic Scholar")

    assert main(["stats", "--data-dir", str(store.root)]) == 0

    reports = capsys.readouterr().out.split("\n\n")
    assert reports[0].startswith("cs.CV archive: 1 paper over 1 year\nyear")
    assert reports[1].startswith("cs.CV citation counts: 1 from Semantic Scholar, ")


def test_stats_on_an_empty_store(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    assert main(["stats", "--data-dir", str(tmp_path / "nowhere")]) == 1
    assert "is empty" in caplog.text


def test_errors_are_reported(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    def fail(*_: object, **__: object) -> str:
        raise FetchError("arxiv.org is down")

    monkeypatch.setattr(HttpClient, "get_text", fail)

    assert main(["fetch"]) == 1
    assert "arxiv.org is down" in caplog.text


def test_rejects_invalid_category(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["fetch", "--category", "not a category"])

    assert exc_info.value.code == 2
    assert "Invalid arXiv category" in capsys.readouterr().err


@pytest.mark.usefixtures("offline")
def test_institutions_catches_up_on_the_store(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data_dir = tmp_path / "data"
    assert main(["update", "--data-dir", str(data_dir), "--crawl-delay", "0", "--max-ror", "0"]) == 0
    capsys.readouterr()

    assert main(["institutions", "--data-dir", str(data_dir)]) == 0

    assert "still pending" in capsys.readouterr().out
    records = [
        record
        for day in (data_dir / "cs.CV").glob("*.json")
        for record in json.loads(day.read_text(encoding="utf-8"))["papers"]
    ]
    assert all((record["institutions"] is None) == (not record["affiliations"]) for record in records)
