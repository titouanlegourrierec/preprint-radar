"""Extract front matter (affiliations, abstract) from arXiv HTML renderings (LaTeXML output).

The HTML front matter depends on the LaTeX class used by the authors. The paper-level set
of affiliations is extracted first (what search and filtering need); when the page also
says who is where — one affiliation block per author, superscript markers, or "A is with
B" notes — each author is additionally mapped to their own affiliations.
"""

import logging
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
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
    r"@|https?://|www\.|equal(ly)? contribut|contributed equally|correspond|work done|project lead"
    r"|senior author|first author|co-first|joint first|equal advising|internship",
    re.IGNORECASE,
)
# The vertical space of a LaTeX line break (\\[5pt]), which LaTeXML prints as text.
_LATEX_SPACE_RE = re.compile(r"\[\s*-?\d*\.?\d+\s*(?:pt|em|ex|mm|cm|in|bp|pc|mu)\s*\]")
# The label of a link whose address is removed as a contact detail, sometimes glued to the
# affiliation before it: "MITProject page".
_LINK_LABEL_RE = re.compile(r"project\s+(?:page|website|homepage|repository|site)\b\s*:?", re.IGNORECASE)
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
# A full stop that ends a sentence, not an initial's: "Spain. L. Zhinin is with" ends at "Spain.".
_FULL_STOP_RE = re.compile(r"(?<!\b[A-Z])\.\s+")
# The same people's next affiliation in one sentence: "is with X and is also with Y".
_TRAILING_CONNECTOR_RE = re.compile(r"[\s,]+(?:and|&)\s*$", re.IGNORECASE)
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
# elsarticle's \affiliation{organization=..., city=..., country=...}, which LaTeXML prints
# verbatim. Any key counts once one of these is present (authors misspell them).
_KEYVAL_RE = re.compile(r"\b(?:organization|addressline|city|postcode|state|country)\s*=", re.IGNORECASE)
_KEY_RE = re.compile(r"\b([a-z]+)\s*=", re.IGNORECASE)
_SPACE_BEFORE_PUNCTUATION_RE = re.compile(r"\s+([,;])")
# Empty fields of some LaTeX classes leave commas in a row: "FPT University, , Cantho".
_REPEATED_COMMA_RE = re.compile(r",(?:\s*,)+")
_EDGE_PUNCTUATION = " ,;:."
_MIN_LENGTH = 3

# Superscripts that mark contribution notes rather than affiliations.
_SYMBOL_MARKERS = frozenset("*†‡§¶⋆♯♭#°ª")
# ``⟨marker⟩`` tokens injected in place of superscripts by :func:`_marked_text`.
_MARKED_RE = re.compile(r"⟨([^⟨⟩]*)⟩")
_MARKER_RUN_RE = r"((?:\s*⟨[^⟨⟩]*⟩)+)"
_MARKER_SPLIT_RE = re.compile(r"[,;\s]+")
_ANCHOR_RE = re.compile(r"⟨([^⟨⟩]+)⟩\s*([^⟨]+)")
_TRAILING_ANCHOR_RE = re.compile(r"([^⟨⟩]+?)\s*⟨([^⟨⟩]+)⟩")
_NUMBERED_ANCHOR_RE = re.compile(r"^\s*(?P<marker>\d{1,2})\s*(?P<name>[A-Z].{2,})$", re.MULTILINE)
# Separators of several names in one creator: "A, B and C", "A & B".
_SEVERAL_PEOPLE_RE = re.compile(r",|&|\band\b", re.IGNORECASE)
# Sentence ends, except after an initial ("E. Milara") or an acronym ("USA.").
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[^\sA-Z][.;])\s+")

type AuthorAffiliations = tuple[tuple[int, ...] | None, ...]
"""Per author, the indices of their affiliations; ``None`` when unknown for that author."""


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


def fetch_front_matter(client: HttpClient, html_url: str, *, authors: Sequence[str] = ()) -> FrontMatter:
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


