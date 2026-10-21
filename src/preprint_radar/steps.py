"""Enrichment steps: what a paper lacks, and the step that gives it (ARCH-2, DEBT-1).

Each enrichment of the stored papers says which papers need it (:meth:`Step.needs`, its
missing test) and gives it to as many as its budget allows (:meth:`Step.run`): the
abstracts, the affiliations of the HTML pages, their institutions through ROR, OpenAlex's
for the papers no page gave any. :func:`enrich` runs steps in turn, saving after each, and
counts what each did (:class:`StepCount`), which the run's report gives. The steps that
write a file of their own (citation counts, published versions, stars, countries) count
what they did the same way.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from preprint_radar.models import Paper


@dataclass(frozen=True, slots=True)
class StepCount:
    """What one step did in a run.

    Attributes:
        step: The step's name, as the run's summary gives it ("HTML pages").
        asked: Papers that needed it when the run began.
        done: Of those, papers it gave what they lacked, or an answer that there is none.
        left: Papers that still need it, for a later run: past a budget or a deadline, or a
            service that failed.
    """

    step: str
    asked: int
    done: int
    left: int


class Step(Protocol):
    """One enrichment of papers, as :func:`enrich` runs it."""

    @property
    def name(self) -> str:
        """The step's name, as the run's summary gives it."""
        ...

    def needs(self, paper: Paper) -> bool:
        """Whether the paper lacks what the step gives, and a run can still give it."""
        ...

    def run(self, papers: list[Paper]) -> list[Paper]:
        """The papers, in their order, with what the step gave those that need it."""
        ...


def enrich(
    papers: Sequence[Paper],
    steps: Iterable[Step],
    *,
    checkpoint: Callable[[list[Paper]], object] | None = None,
) -> tuple[list[Paper], tuple[StepCount, ...]]:
    """Run each step on the papers in turn, saving after each, and count what each did.

    Args:
        papers: The papers to enrich.
        steps: The steps, in order: each gets the papers as the one before left them.
        checkpoint: Called with the papers after each step: their save.

    Returns:
        The papers, enriched, and what each step did.
    """
    current = list(papers)
    counts: list[StepCount] = []
    for step in steps:
        asked = sum(step.needs(paper) for paper in current)
        current = step.run(current)
        left = sum(step.needs(paper) for paper in current)
        counts.append(StepCount(step.name, asked, max(asked - left, 0), left))
        if checkpoint is not None:
            checkpoint(current)
    return current, tuple(counts)


def format_counts(counts: Iterable[StepCount]) -> str:
    """The counts of a run's steps as one line: "HTML pages: 330 of 346, 16 left; ...".

    A step nothing needed is left out; the line is empty when none was.
    """
    return "; ".join(
        f"{count.step}: {count.done:,} of {count.asked:,}" + (f", {count.left:,} left" if count.left else "")
        for count in counts
        if count.asked
    )
