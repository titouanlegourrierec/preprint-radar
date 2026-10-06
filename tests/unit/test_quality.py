from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from rich.console import Console

from preprint_radar.models import Paper
from preprint_radar.sources.arxiv_html import EXTRACTOR_VERSION, PageCache
from preprint_radar.store.quality import (
    EXAMPLES,
    Sign,
    affiliation_quality,
    extracted_again,
    format_quality,
    last_holds_all,
    names_only,
    quality_table,
    string_signs,
)

PAPER = Paper(
    arxiv_id="2609.00001",
    announced=date(2026, 9, 25),
    title="T",
    authors=("Ada Lovelace", "Bob Smith"),
    affiliations=("MIT",),
)


@pytest.mark.parametrize(
    ("affiliation", "signs"),
    [
        pytest.param("Massachusetts Institute of Technology, Cambridge, MA, USA", set(), id="whole"),
        pytest.param("Bob Smith", {Sign.NAMES}, id="names-authors"),
        pytest.param("MIT, jane (at) mit.edu", {Sign.CLEANING}, id="cleaned-again"),
        pytest.param("Code", {Sign.CLEANING}, id="rejected"),
        pytest.param("A. Lovelace is with MIT", {Sign.CLEANING, Sign.STATEMENT}, id="statement"),
        pytest.param(
            "Dept. of Computer ScienceUniversity of Alabama",
            {Sign.GLUED, Sign.CLEANING},
            id="glued-line-break",
        ),
        pytest.param(
            "Monash University; 2Southeast University", {Sign.GLUED, Sign.CLEANING}, id="glued-marker"
        ),
        # A name, and a postcode before a marker-like number.
        pytest.param("VinUniversity, Hanoi, Vietnam", set(), id="name-with-university"),
        pytest.param("Cardiff University, CF24 4AG Cardiff, United Kingdom", set(), id="postcode"),
        pytest.param("University of Toronto, Toronto, ON M5S 2E4, Canada", set(), id="postcode-after-a-code"),
        pytest.param("th Research Institute, China", {Sign.CUT_OFF}, id="ordinal-cut"),
        pytest.param("Nanjing University of Posts and", {Sign.CUT_OFF}, id="end-cut"),
        pytest.param("St Lucia, QLD, Australia", {Sign.PLACE_ONLY}, id="saint-is-not-a-cut"),
        pytest.param("Department of Computer Science and Engineering", {Sign.UNIT_ONLY}, id="unit-only"),
        pytest.param("Department of Computer Science, Stanford University", set(), id="unit-and-host"),
        pytest.param("School of Medicine, Yale University", set(), id="school-and-host"),
        pytest.param("Pittsburgh, PA 15213, USA", {Sign.PLACE_ONLY}, id="city-and-state"),
        pytest.param("Beijing 100084, China", {Sign.PLACE_ONLY}, id="city-and-postcode"),
        # Not told apart from a company: not counted.
        pytest.param("Tokyo, Japan", set(), id="city-and-country"),
        pytest.param("Google DeepMind, USA", set(), id="company-and-country"),
        pytest.param("Mayo Clinic, Rochester, MN, USA", set(), id="institution-then-city"),
        pytest.param("IRIT, UMR 5505, CNRS, Toulouse, France", set(), id="research-unit"),
    ],
)
def test_string_signs(affiliation: str, signs: set[Sign]) -> None:
    paper = replace(PAPER, affiliations=(affiliation,))
    assert set(string_signs(affiliation, paper)) == signs


def test_a_name_the_registry_knows_is_kept() -> None:
    paper = replace(PAPER, affiliations=("Bob Smith", "MIT"), institutions=("Bob Smith", None))
    assert names_only(paper) == []
    assert names_only(replace(paper, institutions=None)) == ["Bob Smith"]


type Mapping = tuple[tuple[int, ...] | None, ...]


def _mapped(mapping: Mapping | None) -> Paper:
    authors = PAPER.authors[: len(mapping)] if mapping else PAPER.authors
    return replace(PAPER, authors=authors, affiliations=("MIT", "NVIDIA"), author_affiliations=mapping)


@pytest.mark.parametrize("mapping", [(None, (0, 1)), (None, (1, 0))])
def test_the_last_author_holds_all(mapping: Mapping) -> None:
    assert last_holds_all(_mapped(mapping))


