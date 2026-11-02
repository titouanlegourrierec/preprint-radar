"""Who is where: each author mapped to their affiliations, by blocks, markers or sentences."""

import re
from collections.abc import Iterable, Mapping, Sequence

from bs4 import BeautifulSoup, Tag

from preprint_radar.affiliations.cleaning import clean_affiliations, is_place, names_only_authors
from preprint_radar.affiliations.dom import _marked_text, _plain_text, _pruned
from preprint_radar.affiliations.folding import _fold
from preprint_radar.affiliations.lines import _note_text, _numbered_lines, _numbered_text
from preprint_radar.affiliations.sources import (
    _contact_groups,
    _contact_segments,
    _glued_name,
    _leading_marker,
    _spread,
)
from preprint_radar.affiliations.vocabulary import (
    _AFFILIATION_NOTES,
    _ALL_AUTHORS_RE,
    _ANCHOR_RE,
    _CONTACT_TAIL_RE,
    _CORRESPONDENCE_RE,
    _EDGE_PUNCTUATION,
    _IS_WITH_RE,
    _MARKED_RE,
    _MARKER_RUN_RE,
    _MARKER_SPLIT_RE,
    _NEXT_SENTENCE_RE,
    _OTHER_THANKS,
    _PAIR_RE,
    _SENTENCE_SPLIT_RE,
    _SEVERAL_PEOPLE_RE,
    _SYMBOL_LINE_RE,
    _SYMBOL_MARKERS,
    _SYMBOL_SPLIT_RE,
    _TRAILING_ANCHOR_RE,
)

type AuthorAffiliations = tuple[tuple[int, ...] | None, ...]
"""Per author, the indices of their affiliations; ``None`` when unknown for that author."""


def _author_affiliations(
    html: str, authors: tuple[str, ...], affiliations: tuple[str, ...], *, partial: bool
) -> AuthorAffiliations | None:
    """Map each author to their affiliations, as indices into ``affiliations``.

    Tried in order: a single affiliation or author (trivial), one affiliation block per
    author, superscript markers matched with marked lines and notes, and "A and B are
    with X" sentences. ``None`` when the page never says who is where; a ``None`` entry
    when it says it only for the other authors. A single affiliation is not everyone's
    when its source left lines out (``partial``): author names dropped next to it, as the
    page had placed people elsewhere, or lines of a block without markers that may be
    other affiliations ("Tencent HY" beside "Southeast University", 2610.14852).
    """
    if not authors or not affiliations:
        return None
    if len(authors) == 1 or (len(affiliations) == 1 and not partial):
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
    block = soup.select_one("div.ltx_authors")
    groups = _contact_groups(block) if block is not None else []
    # One block for all: everyone is at each of the paper's affiliations, which it gave (AQ-5).
    if _spread(groups):
        return (tuple(sorted(set(index_of.values()))),) * len(authors)
    creators = _creators(soup, authors, index_of)
    if not any(indices for _, indices, _ in creators):
        return None
    if len(creators) > 1 and not any(indices for _, indices, _ in creators[:-1]):
        # Only the last author carries affiliations: LaTeXML attaches a block shared by
        # every author to the last one, which says nothing about who is where.
        return None
    places = {index for affiliation, index in index_of.items() if is_place(affiliation)}
    people: list[tuple[str, tuple[int, ...]]] = []
    for name, indices, marked in creators:
        if not _several_people(name, authors):
            people.append((name, indices))
        elif (
            len(creators) > 1
            and not marked
            and "," not in name
            and _PAIR_RE.search(name)
            and not set(indices) <= places
        ):
            # A pair beside other creators, their block under both names and no marker to
            # tell them apart: "Zhiyuan Yang & Jiahao Cheng" share it (2609.36407). Not a
            # block that only names a place, the end of an address the creators before
            # began ("Orlando, FL 32816, USA", 2609.34021): the pair would be placed nowhere.
            people += [(person, indices) for person in _PAIR_RE.split(name)]
        # Otherwise a creator naming several people ("A, B and C", or all of them in one
        # creator) says nothing about which of them is where: markers may.
    aligned = _align([name for name, _ in people], authors)
    if aligned is None:
        return None
    mapping: list[tuple[int, ...] | None] = [None] * len(authors)
    for creator_index, author_index in aligned.items():
        mapping[author_index] = people[creator_index][1] or None
    return tuple(mapping) if any(mapping) else None