def parse_front_matter(html: str, *, authors: Sequence[str] = ()) -> FrontMatter:
    """Extract affiliations, abstract and the author-affiliation mapping from a rendering.

    Contact details (e-mails, URLs) are discarded from affiliations so they are never
    republished.

    Args:
        html: Raw HTML of the paper.
        authors: Author names, in the paper's order. They anchor the author-affiliation
            mapping, and a name is never reported as an affiliation.

    Returns:
        The front matter.
    """
    soup = BeautifulSoup(html, "html.parser")
    names = {author.casefold() for author in authors}
    affiliations = tuple(a for a in _affiliations(soup) if a.casefold() not in names)
    return FrontMatter(
        affiliations=affiliations,
        abstract=_abstract(soup),
        author_affiliations=_author_affiliations(html, tuple(authors), affiliations),
    )


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
                # Stop at the sentence that introduces the next people: "..., Spain. C. Li is with".
                text = line[match.end() : matches[index + 1].start()]
                if stops := list(_FULL_STOP_RE.finditer(text)):
                    text = text[: stops[-1].start()]
                else:
                    text = _TRAILING_CONNECTOR_RE.sub("", text)
            else:
                text = line[match.end() :]
            affiliations.append(_NEXT_SENTENCE_RE.split(_CONTACT_TAIL_RE.sub("", text), maxsplit=1)[0])
    return affiliations


def _segments(node: Tag) -> list[str]:
    """Candidate affiliations in a node: one per line, footnote marker or wide space.

    A line ending with a comma or "and" continues on the next one, and a line that only
    names a place ("Munich, Germany") belongs to the previous one when it has no country.
    elsarticle's ``key=value`` affiliations ignore line breaks instead: see
    :func:`_keyval_chunks`.
    """
    for marker in node.select("sup"):
        marker.replace_with("\n")
    text = _LATEX_SPACE_RE.sub("\n", node.get_text().replace("\xa0", " "))
    if _KEYVAL_RE.search(text):
        return _keyval_chunks(text)
    lines = [line.strip() for line in _SEPARATOR_RE.split(text)]
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


def _keyval_chunks(text: str) -> list[str]:
    """Split elsarticle ``key=value`` text into one raw chunk per affiliation.

    Values wrap across lines ("organization=Centre for Human-Computer", then
    "Interaction, ..."), so line breaks are ignored; a key seen again starts the next
    affiliation. The keys are removed later, by :func:`clean_affiliation`.
    """
    flat = " ".join(text.split())
    chunks: list[str] = []
    seen: set[str] = set()
    start = 0
    for match in _KEY_RE.finditer(flat):
        key = match.group(1).casefold()
        if key in seen:
            chunks.append(flat[start : match.start()])
            seen.clear()
            start = match.start()
        seen.add(key)
    chunks.append(flat[start:])
    return [chunk.strip(_EDGE_PUNCTUATION) for chunk in chunks if chunk.strip(_EDGE_PUNCTUATION)]


def _keyval_text(text: str) -> str:
    """One elsarticle affiliation as plain text: its values, the organization first.

    The organization leads so that the institution comes first whatever the order of the
    source. Empty values and separators (``citysep=,``) are dropped, and a value that
    repeats the previous one is kept once (``addressline=Mandi, city=Mandi``).
    """
    parts = _KEY_RE.split(text)
    pairs = [(key.casefold(), value) for key, value in zip(parts[1::2], parts[2::2], strict=True)]
    fields = [parts[0]]
    fields += [value for key, value in pairs if key == "organization"]
    fields += [value for key, value in pairs if key != "organization"]
    kept: list[str] = []
    for field in (field.strip(_EDGE_PUNCTUATION) for field in fields):
        if any(char.isalnum() for char in field) and (not kept or kept[-1].casefold() != field.casefold()):
            kept.append(field)
    return ", ".join(kept)


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
    text = _LINK_LABEL_RE.sub(" ", _LATEX_SPACE_RE.sub(" ", text))
    if _NOISE_RE.search(text):
        return None
    text = _SPACE_BEFORE_PUNCTUATION_RE.sub(r"\1", " ".join(text.split()))
    text = _REPEATED_COMMA_RE.sub(",", text)
    text = _LEADING_MARKER_RE.sub("", text)
    # After the marker strip, which would eat a leading postcode value.
    if _KEYVAL_RE.search(text):
        text = _keyval_text(text)
    text = _AUTHORS_ARE_WITH_RE.sub("", text).strip(_EDGE_PUNCTUATION)
    text = _CONNECTOR_RE.sub("", text)
    if len(text) < _MIN_LENGTH or not any(char.isalpha() for char in text):
        return None
    return text


