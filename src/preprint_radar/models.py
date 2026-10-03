"""Domain models."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Self

from preprint_radar.exceptions import StoreError

ARXIV_BASE_URL = "https://arxiv.org"

type PaperRecord = dict[str, str | int | list[str] | list[str | None] | list[list[int] | None] | None]
"""JSON-serializable representation of a :class:`Paper`."""


@dataclass(frozen=True, slots=True)
class Institution:
    """An organization of the Research Organization Registry, as a source names it.

    Attributes:
        name: Its name, tidied for display (``sources.ror.organization_name``).
        ror_id: Its ROR id, the last part of ``https://ror.org/<id>``, when the source gives it.
    """

    name: str
    ror_id: str | None = None


@dataclass(frozen=True, slots=True)
class ScholarRecord:
    """What Semantic Scholar knows of a paper beyond its count (``scholar.json``).

    Attributes:
        doi: DOI of the published version (not arXiv's ``10.48550/...``), if any.
        venue: Where it was published, as ``venue.published_venue`` names it
            ("CVPR 2018", "Information Fusion 2024"), if any.
        author_ids: Semantic Scholar's id of each author, in order (``None`` for an author
            it has none for); ``None`` altogether when its author list is not the paper's.
    """

    doi: str | None = None
    venue: str | None = None
    author_ids: tuple[str | None, ...] | None = None

    def is_empty(self) -> bool:
        """Whether Semantic Scholar said nothing of use."""
        return self.doi is None and self.venue is None and self.author_ids is None

    def to_record(self) -> dict[str, object]:
        """The record, without its absent fields."""
        record: dict[str, object] = {}
        if self.doi is not None:
            record["doi"] = self.doi
        if self.venue is not None:
            record["venue"] = self.venue
        if self.author_ids is not None:
            record["author_ids"] = list(self.author_ids)
        return record

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> Self:
        """Rebuild a record written by :meth:`to_record`.

        Raises:
            TypeError: If a field has the wrong type.
        """
        return cls(
            doi=_optional_str(record, "doi"),
            venue=_optional_str(record, "venue"),
            author_ids=_optional_nullable_str_list(record, "author_ids"),
        )


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
        institution_ids: The ROR id of each institution ("03vek6s52"), parallel to
            ``institutions``; ``None`` altogether for institutions named before ids were
            kept, and always when ``institutions`` is.
        extractor: Version of the HTML extraction that gave the affiliations
            (``sources.arxiv_html.EXTRACTOR_VERSION``); ``None`` when they came from
            elsewhere (the API, OpenAlex) or were read before versions were kept.
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
    institution_ids: tuple[str | None, ...] | None = None
    extractor: int | None = None

    def __post_init__(self) -> None:
        """Check that the lists indexing ``affiliations`` line up with it and with ``authors``.

        Raises:
            ValueError: If ``institutions`` (or ``institution_ids``, which needs it) does not
                have one entry per affiliation, or ``author_affiliations`` one entry per
                author, with indices into ``affiliations``.
        """
        count = None if self.affiliations is None else len(self.affiliations)
        if self.institutions is not None and len(self.institutions) != count:
            msg = "'institutions' must have one entry per affiliation"
            raise ValueError(msg)
        if self.institution_ids is not None and (
            self.institutions is None or len(self.institution_ids) != count
        ):
            msg = "'institution_ids' must have one entry per institution"
            raise ValueError(msg)
        if self.author_affiliations is None:
            return
        if len(self.author_affiliations) != len(self.authors):
            msg = "'author_affiliations' must have one entry per author"
            raise ValueError(msg)
        indices = [index for entry in self.author_affiliations if entry is not None for index in entry]
        if indices and (count is None or not all(0 <= index < count for index in indices)):
            msg = "'author_affiliations' must only hold indices into 'affiliations'"
            raise ValueError(msg)

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
            # Written only when known, so that records read before them stay as they were.
            **({} if self.institution_ids is None else {"institution_ids": list(self.institution_ids)}),
            **({} if self.extractor is None else {"extractor": self.extractor}),
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
                author_affiliations=_optional_index_lists(record, "author_affiliations"),
                institutions=_optional_nullable_str_list(record, "institutions"),
                institution_ids=_optional_nullable_str_list(record, "institution_ids"),
                extractor=_optional_int(record, "extractor"),
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


def _optional_int(record: Mapping[str, object], key: str) -> int | None:
    value = record.get(key)
    if value is None:
        return None
    # bool is an int to Python, not to the contract.
    if not isinstance(value, int) or isinstance(value, bool):
        msg = f"{key!r} must be an integer"
        raise TypeError(msg)
    return value


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
        # JSON booleans load as bool, a subclass of int: they are not indices.
        elif isinstance(entry, list) and all(
            isinstance(index, int) and not isinstance(index, bool) for index in entry
        ):
            entries.append(tuple(entry))
        else:
            msg = f"{key!r} entries must be lists of integers or null"
            raise TypeError(msg)
    return tuple(entries)
