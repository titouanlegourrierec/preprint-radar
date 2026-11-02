"""Quality of the stored affiliations: signs of what the extraction heuristics got wrong.

``stats`` measures coverage, how many papers have affiliations; this measures correctness,
through signs of the failures seen so far, each counted with a few examples. Run it
before and after a change to ``sources/arxiv_html.py`` (``stats --affiliations``): with
``--page-cache-dir``, it also measures what today's extraction gives for the cached pages,
next to what is stored for those papers, and with ``--changes`` lists the papers that
change (``make extraction-diff``).

The signs are heuristic: a few strings they flag are fine ("Department of Computer
Science" is a whole affiliation when its institution is written on another line), and
they miss what nobody has described yet.
"""

import re
import unicodedata
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from rich import box
from rich.table import Table

from preprint_radar.affiliations.cleaning import (
    clean_affiliations,
    is_bare_unit,
    is_place,
    marked_pieces,
    names_only_authors,
)
from preprint_radar.models import Paper, Provenance
from preprint_radar.sources.arxiv_html import EXTRACTOR_VERSION, PageCache, parse_front_matter

EXAMPLES = 5
"""Examples kept for each sign."""

# Two affiliations written as one, without a separator: "Dept. of Computer
# ScienceUniversity of Alabama". "VinUniversity" and "AnimSchool" are names, hence four
# lowercase letters before the word (AQ-1). Those run together by plain-text markers ("Monash University;
# 2Southeast University") are found as cleaning splits them, postcodes apart.
_GLUED_RE = re.compile(
    r"[a-z]{4}(?:Universit|Institut|School|Department|College|Laborator|Cent(?:er|re)|Faculty|Hospital)"
)
# The start or the end of a phrase lost to a line break or a marker: "th Research Institute"
# (from "54th"), "Department of Computer Science and". Lowercase only: "St Lucia" starts
# a name, and "TU Wien, AT" ends with a country code.
_CUT_OFF_RE = re.compile(r"^(?:st|nd|rd|th)\s|(?:\b(?:and|of|for|the|at|in)|[&,(-])$")
# A place that starts the string, so that no institution precedes it: a city and its state
# ("Raleigh, NC, USA"), a city and its postcode ("Beijing 100084, China"), a street number.
# "Tokyo, Japan" cannot be told from "Tencent, China", and is not counted.
# A state is followed by a postcode or the country; "UMR 5505" is a French research unit.
_PLACE_START_RE = re.compile(r"[^,\d]+,\s*(?!UMR)[A-Z]{2,3}\s*(?:\d|,)|[^,\d]+\s\d[\d\s-]{2,}(?:,|$)|\d")
# What starts an institution, not a place, before a place's comma: "Mayo Clinic, MN, USA",
# "ICT, CAS, Beijing, China", "LIGM, UGE, ENPC, CNRS, France" (AQ-1).
_NOT_A_PLACE_RE = re.compile(
    r"clinic|hospital|univ|institut|lab|cent(?:er|re)|college|school|(?-i:^[A-Z]{2,}\b)", re.IGNORECASE
)
# TeX left in a string: "$1$ University of ...", "\textsuperscript".
_TEX_RE = re.compile(r"\$|\\[A-Za-z]")
# A note's sentence, or a link's or a note's label, stored as an affiliation.
_NOTE_RE = re.compile(
    r"^(?:(?:This|These|The\s+work|The\s+authors?|Work|Part\s+of\s+this|Manuscript|Supported\s+by|Funded\s+by)\s+[a-z]"
    r"|(?:Project(?:\s+page)?|Code|Equal(?:\s+contribution)?|Links?|Lead\s+authors?|Website|Homepage|GitHub)$)",
    re.IGNORECASE,
)
# A list of affiliations in one string, split by semicolons: "Zhejiang University; Alibaba
# Group; Shanghai AI Lab" (2510.18873). A unit's list leads to its institution
# ("Departments of Radiology; Neurological Surgery; ..., Indiana University").
_LIST_PARTS = 3
# What an "A is with X" sentence leaves when it is not reduced to X.
_STATEMENT_RE = re.compile(r"\b(?:is|are)\s+(?:also\s+)?(?:with|at)\b", re.IGNORECASE)


