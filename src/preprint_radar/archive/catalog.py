"""The catalog of every paper of a category, kept for the citation archive.

The catalog lists the archive's candidates and gives the metadata of the papers that enter
it. It is harvested from arXiv's OAI-PMH (:mod:`preprint_radar.sources.arxiv_oai`) and kept
out of the repository (rebuilt, or restored from a cache in CI), as a gzip-compressed
JSON-lines file per category.
"""

import gzip
import json
import logging
import zlib
from collections.abc import Iterable, Iterator
from datetime import date, timedelta
from pathlib import Path

from preprint_radar.exceptions import StoreError
from preprint_radar.http import HttpClient
from preprint_radar.sources.arxiv_oai import CatalogEntry, ExpiredTokenError, harvest

logger = logging.getLogger(__name__)


class Catalog:
    """The catalog of one category, stored as ``<directory>/<category>.jsonl.gz``.

    A harvest in progress appends its pages to ``<category>.partial.jsonl.gz`` and saves
    its resumption token, so that an interrupted harvest resumes where it stopped.
    """

    def __init__(self, directory: Path, category: str) -> None:
        """Create the catalog of ``category`` in ``directory`` (created on first write)."""
        self.directory = directory
        self.category = category
        self.path = directory / f"{category}.jsonl.gz"
        self._partial = directory / f"{category}.partial.jsonl.gz"
        self._state = directory / f"{category}.state.json"

    @property
    def set_spec(self) -> str:
        """OAI set of the category: ``cs.CV`` is ``cs:cs:CV``."""
        archive = self.category.split(".", maxsplit=1)[0]
        return f"{archive}:{self.category.replace('.', ':')}"

    def entries(self) -> dict[str, CatalogEntry]:
        """Every harvested paper, by arXiv identifier (empty before the first harvest)."""
        return dict(_read(self.path))

    def refresh(self, client: HttpClient, today: date) -> int:
        """Harvest what changed since the last harvest (everything the first time).

        Args:
            client: HTTP client for the OAI-PMH endpoint.
            today: Current day, recorded as the date of this harvest.

        Returns:
            The number of records harvested.

        Raises:
            FetchError: If a page cannot be downloaded; the harvest resumes next time.
            ParseError: If a page is invalid.
        """
        state = self._read_state()
        harvested = state.get("harvested")
        # Datestamps are days: start a day early so that nothing falls between harvests.
        since = date.fromisoformat(harvested) - timedelta(days=1) if harvested else None
        try:
            return self._harvest(client, today, harvested=harvested, since=since, token=state.get("token"))
        except ExpiredTokenError:
            logger.warning("The interrupted harvest expired; harvesting again from the start")
            return self._harvest(client, today, harvested=harvested, since=since, token=None)

    def _harvest(
        self, client: HttpClient, today: date, *, harvested: str | None, since: date | None, token: str | None
    ) -> int:
        logger.info(
            "Harvesting %s %s",
            self.set_spec,
            "(resuming)" if token else f"since {since}" if since else "(everything)",
        )
        self.directory.mkdir(parents=True, exist_ok=True)
        if token:
            self._repair_partial()
        else:
            self._partial.unlink(missing_ok=True)
        count = 0
        for page in harvest(client, self.set_spec, since=since, token=token):
            with gzip.open(self._partial, "at", encoding="utf-8") as partial:
                for entry in page.entries:
                    partial.write(json.dumps(entry.to_record(), ensure_ascii=False) + "\n")
            count += len(page.entries)
            self._write_state({"harvested": harvested, "token": page.resumption_token})
            logger.info("%s records harvested", f"{count:,}")

        merged = self.entries()
        merged.update(_read(self._partial, tolerant=True))
        _write(self.path, merged.values())
        self._partial.unlink(missing_ok=True)
        self._write_state({"harvested": today.isoformat(), "token": None})
        return count

    def _repair_partial(self) -> None:
        """Drop the page an interruption cut short from the pages of the harvest to resume.

        Each page is appended as a new gzip member: after a truncated member, the pages of
        the resumed harvest could not be read back. The cut page is harvested again anyway.
        """
        _write(self._partial, [entry for _, entry in _read(self._partial, tolerant=True)])

    def _read_state(self) -> dict[str, str | None]:
        if not self._state.is_file():
            return {}
        try:
            state = json.loads(self._state.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            msg = f"Invalid catalog state {self._state}: {exc}"
            raise StoreError(msg) from exc
        return {key: value for key, value in state.items() if isinstance(value, str | None)}

    def _write_state(self, state: dict[str, str | None]) -> None:
        tmp = self._state.with_suffix(".tmp")
        tmp.write_text(json.dumps(state) + "\n", encoding="utf-8")
        tmp.replace(self._state)


def _read(path: Path, *, tolerant: bool = False) -> Iterator[tuple[str, CatalogEntry]]:
    """Read catalog entries.

    With ``tolerant``, a truncated end (a harvest killed while writing a page) ends the
    reading instead of failing: that page is harvested again on resumption.
    """
    if not path.is_file():
        return
    try:
        with gzip.open(path, "rt", encoding="utf-8") as lines:
            for line in lines:
                entry = CatalogEntry.from_record(json.loads(line))
                yield entry.arxiv_id, entry
    except (EOFError, gzip.BadGzipFile, zlib.error, json.JSONDecodeError) as exc:
        if tolerant:
            logger.warning("Ignoring the truncated end of %s: %s", path, exc)
            return
        msg = f"Invalid catalog {path}: {exc}"
        raise StoreError(msg) from exc
    except (OSError, KeyError, TypeError, ValueError) as exc:
        msg = f"Invalid catalog {path}: {exc}"
        raise StoreError(msg) from exc


def _write(path: Path, entries: Iterable[CatalogEntry]) -> None:
    """Write catalog entries to ``path`` in one go, replacing it."""
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as out:
        for entry in entries:
            out.write(json.dumps(entry.to_record(), ensure_ascii=False) + "\n")
    tmp.replace(path)
