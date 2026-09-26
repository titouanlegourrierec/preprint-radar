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
    r"@|https?://|www\.|equal(ly)? contribut|contributed equally|corresponding author|work done|project lead"
    r"|senior author|first author|co-first|joint first|equal advising|internship",
    re.IGNORECASE,
)
# Contact details after an affiliation: "..., USA. email: {a, b}@nyu.edu" or "(e-mail: ...)".
_CONTACT_TAIL_RE = re.compile(r"\(?\s*\be-?mails?\b.*$", re.IGNORECASE | re.DOTALL)
# IEEE-style footnotes put in the affiliation macro: "The authors are with Delft University".
_AUTHORS_ARE_WITH_RE = re.compile(
    r"^(?:the\s+)?authors?\s+(?:are|is)\s+(?:with|at|affiliated\s+with)\s+(?:the\s+)?",
    re.IGNORECASE,
)
# IEEE-style acknowledgment notes: "A. Author and B. Author are with the Department of X".
_IS_WITH_RE = re.compile(
    r"\b(?:is|are)\s+(?:also\s+|now\s+|currently\s+)?(?:with|at|affiliated\s+with)\s+(?:the\s+)?",
    re.IGNORECASE,
)
# Sentences that follow an affiliation in acknowledgment notes.
_NEXT_SENTENCE_RE = re.compile(
    r"\.\s+(?=(?:This|These|The\s+work|Corresponding|Manuscript|He|She|They|We|Our|Work|Part|Funding|Supported)\b)"
)
# Leading footnote markers: "1 Cornell University", "* MIT", "†‡ NVIDIA".
_LEADING_MARKER_RE = re.compile(r"^[\d\s*†‡§¶⋆,]+")
# Conjunctions left over when a line break splits "A University and B Institute".
_CONNECTOR_RE = re.compile(r"^(?:and|&)(?:\s+|$)", re.IGNORECASE)
# A line that ends like this continues on the next one ("School of Medicine, and").
_CONTINUED_RE = re.compile(r"(?:,|\band|&)\s*$", re.IGNORECASE)
# Numbered affiliation lines in free-form author blocks (CVPR-like classes): "1ETH Zurich".
_NUMBERED_LINE_RE = re.compile(r"^\s*\d{1,2}\s*(?P<name>[A-Z].{2,})$", re.MULTILINE)
_INSTITUTION_WORD_RE = re.compile(
    r"univ|institut|college|school|lab|cent(?:er|re)|hospital|academy|\binc\b|\bltd\b|gmbh|corp|company"
    r"|research|department|faculty|foundation|technolog|polytechn",
    re.IGNORECASE,
)
# A line that ends with a country, as in "Munich, Germany" or "CA 94720, USA".
_COUNTRY_END_RE = re.compile(
    r"(?:^|,\s*|\s)(?:USA|U\.S\.A?\.?|United States(?: of America)?|UK|U\.K\.|United Kingdom|England|Scotland"
    r"|(?:P\.?\s?R\.?\s?)?China|Hong Kong(?: SAR)?|Macau|Macao|Taiwan|Japan|(?:South |Republic of )?Korea"
    r"|Singapore|India|Germany|France|Italy|Spain|Portugal|(?:The )?Netherlands|Belgium|Switzerland|Austria"
    r"|Sweden|Norway|Denmark|Finland|Ireland|Poland|Czech Republic|Czechia|Hungary|Romania|Greece|Cyprus"
    r"|Turkey|Türkiye|Israel|Iran|Saudi Arabia|United Arab Emirates|UAE|Qatar|Egypt|Morocco|Nigeria"
    r"|South Africa|Canada|Mexico|Brazil|Chile|Argentina|Colombia|Peru|Ecuador|Australia|New Zealand|Russia"
    r"|Ukraine|Vietnam|Viet Nam|Thailand|Malaysia|Indonesia|Philippines|Pakistan|Bangladesh|Luxembourg)\.?$",
    re.IGNORECASE,
)
_MAX_PLACE_LENGTH = 60
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
    """Distinct affiliations of the front matter, deduplicated case-insensitively.

    Sources, from the most to the least reliable: affiliations and addresses marked up in
    the author block, front-matter notes (from the LaTeX address, institute and numbered
    footnotetext macros), numbered lines after the author names, and "A is with B"
    sentences in thanks notes.
    """
    article = soup.select_one("article.ltx_document") or soup
    # Notes are read first: the author block is then cleaned of them.
    from_notes = [
        segment
        for note in soup.select(".ltx_note.ltx_role_address, .ltx_note.ltx_role_institutetext")
        for segment in _note_segments(note)
    ]
    from_notes += [
        segment
        for note in article.find_all("span", class_="ltx_role_footnotetext", recursive=False)
        for segment in _footnote_affiliations(note)
    ]
    thanks = [_note_text(note) for note in soup.select(".ltx_note.ltx_role_thanks")]

    tagged: list[str] = []
    numbered: list[str] = []
    authors = soup.select_one("div.ltx_authors")
    if authors is not None:
        for noise in authors.select(".ltx_role_email, .ltx_contact_name, .ltx_note, a"):
            noise.decompose()
        tagged = _tagged_affiliations(authors)
        numbered = [] if tagged else _numbered_affiliations(authors)
    return _dedupe((tagged + from_notes) or numbered or _thanks_affiliations(thanks))


