import gzip
import json
import logging
import os
import runpy
import signal
import time
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from rich.console import Console
from tests.conftest import FIXTURES_DIR

from preprint_radar.archive.catalog import Catalog
from preprint_radar.archive.update import ArchiveClients, ArchiveReport
from preprint_radar.cli import build_parser, log_level, main
from preprint_radar.collect import (
    ArchiveAffiliationsReport,
    CitationsReport,
    CodeReport,
    CountriesReport,
    HtmlReading,
    OpenAlexReport,
    Ror,
    Stop,
    UpdateReport,
)
from preprint_radar.config import DEFAULT_MAX_HTML
from preprint_radar.exceptions import FetchError, NotFoundError
from preprint_radar.http import DEFAULT_USER_AGENT, HttpClient
from preprint_radar.models import Listing, Paper
from preprint_radar.sources.arxiv_html import EXTRACTOR_VERSION, PageCache
from preprint_radar.sources.arxiv_oai import OAI_URL, CatalogEntry
from preprint_radar.sources.openalex import OPENALEX_WORKS_URL
from preprint_radar.sources.semantic_scholar import S2_BATCH_URL
from preprint_radar.steps import StepCount
from preprint_radar.store.paper_store import PaperStore


@pytest.fixture(autouse=True)
def _run_day(monkeypatch: pytest.MonkeyPatch) -> None:
    """The day of the fixtures' newest announcement: `update` sees the store as up to date (CI-7)."""
    monkeypatch.setattr("preprint_radar.collect.today", lambda: date(2026, 9, 25))


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
def test_update_populates_store(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    data_dir = tmp_path / "data"

    assert main(["update", "--data-dir", str(data_dir), "--crawl-delay", "0"]) == 0

    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    assert [day["count"] for day in index["categories"]["cs.CV"]] == [5, 2]
    assert "cs.CV: 7 listed, 7 new" in capsys.readouterr().out
    assert "No contact given" in caplog.text


def test_update_warns_of_a_listing_out_of_date(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    listing_html: str,
    catchup_html: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def get_text(_: HttpClient, url: str, *, params: Mapping[str, str | int] | None = None) -> str:
        del params
        if "/list/" in url:
            return listing_html
        if url.endswith("/catchup/cs.CV/2026-09-28"):
            return catchup_html.replace("Tue, 01 Sep 2026", "Mon, 28 Sep 2026")
        raise NotFoundError(url)

    monkeypatch.setattr(HttpClient, "get_text", get_text)
    monkeypatch.setattr("preprint_radar.collect.today", lambda: date(2026, 9, 28))
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    data_dir = tmp_path / "data"

    assert main(["update", "--data-dir", str(data_dir), "--crawl-delay", "0", "--max-html", "0"]) == 0

    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    assert index["categories"]["cs.CV"][0] == {"date": "2026-09-28", "count": 4}
    out = capsys.readouterr().out
    assert "::warning title=Listing out of date::cs.CV: 11 listed, 11 new" in out
    assert "the listing lacked 2026-09-28: 4 papers from its catchup page" in out


@pytest.mark.usefixtures("offline")
def test_update_catches_up_on_days_after_an_outage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    assert main(["update", "--data-dir", str(data_dir), "--crawl-delay", "0", "--max-html", "0"]) == 0
    # Six weekdays later: the listing no longer holds the days in between, nor those of the
    # papers whose pages were not read (CI-7).
    monkeypatch.setattr("preprint_radar.collect.today", lambda: date(2026, 10, 5))
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    capsys.readouterr()

    assert main(["update", "--data-dir", str(data_dir), "--crawl-delay", "0", "--max-html", "0"]) == 0

    out = capsys.readouterr().out
    assert "::warning title=Catching up::cs.CV: reading every day since 2026-09-24 from catchup pages" in out
    assert "cs.CV: 0 listed, 0 new" in out


@pytest.mark.usefixtures("offline")
def test_update_whose_listing_fails_keeps_the_store_and_exits_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    data_dir = tmp_path / "data"
    assert main(["update", "--data-dir", str(data_dir), "--crawl-delay", "0"]) == 0
    stored = {path.name: path.read_bytes() for path in (data_dir / "cs.CV").glob("2026-*.json")}

    def get_text(_: HttpClient, url: str, *, params: Mapping[str, str | int] | None = None) -> str:
        del params
        raise FetchError(f"arxiv.org is down: {url}")

    monkeypatch.setattr(HttpClient, "get_text", get_text)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    capsys.readouterr()

    assert main(["update", "--data-dir", str(data_dir), "--crawl-delay", "0"]) == 1

    # The days stored before are untouched, and the index still lists them (TEST-2).
    assert {path.name: path.read_bytes() for path in (data_dir / "cs.CV").glob("2026-*.json")} == stored
    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    assert [day["count"] for day in index["categories"]["cs.CV"]] == [5, 2]
    assert "arxiv.org is down: https://arxiv.org/list/cs.CV/recent" in caplog.text
    out = capsys.readouterr().out
    assert "Index written to" in out
    assert "::error title=preprint-radar update failed::arxiv.org is down" in out


@pytest.mark.usefixtures("offline")
def test_update_keeps_a_category_read_before_another_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, listing_html: str, caplog: pytest.LogCaptureFixture
) -> None:
    def get_text(_: HttpClient, url: str, *, params: Mapping[str, str | int] | None = None) -> str:
        del params
        if url.endswith("/list/cs.CV/recent"):
            return listing_html
        if "/list/" in url:
            raise FetchError(f"arxiv.org is down: {url}")
        raise NotFoundError(url)

    monkeypatch.setattr(HttpClient, "get_text", get_text)
    data_dir = tmp_path / "data"

    args = ["--data-dir", str(data_dir), "--crawl-delay", "0", "--category", "cs.CV", "--category", "cs.RO"]
    assert main(["update", *args]) == 1

    # cs.CV's days are saved and indexed; cs.RO has none (TEST-2).
    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    assert list(index["categories"]) == ["cs.CV"]
    assert [day["count"] for day in index["categories"]["cs.CV"]] == [5, 2]
    assert "arxiv.org is down: https://arxiv.org/list/cs.RO/recent" in caplog.text


@pytest.mark.usefixtures("offline")
def test_a_failing_category_leaves_the_next_to_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, listing_html: str, capsys: pytest.CaptureFixture[str]
) -> None:
    def get_text(_: HttpClient, url: str, *, params: Mapping[str, str | int] | None = None) -> str:
        del params
        if url.endswith("/list/cs.CV/recent"):
            return listing_html
        if "/list/" in url:
            raise FetchError(f"arxiv.org is down: {url}")
        raise NotFoundError(url)

    monkeypatch.setattr(HttpClient, "get_text", get_text)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    data_dir = tmp_path / "data"

    args = ["--data-dir", str(data_dir), "--crawl-delay", "0", "--category", "cs.RO", "--category", "cs.CV"]
    assert main(["update", *args]) == 1

    # cs.RO failed first; cs.CV ran all the same (REL-5).
    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    assert [day["count"] for day in index["categories"]["cs.CV"]] == [5, 2]
    out = capsys.readouterr().out
    assert (
        "::error title=preprint-radar update failed::arxiv.org is down: https://arxiv.org/list/cs.RO/recent"
        in out
    )
    assert "cs.CV: 7 listed, 7 new" in out


