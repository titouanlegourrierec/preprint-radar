"""The lines of an author block or a note, joined into affiliations."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

from preprint_radar.affiliations.cleaning import (
    _keyval_chunks,
    clean_affiliation,
    is_bare_unit,
    is_place,
    names_only_authors,
)
from preprint_radar.affiliations.dom import _inside_word
from preprint_radar.affiliations.vocabulary import (
    _ADDRESS_END_RE,
    _ADDRESS_LINE_RE,
    _CONTINUED_RE,
    _COUNTRY_END_RE,
    _DANGLING_RE,
    _EDGE_PUNCTUATION,
    _INSTITUTION_WORD_RE,
    _IS_WITH_RE,
    _KEYVAL_RE,
    _LATEX_SPACE_RE,
    _MARKER_BREAK,
    _MAX_PLACE_LENGTH,
    _NOISE_RE,
    _NUMBERED_ANCHOR_RE,
    _SENTENCE_START_RE,
    _SEPARATOR_RE,
    _UNIT_NAME_GOES_ON_RE,
)


def _note_text(note: Tag) -> str:
    content = note.select_one(".ltx_note_content") or note
    for noise in content.select(".ltx_note_mark, .ltx_note_type"):
        noise.decompose()
    return _unwrapped(content.get_text())


def _unwrapped(text: str) -> str:
    """The text with the lines its source wrapped joined again.

    Thanks notes keep the line breaks of the LaTeX source, which wrap sentences anywhere:
    "are with the School of" then "Intelligent Engineering and Automation" (2609.33097).
    A line continues the previous one unless that one ends a sentence, or the line starts
    one: a sentence of the usual notes, a marker, or a new "B is with" statement, unless
    the previous line holds the start of its list of people (2609.15562).
    """
    lines: list[str] = []
    for line in text.splitlines():
        if (
            lines
            and line.strip()
            and not lines[-1].rstrip().endswith((".", ";", ":", "!", "?"))
            and not (_IS_WITH_RE.search(line) and _IS_WITH_RE.search(lines[-1]))
            and not _SENTENCE_START_RE.match(line)
        ):
            lines[-1] = f"{lines[-1].rstrip()} {line.strip()}"
        else:
            lines.append(line)
    return "\n".join(lines)


def _segments(node: Tag) -> list[str]:
    """Candidate affiliations in a node: one per line, footnote marker or wide space.

    elsarticle's ``key=value`` affiliations ignore line breaks: see :func:`_keyval_chunks`.
    Other lines are joined as :func:`_joined` says.
    """
    return _joined(_lines(node))


@dataclass(frozen=True, slots=True)
class _Line:
    """A line of a node, and whether a footnote marker starts it (a new affiliation)."""

    text: str
    marked: bool = False


def _lines(node: Tag) -> list[_Line]:
    """The lines of a node, split at line breaks, footnote markers and wide spaces."""
    for marker in node.select("sup"):
        marker.replace_with(marker.get_text() if _inside_word(marker) else f"\n{_MARKER_BREAK}")
    text = _LATEX_SPACE_RE.sub("\n", node.get_text().replace("\xa0", " "))
    if _KEYVAL_RE.search(text):
        return [_Line(chunk, marked=True) for chunk in _keyval_chunks(text.replace(_MARKER_BREAK, ""))]
    lines = [line.strip() for line in _SEPARATOR_RE.split(text)]
    return [
        _Line(line.lstrip(_MARKER_BREAK).strip(), marked=line.startswith(_MARKER_BREAK))
        for line in lines
        if line.lstrip(_MARKER_BREAK).strip()
    ]


def _joined(lines: Iterable[_Line], authors: Sequence[str] = ()) -> list[str]:
    """Lines joined into affiliations.

    A line ending with a comma, "and" or a preposition ("Ministry of") continues on the next
    one, unless a marker starts it, so does the name of a
    unit on a line starting with "and" ("Faculty of Medicine" then "and Health Sciences",
    2610.03290), and a line that completes the previous one (:func:`_completes`) is added
    to it after a comma. A line that only names authors is left alone: "Terrence Chen,
    Ziyan Wu" then "United Imaging Intelligence, Boston MA, USA" are names and an
    affiliation (2610.02382), and the names are dropped later.
    """
    joined: list[str] = []
    for line in lines:
        previous = joined[-1] if joined else ""
        if not previous or names_only_authors(previous, authors):
            joined.append(line.text)
        elif (
            _CONTINUED_RE.search(previous)
            or (not line.marked and _DANGLING_RE.search(previous))
            or _continues(previous, line)
        ):
            joined[-1] = f"{previous} {line.text}"
        elif _completes(previous, line):
            joined[-1] = f"{previous.rstrip(_EDGE_PUNCTUATION)}, {line.text}"
        else:
            joined.append(line.text)
    return joined


def _continues(previous: str, line: _Line) -> bool:
    """Whether a line goes on with the name of the unit that ends the previous one.

    "and Statistics" ends "School of Mathematics", but "and Mila" is not part of "Stanford
    University", nor "& Canada-CIFAR AI Chair" of anything. So does the end of a field a
    line break cut, "Engineering" after "Department of Electrical and Computer" (2610.01022),
    and the quoted name of a unit, "“Tullio Levi-Civita”" after "Department of Mathematics"
    (2609.37047): joined with a space, not the comma between two parts (AQ-11).
    """
    return (
        not line.marked
        and (line.text.startswith("and ") or _UNIT_NAME_GOES_ON_RE.match(line.text) is not None)
        and is_bare_unit(previous.rsplit(",", maxsplit=1)[-1].strip())
    )


def _completes(previous: str, line: _Line) -> bool:
    """Whether a line completes the affiliation before it.

    A line that only names a place ("Munich, Germany") completes one without a country, or
    a name that ends with the place's country: "National Research Council Canada" then
    "London, ON, Canada" (2609.12374), but not "University of Luxembourg" then "Trier,
    Germany", the next column of a table (2609.06629). A
    unit without its institution is completed by the next line, unless a marker starts
    that line or it is not an affiliation: "Department of Computer Science", then
    "Dartmouth College" (AFF-10, 2609.38705), or the start of one: "School of SE", then
    "Huazhong University of Science and", which the line after goes on (2610.23250).
    """
    if is_place(line.text) or (not line.marked and _is_address(line.text)):
        previous = previous.rstrip(_EDGE_PUNCTUATION)
        if _ADDRESS_END_RE.search(previous):
            return False
        named = _COUNTRY_END_RE.search(previous)
        return named is None or _last_word(named[0]) == _last_word(line.text)
    return (
        not line.marked
        and is_bare_unit(previous)
        and not is_bare_unit(line.text)
        and not _NOISE_RE.search(line.text)
        and (_goes_on(line.text) or clean_affiliation(line.text) is not None)
    )


def _goes_on(line: str) -> bool:
    """Whether the next line goes on with this one: it ends with a comma, "and" or a preposition."""
    return _CONTINUED_RE.search(line) is not None or _DANGLING_RE.search(line) is not None


def _is_address(line: str) -> bool:
    """Whether a line is an address without its country (``_ADDRESS_LINE_RE``): "10243 Berlin"."""
    address = line.strip(_EDGE_PUNCTUATION)
    return (
        len(address) <= _MAX_PLACE_LENGTH
        and _ADDRESS_LINE_RE.search(address) is not None
        and not _INSTITUTION_WORD_RE.search(address)
        and not _NOISE_RE.search(address)
    )


def _last_word(text: str) -> str:
    return text.rstrip(_EDGE_PUNCTUATION).rsplit(maxsplit=1)[-1].casefold()


def _numbered_lines(text: str) -> list[tuple[str, str]]:
    """Each numbered line's marker and affiliation, with the lines after it that go on with it (AQ-3).

    Up to the next marker, or a line led by a number the pattern does not take ("²pix.ai",
    2610.30875): another affiliation.
    """
    matches = list(_NUMBERED_ANCHOR_RE.finditer(text))
    ends = [match.start() for match in matches[1:]] + [len(text)] * bool(matches)
    numbered: list[tuple[str, str]] = []
    for match, end in zip(matches, ends, strict=True):
        lines = [_Line(match.group("name").strip(), marked=True)]
        for line in text[match.end() : end].splitlines():
            if line.strip()[:1].isdigit():
                break
            if line.strip():
                lines.append(_Line(line.strip()))
        numbered.append((match.group("marker"), _joined(lines)[0]))
    return numbered


def _numbered_text(block: Tag) -> str:
    """The text of an author block, a line starting at each marker glued to the next word.

    Free-form blocks write several numbered affiliations on one line: "University of
    California, Berkeley ²Duke University ³Carnegie Mellon University" (2609.38079). A
    marker glued to the word after it introduces an affiliation; one after a name is
    followed by a space. So does one set apart from both words around it, before a
    capital: "¹ NVIDIA ² MIT ³ UCB" (2610.19495), where a name's is glued to it ("Yunze Liu¹,").
    A marker that ends a span of text is followed by the text after it: "ZJU<span>    ²</span>Video
    Rebirth" (2605.09681), not one that ends a name ("Ada Lovelace¹", then the next author).
    """
    copy = BeautifulSoup(str(block), "html.parser")
    for sup in copy.select("sup"):
        after, before = sup.next_sibling, sup.previous_sibling
        if after is None and isinstance(sup.parent, Tag) and "ltx_text" in (sup.parent.get("class") or ()):
            after = sup.parent.next_sibling
        text = after.get_text() if isinstance(after, Tag) else str(after or "")
        lead = before.get_text() if isinstance(before, Tag) else str(before or "")
        apart = lead[-1:].isspace() or not lead
        if (text[:1].isalpha() and not _inside_word(sup)) or (
            apart and text[:1].isspace() and text.lstrip()[:1].isupper()
        ):
            sup.insert_before("\n")
    return copy.get_text().replace("\xa0", " ")
