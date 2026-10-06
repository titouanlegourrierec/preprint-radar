"""Quality of the stored affiliations: signs of what the extraction heuristics got wrong.

``stats`` measures coverage, how many papers have affiliations; this measures correctness,
through signs of the failures seen so far, each counted with a few examples. Run it
before and after a change to ``sources/arxiv_html.py`` (``stats --affiliations``): with
``--page-cache``, it also measures what today's extraction gives for the cached pages,
next to what is stored for those papers.

The signs are heuristic: a few strings they flag are fine ("Department of Computer
Science" is a whole affiliation when its institution is written on another line), and
they miss what nobody has described yet.
"""

import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum

from rich import box
from rich.table import Table

from preprint_radar.models import Paper
from preprint_radar.sources.arxiv_html import (
    EXTRACTOR_VERSION,
    PageCache,
    clean_affiliations,
    is_bare_unit,
    is_place,
    names_only_authors,
    parse_front_matter,
)

EXAMPLES = 5
"""Examples kept for each sign."""

# Two affiliations written as one, without a separator: "Dept. of Computer
# ScienceUniversity of Alabama", or with plain-text markers: "Monash University; 2Southeast
# University". "VinUniversity" is a name, hence three lowercase letters before the word.
_GLUED_RE = re.compile(
    r"[a-z]{3}(?:Universit|Institut|School|Department|College|Laborator|Cent(?:er|re)|Faculty|Hospital)"
    r"|[A-Za-z)][;,]?\s\d{1,2}(?=[A-Z])"
)
# The start or the end of a phrase lost to a line break or a marker: "th Research Institute"
# (from "54th"), "Department of Computer Science and". Lowercase starts only: "St Lucia".
_CUT_OFF_RE = re.compile(r"^(?:st|nd|rd|th)\s|(?i:\b(?:and|of|for|the|at|in)|[&,(-])$")
# A place that starts the string, so that no institution precedes it: a city and its state
# ("Raleigh, NC, USA"), a city and its postcode ("Beijing 100084, China"), a street number.
# "Tokyo, Japan" cannot be told from "Tencent, China", and is not counted.
# A state is followed by a postcode or the country; "UMR 5505" is a French research unit.
_PLACE_START_RE = re.compile(r"[^,\d]+,\s*(?!UMR)[A-Z]{2,3}\s*(?:\d|,)|[^,\d]+\s\d[\d\s-]{2,}(?:,|$)|\d")
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
    LAST_HOLDS_ALL = "last holds all"

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
    Sign.LAST_HOLDS_ALL: "papers whose last author alone is placed, at every affiliation",
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
        papers: Papers of day files. Archived papers carry OpenAlex names, which these
            signs do not describe.

    Returns:
        The tallies, with up to :data:`EXAMPLES` examples each.
    """
    quality = AffiliationQuality()
    for paper in papers:
        if not paper.affiliations:
            continue
        quality.papers += 1
        quality.strings += len(paper.affiliations)
        seen: set[Sign] = set()
        for affiliation in paper.affiliations:
            for sign in string_signs(affiliation, paper):
                _count(quality.tallies[sign], f"{paper.arxiv_id}: {affiliation}")
                seen.add(sign)
        if last_holds_all(paper):
            _count(quality.tallies[Sign.LAST_HOLDS_ALL], paper.arxiv_id)
            seen.add(Sign.LAST_HOLDS_ALL)
        for sign in seen:
            quality.tallies[sign].papers += 1
    return quality


def _count(tally: Tally, example: str) -> None:
    tally.strings += 1
    if len(tally.examples) < EXAMPLES:
        tally.examples.append(example)


def string_signs(affiliation: str, paper: Paper) -> Iterator[Sign]:
    """The signs that one affiliation string of ``paper`` is wrong."""
    if affiliation in names_only(paper):
        yield Sign.NAMES
    if clean_affiliations(affiliation) != (affiliation,):
        yield Sign.CLEANING
    if _STATEMENT_RE.search(affiliation):
        yield Sign.STATEMENT
    if _GLUED_RE.search(affiliation):
        yield Sign.GLUED
    if _CUT_OFF_RE.search(affiliation):
        yield Sign.CUT_OFF
    if is_bare_unit(affiliation):
        yield Sign.UNIT_ONLY
    if is_place(affiliation) and _PLACE_START_RE.match(affiliation):
        yield Sign.PLACE_ONLY


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
        extracted = replace(
            paper,
            affiliations=front.affiliations,
            author_affiliations=front.author_affiliations,
            institutions=None,
            institution_ids=None,
            extractor=EXTRACTOR_VERSION,
        )
        pairs.append((paper, extracted))
    return pairs


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
    """:func:`format_quality` as a rich table, for a terminal."""
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
