"""Check the data store against its contract, before it is committed and deployed.

Structural rules are errors: a file that does not load, a record the web app would
misread, an index that disagrees with the files, a contact detail in an affiliation.
Heuristic rules are warnings: what the extraction heuristics should have avoided, in day
files (an affiliation that only names authors, the last author alone holding every
affiliation, a paper ``reclean`` would still change), and an acronym named otherwise than
the registry names its institution. Nothing is fetched or written.
"""

import json
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

from preprint_radar.exceptions import StoreError
from preprint_radar.institutions import ACRONYMS
from preprint_radar.models import Paper
from preprint_radar.sources.arxiv_html import has_contact
from preprint_radar.store.paper_store import (
    ARCHIVE_DIRNAME,
    CITATIONS_FILENAME,
    CODE_FILENAME,
    COUNTRIES_FILENAME,
    GAINS_FILENAME,
    INDEX_FILENAME,
    SCHEMA_VERSION,
    SCHOLAR_FILENAME,
    TOP_RECENT_FILENAME,
    PaperStore,
)
from preprint_radar.store.quality import last_holds_all, names_only
from preprint_radar.store.reclean import reclean_paper


class Level(StrEnum):
    """How serious a finding is."""

    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True, slots=True)
class Finding:
    """One rule broken by one file or paper.

    Attributes:
        level: ``ERROR`` for a structural rule, ``WARNING`` for a heuristic one.
        path: The file, relative to the store's parent directory.
        message: What is wrong, starting with the paper's identifier when it is about one.
    """

    level: Level
    path: str
    message: str

    def __str__(self) -> str:
        """The finding as one log line."""
        return f"{self.level} {self.path}: {self.message}"


