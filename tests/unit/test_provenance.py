from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from preprint_radar.models import Paper, Provenance
from preprint_radar.store.paper_store import PaperStore
from preprint_radar.store.provenance import infer_provenance_again, inferred

PAPER = Paper(
    arxiv_id="2609.00001",
    announced=date(2026, 9, 1),
    title="A paper",
    authors=("Ada Lovelace", "Alan Turing"),
    html_url="https://arxiv.org/html/2609.00001v1",
    affiliations=("MIT",),
)


@pytest.mark.parametrize(
    ("changes", "affiliations", "institutions"),
    [
        pytest.param({"extractor": 3, "institutions": (None,)}, "html", "ror", id="versioned"),
        pytest.param(
            {"html_url": None, "institutions": ("MIT",)},
            "openalex",
            "openalex",
            id="archived-from-the-catalog",
        ),
        pytest.param({"author_affiliations": ((0,), None)}, "html", None, id="mapped"),
        pytest.param({"affiliations": ()}, "html", None, id="none-found"),
        pytest.param({"institutions": ("MIT",)}, None, "ror", id="declared-or-unmapped"),
        pytest.param({"affiliations": None}, None, None, id="not-read-yet"),
    ],
)
def test_the_record_tells_where_its_affiliations_came_from(
    changes: dict[str, object], affiliations: str | None, institutions: str | None
) -> None:
    paper = inferred(replace(PAPER, **changes))

    assert paper.affiliations_provenance == (None if affiliations is None else Provenance(affiliations))
    assert paper.institutions_provenance == (None if institutions is None else Provenance(institutions))


def test_a_known_provenance_stays() -> None:
    known = replace(
        PAPER,
        institutions=("MIT",),
        affiliations_provenance=Provenance("api", date(2026, 10, 6)),
        institutions_provenance=Provenance("ror", date(2026, 10, 6)),
    )

    assert inferred(known) == known


def test_the_store_gets_the_provenance_of_its_records(tmp_path: Path) -> None:
    store = PaperStore(tmp_path / "data")
    store.save(
        "cs.CV",
        [
            replace(PAPER, extractor=3),
            replace(PAPER, arxiv_id="2609.00002"),
            replace(PAPER, arxiv_id="2609.00003", affiliations=None),
        ],
    )
    store.write_archive(
        "cs.CV", [replace(PAPER, arxiv_id="1512.03385", announced=date(2015, 12, 10), html_url=None)]
    )

    report = infer_provenance_again(store, "cs.CV")

    # 2609.00002 is the unknown one; 2609.00003 has nothing to tell.
    assert (report.papers, dict(report.sources), report.unknown) == (4, {"html": 1, "openalex": 1}, 1)
    stored = {paper.arxiv_id: paper for paper in store.iter_papers("cs.CV")}
    assert stored["2609.00001"].affiliations_provenance == Provenance("html")
    [archived] = store.iter_archive("cs.CV")
    assert archived.affiliations_provenance == Provenance("openalex")

    files = {path: path.stat().st_mtime_ns for path in (tmp_path / "data").rglob("*.json")}
    assert infer_provenance_again(store, "cs.CV") == report
    assert {path: path.stat().st_mtime_ns for path in (tmp_path / "data").rglob("*.json")} == files
