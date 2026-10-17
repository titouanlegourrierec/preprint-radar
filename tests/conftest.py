import os
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from preprint_radar.models import Listing
from preprint_radar.sources.arxiv_listing import parse_listing

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Tests assert on plain lines, and rich styles them whenever FORCE_COLOR is set (some
# terminals export it). It reads the variable once, when `console` creates its consoles at
# import, before any fixture runs: none of the imports above loads that module.
os.environ.pop("FORCE_COLOR", None)


@pytest.fixture(autouse=True)
def _working_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every test in its own directory: default paths are relative (``data/``,
    ``.cache/front-matter/``), and a test must never write into the repository.
    """
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def _environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hide the maintainer's settings, from ``.env`` through the Makefile or the shell, and CI's.

    In GitHub Actions, commands write to the job summary and print annotations: the tests
    that check it set these variables themselves.
    """
    for name in (
        "PREPRINT_RADAR_CONTACT",
        "SEMANTIC_SCHOLAR_API_KEY",
        "GITHUB_TOKEN",
        "GITHUB_ACTIONS",
        "GITHUB_STEP_SUMMARY",
    ):
        monkeypatch.delenv(name, raising=False)


class OfflineError(RuntimeError):
    """A test reached for the network.

    Not an httpx error on purpose: `HttpClient` retries those and turns them into
    `FetchError`, which the pipeline often logs and skips (a page, a ROR lookup, an OpenAlex
    batch), so that a test that forgot its mock would pass, slowly, against the real service.
    """


@pytest.fixture(autouse=True)
def _offline(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests off the network (TEST-6), but those marked ``network``.

    A test injects `httpx.MockTransport` into `HttpClient`, or patches its
    ``get_text``/``post_text``; the real transport refuses every request.
    """
    if request.node.get_closest_marker("network"):
        return

    def refuse(_transport: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        msg = (
            f"tests are offline, but this one asked for {request.url}: inject "
            "httpx.MockTransport, or patch HttpClient.get_text or post_text"
        )
        raise OfflineError(msg)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)


@pytest.fixture(scope="session")
def listing_html() -> str:
    """Trimmed copy of https://arxiv.org/list/cs.CV/recent (7 entries over 2 days)."""
    return (FIXTURES_DIR / "listing_cs_cv.html").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def listing(listing_html: str) -> Listing:
    return parse_listing(listing_html)


@pytest.fixture(scope="session")
def catchup_html() -> str:
    """Trimmed copy of https://arxiv.org/catchup/cs.CV/2026-09-01?abs=True.

    Three new submissions, one cross-list and one replacement, with abstracts.
    """
    return (FIXTURES_DIR / "catchup_cs_cv.html").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def catchup_empty_html() -> str:
    """Copy of the catchup page of a day without announcement (a Saturday)."""
    return (FIXTURES_DIR / "catchup_cs_cv_empty.html").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def api_feed() -> str:
    """arXiv API response with a plain entry, an entry with affiliations and an error entry."""
    return (FIXTURES_DIR / "api_feed.xml").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def paper_html() -> Callable[[str], str]:
    """Front matter of real arXiv HTML renderings (e-mails replaced by placeholders)."""

    def load(arxiv_id: str) -> str:
        return (FIXTURES_DIR / "html" / f"{arxiv_id}.html").read_text(encoding="utf-8")

    return load
