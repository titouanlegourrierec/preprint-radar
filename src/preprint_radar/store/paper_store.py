"""On-disk store of papers, laid out for static hosting.

Layout::

    <root>/
    ├── index.json                 # categories, days, archive years and paper counts
    └── <category>/
        ├── <YYYY-MM-DD>.json      # papers announced that day in that category
        ├── citations.json         # citation counts of the stored papers
        ├── citation-gains.json    # what each gained between the last two full refreshes
        ├── scholar.json           # their DOI, published venue and author ids
        ├── top-recent.json        # the most cited papers of the last 12 months
        └── archive/
            └── <YYYY>.json        # highly cited older papers, by year of first version

One file per day keeps each update small, and lets the web app load only the days
it needs. The archive holds the papers kept for their citations once they are older than
the days kept in full; it is rewritten as a whole by :meth:`PaperStore.write_archive`, and
the most cited papers of the last 12 months, many of which no day file holds, by
:meth:`PaperStore.write_top_recent` (PROD-11).

Every file carries the ``schema_version`` it was written with, and the store refuses to
read one of another version (DATA-9): an older pipeline would otherwise misread a newer
store, and rewrite its files stamped with its own version.
"""

import json
import logging
import re
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from preprint_radar.config import GAINS_MIN_DAYS
from preprint_radar.exceptions import SchemaVersionError, StoreError
from preprint_radar.models import Paper, ScholarRecord

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
INDEX_FILENAME = "index.json"
CITATIONS_FILENAME = "citations.json"
GAINS_FILENAME = "citation-gains.json"
SCHOLAR_FILENAME = "scholar.json"
TOP_RECENT_FILENAME = "top-recent.json"
ARCHIVE_DIRNAME = "archive"
_DAY_STEM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_YEAR_STEM_RE = re.compile(r"^\d{4}$")


@dataclass(frozen=True, slots=True)
class CitationCounts:
    """Citation counts of the stored papers of a category, as the archive last wrote them."""

    counts: dict[str, int]
    source: str
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class CitationGains:
    """What the stored papers of a category gained between two full refreshes (CIT-9).

    Attributes:
        gains: Citations gained, for each paper that gained any.
        since: Date of the refresh they are counted from.
        generated_at: Date of the refresh they are counted to.
    """

    gains: dict[str, int]
    since: datetime
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class ScholarFile:
    """What Semantic Scholar knows of the stored papers of a category, as last written."""

    papers: dict[str, ScholarRecord]
    source: str
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class TopRecent:
    """The most cited papers of the last 12 months of a category, as the archive last chose them.

    Attributes:
        papers: The papers, newest first.
        since: First day of first appearance of the 12 months they were chosen from.
    """

    papers: list[Paper]
    since: date


@dataclass(frozen=True, slots=True)
class DaySummary:
    """Number of papers stored for one announcement day."""

    day: date
    count: int


