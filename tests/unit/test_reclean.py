from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from preprint_radar.models import Paper, Provenance
from preprint_radar.store.paper_store import PaperStore
from preprint_radar.store.reclean import RecleanReport, reclean_paper, reclean_store

AUTHORS = ("Ada Lovelace", "Bob Smith", "Carl Jones")


def _paper(
    affiliations: tuple[str, ...] | None,
    mapping: tuple[tuple[int, ...] | None, ...] | None = None,
    *,
    authors: tuple[str, ...] = AUTHORS,
    institutions: tuple[str | None, ...] | None = None,
    arxiv_id: str = "2609.00001",
) -> Paper:
    return Paper(
        arxiv_id=arxiv_id,
        announced=date(2026, 9, 25),
        title="T",
        authors=authors,
        affiliations=affiliations,
        author_affiliations=mapping,
        institutions=institutions,
    )


def test_leaves_clean_papers_and_papers_without_affiliations_alone() -> None:
    clean = _paper(("MIT", "Stanford University"), ((0,), (1,), None), institutions=("MIT", None))

    assert reclean_paper(clean) == clean
    assert reclean_paper(_paper(None)) == _paper(None)
    assert reclean_paper(_paper(())) == _paper(())
    # OpenAlex's names, of a paper without an HTML page, are no strings of a page (AFF-27).
    openalex = replace(_paper(("MIT", "Code"), None), affiliations_provenance=Provenance("openalex"))
    assert reclean_paper(openalex) is openalex


def test_drops_a_middle_string_and_shifts_the_mapping() -> None:
    paper = _paper(
        ("MIT", "Correspondence", "Stanford University"),
        ((0,), (1,), (1, 2)),
        institutions=("Massachusetts Institute of Technology", None, "Stanford University"),
    )

    recleaned = reclean_paper(paper)

    assert recleaned.affiliations == ("MIT", "Stanford University")
    # Bob was only placed at the dropped string.
    assert recleaned.author_affiliations == ((0,), None, (1,))
    # The strings changed: the next run names them again.
    assert recleaned.institutions is None


def test_splits_also_with_and_gives_the_author_every_part() -> None:
    paper = _paper(("MIT, USA, and also with NVIDIA, USA", "Stanford University"), ((0,), (1,), (0, 1)))

    recleaned = reclean_paper(paper)

    assert recleaned.affiliations == ("MIT, USA", "NVIDIA, USA", "Stanford University")
    assert recleaned.author_affiliations == ((0, 1), (2,), (0, 1, 2))


def test_merges_strings_that_clean_to_the_same_affiliation() -> None:
    paper = _paper(
        ("Ada Lovelace is with MIT", "Carl Jones is with MIT", "Bob Smith is with Stanford University"),
        ((0,), (2,), (1,)),
    )

    recleaned = reclean_paper(paper)

    assert recleaned.affiliations == ("MIT", "Stanford University")
    assert recleaned.author_affiliations == ((0,), (1,), (0,))


def test_drops_author_names_and_keeps_the_one_affiliation_left_to_its_people() -> None:
    paper = _paper(("Nicolás Ugrinovic", "Carnegie Mellon University"), (None, (0,), (1,)))
    paper = replace(paper, authors=("Ada Lovelace", "Nicolas Ugrinovic", "Carl Jones"))

    recleaned = reclean_paper(paper)

    assert recleaned.affiliations == ("Carnegie Mellon University",)
    # Not everyone's once a name was dropped; Carl, the last author alone, places nobody.
    assert recleaned.author_affiliations is None


def test_keeps_a_name_the_registry_named() -> None:
    authors = ("Ada Lovelace", "Open Vision")
    paper = _paper(("Open Vision", "MIT"), ((1,), (0,)), authors=authors, institutions=("Open Vision", "MIT"))

    assert reclean_paper(paper) == paper


def test_one_affiliation_is_everyones_and_one_author_holds_all() -> None:
    shared = _paper(("[5pt]", "Johns Hopkins University"), (None, None, (0, 1)))
    alone = _paper(("MIT", "Code", "NVIDIA"), (None,), authors=("Ada Lovelace",))

    assert reclean_paper(shared).author_affiliations == ((0,), (0,), (0,))
    assert reclean_paper(alone).author_affiliations == ((0, 1),)


def test_the_last_author_alone_holding_everything_places_nobody() -> None:
    paper = _paper(("MIT", "Stanford University"), (None, None, (0, 1)))

    recleaned = reclean_paper(paper)

    assert recleaned.affiliations == paper.affiliations
    assert recleaned.author_affiliations is None


def test_the_last_author_placed_at_part_of_the_affiliations_keeps_them() -> None:
    paper = _paper(("MIT", "Stanford University"), (None, None, (1,)))

    assert reclean_paper(paper) == paper


def test_sentences_that_name_people_place_them() -> None:
    # One string of several sentences, stored as everyone's.
    sentences = (
        "Ada Lovelace and Carl Jones are at Imperial College London. A. Lovelace is with the AI Lab. "
        "C. Jones is with CSAIL"
    )
    paper = _paper((sentences,), ((0,), (0,), (0,)))

    recleaned = reclean_paper(paper)

    assert recleaned.affiliations == ("Imperial College London", "AI Lab", "CSAIL")
    assert recleaned.author_affiliations == ((0, 1), None, (0, 2))


