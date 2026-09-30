import json
import logging
import runpy
from collections.abc import Mapping
from datetime import date
from pathlib import Path

import pytest
from rich.console import Console

from preprint_radar.archive import ArchiveClients, ArchiveReport
from preprint_radar.catalog import Catalog
from preprint_radar.cli import main
from preprint_radar.exceptions import FetchError, NotFoundError
from preprint_radar.http import HttpClient
from preprint_radar.models import Listing, Paper
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
def test_update_populates_store(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    data_dir = tmp_path / "data"

    assert main(["update", "--data-dir", str(data_dir), "--crawl-delay", "0"]) == 0

    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    assert [day["count"] for day in index["categories"]["cs.CV"]] == [5, 2]
    assert "cs.CV: 7 listed, 7 new" in capsys.readouterr().out
    assert "No contact given" in caplog.text


@pytest.mark.usefixtures("offline")
def test_backfill_populates_store(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    data_dir = tmp_path / "data"

    args = ["--since", "2026-08-31", "--until", "2026-09-02", "--max-html", "0", "--crawl-delay", "0"]
    assert main(["backfill", "--data-dir", str(data_dir), *args]) == 0

    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    assert index["categories"]["cs.CV"] == [{"date": "2026-09-01", "count": 4}]
    assert "cs.CV: 4 listed, 4 new, 4 abstracts" in capsys.readouterr().out
    assert "No contact given" in caplog.text


@pytest.mark.usefixtures("offline")
@pytest.mark.parametrize(
    "command", [["update"], ["backfill", "--since", "2026-09-01", "--until", "2026-09-01"]]
)
def test_a_contact_silences_the_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, command: list[str]
) -> None:
    args = [*command, "--data-dir", str(tmp_path / "data"), "--crawl-delay", "0", "--max-html", "0"]

    assert main(["--contact", "https://example.org/radar", *args]) == 0

    assert "No contact given" not in caplog.text


def test_fetch_without_papers_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr("preprint_radar.cli.fetch_listing", lambda *_, **__: Listing(papers=()))
    output = tmp_path / "papers.json"

    assert main(["fetch", "--output", str(output)]) == 0

    assert not output.exists()
    assert "No papers left to export" in caplog.text


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


def test_stats_draws_tables_in_a_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("preprint_radar.cli.console", Console(force_terminal=True, width=120))
    store = PaperStore(tmp_path / "data")
    store.save("cs.CV", [Paper(arxiv_id="2609.00001", announced=date(2026, 9, 25), title="T", authors=())])
    resnet = Paper(
        arxiv_id="1512.03385", announced=date(2015, 12, 10), title="ResNet", authors=("Kaiming He",)
    )
    store.write_archive("cs.CV", [resnet])

    assert main(["stats", "--data-dir", str(store.root)]) == 0

    out = capsys.readouterr().out
    assert "\x1b[" in out  # styled
    assert "cs.CV: 1 paper over 1 day" in out
    assert "cs.CV archive: 1 paper over 1 year" in out


def test_stats_skips_categories_without_papers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    store = PaperStore(tmp_path / "data")
    store.save("cs.CV", [Paper(arxiv_id="2609.00001", announced=date(2026, 9, 25), title="T", authors=())])

    assert main(["stats", "--data-dir", str(store.root), "-c", "cs.CV", "-c", "cs.LG"]) == 0

    assert capsys.readouterr().out.startswith("cs.CV: 1 paper over 1 day")
    assert "No stored papers for cs.LG" in caplog.text


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


@pytest.fixture
def archive_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, object]]]:
    """Record the calls to ``update_archive`` instead of reaching OAI-PMH and Semantic Scholar."""
    calls: list[tuple[str, dict[str, object]]] = []

    def update_archive(category: str, **options: object) -> ArchiveReport:
        calls.append((category, options))
        return ArchiveReport(
            category=category,
            candidates=100,
            coverage=0.99,
            threshold=19.5,
            archived=10,
            entered=2,
            left=1,
            pruned_days=0,
            written=False,
        )

    monkeypatch.setattr("preprint_radar.cli.update_archive", update_archive)
    return calls


def test_archive_passes_its_options_and_reports(
    tmp_path: Path,
    archive_calls: list[tuple[str, dict[str, object]]],
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    args = ["archive", "--data-dir", str(tmp_path / "data"), "--catalog-dir", str(tmp_path / "catalog")]

    assert main([*args, "--budget", "10", "--prune", "--dry-run"]) == 0

    [(category, options)] = archive_calls
    assert category == "cs.CV"
    assert (options["budget"], options["prune"], options["dry_run"]) == (10, True, True)
    assert isinstance(options["catalog"], Catalog)
    assert options["catalog"].path == tmp_path / "catalog" / "cs.CV.jsonl.gz"
    assert isinstance(options["clients"], ArchiveClients)
    assert options["clients"].citations_key is None
    assert "No Semantic Scholar API key" in caplog.text
    assert capsys.readouterr().out == (
        "cs.CV: 10 archived papers (2 in, 1 out), threshold 19.5 citations a year, citation counts "
        "for 99.0% of 100 papers, 0 day files pruned (dry run: nothing written)\n"
    )


def test_archive_uses_the_semantic_scholar_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    archive_calls: list[tuple[str, dict[str, object]]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "test-key")
    caplog.set_level(logging.INFO)

    assert main(["archive", "--data-dir", str(tmp_path / "data"), "-c", "cs.CV", "-c", "cs.LG"]) == 0

    assert [category for category, _ in archive_calls] == ["cs.CV", "cs.LG"]
    clients = archive_calls[0][1]["clients"]
    assert isinstance(clients, ArchiveClients)
    assert clients.citations_key == "test-key"
    assert "Semantic Scholar: requests with an API key" in caplog.text
    assert "test-key" not in caplog.text
    assert "No Semantic Scholar API key" not in caplog.text


def test_runs_as_a_module(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.argv", ["preprint-radar", "--version"])

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("preprint_radar", run_name="__main__")

    assert exc_info.value.code == 0
    assert capsys.readouterr().out.startswith("preprint-radar ")