@dataclass(slots=True)
class ValidationReport:
    """Everything :func:`validate_store` found.

    Attributes:
        files: Files checked.
        papers: Paper records checked.
        findings: Broken rules, in the order found.
    """

    files: int = 0
    papers: int = 0
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        """The findings that break a structural rule."""
        return [finding for finding in self.findings if finding.level is Level.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        """The findings that break a heuristic rule."""
        return [finding for finding in self.findings if finding.level is Level.WARNING]

    def summary(self) -> str:
        """One line: what was checked, and how many errors and warnings."""
        return (
            f"{self.papers:,} papers in {self.files} files: "
            f"{len(self.errors)} errors, {len(self.warnings)} warnings"
        )


def validate_store(store: PaperStore) -> ValidationReport:
    """Check every file of the store: days, archive years, recent papers, citations and the index.

    Args:
        store: The data store.

    Returns:
        The findings, empty when the store follows the contract.
    """
    report = ValidationReport()
    counts: dict[str, dict[str, Any]] = {}
    for category in store.categories():
        counts[category] = _validate_category(store, category, report)
    _validate_index(store, counts, report)
    return report


def _validate_category(store: PaperStore, category: str, report: ValidationReport) -> dict[str, Any]:
    """Check one category's files; return its days, years and recent papers, as the index lists them."""
    directory = store.root / category
    stored: set[str] = set()
    authors: dict[str, int] = {}
    # Each institution named, and whether a registry named it with its id once.
    named: dict[str, bool] = {}
    days: list[dict[str, Any]] = []
    first_day: dict[str, date] = {}
    for day in store.days(category):
        path = directory / f"{day.isoformat()}.json"
        papers, records, _ = _load(path, store, report, category=category, fields={"date": day.isoformat()})
        days.append({"date": day.isoformat(), "count": records})
        for paper in papers:
            where = _where(path, store)
            if paper.announced != day:
                report.findings.append(
                    Finding(Level.ERROR, where, f"{paper.arxiv_id}: announced {paper.announced}")
                )
            if paper.arxiv_id in first_day:
                message = f"{paper.arxiv_id}: stored on {first_day[paper.arxiv_id]} too"
                report.findings.append(Finding(Level.ERROR, where, message))
            first_day.setdefault(paper.arxiv_id, day)
            _check_contacts(paper, where, report)
            _note_institutions(paper, named)
            report.findings.extend(Finding(Level.WARNING, where, message) for message in _heuristics(paper))
        stored.update(paper.arxiv_id for paper in papers)
        authors.update((paper.arxiv_id, len(paper.authors)) for paper in papers)

    years: list[dict[str, Any]] = []
    archived: set[str] = set()
    for year in store.archive_years(category):
        path = directory / ARCHIVE_DIRNAME / f"{year}.json"
        papers, records, _ = _load(path, store, report, category=category, fields={"year": year})
        years.append({"year": year, "count": records})
        for paper in papers:
            where = _where(path, store)
            if paper.announced.year != year:
                report.findings.append(
                    Finding(Level.ERROR, where, f"{paper.arxiv_id}: announced {paper.announced}")
                )
            if paper.arxiv_id in archived:
                report.findings.append(Finding(Level.ERROR, where, f"{paper.arxiv_id}: archived twice"))
            archived.add(paper.arxiv_id)
            authors.setdefault(paper.arxiv_id, len(paper.authors))
            _check_contacts(paper, where, report)
            _note_institutions(paper, named)
    stored |= archived
    top_recent, recent = _validate_top_recent(store, category, archived, report)
    stored.update(paper.arxiv_id for paper in recent)
    for paper in recent:
        authors.setdefault(paper.arxiv_id, len(paper.authors))
        _note_institutions(paper, named)

    _validate_acronyms(_where(directory, store), named, report)
    _validate_citations(store, category, stored, report)
    _validate_gains(store, category, stored, report)
    _validate_scholar(store, category, authors, report)
    _validate_code(store, category, stored, report)
    _validate_countries(store, category, report)
    return {"days": days, "years": years, "top_recent": top_recent}


def _validate_top_recent(
    store: PaperStore, category: str, archived: set[str], report: ValidationReport
) -> tuple[dict[str, Any] | None, list[Paper]]:
    """``top-recent.json``: papers first seen since its ``since`` day, each once, none archived.

    Returns its entry of the index (``None`` without the file) and its papers that load.
    """
    path = store.root / category / TOP_RECENT_FILENAME
    if not path.is_file():
        return None, []
    where = _where(path, store)
    papers, records, payload = _load(path, store, report, category=category)
    try:
        since = date.fromisoformat(payload["since"])
    except (KeyError, TypeError, ValueError):
        report.findings.append(Finding(Level.ERROR, where, f"'since' is {payload.get('since')!r}, not a day"))
        return {"since": payload.get("since"), "count": records}, papers
    listed: set[str] = set()
    for paper in papers:
        if paper.announced < since:
            report.findings.append(
                Finding(Level.ERROR, where, f"{paper.arxiv_id}: announced {paper.announced}")
            )
        if paper.arxiv_id in listed:
            report.findings.append(Finding(Level.ERROR, where, f"{paper.arxiv_id}: listed twice"))
        if paper.arxiv_id in archived:
            report.findings.append(Finding(Level.ERROR, where, f"{paper.arxiv_id}: archived too"))
        listed.add(paper.arxiv_id)
        _check_contacts(paper, where, report)
    return {"since": since.isoformat(), "count": records}, papers


def _load(
    path: Path,
    store: PaperStore,
    report: ValidationReport,
    *,
    category: str,
    fields: Mapping[str, object] | None = None,
) -> tuple[list[Paper], int, dict[str, Any]]:
    """The papers of a file of papers that load, its number of records, and its JSON object.

    The broken rules are added to ``report``: among them, a field other than ``fields`` says.
    """
    report.files += 1
    where = _where(path, store)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.findings.append(Finding(Level.ERROR, where, f"not valid JSON: {exc}"))
        return [], 0, {}
    if not isinstance(payload, dict) or not isinstance(payload.get("papers"), list):
        report.findings.append(Finding(Level.ERROR, where, "no 'papers' list"))
        return [], 0, payload if isinstance(payload, dict) else {}
    expected = {"schema_version": SCHEMA_VERSION, "category": category, **(fields or {})}
    for name, wanted in expected.items():
        if payload.get(name) != wanted:
            message = f"{name!r} is {payload.get(name)!r}, expected {wanted!r}"
            report.findings.append(Finding(Level.ERROR, where, message))
    papers: list[Paper] = []
    for record in payload["papers"]:
        report.papers += 1
        try:
            papers.append(Paper.from_record(record))
        except StoreError as exc:
            report.findings.append(Finding(Level.ERROR, where, str(exc)))
    return papers, len(payload["papers"]), payload


def _check_contacts(paper: Paper, where: str, report: ValidationReport) -> None:
    for affiliation in paper.affiliations or ():
        if has_contact(affiliation):
            message = f"{paper.arxiv_id}: contact details in affiliation {affiliation!r}"
            report.findings.append(Finding(Level.ERROR, where, message))


def _note_institutions(paper: Paper, named: dict[str, bool]) -> None:
    """Add the institutions ``paper`` names to ``named``, each true once named with its id."""
    ids = paper.institution_ids or ()
    for at, name in enumerate(paper.institutions or ()):
        if name is not None:
            named[name] = named.get(name, False) or (at < len(ids) and ids[at] is not None)


def _validate_acronyms(where: str, named: Mapping[str, bool], report: ValidationReport) -> None:
    """An acronym's institution the store names, but never with a registry's id (TEST-9).

    ``ACRONYMS`` gives an acronym written alone the name ROR gives its institution, so that
    both share a node; spelled otherwise, it makes a node of its own: "University of
    California, San Diego" held the 7 papers that wrote "UCSD" alone, apart from the 246
    of ROR's "University of California San Diego".
    """
    acronyms: defaultdict[str, list[str]] = defaultdict(list)
    for acronym, name in ACRONYMS.items():
        acronyms[name].append(acronym)
    for name, written in acronyms.items():
        if named.get(name) is False:
            plural = len(written) > 1
            message = (
                f"{'acronyms' if plural else 'acronym'} {' and '.join(map(repr, written))} "
                f"{'name' if plural else 'names'} {name!r}, which no institution with an id is called"
            )
            report.findings.append(Finding(Level.WARNING, where, message))


def _heuristics(paper: Paper) -> Iterator[str]:
    """What the extraction heuristics should have avoided in a day-file paper.

    The strongest signs of :mod:`~preprint_radar.store.quality`, which ``stats
    --affiliations`` counts in full. OpenAlex's affiliations (a paper without an HTML page,
    AFF-27) were not extracted: none.
    """
    if paper.affiliations_from_openalex:
        return
    names = names_only(paper)
    for affiliation in names:
        yield f"{paper.arxiv_id}: affiliation {affiliation!r} only names authors"
    shared = last_holds_all(paper)
    if shared:
        yield f"{paper.arxiv_id}: only the last author is placed, at every affiliation"
    if not names and not shared and reclean_paper(paper) != paper:
        yield f"{paper.arxiv_id}: `reclean` would change its affiliations"


def _validate_citations(store: PaperStore, category: str, stored: set[str], report: ValidationReport) -> None:
    path = store.root / category / CITATIONS_FILENAME
    if not path.is_file():
        return
    report.files += 1
    where = _where(path, store)
    try:
        citations = store.load_citation_counts(category)
    except StoreError as exc:
        report.findings.append(Finding(Level.ERROR, where, str(exc)))
        return
    unknown = sorted(set(citations.counts) - stored) if citations else []
    if unknown:
        examples = ", ".join(unknown[:5])
        message = f"{len(unknown)} counts of papers that are not stored, e.g. {examples}"
        report.findings.append(Finding(Level.ERROR, where, message))


def _validate_gains(store: PaperStore, category: str, stored: set[str], report: ValidationReport) -> None:
    """``citation-gains.json`` must load; gains of papers no longer stored only warn.

    It is written with the weekly counts, from which the pruned papers left, and the next
    refresh drops them.
    """
    path = store.root / category / GAINS_FILENAME
    if not path.is_file():
        return
    report.files += 1
    where = _where(path, store)
    try:
        gains = store.load_citation_gains(category)
    except StoreError as exc:
        report.findings.append(Finding(Level.ERROR, where, str(exc)))
        return
    unknown = sorted(set(gains.gains) - stored) if gains else []
    if unknown:
        message = f"{len(unknown)} gains of papers that are not stored, e.g. {', '.join(unknown[:5])}"
        report.findings.append(Finding(Level.WARNING, where, message))


def _validate_code(store: PaperStore, category: str, stored: set[str], report: ValidationReport) -> None:
    """``code.json`` must load; records of papers no longer stored only warn.

    It is written weekly, with the counts, from which the pruned papers left, and the next
    refresh drops them.
    """
    path = store.root / category / CODE_FILENAME
    if not path.is_file():
        return
    report.files += 1
    where = _where(path, store)
    try:
        code = store.load_code(category)
    except StoreError as exc:
        report.findings.append(Finding(Level.ERROR, where, str(exc)))
        return
    unknown = sorted(set(code.papers) - stored) if code else []
    if unknown:
        message = f"{len(unknown)} records of papers that are not stored, e.g. {', '.join(unknown[:5])}"
        report.findings.append(Finding(Level.WARNING, where, message))


def _validate_countries(store: PaperStore, category: str, report: ValidationReport) -> None:
    """``countries.json`` must load (UX-40): the site's map reads it as it is."""
    path = store.root / category / COUNTRIES_FILENAME
    if not path.is_file():
        return
    report.files += 1
    try:
        store.load_countries(category)
    except StoreError as exc:
        report.findings.append(Finding(Level.ERROR, _where(path, store), str(exc)))


def _validate_scholar(
    store: PaperStore, category: str, authors: dict[str, int], report: ValidationReport
) -> None:
    """``scholar.json`` must load; stale records only warn.

    A record of a paper no longer stored, or whose author ids no longer fit its author list
    (a new version), is dropped by the next weekly run.
    """
    path = store.root / category / SCHOLAR_FILENAME
    if not path.is_file():
        return
    report.files += 1
    where = _where(path, store)
    try:
        scholar = store.load_scholar(category)
    except StoreError as exc:
        report.findings.append(Finding(Level.ERROR, where, str(exc)))
        return
    records = scholar.papers if scholar else {}
    unknown = sorted(set(records) - set(authors))
    if unknown:
        message = f"{len(unknown)} records of papers that are not stored, e.g. {', '.join(unknown[:5])}"
        report.findings.append(Finding(Level.WARNING, where, message))
    misfits = sorted(
        arxiv_id
        for arxiv_id, record in records.items()
        if record.author_ids is not None
        and arxiv_id in authors
        and len(record.author_ids) != authors[arxiv_id]
    )
    if misfits:
        message = f"{len(misfits)} author id lists that do not fit the authors, e.g. {', '.join(misfits[:5])}"
        report.findings.append(Finding(Level.WARNING, where, message))


def _validate_index(store: PaperStore, counts: dict[str, dict[str, Any]], report: ValidationReport) -> None:
    path = store.root / INDEX_FILENAME
    where = _where(path, store)
    report.files += 1
    try:
        index: Any = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        report.findings.append(Finding(Level.ERROR, where, "missing"))
        return
    except json.JSONDecodeError as exc:
        report.findings.append(Finding(Level.ERROR, where, f"not valid JSON: {exc}"))
        return
    if not isinstance(index, dict):
        report.findings.append(Finding(Level.ERROR, where, "not a JSON object"))
        return
    if index.get("schema_version") != SCHEMA_VERSION:
        message = f"'schema_version' is {index.get('schema_version')!r}, expected {SCHEMA_VERSION}"
        report.findings.append(Finding(Level.ERROR, where, message))
    days = {category: found["days"] for category, found in counts.items()}
    years = {category: found["years"] for category, found in counts.items() if found["years"]}
    recent = {category: found["top_recent"] for category, found in counts.items() if found["top_recent"]}
    if index.get("categories") != days:
        report.findings.append(Finding(Level.ERROR, where, "days or counts differ from the day files"))
    if index.get("archives", {}) != years:
        report.findings.append(Finding(Level.ERROR, where, "years or counts differ from the archive files"))
    if index.get("top_recent", {}) != recent:
        message = "the papers of the last 12 months differ from top-recent.json"
        report.findings.append(Finding(Level.ERROR, where, message))


def _where(path: Path, store: PaperStore) -> str:
    """The path as the report prints it: relative to the store's parent (``data/...``)."""
    return path.relative_to(store.root.parent).as_posix()
