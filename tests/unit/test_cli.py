import json
import logging
import os
import runpy
import signal
import time
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from rich.console import Console

from preprint_radar.archive.catalog import Catalog
from preprint_radar.archive.update import ArchiveClients, ArchiveReport
from preprint_radar.cli import main
from preprint_radar.collect import CitationsReport, HtmlReading, Stop, UpdateReport
from preprint_radar.exceptions import FetchError, NotFoundError
from preprint_radar.http import HttpClient
from preprint_radar.models import Listing, Paper
from preprint_radar.sources.arxiv_html import EXTRACTOR_VERSION, PageCache
from preprint_radar.store.paper_store import PaperStore


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


def test_backfill_writes_the_index_even_when_it_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, catchup_html: str
) -> None:
    def get_text(_: HttpClient, url: str, *, params: Mapping[str, str | int] | None = None) -> str:
        del params
        # Days are fetched from the latest: 2026-09-01 is saved, then arXiv fails.
        if url.endswith("/catchup/cs.CV/2026-09-01"):
            return catchup_html
        raise FetchError("arxiv.org is down")

    monkeypatch.setattr(HttpClient, "get_text", get_text)
    data_dir = tmp_path / "data"

    args = ["--since", "2026-08-31", "--until", "2026-09-01", "--max-html", "0", "--crawl-delay", "0"]
    assert main(["backfill", "--data-dir", str(data_dir), *args]) == 1

    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    assert index["categories"]["cs.CV"] == [{"date": "2026-09-01", "count": 4}]


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


def test_stats_counts_signs_of_wrong_affiliations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    store = PaperStore(tmp_path / "data")
    store.save(
        "cs.CV",
        [
            Paper(
                arxiv_id="2609.00001",
                announced=date(2026, 9, 25),
                title="T",
                authors=("Ada Lovelace",),
                affiliations=("Code", "Nanjing University of Posts and"),
            )
        ],
    )

    assert main(["stats", "--affiliations", "--data-dir", str(store.root), "-c", "cs.CV", "-c", "cs.LG"]) == 0

    lines = [line.strip() for line in capsys.readouterr().out.splitlines()]
    assert lines[:2] == ["cs.CV: affiliations of the day files", "2 affiliation strings in 1 paper"]
    assert "2609.00001: Code" in lines
    assert "2609.00001: Nanjing University of Posts and" in lines
    assert "No stored papers for cs.LG" in caplog.text


