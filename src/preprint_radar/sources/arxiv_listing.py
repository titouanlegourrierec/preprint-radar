"""Fetch and parse arXiv listing pages.

Two kinds of pages share the same ``<dt>``/``<dd>`` markup for their entries:

- ``/list/<category>/recent`` covers the last few announcement days, without abstracts;
- ``/catchup/<category>/<YYYY-MM-DD>`` covers one announcement day, abstracts included,
  which makes it the way to collect past days.
"""

import logging
import re
from collections.abc import Iterator
from datetime import UTC, date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from preprint_radar.exceptions import ParseError
from preprint_radar.http import HttpClient
from preprint_radar.latex import plain_text
from preprint_radar.models import ARXIV_BASE_URL, Listing, Paper
from preprint_radar.venue import extract_venue
from preprint_radar.withdrawal import is_withdrawn

logger = logging.getLogger(__name__)

MAX_LISTING_ENTRIES = 2000

# Archive with optional subject class: "cs.CV", "astro-ph.CO", "hep-th", "q-bio.NC"...
_CATEGORY_RE = re.compile(r"^[a-z][a-z\-]*(\.[A-Za-z][A-Za-z\-]*)?$")
_DAY_FORMAT = "%a, %d %b %Y"
_TOTAL_RE = re.compile(r"Total of (\d+) entries")
_CROSS_LIST_RE = re.compile(r"cross-list from ([\w.\-]+)")
# Catchup page title: "Catchup results for Computer Vision ... on Tue, 01 Sep 2026".
_CATCHUP_TITLE_RE = re.compile(r"\bon (?P<day>\w{3}, \d{1,2} \w{3} \d{4})\s*$")
# Catchup section heading: "New submissions (showing 111 of 111 entries)".
_SHOWING_RE = re.compile(r"showing \d+ of (\d+) entries")
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
        f"{ARXIV_BASE_URL}/list/{category}/recent",
        # A parameter arXiv ignores, new at each request: its cache served this page hours
        # old on 2026-10-15 (`age: 16802`), without the day announced late that night.
        params={"skip": 0, "show": max_entries, "fresh": datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")},
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


def fetch_catchup(client: HttpClient, category: str, day: date) -> Listing:
    """Download and parse the catchup page of one announcement day, with abstracts.

    Args:
        client: HTTP client pointed at arxiv.org.
        category: arXiv category, e.g. ``"cs.CV"``.
        day: Announcement day. Days without an announcement (weekends, holidays) give an
            empty listing.

    Returns:
        The new submissions and cross-lists announced that day.

    Raises:
        ValueError: If ``category`` is malformed.
        FetchError: If the page cannot be retrieved.
        ParseError: If the page does not have the expected structure.
    """
    validate_category(category)
    logger.info("Fetching the %s catchup page of %s", category, day.isoformat())
    html = client.get_text(f"{ARXIV_BASE_URL}/catchup/{category}/{day.isoformat()}", params={"abs": "True"})
    listing = parse_catchup(html)
    if not listing.is_complete:
        logger.warning(
            "Parsed %d papers but the %s catchup page of %s announces %s.",
            len(listing.papers),
            category,
            day.isoformat(),
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


def parse_catchup(html: str) -> Listing:
    """Parse an arXiv ``/catchup/<category>/<YYYY-MM-DD>`` page.

    The page covers the announcement day named in its ``<h1>``. It has one
    ``<dl id="articles">`` section per kind of announcement, each starting with an
    ``<h3>`` such as "New submissions (showing 111 of 111 entries)". New submissions and
    cross-lists are kept; replacements (new versions of older papers) are skipped, as the
    recent listing does. A day without announcement has no section at all.

    Args:
        html: Raw HTML of the catchup page.

    Returns:
        The parsed listing, with abstracts when the page was requested with ``abs=True``.

    Raises:
        ParseError: If the page does not have the expected structure.
    """
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one("#dlpage h1")
    match = _CATCHUP_TITLE_RE.search(title.get_text()) if title else None
    if match is None:
        msg = "No dated catchup title found; the arXiv catchup layout may have changed."
        raise ParseError(msg)
    announced = _parse_day(match.group("day"))

    papers: list[Paper] = []
    totals: list[int | None] = []
    for section in soup.select("dl#articles"):
        heading = _normalize(_require(section, "h3").get_text())
        kind = heading.lower()
        if kind.startswith("replacement"):
            continue
        if not kind.startswith(("new", "cross")):
            msg = f"Unexpected catchup section {heading!r}; the arXiv catchup layout may have changed."
            raise ParseError(msg)
        showing = _SHOWING_RE.search(heading)
        totals.append(int(showing.group(1)) if showing else None)
        papers.extend(_parse_entries(section, announced))
    total = None if None in totals else sum(count for count in totals if count is not None)
    return Listing(papers=tuple(papers), total=total)


def _parse_total(soup: BeautifulSoup) -> int | None:
    paging = soup.select_one("div.paging")
    if paging is None:
        return None
    match = _TOTAL_RE.search(paging.get_text())
    return int(match.group(1)) if match else None


def _parse_section(section: Tag) -> Iterator[Paper]:
    yield from _parse_entries(section, _parse_day(_require(section, "h3").get_text()))


def _parse_entries(section: Tag, announced: date) -> Iterator[Paper]:
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


def _html_url(link: Tag | None) -> str | None:
    """The paper's HTML page, resolved against arXiv, and only there (SEC-2).

    The site renders it as a link: another scheme or host from the page would reach readers.
    """
    if link is None:
        return None
    url = urljoin(f"{ARXIV_BASE_URL}/", str(link["href"]))
    return url if url.startswith(f"{ARXIV_BASE_URL}/html/") else None


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
    comments = _field_text(detail, "div.list-comments")
    journal_ref = _field_text(detail, "div.list-journal-ref")
    # Only catchup pages requested with ``abs=True`` show abstracts.
    abstract = _field_text(detail, "p.mathjax")

    return Paper(
        arxiv_id=arxiv_id,
        announced=announced,
        title=title,
        authors=tuple(_normalize(a.get_text()) for a in detail.select("div.list-authors a")),
        primary_subject=_normalize(primary.get_text()) if primary else None,
        subjects=tuple(s.strip() for s in subjects.split(";") if s.strip()),
        comments=comments,
        journal_ref=journal_ref,
        venue=extract_venue(comments, journal_ref),
        withdrawn=is_withdrawn(comments),
        cross_list_from=cross_list.group(1) if cross_list else None,
        html_url=_html_url(html_link),
        abstract=plain_text(abstract) if abstract else None,
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
