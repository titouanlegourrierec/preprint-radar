"""Name the stored institutions again with today's rules, without asking any registry (AFF-13).

An institution is named once, when ROR (day files) or OpenAlex (archive) is asked
(``collect.add_institutions``, the archive's OpenAlex step): the registry's name, a
company's subsidiaries named as the company, and the rules' name where the registry gave
none (``institutions.name_institutions``). After a change to those rules, ``institutions
--again`` applies it to the stored papers: what a registry named keeps its name (it is
only made canonical again), and the rest is named again from its affiliation string.
"""

from dataclasses import dataclass, replace

from preprint_radar.institutions import ids_where_named, name_institutions
from preprint_radar.models import Paper
from preprint_radar.store.paper_store import PaperStore


@dataclass(frozen=True, slots=True)
class NamingReport:
    """What :func:`name_institutions_again` changed in one category.

    Attributes:
        category: The arXiv category.
        papers: Papers looked at, day files and archive (the most cited of the last 12
            months with it).
        unnamed_before: Affiliations without an institution before.
        unnamed_after: Affiliations without an institution after.
        changed: Papers whose institutions changed.
        days: Day files written again.
        archive: Whether the archive, or the most cited papers of the last 12 months, was
            written again.
    """

    category: str
    papers: int
    unnamed_before: int
    unnamed_after: int
    changed: int
    days: int
    archive: bool


def name_institutions_again(store: PaperStore, category: str) -> NamingReport:
    """Name the institutions of every stored paper of a category again.

    Papers whose institutions are not named yet are left to ``institutions``. Only the day
    files holding a changed paper are written, and the archive, or the most cited papers of
    the last 12 months, only when one of its papers changed.

    Args:
        store: The data store.
        category: The arXiv category.

    Returns:
        What was looked at and changed.
    """
    papers = before = after = changed = days = 0
    for day in store.days(category):
        stored = store.load_day(category, day)
        named = [named_again(paper) for paper in stored]
        updated = [new for old, new in zip(stored, named, strict=True) if new != old]
        papers += len(stored)
        before += sum(_unnamed(paper) for paper in stored)
        after += sum(_unnamed(paper) for paper in named)
        if updated:
            store.save(category, updated)
            changed += len(updated)
            days += 1
    archive = list(store.iter_archive(category))
    top_recent = store.load_top_recent(category)
    recent = top_recent.papers if top_recent else []
    new_archive = [named_again(paper) for paper in archive]
    new_recent = [named_again(paper) for paper in recent]
    if new_archive != archive:
        store.write_archive(category, new_archive)
    if top_recent and new_recent != recent:
        store.write_top_recent(category, new_recent, since=top_recent.since)
    # The most cited papers of the last 12 months are counted with the archive.
    archived, named = [*archive, *recent], [*new_archive, *new_recent]
    archive_changed = sum(new != old for old, new in zip(archived, named, strict=True))
    return NamingReport(
        category=category,
        papers=papers + len(archived),
        unnamed_before=before + sum(_unnamed(paper) for paper in archived),
        unnamed_after=after + sum(_unnamed(paper) for paper in named),
        changed=changed + archive_changed,
        days=days,
        archive=archive_changed > 0,
    )


def named_again(paper: Paper) -> Paper:
    """The paper with its institutions named again by today's rules.

    A name with a ROR id, or from OpenAlex, came from a registry: it stays, made canonical
    again. Any other was the rules': it is named again from its affiliation string.

    Args:
        paper: A stored paper.

    Returns:
        The paper, its institutions named again.
    """
    if paper.affiliations is None or paper.institutions is None:
        return paper
    ids = paper.institution_ids or (None,) * len(paper.institutions)
    provenance = paper.institutions_provenance
    from_openalex = provenance is not None and provenance.source == "openalex"
    registered = [
        name if name is not None and (ror_id is not None or from_openalex) else None
        for name, ror_id in zip(paper.institutions, ids, strict=True)
    ]
    names = name_institutions(paper.affiliations, registered, paper.authors)
    if names == paper.institutions:
        return paper
    return replace(paper, institutions=names, institution_ids=ids_where_named(paper.institution_ids, names))


def _unnamed(paper: Paper) -> int:
    return sum(name is None for name in paper.institutions or ())
