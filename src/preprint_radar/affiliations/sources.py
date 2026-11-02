"""The affiliations of a page, from its sources in turn: contacts, notes, lines, numbered lists."""

from collections.abc import Iterable, Sequence

from bs4 import BeautifulSoup, Tag

from preprint_radar.affiliations.cleaning import (
    _stated_affiliations,
    clean_affiliations,
    has_contact,
    is_place,
    marked_pieces,
    names_only_authors,
)
from preprint_radar.affiliations.dom import _plain_text, _pruned
from preprint_radar.affiliations.folding import _fold
from preprint_radar.affiliations.lines import (
    _joined,
    _Line,
    _lines,
    _note_text,
    _numbered_lines,
    _numbered_text,
    _segments,
)
from preprint_radar.affiliations.vocabulary import (
    _ADDRESS_END_RE,
    _AFFILIATION_NOTES,
    _AI_COMPANY_RE,
    _COLLECTIVE_RE,
    _CORRESPONDENCE_RE,
    _COUNTRY_END_RE,
    _DOMAIN_RE,
    _EDGE_PUNCTUATION,
    _INSTITUTION_WORD_RE,
    _LATEX_SPACE_RE,
    _MAX_PIECE_WORDS,
    _NOISE_RE,
    _NUMBERED_ANCHOR_RE,
    _OTHER_THANKS,
    _ROLE_RE,
    _SENTENCE_WORD_RE,
    _SEPARATOR_RE,
    _SYMBOL_LINE_RE,
    _SYMBOL_MARKERS,
    _TEXT_MARKER_RE,
)


def _affiliations(soup: BeautifulSoup, authors: Sequence[str]) -> tuple[tuple[str, ...], bool]:
    """Distinct affiliations of the front matter, and whether its source left some lines out.

    Lines left out are author names dropped from the affiliations, or lines of a block
    without markers that may be other affiliations: either way, one affiliation left is not
    everyone's (:func:`_author_affiliations`).

    Sources, from the most to the least reliable: affiliations and addresses marked up in
    the author block (with the numbered lines LaTeXML set as authors beside them, and the
    affiliations glued to a name), front-matter notes (from the LaTeX address, institute,
    affiliation and numbered footnotetext macros), numbered lines after the author names,
    lines led by symbols that each name an institution, "A is with B" sentences in thanks
    notes, the lines of a block without markers that name an institution, and last the
    affiliations a thanks note lists without a sentence (:func:`_listed_affiliations`). The
    first source that gives an affiliation is used; one that only names authors gives none:
    IEEE classes put the names in the affiliation macro and the affiliations in thanks
    notes. Affiliations are deduplicated case-insensitively.
    """
    article = soup.select_one("article.ltx_document") or soup
    # Notes are read first: the author block is then cleaned of them.
    from_notes = [segment for note in soup.select(_AFFILIATION_NOTES) for segment in _note_segments(note)]
    from_notes += [
        segment
        for note in article.find_all("span", class_="ltx_role_footnotetext", recursive=False)
        for segment in _footnote_affiliations(note)
    ]
    thanks_notes = soup.select(".ltx_note.ltx_role_thanks")
    thanks = [_note_text(note) for note in thanks_notes]
    listing = [
        text
        for note, text in zip(thanks_notes, thanks, strict=True)
        if not _OTHER_THANKS & set(note.get_attribute_list("class"))
    ]

    tagged: list[str] = []
    numbered: list[str] = []
    symbols: list[str] = []
    unmarked: list[str] = []
    unmarked_partial = False
    signing: list[str] = []
    block = soup.select_one("div.ltx_authors")
    if block is not None:
        for noise in block.select(".ltx_role_email, .ltx_contact_name, .ltx_note, a"):
            noise.decompose()
        tagged = _tagged_affiliations(block, authors)
        if tagged:
            tagged += _numbered_creators(block)
        else:
            numbered = _numbered_affiliations(block)
            symbols = _symbol_affiliations(block)
            unmarked, unmarked_partial = _unmarked_affiliations(block, authors)
            signing = _signing_organizations(block, authors)
        tagged += _glued_affiliations(block, authors)
    sources = (
        (tagged + from_notes, False),
        (numbered, False),
        # A symbol marks some of the authors, never all of them.
        (symbols, True),
        # The people a sentence names are where it says, not everyone (AFF-9).
        (_stated_affiliations(thanks), True),
        (unmarked, unmarked_partial),
        (signing, True),
        (_listed_affiliations(listing), False),
    )
    names_dropped = False
    for source, partial in sources:
        found = _dedupe(source)
        affiliations = tuple(
            affiliation for affiliation in found if not names_only_authors(affiliation, authors)
        )
        names_dropped = names_dropped or len(affiliations) < len(found)
        if affiliations:
            return affiliations, names_dropped or partial
    return (), names_dropped