def test_stats_counts_them_in_what_the_page_cache_gives_today(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    store = PaperStore(tmp_path / "data")
    url = "https://arxiv.org/html/2609.00001v1"
    store.save(
        "cs.CV",
        [
            Paper(
                arxiv_id="2609.00001",
                announced=date(2026, 9, 25),
                title="T",
                authors=("Ada Lovelace",),
                affiliations=("Code",),
                html_url=url,
            )
        ],
    )
    cache = tmp_path / "cache"
    options = ["stats", "--affiliations", "--data-dir", str(store.root), "--page-cache-dir", str(cache)]

    assert main(options) == 0
    assert "The page cache " in caplog.text
    assert "holds no page of cs.CV" in caplog.text
    capsys.readouterr()

    page = (
        '<article class="ltx_document"><div class="ltx_authors">'
        '<span class="ltx_creator ltx_role_author"><span class="ltx_personname">Ada Lovelace</span>'
        '<span class="ltx_contact ltx_role_affiliation">Stanford University</span></span></div></article>'
    )
    PageCache(cache).put(url, page)
    assert main(options) == 0

    reports = capsys.readouterr().out.split("\n\n")
    assert [report.splitlines()[0] for report in reports] == [
        "cs.CV: affiliations of the day files",
        "cs.CV: the papers with a cached page, as stored",
        f"cs.CV: the same papers, as extracted today (version {EXTRACTOR_VERSION})",
    ]
    assert "2609.00001: Code" in reports[1]
    assert "2609.00001: Code" not in reports[2]
    assert store.load_day("cs.CV", date(2026, 9, 25))[0].affiliations == ("Code",)  # nothing written

    assert main([*options, "--changes"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"cs.CV, version {EXTRACTOR_VERSION}: 1 of 1 cached papers change, 1 losing words",
        "2609.00001  (who is where changes)",
        "  - Code",
        "  + Stanford University",
        "  ! words lost: code",
    ]


def test_stats_draws_signs_in_a_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("preprint_radar.cli.console", Console(force_terminal=True, width=160))
    store = PaperStore(tmp_path / "data")
    store.save(
        "cs.CV",
        [
            Paper(
                arxiv_id="2609.00001",
                announced=date(2026, 9, 25),
                title="T",
                authors=(),
                affiliations=("Code",),
            )
        ],
    )

    assert main(["stats", "--affiliations", "--data-dir", str(store.root)]) == 0

    out = capsys.readouterr().out
    assert "\x1b[" in out
    assert "2609.00001: Code" in out


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
        "for 99.0% of 100 papers, 0 papers' comments refreshed, 0 day files pruned "
        "(dry run: nothing written)\n"
    )


def test_archive_fails_below_the_coverage_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def gated(category: str, **_: object) -> ArchiveReport:
        return ArchiveReport(
            category=category,
            candidates=100,
            coverage=0.5,
            threshold=0.0,
            archived=10,
            entered=0,
            left=0,
            pruned_days=0,
            written=True,
        )

    monkeypatch.setattr("preprint_radar.cli.update_archive", gated)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    args = ["archive", "--data-dir", str(tmp_path / "data"), "--catalog-dir", str(tmp_path / "catalog")]

    assert main(args) == 1
    assert "Too few citation counts: the archive of cs.CV was not updated" in caplog.text
    assert "::error title=Archive not updated::Too few citation counts. cs.CV: " in capsys.readouterr().out


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


def test_citations_fetches_the_missing_counts_of_each_category(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, bool, str | None, float | None]] = []

    def update_citation_counts(
        _: PaperStore,
        category: str,
        __: HttpClient,
        *,
        key: str | None,
        refresh: bool,
        max_seconds: float | None,
    ) -> CitationsReport:
        calls.append((category, refresh, key, max_seconds))
        return CitationsReport(category=category, asked=3, found=3)

    monkeypatch.setattr("preprint_radar.cli.update_citation_counts", update_citation_counts)
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "test-key")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    store = PaperStore(tmp_path / "data")
    store.save("cs.CV", [Paper(arxiv_id="2609.00001", announced=date(2026, 9, 25), title="T", authors=())])

    assert main(["citations", "--data-dir", str(store.root), "--max-minutes", "10"]) == 0
    assert main(["citations", "--data-dir", str(store.root), "-c", "cs.LG", "--all"]) == 0

    assert calls == [("cs.CV", False, "test-key", 600), ("cs.LG", True, "test-key", None)]
    assert capsys.readouterr().out.count("citation counts for 3 of 3 papers") == 2
    assert summary.read_text(encoding="utf-8").count("**Citation counts.** cs.CV: citation counts") == 1


