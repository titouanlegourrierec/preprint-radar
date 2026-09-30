"""Weekly archive update: keep the most cited older papers, within a size budget.

The store keeps every paper of the last 12 months in its day files, and an archive of
older papers chosen by citations per year of age (:mod:`preprint_radar.selection`). Each
week, :func:`update_archive`:

1. refreshes the category's catalog from OAI-PMH (:mod:`preprint_radar.catalog`);
2. fetches the citation counts of every paper since 2010 (:mod:`preprint_radar.citations`);
3. selects the archive, and builds the papers that enter it: from the day files when they
   graduate from the rolling year (enrichment kept), else from the catalog, with
   affiliations from OpenAlex (:mod:`preprint_radar.openalex`);
4. writes the archive, the citation counts of the stored papers and the index, and, when
   asked to, deletes the day files older than 12 months.
"""

import json
import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import date

from preprint_radar.catalog import Catalog, CatalogEntry
from preprint_radar.citations import fetch_citation_counts
from preprint_radar.http import HttpClient
from preprint_radar.models import Paper
from preprint_radar.openalex import fetch_affiliations
from preprint_radar.selection import RECENT_DAYS, Candidate, Selection, select_archive
from preprint_radar.store import PaperStore
from preprint_radar.venue import extract_venue

logger = logging.getLogger(__name__)

ARCHIVE_SINCE = date(2010, 1, 1)
# The archive only changes, and day files are only deleted, when nearly every candidate
# has a citation count: with counts missing (Semantic Scholar down), papers that deserve
# the archive would score nothing and be lost.
MIN_COVERAGE = 0.95
CITATION_SOURCE = "Semantic Scholar"
_SUBJECT_CODE_RE = re.compile(r"\(([^()]+)\)\s*$")


@dataclass(frozen=True, slots=True)
class ArchiveClients:
    """HTTP clients of the services the archive update uses."""

    oai: HttpClient
    citations: HttpClient
    openalex: HttpClient
    #: Semantic Scholar API key, ``None`` for anonymous requests.
    citations_key: str | None = None


@dataclass(frozen=True, slots=True)
class ArchiveReport:
    """Summary of an archive update.

    Attributes:
        category: Updated category.
        candidates: Papers since 2010 in the catalog.
        coverage: Share of them with a citation count.
        threshold: Citations per year of the last paper within the budget.
        archived: Papers in the archive after the update.
        entered: Papers that entered it.
        left: Papers that left it.
        pruned_days: Day files deleted (older than 12 months).
        written: Whether anything was written (not a dry run).
    """

    category: str
    candidates: int
    coverage: float
    threshold: float
    archived: int
    entered: int
    left: int
    pruned_days: int
    written: bool


def update_archive(
    category: str,
    *,
    store: PaperStore,
    catalog: Catalog,
    clients: ArchiveClients,
    budget: int,
    today: date,
    prune: bool = False,
    dry_run: bool = False,
) -> ArchiveReport:
    """Update the archive of ``category``; see the module documentation.

    Args:
        category: arXiv category, e.g. ``"cs.CV"``.
        store: Data store.
        catalog: Catalog of the category.
        clients: HTTP clients for OAI-PMH, Semantic Scholar and OpenAlex.
        budget: Number of older papers the archive aims to hold.
        today: Day of the update.
        prune: Delete the day files older than 12 months (their archived papers are kept).
        dry_run: Compute and report, write nothing.

    Returns:
        A summary of the update.

    Raises:
        FetchError: If the catalog cannot be refreshed.
        ParseError: If an OAI-PMH page is invalid.
    """
    catalog.refresh(clients.oai, today)
    entries = {
        arxiv_id: entry for arxiv_id, entry in catalog.entries().items() if entry.first_seen >= ARCHIVE_SINCE
    }
    stored_days = {day: store.load_day(category, day) for day in store.days(category)}
    stale_days = [day for day in stored_days if (today - day).days >= RECENT_DAYS] if prune else []
    recent_ids = {
        paper.arxiv_id for day, papers in stored_days.items() if day not in stale_days for paper in papers
    }
    archived = {paper.arxiv_id: paper for paper in store.iter_archive(category)}

    wanted = [*entries, *recent_ids, *archived]
    counts = _citation_counts(catalog, clients, wanted, today)
    coverage = sum(arxiv_id in counts for arxiv_id in entries) / max(1, len(entries))
    logger.info("%s: citation counts for %.1f%% of %d candidates", category, 100 * coverage, len(entries))
    if coverage < MIN_COVERAGE:
        logger.warning(
            "Only %.1f%% of citation counts: the archive and day files stay as they are", 100 * coverage
        )
        stale_days = []
        selection = Selection(keep=frozenset(archived), entered=frozenset(), left=frozenset(), threshold=0.0)
    else:
        selection = select_archive(
            (
                Candidate(arxiv_id, entry.first_seen, counts.get(arxiv_id))
                for arxiv_id, entry in entries.items()
                if arxiv_id not in recent_ids
            ),
            set(archived),
            budget=budget,
            today=today,
        )
    graduating = {paper.arxiv_id: paper for day in stale_days for paper in stored_days[day]}
    subjects = _subject_names(paper for papers in stored_days.values() for paper in papers)
    new_papers = [
        graduating.get(arxiv_id) or paper_from_catalog(entries[arxiv_id], category, subjects)
        for arxiv_id in sorted(selection.entered)
        if arxiv_id in graduating or arxiv_id in entries
    ]
    logger.info(
        "%s: %d archived, %d entering, %d leaving (threshold %.1f citations a year)",
        category,
        len(selection.keep),
        len(selection.entered),
        len(selection.left),
        selection.threshold,
    )

    report = ArchiveReport(
        category=category,
        candidates=len(entries),
        coverage=coverage,
        threshold=selection.threshold,
        archived=len(selection.keep),
        entered=len(selection.entered),
        left=len(selection.left),
        pruned_days=len(stale_days),
        written=not dry_run,
    )
    if dry_run:
        return report

    kept = [paper for arxiv_id, paper in archived.items() if arxiv_id in selection.keep]
    # Entering papers, and archived ones OpenAlex did not return last time.
    store.write_archive(category, _with_affiliations([*kept, *new_papers], clients.openalex))
    store.remove_days(category, stale_days)
    stored_ids = recent_ids | selection.keep
    store.write_citations(
        category,
        {arxiv_id: count for arxiv_id in stored_ids if (count := counts.get(arxiv_id)) is not None},
        source=CITATION_SOURCE,
    )
    store.write_index()
    return report