def _tagged_affiliations(block: Tag, authors: Sequence[str]) -> list[str]:
    """Affiliations marked up by LaTeXML: affiliation and address macros of ACM- or IEEE-like classes.

    A block spread over the creators (:func:`_spread`) is read as one.
    """
    groups = _contact_groups(block)
    if _spread(groups):
        return _contact_segments((node for nodes in groups for node in nodes), authors)
    return [segment for nodes in groups for segment in _contact_segments(nodes, authors)]


def _spread(groups: Sequence[Sequence[Tag]]) -> bool:
    """Whether the creators' contacts are one shared block LaTeXML spread over them (AQ-5).

    A class that gives each author a line of the paper's one affiliation makes a creator of
    the unit and university, the next of "Birmingham, AL, USA", the last of the e-mails
    (2609.13271; 2609.06726, 2609.34021): from a creator after the first whose contacts name
    a place and nothing else but e-mails, every creator's do, and none before ends with its
    country. Whole addresses, each ending with its country, are each author's own
    ("HeartFlow, California, USA" among Imperial College's, 1804.03999).
    """
    texts = [[line.text for node in nodes for line in _lines(_pruned(node))] for nodes in groups]

    def address_end(lines: Sequence[str]) -> bool:
        return any(is_place(line) for line in lines) and all(
            is_place(line) or has_contact(line) for line in lines
        )

    first = next((index for index, lines in enumerate(texts) if index and address_end(lines)), None)
    return (
        first is not None
        and all(address_end(lines) or all(map(has_contact, lines)) for lines in texts[first:])
        and not any(_COUNTRY_END_RE.search(line) for lines in texts[:first] for line in lines)
    )


def _contact_groups(authors: Tag) -> list[list[Tag]]:
    """The affiliation and address nodes of an author block, those of each author together.

    IEEE conference classes write each line of an author's address as its own node:
    "Department of Computer Science", "Dartmouth College", "Hanover, NH, USA" (2609.38705).
    """
    groups: list[list[Tag]] = []
    owners: list[Tag | None] = []
    for node in authors.select(".ltx_role_affiliation, .ltx_role_address"):
        owner = node.find_parent("span", class_="ltx_creator")
        if groups and owner is not None and owners[-1] is owner:
            groups[-1].append(node)
        else:
            groups.append([node])
            owners.append(owner)
    return groups


def _contact_segments(nodes: Iterable[Tag], authors: Sequence[str]) -> list[str]:
    """The affiliations in one author's contact nodes, read as the lines of one text."""
    return _joined((line for node in nodes for line in _lines(node)), authors)


def _numbered_creators(block: Tag) -> list[str]:
    """The numbered affiliation lines LaTeXML set as authors, beside contact nodes.

    2610.12978 gives "¹Sun Yat-sen University" as a contact of its last author, then
    "²Alibaba Group", "³The University of Hong Kong" and "⁴Shanghai Jiao Tong University"
    as creators of their own, each name starting with its number.
    """
    return [
        segment
        for name in block.select("span.ltx_creator.ltx_role_author .ltx_personname")
        if (marker := _leading_marker(name)) is not None and marker.get_text().strip().isdigit()
        for segment in _segments(_pruned(name))
    ]


def _leading_marker(name: Tag) -> Tag | None:
    """The superscript a creator's name starts with: a line of notes or affiliations, no name."""
    first = next((child for child in name.children if not str(child).isspace()), None)
    return first if isinstance(first, Tag) and first.name == "sup" else None


def _glued_affiliations(block: Tag, authors: Sequence[str]) -> list[str]:
    """The affiliations LaTeXML glued to their author's name (:func:`_glued_name`).

    The last name of a creator holding several counts too: "Zheng Ge    Songtao Liu    Feng
    Wang    Zeming Li    Jian SunMegvii Technology" (ar5iv's 2107.08430).
    """
    return [
        glued[1]
        for name in block.select("span.ltx_creator.ltx_role_author .ltx_personname")
        if (glued := _glued_name(_after_names(_plain_text(name), authors), authors)) is not None
    ]


