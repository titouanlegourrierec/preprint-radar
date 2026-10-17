"""Weekly archive update: keep the most cited older papers, within a size budget.

The store keeps every paper of the last 12 months in its day files, and an archive of
older papers chosen by citations per year of age (:mod:`preprint_radar.archive.selection`). Each
week, :func:`update_archive`:

1. refreshes the category's catalog from OAI-PMH (:mod:`preprint_radar.archive.catalog`);
2. fetches the citation counts of every paper since 2010 (:mod:`preprint_radar.sources.semantic_scholar`);
3. selects the archive among the papers first seen over 12 months ago, those of the day
   files included, and builds the papers that enter it: from their day file when they have
   one (enrichment kept), or the record they had among the last 12 months, else from the
   catalog, with affiliations from OpenAlex (:mod:`preprint_radar.sources.openalex`);
4. chooses the most cited papers of the last 12 months by citations per month of age
   (PROD-11): those of the day files as these hold them, the others built from the catalog
   or kept from last week, with affiliations from OpenAlex;
5. writes the archive, those papers, the citation counts of the stored papers and the
   index, and, when asked to, deletes the day files older than 12 months. Pruning only
   decides what is deleted: day-file papers compete for the archive whether or not it is on.

Every stored paper also takes the comments and journal reference of its latest version
from the catalog, and the venue they give (META-2): records otherwise freeze once they
leave the listing. The papers of the archive and of the last 12 months that no day file
holds have their authors and subjects cleaned as the catalog's are (AFF-21, META-8), those
written before it was. Withdrawn papers never enter the archive, and leave it (decision 18).

When Semantic Scholar misses too many counts (below ``MIN_COVERAGE``), the archive, the
papers of the last 12 months and the day files stay as they are, but for the comments of
their papers, and the counts fetched are added to the stored ones.
"""

import json
import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import NamedTuple

