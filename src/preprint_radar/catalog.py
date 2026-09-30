"""Catalog of every paper of a category, harvested from arXiv's OAI-PMH interface.

OAI-PMH (``oaipmh.arxiv.org``) is arXiv's sanctioned way to harvest metadata in bulk: the
set ``cs:cs:CV`` lists every paper of cs.CV, cross-lists included, 1,300 records per page,
with title, authors, abstract, comments and categories. The whole set (about 200,000
papers) takes about 45 minutes; afterwards, a weekly refresh only asks for the records
modified since the last harvest (new papers and new versions).

The catalog feeds the citation archive: it lists the candidates, and gives the metadata of
the papers that enter the archive. It is kept out of the repository (it is rebuilt or
restored from a cache), as a gzip-compressed JSON-lines file per category.
"""

import gzip
import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Self
from xml.etree.ElementTree import Element

from defusedxml import ElementTree

from preprint_radar.exceptions import ParseError, StoreError
from preprint_radar.http import HttpClient

logger = logging.getLogger(__name__)

OAI_URL = "https://oaipmh.arxiv.org/oai"
# arXiv's OAI-PMH has no crawl delay in robots.txt and signals overload with 503 +
# Retry-After (which HttpClient honors); a few seconds between pages is polite.
OAI_DELAY_SECONDS = 5.0

# Identifiers since 2007: YYMM.NNNN(N), the month of first announcement.
_NEW_STYLE_ID_RE = re.compile(r"^(?P<year>\d{2})(?P<month>\d{2})\.\d{4,5}$")

_OAI = "{http://www.openarchives.org/OAI/2.0/}"
_ARXIV = "{http://arxiv.org/OAI/arXiv/}"


class ExpiredTokenError(ParseError):
    """The resumption token of an interrupted harvest is no longer valid."""


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogEntry:
    """A paper as listed by OAI-PMH.

    Attributes:
        arxiv_id: arXiv identifier without version.
        created: Date of the first version.
        categories: Categories, the primary one first.
        title: Title, whitespace collapsed.
        authors: Author names, "Forenames Keyname".
        abstract: Abstract, whitespace collapsed, or ``None``.
        comments: Author comments, or ``None``.
        journal_ref: Journal reference, or ``None``.
    """

    arxiv_id: str
    created: date
    categories: tuple[str, ...]
    title: str
    authors: tuple[str, ...]
    abstract: str | None = None
    comments: str | None = None
    journal_ref: str | None = None

    @property
    def first_seen(self) -> date:
        """Day the paper first appeared on arXiv.

        ``created`` is not always the first version's date (0904.2037, first submitted in
        April 2009, says 2010-01-06), but the identifier always gives the month of first
        announcement: ``created`` is used when it falls in that month.
        """
        match = _NEW_STYLE_ID_RE.match(self.arxiv_id)
        if match is None:
            return self.created
        month = date(2000 + int(match["year"]), int(match["month"]), 1)
        same_month = (self.created.year, self.created.month) == (month.year, month.month)
        return self.created if same_month else month

    def to_record(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "id": self.arxiv_id,
            "created": self.created.isoformat(),
            "categories": list(self.categories),
            "title": self.title,
            "authors": list(self.authors),
            "abstract": self.abstract,
            "comments": self.comments,
            "journal_ref": self.journal_ref,
        }

    @classmethod
    def from_record(cls, record: dict[str, object]) -> Self:
        """Rebuild an entry from :meth:`to_record` output."""
        return cls(
            arxiv_id=str(record["id"]),
            created=date.fromisoformat(str(record["created"])),
            categories=tuple(str(item) for item in _list(record["categories"])),
            title=str(record["title"]),
            authors=tuple(str(item) for item in _list(record["authors"])),
            abstract=_optional(record.get("abstract")),
            comments=_optional(record.get("comments")),
            journal_ref=_optional(record.get("journal_ref")),
        )


@dataclass(frozen=True, slots=True)
class OaiPage:
    """One page of a ``ListRecords`` response."""

    entries: tuple[CatalogEntry, ...]
    #: Token of the next page, ``None`` on the last one.
    resumption_token: str | None