def _after_names(text: str, authors: Sequence[str]) -> str:
    """The text from the last of the authors' names it starts with, spaced or glued to each other.

    "Julio Silva-RodriguezSina HajimiriIsmail Ben AyedJose DolzÉTS Montreal" gives "Jose
    DolzÉTS Montreal" (2312.12730).
    """
    while author := next(
        (
            author
            for author in authors
            if _starts_with(text, author) and _starts_with_any(text[len(author) :].lstrip(), authors)
        ),
        None,
    ):
        text = text[len(author) :].lstrip()
    return text


def _starts_with(text: str, author: str) -> bool:
    """Whether the text starts with the author's name, folded."""
    return _fold(text[: len(author)]) == _fold(author)


def _starts_with_any(text: str, authors: Sequence[str]) -> bool:
    """Whether the text starts with one of the authors' names, folded."""
    return any(_starts_with(text, author) for author in authors)


def _glued_name(name: str, authors: Sequence[str]) -> tuple[str, str] | None:
    """The author a creator's name starts with, and the affiliation glued to it.

    Some IEEE conference blocks lose every line break of an author's address, the one after
    the name included: "Xiaoya TangScientific Computing and Imaging InstituteUniversity of
    Utah" (2610.17412), and "Tolga Tasdizen*Scientific..." once its marker is dropped. Only
    a listed name followed by a capital, without a space, counts, and never before another
    author's: LaTeXML glues names to each other too, "Huy V. VoMaximilian SeitzerFederico
    Baldassarre..." (2508.10104).
    """
    for author in authors:
        rest = name[len(author) :]
        if (
            rest[:1].isupper()
            and _fold(name[: len(author)]) == _fold(author)
            and not any(_fold(other) in _fold(rest) for other in authors if other != author)
        ):
            return author, rest
    return None


def _signing_organizations(block: Tag, authors: Sequence[str]) -> list[str]:
    """The organizations a page is signed by, in place of its authors: "Qwen Team", "Alibaba Group".

    2502.13923 (Qwen2.5-VL) sets two creators, neither of its 27 listed authors. They count
    when no creator names a listed author and each names an institution or a collective:
    a creator naming none may be a person the page spells otherwise (AFF-38).
    """
    names = [
        _plain_text(_pruned(name))
        for name in block.select("span.ltx_creator.ltx_role_author .ltx_personname")
    ]
    kept = [name for name in names if name and not _NOISE_RE.search(name)]
    if not kept or any(
        any(_fold(author) in _fold(name) for author in authors)
        or not (_INSTITUTION_WORD_RE.search(name) or _COLLECTIVE_RE.search(name))
        for name in kept
    ):
        return []
    return kept


def _symbol_affiliations(block: Tag) -> list[str]:
    """Affiliation lines led by symbol markers in a free-form block: "*Oregon State University".

    2610.17605 marks its four affiliations "*", "†", "‡" and "§". Symbols mark notes too
    ("*Equal contribution", "†Now at Google"): the lines that are not noise count only when
    at least half name an institution, as numbered footnotes must
    (:func:`_footnote_affiliations`), and the others are no sentence nor role ("†Now at
    Google", "‡Intern"): "⋆Facebook AI †Sorbonne University" (ar5iv's 2012.12877). Nor when
    one ends with a symbol: the block's markers follow their affiliations, and
    "Independent§University of Waterloo¶" is not "University of Waterloo" marked "§"
    (2505.11293).
    """
    lines = [match["name"].strip() for match in _SYMBOL_LINE_RE.finditer(_numbered_text(block))]
    kept = [line for line in lines if not _NOISE_RE.search(line)]
    if any(line.endswith(tuple(_SYMBOL_MARKERS)) for line in lines):
        return []
    named = [line for line in kept if _INSTITUTION_WORD_RE.search(line)]
    if any(_SENTENCE_WORD_RE.search(line) or _ROLE_RE.search(line) for line in kept if line not in named):
        return []
    return kept if 2 * len(named) >= len(kept) else []