from preprint_radar.archive.catalog import Catalog
from preprint_radar.archive.selection import (
    Candidate,
    Selection,
    is_recent,
    recent_since,
    select_archive,
    select_top_recent,
)
from preprint_radar.archive.subjects import SUBJECT_ALIASES, subject_name, subject_names
from preprint_radar.config import (
    ARCHIVE_SINCE,
    CITATIONS_CACHE_DAYS,
    MIN_COVERAGE,
    RECENT_DAYS,
)
from preprint_radar.console import progress
from preprint_radar.http import HttpClient
from preprint_radar.latex import plain_text
from preprint_radar.models import Paper
from preprint_radar.openalex_affiliations import with_openalex_affiliations
from preprint_radar.sources.arxiv_oai import CatalogEntry, author_names
from preprint_radar.sources.semantic_scholar import S2_SOURCE, fetch_citation_counts
from preprint_radar.store.paper_store import PaperStore, TopRecent
from preprint_radar.venue import extract_venue
from preprint_radar.withdrawal import is_withdrawn

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
        carried: Archived papers, and last week's most cited of the last 12 months, ranked on
            last week's count, missing this week.
        threshold: Citations per year of the last paper within the budget.
        archived: Papers in the archive after the update.
        entered: Papers that entered it.
        left: Papers that left it.
        pruned_days: Day files deleted (older than 12 months).
        written: Whether anything was written (not a dry run).
        refreshed: Stored papers whose comments or journal reference the catalog changed.
        top_recent: Most cited papers of the last 12 months kept (PROD-11).
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
    top_recent: int = 0


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
    stored_days, changed_in_days, in_days, archived, changed_in_archive, previous_top = _stored(
        store, category, entries
    )
    previous_recent = {paper.arxiv_id: paper for paper in (previous_top.papers if previous_top else ())}
    # A stored paper was first seen on the earlier of its day file and the catalog's date,
    # which can be weeks later (2609.00036: announced 2026-09-02, catalog 2026-09-14).
    first_seen = {
        arxiv_id: min(entry.first_seen, paper.announced)
        if (paper := in_days.get(arxiv_id))
        else entry.first_seen
        for arxiv_id, entry in entries.items()
    }

    wanted = [*entries, *in_days, *archived, *previous_recent]
    counts = _citation_counts(catalog, clients, wanted, today)
    coverage = sum(arxiv_id in counts for arxiv_id in entries) / max(1, len(entries))
    logger.info(
        "%s: citation counts for %.1f%% of %s candidates", category, 100 * coverage, f"{len(entries):,}"
    )
    gated = coverage < MIN_COVERAGE
    carried: dict[str, int] = {}
    if gated:
        logger.warning(
            "Only %.1f%% of citation counts: the archive and day files stay as they are", 100 * coverage
        )
        stale_days = []
        selection = Selection(keep=frozenset(archived), entered=frozenset(), left=frozenset(), threshold=0.0)
        top_recent = frozenset(previous_recent)
    else:
        stale_days = [day for day in stored_days if (today - day).days >= RECENT_DAYS] if prune else []
        # An archived paper, or one of last week's most cited of the last 12 months, that
        # Semantic Scholar misses this week (a refused last batch, a flapping null) is ranked
        # on last week's count rather than leave.
        previous = store.load_citations(category)
        carried = {
            arxiv_id: previous[arxiv_id]
            for arxiv_id in (*archived, *previous_recent)
            if counts.get(arxiv_id) is None and arxiv_id in previous
        }
        counts = {**counts, **carried}
        # Withdrawn papers are not Highly cited, however cited (decision 18); archived ones leave.
        withdrawn = {
            arxiv_id
            for arxiv_id, entry in entries.items()
            if is_withdrawn(entry.comments)
            or ((paper := in_days.get(arxiv_id) or archived.get(arxiv_id)) is not None and paper.withdrawn)
        }
        if withdrawn:
            logger.info("%s: %d withdrawn papers are left out", category, len(withdrawn))
        selection = select_archive(
            (
                Candidate(arxiv_id, first_seen[arxiv_id], counts.get(arxiv_id))
                for arxiv_id in entries
                if arxiv_id not in withdrawn
            ),
            set(archived),
            budget=budget,
            today=today,
        )
        top_recent = select_top_recent(
            (
                Candidate(arxiv_id, first_seen[arxiv_id], counts.get(arxiv_id))
                for arxiv_id in entries
                if arxiv_id not in withdrawn and is_recent(first_seen[arxiv_id], today)
            ),
            today=today,
        )
    subjects = _subject_names(in_days.values())
    # A paper that leaves the last 12 months for the archive keeps the record it had there,
    # with the affiliations its published version or its page gave (AFF-20, AFF-28).
    new_papers = [
        _from_day_file(stored, first_seen[arxiv_id])
        if (stored := in_days.get(arxiv_id) or previous_recent.get(arxiv_id)) is not None
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
    logger.info(
        "%s: %d most cited papers of the last 12 months, %d of them new",
        category,
        len(top_recent),
        len(top_recent - set(previous_recent)),
    )
    # Those of the day files are their records there, which the daily update enriches,
    # filed on their day as the links to them; the others are kept from last week, else
    # built from the catalog.
    recent = {
        arxiv_id: in_days.get(arxiv_id)
        or previous_recent.get(arxiv_id)
        or paper_from_catalog(entries[arxiv_id], category, subjects)
        for arxiv_id in sorted(top_recent)
    }

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
        top_recent=len(top_recent),
    )
    if dry_run:
        return report

    # Every lookup comes before the first write: a run stopped between two writes would leave
    # files that disagree, which validate refuses.
    # Entering papers, archived ones without OpenAlex's ids, and young ones it knew no
    # affiliations for (see needs_openalex).
    archive = with_openalex_affiliations(
        [*(paper for arxiv_id, paper in archived.items() if arxiv_id in selection.keep), *new_papers],
        clients.openalex,
        today,
    )
    recent_papers = [
        *(paper for arxiv_id, paper in recent.items() if arxiv_id in in_days),
        *with_openalex_affiliations(
            [paper for arxiv_id, paper in recent.items() if arxiv_id not in in_days], clients.openalex, today
        ),
    ]
    if changed_in_days:
        store.save(category, changed_in_days)
    # Below the coverage, last week's papers stay, with the comments of their latest version.
    # Written before the archive: last week's may hold papers entering it, this week's none
    # it held.
    since = (previous_top.since if previous_top else None) if gated else recent_since(today)
    if since is not None:
        store.write_top_recent(category, recent_papers, since=since)
    store.write_archive(category, archive)
    store.remove_days(category, stale_days)
    on_disk = {
        paper.arxiv_id for day, papers in stored_days.items() if day not in stale_days for paper in papers
    }
    stored_counts = {
        arxiv_id: count
        for arxiv_id in on_disk | selection.keep | top_recent
        if (count := counts.get(arxiv_id)) is not None
    }
    if gated:
        # What was fetched is added; the other counts and the date of the last refresh stay.
        store.merge_citations(category, stored_counts, source=S2_SOURCE)
    else:
        store.write_citations(category, stored_counts, source=S2_SOURCE)
    store.write_index()
    return report


