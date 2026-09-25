"""Fetch and parse arXiv ``/list/<category>/recent`` pages."""

import logging
import re
from collections.abc import Iterator
from datetime import date, datetime

from bs4 import BeautifulSoup, Tag

from preprint_radar.exceptions import ParseError
from preprint_radar.http import HttpClient
from preprint_radar.models import ARXIV_BASE_URL, Listing, Paper

logger = logging.getLogger(__name__)

MAX_LISTING_ENTRIES = 2000

# Archive with optional subject class: "cs.CV", "astro-ph.CO", "hep-th", "q-bio.NC"...
_CATEGORY_RE = re.compile(r"^[a-z][a-z\-]*(\.[A-Za-z][A-Za-z\-]*)?$")
_DAY_FORMAT = "%a, %d %b %Y"
_TOTAL_RE = re.compile(r"Total of (\d+) entries")
_CROSS_LIST_RE = re.compile(r"cross-list from ([\w.\-]+)")
# arXiv shortens external links in comments to this text; the real URL is in ``href``.
_PLACEHOLDER_LINK_RE = re.compile(r"this https? URL")


def validate_category(category: str) -> str:
    """Check that ``category`` looks like an arXiv category.

    Args:
        category: Category identifier, e.g. ``"cs.CV"``.

    Returns:
        The category, unchanged.

    Raises:
        ValueError: If the category is malformed.
    """
    if not _CATEGORY_RE.fullmatch(category):
        msg = f"Invalid arXiv category: {category!r} (expected something like 'cs.CV')."
        raise ValueError(msg)
    return category


def fetch_listing(client: HttpClient, category: str, *, max_entries: int = MAX_LISTING_ENTRIES) -> Listing:
    """Download and parse the recent listing of a category.

    Args:
        client: HTTP client pointed at arxiv.org.
        category: arXiv category, e.g. ``"cs.CV"``.
        max_entries: Maximum number of entries to request in a single page.

    Returns:
        The parsed listing.

    Raises:
        ValueError: If ``category`` is malformed or ``max_entries`` is out of range.
        FetchError: If the page cannot be retrieved.
        ParseError: If the page does not have the expected structure.
    """
    validate_category(category)
    if not 1 <= max_entries <= MAX_LISTING_ENTRIES:
        msg = f"max_entries must be between 1 and {MAX_LISTING_ENTRIES}, got {max_entries}."
        raise ValueError(msg)

    logger.info("Fetching the recent listing of %s", category)
    html = client.get_text(
        f"{ARXIV_BASE_URL}/list/{category}/recent", params={"skip": 0, "show": max_entries}
    )
    listing = parse_listing(html)
    if not listing.is_complete:
        logger.warning(
            "Parsed %d papers but the %s listing announces %s; try a larger max_entries.",
            len(listing.papers),
            category,
            listing.total,
        )
    return listing


def parse_listing(html: str) -> Listing:
    """Parse an arXiv ``/list/<category>/recent`` page.

    The page contains one ``<dl id="articles">`` section per announcement day. Each
    section starts with an ``<h3>`` holding the date, followed by ``<dt>``/``<dd>`` pairs
    (identifier and links, then metadata).

    Args:
        html: Raw HTML of the listing page.

    Returns:
        The parsed listing.

    Raises:
        ParseError: If the page does not have the expected structure.
    """
    soup = BeautifulSoup(html, "html.parser")
    sections = soup.select("dl#articles")
    if not sections:
        msg = "No 'dl#articles' section found; the arXiv listing layout may have changed."
        raise ParseError(msg)

    papers = tuple(paper for section in sections for paper in _parse_section(section))
    return Listing(papers=papers, total=_parse_total(soup))


def _parse_total(soup: BeautifulSoup) -> int | None:
    paging = soup.select_one("div.paging")
    if paging is None:
        return None
    match = _TOTAL_RE.search(paging.get_text())
    return int(match.group(1)) if match else None


def _parse_section(section: Tag) -> Iterator[Paper]:
    announced = _parse_day(_require(section, "h3").get_text())
    terms = section.select(":scope > dt")
    details = section.select(":scope > dd")
    if len(terms) != len(details):
        msg = f"Mismatched <dt>/<dd> counts ({len(terms)} vs {len(details)}) for {announced}."
        raise ParseError(msg)
    for term, detail in zip(terms, details, strict=True):
        yield _parse_entry(term, detail, announced)


def _parse_day(header: str) -> date:
    # "Fri, 25 Sep 2026 (showing 143 of 143 entries )" -> "Fri, 25 Sep 2026"
    label = header.split("(", maxsplit=1)[0].strip()
    try:
        return datetime.strptime(label, _DAY_FORMAT).date()  # noqa: DTZ007 - a calendar day, not an instant
    except ValueError as exc:
        msg = f"Unrecognized announcement date: {label!r}"
        raise ParseError(msg) from exc


def _parse_entry(term: Tag, detail: Tag, announced: date) -> Paper:
    arxiv_id = _normalize(_require(term, 'a[href^="/abs/"]').get_text()).removeprefix("arXiv:")
    cross_list = _CROSS_LIST_RE.search(term.get_text())
    html_link = term.select_one('a[title="View HTML"][href]')

    title = _field_text(detail, "div.list-title")
    if not title:
        msg = f"Missing title for {arxiv_id}."
        raise ParseError(msg)

    primary = detail.select_one("div.list-subjects span.primary-subject")
    subjects = _field_text(detail, "div.list-subjects") or ""

    return Paper(
        arxiv_id=arxiv_id,
        announced=announced,
        title=title,
        authors=tuple(_normalize(a.get_text()) for a in detail.select("div.list-authors a")),
        primary_subject=_normalize(primary.get_text()) if primary else None,
        subjects=tuple(s.strip() for s in subjects.split(";") if s.strip()),
        comments=_field_text(detail, "div.list-comments"),
        journal_ref=_field_text(detail, "div.list-journal-ref"),
        cross_list_from=cross_list.group(1) if cross_list else None,
        html_url=str(html_link["href"]) if html_link else None,
    )


def _field_text(container: Tag, selector: str) -> str | None:
    """Return the text of a metadata field, without its ``Label:`` descriptor.

    Note:
        This mutates the matched node, which is acceptable since the soup is discarded.
    """
    node = container.select_one(selector)
    if node is None:
        return None
    for descriptor in node.select("span.descriptor"):
        descriptor.decompose()
    for link in node.select("a[href]"):
        if _PLACEHOLDER_LINK_RE.fullmatch(link.get_text(strip=True)):
            link.replace_with(str(link["href"]))
    return _normalize(node.get_text()) or None


def _require(container: Tag, selector: str) -> Tag:
    node = container.select_one(selector)
    if node is None:
        msg = f"Expected an element matching {selector!r}."
        raise ParseError(msg)
    return node


def _normalize(text: str) -> str:
    """Collapse runs of whitespace into single spaces."""
    return " ".join(text.split())
