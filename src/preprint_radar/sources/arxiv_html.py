"""Extract front matter (affiliations, abstract) from arXiv HTML renderings (LaTeXML output).

The HTML front matter depends on the LaTeX class used by the authors. The paper-level set
of affiliations is extracted first (what search and filtering need); when the page also
says who is where — one affiliation block per author, superscript markers, or "A is with
B" notes — each author is additionally mapped to their own affiliations.
"""

import gzip
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from preprint_radar.affiliations.cleaning import (
    clean_affiliation,
    clean_affiliations,
    has_contact,
    is_bare_unit,
    is_place,
    marked_pieces,
    names_only_authors,
    states_people,
)
from preprint_radar.affiliations.folding import name_key
from preprint_radar.affiliations.mapping import (
    AuthorAffiliations,
    _author_affiliations,
    map_stated_affiliations,
)
from preprint_radar.affiliations.sources import _affiliations
from preprint_radar.affiliations.vocabulary import (
    _ANNOTATION_RE,
    _GLUED_ADDRESS_RE,
    _LINE_BREAK_RE,
    _RAISED_MARKER_RE,
    _RAISED_RE,
    _TEMPLATE_EXAMPLE_RE,
    COUNTRIES,
)
from preprint_radar.exceptions import NotFoundError
from preprint_radar.http import HttpClient
from preprint_radar.latex import plain_text

__all__ = [
    "AR5IV_HTML_URL",
    "ARXIV_HTML_URL",
    "COUNTRIES",
    "EXTRACTOR_VERSION",
    "AuthorAffiliations",
    "FrontMatter",
    "PageCache",
    "archive_page_url",
    "clean_affiliation",
    "clean_affiliations",
    "fetch_front_matter",
    "first_version_url",
    "front_matter_html",
    "has_contact",
    "is_bare_unit",
    "is_place",
    "logger",
    "map_stated_affiliations",
    "marked_pieces",
    "name_key",
    "names_only_authors",
    "parse_front_matter",
    "states_people",
]

logger = logging.getLogger(__name__)

EXTRACTOR_VERSION = 24
"""Version of the extraction heuristics, stored with the affiliations they give.

Bump it with any change that alters what a page gives (affiliations, author mapping), so
that ``reextract`` knows which stored papers to read again; ``docs/extraction.md`` keeps
what each version changed.
"""


@dataclass(frozen=True, slots=True)
class FrontMatter:
    """Information extracted from the first page of a paper.

    Attributes:
        affiliations: Distinct affiliations, in order of first appearance (possibly empty).
        abstract: Abstract with math as ``$LaTeX$``, or ``None`` if not found.
        author_affiliations: For each author given to the parser, the indices of their own
            affiliations in ``affiliations``; ``None`` for an author the page does not
            place, and ``None`` altogether when the page never says who is where.
    """

    affiliations: tuple[str, ...] = ()
    abstract: str | None = None
    author_affiliations: AuthorAffiliations | None = None


