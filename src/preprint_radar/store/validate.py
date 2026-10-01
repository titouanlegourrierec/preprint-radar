"""Check the data store against its contract, before it is committed and deployed.

Structural rules are errors: a file that does not load, a record the web app would
misread, an index that disagrees with the files, a contact detail in an affiliation.
Heuristic rules are warnings: what the extraction heuristics should have avoided, in day
files (an affiliation that only names authors, the last author alone holding every
affiliation, a paper ``reclean`` would still change). Nothing is fetched or written.
"""

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from preprint_radar.exceptions import StoreError
from preprint_radar.models import Paper
from preprint_radar.sources.arxiv_html import names_only_authors
from preprint_radar.store.paper_store import (
    ARCHIVE_DIRNAME,
    CITATIONS_FILENAME,
    INDEX_FILENAME,
    SCHEMA_VERSION,
    PaperStore,
)
from preprint_radar.store.reclean import reclean_paper

if TYPE_CHECKING:
    from datetime import date

# Contact details the contract keeps out of affiliations. "@" alone is not one: OpenAlex
# names institutions like "IIT@MIT".
_CONTACT_RE = re.compile(
    r"[\w.+-]+@[\w-]+\.[\w.-]+|https?://|www\.|[\[(]\s*at\s*[\])]|\{\s*[a-z0-9._+-]+\s*[,;|]",
    re.IGNORECASE,
)


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
    """Check every file of the store: day files, archive years, citations and the index.

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
    """Check one category's files; return its day and year counts, as the index lists them."""
    directory = store.root / category
    stored: set[str] = set()
    days: list[dict[str, Any]] = []
    first_day: dict[str, date] = {}
    for day in store.days(category):
        path = directory / f"{day.isoformat()}.json"
        papers, records = _load(path, store, report, category=category, key="date", value=day.isoformat())
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
            report.findings.extend(Finding(Level.WARNING, where, message) for message in _heuristics(paper))
        stored.update(paper.arxiv_id for paper in papers)

    years: list[dict[str, Any]] = []
    archived: set[str] = set()
    for year in store.archive_years(category):
        path = directory / ARCHIVE_DIRNAME / f"{year}.json"
        papers, records = _load(path, store, report, category=category, key="year", value=year)
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
            _check_contacts(paper, where, report)
    stored |= archived

    _validate_citations(store, category, stored, report)
    return {"days": days, "years": years}


def _load(
    path: Path, store: PaperStore, report: ValidationReport, *, category: str, key: str, value: object
) -> tuple[list[Paper], int]:
    """The papers of a day or archive file that load, and its number of records.

    The broken rules are added to ``report``.
    """
    report.files += 1
    where = _where(path, store)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.findings.append(Finding(Level.ERROR, where, f"not valid JSON: {exc}"))
        return [], 0
    if not isinstance(payload, dict) or not isinstance(payload.get("papers"), list):
        report.findings.append(Finding(Level.ERROR, where, "no 'papers' list"))
        return [], 0
    expected = {"schema_version": SCHEMA_VERSION, "category": category, key: value}
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
    return papers, len(payload["papers"])


def _check_contacts(paper: Paper, where: str, report: ValidationReport) -> None:
    for affiliation in paper.affiliations or ():
        if _CONTACT_RE.search(affiliation):
            message = f"{paper.arxiv_id}: contact details in affiliation {affiliation!r}"
            report.findings.append(Finding(Level.ERROR, where, message))


def _heuristics(paper: Paper) -> Iterator[str]:
    """What the extraction heuristics should have avoided in a day-file paper."""
    affiliations = paper.affiliations or ()
    institutions = paper.institutions or (None,) * len(affiliations)
    names = [
        affiliation
        for affiliation, institution in zip(affiliations, institutions, strict=True)
        if institution is None and names_only_authors(affiliation, paper.authors)
    ]
    for affiliation in names:
        yield f"{paper.arxiv_id}: affiliation {affiliation!r} only names authors"
    mapping = paper.author_affiliations
    last_holds_all = (
        mapping is not None
        and len(mapping) > 1
        and all(entry is None for entry in mapping[:-1])
        and set(mapping[-1] or ()) == set(range(len(affiliations)))
    )
    if last_holds_all:
        yield f"{paper.arxiv_id}: only the last author is placed, at every affiliation"
    if not names and not last_holds_all and reclean_paper(paper) != paper:
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
    if index.get("categories") != days:
        report.findings.append(Finding(Level.ERROR, where, "days or counts differ from the day files"))
    if index.get("archives", {}) != years:
        report.findings.append(Finding(Level.ERROR, where, "years or counts differ from the archive files"))


def _where(path: Path, store: PaperStore) -> str:
    """The path as the report prints it: relative to the store's parent (``data/...``)."""
    return path.relative_to(store.root.parent).as_posix()