class _Stored(NamedTuple):
    """The stored papers of a category, with the comments of their latest version (:func:`refreshed`)."""

    #: Each day's papers, as stored.
    days: dict[date, list[Paper]]
    #: Papers of the day files the catalog changed.
    changed_in_days: list[Paper]
    #: The papers of the day files, by identifier.
    in_days: dict[str, Paper]
    #: The archived papers, by identifier.
    archived: dict[str, Paper]
    #: Number of archived papers the catalog changed.
    changed_in_archive: int
    #: Last week's most cited papers of the last 12 months, if any.
    top_recent: TopRecent | None


def _stored(store: PaperStore, category: str, entries: Mapping[str, CatalogEntry]) -> _Stored:
    """The stored papers of ``category``, refreshed from the catalog's ``entries``."""
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
    subjects = _subject_names(in_days.values())
    stored_archive = list(store.iter_archive(category))
    archived = {
        paper.arxiv_id: cleaned(refreshed(paper, entries.get(paper.arxiv_id)), subjects)
        for paper in stored_archive
    }
    top_recent = store.load_top_recent(category)
    if top_recent is not None:
        # Those of the day files are their records there, which keep the listing's names.
        top_recent = replace(
            top_recent,
            papers=[
                refreshed(paper, entries.get(paper.arxiv_id))
                if paper.arxiv_id in in_days
                else cleaned(refreshed(paper, entries.get(paper.arxiv_id)), subjects)
                for paper in top_recent.papers
            ],
        )
    return _Stored(
        days=stored_days,
        changed_in_days=changed_in_days,
        in_days=in_days,
        archived=archived,
        changed_in_archive=sum(archived[paper.arxiv_id] is not paper for paper in stored_archive),
        top_recent=top_recent,
    )


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
        paper,
        comments=comments,
        journal_ref=journal_ref,
        venue=extract_venue(comments, journal_ref),
        withdrawn=is_withdrawn(comments),
    )