def _unmarked_affiliations(block: Tag, authors: Sequence[str]) -> tuple[list[str], bool]:
    """The lines of a block without contacts nor markers that name an institution: the last source.

    2610.18323 writes its ten names in the rows of a table, then "Xi'an Jiaotong University"
    and an address, without any marker. Any line of a block could pass: only those with an
    institution word or ending with a country count ("United Imaging Intelligence, Boston,
    MA, USA", 2610.02343), joined as :func:`_joined` joins lines, and never one holding an
    author's name (a name LaTeXML glued to its affiliation). A block with lines led by
    markers is read by them alone, and so is a block :func:`_split_at_commas`.

    Lines led by markers that are notes only ("*corresponding authors: ...") leave the block
    to this source. A line set apart in wide spaces is a row of affiliations, every piece
    kept when one names an institution and none an author: "Meta AI Research    WRI
    Inria" (2508.10104), where "WRI" and "Inria" hold no institution word.

    Returns:
        The affiliations, and whether lines that may be others were left out ("Tencent
        HY", "HKUST(GZ)"): the one affiliation of such a block is everyone's only when
        nothing but names and noise is left.
    """
    names = [_fold(author) for author in authors]
    if _has_marked_affiliations(block, authors, names) or _split_at_commas(block, authors):
        return [], False
    copy = _pruned(block)
    for sup in copy.select("sup"):
        sup.decompose()
    kept, text = _affiliation_rows(_LATEX_SPACE_RE.sub("\n", copy.get_text().replace("\xa0", " ")), names)
    lines = [_Line(line.strip()) for line in _SEPARATOR_RE.split(text) if line.strip()]
    left_out = False
    for line in _joined(lines, authors):
        # Without the authors' names, whose words may hold an institution's ("Labussière").
        rest = _fold(line)
        held = [name for name in names if name in rest]
        for name in held:
            rest = rest.replace(name, " ")
        named = (
            _INSTITUTION_WORD_RE.search(rest)
            or _AI_COMPANY_RE.search(line)
            or _ADDRESS_END_RE.search(rest.rstrip(_EDGE_PUNCTUATION))
        )
        if held:
            left_out = left_out or bool(named)
        elif named:
            kept.append(line)
        elif not names_only_authors(line, authors) and clean_affiliations(line):
            left_out = True
    return kept, left_out


def _has_marked_affiliations(block: Tag, authors: Sequence[str], names: Sequence[str]) -> bool:
    """Whether lines led by markers hold affiliations, not only notes and names.

    2508.10104 marks its first authors' names ("Oriane Siméoni*Huy V. Vo*", the rest glued)
    and a note, "*corresponding authors: ...", its affiliations without a marker.
    """
    marked = _numbered_text(block)
    lines = [
        match["name"] for regex in (_NUMBERED_ANCHOR_RE, _SYMBOL_LINE_RE) for match in regex.finditer(marked)
    ]
    return any(
        clean_affiliations(line) and not names_only_authors(line, authors) and not _names_only(line, names)
        for line in lines
    )


def _names_only(text: str, names: Sequence[str]) -> bool:
    """Whether the text holds nothing but these folded names, however glued: "Cijo JoseVasil Khalidov"."""
    rest = _fold(text)
    for name in names:
        rest = rest.replace(name, " ")
    return not any(char.isalpha() for char in rest)


def _affiliation_rows(text: str, names: Sequence[str]) -> tuple[list[str], str]:
    """The rows of affiliations set apart in wide spaces, and the text without them.

    A row's pieces are kept when one names an institution or a collective and none an
    author: "Meta AI Research    WRI    Inria" (2508.10104), where "WRI" and "Inria" hold no
    institution word, and "Qwen Team  Alibaba Group" (2409.12191, AFF-38).
    """
    kept: list[str] = []
    for raw in text.split("\n"):
        pieces = [piece.strip() for piece in _SEPARATOR_RE.split(raw) if piece.strip()]
        folded = _fold(raw)
        if (
            len(pieces) > 1
            and not any(name in folded for name in names)
            and any(_INSTITUTION_WORD_RE.search(piece) or _COLLECTIVE_RE.search(piece) for piece in pieces)
        ):
            kept += [piece for piece in pieces if clean_affiliations(piece)]
            text = text.replace(raw, "")
    return kept, text


