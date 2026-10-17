"""The failures of Phase 1's exit criteria, run end to end as the data workflows meet them.

Each one must end in a clear red run (an exit code of 1 and an error annotation on the
run's page) or a warning, and lose nothing: what was fetched is saved and passes
``validate`` (so that *Commit data* pushes it), and what was not stays pending for the next
run. The fourth failure, a rebase conflict on the data commit, is run against git
repositories in ``test_commit_data.py``.
"""

from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path

import pytest

from preprint_radar.cli import main
from preprint_radar.exceptions import FetchError, NotFoundError
from preprint_radar.http import HttpClient
from preprint_radar.models import Paper
from preprint_radar.store.paper_store import PaperStore
from preprint_radar.store.validate import validate_store

type Page = Callable[[str], str]
"""What arxiv.org answers for an HTML rendering's URL."""

DAY = date(2026, 9, 25)
UPDATE = ["update", "--crawl-delay", "0", "--max-ror", "0"]


@pytest.fixture(autouse=True)
def _run_day(monkeypatch: pytest.MonkeyPatch) -> None:
    """The day of the fixtures' newest announcement: `update` sees the store as up to date (CI-7)."""
    monkeypatch.setattr("preprint_radar.collect.today", lambda: date(2026, 9, 25))


@pytest.fixture
def arxiv(
    monkeypatch: pytest.MonkeyPatch,
    listing_html: str,
    catchup_html: str,
    catchup_empty_html: str,
    api_feed: str,
) -> Callable[[Page], None]:
    """Serve the listing fixtures, and HTML renderings as the test says."""

    def serve(page: Page) -> None:
        def get_text(_: HttpClient, url: str, *, params: Mapping[str, str | int] | None = None) -> str:
            del params
            if "/list/" in url:
                return listing_html
            if "/catchup/" in url:
                return catchup_html if url.endswith("/2026-09-01") else catchup_empty_html
            if "export.arxiv.org" in url:
                return api_feed
            if "/html/" in url:
                return page(url)
            raise NotFoundError(url)

        monkeypatch.setattr(HttpClient, "get_text", get_text)

    return serve


@pytest.fixture
def actions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run as in GitHub Actions; the job summary's path."""
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    return summary


def _down(url: str) -> str:
    msg = f"Server error 503 for {url}"
    raise FetchError(msg, status=503)


def _new_layout(_: str) -> str:
    return '<html><body><main class="new-layout"><h1>A paper</h1></main></body></html>'


def _pending(store: PaperStore) -> list[Paper]:
    return [paper for paper in store.iter_papers("cs.CV") if paper.html_url and paper.affiliations is None]


@pytest.mark.usefixtures("actions")
def test_an_arxiv_outage_is_a_red_run_that_loses_nothing(
    tmp_path: Path,
    arxiv: Callable[[Page], None],
    paper_html: Callable[[str], str],
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = PaperStore(tmp_path / "data")
    arxiv(_down)

    assert main([*UPDATE, "--data-dir", str(store.root)]) == 1

    out = capsys.readouterr().out
    assert "::error title=Reading HTML pages failed::cs.CV: 7 listed, 7 new" in out
    assert "arxiv.org failed 5 HTML renderings in a row: stopping" in caplog.text
    # The listing and its abstracts are saved, the affiliations left for the next run.
    assert len(list(store.iter_papers("cs.CV"))) == 7
    assert len(_pending(store)) == 7
    assert validate_store(store).errors == []

    # arxiv.org is back: the next run reads them.
    arxiv(lambda _: paper_html("2609.30249"))
    assert main([*UPDATE, "--data-dir", str(store.root)]) == 0
    assert _pending(store) == []


@pytest.mark.usefixtures("actions")
def test_a_layout_change_is_a_red_run_that_keeps_the_papers_pending(
    tmp_path: Path,
    arxiv: Callable[[Page], None],
    paper_html: Callable[[str], str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The breaker needs 40 pages; the listing fixture has 7.
    monkeypatch.setattr("preprint_radar.collect.DRIFT_MIN_PAGES", 5)
    store = PaperStore(tmp_path / "data")
    arxiv(_new_layout)

    assert main([*UPDATE, "--data-dir", str(store.root)]) == 1

    assert "::error title=Reading HTML pages failed::" in capsys.readouterr().out
    assert "5 of 5 HTML renderings gave no affiliation: has arXiv's layout changed?" in caplog.text
    # Not "nothing found" ([]), which would be final: pending, and read again once fixed.
    assert len(_pending(store)) == 7
    assert validate_store(store).errors == []
    # Nor kept in the page cache: an error page served with a 200 would stop every next run.
    assert list(Path(".cache/front-matter").rglob("*.gz")) == []

    capsys.readouterr()
    caplog.clear()
    arxiv(lambda _: paper_html("2609.30249"))
    assert main([*UPDATE, "--data-dir", str(store.root)]) == 0, caplog.text + capsys.readouterr().out
    assert _pending(store) == []


@pytest.mark.parametrize("status", [401, 403])
def test_a_rejected_semantic_scholar_key_is_a_red_run_that_keeps_the_counts(
    tmp_path: Path,
    actions: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    status: int,
) -> None:
    store = PaperStore(tmp_path / "data")
    store.save(
        "cs.CV", [Paper(arxiv_id=f"2609.0000{n}", announced=DAY, title="T", authors=()) for n in (1, 2)]
    )
    store.write_citations("cs.CV", {"2609.00001": 3}, source="Semantic Scholar")
    store.write_index()
    citations = (store.root / "cs.CV" / "citations.json").read_text(encoding="utf-8")
    posted: list[str] = []

    def post_text(_: HttpClient, url: str, **__: object) -> str:
        posted.append(url)
        msg = f"Client error {status} for {url}"
        raise FetchError(msg, status=status)

    monkeypatch.setattr(HttpClient, "post_text", post_text)
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "revoked")

    assert main(["citations", "--data-dir", str(store.root), "--max-minutes", "10"]) == 1

    message = f"Semantic Scholar rejected the API key (HTTP {status})"
    assert message in caplog.text
    assert f"::error title=preprint-radar citations failed::{message}" in capsys.readouterr().out
    assert len(posted) == 1  # no retries: a rejected key is not a busy server
    assert (store.root / "cs.CV" / "citations.json").read_text(encoding="utf-8") == citations
    assert validate_store(store).errors == []
    assert not actions.exists() or "Citation counts" not in actions.read_text(encoding="utf-8")


def test_errors_are_annotated_only_in_github_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*_: object, **__: object) -> str:
        msg = "arxiv.org is down"
        raise FetchError(msg)

    monkeypatch.setattr(HttpClient, "get_text", fail)
    update = ["update", "--data-dir", str(tmp_path / "data"), "--crawl-delay", "0"]

    assert main(update) == 1
    assert "::error" not in capsys.readouterr().out
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert main(update) == 1
    assert "::error title=preprint-radar update failed::arxiv.org is down" in capsys.readouterr().out
