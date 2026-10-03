from collections.abc import Callable
from pathlib import Path

import pytest

from preprint_radar.models import Listing
from preprint_radar.sources.arxiv_listing import parse_listing

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _working_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every test in its own directory: default paths are relative (``data/``,
    ``.cache/front-matter/``, ``exports/``), and a test must never write into the repository.
    """
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def _environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hide the maintainer's settings, which the Makefile exports from ``.env``, and CI's.

    In GitHub Actions, commands write to the job summary and print annotations: the tests
    that check it set these variables themselves.
    """
    for name in (
        "PREPRINT_RADAR_CONTACT",
        "SEMANTIC_SCHOLAR_API_KEY",
        "GITHUB_ACTIONS",
        "GITHUB_STEP_SUMMARY",
    ):
        monkeypatch.delenv(name, raising=False)


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
