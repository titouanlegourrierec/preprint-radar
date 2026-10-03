"""On-disk store of papers, laid out for static hosting.

Layout::

    <root>/
    ├── index.json                 # categories, days, archive years and paper counts
    └── <category>/
        ├── <YYYY-MM-DD>.json      # papers announced that day in that category
        ├── citations.json         # citation counts of the stored papers
        ├── scholar.json           # their DOI, published venue and author ids
        └── archive/
            └── <YYYY>.json        # highly cited older papers, by year of first version

One file per day keeps each update small, and lets the web app load only the days
it needs. The archive holds the papers kept for their citations once they are older than
the days kept in full; it is rewritten as a whole by :meth:`PaperStore.write_archive`.
"""

import json
import logging
import re
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from preprint_radar.exceptions import StoreError
from preprint_radar.models import Paper, ScholarRecord

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
INDEX_FILENAME = "index.json"
CITATIONS_FILENAME = "citations.json"
SCHOLAR_FILENAME = "scholar.json"
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
class ScholarFile:
    """What Semantic Scholar knows of the stored papers of a category, as last written."""

    papers: dict[str, ScholarRecord]
    source: str
    generated_at: datetime


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
            StoreError: If the file is not a valid day file.
        """
        return self._load_papers(self._day_path(category, day))

    def _load_papers(self, path: Path) -> list[Paper]:
        if not path.is_file():
            return []
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
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
                records = json.loads(path.read_text(encoding="utf-8"))["papers"]
                ids = [str(record["arxiv_id"]) for record in records]
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
            StoreError: If the file is not a valid archive file.
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

    def load_citations(self, category: str) -> dict[str, int]:
        """Citation counts of the stored papers of ``category`` (empty if never written)."""
        citations = self.load_citation_counts(category)
        return citations.counts if citations else {}

    def load_citation_counts(self, category: str) -> CitationCounts | None:
        """Citation counts of ``category`` with their source and date, if ever written.

        Raises:
            StoreError: If the file is not a valid citations file.
        """
        path = self.root / category / CITATIONS_FILENAME
        if not path.is_file():
            return None
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
            return CitationCounts(
                counts={str(arxiv_id): int(count) for arxiv_id, count in payload["counts"].items()},
                source=str(payload["source"]),
                generated_at=datetime.fromisoformat(payload["generated_at"]),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            msg = f"Invalid citations file {path}: {exc}"
            raise StoreError(msg) from exc

    def write_citations(self, category: str, counts: Mapping[str, int], *, source: str) -> None:
        """Write the citation counts of the stored papers of ``category``, dated now."""
        self._write_citations(category, counts, source=source, generated_at=datetime.now(tz=UTC))

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
            StoreError: If the file is not a valid ``scholar.json``.
        """
        path = self.root / category / SCHOLAR_FILENAME
        if not path.is_file():
            return None
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
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


def _write_json(path: Path, payload: object) -> None:
    """Write JSON atomically, so an interrupted run never leaves a truncated file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)