def parse_list_records(xml: str) -> OaiPage:
    """Parse a ``ListRecords`` page in the ``arXiv`` metadata format.

    Deleted records are skipped; ``noRecordsMatch`` (nothing modified since the requested
    date) is an empty last page.

    Raises:
        ParseError: If the page is not valid OAI-PMH, or reports another error.
    """
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        msg = f"Invalid OAI-PMH response: {exc}"
        raise ParseError(msg) from exc
    error = root.find(f"{_OAI}error")
    if error is not None:
        code = error.get("code")
        if code == "noRecordsMatch":
            return OaiPage((), None)
        msg = f"OAI-PMH error {code}: {(error.text or '').strip()}"
        # arXiv's tokens expire at midnight UTC.
        raise ExpiredTokenError(msg) if code == "badResumptionToken" else ParseError(msg)
    records = root.find(f"{_OAI}ListRecords")
    if records is None:
        msg = "OAI-PMH response without ListRecords"
        raise ParseError(msg)
    entries = [entry for record in records.findall(f"{_OAI}record") if (entry := _entry(record)) is not None]
    token = records.find(f"{_OAI}resumptionToken")
    text = (token.text or "").strip() if token is not None else ""
    return OaiPage(tuple(entries), text or None)


def harvest(
    client: HttpClient, set_spec: str, *, since: date | None = None, token: str | None = None
) -> Iterator[OaiPage]:
    """Yield the pages of a ``ListRecords`` harvest, from ``since`` or a resumption token.

    Args:
        client: HTTP client for the OAI-PMH endpoint.
        set_spec: OAI set, e.g. ``"cs:cs:CV"``.
        since: Only records modified since this day (``None``: all of them).
        token: Resumption token of an interrupted harvest, to continue it.

    Raises:
        FetchError: If a page cannot be downloaded.
        ParseError: If a page is invalid.
    """
    while True:
        if token:
            params: dict[str, str | int] = {"verb": "ListRecords", "resumptionToken": token}
        else:
            params = {"verb": "ListRecords", "metadataPrefix": "arXiv", "set": set_spec}
            if since is not None:
                params["from"] = since.isoformat()
        page = parse_list_records(client.get_text(OAI_URL, params=params))
        yield page
        if page.resumption_token is None:
            return
        token = page.resumption_token


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
        if not token:
            self._partial.unlink(missing_ok=True)
        count = 0
        for page in harvest(client, self.set_spec, since=since, token=token):
            with gzip.open(self._partial, "at", encoding="utf-8") as partial:
                for entry in page.entries:
                    partial.write(json.dumps(entry.to_record(), ensure_ascii=False) + "\n")
            count += len(page.entries)
            self._write_state({"harvested": harvested, "token": page.resumption_token})
            logger.info("%d records harvested", count)

        merged = self.entries()
        merged.update(_read(self._partial, tolerant=True))
        tmp = self.path.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as out:
            for entry in merged.values():
                out.write(json.dumps(entry.to_record(), ensure_ascii=False) + "\n")
        tmp.replace(self.path)
        self._partial.unlink(missing_ok=True)
        self._write_state({"harvested": today.isoformat(), "token": None})
        return count

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


def _entry(record: Element) -> CatalogEntry | None:
    header = record.find(f"{_OAI}header")
    if header is not None and header.get("status") == "deleted":
        return None
    meta = record.find(f"{_OAI}metadata/{_ARXIV}arXiv")
    if meta is None:
        return None
    arxiv_id = _text(meta, "id")
    created = _text(meta, "created")
    title = _text(meta, "title")
    if not arxiv_id or not created or not title:
        return None
    authors = []
    for author in meta.findall(f"{_ARXIV}authors/{_ARXIV}author"):
        name = " ".join(
            filter(None, (_text(author, "forenames"), _text(author, "keyname"), _text(author, "suffix")))
        )
        if name:
            authors.append(name)
    return CatalogEntry(
        arxiv_id=arxiv_id,
        created=date.fromisoformat(created),
        categories=tuple((_text(meta, "categories") or "").split()),
        title=title,
        authors=tuple(authors),
        abstract=_text(meta, "abstract"),
        comments=_text(meta, "comments"),
        journal_ref=_text(meta, "journal-ref"),
    )


def _text(element: Element, name: str) -> str | None:
    child = element.find(f"{_ARXIV}{name}")
    if child is None or child.text is None:
        return None
    return " ".join(child.text.split()) or None


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
    except (EOFError, gzip.BadGzipFile, json.JSONDecodeError) as exc:
        if tolerant:
            logger.warning("Ignoring the truncated end of %s: %s", path, exc)
            return
        msg = f"Invalid catalog {path}: {exc}"
        raise StoreError(msg) from exc
    except (OSError, KeyError, TypeError, ValueError) as exc:
        msg = f"Invalid catalog {path}: {exc}"
        raise StoreError(msg) from exc


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        msg = f"Expected a list, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def _optional(value: object) -> str | None:
    return None if value is None else str(value)