def _split_at_commas(block: Tag, authors: Sequence[str]) -> bool:
    """Whether LaTeXML cut the author field at each comma and "and", affiliations included.

    Each piece is then a creator: "University of Science" and "Technology of China", "School
    of Software", "Tsinghua University", "Beijing", "China" (2411.15633, 2510.11387), whose
    lines are pieces rather than affiliations. A creator naming no author that holds a line
    of at most two words naming no institution nor country ("College Park", "Computer
    Engineering", "Telecommunications") tells it.
    """
    names = [_fold(author) for author in authors]
    for name in block.select("span.ltx_creator.ltx_role_author .ltx_personname"):
        text = _plain_text(_pruned(name))
        if any(author in _fold(text) for author in names):
            continue
        # Line by line: a piece is a creator's whole line, never part of a row set apart in
        # wide spaces ("Meta AI Research    WRI    Inria", 2508.10104), nor the spacing of a
        # line break printed as text ("[0.25cm]", ar5iv's 2105.15203).
        for line in _LATEX_SPACE_RE.sub("\n", name.get_text().replace("\xa0", " ")).split("\n"):
            piece = line.strip().strip(_EDGE_PUNCTUATION)
            # A qualifier in brackets is no piece: "(Guangzhou)" under its university (2609.33258).
            if (
                piece
                and not piece.startswith("(")
                and len(piece.split()) <= _MAX_PIECE_WORDS
                and not _NOISE_RE.search(piece)
                and not _INSTITUTION_WORD_RE.search(piece)
                and not _ADDRESS_END_RE.search(piece)
            ):
                return True
    return False


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

    Only footnotes that start with a marker qualify, as other footnotes of the front matter
    say anything ("This work has been submitted to..."): those that consist of
    institutions, or whose pieces up to their correspondence sentence, those that clean to
    nothing aside ("Equal contribution", a project page), qualify as a thanks note's list
    does (:func:`_listed_affiliations`): ICML's notice, "¹University of Tübingen. ²KAIST
    AI. Correspondence to: …" (2610.35857, 2610.35706), where "KAIST AI" names no
    institution and the correspondence ends the last piece.
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
    if all(_INSTITUTION_WORD_RE.search(segment) for segment in segments):
        return segments
    pieces: list[str] = []
    for segment in segments:
        kept = _CORRESPONDENCE_RE.sub("", segment)
        if clean_affiliations(kept):
            pieces.append(kept.strip(" ,;."))
        if kept != segment:
            break
    if not pieces or any(_SENTENCE_WORD_RE.search(piece) or _DOMAIN_RE.fullmatch(piece) for piece in pieces):
        return []
    named = [piece for piece in pieces if _INSTITUTION_WORD_RE.search(piece) or _ADDRESS_END_RE.search(piece)]
    return pieces if 2 * len(named) >= len(pieces) else []


def _listed_affiliations(notes: list[str]) -> list[str]:
    """The affiliations a thanks note lists without a sentence around them: the last source.

    IEEE conference classes, which IROS papers use, put the affiliations in thanks notes:
    as "A is with B" sentences (:func:`_stated_affiliations`), or alone, the whole note
    ("Department of Computer Science, University of Freiburg, Germany.", 2609.26325), a
    note each, numbered ("¹FZI Research Center for Information Technology, 76131
    Karlsruhe, Germany.", 2609.03677), or a numbered list after other sentences, whose
    markers LaTeXML printed as text ("$^1$University of Southern California, $^2$Stanford
    University", 2609.16443). A note qualifies when none of its pieces reads as a sentence
    or is a web domain, and at least half of them name an institution or end with a
    country: "UC San Diego" names none. Notes on funding and correspondence never do.
    Last, so that it only ever fills an empty page: of 166 thanks notes of 401 cached
    pages (2026-10-17), it read the 4 of these 3 papers, and a domain.
    """
    affiliations: list[str] = []
    for note in notes:
        pieces = marked_pieces(" ".join(_TEXT_MARKER_RE.sub(r" \1", note).split()))
        if len(pieces) > 1 and not pieces[0][:1].isdigit():
            # The sentences before a numbered list.
            pieces = pieces[1:]
        pieces = [stripped for piece in pieces if (stripped := piece.strip(" ,;."))]
        if not pieces or any(
            _SENTENCE_WORD_RE.search(piece) or _DOMAIN_RE.fullmatch(piece) for piece in pieces
        ):
            continue
        named = [
            piece for piece in pieces if _INSTITUTION_WORD_RE.search(piece) or _ADDRESS_END_RE.search(piece)
        ]
        if 2 * len(named) >= len(pieces):
            affiliations += pieces
    return affiliations


def _numbered_affiliations(authors: Tag) -> list[str]:
    """Affiliations written as numbered lines after the author names.

    Superscript markers are kept here: they are what identifies these lines. Each takes the
    lines after it that go on with it, up to the next marker, as :func:`_joined` joins
    them: blocks setting each affiliation as rows of a table ("¹ Department of Computer
    Science", then "Stony Brook University", 2609.38607) kept the unit alone (AQ-3).
    """
    return [name for _, name in _numbered_lines(_numbered_text(authors))]


def _dedupe(candidates: list[str]) -> tuple[str, ...]:
    seen: dict[str, str] = {}
    for candidate in candidates:
        for affiliation in clean_affiliations(candidate):
            seen.setdefault(affiliation.casefold(), affiliation)
    return tuple(seen.values())