def test_backfill_goes_on_past_a_failing_day_and_exits_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    catchup_html: str,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    def get_text(_: HttpClient, url: str, *, params: Mapping[str, str | int] | None = None) -> str:
        del params
        # Days are fetched from the latest: arXiv fails on 2026-09-02, then 2026-09-01 is saved.
        if url.endswith("/catchup/cs.CV/2026-09-01"):
            return catchup_html
        raise FetchError("arxiv.org is down")

    monkeypatch.setattr(HttpClient, "get_text", get_text)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    data_dir = tmp_path / "data"

    args = ["--since", "2026-09-01", "--until", "2026-09-02", "--max-html", "0", "--crawl-delay", "0"]
    assert main(["backfill", "--data-dir", str(data_dir), *args]) == 1

    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    assert index["categories"]["cs.CV"] == [{"date": "2026-09-01", "count": 4}]
    out = capsys.readouterr().out
    assert "::error title=Catchup pages failed::cs.CV: 4 listed, 4 new" in out
    assert "; days not read: 2026-09-02" in out
    assert "Reading HTML pages failed" not in out
    assert "Catchup pages failed for cs.CV: see above" in caplog.text
    assert "Reading HTML pages failed for" not in caplog.text


def test_backfill_writes_the_index_even_when_it_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def backfill_category(category: str, *_: object, store: PaperStore, **__: object) -> UpdateReport:
        store.save(
            category, [Paper(arxiv_id="2609.00001", announced=date(2026, 9, 1), title="T", authors=())]
        )
        raise FetchError("arxiv.org is down")

    monkeypatch.setattr("preprint_radar.cli.backfill_category", backfill_category)
    data_dir = tmp_path / "data"

    assert (
        main(["backfill", "--data-dir", str(data_dir), "--since", "2026-09-01", "--until", "2026-09-01"]) == 1
    )

    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    assert index["categories"]["cs.CV"] == [{"date": "2026-09-01", "count": 1}]


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


