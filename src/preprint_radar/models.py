"""Domain models."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Self

from preprint_radar.exceptions import StoreError

ARXIV_BASE_URL = "https://arxiv.org"

type PaperRecord = dict[str, str | list[str] | list[str | None] | list[list[int] | None] | None]
"""JSON-serializable representation of a :class:`Paper`."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Paper:
    """A paper as announced in an arXiv listing, optionally enriched.

    Enrichment fields use ``None`` to mean "not retrieved yet", so that an empty value
    (e.g. no affiliation could be found) is not fetched again on the next run.

    Attributes:
        arxiv_id: arXiv identifier without version, e.g. ``"2609.30245"``.
        announced: Day on which the paper appeared in the listing.
        title: Paper title. LaTeX markup (e.g. ``$^2$``) is kept as-is.
        authors: Author names, in order.
        primary_subject: Primary subject, e.g. ``"Computer Vision and Pattern Recognition (cs.CV)"``.
        subjects: All subjects, primary one included.
        comments: Free-form author comments (venue, page count, project URL...).
        journal_ref: Journal reference, when the paper has been published.
        venue: Venue the paper was accepted at, detected from comments, e.g. ``"ECCV 2026"``.
        cross_list_from: Category the paper is cross-listed from, if any.
        html_url: URL of the HTML rendering, when arXiv could produce one.
        abstract: Abstract, or ``None`` if not retrieved yet.
        affiliations: Distinct affiliations of all authors, or ``None`` if not retrieved yet.
        author_affiliations: For each author, the indices of their own affiliations in
            ``affiliations``; ``None`` for an author the paper does not place, and ``None``
            altogether when the front matter never says who is where.
        institutions: For each affiliation, the institution it belongs to according to the
            Research Organization Registry, or ``None`` when there is no confident match;
            ``None`` altogether if not looked up yet. Always as long as ``affiliations``.
    """

    arxiv_id: str
    announced: date
    title: str
    authors: tuple[str, ...]
    primary_subject: str | None = None
    subjects: tuple[str, ...] = ()
    comments: str | None = None
    journal_ref: str | None = None
    venue: str | None = None
    cross_list_from: str | None = None
    html_url: str | None = None
    abstract: str | None = None
    affiliations: tuple[str, ...] | None = None
    author_affiliations: tuple[tuple[int, ...] | None, ...] | None = None
    institutions: tuple[str | None, ...] | None = None

    @property
    def abs_url(self) -> str:
        """URL of the abstract page."""
        return f"{ARXIV_BASE_URL}/abs/{self.arxiv_id}"

    @property
    def pdf_url(self) -> str:
        """URL of the PDF."""
        return f"{ARXIV_BASE_URL}/pdf/{self.arxiv_id}"

    @property
    def is_cross_list(self) -> bool:
        """Whether the paper is cross-listed from another category."""
        return self.cross_list_from is not None

    @property
    def is_enriched(self) -> bool:
        """Whether both the abstract and the affiliations have been retrieved."""
        return self.abstract is not None and self.affiliations is not None

    def to_record(self) -> PaperRecord:
        """Return a JSON-serializable representation of the paper."""
        return {
            "arxiv_id": self.arxiv_id,
            "announced": self.announced.isoformat(),
            "title": self.title,
            "authors": list(self.authors),
            "primary_subject": self.primary_subject,
            "subjects": list(self.subjects),
            "comments": self.comments,
            "journal_ref": self.journal_ref,
            "venue": self.venue,
            "cross_list_from": self.cross_list_from,
            "html_url": self.html_url,
            "abstract": self.abstract,
            "affiliations": None if self.affiliations is None else list(self.affiliations),
            "author_affiliations": None
            if self.author_affiliations is None
            else [None if entry is None else list(entry) for entry in self.author_affiliations],
            "institutions": None if self.institutions is None else list(self.institutions),
            "abs_url": self.abs_url,
            "pdf_url": self.pdf_url,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> Self:
        """Rebuild a paper from :meth:`to_record` output.

        Args:
            record: A mapping as produced by :meth:`to_record` (derived URLs are ignored).

        Returns:
            The paper.

        Raises:
            StoreError: If a field is missing or has the wrong type.
        """
        try:
            affiliations = _optional_str_list(record, "affiliations")
            author_affiliations = _optional_index_lists(record, "author_affiliations")
            institutions = _institutions(record, affiliations)
            return cls(
                arxiv_id=_str(record, "arxiv_id"),
                announced=date.fromisoformat(_str(record, "announced")),
                title=_str(record, "title"),
                authors=tuple(_str_list(record, "authors")),
                primary_subject=_optional_str(record, "primary_subject"),
                subjects=tuple(_str_list(record, "subjects")),
                comments=_optional_str(record, "comments"),
                journal_ref=_optional_str(record, "journal_ref"),
                venue=_optional_str(record, "venue"),
                cross_list_from=_optional_str(record, "cross_list_from"),
                html_url=_optional_str(record, "html_url"),
                abstract=_optional_str(record, "abstract"),
                affiliations=None if affiliations is None else tuple(affiliations),
                author_affiliations=author_affiliations,
                institutions=institutions,
            )
        except (KeyError, TypeError, ValueError) as exc:
            msg = f"Invalid paper record {record.get('arxiv_id')!r}: {exc}"
            raise StoreError(msg) from exc


@dataclass(frozen=True, slots=True)
class Listing:
    """Papers parsed from an arXiv listing page.

    Attributes:
        papers: Papers in page order (most recent announcement day first).
        total: Number of entries the page claims to contain, if stated.
    """

    papers: tuple[Paper, ...]
    total: int | None = None

    @property
    def is_complete(self) -> bool:
        """Whether every entry announced by the page was parsed."""
        return self.total is None or self.total == len(self.papers)


def _str(record: Mapping[str, object], key: str) -> str:
    value = record[key]
    if not isinstance(value, str):
        msg = f"{key!r} must be a string, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def _optional_str(record: Mapping[str, object], key: str) -> str | None:
    return None if record.get(key) is None else _str(record, key)


def _str_list(record: Mapping[str, object], key: str) -> list[str]:
    value = record[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        msg = f"{key!r} must be a list of strings"
        raise TypeError(msg)
    return [str(item) for item in value]


def _optional_str_list(record: Mapping[str, object], key: str) -> list[str] | None:
    return None if record.get(key) is None else _str_list(record, key)


def _optional_nullable_str_list(record: Mapping[str, object], key: str) -> tuple[str | None, ...] | None:
    """Parse a list of strings where both the whole and each entry may be ``None``."""
    value = record.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or not all(item is None or isinstance(item, str) for item in value):
        msg = f"{key!r} must be a list of strings or null"
        raise TypeError(msg)
    return tuple(value)


def _institutions(
    record: Mapping[str, object], affiliations: list[str] | None
) -> tuple[str | None, ...] | None:
    """Parse the institutions, which must match the affiliations one to one."""
    institutions = _optional_nullable_str_list(record, "institutions")
    if institutions is not None and (affiliations is None or len(institutions) != len(affiliations)):
        msg = "'institutions' must have one entry per affiliation"
        raise ValueError(msg)
    return institutions


def _optional_index_lists(
    record: Mapping[str, object], key: str
) -> tuple[tuple[int, ...] | None, ...] | None:
    """Parse a list of index lists where both the whole and each entry may be ``None``."""
    value = record.get(key)
    if value is None:
        return None
    if not isinstance(value, list):
        msg = f"{key!r} must be a list, got {type(value).__name__}"
        raise TypeError(msg)
    entries: list[tuple[int, ...] | None] = []
    for entry in value:
        if entry is None:
            entries.append(None)
        elif isinstance(entry, list) and all(isinstance(index, int) for index in entry):
            entries.append(tuple(entry))
        else:
            msg = f"{key!r} entries must be lists of integers or null"
            raise TypeError(msg)
    return tuple(entries)
