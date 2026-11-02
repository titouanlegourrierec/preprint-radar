"""Everything each HTML fixture gives, pinned in ``tests/fixtures/html/expected.json``.

The named tests of ``test_arxiv_html.py`` say what a heuristic is for; this one shows what
a change does to every page at once. The expectations list who is placed where by name,
so that a failing diff reads like the page. After a deliberate change, write them again
and review the diff of the file::

    UPDATE_GOLDEN=1 uv run pytest tests/unit/test_golden_fixtures.py

A new fixture needs an entry with its authors (the listing's, in order) before that.

``versions.json`` keeps the ``EXTRACTOR_VERSION`` under which each fixture's output last
changed (EXT-8): a change to what a page gives needs a new version, which ``reextract``
reads the stored papers again for, and writing the expectations again refuses an output
that changed under the version it was written with. While a version has not reached
``main``, ``UPDATE_GOLDEN=unreleased`` writes them under it again.
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from preprint_radar.sources.arxiv_html import EXTRACTOR_VERSION, has_contact, parse_front_matter

HTML_DIR = Path(__file__).parents[1] / "fixtures" / "html"
EXPECTED = HTML_DIR / "expected.json"
VERSIONS = HTML_DIR / "versions.json"
FIXTURES = sorted(path.stem for path in HTML_DIR.glob("*.html"))


def _load() -> dict[str, dict[str, Any]]:
    return json.loads(EXPECTED.read_text(encoding="utf-8"))


def extracted(html: str, authors: list[str]) -> dict[str, Any]:
    """What the page gives, authors placed by the names of their affiliations."""
    front = parse_front_matter(html, authors=authors)
    placed = (
        None
        if front.author_affiliations is None
        else [
            [author, None if entry is None else [front.affiliations[index] for index in entry]]
            for author, entry in zip(authors, front.author_affiliations, strict=True)
        ]
    )
    return {
        "authors": authors,
        "affiliations": list(front.affiliations),
        "placed": placed,
        "abstract": front.abstract,
    }


@pytest.mark.parametrize("arxiv_id", FIXTURES)
def test_a_fixture_gives_what_it_gave(arxiv_id: str) -> None:
    golden = _load()
    assert arxiv_id in golden, f"add {arxiv_id} to {EXPECTED.name} with its authors"
    html = (HTML_DIR / f"{arxiv_id}.html").read_text(encoding="utf-8")
    actual = extracted(html, golden[arxiv_id]["authors"])
    if update := os.environ.get("UPDATE_GOLDEN"):
        versions = json.loads(VERSIONS.read_text(encoding="utf-8"))
        written = versions.get(arxiv_id)
        if actual != golden[arxiv_id] and "affiliations" in golden[arxiv_id]:
            # What a page gives changed: under a new version, or one not released yet.
            assert written is None or written < EXTRACTOR_VERSION or update == "unreleased", (
                f"{arxiv_id} gives other affiliations under version {EXTRACTOR_VERSION}: bump "
                "EXTRACTOR_VERSION (docs/extraction.md)"
            )
            versions[arxiv_id] = EXTRACTOR_VERSION
        versions.setdefault(arxiv_id, EXTRACTOR_VERSION)
        VERSIONS.write_text(json.dumps(dict(sorted(versions.items())), indent=2) + "\n", encoding="utf-8")
        golden[arxiv_id] = actual
        EXPECTED.write_text(json.dumps(golden, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    assert actual == golden[arxiv_id]


def test_every_expectation_has_its_fixture() -> None:
    assert sorted(_load()) == FIXTURES


def test_no_output_is_of_a_version_to_come() -> None:
    """Each fixture's output was written under a version up to today's (EXT-8)."""
    versions = json.loads(VERSIONS.read_text(encoding="utf-8"))
    assert sorted(versions) == FIXTURES
    assert max(versions.values()) <= EXTRACTOR_VERSION


def test_no_page_gives_what_validate_refuses() -> None:
    """No fixture gives an affiliation holding a contact detail, which `validate` refuses:
    a data workflow would push nothing (AFF-32, 2610.25235)."""
    expected = _load()
    contacts = [
        (arxiv_id, affiliation)
        for arxiv_id in FIXTURES
        for affiliation in extracted(
            (HTML_DIR / f"{arxiv_id}.html").read_text(encoding="utf-8"), expected[arxiv_id]["authors"]
        )["affiliations"]
        if has_contact(affiliation)
    ]
    assert contacts == []