def test_backfill_rejects_reversed_dates(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["backfill", "--since", "2026-09-02", "--until", "2026-09-01"])

    assert exc_info.value.code == 2
    assert "--since must not be after --until" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["update", "--max-html", "-1"], "must be 0 or more, got -1"),
        (["update", "--max-ror", "many"], "not a whole number: 'many'"),
        (["citations", "--max-minutes", "-5"], "must be a number, 0 or more, got -5"),
        (["update", "--deadline-minutes", "nan"], "must be a number, 0 or more, got nan"),
        (["update", "--crawl-delay", "soon"], "not a number: 'soon'"),
        (["update", "--crawl-delay", "inf"], "must be a number, 0 or more, got inf"),
        (["update", "--crawl-delay", "1e10"], "must be 3600 seconds at most, got 1e10"),
        (["reextract", "--match", "("], "not a valid regular expression: missing )"),
        (["stats", "--affiliations", "--changes"], "--changes needs --page-cache-dir"),
        (["stats", "--page-cache-dir", "cache"], "--page-cache-dir goes with --affiliations"),
    ],
    ids=["html", "ror", "minutes", "nan", "delay", "inf", "long", "regex", "changes", "cache"],
)
def test_arguments_out_of_range_are_refused_with_a_usage_line(
    argv: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(argv)

    assert exc_info.value.code == 2
    assert message in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "level"),
    [
        (["stats"], logging.WARNING),
        (["-v", "stats"], logging.INFO),
        (["stats", "-vv"], logging.DEBUG),
        (["-v", "stats", "-v"], logging.DEBUG),
        # The long commands log their progress without -v, but for -q (DOC-5).
        (["update"], logging.INFO),
        (["-v", "archive"], logging.INFO),
        (["-vv", "citations"], logging.DEBUG),
        (["-q", "update"], logging.WARNING),
        (["backfill", "--since", "2026-09-01", "-q", "-v"], logging.WARNING),
    ],
)
def test_verbosity_goes_before_or_after_the_command(argv: list[str], level: int) -> None:
    assert log_level(build_parser().parse_args(argv)) == level


def test_numbers_in_range_are_taken() -> None:
    parser = build_parser()

    assert parser.parse_args(["update", "--max-html", "0", "--crawl-delay", "0"]).max_html == 0


@pytest.mark.parametrize(
    ("argv", "max_html"),
    [
        # What the daily workflow reads within its deadline, unless told otherwise (DEBT-7).
        (["update"], DEFAULT_MAX_HTML),
        (["backfill", "--since", "2026-09-01"], DEFAULT_MAX_HTML),
        # The workflow gives reextract its own budget; locally, the cache makes most pages free.
        (["reextract"], None),
    ],
    ids=["update", "backfill", "reextract"],
)
def test_html_pages_are_limited_by_default_but_for_reextract(argv: list[str], max_html: int | None) -> None:
    assert build_parser().parse_args(argv).max_html == max_html