class PageCache:
    """The front matter of every HTML page read, so that extracting again reads no page.

    One gzipped file per paper version (``<directory>/2609/2609.30249v1.html.gz``), and per
    paper for ar5iv's renderings, of a paper's latest version (``1703/1703.06870.html.gz``),
    holding :func:`front_matter_html` of the page: 1 or 2 KB instead of hundreds. A new version of
    a paper is a new page, read again. A page that does not exist (404) leaves an empty
    ``.missing`` file instead, which the archive's pages skip (:meth:`missing`).
    """

    def __init__(self, directory: Path) -> None:
        """Keep the pages in ``directory`` (created on first write)."""
        self.directory = directory

    def __contains__(self, html_url: object) -> bool:
        """Whether the cache holds the page at ``html_url``."""
        path = self._path(html_url) if isinstance(html_url, str) else None
        return path is not None and path.is_file()

    def get(self, html_url: str) -> str | None:
        """The cached front matter of the page at ``html_url``, if any."""
        path = self._path(html_url)
        if path is None or not path.is_file():
            return None
        return gzip.decompress(path.read_bytes()).decode("utf-8")

    def put(self, html_url: str, html: str) -> None:
        """Keep the front matter of the page at ``html_url``, whose HTML is ``html``.

        Args:
            html_url: URL of the paper's HTML rendering, which names the cached file.
            html: The page's HTML, of which only the front matter is kept.
        """
        path = self._path(html_url)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        # Written aside then renamed, so that a killed run never leaves a truncated page.
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(gzip.compress(front_matter_html(html).encode("utf-8"), mtime=0))
        tmp.replace(path)

    def missing(self, html_url: str) -> bool:
        """Whether arXiv answered that the page at ``html_url`` does not exist (:meth:`put_missing`)."""
        path = self._path(html_url)
        return path is not None and path.with_suffix(".missing").is_file()

    def put_missing(self, html_url: str) -> None:
        """Remember that the page at ``html_url`` does not exist: arXiv could not render it."""
        path = self._path(html_url)
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.with_suffix(".missing").touch()

    def stale(self, html_url: str) -> bool:
        """Whether the page at ``html_url`` was kept with less than its front matter.

        Kept before the front matter kept its tables, a page lost those of its author block,
        which some classes lay names and affiliations out in (2609.06629); kept before a list
        of acronyms set before the title was skipped, it lost everything (2610.09677). Read
        again, either may give fewer affiliations than the page has.
        """
        html = self.get(html_url)
        # A page without a document was kept whole, and lost nothing.
        return (
            html is not None
            and "ltx_document" in html
            and (
                _front_matter_version(html) < _TABLES_KEPT or _EMPTY_FRONT_MATTER_RE.search(html) is not None
            )
        )

    def doubtful(self, html_url: str) -> bool:
        """Whether the page at ``html_url`` may have been kept with less than its front matter.

        :meth:`stale`, or kept before a figure holding the author block stayed, without an
        author block: 2503.22976 sets its title, authors and abstract in a teaser figure,
        which the front matter dropped, and read again from the cache, it lost its two
        affiliations. Many pages have no author block, so this is only a doubt: a paper the
        page gives no affiliation keeps those it has, and the page is downloaded again.
        """
        html = self.get(html_url)
        return self.stale(html_url) or (
            html is not None
            and "ltx_document" in html
            and _front_matter_version(html) < _FRONT_MATTER_VERSION
            and "ltx_authors" not in html
        )

    def discard(self, html_url: str) -> None:
        """Forget the page at ``html_url``, so that it is downloaded again next time."""
        path = self._path(html_url)
        if path is not None:
            path.unlink(missing_ok=True)

    def _path(self, html_url: str) -> Path | None:
        """``<directory>/<yymm>/<id>v<version>.html.gz``, ar5iv's ``<id>.html.gz``; else ``None``."""
        match = _CACHE_KEY_RE.search(html_url) or _AR5IV_KEY_RE.search(html_url)
        return (
            None
            if match is None
            else self.directory / match["month"] / f"{html_url.rsplit('/', 1)[-1]}.html.gz"
        )


ARXIV_HTML_URL = "https://arxiv.org/html"
AR5IV_HTML_URL = "https://ar5iv.labs.arxiv.org/html"
_NEW_STYLE_ID_RE = re.compile(r"\d{4}\.\d{4,5}")
# The month of the first papers arXiv rendered in HTML.
_FIRST_RENDERED_MONTH = "2312"
_CACHE_KEY_RE = re.compile(r"(?P<month>\d{4})\.\d{4,5}v\d+$")
# ar5iv renders a paper's latest version, under its identifier alone.
_AR5IV_KEY_RE = re.compile(rf"^{re.escape(AR5IV_HTML_URL)}/(?P<month>\d{{4}})\.\d{{4,5}}$")
# What follows the front matter in a LaTeXML document: the body, references and appendices.
_BODY_CLASSES = frozenset({"ltx_section", "ltx_bibliography", "ltx_appendix"})
# Sections a document may set before its title: a list of acronyms or a glossary
# (2610.09677, 2610.11653), not the body the front matter ends at.
_PREAMBLE_CLASSES = frozenset({"ltx_glossary"})
# Figures and tables say nothing of affiliations, and are most of a front matter's size;
# but for the tables of the author block.
_FIGURE_TAGS = ("figure", "img", "svg", "table")
_FIGURE_CLASSES = frozenset({"ltx_figure", "ltx_table"})
# What a front matter says of itself: version 2 kept the tables of its author block
# (2026-10-06), 3 a figure holding the author block (2026-10-29).
_TABLES_KEPT = 2
_FRONT_MATTER_VERSION = 3
_FRONT_MATTER_MARK = f'data-front-matter="{_FRONT_MATTER_VERSION}"'
_FRONT_MATTER_MARK_RE = re.compile(r'data-front-matter="(\d+)"')
# A front matter that kept nothing: every document has a title at least.
_EMPTY_FRONT_MATTER_RE = re.compile(r'data-front-matter="\d+">\s*</article>')


