"""arXiv's OAI-PMH interface: every paper of a category, harvested in bulk.

OAI-PMH (``oaipmh.arxiv.org``) is arXiv's sanctioned way to harvest metadata in bulk: the
set ``cs:cs:CV`` lists every paper of cs.CV, cross-lists included, 1,300 records per page,
with title, authors, abstract, comments and categories. The whole set (about 200,000
papers) takes about 45 minutes; a refresh only asks for the records modified since a day.
:mod:`preprint_radar.archive.catalog` keeps the harvested records.
"""

import logging
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date
from typing import Self
from xml.etree.ElementTree import Element

from defusedxml import ElementTree

from preprint_radar.exceptions import ParseError
from preprint_radar.http import HttpClient

logger = logging.getLogger(__name__)

OAI_URL = "https://oaipmh.arxiv.org/oai"
# arXiv's OAI-PMH has no crawl delay in robots.txt and signals overload with 503 +
# Retry-After (which HttpClient honors); a few seconds between pages is polite.
OAI_DELAY_SECONDS = 5.0
# A page of 1,300 records can take a while to be generated.
OAI_TIMEOUT_SECONDS = 180.0

# Identifiers since 2007: YYMM.NNNN(N), the month of first announcement.
_NEW_STYLE_ID_RE = re.compile(r"^(?P<year>\d{2})(?P<month>\d{2})\.\d{4,5}$")
# arXiv splits the author list it was given as written (AFF-21): a footnote marker stays
# on the name ("Jie Qin1" in 2104.14913, "Yulong Cao*" in 2106.09249), the last author
# keeps its "and " ("and Haibin Ling" in 2201.08049), and "et al." is an author named
# "others" (2005.03412, 2505.18988).
_NAME_MARKERS_RE = re.compile(r"[\s\d*†]+$")
_LEADING_AND_RE = re.compile(r"^(?:and\s+)+")
_ET_AL = "others"

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
        authors: Author names, "Forenames Keyname", cleaned by :func:`author_names`.
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
            # A catalog harvested before the names were cleaned is cleaned as it is read.
            authors=author_names(str(item) for item in _list(record["authors"])),
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


def author_names(names: Iterable[str]) -> tuple[str, ...]:
    """Author names as arXiv's metadata gives them, without what the author list added.

    Trailing digits and the markers ``*`` and ``†`` (footnotes) and a leading "and " are
    dropped; so are the author "others" ("et al.") and a name left empty (a lone footnote
    number). Cleaning clean names changes nothing, so a catalog can be cleaned again.
    """
    cleaned = (_NAME_MARKERS_RE.sub("", _LEADING_AND_RE.sub("", name.strip())) for name in names)
    return tuple(name for name in cleaned if name and name != _ET_AL)


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
    authors = author_names(
        " ".join(
            filter(None, (_text(author, "forenames"), _text(author, "keyname"), _text(author, "suffix")))
        )
        for author in meta.findall(f"{_ARXIV}authors/{_ARXIV}author")
    )
    return CatalogEntry(
        arxiv_id=arxiv_id,
        created=date.fromisoformat(created),
        categories=tuple((_text(meta, "categories") or "").split()),
        title=title,
        authors=authors,
        abstract=_text(meta, "abstract"),
        comments=_text(meta, "comments"),
        journal_ref=_text(meta, "journal-ref"),
    )


def _text(element: Element, name: str) -> str | None:
    child = element.find(f"{_ARXIV}{name}")
    if child is None or child.text is None:
        return None
    return " ".join(child.text.split()) or None


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        msg = f"Expected a list, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def _optional(value: object) -> str | None:
    return None if value is None else str(value)