@pytest.mark.parametrize(
    ("command", "default"),
    [("update", f"default: {DEFAULT_MAX_HTML};"), ("reextract", "default: no limit;")],
)
def test_help_gives_each_command_its_html_limit(
    command: str, default: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        main([command, "--help"])

    assert default in " ".join(capsys.readouterr().out.split())


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
    assert lines[2].split() == ["2026-09-25", "5", "0", "0", "0", "5", "0", "0", "0", "2", "0"]
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


def test_errors_are_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fail(*_: object, **__: object) -> str:
        raise FetchError("arxiv.org is down")

    monkeypatch.setattr(HttpClient, "get_text", fail)

    assert main(["update", "--data-dir", str(tmp_path / "data"), "--crawl-delay", "0"]) == 1
    assert "arxiv.org is down" in caplog.text


def test_rejects_invalid_category(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["update", "--category", "not a category"])

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
        "cs.CV: 10 archived papers (2 in, 1 out), threshold 19.5 citations a year, 0 most cited of "
        "the last 12 months, citation counts for 99.0% of 100 papers, 0 papers' comments refreshed, "
        "0 day files pruned "
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


def test_archive_sends_the_contact_to_arxiv_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agents: dict[str, str] = {}

    def handle_request(_: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        agents[request.url.host] = request.headers["User-Agent"]
        return httpx.Response(200, text="")

    def update_archive(category: str, *, clients: ArchiveClients, **_: object) -> ArchiveReport:
        clients.oai.get_text(OAI_URL)
        clients.citations.get_text(S2_BATCH_URL)
        clients.openalex.get_text(OPENALEX_WORKS_URL)
        return ArchiveReport(
            category=category,
            candidates=100,
            coverage=0.99,
            threshold=19.5,
            archived=10,
            entered=0,
            left=0,
            pruned_days=0,
            written=False,
        )

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle_request)
    monkeypatch.setattr("preprint_radar.cli.update_archive", update_archive)
    args = ["archive", "--data-dir", str(tmp_path / "data"), "--catalog-dir", str(tmp_path / "catalog")]

    assert main(["--contact", "author@example.org", *args]) == 0

    assert agents == {
        "oaipmh.arxiv.org": f"{DEFAULT_USER_AGENT} (author@example.org)",
        "api.semanticscholar.org": DEFAULT_USER_AGENT,
        "api.openalex.org": DEFAULT_USER_AGENT,
    }


# OAI-PMH with nothing new since the last harvest, Semantic Scholar with these counts, and
# OpenAlex with the works of its fixture: the archive's services, for real runs (TEST-11).
NOTHING_NEW = '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><error code="noRecordsMatch"/></OAI-PMH>'
WORKS = (FIXTURES_DIR / "openalex" / "works.json").read_text(encoding="utf-8")


def _serve_archive(monkeypatch: pytest.MonkeyPatch, counts: Mapping[str, int]) -> list[str]:
    """Answer the archive's services offline, without their delays; the hosts asked, in order."""
    hosts: list[str] = []

    def handle_request(_: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        if request.url.host == "oaipmh.arxiv.org":
            return httpx.Response(200, text=NOTHING_NEW)
        if request.url.host == "api.semanticscholar.org":
            ids = [paper_id.removeprefix("ARXIV:") for paper_id in json.loads(request.content)["ids"]]
            return httpx.Response(200, json=[{"citationCount": counts.get(arxiv_id)} for arxiv_id in ids])
        return httpx.Response(200, text=WORKS)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle_request)
    for delay in (
        "OAI_DELAY_SECONDS",
        "OPENALEX_DELAY_SECONDS",
        "S2_DELAY_SECONDS",
        "S2_ANONYMOUS_DELAY_SECONDS",
    ):
        monkeypatch.setattr(f"preprint_radar.cli.{delay}", 0)
    return hosts


def test_archive_runs_over_a_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The papers of a catalog harvested a week ago: two older than 12 months, one recent.
    today = datetime.now(tz=UTC).date()
    recent = today - timedelta(days=20)
    recent_id = f"{recent:%y%m}.00001"
    entries = [
        ("1512.03385", date(2015, 12, 10), ("cs.CV",)),
        ("2010.11929", date(2020, 10, 22), ("cs.LG", "cs.CV")),
        ("2209.00001", date(2022, 9, 1), ("cs.CV",)),
        (recent_id, recent, ("cs.CV",)),
    ]
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    with gzip.open(catalog / "cs.CV.jsonl.gz", "wt", encoding="utf-8") as out:
        for arxiv_id, created, categories in entries:
            entry = CatalogEntry(
                arxiv_id=arxiv_id,
                created=created,
                categories=categories,
                title=f"Paper {arxiv_id}",
                authors=("A One", "B Two"),
                abstract="An abstract.",
                comments="Accepted to CVPR 2016",
            )
            out.write(json.dumps(entry.to_record()) + "\n")
    harvested = {"harvested": (today - timedelta(days=7)).isoformat(), "token": None}
    (catalog / "cs.CV.state.json").write_text(json.dumps(harvested), encoding="utf-8")
    counts = {"1512.03385": 240_000, "2010.11929": 70_000, "2209.00001": 1, recent_id: 3}
    hosts = _serve_archive(monkeypatch, counts)
    data_dir = tmp_path / "data"

    assert main(["archive", "--data-dir", str(data_dir), "--catalog-dir", str(catalog), "--budget", "2"]) == 0

    # The catalog refreshed, every candidate counted, the entering papers asked of OpenAlex.
    assert hosts[:2] == ["oaipmh.arxiv.org", "api.semanticscholar.org"]
    assert "api.openalex.org" in hosts
    store = PaperStore(data_dir)
    archived = {paper.arxiv_id: paper for paper in store.iter_archive("cs.CV")}
    assert set(archived) == {"1512.03385", "2010.11929"}
    assert archived["1512.03385"].affiliations == ("Microsoft",)
    assert archived["1512.03385"].venue == "CVPR 2016"
    top_recent = store.load_top_recent("cs.CV")
    assert top_recent is not None
    assert [paper.arxiv_id for paper in top_recent.papers] == [recent_id]
    stored = json.loads((data_dir / "cs.CV" / "citations.json").read_text(encoding="utf-8"))
    # The counts of the stored papers: 2209.00001 is not one, below the budget.
    assert stored["counts"] == {
        arxiv_id: counts[arxiv_id] for arxiv_id in ("1512.03385", "2010.11929", recent_id)
    }
    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    assert [entry["year"] for entry in index["archives"]["cs.CV"]] == [2020, 2015]
    assert capsys.readouterr().out.startswith("cs.CV: 2 archived papers (2 in, 0 out), threshold ")


def test_trends_counts_the_titles_of_the_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    with gzip.open(catalog / "cs.CV.jsonl.gz", "wt", encoding="utf-8") as out:
        for index in range(10):
            entry = CatalogEntry(
                arxiv_id=f"2609.{index:05d}",
                created=date(2026, 9, 10 + index),
                categories=("cs.CV",),
                title="World Models for Robots",
                authors=("A One",),
            )
            out.write(json.dumps(entry.to_record()) + "\n")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    store = PaperStore(tmp_path / "data")
    args = ["trends", "--data-dir", str(store.root), "--catalog-dir", str(catalog)]

    # Without the week's citation counts: titles only.
    assert main(args) == 0

    assert "No citation counts of the week in" in caplog.text
    trends = store.load_trends("cs.CV")
    assert trends is not None
    assert trends.source == "arXiv"
    assert trends.windows["quarter"].rising == ("world models for robot",)
    assert trends.topics["world models for robot"].papers == ()
    topics = store.load_topics("cs.CV")
    assert topics is not None
    assert set(topics.topics) == {
        "world",
        "robot",
        "world model",
        "world models for robot",
        "models for robot",
    }
    line = "cs.CV: 5 topics of 10 papers to 2026-09-19; last 90 days: 1 rising (world models for robot…)"
    assert line in capsys.readouterr().out
    assert f"**Trends.** {line}" in summary.read_text(encoding="utf-8")

    # With the counts the archive cached this week.
    today = datetime.now(tz=UTC).date()
    counts = {"2609.00003": 7, "2609.00001": 2}
    (catalog / "cs.CV.citations.jsonl").write_text(
        f"{json.dumps({'date': today.isoformat()})}\n{json.dumps(counts)}\n", encoding="utf-8"
    )
    assert main(args) == 0

    trends = store.load_trends("cs.CV")
    assert trends is not None
    assert trends.source == "arXiv, Semantic Scholar"
    assert [paper.arxiv_id for paper in trends.topics["world models for robot"].papers] == [
        "2609.00003",
        "2609.00001",
    ]


def test_trends_needs_the_catalog(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    args = ["trends", "-c", "cs.RO", "--data-dir", str(tmp_path / "data"), "--catalog-dir", str(tmp_path)]

    assert main(args) == 1

    assert f"The catalog of cs.RO in {tmp_path} holds no paper since 2010: archive harvests it" in caplog.text
    assert not (tmp_path / "data").exists()


def test_citations_runs_over_a_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    store = PaperStore(tmp_path / "data")
    store.save(
        "cs.CV",
        [
            Paper(arxiv_id="2609.00001", announced=date(2026, 9, 25), title="T", authors=()),
            Paper(arxiv_id="2609.00002", announced=date(2026, 9, 25), title="U", authors=()),
        ],
    )
    hosts = _serve_archive(monkeypatch, {"2609.00001": 12})

    assert main(["citations", "--data-dir", str(store.root)]) == 0

    assert hosts == ["api.semanticscholar.org"]
    stored = json.loads((store.root / "cs.CV" / "citations.json").read_text(encoding="utf-8"))
    # Semantic Scholar does not know the other one yet: asked for again next time.
    assert stored["counts"] == {"2609.00001": 12}
    assert "cs.CV: citation counts for 1 of 2 papers" in capsys.readouterr().out


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


def test_affiliations_asks_openalex_for_each_category(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, str]] = []

    def handle_request(_: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        calls.append((request.url.host, request.headers["User-Agent"]))
        return httpx.Response(200, text="")

    def update_openalex_affiliations(
        _: PaperStore, category: str, client: HttpClient, *, today: date
    ) -> OpenAlexReport:
        client.get_text(OPENALEX_WORKS_URL)
        assert today == datetime.now(tz=UTC).date()
        return OpenAlexReport(category=category, asked=4, found=1)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle_request)
    monkeypatch.setattr("preprint_radar.cli.update_openalex_affiliations", update_openalex_affiliations)
    monkeypatch.setenv("PREPRINT_RADAR_CONTACT", "author@example.org")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    store = PaperStore(tmp_path / "data")
    store.save("cs.CV", [Paper(arxiv_id="2609.00001", announced=date(2026, 9, 25), title="T", authors=())])

    assert main(["affiliations", "--data-dir", str(store.root)]) == 0

    # Only arXiv gets the contact.
    assert calls == [("api.openalex.org", DEFAULT_USER_AGENT)]
    assert (
        "cs.CV: OpenAlex gave affiliations for 1 of 4 papers without any from a page"
        in capsys.readouterr().out
    )
    assert "**Affiliations from OpenAlex.** cs.CV:" in summary.read_text(encoding="utf-8")


def _user_agents(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """The host and User-Agent of each request, which gets an empty answer."""
    calls: list[tuple[str, str]] = []

    def handle_request(_: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        calls.append((request.url.host, request.headers["User-Agent"]))
        return httpx.Response(200, text="")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle_request)
    return calls


def test_archive_affiliations_asks_openalex_only_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[bool, int | None, bool, int | None]] = []

    def update_archive_affiliations(
        _: PaperStore,
        category: str,
        *,
        openalex_client: HttpClient,
        today: date,
        site_client: HttpClient | None,
        html: HtmlReading,
        ror: Ror,
    ) -> ArchiveAffiliationsReport:
        openalex_client.get_text(OPENALEX_WORKS_URL)
        assert today == datetime.now(tz=UTC).date()
        calls.append((site_client is None, html.limit, ror.client is None, ror.max_lookups))
        return ArchiveAffiliationsReport(category=category, without=10, from_published=7)

    requests = _user_agents(monkeypatch)
    monkeypatch.setattr("preprint_radar.cli.update_archive_affiliations", update_archive_affiliations)
    monkeypatch.setenv("PREPRINT_RADAR_CONTACT", "author@example.org")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    assert main(["archive-affiliations", "--data-dir", str(tmp_path / "data")]) == 0

    # No page, and every unnamed institution looked up in ROR.
    assert calls == [(True, 0, False, None)]
    # Only arXiv gets the contact.
    assert requests == [("api.openalex.org", DEFAULT_USER_AGENT)]
    line = (
        "cs.CV: 7 of 10 highly cited papers without affiliations got some, "
        "7 from OpenAlex's published versions"
    )
    assert line in capsys.readouterr().out
    assert f"**Affiliations of the highly cited papers.** {line}" in summary.read_text(encoding="utf-8")


def test_archive_affiliations_reads_pages_with_the_contact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def update_archive_affiliations(
        _: PaperStore,
        category: str,
        *,
        site_client: HttpClient | None,
        html: HtmlReading,
        ror: Ror,
        **_others: object,
    ) -> ArchiveAffiliationsReport:
        assert site_client is not None
        site_client.get_text("https://arxiv.org/html/2501.00001v1")
        assert (html.limit, html.cache is not None, ror.client) == (5, True, None)
        return ArchiveAffiliationsReport(
            category=category, without=10, from_published=0, stopped=Stop.FAILURES
        )

    requests = _user_agents(monkeypatch)
    monkeypatch.setattr("preprint_radar.cli.update_archive_affiliations", update_archive_affiliations)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    arguments = [
        "archive-affiliations",
        "--data-dir",
        str(tmp_path / "data"),
        "--max-html",
        "5",
        "--max-ror",
        "0",
    ]

    # The reading of pages failed: the command fails.
    assert main(["--contact", "author@example.org", *arguments]) == 1
    assert "No contact given" not in caplog.text
    assert requests[0][0] == "arxiv.org"
    assert "author@example.org" in requests[0][1]
    assert main(arguments) == 1
    assert "No contact given" in caplog.text
    assert "::error title=Reading HTML pages failed::cs.CV: 0 of 10" in capsys.readouterr().out


def test_code_needs_a_github_token(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    assert main(["code", "--data-dir", str(tmp_path / "data")]) == 1
    assert "No GitHub token: set GITHUB_TOKEN" in caplog.text


def test_code_asks_github_and_the_hub_without_the_contact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def update_code_records(
        _: PaperStore, category: str, *, github: HttpClient, token: str, hub: HttpClient, new_only: bool
    ) -> CodeReport:
        assert token == "test-token"
        assert new_only  # --new: the daily run
        github.get_text("https://api.github.com/graphql")
        hub.get_text("https://huggingface.co/api/models/lab/fast-net")
        return CodeReport(category=category, linked=5, asked=1, stars=3, shared=1, likes=1, gone=1, kept=0)

    requests = _user_agents(monkeypatch)
    monkeypatch.setattr("preprint_radar.cli.update_code_records", update_code_records)
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("PREPRINT_RADAR_CONTACT", "author@example.org")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    store = PaperStore(tmp_path / "data")
    store.save("cs.CV", [Paper(arxiv_id="2609.00001", announced=date(2026, 9, 25), title="T", authors=())])

    assert main(["code", "--data-dir", str(store.root), "--new"]) == 0

    assert requests == [("api.github.com", DEFAULT_USER_AGENT), ("huggingface.co", DEFAULT_USER_AGENT)]
    assert "cs.CV: 5 papers link their code, 1 asked: 3 with GitHub stars" in capsys.readouterr().out
    assert "**Stars of the code.** cs.CV:" in summary.read_text(encoding="utf-8")


def test_countries_ask_openalex_without_the_contact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def update_countries(
        _: PaperStore, category: str, client: HttpClient, *, refresh: bool
    ) -> CountriesReport:
        assert refresh  # --all
        client.get_text("https://api.openalex.org/institutions")
        return CountriesReport(
            category=category,
            institutions=3,
            asked=3,
            placed=2,
            nowhere=1,
            failed=0,
            papers=4,
            papers_placed=2,
        )

    requests = _user_agents(monkeypatch)
    monkeypatch.setattr("preprint_radar.cli.update_countries", update_countries)
    monkeypatch.setenv("PREPRINT_RADAR_CONTACT", "author@example.org")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    store = PaperStore(tmp_path / "data")
    store.save("cs.CV", [Paper(arxiv_id="2609.00001", announced=date(2026, 9, 25), title="T", authors=())])

    assert main(["countries", "--data-dir", str(store.root), "--all"]) == 0

    assert requests == [("api.openalex.org", DEFAULT_USER_AGENT)]
    assert "cs.CV: 3 institutions, 3 asked: 2 placed in a country" in capsys.readouterr().out
    assert "**Countries of institutions.** cs.CV:" in summary.read_text(encoding="utf-8")


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
            steps=(StepCount("Abstracts", 0, 0, 0), StepCount("HTML pages", 3, 2, 1)),
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
    # What each step did, those nothing needed left out (ARCH-2).
    assert "**Steps.** HTML pages: 2 of 3, 1 left\n" in summary.read_text(encoding="utf-8")
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