def cleaned(paper: Paper, subjects: Mapping[str, str]) -> Paper:
    """A paper built from the catalog, with its authors and subjects as the catalog's are now.

    The archive's papers written before the catalog was cleaned (AFF-21, META-8) kept what
    the author list added to the names ("Jie Qin1", the author "others") and the codes of
    the subjects neither the days nor the taxonomy named then ("cs.LG"). A name dropped
    takes its place in the author mapping with it. The same paper comes back when nothing
    changes, as for any paper cleaned before.

    Args:
        paper: A stored paper of the archive, or of the last 12 months no day file holds.
        subjects: Full subject names the stored days give, by code.
    """
    kept = [
        (position, names[0]) for position, name in enumerate(paper.authors) if (names := author_names([name]))
    ]
    authors = tuple(name for _, name in kept)
    mapping = paper.author_affiliations
    if mapping is not None and authors != paper.authors:
        mapping = tuple(mapping[position] for position, _ in kept)
    primary = paper.primary_subject
    if primary is not None and not _SUBJECT_CODE_RE.search(primary):
        primary = subject_name(primary, subjects)
    named = tuple(
        dict.fromkeys(
            subject if _SUBJECT_CODE_RE.search(subject) else subject_name(subject, subjects)
            for subject in paper.subjects
        )
    )
    if (authors, primary, named) == (paper.authors, paper.primary_subject, paper.subjects):
        return paper
    return replace(
        paper, authors=authors, author_affiliations=mapping, primary_subject=primary, subjects=named
    )


def _from_day_file(paper: Paper, first_seen: date) -> Paper:
    """A paper entering the archive with its stored record, filed under its first appearance.

    Its record is its day file's, or the one it had among the last 12 months. An old paper
    cross-listed into the category lately is filed under its own year, not under the day of
    the cross-list.
    """
    return paper if paper.announced == first_seen else replace(paper, announced=first_seen)


def paper_from_catalog(entry: CatalogEntry, category: str, subjects: Mapping[str, str]) -> Paper:
    """A paper of the archive, built from its catalog entry (affiliations not looked up yet).

    Args:
        entry: Catalog entry.
        category: Category of the archive; another primary category makes a cross-list.
        subjects: Full subject names the stored days give, by code ("cs.LG" -> "Machine
            Learning (cs.LG)"); arXiv's taxonomy names the others, an alias as its
            canonical code (:mod:`preprint_radar.archive.subjects`), and a code neither
            knows is kept as it is.
    """
    # Under its canonical code, as its name: "cs.SY" is a cross-list from "eess.SY".
    primary = SUBJECT_ALIASES.get(entry.categories[0], entry.categories[0]) if entry.categories else category
    return Paper(
        arxiv_id=entry.arxiv_id,
        announced=entry.first_seen,
        title=entry.title,
        authors=entry.authors,
        primary_subject=subject_name(primary, subjects),
        subjects=subject_names(entry.categories, subjects),
        comments=entry.comments,
        journal_ref=entry.journal_ref,
        venue=extract_venue(entry.comments, entry.journal_ref),
        withdrawn=is_withdrawn(entry.comments),
        cross_list_from=None if primary == category else primary,
        abstract=plain_text(entry.abstract) if entry.abstract else None,
    )


def format_archive_report(report: ArchiveReport) -> str:
    """Render an :class:`ArchiveReport` as a one-line human-readable summary."""
    return (
        f"{report.category}: {report.archived:,} archived papers "
        f"({report.entered:,} in, {report.left:,} out), "
        f"threshold {report.threshold:.1f} citations a year, "
        f"{report.top_recent:,} most cited of the last 12 months, citation counts for "
        f"{100 * report.coverage:.1f}% of {report.candidates:,} papers"
        + (f" ({report.carried:,} papers on last week's count)" if report.carried else "")
        + f", {report.refreshed:,} papers' comments refreshed, {report.pruned_days:,} day files pruned"
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
        with progress("Citation counts", len(missing)) as advance:
            counts.update(
                fetch_citation_counts(
                    clients.citations, missing, key=clients.citations_key, on_batch=save, progress=advance
                )
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
    logger.info("Reusing %s citation counts saved on %s", f"{len(counts):,}", started.isoformat())
    return started, counts


def _subject_names(papers: Iterable[Paper]) -> dict[str, str]:
    """Full subject names by code, as the listings write them ("Robotics (cs.RO)")."""
    names: dict[str, str] = {}
    for paper in papers:
        for subject in paper.subjects:
            if match := _SUBJECT_CODE_RE.search(subject):
                names.setdefault(match.group(1), subject)
    return names
