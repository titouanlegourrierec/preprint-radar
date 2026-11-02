"""One affiliation string made clean: contacts, markers, notes and leftovers removed.

What every source of affiliations goes through, pages, the API and stored strings alike
(``reclean``): the rules do not depend on the tier a string came from (EXT-4).
"""

import re
from collections.abc import Sequence

from preprint_radar.affiliations.folding import name_key
from preprint_radar.affiliations.vocabulary import (
    _ADDRESS_END_RE,
    _AFFILIATIONS_NOTE_RE,
    _ALSO_WITH_RE,
    _ANY_TEXT_MARKER_RE,
    _BARE_UNIT_RE,
    _COLLECTIVE_RE,
    _COMPANY_SUFFIX_RE,
    _CONNECTOR_RE,
    _CONTACT_RE,
    _CONTACT_TAIL_RE,
    _COUNTRY_END_RE,
    _CUT_CONNECTOR_RE,
    _DANGLING_RE,
    _EDGE_PUNCTUATION,
    _EMPTY_BRACKETS_RE,
    _FULL_STOP_RE,
    _GLUE_RE,
    _GLUED_COUNTRY_RE,
    _GLUED_NOTE_RE,
    _HOST_RE,
    _INLINE_MARKER_RE,
    _INSTITUTION_START_RE,
    _INSTITUTION_WORD_RE,
    _INSTITUTION_WORD_START_RE,
    _INVISIBLE,
    _IS_WITH_RE,
    _JUNK_RE,
    _KEY_RE,
    _KEYVAL_RE,
    _LABELS_ONLY_RE,
    _LATER_NOTE_RE,
    _LATEX_SPACE_RE,
    _LEADING_MARKER_RE,
    _LINK_LABEL_RE,
    _LINK_TAIL_RE,
    _LINKS_HEADING_RE,
    _LIST_END_RE,
    _MACRO_RE,
    _MAIL_FRAGMENT_RE,
    _MAILBOX_LIST_RE,
    _MARKED_WORD_RE,
    _MAX_PLACE_LENGTH,
    _MIN_LENGTH,
    _NAME_GOES_ON_RE,
    _NAME_MARKER_RE,
    _NAME_START_RE,
    _NAME_SUFFIX_RE,
    _NEXT_SENTENCE_RE,
    _NOISE_RE,
    _NOTE_SENTENCE_RE,
    _OBFUSCATED_EMAIL_RE,
    _ORCID_RE,
    _REPEATED_COMMA_RE,
    _RUN_TOGETHER_RE,
    _SENTENCE_WORD_RE,
    _SEVERAL_PEOPLE_RE,
    _SPACE_BEFORE_PUNCTUATION_RE,
    _SUBJECT_RE,
    _TEX_SOURCE_RE,
    _TRAILING_CONNECTOR_RE,
    _UNIT_WORD_RE,
    _WORD_BEFORE_ADDRESS_RE,
)


def _stated_affiliations(notes: list[str]) -> list[str]:
    """Affiliations stated in sentences: "A and B are with the X, Y (e-mail: ...)".

    Thanks notes are written that way, and so are some affiliation macros, several
    sentences in a row: "A, B and C are at X. A is with Y. B is with Z". What follows "is
    at" or "is with" is cut at its semicolons, and each piece kept only when it is a name
    (:func:`_names_a_place`, AFF-9): "This work is at the intersection of vision and
    language" states none.
    """
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
            stated = _NEXT_SENTENCE_RE.split(_CONTACT_TAIL_RE.sub("", text), maxsplit=1)[0]
            affiliations += [piece for piece in stated.split(";") if _names_a_place(piece)]
    return affiliations


def _names_a_place(text: str) -> bool:
    """Whether a stated affiliation is a name, not "the intersection of vision and language".

    Capitalized ("MIT", "NVIDIA", "ETH Zurich"), or naming an institution, ending with a
    country or holding a comma, as "the department of physics, ..." does.
    """
    text = text.strip().rstrip(".")
    return bool(
        text[:1].isupper() or _INSTITUTION_WORD_RE.search(text) or _ADDRESS_END_RE.search(text) or "," in text
    )


