"""Extract front matter (affiliations, abstract) from arXiv HTML renderings (LaTeXML output).

The HTML front matter depends on the LaTeX class used by the authors, so the mapping
from authors to affiliations cannot be recovered reliably. We therefore extract the
paper-level set of affiliations, which is what search and filtering need.
"""

import logging
import re
from collections.abc import Collection
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

from preprint_radar.exceptions import NotFoundError
from preprint_radar.http import HttpClient

logger = logging.getLogger(__name__)

# LaTeXML renders line breaks and \quad between affiliations as newlines, em spaces
# or runs of (non-breaking) spaces.
_SEPARATOR_RE = re.compile(r"\n|\u2003|\s{2,}")
# Contact details and footnotes that are not affiliations.
_NOISE_RE = re.compile(
    r"@|https?://|www\.|equal(ly)? contribut|contributed equally|corresponding author|work done|project lead",
    re.IGNORECASE,
)
# Leading footnote markers: "1 Cornell University", "* MIT", "†‡ NVIDIA".
_LEADING_MARKER_RE = re.compile(r"^[\d\s*†‡§¶,]+")
# Numbered affiliation lines in free-form author blocks (CVPR-like classes): "1ETH Zurich".
_NUMBERED_LINE_RE = re.compile(r"^\s*\d{1,2}\s*(?P<name>[A-Z].{2,})$", re.MULTILINE)
_SPACE_BEFORE_PUNCTUATION_RE = re.compile(r"\s+([,;])")
_EDGE_PUNCTUATION = " ,;:."
_MIN_LENGTH = 3


@dataclass(frozen=True, slots=True)
class FrontMatter:
    """Information extracted from the first page of a paper.

    Attributes:
        affiliations: Distinct affiliations, in order of first appearance (possibly empty).
        abstract: Abstract with math as ``$LaTeX$``, or ``None`` if not found.
    """

    affiliations: tuple[str, ...] = ()
    abstract: str | None = None


def fetch_front_matter(client: HttpClient, html_url: str, *, authors: Collection[str] = ()) -> FrontMatter:
    """Download an HTML rendering and extract its front matter.

    Args:
        client: HTTP client, rate-limited according to arxiv.org's crawl delay.
        html_url: URL of the paper's HTML rendering.
        authors: Author names, never reported as affiliations.

    Returns:
        The front matter; empty if the rendering does not exist.

    Raises:
        FetchError: If the page cannot be retrieved for a reason other than a 404.
    """
    try:
        html = client.get_text(html_url)
    except NotFoundError:
        logger.info("No HTML rendering at %s", html_url)
        return FrontMatter()
    return parse_front_matter(html, authors=authors)


def parse_front_matter(html: str, *, authors: Collection[str] = ()) -> FrontMatter:
    """Extract affiliations and abstract from a paper's HTML rendering.

    Contact details (e-mails, URLs) are discarded from affiliations so they are never
    republished.

    Args:
        html: Raw HTML of the paper.
        authors: Author names; free-form author blocks can make a name look like an
            affiliation, so these are filtered out.

    Returns:
        The front matter.
    """
    soup = BeautifulSoup(html, "html.parser")
    names = {author.casefold() for author in authors}
    affiliations = tuple(a for a in _affiliations(soup) if a.casefold() not in names)
    return FrontMatter(affiliations=affiliations, abstract=_abstract(soup))


def _abstract(soup: BeautifulSoup) -> str | None:
    node = soup.select_one("div.ltx_abstract")
    if node is None:
        return None
    for title in node.select(".ltx_title"):
        title.decompose()
    # Render MathML the way arXiv metadata does, as inline LaTeX.
    for math in node.select("math[alttext]"):
        math.replace_with(f"${math['alttext']}$")
    return " ".join(node.get_text().split()) or None


def _affiliations(soup: BeautifulSoup) -> tuple[str, ...]:
    """Distinct affiliations listed in the author block, deduplicated case-insensitively."""
    authors = soup.select_one("div.ltx_authors")
    if authors is None:
        return ()
    for noise in authors.select(".ltx_role_email, .ltx_contact_name, .ltx_note, a"):
        noise.decompose()
    return _dedupe(_tagged_affiliations(authors) or _numbered_affiliations(authors))


def _tagged_affiliations(authors: Tag) -> list[str]:
    """Affiliations explicitly marked up by LaTeXML (the affiliation macros of ACM-like classes)."""
    parts: list[str] = []
    for node in authors.select(".ltx_role_affiliation"):
        for marker in node.select("sup"):
            marker.decompose()
        parts.extend(_SEPARATOR_RE.split(node.get_text()))
    return parts


def _numbered_affiliations(authors: Tag) -> list[str]:
    """Affiliations written as numbered lines after the author names.

    Superscript markers are kept here: they are what identifies these lines.
    """
    text = authors.get_text().replace("\xa0", " ")
    return [match.group("name") for match in _NUMBERED_LINE_RE.finditer(text)]


def _dedupe(candidates: list[str]) -> tuple[str, ...]:
    seen: dict[str, str] = {}
    for candidate in candidates:
        if affiliation := _clean(candidate):
            seen.setdefault(affiliation.casefold(), affiliation)
    return tuple(seen.values())


def _clean(text: str) -> str | None:
    text = text.replace("\xa0", " ")
    if _NOISE_RE.search(text):
        return None
    text = _SPACE_BEFORE_PUNCTUATION_RE.sub(r"\1", " ".join(text.split()))
    text = _LEADING_MARKER_RE.sub("", text).strip(_EDGE_PUNCTUATION)
    if len(text) < _MIN_LENGTH or not any(char.isalpha() for char in text):
        return None
    return text