def _tagged_affiliations(authors: Tag) -> list[str]:
    """Affiliations marked up by LaTeXML: affiliation and address macros of ACM- or IEEE-like classes."""
    return [
        segment
        for node in authors.select(".ltx_role_affiliation, .ltx_role_address")
        for segment in _segments(node)
    ]


def _note_segments(note: Tag) -> list[str]:
    """Affiliations in an address or institute note, e.g. "⋆The University of Tokyo †NII"."""
    content = note.select_one(".ltx_note_content")
    if content is None:
        return []
    for noise in content.select(".ltx_note, .ltx_note_mark, .ltx_note_type"):
        noise.decompose()
    return _segments(content)


def _footnote_affiliations(note: Tag) -> list[str]:
    """Numbered affiliations in a footnote next to the author list, e.g. "¹School of AI, Wuhan University".

    Only footnotes that start with a marker and consist of institutions qualify, as other
    footnotes of the front matter say anything ("This work has been submitted to...").
    """
    content = note.select_one(".ltx_note_content")
    if content is None:
        return []
    for noise in content.select(".ltx_note_mark, .ltx_note_type"):
        noise.decompose()
    first = next((child for child in content.children if not str(child).isspace()), None)
    if not isinstance(first, Tag) or first.name != "sup":
        return []
    segments = _segments(content)
    return segments if all(_INSTITUTION_WORD_RE.search(segment) for segment in segments) else []


def _note_text(note: Tag) -> str:
    content = note.select_one(".ltx_note_content") or note
    for noise in content.select(".ltx_note_mark, .ltx_note_type"):
        noise.decompose()
    return content.get_text()


def _thanks_affiliations(notes: list[str]) -> list[str]:
    """Affiliations stated in thanks notes: "A and B are with the X, Y (e-mail: ...)"."""
    affiliations: list[str] = []
    for line in (line for note in notes for line in note.splitlines()):
        matches = list(_IS_WITH_RE.finditer(line))
        for index, match in enumerate(matches):
            if index + 1 < len(matches):
                # Stop at the sentence that introduces the next people: "..., Spain. C is with".
                text = line[match.end() : matches[index + 1].start()].rsplit(". ", maxsplit=1)[0]
            else:
                text = line[match.end() :]
            affiliations.append(_NEXT_SENTENCE_RE.split(_CONTACT_TAIL_RE.sub("", text), maxsplit=1)[0])
    return affiliations


def _segments(node: Tag) -> list[str]:
    """Candidate affiliations in a node: one per line, footnote marker or wide space.

    A line ending with a comma or "and" continues on the next one, and a line that only
    names a place ("Munich, Germany") belongs to the previous one when it has no country.
    """
    for marker in node.select("sup"):
        marker.replace_with("\n")
    lines = [line.strip() for line in _SEPARATOR_RE.split(node.get_text().replace("\xa0", " "))]
    joined: list[str] = []
    for line in filter(None, lines):
        previous = joined[-1] if joined else ""
        if previous and _CONTINUED_RE.search(previous):
            joined[-1] = f"{previous} {line}"
        elif previous and _is_place(line) and not _COUNTRY_END_RE.search(previous.rstrip(_EDGE_PUNCTUATION)):
            joined[-1] = f"{previous.rstrip(_EDGE_PUNCTUATION)}, {line}"
        else:
            joined.append(line)
    return joined


def _is_place(line: str) -> bool:
    """Whether a line only names a place, like "Munich, Germany" or "CA 94720, USA"."""
    place = line.strip(_EDGE_PUNCTUATION)
    return (
        len(place) <= _MAX_PLACE_LENGTH
        and not _INSTITUTION_WORD_RE.search(place)
        and _COUNTRY_END_RE.search(place) is not None
    )


def _numbered_affiliations(authors: Tag) -> list[str]:
    """Affiliations written as numbered lines after the author names.

    Superscript markers are kept here: they are what identifies these lines.
    """
    text = authors.get_text().replace("\xa0", " ")
    return [match.group("name") for match in _NUMBERED_LINE_RE.finditer(text)]


def _dedupe(candidates: list[str]) -> tuple[str, ...]:
    seen: dict[str, str] = {}
    for candidate in candidates:
        if affiliation := clean_affiliation(candidate):
            seen.setdefault(affiliation.casefold(), affiliation)
    return tuple(seen.values())


def clean_affiliation(text: str) -> str | None:
    """Normalize one affiliation string, or return ``None`` if it is not an affiliation."""
    text = _CONTACT_TAIL_RE.sub("", text.replace("\xa0", " "))
    if _NOISE_RE.search(text):
        return None
    text = _SPACE_BEFORE_PUNCTUATION_RE.sub(r"\1", " ".join(text.split()))
    text = _LEADING_MARKER_RE.sub("", text)
    text = _AUTHORS_ARE_WITH_RE.sub("", text).strip(_EDGE_PUNCTUATION)
    text = _CONNECTOR_RE.sub("", text)
    if len(text) < _MIN_LENGTH or not any(char.isalpha() for char in text):
        return None
    return text