class PaperStore:
    """Read and write papers grouped by category and announcement day."""

    def __init__(self, root: Path) -> None:
        """Create a store rooted at ``root`` (created on first write)."""
        self.root = root

    def categories(self) -> list[str]:
        """Return the categories present in the store, sorted."""
        if not self.root.is_dir():
            return []
        return sorted(path.name for path in self.root.iterdir() if path.is_dir())

    def days(self, category: str) -> list[date]:
        """Return the announcement days stored for ``category``, most recent first."""
        directory = self.root / category
        if not directory.is_dir():
            return []
        return sorted(
            (
                date.fromisoformat(path.stem)
                for path in directory.glob("*.json")
                if _DAY_STEM_RE.match(path.stem)
            ),
            reverse=True,
        )

    def load_day(self, category: str, day: date) -> list[Paper]:
        """Load the papers of one day, or an empty list if the day is not stored.

        Raises:
            StoreError: If the file is not a valid day file, or of another ``schema_version``.
        """
        return self._load_papers(self._day_path(category, day))

    def _load_papers(self, path: Path) -> list[Paper]:
        if not path.is_file():
            return []
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
            _check_version(payload, path, "papers")
            records = payload["papers"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            msg = f"Invalid papers file {path}: {exc}"
            raise StoreError(msg) from exc
        return [Paper.from_record(record) for record in records]

    def iter_papers(self, category: str | None = None) -> Iterator[Paper]:
        """Iterate over stored papers, optionally restricted to one category."""
        categories = [category] if category else self.categories()
        for name in categories:
            for day in self.days(name):
                yield from self.load_day(name, day)

    def save(self, category: str, papers: Iterable[Paper]) -> list[date]:
        """Write papers to their day files, replacing existing entries with the same id.

        Papers already stored for the same day but absent from ``papers`` are kept, so
        saving is idempotent and never loses data. A paper is stored once, on the first day
        it was announced: a cross-list can be announced again days later (2609.10714), and
        then stays on its earlier day, or moves there from a later one.

        Args:
            category: Category the papers were listed in.
            papers: Papers to store.

        Returns:
            The days whose file was written.
        """
        stored = self._stored_days(category)
        targets: dict[str, Paper] = {}
        for paper in papers:
            earlier = targets.get(paper.arxiv_id)
            first = min(
                [paper.announced, *stored.get(paper.arxiv_id, ()), *([earlier.announced] if earlier else [])]
            )
            targets[paper.arxiv_id] = paper if first == paper.announced else replace(paper, announced=first)

        by_day: defaultdict[date, list[Paper]] = defaultdict(list)
        leaving: defaultdict[date, set[str]] = defaultdict(set)
        for paper in targets.values():
            by_day[paper.announced].append(paper)
            for day in stored.get(paper.arxiv_id, ()):
                if day != paper.announced:
                    leaving[day].add(paper.arxiv_id)

        for day in by_day.keys() | leaving.keys():
            merged = {
                paper.arxiv_id: paper
                for paper in self.load_day(category, day)
                if paper.arxiv_id not in leaving[day]
            }
            merged.update((paper.arxiv_id, paper) for paper in by_day[day])
            self._write_day(category, day, list(merged.values()))
        return sorted(by_day.keys() | leaving.keys(), reverse=True)

    def _stored_days(self, category: str) -> dict[str, list[date]]:
        """The days each stored paper of ``category`` is on (one, unless stored twice)."""
        days: defaultdict[str, list[date]] = defaultdict(list)
        for day in self.days(category):
            path = self._day_path(category, day)
            try:
                payload: Any = json.loads(path.read_text(encoding="utf-8"))
                _check_version(payload, path, "papers")
                ids = [str(record["arxiv_id"]) for record in payload["papers"]]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                msg = f"Invalid papers file {path}: {exc}"
                raise StoreError(msg) from exc
            for arxiv_id in ids:
                days[arxiv_id].append(day)
        return days

    def remove_days(self, category: str, days: Iterable[date]) -> None:
        """Delete the files of the given days (the archive keeps what must be kept)."""
        for day in days:
            self._day_path(category, day).unlink(missing_ok=True)

    def archive_years(self, category: str) -> list[int]:
        """Return the years of the archive of ``category``, most recent first."""
        directory = self.root / category / ARCHIVE_DIRNAME
        if not directory.is_dir():
            return []
        return sorted(
            (int(path.stem) for path in directory.glob("*.json") if _YEAR_STEM_RE.match(path.stem)),
            reverse=True,
        )

    def load_archive(self, category: str, year: int) -> list[Paper]:
        """Load the archived papers of one year, or an empty list.

        Raises:
            StoreError: If the file is not a valid archive file, or of another ``schema_version``.
        """
        return self._load_papers(self._archive_path(category, year))

    def iter_archive(self, category: str) -> Iterator[Paper]:
        """Iterate over the archived papers of ``category``."""
        for year in self.archive_years(category):
            yield from self.load_archive(category, year)

    def write_archive(self, category: str, papers: Iterable[Paper]) -> None:
        """Replace the whole archive of ``category``: one file per year of ``announced``."""
        by_year: defaultdict[int, list[Paper]] = defaultdict(list)
        for paper in papers:
            by_year[paper.announced.year].append(paper)
        for year in set(self.archive_years(category)) - set(by_year):
            self._archive_path(category, year).unlink()
        for year, year_papers in by_year.items():
            year_papers.sort(key=lambda paper: (paper.announced, paper.arxiv_id), reverse=True)
            payload = {
                "schema_version": SCHEMA_VERSION,
                "category": category,
                "year": year,
                "papers": [paper.to_record() for paper in year_papers],
            }
            _write_json(self._archive_path(category, year), payload)

    def load_top_recent(self, category: str) -> TopRecent | None:
        """The most cited papers of the last 12 months of ``category``, if ever written.

        Raises:
            StoreError: If the file is not a valid top-recent file, or of another ``schema_version``.
        """
        path = self.root / category / TOP_RECENT_FILENAME
        if not path.is_file():
            return None
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
            _check_version(payload, path, "top-recent")
            since = date.fromisoformat(payload["since"])
            records = payload["papers"]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            msg = f"Invalid top-recent file {path}: {exc}"
            raise StoreError(msg) from exc
        return TopRecent([Paper.from_record(record) for record in records], since)

    def iter_top_recent(self, category: str) -> Iterator[Paper]:
        """Iterate over the most cited papers of the last 12 months of ``category``."""
        top_recent = self.load_top_recent(category)
        yield from top_recent.papers if top_recent else ()

    def write_top_recent(self, category: str, papers: Iterable[Paper], *, since: date) -> None:
        """Replace the most cited papers of the last 12 months of ``category``.

        Args:
            category: arXiv category.
            papers: The papers, first seen on ``since`` or later.
            since: First day of first appearance of the 12 months they were chosen from.
        """
        payload = {
            "schema_version": SCHEMA_VERSION,
            "category": category,
            "since": since.isoformat(),
            "papers": [
                paper.to_record()
                for paper in sorted(papers, key=lambda paper: (paper.announced, paper.arxiv_id), reverse=True)
            ],
        }
        _write_json(self.root / category / TOP_RECENT_FILENAME, payload)

    def load_citations(self, category: str) -> dict[str, int]:
        """Citation counts of the stored papers of ``category`` (empty if never written)."""
        citations = self.load_citation_counts(category)
        return citations.counts if citations else {}

    def load_citation_counts(self, category: str) -> CitationCounts | None:
        """Citation counts of ``category`` with their source and date, if ever written.

        Raises:
            StoreError: If the file is not a valid citations file, or of another ``schema_version``.
        """
        path = self.root / category / CITATIONS_FILENAME
        if not path.is_file():
            return None
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
            _check_version(payload, path, "citations")
            return CitationCounts(
                counts={str(arxiv_id): int(count) for arxiv_id, count in payload["counts"].items()},
                source=str(payload["source"]),
                generated_at=datetime.fromisoformat(payload["generated_at"]),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            msg = f"Invalid citations file {path}: {exc}"
            raise StoreError(msg) from exc

    def write_citations(
        self, category: str, counts: Mapping[str, int], *, source: str, now: datetime | None = None
    ) -> None:
        """Write the citation counts of the stored papers of ``category``, dated now.

        The counts they replace, when at least ``GAINS_MIN_DAYS`` old (``config.py``), give
        what each paper gained since into ``citation-gains.json``: the site's rising papers.

        Raises:
            SchemaVersionError: If the counts it replaces are of another ``schema_version``.
        """
        now = now or datetime.now(tz=UTC)
        try:
            current = self.load_citation_counts(category)
        except SchemaVersionError:
            raise
        except StoreError:
            logger.warning("No citation gains: the former counts of %s do not load", category)
            current = None
        if current is not None and now - current.generated_at >= timedelta(days=GAINS_MIN_DAYS):
            gains = {
                arxiv_id: count - before
                for arxiv_id, count in counts.items()
                if (before := current.counts.get(arxiv_id)) is not None and count > before
            }
            payload = {
                "schema_version": SCHEMA_VERSION,
                "category": category,
                "since": current.generated_at.isoformat(timespec="seconds"),
                "generated_at": now.isoformat(timespec="seconds"),
                "source": source,
                "gains": dict(sorted(gains.items())),
            }
            _write_json(self.root / category / GAINS_FILENAME, payload)
        self._write_citations(category, counts, source=source, generated_at=now)

    def load_citation_gains(self, category: str) -> CitationGains | None:
        """What the papers of ``category`` gained between the last two full refreshes, if known.

        Raises:
            StoreError: If the file is not a valid citation gains file, or of another ``schema_version``.
        """
        path = self.root / category / GAINS_FILENAME
        if not path.is_file():
            return None
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
            _check_version(payload, path, "citation gains")
            return CitationGains(
                gains={str(arxiv_id): int(gain) for arxiv_id, gain in payload["gains"].items()},
                since=datetime.fromisoformat(payload["since"]),
                generated_at=datetime.fromisoformat(payload["generated_at"]),
            )
        except (json.JSONDecodeError, AttributeError, KeyError, TypeError, ValueError) as exc:
            msg = f"Invalid citation gains file {path}: {exc}"
            raise StoreError(msg) from exc

    def merge_citations(self, category: str, counts: Mapping[str, int], *, source: str) -> None:
        """Add counts to those of ``category``, updating the ones already there.

        The file keeps the date and source of its last full refresh
        (:meth:`write_citations`): the counts added in between are newer, never older.
        """
        current = self.load_citation_counts(category)
        if current is None:
            self.write_citations(category, counts, source=source)
            return
        merged = {**current.counts, **counts}
        self._write_citations(category, merged, source=current.source, generated_at=current.generated_at)

    def _write_citations(
        self, category: str, counts: Mapping[str, int], *, source: str, generated_at: datetime
    ) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "category": category,
            "generated_at": generated_at.isoformat(timespec="seconds"),
            "source": source,
            "counts": dict(sorted(counts.items())),
        }
        _write_json(self.root / category / CITATIONS_FILENAME, payload)

    def load_scholar(self, category: str) -> ScholarFile | None:
        """The DOIs, published venues and author ids of ``category``, if ever written.

        Raises:
            StoreError: If the file is not a valid ``scholar.json``, or of another ``schema_version``.
        """
        path = self.root / category / SCHOLAR_FILENAME
        if not path.is_file():
            return None
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
            _check_version(payload, path, "scholar")
            return ScholarFile(
                papers={
                    str(arxiv_id): ScholarRecord.from_record(record)
                    for arxiv_id, record in payload["papers"].items()
                },
                source=str(payload["source"]),
                generated_at=datetime.fromisoformat(payload["generated_at"]),
            )
        except (json.JSONDecodeError, AttributeError, KeyError, TypeError, ValueError) as exc:
            msg = f"Invalid scholar file {path}: {exc}"
            raise StoreError(msg) from exc

    def write_scholar(self, category: str, papers: Mapping[str, ScholarRecord], *, source: str) -> None:
        """Write what Semantic Scholar knows of the stored papers of ``category``, dated now.

        Papers it knows nothing of are left out.
        """
        payload = {
            "schema_version": SCHEMA_VERSION,
            "category": category,
            "generated_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "source": source,
            "papers": {
                arxiv_id: record.to_record()
                for arxiv_id, record in sorted(papers.items())
                if not record.is_empty()
            },
        }
        _write_json(self.root / category / SCHOLAR_FILENAME, payload)

    def summaries(self, category: str) -> list[DaySummary]:
        """Return the number of papers per day for ``category``, most recent first."""
        return [DaySummary(day, len(self.load_day(category, day))) for day in self.days(category)]

    def write_index(self) -> Path:
        """Write ``index.json``, which the web app reads to discover available data."""
        index = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "categories": {
                category: [
                    {"date": summary.day.isoformat(), "count": summary.count}
                    for summary in self.summaries(category)
                ]
                for category in self.categories()
            },
            "archives": {
                category: [{"year": year, "count": len(self.load_archive(category, year))} for year in years]
                for category in self.categories()
                if (years := self.archive_years(category))
            },
            "top_recent": {
                category: {"since": top_recent.since.isoformat(), "count": len(top_recent.papers)}
                for category in self.categories()
                if (top_recent := self.load_top_recent(category))
            },
        }
        path = self.root / INDEX_FILENAME
        _write_json(path, index)
        return path

    def _archive_path(self, category: str, year: int) -> Path:
        return self.root / category / ARCHIVE_DIRNAME / f"{year}.json"

    def _day_path(self, category: str, day: date) -> Path:
        return self.root / category / f"{day.isoformat()}.json"

    def _write_day(self, category: str, day: date, papers: list[Paper]) -> None:
        path = self._day_path(category, day)
        logger.debug("Writing %d papers to %s", len(papers), path)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "category": category,
            "date": day.isoformat(),
            "papers": [paper.to_record() for paper in papers],
        }
        _write_json(path, payload)


def _check_version(payload: object, path: Path, kind: str) -> None:
    """Refuse a file written with another ``schema_version`` than this code's.

    A breaking change bumps the version and migrates the files in the same commit, so a
    file of another version is one this code would misread, or relabel when saving.

    Raises:
        SchemaVersionError: If ``payload`` is a JSON object without ``SCHEMA_VERSION``.
    """
    if isinstance(payload, dict) and (found := payload.get("schema_version")) != SCHEMA_VERSION:
        msg = f"Invalid {kind} file {path}: schema_version is {found!r}, expected {SCHEMA_VERSION}"
        raise SchemaVersionError(msg)


def _write_json(path: Path, payload: object) -> None:
    """Write JSON atomically, so an interrupted run never leaves a truncated file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)