class Sign(StrEnum):
    """A sign that an affiliation string, or a paper's author mapping, is wrong."""

    NAMES = "names authors"
    CLEANING = "cleaned again"
    STATEMENT = "is with"
    GLUED = "glued"
    CUT_OFF = "cut off"
    UNIT_ONLY = "unit only"
    PLACE_ONLY = "place only"
    RESIDUE = "residue"
    NOTE = "note"
    LIST = "list"
    LAST_HOLDS_ALL = "last holds all"
    PLACED_NOWHERE = "placed at a unit"

    @property
    def description(self) -> str:
        """What the sign means, for the report."""
        return _DESCRIPTIONS[self]


_DESCRIPTIONS = {
    Sign.NAMES: "only names authors of the paper",
    Sign.CLEANING: "today's cleaning rejects or changes it (`reclean` would)",
    Sign.STATEMENT: 'a sentence about people ("A is with X")',
    Sign.GLUED: "two affiliations in one string",
    Sign.CUT_OFF: "a start or an end lost to a line break or a marker",
    Sign.UNIT_ONLY: "a department or school without its institution",
    Sign.PLACE_ONLY: "a city or an address without its institution",
    Sign.RESIDUE: "TeX, an invisible character or a leading symbol left in it",
    Sign.NOTE: "a note's sentence, or a link's or a note's label",
    Sign.LIST: "several affiliations split by semicolons",
    Sign.LAST_HOLDS_ALL: "papers whose last author alone is placed, at every affiliation",
    Sign.PLACED_NOWHERE: "papers with an author placed only at units or places",
}


@dataclass(slots=True)
class Tally:
    """How often a sign was seen.

    Attributes:
        strings: Affiliation strings with the sign (papers, for a paper-level sign).
        papers: Papers with at least one of them.
        examples: The first few, as ``"<arXiv id>: <string>"``.
    """

    strings: int = 0
    papers: int = 0
    examples: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AffiliationQuality:
    """The signs seen in a set of papers.

    Attributes:
        papers: Papers with at least one affiliation, all looked at.
        strings: Their affiliation strings.
        tallies: Per sign, in the order of :class:`Sign`.
    """

    papers: int = 0
    strings: int = 0
    tallies: dict[Sign, Tally] = field(default_factory=lambda: {sign: Tally() for sign in Sign})


def affiliation_quality(papers: Iterable[Paper]) -> AffiliationQuality:
    """Count the signs of wrong affiliations in ``papers``.

    Args:
        papers: Papers of day files. OpenAlex's names, those of archived papers and of day
            files' papers without an HTML page (AFF-27), are left out: these signs do not
            describe them.

    Returns:
        The tallies, with up to :data:`EXAMPLES` examples each.
    """
    quality = AffiliationQuality()
    for paper in papers:
        if not paper.affiliations or paper.affiliations_from_openalex or paper.affiliations_by_hand:
            continue
        quality.papers += 1
        quality.strings += len(paper.affiliations)
        seen: set[Sign] = set()
        for affiliation in paper.affiliations:
            for sign in string_signs(affiliation, paper):
                _count(quality.tallies[sign], f"{paper.arxiv_id}: {affiliation}")
                seen.add(sign)
        for sign, holds in ((Sign.LAST_HOLDS_ALL, last_holds_all), (Sign.PLACED_NOWHERE, placed_nowhere)):
            if holds(paper):
                _count(quality.tallies[sign], paper.arxiv_id)
                seen.add(sign)
        for sign in seen:
            quality.tallies[sign].papers += 1
    return quality


def _count(tally: Tally, example: str) -> None:
    tally.strings += 1
    if len(tally.examples) < EXAMPLES:
        tally.examples.append(example)


def string_signs(affiliation: str, paper: Paper) -> Iterator[Sign]:
    """The signs that one affiliation string of ``paper`` is wrong.

    Args:
        affiliation: One of the paper's affiliation strings.
        paper: The paper, whose authors and other strings some signs compare it with.
    """
    held = {
        Sign.NAMES: affiliation in names_only(paper),
        Sign.CLEANING: clean_affiliations(affiliation) != (affiliation,),
        Sign.STATEMENT: _STATEMENT_RE.search(affiliation) is not None,
        Sign.GLUED: _GLUED_RE.search(affiliation) is not None or len(marked_pieces(affiliation)) > 1,
        Sign.CUT_OFF: _CUT_OFF_RE.search(affiliation) is not None,
        Sign.UNIT_ONLY: is_bare_unit(affiliation),
        Sign.PLACE_ONLY: _place_only(affiliation),
        Sign.RESIDUE: _residue(affiliation),
        Sign.NOTE: _NOTE_RE.match(affiliation) is not None,
        Sign.LIST: affiliation.count(";") >= _LIST_PARTS - 1,
    }
    yield from (sign for sign, holds in held.items() if holds)