def is_bare_unit(line: str) -> bool:
    """Whether a line names a unit without its institution, like "Department of Computer Science".

    Args:
        line: A line of an author block, or a stored affiliation.

    Returns:
        ``True`` when it starts with a unit ("School of", "Laboratory for") and has
        neither an institution word nor a comma, after which one usually comes.
    """
    return _BARE_UNIT_RE.match(line) is not None and _HOST_RE.search(line) is None


def is_place(line: str) -> bool:
    """Whether a line only names a place, like "Munich, Germany" or "CA 94720, USA".

    Args:
        line: A line of an author block, or a stored affiliation.

    Returns:
        ``True`` for a short line that ends with a country and has no institution word.
    """
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


def clean_affiliations(text: str) -> tuple[str, ...]:
    """The affiliations in one candidate string, each normalized by :func:`clean_affiliation`.

    Usually one; none when the string is not an affiliation; several for IEEE's "X, China,
    and also with Y", which gives its people both.

    Args:
        text: A candidate string, from a page or from stored data.

    Returns:
        The affiliations, in order (possibly empty).
    """
    # A role ("X is Robotics Lead at Y") is no statement of thanks notes: the string is one.
    text = text.translate(_INVISIBLE)
    statements = (_stated_affiliations([text]) or [text]) if _people(text) else [text]
    return tuple(
        affiliation
        for statement in statements
        for part in _ALSO_WITH_RE.split(statement)
        for unmarked in _ANY_TEXT_MARKER_RE.split(part)
        for marked in marked_pieces(" ".join(unmarked.split()))
        for piece in _run_together(marked)
        if (affiliation := clean_affiliation(piece))
    )


def marked_pieces(text: str) -> list[str]:
    """The affiliations of a string that numbered markers written as text run together.

    "Cornell University 2University of California, Berkeley" is two (AFF-23). A marker is
    one or two digits glued to a capitalized word ("2Duke", "3HKUST", "4eBay") after a
    space; the word before holds no digit, unless it is itself marked ("2CASIA 3HKUST"), so
    that postcodes stay whole ("London WC1E 6AE", "QC H2S 3H1"), and so do "3D Vision Lab"
    or "4K" (one letter), and is no preposition: "Faculty of 3mE" (2203.10157).

    Args:
        text: A candidate string, from a page or from stored data.

    Returns:
        The pieces, each with its marker, which cleaning strips; the text alone when it
        holds no marker.
    """
    cuts = []
    for match in _INLINE_MARKER_RE.finditer(text):
        word = text[match.end() : match.end() + 2]
        before = text[: match.start()].split()
        if (
            (word[0].isupper() or word[1].isupper())
            and (not any(char.isdigit() for char in before[-1]) or _MARKED_WORD_RE.fullmatch(before[-1]))
            and not _DANGLING_RE.search(text[: match.start()])
        ):
            cuts.append(match.start())
    return [text[start:end] for start, end in zip([0, *cuts], [*cuts, len(text)], strict=True)]


def _run_together(text: str) -> list[str]:
    """The universities of a string that ran them together, each apart (see ``_RUN_TOGETHER_RE``)."""
    cuts = [match.end() for match in _RUN_TOGETHER_RE.finditer(text)]
    return [text[start:end] for start, end in zip([0, *cuts], [*cuts, len(text)], strict=True)]


