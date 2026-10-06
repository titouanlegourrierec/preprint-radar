"""Weekly archive update: keep the most cited older papers, within a size budget.

The store keeps every paper of the last 12 months in its day files, and an archive of
older papers chosen by citations per year of age (:mod:`preprint_radar.archive.selection`). Each
week, :func:`update_archive`:

1. refreshes the category's catalog from OAI-PMH (:mod:`preprint_radar.archive.catalog`);
2. fetches the citation counts of every paper since 2010 (:mod:`preprint_radar.sources.semantic_scholar`);
3. selects the archive among the papers first seen over 12 months ago, those of the day
   files included, and builds the papers that enter it: from their day file when they have
   one (enrichment kept), else from the catalog, with affiliations from OpenAlex
   (:mod:`preprint_radar.sources.openalex`);
4. writes the archive, the citation counts of the stored papers and the index, and, when
   asked to, deletes the day files older than 12 months. Pruning only decides what is
   deleted: day-file papers compete for the archive whether or not it is on.

Every stored paper also takes the comments and journal reference of its latest version
from the catalog, and the venue they give (META-2): records otherwise freeze once they
leave the listing.

When Semantic Scholar misses too many counts (below ``MIN_COVERAGE``), the archive and the
day files stay as they are, but for the comments of their papers, and the counts fetched are
added to the stored ones.
"""

import json
import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from preprint_radar.archive.catalog import Catalog
from preprint_radar.archive.selection import Candidate, Selection, select_archive
from preprint_radar.config import ARCHIVE_SINCE, CITATIONS_CACHE_DAYS, MIN_COVERAGE, RECENT_DAYS
from preprint_radar.http import HttpClient
from preprint_radar.models import Paper, Provenance
from preprint_radar.sources.arxiv_oai import CatalogEntry
from preprint_radar.sources.openalex import fetch_affiliations
from preprint_radar.sources.semantic_scholar import S2_SOURCE, fetch_citation_counts
from preprint_radar.store.paper_store import PaperStore
from preprint_radar.venue import extract_venue

logger = logging.getLogger(__name__)

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
        carried: Archived papers ranked on last week's count, missing this week.
        threshold: Citations per year of the last paper within the budget.
        archived: Papers in the archive after the update.
        entered: Papers that entered it.
        left: Papers that left it.
        pruned_days: Day files deleted (older than 12 months).
        written: Whether anything was written (not a dry run).
        refreshed: Stored papers whose comments or journal reference the catalog changed.
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
    carried: int = 0
    refreshed: int = 0


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
    refreshed_days = {
        day: [refreshed(paper, entries.get(paper.arxiv_id)) for paper in papers]
        for day, papers in stored_days.items()
    }
    changed_in_days = [
        new
        for day, papers in stored_days.items()
        for old, new in zip(papers, refreshed_days[day], strict=True)
        if new is not old
    ]
    in_days = {paper.arxiv_id: paper for papers in refreshed_days.values() for paper in papers}
    stored_archive = list(store.iter_archive(category))
    archived = {paper.arxiv_id: refreshed(paper, entries.get(paper.arxiv_id)) for paper in stored_archive}
    changed_in_archive = sum(archived[paper.arxiv_id] is not paper for paper in stored_archive)
    # A stored paper was first seen on the earlier of its day file and the catalog's date,
    # which can be weeks later (2609.00036: announced 2026-09-02, catalog 2026-09-14).
    first_seen = {
        arxiv_id: min(entry.first_seen, paper.announced)
        if (paper := in_days.get(arxiv_id))
        else entry.first_seen
        for arxiv_id, entry in entries.items()
    }

    wanted = [*entries, *in_days, *archived]
    counts = _citation_counts(catalog, clients, wanted, today)
    coverage = sum(arxiv_id in counts for arxiv_id in entries) / max(1, len(entries))
    logger.info("%s: citation counts for %.1f%% of %d candidates", category, 100 * coverage, len(entries))
    gated = coverage < MIN_COVERAGE
    carried: dict[str, int] = {}
    if gated:
        logger.warning(
            "Only %.1f%% of citation counts: the archive and day files stay as they are", 100 * coverage
        )
        stale_days = []
        selection = Selection(keep=frozenset(archived), entered=frozenset(), left=frozenset(), threshold=0.0)
    else:
        stale_days = [day for day in stored_days if (today - day).days >= RECENT_DAYS] if prune else []
        # An archived paper Semantic Scholar misses this week (a refused last batch, a
        # flapping null) is ranked on last week's count rather than leave.
        previous = store.load_citations(category)
        carried = {
            arxiv_id: previous[arxiv_id]
            for arxiv_id in archived
            if counts.get(arxiv_id) is None and arxiv_id in previous
        }
        counts = {**counts, **carried}
        selection = select_archive(
            (Candidate(arxiv_id, first_seen[arxiv_id], counts.get(arxiv_id)) for arxiv_id in entries),
            set(archived),
            budget=budget,
            today=today,
        )
    subjects = _subject_names(in_days.values())
    new_papers = [
        _from_day_file(in_days[arxiv_id], first_seen[arxiv_id])
        if arxiv_id in in_days
        else paper_from_catalog(entries[arxiv_id], category, subjects)
        for arxiv_id in sorted(selection.entered)
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
        carried=len(carried),
        refreshed=len(changed_in_days) + changed_in_archive,
    )
    if dry_run:
        return report

    if changed_in_days:
        store.save(category, changed_in_days)
    kept = [paper for arxiv_id, paper in archived.items() if arxiv_id in selection.keep]
    # Entering papers, and archived ones OpenAlex did not return last time.
    store.write_archive(category, _with_affiliations([*kept, *new_papers], clients.openalex, today))
    store.remove_days(category, stale_days)
    on_disk = {
        paper.arxiv_id for day, papers in stored_days.items() if day not in stale_days for paper in papers
    }
    stored_counts = {
        arxiv_id: count
        for arxiv_id in on_disk | selection.keep
        if (count := counts.get(arxiv_id)) is not None
    }
    if gated:
        # What was fetched is added; the other counts and the date of the last refresh stay.
        store.merge_citations(category, stored_counts, source=S2_SOURCE)
    else:
        store.write_citations(category, stored_counts, source=S2_SOURCE)
    store.write_index()
    return report


