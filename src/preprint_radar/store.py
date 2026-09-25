"""On-disk store of papers, laid out for static hosting.

Layout::

    <root>/
    ├── index.json                 # categories, days and paper counts
    └── <category>/
        └── <YYYY-MM-DD>.json      # papers announced that day in that category

One file per day keeps each update small, and lets the web app load only the days
it needs.
"""

import json
import logging
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from preprint_radar.exceptions import StoreError
from preprint_radar.models import Paper

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
INDEX_FILENAME = "index.json"


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
        return sorted((date.fromisoformat(path.stem) for path in directory.glob("*.json")), reverse=True)

    def load_day(self, category: str, day: date) -> list[Paper]:
        """Load the papers of one day, or an empty list if the day is not stored.

        Raises:
            StoreError: If the file is not a valid day file.
        """
        path = self._day_path(category, day)
        if not path.is_file():
            return []
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
            records = payload["papers"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            msg = f"Invalid day file {path}: {exc}"
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
        saving is idempotent and never loses data.

        Args:
            category: Category the papers were listed in.
            papers: Papers to store.

        Returns:
            The days whose file was written.
        """
        by_day: defaultdict[date, list[Paper]] = defaultdict(list)
        for paper in papers:
            by_day[paper.announced].append(paper)

        for day, new_papers in by_day.items():
            merged = {paper.arxiv_id: paper for paper in self.load_day(category, day)}
            merged.update((paper.arxiv_id, paper) for paper in new_papers)
            self._write_day(category, day, list(merged.values()))
        return sorted(by_day, reverse=True)

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
        }
        path = self.root / INDEX_FILENAME
        _write_json(path, index)
        return path

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
