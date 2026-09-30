"""Writers to persist papers to disk."""

import csv
import json
from collections.abc import Sequence
from dataclasses import fields
from enum import StrEnum
from pathlib import Path
from typing import Self

from preprint_radar.models import Paper

CSV_LIST_SEPARATOR = "; "
# The author-affiliation mapping is indices into another column: meaningless in a flat CSV.
CSV_COLUMNS = (
    *(field.name for field in fields(Paper) if field.name != "author_affiliations"),
    "abs_url",
    "pdf_url",
)


class ExportFormat(StrEnum):
    """Supported output formats."""

    JSON = "json"
    CSV = "csv"

    @classmethod
    def from_path(cls, path: Path) -> Self | None:
        """Infer the format from a file extension, if it is a known one."""
        try:
            return cls(path.suffix.removeprefix(".").lower())
        except ValueError:
            return None


def export_papers(papers: Sequence[Paper], path: Path, fmt: ExportFormat) -> None:
    """Write papers to ``path``, creating parent directories as needed.

    Args:
        papers: Papers to write.
        path: Destination file.
        fmt: Output format.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    match fmt:
        case ExportFormat.JSON:
            write_json(papers, path)
        case ExportFormat.CSV:  # pragma: no branch - the match covers every format
            write_csv(papers, path)


def write_json(papers: Sequence[Paper], path: Path) -> None:
    """Write papers as a JSON array of records."""
    records = [paper.to_record() for paper in papers]
    with path.open("w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=2)
        file.write("\n")


def write_csv(papers: Sequence[Paper], path: Path) -> None:
    """Write papers as CSV, joining list fields with :data:`CSV_LIST_SEPARATOR`."""
    records = [paper.to_record() for paper in papers]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    key: CSV_LIST_SEPARATOR.join(str(item) for item in value)
                    if isinstance(value, list)
                    else value
                    for key, value in record.items()
                }
            )