def _place_only(affiliation: str) -> bool:
    return (
        is_place(affiliation)
        and _PLACE_START_RE.match(affiliation) is not None
        and not _NOT_A_PLACE_RE.search(affiliation.split(",", 1)[0])
    )


def _residue(affiliation: str) -> bool:
    """TeX, an invisible (Cf) character, or a leading symbol other than a bracket or a quote."""
    return (
        _TEX_RE.search(affiliation) is not None
        or any(unicodedata.category(char) == "Cf" for char in affiliation)
        or not (affiliation[:1].isalnum() or affiliation[:1] in "(\"'\u201c\u2018")
    )


def names_only(paper: Paper) -> list[str]:
    """The affiliations of ``paper`` that only name its authors.

    A string the registry named stays: a collective that signs as an author.
    """
    affiliations = paper.affiliations or ()
    institutions = paper.institutions or (None,) * len(affiliations)
    return [
        affiliation
        for affiliation, institution in zip(affiliations, institutions, strict=True)
        if institution is None and names_only_authors(affiliation, paper.authors)
    ]


def last_holds_all(paper: Paper) -> bool:
    """Whether only the last of several authors is placed, at every affiliation.

    LaTeXML attaches an author block shared by everyone to the last author: the mapping
    then says nothing about who is where.
    """
    mapping = paper.author_affiliations
    return (
        mapping is not None
        and len(mapping) > 1
        and all(entry is None for entry in mapping[:-1])
        and set(mapping[-1] or ()) == set(range(len(paper.affiliations or ())))
    )


def placed_nowhere(paper: Paper) -> bool:
    """Whether an author is placed, but only at departments or places without their institution.

    "Department of Computer Science" for everyone, the institution on a line the extraction
    lost (2609.38607), or a city read as an affiliation ("Pittsburgh, PA, USA"). A company
    and its city ("Saab AB, Linköping, Sweden") cannot be told from a place, which an
    institution named by the rules alone would sign too ("Seoul, Korea" named "Seoul"):
    neither is counted (AQ-1).
    """
    affiliations = paper.affiliations or ()
    return any(
        entry
        and all(is_bare_unit(affiliations[index]) or _place_only(affiliations[index]) for index in entry)
        for entry in paper.author_affiliations or ()
    )


def extracted_again(papers: Iterable[Paper], cache: PageCache) -> list[tuple[Paper, Paper]]:
    """The papers whose page is cached, with what today's extraction gives for them.

    Nothing is fetched, and the papers are not changed: this measures a change to the
    heuristics before ``reextract`` applies it.

    Args:
        papers: Stored papers.
        cache: The page cache.

    Returns:
        ``(stored, extracted)`` pairs, the extracted paper carrying today's affiliations,
        author mapping and :data:`EXTRACTOR_VERSION`.
    """
    pairs: list[tuple[Paper, Paper]] = []
    for paper in papers:
        html = cache.get(paper.html_url) if paper.html_url else None
        if html is None:
            continue
        front = parse_front_matter(html, authors=paper.authors)
        extracted = paper.with_affiliations(
            front.affiliations,
            front.author_affiliations,
            provenance=Provenance("html"),
            extractor=EXTRACTOR_VERSION,
        )
        pairs.append((paper, extracted))
    return pairs


@dataclass(frozen=True, slots=True)
class ExtractionChange:
    """What today's extraction changes for one stored paper whose page is cached.

    Attributes:
        arxiv_id: The paper.
        removed: Stored affiliations that the extraction no longer gives.
        added: Affiliations it gives that are not stored.
        remapped: Whether who is where changes.
        lost: Words of the stored affiliations found in none of the new ones: author names
            and noise are expected, an institution's is a regression.
    """

    arxiv_id: str
    removed: tuple[str, ...]
    added: tuple[str, ...]
    remapped: bool
    lost: tuple[str, ...]


# Words compared for :attr:`ExtractionChange.lost`: three letters or more, case folded.
_WORD_RE = re.compile(r"[^\W\d_]{3,}")


