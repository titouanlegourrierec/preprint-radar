from dataclasses import dataclass, replace
from datetime import date

from preprint_radar.models import Paper
from preprint_radar.steps import StepCount, enrich, format_counts

DAY = date(2026, 10, 21)


def _paper(arxiv_id: str, abstract: str | None = None) -> Paper:
    return Paper(
        arxiv_id=arxiv_id, announced=DAY, title=f"Paper {arxiv_id}", authors=("A One",), abstract=abstract
    )


@dataclass
class Abstracts:
    """Gives an abstract to at most ``budget`` papers without one."""

    budget: int
    name = "Abstracts"

    def needs(self, paper: Paper) -> bool:
        return paper.abstract is None

    def run(self, papers: list[Paper]) -> list[Paper]:
        given = 0
        enriched = []
        for paper in papers:
            if self.needs(paper) and given < self.budget:
                enriched.append(replace(paper, abstract="An abstract."))
                given += 1
            else:
                enriched.append(paper)
        return enriched


@dataclass
class Titles:
    """Upper-cases every title: only papers without a title would need it."""

    name = "Titles"

    def needs(self, paper: Paper) -> bool:
        return not paper.title

    def run(self, papers: list[Paper]) -> list[Paper]:
        return [replace(paper, title=paper.title.upper()) for paper in papers]


def test_enrich_runs_each_step_in_turn_and_counts_what_it_did() -> None:
    papers = [_paper("2610.00001"), _paper("2610.00002", "Known."), _paper("2610.00003")]
    saved: list[list[str | None]] = []

    enriched, counts = enrich(
        papers,
        [Abstracts(budget=1), Titles()],
        checkpoint=lambda current: saved.append([paper.abstract for paper in current]),
    )

    assert [paper.abstract for paper in enriched] == ["An abstract.", "Known.", None]
    assert [paper.title for paper in enriched] == ["PAPER 2610.00001", "PAPER 2610.00002", "PAPER 2610.00003"]
    # Two needed an abstract, the budget gave one: the other is left for a later run.
    assert counts == (StepCount("Abstracts", 2, 1, 1), StepCount("Titles", 0, 0, 0))
    # Saved after each step, as it left the papers.
    assert saved == [["An abstract.", "Known.", None], ["An abstract.", "Known.", None]]


def test_enrich_without_steps_or_checkpoint_changes_nothing() -> None:
    papers = [_paper("2610.00001")]

    assert enrich(papers, []) == (papers, ())


def test_the_counts_of_a_run_read_as_one_line() -> None:
    counts = (
        StepCount("Abstracts", 0, 0, 0),
        StepCount("HTML pages", 1_346, 1_330, 16),
        StepCount("ROR institutions", 289, 289, 0),
    )

    assert format_counts(counts) == "HTML pages: 1,330 of 1,346, 16 left; ROR institutions: 289 of 289"
    assert format_counts(counts[:1]) == ""
