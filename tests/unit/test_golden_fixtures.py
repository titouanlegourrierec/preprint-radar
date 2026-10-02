"""Everything each HTML fixture gives, pinned in ``tests/fixtures/html/expected.json``.

The named tests of ``test_arxiv_html.py`` say what a heuristic is for; this one shows what
a change does to every page at once. The expectations list who is placed where by name,
so that a failing diff reads like the page. After a deliberate change, write them again
and review the diff of the file::

    UPDATE_GOLDEN=1 uv run pytest tests/unit/test_golden_fixtures.py

A new fixture needs an entry with its authors (the listing's, in order) before that.
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from preprint_radar.sources.arxiv_html import parse_front_matter

HTML_DIR = Path(__file__).parents[1] / "fixtures" / "html"
EXPECTED = HTML_DIR / "expected.json"
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
    if os.environ.get("UPDATE_GOLDEN"):
        golden[arxiv_id] = actual
        EXPECTED.write_text(json.dumps(golden, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    assert actual == golden[arxiv_id]


def test_every_expectation_has_its_fixture() -> None:
    assert sorted(_load()) == FIXTURES
