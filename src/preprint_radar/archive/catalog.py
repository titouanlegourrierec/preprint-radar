"""The catalog of every paper of a category, kept for the citation archive.

The catalog lists the archive's candidates and gives the metadata of the papers that enter
it. It is harvested from arXiv's OAI-PMH (:mod:`preprint_radar.sources.arxiv_oai`) and kept
out of the repository (rebuilt, or restored from a cache in CI), as a gzip-compressed
JSON-lines file per category.

A refresh asks for the records modified since the last harvest, and drops those OAI says
were deleted. A record that leaves the category's set (a cross-list removed) is not among
them: every ``FULL_HARVEST_DAYS`` the whole set is harvested again and replaces the catalog
(META-6).
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

# Days between two harvests of the whole set, which drop the records that left it: about
# 45 minutes for cs.CV's 210,000, four times a year.
FULL_HARVEST_DAYS = 90
# A whole set that lists fewer of the catalog's records is not trusted to replace it: a
# quarter's removed cross-lists are a handful, and an archived paper that leaves the
# catalog leaves the archive.
FULL_HARVEST_MIN_SHARE = 0.99

# arXiv's groups that are archives of their own, as ``ListSets`` names them; every other
# archive (astro-ph, cond-mat, hep-th, quant-ph…) is in the physics group.
_GROUPS = frozenset({"cs", "econ", "eess", "math", "q-bio", "q-fin", "stat"})


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
        """OAI set of the category, as ``ListSets`` names it (META-6).

        ``cs.CV`` is ``cs:cs:CV``, ``astro-ph.CO`` is ``physics:astro-ph:CO``, and
        ``hep-th``, an archive without categories, ``physics:hep-th``.
        """
        archive, _, subject = self.category.partition(".")
        group = archive if archive in _GROUPS else "physics"
        return ":".join(filter(None, (group, archive, subject)))

    def entries(self) -> dict[str, CatalogEntry]:
        """Every harvested paper, by arXiv identifier (empty before the first harvest)."""
        return {arxiv_id: entry for arxiv_id, entry in _read(self.path) if entry is not None}

    def refresh(self, client: HttpClient, today: date) -> int:
        """Harvest what changed since the last harvest, or the whole set when due.

        The whole set is harvested the first time, then every ``FULL_HARVEST_DAYS``, and
        replaces the catalog; in between, what changed is merged into it.

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
        # A catalog harvested before whole harvests were dated counts from its last harvest.
        full = state.get("full") or harvested
        token = state.get("token")
        if token:
            whole = state.get("mode") == "full"
        else:
            whole = full is None or today - date.fromisoformat(full) >= timedelta(days=FULL_HARVEST_DAYS)
        # Datestamps are days: start a day early so that nothing falls between harvests.
        since = date.fromisoformat(harvested) - timedelta(days=1) if harvested and not whole else None
        try:
            return self._harvest(client, today, harvested=harvested, full=full, since=since, token=token)
        except ExpiredTokenError:
            logger.warning("The interrupted harvest expired; harvesting again from the start")
            return self._harvest(client, today, harvested=harvested, full=full, since=since, token=None)

    def _harvest(
        self,
        client: HttpClient,
        today: date,
        *,
        harvested: str | None,
        full: str | None,
        since: date | None,
        token: str | None,
    ) -> int:
        """Harvest the set since ``since`` (``None``: the whole set), resuming ``token``."""
        logger.info(
            "Harvesting %s %s",
            self.set_spec,
            "(resuming)" if token else f"since {since}" if since else "(everything)",
        )
        whole = since is None
        self.directory.mkdir(parents=True, exist_ok=True)
        if token:
            self._repair_partial()
        else:
            self._partial.unlink(missing_ok=True)
        count = 0
        for page in harvest(client, self.set_spec, since=since, token=token):
            # A deleted record is written as a tombstone, which drops it from the catalog.
            _append(
                self._partial,
                [*((entry.arxiv_id, entry) for entry in page.entries), *((i, None) for i in page.deleted)],
            )
            count += len(page.entries)
            self._write_state(
                {
                    "harvested": harvested,
                    "token": page.resumption_token,
                    "full": full,
                    "mode": "full" if whole else "since",
                }
            )
            logger.info("%s records harvested", f"{count:,}")

        _write(self.path, self._merged(whole=whole).items())
        self._partial.unlink(missing_ok=True)
        self._write_state(
            {"harvested": today.isoformat(), "token": None, "full": today.isoformat() if whole else full}
        )
        return count

    def _merged(self, *, whole: bool) -> dict[str, CatalogEntry]:
        """The catalog with the harvest's records: those of the whole set, or what changed.

        The whole set replaces the catalog, unless it lists fewer than
        ``FULL_HARVEST_MIN_SHARE`` of its records, which a warning says.
        """
        previous = self.entries()
        merged = {} if whole else dict(previous)
        for arxiv_id, entry in _read(self._partial, tolerant=True):
            if entry is None:
                merged.pop(arxiv_id, None)
            else:
                merged[arxiv_id] = entry
        if not whole or not previous:
            return merged
        kept = len(previous.keys() & merged.keys())
        if kept < FULL_HARVEST_MIN_SHARE * len(previous):
            logger.warning(
                "The whole set of %s lists %s of the catalog's %s records: kept them all",
                self.category,
                f"{kept:,}",
                f"{len(previous):,}",
            )
            return previous | merged
        logger.info(
            "%s records left %s since its last whole harvest", f"{len(previous) - kept:,}", self.set_spec
        )
        return merged

    def _repair_partial(self) -> None:
        """Drop the page an interruption cut short from the pages of the harvest to resume.

        Each page is appended as a new gzip member: after a truncated member, the pages of
        the resumed harvest could not be read back. The cut page is harvested again anyway.
        """
        _write(self._partial, list(_read(self._partial, tolerant=True)))

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


def _read(path: Path, *, tolerant: bool = False) -> Iterator[tuple[str, CatalogEntry | None]]:
    """Read catalog entries, and the tombstones of deleted records (``None``) of a harvest.

    With ``tolerant``, a truncated end (a harvest killed while writing a page) ends the
    reading instead of failing: that page is harvested again on resumption.
    """
    if not path.is_file():
        return
    try:
        with gzip.open(path, "rt", encoding="utf-8") as lines:
            for line in lines:
                record = json.loads(line)
                if "deleted" in record:
                    yield str(record["deleted"]), None
                    continue
                entry = CatalogEntry.from_record(record)
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


def _write(path: Path, records: Iterable[tuple[str, CatalogEntry | None]]) -> None:
    """Write catalog entries to ``path`` in one go, replacing it."""
    tmp = path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    _append(tmp, records)
    tmp.replace(path)


def _append(path: Path, records: Iterable[tuple[str, CatalogEntry | None]]) -> None:
    """Append entries to ``path`` as one gzip member, a deleted record's (``None``) as a tombstone."""
    with gzip.open(path, "at", encoding="utf-8") as out:
        for arxiv_id, entry in records:
            record = entry.to_record() if entry is not None else {"deleted": arxiv_id}
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