def _author_affiliations(
    html: str, authors: tuple[str, ...], affiliations: tuple[str, ...]
) -> AuthorAffiliations | None:
    """Map each author to their affiliations, as indices into ``affiliations``.

    Tried in order: a single affiliation or author (trivial), one affiliation block per
    author, superscript markers matched with marked lines and notes, and "A and B are
    with X" thanks notes. ``None`` when the page never says who is where; a ``None``
    entry when it says it only for the other authors.
    """
    if not authors or not affiliations:
        return None
    if len(affiliations) == 1 or len(authors) == 1:
        return (tuple(range(len(affiliations))),) * len(authors)
    # The soup of the paper-level pass was pruned in place: parse a fresh one.
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one("div.ltx_authors") is None:
        return None
    index_of = {affiliation.casefold(): index for index, affiliation in enumerate(affiliations)}
    for tier in (_per_creator_map, _marker_map, _thanks_map):
        if (mapping := tier(soup, authors, index_of)) is not None:
            return mapping
    return None


def _per_creator_map(
    soup: BeautifulSoup, authors: tuple[str, ...], index_of: Mapping[str, int]
) -> AuthorAffiliations | None:
    """One affiliation block per author (ACM- and IEEE-like classes)."""
    creators: list[tuple[str, tuple[int, ...]]] = []
    for creator in soup.select("div.ltx_authors span.ltx_creator.ltx_role_author"):
        name = creator.select_one(".ltx_personname")
        if name is None:
            continue
        contacts = [
            segment
            for contact in creator.select(".ltx_role_affiliation, .ltx_role_address")
            for segment in _segments(_pruned(contact))
        ]
        creators.append((_plain_text(name), _indices(contacts, index_of)))
    if not any(indices for _, indices in creators):
        return None
    if len(creators) > 1 and not any(indices for _, indices in creators[:-1]):
        # Only the last author carries affiliations: LaTeXML attaches a block shared by
        # every author to the last one, which says nothing about who is where.
        return None
    # A creator naming several people ("A, B and C", "A & B") says nothing about which of
    # them is where (markers may): only creators of one person are aligned with the authors.
    people = [(name, indices) for name, indices in creators if not _SEVERAL_PEOPLE_RE.search(name)]
    aligned = _align([name for name, _ in people], authors)
    if aligned is None:
        return None
    mapping: list[tuple[int, ...] | None] = [None] * len(authors)
    for creator_index, author_index in aligned.items():
        mapping[author_index] = people[creator_index][1] or None
    return tuple(mapping) if any(mapping) else None


def _marker_map(
    soup: BeautifulSoup, authors: tuple[str, ...], index_of: Mapping[str, int]
) -> AuthorAffiliations | None:
    """Superscript markers on names, matched with marker-led affiliation lines and notes."""
    block = soup.select_one("div.ltx_authors")
    if block is None:  # pragma: no cover - _author_affiliations only maps pages with an author block
        return None
    names = _fold(" , ".join(_marked_text(name) for name in block.select(".ltx_personname")))
    anchors = _anchors(soup, block, index_of)
    if not anchors:
        return None

    mapping: list[tuple[int, ...] | None] = [None] * len(authors)
    resolved = 0
    for position, author in enumerate(authors):
        match = re.search(re.escape(_fold(author)) + r"[,\s]*" + _MARKER_RUN_RE, names)
        if match is None:
            continue
        markers = [
            marker
            for token in _MARKED_RE.findall(match.group(1))
            for marker in _MARKER_SPLIT_RE.split(token)
            if marker
        ]
        indices: list[int] = []
        for marker in _expand(markers, anchors):
            if marker in anchors:
                if anchors[marker] not in indices:
                    indices.append(anchors[marker])
            elif not set(marker) <= _SYMBOL_MARKERS:
                # An affiliation-like marker without an anchor: the anchor set is wrong.
                return None
        if indices:
            mapping[position] = tuple(indices)
            resolved += 1
    return tuple(mapping) if resolved else None


def _expand(markers: Iterable[str], anchors: Mapping[str, int]) -> list[str]:
    """Split marker runs written without separators ("⋆†", "12") into known markers."""
    expanded: list[str] = []
    for marker in markers:
        if marker not in anchors and len(marker) > 1 and all(char in anchors for char in marker):
            expanded.extend(marker)
        else:
            expanded.append(marker)
    return expanded