def front_matter_html(html: str) -> str:
    """The part of an HTML rendering that :func:`parse_front_matter` reads, as a page.

    The children of the document before its first section (title, author block and its
    notes, footnotes, abstract), without figures or tables: what the cache keeps. The
    tables of the author block stay: some classes lay names and affiliations out in one
    (2609.06629, whose five affiliations a cached page had lost). A list of acronyms set
    before the title is no first section: the pages of 2610.09677 and 2610.11653 were kept
    empty, and read again from the cache, lost their affiliations. A figure holding the
    author block stays, without its images: 2503.22976 sets its title, authors and abstract
    in a teaser figure, and lost them all.
    """
    soup = BeautifulSoup(html, "html.parser")
    article = soup.select_one("article.ltx_document")
    if article is None:
        return html
    kept: list[str] = []
    for child in article.children:
        if isinstance(child, Tag):
            classes = set(child.get_attribute_list("class"))
            if _PREAMBLE_CLASSES & classes:
                continue
            if child.name == "section" or _BODY_CLASSES & classes:
                break
            if (child.name in _FIGURE_TAGS or _FIGURE_CLASSES & classes) and not child.select_one(
                ".ltx_authors"
            ):
                continue
            for noise in child.select(", ".join([*_FIGURE_TAGS, *(f".{name}" for name in _FIGURE_CLASSES)])):
                kept_table = noise.name == "table" and noise.find_parent(class_="ltx_authors") is not None
                if not kept_table and not noise.select_one(".ltx_authors"):
                    noise.decompose()
        kept.append(str(child))
    article_tag = f'<article class="ltx_document" {_FRONT_MATTER_MARK}>'
    return f"<html><body>{article_tag}{''.join(kept)}</article></body></html>"


def _front_matter_version(html: str) -> int:
    """The version of :func:`front_matter_html` a cached page was kept by, 0 before versions (DATA-1)."""
    match = _FRONT_MATTER_MARK_RE.search(html)
    return int(match.group(1)) if match else 0


def first_version_url(arxiv_id: str) -> str | None:
    """The HTML rendering of a paper's first version, ``None`` before arXiv rendered any.

    arXiv renders the papers submitted since December 2023 (``2312.*``): the first version
    is the one a day file links to for a new paper. Older ones have no rendering, nor have
    old-style identifiers ("cs/0112017").
    """
    if not _NEW_STYLE_ID_RE.fullmatch(arxiv_id) or arxiv_id < _FIRST_RENDERED_MONTH:
        return None
    return f"{ARXIV_HTML_URL}/{arxiv_id}v1"


def archive_page_url(arxiv_id: str) -> str | None:
    """The page a highly cited paper's affiliations are read from, ``None`` without one.

    Its first version's rendering on arXiv (:func:`first_version_url`), else ar5iv's (arXiv
    Labs), which renders the papers before December 2023 with the same LaTeXML, their
    latest version: the same extraction reads it ("Facebook AI Research (FAIR)" for Mask
    R-CNN, 1703.06870, which OpenAlex left without any; AFF-37). ar5iv's ``robots.txt``
    disallows ``/log/`` alone. Old-style identifiers ("cs/0112017") have neither.
    """
    if (url := first_version_url(arxiv_id)) is not None:
        return url
    return f"{AR5IV_HTML_URL}/{arxiv_id}" if _NEW_STYLE_ID_RE.fullmatch(arxiv_id) else None