def test_index_is_written_again_from_the_stored_files(
    tmp_path: Path, listing: Listing, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    PaperStore(data_dir).save("cs.CV", listing.papers)
    (data_dir / "index.json").write_text("<<<<<<< a conflict left by a rebase\n", encoding="utf-8")

    assert main(["index", "--data-dir", str(data_dir)]) == 0

    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    assert index["categories"]["cs.CV"] == [
        {"date": "2026-09-25", "count": 5},
        {"date": "2026-09-24", "count": 2},
    ]
    assert capsys.readouterr().out.startswith("Index written to")


def test_reclean_cleans_the_stored_affiliations(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data_dir = tmp_path / "data"
    paper = Paper(
        arxiv_id="2609.00001",
        announced=date(2026, 9, 25),
        title="T",
        authors=("Ada Lovelace", "Bob Smith"),
        affiliations=("MIT", "Code"),
        author_affiliations=((0,), (1,)),
    )
    PaperStore(data_dir).save("cs.CV", [paper])

    assert main(["reclean", "--data-dir", str(data_dir)]) == 0

    (stored,) = PaperStore(data_dir).iter_papers("cs.CV")
    assert stored.affiliations == ("MIT",)
    assert capsys.readouterr().out == "cs.CV: 1 of 1 affiliated papers changed, in 1 day files\n"


def test_validate_fails_on_a_structural_error(
    tmp_path: Path, listing: Listing, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    store = PaperStore(data_dir)
    store.save("cs.CV", listing.papers)
    store.write_index()

    assert main(["validate", "--data-dir", str(data_dir)]) == 0
    assert capsys.readouterr().out == "7 papers in 3 files: 0 errors, 0 warnings\n"

    (data_dir / "index.json").unlink()

    assert main(["validate", "--data-dir", str(data_dir)]) == 1
    assert capsys.readouterr().out == (
        "ERROR data/index.json: missing\n7 papers in 3 files: 1 errors, 0 warnings\n"
    )


@pytest.mark.parametrize(
    ("stopped", "code", "annotation"),
    [
        (Stop.FAILURES, 1, "::error title=Reading HTML pages failed::"),
        (Stop.DEADLINE, 0, "::warning title=Out of time::"),
    ],
)
def test_update_reports_why_reading_html_pages_stopped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    stopped: Stop,
    code: int,
    annotation: str,
) -> None:
    deadlines: list[object] = []

    def update_category(category: str, **options: object) -> UpdateReport:
        html = options["html"]
        assert isinstance(html, HtmlReading)
        deadlines.append(html.deadline)
        return UpdateReport(
            category=category,
            listed=1,
            new=0,
            abstracts_fetched=0,
            affiliations_fetched=0,
            pending=1,
            stopped=stopped,
        )

    monkeypatch.setattr("preprint_radar.cli.update_category", update_category)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    assert main(["update", "--data-dir", str(tmp_path / "data"), "--deadline-minutes", "5"]) == code

    [deadline] = deadlines
    assert isinstance(deadline, float)
    assert deadline > time.monotonic() + 4 * 60
    assert annotation in capsys.readouterr().out
    assert summary.read_text(encoding="utf-8").startswith("**Papers.** cs.CV: 1 listed, 0 new")
    assert ("Reading HTML pages failed for cs.CV" in caplog.text) == bool(code)


def test_backfill_saves_its_progress_when_terminated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def backfill_category(*_: object, **__: object) -> UpdateReport:
        os.kill(os.getpid(), signal.SIGTERM)
        raise AssertionError  # pragma: no cover - the signal interrupts before

    monkeypatch.setattr("preprint_radar.cli.backfill_category", backfill_category)
    data_dir = tmp_path / "data"
    previous = signal.getsignal(signal.SIGTERM)

    with pytest.raises(KeyboardInterrupt):
        main(["backfill", "--data-dir", str(data_dir), "--since", "2026-09-01", "--until", "2026-09-01"])

    assert (data_dir / "index.json").is_file()
    assert signal.getsignal(signal.SIGTERM) is previous


def test_summary_reports_freshness_and_warns_when_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    store = PaperStore(tmp_path / "data")
    old = date(2026, 9, 1)
    store.save("cs.CV", [Paper(arxiv_id="2609.00001", announced=old, title="T", authors=())])
    store.write_archive(
        "cs.CV", [Paper(arxiv_id="1512.03385", announced=date(2015, 12, 10), title="T", authors=())]
    )
    store.write_citations("cs.CV", {"2609.00001": 3}, source="S2")
    path = store.root / "cs.CV" / "citations.json"
    path.write_text(
        path.read_text(encoding="utf-8").replace('"generated_at": "2026', '"generated_at": "2025')
    )
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    assert main(["summary", "--data-dir", str(store.root)]) == 0

    out = capsys.readouterr().out
    assert "cs.CV: newest announcement day 2026-09-01, " in out
    assert "::warning title=Stale data::cs.CV: no new day for " in out
    assert "::warning title=Stale citation counts::cs.CV citation counts: 1 from S2, 2025-" in out
    assert "cs.CV archive: 1 paper over 1 year" in out
    written = summary.read_text(encoding="utf-8")
    assert written.startswith("### Data\n\n- cs.CV: newest announcement day 2026-09-01")
    assert "<details><summary>Coverage by day and by archive year</summary>" in written
    assert "<details><summary>Signs of wrong affiliations (" in written
    assert "cs.CV: signs of wrong affiliations\n0 affiliation strings in 0 papers" in written


def test_summary_of_fresh_data_warns_of_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    store = PaperStore(tmp_path / "data")
    today = datetime.now(tz=UTC).date()
    store.save("cs.CV", [Paper(arxiv_id="2609.00001", announced=today, title="T", authors=())])
    store.write_citations("cs.CV", {"2609.00001": 3}, source="S2")
    (store.root / "cs.LG").mkdir()  # a category without anything yet
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    assert main(["summary", "--data-dir", str(store.root)]) == 0

    out = capsys.readouterr().out
    assert f"cs.CV: newest announcement day {today.isoformat()}, 0 weekdays ago" in out
    assert "::warning" not in out


def test_summary_of_an_archive_alone_has_no_signs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = PaperStore(tmp_path / "data")
    store.write_archive(
        "cs.CV", [Paper(arxiv_id="1512.03385", announced=date(2015, 12, 10), title="T", authors=())]
    )
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    assert main(["summary", "--data-dir", str(store.root)]) == 0

    written = summary.read_text(encoding="utf-8")
    assert "cs.CV archive: 1 paper over 1 year" in written
    assert "Signs of wrong affiliations" not in written


@pytest.mark.parametrize(
    ("options", "picked"),
    [
        pytest.param([], ["2609.00001"], id="older-versions"),
        pytest.param(["--below-version", "3"], ["2609.00001", "2609.00002"], id="below-a-version"),
        pytest.param(["--ids", "2609.00003", "2609.00002"], ["2609.00002", "2609.00003"], id="ids"),
        pytest.param(["--match", "(?i)stanford"], ["2609.00003"], id="match"),
    ],
)
def test_reextract_selects_papers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, options: list[str], picked: list[str]
) -> None:
    papers = [
        Paper(arxiv_id="2609.00001", announced=date(2026, 9, 25), title="T", authors=(), extractor=0),
        Paper(arxiv_id="2609.00002", announced=date(2026, 9, 25), title="T", authors=(), extractor=2),
        Paper(
            arxiv_id="2609.00003",
            announced=date(2026, 9, 25),
            title="T",
            authors=(),
            affiliations=("Stanford University",),
        ),
    ]
    selected: list[list[str]] = []

    def reextract_category(category: str, select: Callable[[Paper], bool], **options: object) -> UpdateReport:
        assert isinstance(options["html"], HtmlReading)
        selected.append(sorted(paper.arxiv_id for paper in papers if select(paper)))
        return UpdateReport(
            category=category, listed=1, new=0, abstracts_fetched=0, affiliations_fetched=1, pending=0
        )

    monkeypatch.setattr("preprint_radar.cli.reextract_category", reextract_category)
    monkeypatch.setattr("preprint_radar.cli.EXTRACTOR_VERSION", 1)
    data_dir = tmp_path / "data"
    args = ["reextract", "--data-dir", str(data_dir), "--page-cache-dir", str(tmp_path / "pages"), *options]

    assert main(args) == 0
    assert selected == [picked]
    assert (data_dir / "index.json").is_file()