def test_the_authors_sentence_keeps_the_stored_mapping() -> None:
    # A footnote of the last two authors: "the authors" are not everyone.
    paper = _paper(("MIT", "The authors are also with NVIDIA"), ((0,), (0, 1), (0, 1)))

    recleaned = reclean_paper(paper)

    assert recleaned.affiliations == ("MIT", "NVIDIA")
    assert recleaned.author_affiliations == ((0,), (0, 1), (0, 1))


def test_a_sentence_naming_nobody_keeps_the_stored_mapping() -> None:
    paper = _paper(("Grace Hopper is with MIT", "Stanford University"), ((0,), (1,), (0, 1)))

    recleaned = reclean_paper(paper)

    assert recleaned.affiliations == ("MIT", "Stanford University")
    assert recleaned.author_affiliations == ((0,), (1,), (0, 1))


def test_nothing_left_means_tried_and_none_found() -> None:
    recleaned = reclean_paper(
        _paper(("Ada Lovelace, and Bob Smith",), ((0,), (0,), (0,)), institutions=(None,))
    )

    assert recleaned.affiliations == ()
    assert recleaned.author_affiliations is None
    assert recleaned.institutions is None


def test_reclean_store_rewrites_only_the_days_that_change(tmp_path: Path) -> None:
    store = PaperStore(tmp_path)
    dirty = _paper(("MIT", "the"), ((0,), (1,), (0,)), arxiv_id="2609.00001")
    clean = replace(_paper(("MIT",), ((0,), (0,), (0,)), arxiv_id="2609.00002"), announced=date(2026, 9, 24))
    store.save("cs.CV", [dirty, clean, _paper(None, arxiv_id="2609.00003")])
    untouched = tmp_path / "cs.CV" / "2026-09-24.json"
    untouched.write_text(untouched.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    report = reclean_store(store, "cs.CV")

    assert report == RecleanReport("cs.CV", papers=2, changed=1, days=1)
    assert untouched.read_text(encoding="utf-8").endswith("\n\n")
    stored = {paper.arxiv_id: paper for paper in store.iter_papers("cs.CV")}
    assert stored["2609.00001"].affiliations == ("MIT",)
    assert stored["2609.00001"].author_affiliations == ((0,), (0,), (0,))
    assert stored["2609.00003"].affiliations is None


def test_reclean_store_cleans_the_archives_papers_read_from_a_page(tmp_path: Path) -> None:
    store = PaperStore(tmp_path)
    read = replace(
        _paper(("\\authormark1Department of Physics, MIT",), ((0,), (0,), (0,)), arxiv_id="2505.00001"),
        announced=date(2025, 5, 2),
        affiliations_provenance=Provenance("html", date(2025, 5, 3)),
    )
    # OpenAlex's names, which the cleaner would damage, are left as they are.
    registry = replace(
        _paper(("IIT@MIT",), ((0,), (0,), (0,)), arxiv_id="2505.00002"),
        announced=date(2025, 5, 2),
        affiliations_provenance=Provenance("openalex", date(2025, 5, 3)),
    )
    store.write_archive("cs.CV", [read, registry])
    store.write_top_recent("cs.CV", [read], since=date(2025, 10, 28))

    report = reclean_store(store, "cs.CV")

    assert report == RecleanReport("cs.CV", papers=2, changed=2, days=0, archive=True)
    archived = {paper.arxiv_id: paper for paper in store.iter_archive("cs.CV")}
    assert archived["2505.00001"].affiliations == ("Department of Physics, MIT",)
    assert archived["2505.00002"].affiliations == ("IIT@MIT",)
    assert [paper.affiliations for paper in store.iter_top_recent("cs.CV")] == [
        ("Department of Physics, MIT",)
    ]
    assert reclean_store(store, "cs.CV") == RecleanReport("cs.CV", papers=2, changed=0, days=0)


def test_a_paper_without_mapping_gets_the_one_its_sentences_give() -> None:
    paper = _paper(
        ("Ada Lovelace and Carl Jones are with MIT", "Bob Smith is with NVIDIA, and also with NVIDIA")
    )

    recleaned = reclean_paper(paper)

    assert recleaned.affiliations == ("MIT", "NVIDIA")
    assert recleaned.author_affiliations == ((0,), (1,), (0,))


@pytest.mark.parametrize(
    "paper",
    [
        pytest.param(_paper(("Nicolás Ugrinovic", "MIT"), ((0,), None, (1,))), id="name-dropped-next-to-one"),
        pytest.param(_paper(("Ada Lovelace, and Bob Smith", "MIT"), ((0,), (0,), (1,))), id="names-then-one"),
        pytest.param(_paper(("[5pt]", "MIT"), (None, (1,), None)), id="junk-then-one"),
        pytest.param(
            _paper(("C. Jones is with MIT", "C. Jones is with NVIDIA")), id="sentences-for-the-last"
        ),
        pytest.param(
            _paper(("MIT, and also with NVIDIA", "Code"), (None, None, (0,))), id="split-for-the-last"
        ),
    ],
)
def test_a_second_pass_changes_nothing(paper: Paper) -> None:
    once = reclean_paper(replace(paper, authors=("Ada Lovelace", "Nicolas Ugrinovic", "Carl Jones")))

    assert reclean_paper(once) == once