def paper_from_catalog(entry: CatalogEntry, category: str, subjects: Mapping[str, str]) -> Paper:
    """A paper of the archive, built from its catalog entry (affiliations not looked up yet).

    Args:
        entry: Catalog entry.
        category: Category of the archive; another primary category makes a cross-list.
        subjects: Full subject names by code ("cs.LG" -> "Machine Learning (cs.LG)");
            codes without a name are kept as they are.
    """
    primary = entry.categories[0] if entry.categories else category
    return Paper(
        arxiv_id=entry.arxiv_id,
        announced=entry.first_seen,
        title=entry.title,
        authors=entry.authors,
        primary_subject=subjects.get(primary, primary),
        subjects=tuple(subjects.get(code, code) for code in entry.categories),
        comments=entry.comments,
        journal_ref=entry.journal_ref,
        venue=extract_venue(entry.comments, entry.journal_ref),
        cross_list_from=None if primary == category else primary,
        abstract=entry.abstract,
    )


def format_archive_report(report: ArchiveReport) -> str:
    """Render an :class:`ArchiveReport` as a one-line human-readable summary."""
    return (
        f"{report.category}: {report.archived} archived papers ({report.entered} in, {report.left} out), "
        f"threshold {report.threshold:.1f} citations a year, citation counts for "
        f"{100 * report.coverage:.1f}% of {report.candidates} papers, {report.pruned_days} day files pruned"
        + ("" if report.written else " (dry run: nothing written)")
    )


def _citation_counts(
    catalog: Catalog, clients: ArchiveClients, arxiv_ids: Iterable[str], today: date
) -> dict[str, int | None]:
    """Citation counts, resuming a run interrupted the same day from a cache file."""
    cache = catalog.directory / f"{catalog.category}.citations.jsonl"
    counts: dict[str, int | None] = {}
    if cache.is_file():
        lines = cache.read_text(encoding="utf-8").splitlines()
        if lines and json.loads(lines[0]).get("date") == today.isoformat():
            for line in lines[1:]:
                counts.update(json.loads(line))
    if not counts:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"date": today.isoformat()}) + "\n", encoding="utf-8")

    def save(batch: Mapping[str, int | None]) -> None:
        with cache.open("a", encoding="utf-8") as out:
            out.write(json.dumps(dict(batch)) + "\n")

    missing = [arxiv_id for arxiv_id in dict.fromkeys(arxiv_ids) if arxiv_id not in counts]
    if missing:
        counts.update(
            fetch_citation_counts(clients.citations, missing, key=clients.citations_key, on_batch=save)
        )
    return counts


def _with_affiliations(papers: list[Paper], client: HttpClient) -> list[Paper]:
    """Fill the affiliations of papers that have none yet, from OpenAlex."""
    pending = {paper.arxiv_id: len(paper.authors) for paper in papers if paper.affiliations is None}
    if not pending:
        return papers
    found = fetch_affiliations(client, pending)
    return [
        replace(
            paper,
            affiliations=found[paper.arxiv_id].affiliations,
            author_affiliations=found[paper.arxiv_id].author_affiliations,
            # OpenAlex's institutions are registry entries: they are their own institutions.
            institutions=found[paper.arxiv_id].affiliations,
        )
        if paper.arxiv_id in found
        else paper
        for paper in papers
    ]


def _subject_names(papers: Iterable[Paper]) -> dict[str, str]:
    """Full subject names by code, as the listings write them ("Robotics (cs.RO)")."""
    names: dict[str, str] = {}
    for paper in papers:
        for subject in paper.subjects:
            if match := _SUBJECT_CODE_RE.search(subject):
                names.setdefault(match.group(1), subject)
    return names