def _anchors(soup: BeautifulSoup, block: Tag, index_of: Mapping[str, int]) -> dict[str, int]:
    """Affiliations introduced by a marker, as ``marker -> affiliation index``."""
    article = soup.select_one("article.ltx_document") or soup
    nodes: list[Tag] = list(block.select(".ltx_role_affiliation, .ltx_role_address"))
    nodes += soup.select(".ltx_note.ltx_role_address, .ltx_note.ltx_role_institutetext")
    nodes += article.find_all("span", class_="ltx_role_footnotetext", recursive=False)

    anchors: dict[str, int] = {}

    def add(marker: str, candidate: str) -> None:
        cleaned = clean_affiliation(candidate)
        index = index_of.get(cleaned.casefold()) if cleaned else None
        if index is not None:
            anchors.setdefault(marker.strip(), index)

    for node in nodes:
        label = node.select_one(".ltx_note_mark")
        marked = _marked_text(_pruned(node))
        # Markers may lead ("¹ETH Zurich") or trail ("Tampere University¹") their
        # affiliation: keep the orientation that explains more of the node.
        leading = [
            (marker, candidate)
            for marker, candidate in _ANCHOR_RE.findall(marked)
            if _known(candidate, index_of)
        ]
        trailing = [
            (marker, candidate)
            for candidate, marker in _TRAILING_ANCHOR_RE.findall(marked)
            if _known(candidate, index_of)
        ]
        pairs = max(leading, trailing, key=len)
        if pairs:
            for marker, candidate in pairs:
                add(marker, candidate)
        elif label is not None:
            # A note whose only marker is its own mark: "1institutetext: ...".
            add(_plain_text(label), _MARKED_RE.sub(" ", marked))
    # Free-form blocks write the marker as plain text: "1ETH Zurich".
    for match in _NUMBERED_ANCHOR_RE.finditer(_pruned(block).get_text().replace("\xa0", " ")):
        add(match.group("marker"), match.group("name"))
    return anchors


def _known(candidate: str, index_of: Mapping[str, int]) -> bool:
    """Whether the candidate cleans to one of the paper's affiliations."""
    cleaned = clean_affiliation(candidate)
    return cleaned is not None and cleaned.casefold() in index_of


def _thanks_map(
    soup: BeautifulSoup, authors: tuple[str, ...], index_of: Mapping[str, int]
) -> AuthorAffiliations | None:
    """Thanks notes naming who is where: "A. Author and B. Author are with the X"."""
    mapping: list[tuple[int, ...] | None] = [None] * len(authors)
    resolved = 0
    sentences = [
        sentence
        for note in soup.select(".ltx_note.ltx_role_thanks")
        for line in _note_text(_pruned(note)).splitlines()
        for sentence in _SENTENCE_SPLIT_RE.split(line)
    ]
    for sentence in sentences:
        match = _IS_WITH_RE.search(sentence)
        if match is None:
            continue
        value = _NEXT_SENTENCE_RE.split(_CONTACT_TAIL_RE.sub("", sentence[match.end() :]), maxsplit=1)[0]
        cleaned = clean_affiliation(value)
        index = index_of.get(cleaned.casefold()) if cleaned else None
        if index is None:
            continue
        subject = _fold(sentence[: match.start()])
        placed = (
            range(len(authors))
            if "the authors" in subject
            else [position for position, author in enumerate(authors) if _named_in(subject, author, authors)]
        )
        for position in placed:
            entry = mapping[position] or ()
            if index not in entry:
                mapping[position] = (*entry, index)
                resolved += 1
    return tuple(mapping) if resolved else None


def _named_in(subject: str, author: str, authors: tuple[str, ...]) -> bool:
    """Whether the folded ``subject`` names the author, possibly with initials.

    "E. Milara" names Eva Milara when no other author shares that initial and surname.
    """
    folded = _fold(author)
    if folded in subject:
        return True
    first, _, surname = folded.partition(" ")
    if not surname:
        return False
    initial = first[:1]
    surname = surname.rsplit(maxsplit=1)[-1]
    twins = sum(
        1
        for other in authors
        if (other_parts := _fold(other).split())
        and other_parts[0][:1] == initial
        and other_parts[-1] == surname
    )
    if twins != 1:
        return False
    pattern = rf"\b{re.escape(initial)}[\w'-]*\.?(?:\s+[\w'.-]+)*?\s+{re.escape(surname)}\b"
    return re.search(pattern, subject) is not None


