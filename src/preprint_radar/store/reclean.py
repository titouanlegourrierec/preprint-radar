"""Clean the stored affiliations again with today's rules, without fetching anything.

The HTML front matter of a paper is read once, so a fix to the cleaning heuristics of
``sources/arxiv_html.py`` only reaches the papers announced after it. ``reclean`` applies
the rules that need no page to the stored strings: :func:`clean_affiliations` (contact
details, junk, "A is with X" sentences, "also with" lists) and :func:`names_only_authors`.
The author mapping follows the strings, and the mapping rules that need no page run again.

Day files only: the archive's affiliations are OpenAlex institution names, which the
cleaner would damage ("IIT@MIT").
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace

from preprint_radar.models import Paper
from preprint_radar.sources.arxiv_html import (
    AuthorAffiliations,
    clean_affiliations,
    map_stated_affiliations,
    names_only_authors,
    states_people,
)
from preprint_radar.store.paper_store import PaperStore


@dataclass(frozen=True, slots=True)
class RecleanReport:
    """What :func:`reclean_store` changed in one category.

    Attributes:
        category: The arXiv category.
        papers: Papers with affiliations, all looked at.
        changed: Papers whose affiliations, mapping or institutions changed.
        days: Day files written again.
    """

    category: str
    papers: int
    changed: int
    days: int


def reclean_store(store: PaperStore, category: str) -> RecleanReport:
    """Clean the affiliations of every stored day of a category again.

    Only the day files holding a changed paper are written.

    Args:
        store: The data store.
        category: The arXiv category.

    Returns:
        What was looked at and changed.
    """
    papers = changed = days = 0
    for day in store.days(category):
        stored = store.load_day(category, day)
        recleaned = [reclean_paper(paper) for paper in stored]
        papers += sum(1 for paper in stored if paper.affiliations)
        updated = [new for old, new in zip(stored, recleaned, strict=True) if new != old]
        if updated:
            store.save(category, updated)
            changed += len(updated)
            days += 1
    return RecleanReport(category, papers, changed, days)


def reclean_paper(paper: Paper) -> Paper:
    """The paper with its affiliations cleaned by today's rules.

    Each stored string is cleaned again, and dropped when it only names the paper's authors
    (unless the Research Organization Registry named it). The author mapping follows the
    strings through an old-to-new index table, and an author left without affiliation
    becomes ``None``. Then the rules that need no page: one author holds every
    affiliation; one affiliation is everyone's, unless author names were dropped next to
    it; "A and B are with X" sentences place the authors they name; and the last author
    alone holding every affiliation places nobody (a block LaTeXML attached to the last
    author). The institutions are reset to ``None`` when the strings change, so that the
    next run names them again. Running it twice changes nothing more.

    Args:
        paper: A stored paper.

    Returns:
        The paper, unchanged when today's rules agree with what is stored.
    """
    if not paper.affiliations:
        return paper
    institutions = paper.institutions or (None,) * len(paper.affiliations)
    affiliations: list[str] = []
    index_of: dict[str, int] = {}
    remap: list[tuple[int, ...]] = []
    names_dropped = False
    for text, institution in zip(paper.affiliations, institutions, strict=True):
        parts = clean_affiliations(text)
        kept = [
            part for part in parts if institution is not None or not names_only_authors(part, paper.authors)
        ]
        names_dropped = names_dropped or len(kept) < len(parts)
        indices: list[int] = []
        for part in kept:
            index = index_of.setdefault(part.casefold(), len(affiliations))
            if index == len(affiliations):
                affiliations.append(part)
            if index not in indices:
                indices.append(index)
        remap.append(tuple(indices))

    cleaned = tuple(affiliations)
    mapping = _mapping(paper, paper.affiliations, cleaned, remap, names_dropped=names_dropped)
    return replace(
        paper,
        affiliations=cleaned,
        author_affiliations=mapping,
        institutions=paper.institutions if cleaned == paper.affiliations else None,
        institution_ids=paper.institution_ids if cleaned == paper.affiliations else None,
    )


def _mapping(
    paper: Paper,
    stored: tuple[str, ...],
    affiliations: tuple[str, ...],
    remap: Sequence[tuple[int, ...]],
    *,
    names_dropped: bool,
) -> AuthorAffiliations | None:
    """The author mapping of the cleaned affiliations (see :func:`reclean_paper`).

    ``stored`` are the paper's strings before cleaning, and ``remap`` gives the new indices
    of each of them.
    """
    if not affiliations:
        return None
    everything = tuple(range(len(affiliations)))
    # One affiliation is everyone's, as the parser has it, unless author names were dropped
    # next to it. Only when this pass changed the strings: a second pass no longer knows that
    # names were dropped, and would give everyone what the first one left to its people.
    if len(paper.authors) == 1 or (len(affiliations) == 1 and affiliations != stored and not names_dropped):
        return (everything,) * len(paper.authors)
    # A sentence that names people places them itself, whatever was stored: a mapping made
    # from the whole sentence may give it to everyone (2609.34010 names three of its five
    # authors). "The authors are with X" names nobody: written in the footnote of some
    # authors (2609.20566), it leaves their stored mapping as it is.
    stated = [
        map_stated_affiliations([text], paper.authors, affiliations, everyone=False)
        if states_people(text)
        else None
        for text in stored
    ]
    followed = [() if placed is not None else indices for placed, indices in zip(stated, remap, strict=True)]
    entries: list[tuple[int, ...] | None] = [None] * len(paper.authors)
    if paper.author_affiliations is not None:
        entries = [_follow(entry, followed) for entry in paper.author_affiliations]
    for placed in filter(None, stated):
        entries = [_union(entry, extra) for entry, extra in zip(entries, placed, strict=True)]
    if not any(entries) or _last_holds_all(entries, everything):
        return None
    return tuple(entries)


def _follow(entry: tuple[int, ...] | None, remap: Sequence[tuple[int, ...]]) -> tuple[int, ...] | None:
    """An author's old indices, as indices into the cleaned affiliations; ``None`` if none is left."""
    if entry is None:
        return None
    indices: list[int] = []
    for old in entry:
        indices.extend(index for index in remap[old] if index not in indices)
    return tuple(indices) or None


def _union(entry: tuple[int, ...] | None, extra: tuple[int, ...] | None) -> tuple[int, ...] | None:
    return tuple(dict.fromkeys((*(entry or ()), *(extra or ())))) or None


def _last_holds_all(entries: Sequence[tuple[int, ...] | None], everything: tuple[int, ...]) -> bool:
    """Whether only the last author is placed, at every affiliation of the paper."""
    *others, last = entries
    return all(entry is None for entry in others) and set(last or ()) == set(everything)