def _creators(
    soup: BeautifulSoup, authors: tuple[str, ...], index_of: Mapping[str, int]
) -> list[tuple[str, tuple[int, ...], bool]]:
    """The people of the author block: each one's name, affiliations, and whether markers follow it.

    An affiliation glued to a name is that person's (2610.17412).
    """
    creators: list[tuple[str, tuple[int, ...], bool]] = []
    for creator in soup.select("div.ltx_authors span.ltx_creator.ltx_role_author"):
        name = creator.select_one(".ltx_personname")
        if name is None or not _names_a_person(name, authors):
            continue
        contacts = _contact_segments(
            (_pruned(contact) for contact in creator.select(".ltx_role_affiliation, .ltx_role_address")),
            authors,
        )
        person = _plain_text(name)
        if (glued := _glued_name(person, authors)) is not None:
            person, affiliation = glued
            contacts.append(affiliation)
        marked = _pruned(name).select_one("sup") is not None
        creators.append((person, _indices(contacts, index_of), marked))
    return creators


def _names_a_person(name: Tag, authors: Sequence[str]) -> bool:
    """Whether a creator's name is a person's.

    Not a link set as an author ("Project Page", a repository: 2609.37107), nor what else
    LaTeXML makes creators of (2610.12978): an address ("author@taobao.com"), or a line
    led by a marker ("²Alibaba Group", "✉Corresponding author") that names no author. Left
    in, the last of them would hide that only the last person carries the shared block.
    """
    text = _plain_text(_pruned(name))
    if not text or all("@" in word for word in text.replace(",", " ").split()):
        return False
    return _leading_marker(name) is None or names_only_authors(text, authors)


def _several_people(name: str, authors: Sequence[str]) -> bool:
    """Whether a creator names several people: separators, or several authors' names.

    2610.01434 writes its eight authors in one creator separated by wide spaces only.
    """
    folded = _fold(name)
    return (
        _SEVERAL_PEOPLE_RE.search(name) is not None or sum(_fold(author) in folded for author in authors) > 1
    )


def _marker_map(
    soup: BeautifulSoup, authors: tuple[str, ...], index_of: Mapping[str, int]
) -> AuthorAffiliations | None:
    """Superscript markers on names, matched with marker-led affiliation lines and notes."""
    block = soup.select_one("div.ltx_authors")
    if block is None:  # pragma: no cover - _author_affiliations only maps pages with an author block
        return None
    persons = block.select(".ltx_personname")
    # A footnote mark beside markers written by hand points to a note ("Equal contribution"),
    # not to an affiliation, whose numbers it would take (2609.39548, AQ-2); alone, it may
    # point to the footnote of one (\footnotemark and \footnotetext).
    notes = any(person.select_one("sup.ltx_sup") for person in persons)
    names = _fold(" , ".join(_marked_text(person, without_notes=notes) for person in persons))
    anchors = _anchors(soup, block, index_of)
    if not anchors:
        return None

    mapping: list[tuple[int, ...] | None] = [None] * len(authors)
    resolved = 0
    for position, author in enumerate(authors):
        match = re.search(re.escape(_fold(author)) + r"[,\s]*" + _MARKER_RUN_RE, names)
        if match is None:
            continue
        tokens = _MARKED_RE.findall(match.group(1))
        # The last author's run may end with the marker of the first affiliation line, which
        # a line break, not a glued word, sets apart: "Hieu Le⟨2⟩ ⟨1⟩ Department of Computer
        # Science, Stony Brook University" (2609.38607, AQ-3).
        following = names[match.end() :].split("⟨", 1)[0]
        if len(tokens) > 1 and following.strip() and _known(following, index_of):
            tokens = tokens[:-1]
        markers = [marker for token in tokens for marker in _MARKER_SPLIT_RE.split(token) if marker]
        indices: list[int] = []
        for marker in _expand(markers, anchors):
            if marker in anchors:
                indices.extend(index for index in anchors[marker] if index not in indices)
            elif not set(marker) <= _SYMBOL_MARKERS:
                # An affiliation-like marker without an anchor: the anchor set is wrong.
                return None
        if indices:
            mapping[position] = tuple(indices)
            resolved += 1
    return tuple(mapping) if resolved else None