def fetch_front_matter(
    client: HttpClient, html_url: str, *, authors: Sequence[str] = (), cache: PageCache | None = None
) -> FrontMatter:
    """Download an HTML rendering, or take it from the cache, and extract its front matter.

    Args:
        client: HTTP client, rate-limited according to arxiv.org's crawl delay.
        html_url: URL of the paper's HTML rendering.
        authors: Author names, never reported as affiliations.
        cache: Pages read before; a page downloaded is added to it.

    Returns:
        The front matter; empty if the rendering does not exist.

    Raises:
        FetchError: If the page cannot be retrieved for a reason other than a 404.
    """
    html = cache.get(html_url) if cache is not None else None
    if html is None:
        try:
            html = client.get_text(html_url)
        except NotFoundError:
            logger.info("No HTML rendering at %s", html_url)
            if cache is not None:
                cache.put_missing(html_url)
            return FrontMatter()
        if cache is not None:
            cache.put(html_url, html)
    return parse_front_matter(html, authors=authors)


def parse_front_matter(html: str, *, authors: Sequence[str] = ()) -> FrontMatter:
    """Extract affiliations, abstract and the author-affiliation mapping from a rendering.

    Contact details (e-mails, URLs) are discarded from affiliations so they are never
    republished.

    Args:
        html: Raw HTML of the paper.
        authors: Author names, in the paper's order. They anchor the author-affiliation
            mapping, and names are never reported as affiliations (see
            :func:`names_only_authors`).

    Returns:
        The front matter.
    """
    html = _GLUED_ADDRESS_RE.sub(" ", _ANNOTATION_RE.sub("", _LINE_BREAK_RE.sub("\n", html)))
    html = _raised_markers_as_superscripts(html)
    soup = BeautifulSoup(html, "html.parser")
    if _without_template_authors(soup):
        html = str(soup)
    affiliations, partial = _affiliations(soup, authors)
    return FrontMatter(
        affiliations=affiliations,
        abstract=_abstract(soup),
        author_affiliations=_author_affiliations(html, tuple(authors), affiliations, partial=partial),
    )


def _without_template_authors(soup: BeautifulSoup) -> bool:
    """Drop the creators of a template's example authors (``_TEMPLATE_EXAMPLE_RE``), if any.

    NeurIPS's "David S. Hippocampus" comes with "Department of Computer Science" and
    "Pittsburgh, PA 15213" beside his Cranberry-Lemon University, which every tier would
    otherwise read as the paper's (2502.10841, 2610.27759).

    Returns:
        Whether one was dropped.
    """
    examples = [
        creator
        for creator in soup.select("span.ltx_creator")
        if _TEMPLATE_EXAMPLE_RE.search(creator.get_text())
    ]
    for creator in examples:
        creator.decompose()
    return bool(examples)


def _raised_markers_as_superscripts(html: str) -> str:
    """The page with each marker raised by a span's style written as a superscript (``_RAISED_RE``)."""
    if "bottom:" not in html:
        return html
    soup = BeautifulSoup(html, "html.parser")
    raised = [
        span
        for span in soup.select('span[style*="bottom:"]')
        if _RAISED_RE.search(str(span.get("style", "")))
        and _RAISED_MARKER_RE.fullmatch(span.get_text().strip())
    ]
    for span in raised:
        span.name = "sup"
        span.attrs = {"class": "ltx_sup"}
    return str(soup) if raised else html


def _abstract(soup: BeautifulSoup) -> str | None:
    node = soup.select_one("div.ltx_abstract")
    if node is None:
        return None
    for title in node.select(".ltx_title"):
        title.decompose()
    # Render MathML the way arXiv metadata does, as inline LaTeX, then as plain text.
    for math in node.select("math[alttext]"):
        math.replace_with(f"${math['alttext']}$")
    return plain_text(node.get_text()) or None