def clean_affiliation(text: str) -> str | None:
    """Normalize one affiliation string, or return ``None`` if it is not an affiliation.

    Contact details are removed, including obfuscated addresses and lists of mailbox names,
    and so are the people an IEEE sentence starts with: "A and B are with X" gives X. A
    string holding several affiliations is split first, by :func:`clean_affiliations`.
    """
    text = _TEX_SOURCE_RE.sub("", _MACRO_RE.sub("", text.translate(_INVISIBLE).replace("\xa0", " ")))
    text = _ANY_TEXT_MARKER_RE.sub(" ", text)
    text = _WORD_BEFORE_ADDRESS_RE.sub(r"\1 ", text)
    text = _CONTACT_TAIL_RE.sub(
        "", _AFFILIATIONS_NOTE_RE.sub("", _GLUED_NOTE_RE.sub("", _ORCID_RE.sub(" ", text)))
    )
    text = _MAILBOX_LIST_RE.sub(" ", _OBFUSCATED_EMAIL_RE.sub(" ", text))
    text = _EMPTY_BRACKETS_RE.sub(" ", _LINK_LABEL_RE.sub(" ", _LATEX_SPACE_RE.sub(" ", text)))
    text = _LINK_TAIL_RE.sub("", _LINKS_HEADING_RE.sub("", text))
    if (
        _NOISE_RE.search(text)
        or _LATER_NOTE_RE.search(text)
        or _is_note_sentence(text)
        or _LABELS_ONLY_RE.match(text.strip())
    ):
        return None
    text = _SPACE_BEFORE_PUNCTUATION_RE.sub(r"\1", " ".join(_unglued(text).split()))
    text = _REPEATED_COMMA_RE.sub(",", text)
    text = _LEADING_MARKER_RE.sub("", text)
    # After the marker strip, which would eat a leading postcode value.
    if _KEYVAL_RE.search(text):
        text = _keyval_text(text)
    if people := _people(text):
        text = text[people.end() :]
    # A list cut after its connector ("The University of Hong Kong, and", 2609.04958) or a
    # dash ("Hamburg, Germany -"): what precedes it stands alone.
    text = _LIST_END_RE.sub("", text.strip(_EDGE_PUNCTUATION)).rstrip(_EDGE_PUNCTUATION + "-\u2013")
    text = _CONNECTOR_RE.sub("", text)
    # A string cut short: after a preposition ("Technion - Israel Institute of"), nothing
    # says what it was; after "and", what precedes it may stand alone.
    if cut := _CUT_CONNECTOR_RE.search(text):
        text = text[: cut.start()]
        if _NAME_GOES_ON_RE.search(text) and not is_bare_unit(text):
            return None
    if _DANGLING_RE.search(text):
        return None
    if len(text) < _MIN_LENGTH or not any(char.isalpha() for char in text) or _JUNK_RE.fullmatch(text):
        return None
    # A contact detail the rules above did not strip: the whole string goes, rather than a
    # store `validate` refuses, which a data workflow does not push (AFF-32).
    if has_contact(text):
        return None
    return text


def _is_note_sentence(text: str) -> bool:
    """Whether a string is a note's sentence, which an affiliation never is (EXT-4)."""
    return _NOTE_SENTENCE_RE.match(_LEADING_MARKER_RE.sub("", text)) is not None and (
        _SENTENCE_WORD_RE.search(text) is not None or text.startswith("Manuscript")
    )


def has_contact(text: str) -> bool:
    """Whether the text holds a contact detail, which the data contract keeps out of affiliations.

    The cleaning drops a string that still holds one, and ``validate`` refuses a store that
    does: both ask this.
    """
    return _CONTACT_RE.search(text) is not None or _MAIL_FRAGMENT_RE.search(text.strip()) is not None


def _unglued(text: str) -> str:
    """The text with a comma where LaTeXML glued two parts of an affiliation (see ``_GLUE_RE``).

    "Department of Computer Science and EngineeringMichigan State University" becomes
    "Department of Computer Science and Engineering, Michigan State University".
    """
    cuts: list[int] = []
    for match in _GLUE_RE.finditer(text):
        at = match.start()
        # The part since the last comma, its cuts so far apart: a unit before an earlier
        # cut still counts ("School of Computer ScienceNanjing UniversityJiangsu",
        # 2610.13681), and so does one an earlier cut ends ("Research LabDepartment of …
        # ScienceTexas A&M", 2609.22631).
        bounds = [text.rfind(",", 0, at) + 1]
        bounds += [cut for cut in cuts if cut > bounds[0]]
        part = " ".join(text[begin:end] for begin, end in zip(bounds, [*bounds[1:], at], strict=True))
        word = part.rsplit(maxsplit=1)[-1] if part.split() else ""
        inside_brackets = part.count("(") > part.count(")")
        if text[at - 1] == ")" or ("-" not in word and not inside_brackets and _glued_at(text, at, part)):
            cuts.append(at)
    ends = [*cuts, len(text)]
    return ", ".join(text[begin:end] for begin, end in zip([0, *cuts], ends, strict=True))


