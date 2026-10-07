from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from preprint_radar.cli import main
from preprint_radar.models import Paper, Provenance
from preprint_radar.store.naming import NamingReport, name_institutions_again, named_again
from preprint_radar.store.paper_store import PaperStore

PAPER = Paper(
    arxiv_id="2609.00001",
    announced=date(2026, 9, 24),
    title="T",
    authors=("Ada Lovelace",),
    affiliations=("School of CS, Peking University", "CMU", "Google Research, Zurich", "Ada Lovelace"),
    institutions=("Peking University", None, "Google (Switzerland)", None),
    institution_ids=("02v51f717", None, "00njsd438", None),
    institutions_provenance=Provenance("ror", date(2026, 9, 24)),
)


def test_registry_names_stay_and_the_rules_name_the_rest() -> None:
    named = named_again(PAPER)

    # The company's name for its subsidiary; the rules for the rest; never an author.
    assert named.institutions == ("Peking University", "Carnegie Mellon University", "Google", None)
    assert named.institution_ids == PAPER.institution_ids
    assert named_again(named) is named


def test_openalex_names_are_registry_names_without_ids() -> None:
    archived = replace(
        PAPER,
        arxiv_id="1511.00001",
        affiliations=("Tencent (China)", "Peking University"),
        institutions=("Tencent (China)", "Peking University"),
        institution_ids=None,
        institutions_provenance=Provenance("openalex"),
    )

    assert named_again(archived).institutions == ("Tencent", "Peking University")


@pytest.mark.parametrize(
    "paper",
    [
        replace(PAPER, institutions=None, institution_ids=None, institutions_provenance=None),
        replace(
            PAPER,
            affiliations=None,
            author_affiliations=None,
            institutions=None,
            institution_ids=None,
            institutions_provenance=None,
        ),
    ],
    ids=["not-named-yet", "not-read-yet"],
)
def test_papers_not_named_yet_are_left_to_ror(paper: Paper) -> None:
    assert named_again(paper) is paper


def test_names_the_store_again(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = PaperStore(tmp_path / "data")
    store.save("cs.CV", [PAPER])
    store.write_archive(
        "cs.CV",
        [
            replace(
                PAPER,
                arxiv_id="1511.00001",
                announced=date(2015, 11, 2),
                institutions_provenance=Provenance("openalex"),
            )
        ],
    )

    report = name_institutions_again(store, "cs.CV")

    assert report == NamingReport(
        category="cs.CV", papers=2, unnamed_before=4, unnamed_after=2, changed=2, days=1, archive=True
    )
    [stored] = store.iter_papers("cs.CV")
    assert stored.institutions == ("Peking University", "Carnegie Mellon University", "Google", None)
    again = name_institutions_again(store, "cs.CV")
    assert (again.changed, again.days, again.archive) == (0, 0, False)

    assert main(["institutions", "--again", "--data-dir", str(tmp_path / "data")]) == 0
    assert (
        "cs.CV: 0 of 2 papers changed, in 0 day files; affiliations without an institution 2 -> 2"
        in capsys.readouterr().out
    )