def refreshed(paper: Paper, entry: CatalogEntry | None) -> Paper:
    """The paper with the comments and journal reference of its latest version, and their venue.

    The catalog holds each paper's latest version; a stored record keeps what the listing
    said when it was announced. The catalog never empties a field: a version without
    comments may only be one the harvest has not seen whole. The same paper comes back
    when nothing changed.

    Args:
        paper: A stored paper.
        entry: Its catalog entry, if the catalog has it.
    """
    if entry is None:
        return paper
    comments = entry.comments or paper.comments
    journal_ref = entry.journal_ref or paper.journal_ref
    if (comments, journal_ref) == (paper.comments, paper.journal_ref):
        return paper
    return replace(
        paper, comments=comments, journal_ref=journal_ref, venue=extract_venue(comments, journal_ref)
    )


def _from_day_file(paper: Paper, first_seen: date) -> Paper:
    """A paper entering the archive from its day file, filed under its first appearance.

    An old paper cross-listed into the category lately is filed under its own year, not
    under the day of the cross-list.
    """
    return paper if paper.announced == first_seen else replace(paper, announced=first_seen)


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
        f"{100 * report.coverage:.1f}% of {report.candidates} papers"
        + (f" ({report.carried} archived papers on last week's count)" if report.carried else "")
        + f", {report.refreshed} papers' comments refreshed, {report.pruned_days} day files pruned"
        + ("" if report.written else " (dry run: nothing written)")
    )


def _citation_counts(
    catalog: Catalog, clients: ArchiveClients, arxiv_ids: Iterable[str], today: date
) -> dict[str, int | None]:
    """Citation counts, resuming from those a recent run saved in a cache file."""
    cache = catalog.directory / f"{catalog.category}.citations.jsonl"
    started, counts = _read_citations_cache(cache, today)
    # Rewritten in one piece: a run killed while appending a batch leaves a cut last line.
    cache.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"date": started.isoformat()}), *([json.dumps(counts)] if counts else [])]
    cache.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def save(batch: Mapping[str, int | None]) -> None:
        with cache.open("a", encoding="utf-8") as out:
            out.write(json.dumps(dict(batch)) + "\n")

    missing = [arxiv_id for arxiv_id in dict.fromkeys(arxiv_ids) if arxiv_id not in counts]
    if missing:
        counts.update(
            fetch_citation_counts(clients.citations, missing, key=clients.citations_key, on_batch=save)
        )
    return counts


def _read_citations_cache(cache: Path, today: date) -> tuple[date, dict[str, int | None]]:
    """The day a recent run started its cache, and the counts it saved; else today and none."""
    lines = cache.read_text(encoding="utf-8").splitlines() if cache.is_file() else []
    try:
        started = date.fromisoformat(json.loads(lines[0])["date"])
    except (IndexError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return today, {}
    if not 0 <= (today - started).days < CITATIONS_CACHE_DAYS:
        return today, {}
    counts: dict[str, int | None] = {}
    for line in lines[1:]:
        try:
            counts.update(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("Ignoring a cut line of %s", cache)
    logger.info("Reusing %d citation counts saved on %s", len(counts), started.isoformat())
    return started, counts


def _with_affiliations(papers: list[Paper], client: HttpClient, today: date) -> list[Paper]:
    """Fill the affiliations of papers that have none yet, from OpenAlex.

    Papers whose affiliations came from OpenAlex before ROR ids were kept (their
    institutions are their affiliations, OpenAlex's registry names) are asked for again,
    once, for the ids: their affiliations are replaced by OpenAlex's current ones, unless
    it now gives none.
    """
    pending = {paper.arxiv_id: len(paper.authors) for paper in papers if _needs_openalex(paper)}
    if not pending:
        return papers
    found = fetch_affiliations(client, pending)
    # Said only of what OpenAlex gave: a paper it does not know yet stays unread.
    read = Provenance("openalex", today)
    return [
        replace(
            paper,
            affiliations=found[paper.arxiv_id].affiliations,
            author_affiliations=found[paper.arxiv_id].author_affiliations,
            # OpenAlex's institutions are registry entries: they are their own institutions.
            institutions=found[paper.arxiv_id].affiliations,
            institution_ids=found[paper.arxiv_id].institution_ids or None,
            affiliations_provenance=None if found[paper.arxiv_id].affiliations is None else read,
            institutions_provenance=None if found[paper.arxiv_id].affiliations is None else read,
        )
        if paper.arxiv_id in found and (paper.affiliations is None or found[paper.arxiv_id].affiliations)
        else paper
        for paper in papers
    ]


def _needs_openalex(paper: Paper) -> bool:
    """No affiliations yet, or OpenAlex's without their ROR ids."""
    return paper.affiliations is None or (
        bool(paper.affiliations)
        and paper.institution_ids is None
        and paper.institutions == paper.affiliations
    )


def _subject_names(papers: Iterable[Paper]) -> dict[str, str]:
    """Full subject names by code, as the listings write them ("Robotics (cs.RO)")."""
    names: dict[str, str] = {}
    for paper in papers:
        for subject in paper.subjects:
            if match := _SUBJECT_CODE_RE.search(subject):
                names.setdefault(match.group(1), subject)
    return names