@pytest.mark.parametrize("mapping", [(None, (0,)), ((0,), (1,)), ((0, 1),), None])
def test_the_last_author_does_not_hold_all(mapping: Mapping | None) -> None:
    assert not last_holds_all(_mapped(mapping))


def test_affiliation_quality_counts_strings_and_papers() -> None:
    papers = [
        replace(PAPER, affiliations=("School of", "Code", "MIT")),
        replace(
            PAPER,
            arxiv_id="2609.00002",
            affiliations=("Department of Computer Science and Engineering", "NVIDIA"),
            author_affiliations=(None, (0, 1)),
        ),
        replace(PAPER, arxiv_id="2609.00003", affiliations=()),
        replace(PAPER, arxiv_id="2609.00004", affiliations=None),
    ]

    quality = affiliation_quality(papers)

    assert (quality.papers, quality.strings) == (2, 5)
    cleaning = quality.tallies[Sign.CLEANING]
    assert (cleaning.strings, cleaning.papers) == (2, 1)
    assert cleaning.examples == ["2609.00001: School of", "2609.00001: Code"]
    assert quality.tallies[Sign.UNIT_ONLY].examples == [
        "2609.00001: School of",
        "2609.00002: Department of Computer Science and Engineering",
    ]
    assert quality.tallies[Sign.CUT_OFF].examples == ["2609.00001: School of"]
    assert quality.tallies[Sign.LAST_HOLDS_ALL].examples == ["2609.00002"]
    assert quality.tallies[Sign.GLUED].strings == 0


def test_affiliation_quality_keeps_a_few_examples() -> None:
    papers = [replace(PAPER, arxiv_id=f"2609.{index:05}", affiliations=("Code",)) for index in range(9)]

    tally = affiliation_quality(papers).tallies[Sign.CLEANING]

    assert (tally.strings, tally.papers, len(tally.examples)) == (9, 9, EXAMPLES)


def test_format_quality() -> None:
    quality = affiliation_quality([replace(PAPER, affiliations=("Code", "MIT"))])

    text = format_quality("cs.CV: affiliations", quality)

    lines = text.splitlines()
    assert lines[:3] == ["cs.CV: affiliations", "2 affiliation strings in 1 paper", "sign" + lines[2][4:]]
    assert lines[2].split() == ["sign", "strings", "papers"]
    assert lines[3].split()[:4] == ["names", "authors", "0", "0"]
    assert lines[4].split()[:4] == ["cleaned", "again", "1", "1"]
    assert lines[5].strip() == "2609.00001: Code"
    assert len(lines) == 3 + len(Sign) + 1
    assert "2609.00001: Code" not in format_quality("cs.CV", quality, examples=False)


def test_quality_table_shows_brackets_as_written() -> None:
    quality = affiliation_quality([replace(PAPER, affiliations=("MIT [x]", "Code"))])
    console = Console(width=200, record=True)

    console.print(quality_table("cs.CV: affiliations", quality))

    text = console.export_text()
    assert "cs.CV: affiliations" in text
    assert "2 affiliation strings in 1 paper" in text
    assert "2609.00001: Code" in text


def test_extracted_again_reads_the_cached_pages_only(tmp_path: Path) -> None:
    cache = PageCache(tmp_path / "cache")
    url = "https://arxiv.org/html/2609.00001v1"
    cache.put(
        url,
        """<article class="ltx_document"><div class="ltx_authors">
        <span class="ltx_creator ltx_role_author"><span class="ltx_personname">Ada Lovelace</span>
        <span class="ltx_contact ltx_role_affiliation">Stanford University</span></span>
        </div></article>""",
    )
    cached = replace(PAPER, authors=("Ada Lovelace",), html_url=url, institutions=("MIT",))
    papers = [
        cached,
        replace(PAPER, arxiv_id="2609.00002", html_url="https://arxiv.org/html/2609.00002v1"),
        replace(PAPER, arxiv_id="2609.00003", html_url=None),
    ]

    pairs = extracted_again(papers, cache)

    assert [stored for stored, _ in pairs] == [cached]
    ((_, extracted),) = pairs
    assert extracted.affiliations == ("Stanford University",)
    assert extracted.author_affiliations == ((0,),)
    assert extracted.institutions is None
    assert extracted.extractor == EXTRACTOR_VERSION