def _align(names: Sequence[str], authors: tuple[str, ...]) -> dict[int, int] | None:
    """Match creator names to the listing's authors.

    Folded full names first, then surname plus first initial, then position when both
    lists have the same length. An ambiguous name fails the whole alignment: a wrong
    author-affiliation pair is worse than none.
    """
    folded = [_fold(author) for author in authors]
    result: dict[int, int] = {}
    used: set[int] = set()
    unmatched: list[int] = []
    for position, name in enumerate(names):
        target = _fold(name)
        hits = [j for j, author in enumerate(folded) if author == target and j not in used]
        if not hits and (parts := target.split()):
            hits = [
                j
                for j, author in enumerate(folded)
                if j not in used and author.rsplit(maxsplit=1)[-1] == parts[-1] and author[:1] == parts[0][:1]
            ]
        if len(hits) > 1:
            return None
        if hits:
            result[position] = hits[0]
            used.add(hits[0])
        else:
            unmatched.append(position)
    if len(names) == len(authors):
        for position in unmatched:
            if position not in used:
                result[position] = position
                used.add(position)
    return result or None


def _indices(candidates: Iterable[str], index_of: Mapping[str, int]) -> tuple[int, ...]:
    """Indices of the candidates that clean to a known affiliation, deduplicated."""
    found: list[int] = []
    for candidate in candidates:
        cleaned = clean_affiliation(candidate)
        index = index_of.get(cleaned.casefold()) if cleaned else None
        if index is not None and index not in found:
            found.append(index)
    return tuple(found)


def _pruned(node: Tag) -> Tag:
    """A copy of the node without contact labels, e-mails, links and note decorations.

    The copied node itself is kept even when it is a note: only what it contains is noise.
    """
    copy = BeautifulSoup(str(node), "html.parser")
    root = next(iter(copy.find_all(name=True, limit=1)), None)
    for noise in copy.select(
        ".ltx_contact_name, .ltx_role_email, .ltx_note, .ltx_note_mark, .ltx_note_type, a"
    ):
        if noise is not root:
            noise.decompose()
    return copy


def _marked_text(node: Tag) -> str:
    """Node text with each superscript rendered as a ``⟨marker⟩`` token."""
    copy = BeautifulSoup(str(node), "html.parser")
    for sup in copy.select("sup"):
        sup.replace_with(f"⟨{' '.join(sup.get_text().split())}⟩")
    return " ".join(copy.get_text().split())


def _plain_text(node: Tag) -> str:
    """Node text without superscripts, whitespace collapsed."""
    copy = BeautifulSoup(str(node), "html.parser")
    for sup in copy.select("sup"):
        sup.decompose()
    return " ".join(copy.get_text().split())


# Curly quotes and long dashes fold to their ASCII forms: "Shin\u2019ichi" == "Shin'ichi".
_PUNCTUATION_VARIANTS = str.maketrans("\u2018\u2019\u02bc\u2013\u2014\u2212", "'" * 3 + "-" * 3)


def _fold(text: str) -> str:
    """Lowercase, strip accents and normalize punctuation, for name comparison."""
    decomposed = unicodedata.normalize("NFKD", text.translate(_PUNCTUATION_VARIANTS))
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


# Apostrophes and LaTeX accent leftovers join the letters around them ("Niccol`o" is "Niccolò").
_NAME_JOINERS_RE = re.compile(r"['`^~\"]")


def name_key(name: str) -> tuple[str, ...]:
    """Key under which two spellings of one person's name compare equal.

    Case, accents, punctuation and word order are ignored, so a new version of a paper
    that respells an author ("Ma Ziqi" as "Ziqi Ma", "Niccol`o" as "Niccolò") keeps them.

    Args:
        name: An author name as listed.

    Returns:
        The name's words, folded and sorted.
    """
    return tuple(sorted(re.findall(r"[^\W_]+", _NAME_JOINERS_RE.sub("", _fold(name)))))