def _glued_at(text: str, at: int, part: str) -> bool:
    """Whether the part of an affiliation before ``at`` ends there (see ``_GLUE_RE``).

    It does after a unit ("Dept. of Computer ScienceUniversity of Alabama") or a company's
    suffix ("ByteDance IncShanghai"), and a name of several words does before an
    institution's first word or its country ("Visual Geometry GroupUniversity of OxfordUK").
    Two capitals only start a country: "Department of CSRPI" stays.
    """
    words = part.split()
    several = len(words) > 1
    if text[at + 1].isupper():
        return several and _GLUED_COUNTRY_RE.match(text, at) is not None
    return (
        _UNIT_WORD_RE.search(part) is not None
        or (bool(words) and _COMPANY_SUFFIX_RE.fullmatch(words[-1]) is not None)
        or (several and _GLUED_COUNTRY_RE.match(text, at) is not None)
        or (
            several
            and _INSTITUTION_START_RE.match(text, at) is not None
            and _NAME_START_RE.fullmatch(words[-1]) is None
        )
    )


def states_people(text: str) -> bool:
    """Whether the text is a sentence about people: "A and B are with X", "The authors are with X".

    Args:
        text: An affiliation candidate or a stored affiliation string.

    Returns:
        ``True`` when its affiliation follows the people it names.
    """
    return _people(text) is not None


def _people(text: str) -> re.Match[str] | None:
    """The people an "A and B are with X" sentence starts with, verb included.

    ``None`` when the text does not start that way, or when what precedes the verb names an
    institution, as it is then not a list of people: a word starting as an institution's
    does, not a name holding one ("Ahmad El-Sallab", 1808.02350).
    """
    match = _SUBJECT_RE.match(text)
    if match is None or _INSTITUTION_WORD_START_RE.search(match.group("subject")):
        return None
    return match


def names_only_authors(text: str, authors: Sequence[str]) -> bool:
    """Whether an affiliation candidate only names some of the paper's own authors.

    LaTeX classes put names where affiliations go: "Nicolás Ugrinovic", "Yiqun Zhang, and
    Yiu-Ming Cheung", "Benoît Macq Fellow, IEEE, and Christophe De Vleeschouwer Member,
    IEEE". Each name of the list is compared by :func:`name_key`, IEEE grades and "Jr."
    left out. A string with an institution word stays, and so does a collective that signs
    as an author ("Alzheimer's Disease Neuroimaging Initiative"). Names keep no markers: the
    last name of a line of names, its marker read as text, is "Saining Xie 1" (2406.18533),
    and a name in a table, "Kai Wang2" (2610.17877).

    Args:
        text: A cleaned affiliation.
        authors: The paper's author names.

    Returns:
        ``True`` when every name of ``text`` is one of ``authors``.
    """
    # Words that start an institution's: "lab" inside "Alabdulmohsin" is a name's (2307.06304).
    if _INSTITUTION_WORD_START_RE.search(text) or _COLLECTIVE_RE.search(text):
        return False
    known = {name_key(_NAME_SUFFIX_RE.sub(" ", author)) for author in authors}
    unmarked = _NAME_MARKER_RE.sub(" ", _NAME_SUFFIX_RE.sub(" ", text))
    names = [key for name in _SEVERAL_PEOPLE_RE.split(unmarked) if (key := name_key(name))]
    return bool(names) and all(key in known for key in names)
