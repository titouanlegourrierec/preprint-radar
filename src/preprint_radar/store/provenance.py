"""The provenance of what was stored before it was kept (META-3), inferred from the records.

Run once over the store when provenance was introduced; what is written afterwards carries
its own. Days are never invented: the inferred provenance has none. A record says enough
for most papers:

- affiliations with an extraction version came from the HTML page;
- an archived paper without an HTML URL was built from the catalog: its affiliations came
  from OpenAlex, and so did its institutions (a day-file paper loses its HTML URL when a
  later version has no rendering: 2609.34579 kept the affiliations of its first);
- affiliations with an author mapping, or an empty list, came from the HTML page: the
  submitter-declared ones of the arXiv API never come with a mapping, nor empty;
- other institutions were named by ROR.

What remains is a paper read before extraction versions were kept, whose affiliations have
no mapping: declared through the API, or read from a page that does not say who is where.
It keeps no affiliations provenance.
"""

from collections import Counter
from dataclasses import dataclass, replace

from preprint_radar.models import Paper, Provenance
from preprint_radar.store.paper_store import PaperStore


@dataclass(frozen=True, slots=True)
class ProvenanceReport:
    """What :func:`infer_provenance_again` found.

    Attributes:
        papers: Papers looked at, day files and archive.
        sources: Papers given an affiliations provenance, by source.
        unknown: Papers with affiliations whose source cannot be told.
    """

    papers: int
    sources: Counter[str]
    unknown: int


def inferred(paper: Paper, *, archived: bool = False) -> Paper:
    """The paper with the provenance its record implies, where it has none yet.

    Args:
        paper: A stored paper.
        archived: Whether it is a record of the archive rather than of a day file.
    """
    affiliations = paper.affiliations_provenance or _affiliations_source(paper, archived=archived)
    institutions = paper.institutions_provenance
    if institutions is None and paper.institutions is not None:
        from_openalex = affiliations is not None and affiliations.source == "openalex"
        institutions = Provenance("openalex" if from_openalex else "ror")
    return replace(paper, affiliations_provenance=affiliations, institutions_provenance=institutions)


def _affiliations_source(paper: Paper, *, archived: bool) -> Provenance | None:
    if paper.affiliations is None:
        return None
    if paper.extractor is not None:
        return Provenance("html")
    if archived and paper.html_url is None:
        return Provenance("openalex")
    if paper.author_affiliations is not None or not paper.affiliations:
        return Provenance("html")
    return None


def infer_provenance_again(store: PaperStore, category: str) -> ProvenanceReport:
    """Give every stored paper of a category the provenance its record implies.

    Only the day files holding a changed paper are written, and the archive only when one
    of its papers changed.
    """
    sources: Counter[str] = Counter()
    papers = unknown = 0

    def count(paper: Paper) -> None:
        nonlocal papers, unknown
        papers += 1
        if paper.affiliations_provenance is not None:
            sources[paper.affiliations_provenance.source] += 1
        elif paper.affiliations is not None:
            unknown += 1

    for day in store.days(category):
        stored = store.load_day(category, day)
        updated = [inferred(paper) for paper in stored]
        for paper in updated:
            count(paper)
        if changed := [new for old, new in zip(stored, updated, strict=True) if new != old]:
            store.save(category, changed)
    archived = list(store.iter_archive(category))
    updated = [inferred(paper, archived=True) for paper in archived]
    for paper in updated:
        count(paper)
    if updated != archived:
        store.write_archive(category, updated)
    return ProvenanceReport(papers=papers, sources=sources, unknown=unknown)