def _expand(markers: Iterable[str], anchors: Mapping[str, tuple[int, ...]]) -> list[str]:
    """Split marker runs written without separators ("⋆†", "12", "6*‡") into known markers.

    Symbols come off a number first: "2,6*‡" places its author at 2 and 6 (2609.38079).
    """
    expanded: list[str] = []
    for run in markers:
        parts = [run] if run in anchors else [part for part in _SYMBOL_SPLIT_RE.split(run) if part]
        for marker in parts:
            if marker not in anchors and len(marker) > 1 and all(char in anchors for char in marker):
                expanded.extend(marker)
            else:
                expanded.append(marker)
    return expanded


def _anchors(soup: BeautifulSoup, block: Tag, index_of: Mapping[str, int]) -> dict[str, tuple[int, ...]]:
    """Affiliations introduced by a marker, as ``marker -> affiliation indices``."""
    article = soup.select_one("article.ltx_document") or soup
    nodes: list[Tag] = list(block.select(".ltx_role_affiliation, .ltx_role_address"))
    nodes += soup.select(_AFFILIATION_NOTES)
    nodes += article.find_all("span", class_="ltx_role_footnotetext", recursive=False)
    # Thanks notes that number their affiliation ("¹FZI Research Center...", 2609.03677), by
    # their markers only: their own mark, the same for every note, names no affiliation.
    thanks = [
        note
        for note in soup.select(".ltx_note.ltx_role_thanks")
        if not _OTHER_THANKS & set(note.get_attribute_list("class"))
    ]

    anchors: dict[str, tuple[int, ...]] = {}

    def add(marker: str, candidate: str) -> None:
        if indices := _anchored(candidate, index_of):
            anchors.setdefault(marker.strip(), indices)

    footnotes = set(article.find_all("span", class_="ltx_role_footnotetext", recursive=False))
    for node in [*nodes, *thanks]:
        label = node.select_one(".ltx_note_mark") if node not in thanks else None
        marked = _marked_text(_pruned(node))
        if node in footnotes:
            # Its last affiliation ends where its correspondence starts (2610.35857).
            marked = _CORRESPONDENCE_RE.sub("", marked)
        # Markers may lead ("¹ETH Zurich") or trail ("Tampere University¹") their
        # affiliation: keep the orientation that explains more of the node.
        leading = [
            (marker, candidate)
            for run, candidate in _ANCHOR_RE.findall(marked)
            if _known(candidate, index_of)
            for marker in _MARKED_RE.findall(run)
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
    # Free-form blocks write the marker as plain text: "1ETH Zurich", or a symbol: "*Oregon
    # State University" (2610.17605), which anchors only an affiliation, not "*Equal contribution".
    text = _numbered_text(_pruned(block))
    for marker, name in _numbered_lines(text):
        add(marker, name)
    for match in _SYMBOL_LINE_RE.finditer(text):
        add(match.group("marker"), match.group("name"))
    return anchors


def _known(candidate: str, index_of: Mapping[str, int]) -> bool:
    """Whether the candidate cleans to one of the paper's affiliations, or is made of them."""
    return bool(_anchored(candidate, index_of))


def _anchored(candidate: str, index_of: Mapping[str, int]) -> tuple[int, ...]:
    """The affiliations of the text after a marker: the one it cleans to, or those it is made of.

    A marker's text runs to the next marker, read as one line: it may hold the lines an
    affiliation was joined from, then another affiliation of the same marker:
    "⟨2⟩Laboratory for intelligent Global Health and Humanitarian Response / Technologies
    (LiGHT) / Swiss Federal Institute of Technology (EPFL), Lausanne, Switzerland"
    (2610.03290). It is then cut into the paper's affiliations, one after another, without
    regard to commas; a text that is not wholly made of them anchors nothing.
    """
    if indices := _indices([candidate], index_of):
        return indices
    loose = {_loose(affiliation): index for affiliation, index in index_of.items()}
    rest = _loose(candidate.strip(_EDGE_PUNCTUATION))
    found: list[int] = []
    while rest:
        head = max((key for key in loose if rest == key or rest.startswith(f"{key} ")), key=len, default=None)
        if head is None:
            return ()
        found.append(loose[head])
        rest = rest[len(head) :].strip()
    return tuple(dict.fromkeys(found))


def _thanks_map(
    soup: BeautifulSoup, authors: tuple[str, ...], index_of: Mapping[str, int]
) -> AuthorAffiliations | None:
    """Sentences naming who is where: "A. Author and B. Author are with the X".

    They are written in thanks notes, and by some classes in the affiliation macro.
    """
    notes = soup.select(".ltx_note.ltx_role_thanks")
    notes += soup.select("div.ltx_authors .ltx_role_affiliation, div.ltx_authors .ltx_role_address")
    return _sentence_map([_note_text(_pruned(note)) for note in notes], authors, index_of)


def map_stated_affiliations(
    texts: Iterable[str], authors: Sequence[str], affiliations: Sequence[str], *, everyone: bool = True
) -> AuthorAffiliations | None:
    """Place the authors that "A and B are with X" sentences name, as the page parser does.

    Args:
        texts: Text holding the sentences, such as stored affiliation strings.
        authors: The paper's author names, in order.
        affiliations: The paper's affiliations, which the sentences' affiliations must clean to.
        everyone: Whether "The authors are with X" places every author. A footnote shared by
            some of them says it too.

    Returns:
        For each author, the indices of their affiliations (``None`` for an author no
        sentence names), or ``None`` when no sentence places anybody.
    """
    index_of = {affiliation.casefold(): index for index, affiliation in enumerate(affiliations)}
    return _sentence_map(texts, tuple(authors), index_of, everyone=everyone)


def _sentence_map(
    texts: Iterable[str], authors: tuple[str, ...], index_of: Mapping[str, int], *, everyone: bool = True
) -> AuthorAffiliations | None:
    mapping: list[tuple[int, ...] | None] = [None] * len(authors)
    resolved = 0
    sentences = [
        sentence
        for text in texts
        for line in text.splitlines()
        for sentence in _SENTENCE_SPLIT_RE.split(line)
    ]
    for sentence in sentences:
        match = _IS_WITH_RE.search(sentence)
        if match is None:
            continue
        value = _NEXT_SENTENCE_RE.split(_CONTACT_TAIL_RE.sub("", sentence[match.end() :]), maxsplit=1)[0]
        indices = _indices([value], index_of)
        if not indices:
            continue
        subject = _fold(sentence[: match.start()])
        if _ALL_AUTHORS_RE.search(subject):
            placed: Iterable[int] = range(len(authors)) if everyone else ()
        else:
            placed = [
                position for position, author in enumerate(authors) if _named_in(subject, author, authors)
            ]
        for position in placed:
            entry = mapping[position] or ()
            if new := tuple(index for index in indices if index not in entry):
                mapping[position] = (*entry, *new)
                resolved += 1
    return tuple(mapping) if resolved else None


def _named_in(subject: str, author: str, authors: tuple[str, ...]) -> bool:
    """Whether the folded ``subject`` names the author, possibly with initials.

    "E. Milara" names Eva Milara when no other author shares that initial and surname, and
    so does "E.Milara", the surname right after the initial's full stop (2410.08613).
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
    pattern = rf"\b{re.escape(initial)}[\w'-]*\.?(?:\s+[\w'.-]+)*?(?:\s+|(?<=\.)){re.escape(surname)}\b"
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
    """Indices of the candidates that clean to a known affiliation, deduplicated.

    Commas do not count: a marked line read as one text ("Department of Computer Science
    University of Central Florida") is the affiliation its lines were joined into
    ("Department of Computer Science, University of Central Florida", 2610.02000).
    """
    loose = {_loose(affiliation): index for affiliation, index in index_of.items()}
    found: list[int] = []
    for candidate in candidates:
        for affiliation in clean_affiliations(candidate):
            index = index_of.get(affiliation.casefold(), loose.get(_loose(affiliation)))
            if index is not None and index not in found:
                found.append(index)
    return tuple(found)


def _loose(affiliation: str) -> str:
    return " ".join(affiliation.casefold().replace(",", " ").split())