def extraction_changes(pairs: Iterable[tuple[Paper, Paper]]) -> list[ExtractionChange]:
    """The papers of :func:`extracted_again` whose affiliations or mapping change.

    Those that would lose words come first: run it before bumping ``EXTRACTOR_VERSION``,
    as each version from 3 to 7 fixed what the one before lost.

    Args:
        pairs: ``(stored, extracted)`` pairs.

    Returns:
        The changes, those losing words first, then by identifier.
    """
    changes: list[ExtractionChange] = []
    for stored, extracted in pairs:
        old, new = stored.affiliations or (), extracted.affiliations or ()
        remapped = stored.author_affiliations != extracted.author_affiliations
        if old == new and not remapped:
            continue
        changes.append(
            ExtractionChange(
                arxiv_id=stored.arxiv_id,
                removed=tuple(affiliation for affiliation in old if affiliation not in new),
                added=tuple(affiliation for affiliation in new if affiliation not in old),
                remapped=remapped,
                lost=tuple(sorted(_words(old) - _words(new))),
            )
        )
    return sorted(changes, key=lambda change: (not change.lost, change.arxiv_id))


def _words(affiliations: Iterable[str]) -> set[str]:
    return {word for affiliation in affiliations for word in _WORD_RE.findall(affiliation.casefold())}


def format_changes(title: str, papers: int, changes: Sequence[ExtractionChange]) -> str:
    """The changes as text: a summary line, then each paper, its lost words flagged.

    Args:
        title: What the papers are, e.g. ``"cs.CV"``.
        papers: Papers compared (those with a cached page).
        changes: From :func:`extraction_changes`.
    """
    losing = sum(bool(change.lost) for change in changes)
    lines = [f"{title}: {len(changes)} of {papers} cached papers change, {losing} losing words"]
    for change in changes:
        lines.append(change.arxiv_id + ("  (who is where changes)" if change.remapped else ""))
        lines += [f"  - {affiliation}" for affiliation in change.removed]
        lines += [f"  + {affiliation}" for affiliation in change.added]
        if change.lost:
            lines.append(f"  ! words lost: {', '.join(change.lost)}")
    return "\n".join(lines)


def format_quality(title: str, quality: AffiliationQuality, *, examples: bool = True) -> str:
    """Render the tallies as plain text: one line per sign, then its examples.

    Args:
        title: The first line.
        quality: The tallies.
        examples: Whether to list the examples of each sign.

    Returns:
        The report, one sign a line.
    """
    width = max(len(sign) for sign in Sign)
    lines = [title, _overview(quality), f"{'sign':<{width}}  {'strings':>7}  {'papers':>6}"]
    for sign, tally in quality.tallies.items():
        lines.append(f"{sign:<{width}}  {tally.strings:>7,}  {tally.papers:>6,}  {sign.description}")
        if examples:
            lines.extend(f"{'':<{width}}    {example}" for example in tally.examples)
    return "\n".join(lines)


def quality_table(title: str, quality: AffiliationQuality) -> Table:
    """:func:`format_quality` as a rich table, for a terminal.

    Args:
        title: The table's title.
        quality: The counts and examples to show.
    """
    table = Table(
        title=title,
        title_justify="left",
        title_style="bold",
        caption=_overview(quality),
        caption_justify="left",
        header_style="bold cyan",
        box=box.SIMPLE_HEAD,
    )
    table.add_column("sign", style="bold")
    table.add_column("strings", justify="right")
    table.add_column("papers", justify="right")
    table.add_column("examples")
    for sign, tally in quality.tallies.items():
        table.add_row(sign, f"{tally.strings:,}", f"{tally.papers:,}", _examples(sign, tally.examples))
    return table


def _examples(sign: Sign, examples: Sequence[str]) -> str:
    return "\n".join((f"[dim]{sign.description}[/dim]", *(_escape(example) for example in examples)))


def _escape(text: str) -> str:
    """Text shown as is by rich, whose markup uses square brackets."""
    return text.replace("[", r"\[")


def _overview(quality: AffiliationQuality) -> str:
    strings = f"{quality.strings:,} affiliation string{'' if quality.strings == 1 else 's'}"
    return f"{strings} in {quality.papers:,} paper{'' if quality.papers == 1 else 's'}"
