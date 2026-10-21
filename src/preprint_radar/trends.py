"""What the titles of a category's papers say, month by month: rising and cooling topics (PROD-20).

A topic is a phrase of the titles, one to four words: "world model", "vision-language-action
model", "VLA", "Mamba". It is keyed by its lower-case words, the last one singular, and named
as titles most often write it. A word alone is a topic of the lists only as an acronym
("VLA", "JEPA"): titles write too many words alone that name none ("evidence", "advancing");
the explorer has the others ("mamba", "transformer"). The weekly archive's catalog holds every
paper of the category since 2010 with its title: each month counts the papers whose title
says each phrase that enough papers say (the vocabulary). Titles only: they say what a paper
is about, where an abstract also names its tools and baselines.

Two windows compare the share of the papers a topic has: the last 90 days against the same
days a year before, which the conferences' seasons do not bias, and the last 12 months
against the 12 before. A topic rises when its share grows, ranked by its lift, the ratio of
its two shares with the share of a few papers added to each, so that one paper becoming six
does not lead; it cools when its share falls. Two phrases sharing half their papers are one
topic, and the more specific stays ("visual token pruning" over "visual token"). Topics that
first appeared within the last 12 months are listed apart.

Each listed topic keeps its counts of the last three years, the share of its papers among the
most cited tenth of their month (its impact), and its most cited papers of the last year. Every
topic of the vocabulary keeps its counts since 2010, for the site's explorer. The thresholds
scale with the category's size: cs.CV's are calibrated on its 210,000 papers (docs/trends.md).
"""

import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import date, timedelta

from preprint_radar.config import ARCHIVE_SINCE
from preprint_radar.models import KeyPaper, TopicSeries, Trends, TrendTopic, TrendWindow
from preprint_radar.sources.arxiv_oai import CatalogEntry

# Phrases of at most this many words, and this many parts once hyphens split them
# ("vision-language-action model" is two words, four parts).
MAX_WORDS = 4
MAX_PARTS = 6
# The vocabulary: phrases this share of the papers says, at least that many (32 for cs.CV).
VOCABULARY_SHARE = 0.00015
VOCABULARY_MIN = 5
# The windows, by name: the days of each period, and the share of the recent period's
# papers a topic needs to be ranked (31 papers of cs.CV's 10,476 of 90 days, 59 of 12 months).
WINDOWS = {"quarter": (90, 0.003), "year": (365, 0.0015)}
RANK_MIN = 10
# Topics a list names.
LIST_SIZE = 25
NEW_SIZE = 15
# Two phrases whose papers overlap this much (those they share, of those either has) are one
# topic.
SAME_TOPIC = 0.5
# A new topic: its first month with this many papers is within the last 12 months.
FIRST_PAPERS = 3
NEW_MONTHS = 12
# Months of a listed topic's counts: the last three years, and the month of the last day.
MONTHS = 37
# Its impact: of its papers of these months before the last, the share among the most cited
# tenth of their month (cs.CV: 54% for "world model", 4% for "semi-supervised"), with this
# many papers at least.
IMPACT_MONTHS = (3, 15)
IMPACT_MIN_PAPERS = 20
TOP_SHARE = 0.10
KEY_PAPERS = 3


def _words(text: str) -> frozenset[str]:
    """The words of a list written as text."""
    return frozenset(text.split())


# Function words, which neither start nor end a topic.
_FUNCTION = _words(
    """a an the of for with and or in on to via from by at as is are be using towards toward into
    under over through without beyond across based its their our we not do does can how what when
    why which more less than all any one two vs versus your you it this that these those up down
    out off about after before between during while within upon among against s"""
)
# Words of every title, whatever its topic: a phrase made of them alone, or with modifiers,
# is none ("comprehensive survey", "high-quality", "large-scale dataset").
_GENERIC = _words(
    """leveraging exploring rethinking revisiting novel comprehensive simple efficient effective
    improved improving enhanced enhancing better robust fast accurate unified general generalized
    scalable learning approach framework method model network study analysis result performance
    paper task system technique application algorithm new deep neural large small multi semi high
    quality survey review overview benchmark dataset"""
)
# Words that qualify a topic but never end one: "geometry-aware", "3D semantic", "pre-trained".
_MODIFIERS = _words(
    """semantic visual spatial temporal aware guided based driven free level scale wise agnostic
    specific invariant conditioned consistent oriented centric augmented enhanced assisted informed
    inspired powered preserving trained grounded"""
)
# Acronyms of every field, which name no topic alone, nor end one ("feed-forward 3D").
_GENERIC_ACRONYMS = frozenset({"2d", "3d", "4d", "ai", "rgb", "id", "ii", "iii", "iv", "gt"})
_NO_END = _FUNCTION | _MODIFIERS | _GENERIC_ACRONYMS
_COMMON = _FUNCTION | _GENERIC | _MODIFIERS
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+]*(?:-[A-Za-z0-9+]+)*")
# Where a title's phrases end: "Name: What It Does", lists, brackets, a dash between spaces.
_BREAK_RE = re.compile(r"[:;,.!?()\[\]{}\"\u201c\u201d]|\s[-\u2013\u2014]+\s")
_YEAR_RE = re.compile(r"^(?:19|20)\d\d$")
_ACRONYM_CAPITALS = 2
_MAX_ACRONYM = 10
_MAX_ALL_CAPS = 6
# Plurals shorter than these keep their last letters: "ties", "gas", "bus".
_SHORTEST_IES = 5
_SHORTEST_S = 4
# Words ending as plurals that are none: fields ("robotics", "graphics"), adjectives ("various").
_NOT_PLURAL = frozenset({"series", "species", "news", "lens", "bias", "atlas", "canvas", "alias", "chaos"})
_NOT_PLURAL_ENDINGS = ("ss", "us", "is", "ics", "ous")


@dataclass(frozen=True, slots=True)
class _Part:
    """A part of a title's word, hyphens split: as keyed, and as named."""

    key: str
    text: str
    acronym: bool


def _is_acronym(part: str) -> bool:
    """Whether a part is an acronym: two capitals or more within it ("NeRF", "VLA", "3DGS").

    A word of a title in capitals ("BENCHMARK") is not one.
    """
    capitals = sum(char.isupper() for char in part)
    shouted = part.isupper() and len(part) > _MAX_ALL_CAPS
    return capitals >= _ACRONYM_CAPITALS and len(part) <= _MAX_ACRONYM and not shouted


def _parts(word: str) -> list[_Part]:
    """A word's parts, hyphens split, each named as written if an acronym or short in capitals ("3D")."""
    parts: list[_Part] = []
    for part in word.split("-"):  # never empty: _WORD_RE has a letter or digit after each hyphen
        acronym = _is_acronym(part)
        as_written = acronym or (part.isupper() and len(part) <= _MAX_ALL_CAPS)
        parts.append(_Part(part.lower(), part if as_written else part.lower(), acronym))
    return parts


def _singular(word: str) -> str:
    """A title's plural, singular: "models" is "model", "patches" "patch", "fields" "field"."""
    if word in _NOT_PLURAL or word.endswith(_NOT_PLURAL_ENDINGS):
        return word
    if len(word) >= _SHORTEST_IES and word.endswith("ies"):
        return f"{word[:-3]}y"
    if word.endswith(("sses", "ches", "shes", "xes")):
        return word[:-2]
    if len(word) >= _SHORTEST_S and word.endswith("s"):
        return word[:-1]
    return word


def _singular_text(part: _Part) -> str:
    """A part as named, singular: an acronym's plural "s" goes ("VLMs" is "VLM")."""
    if part.acronym:
        return part.text[:-1] if part.text.endswith("s") and part.text[-2:-1].isupper() else part.text
    return _singular(part.text)


def _a_topic(words: list[list[_Part]]) -> bool:
    """Whether words of a title make a topic: what they start and end with, and say.

    Words are taken as written and singular: "networks" is generic, as "network" is.
    """
    parts = [part for word in words for part in word]
    keys = [part.key for part in parts]
    if keys[0] in _FUNCTION or {keys[-1], _singular(keys[-1])} & _NO_END:
        return False
    if any(_YEAR_RE.match(key) for key in keys):
        return False
    if len(parts) == 1 and parts[0].acronym:
        return True
    return not all(key in _COMMON or _singular(key) in _COMMON for key in keys)


def title_phrases(title: str) -> dict[str, str]:
    """The topics a title says, by key, each named as the title writes it.

    A phrase starts with a word and ends with one, hyphens included: "Semi-Supervised Medical
    Image Segmentation" says "semi-supervised medical image segmentation", never "supervised
    medical image"; nor does it cross punctuation: "VLMs Are Blind: Rethinking NeRF" says
    "rethinking NeRF", never "blind rethinking".

    Args:
        title: A paper's title.

    Returns:
        Each phrase's name, by its key: lower-case words, the last singular.
    """
    phrases: dict[str, str] = {}
    for segment in _BREAK_RE.split(title):
        words = [_parts(word) for word in _WORD_RE.findall(segment)]
        for first in range(len(words)):
            for last in range(first, min(first + MAX_WORDS, len(words))):
                span = words[first : last + 1]
                parts = [part for word in span for part in word]
                if len(parts) > MAX_PARTS:
                    break
                if not _a_topic(span):
                    continue
                key = " ".join([*(part.key for part in parts[:-1]), _singular(parts[-1].key)])
                named = [[part.text for part in word] for word in span]
                named[-1][-1] = _singular_text(span[-1][-1])
                phrases.setdefault(key, " ".join("-".join(word) for word in named))
    return phrases


def _month(day: date) -> int:
    """The index of a day's month among those since ``ARCHIVE_SINCE``."""
    return (day.year - ARCHIVE_SINCE.year) * 12 + day.month - ARCHIVE_SINCE.month


def _month_name(index: int) -> str:
    year, month = divmod(ARCHIVE_SINCE.month - 1 + index, 12)
    return f"{ARCHIVE_SINCE.year + year}-{month + 1:02d}"


@dataclass(frozen=True, slots=True)
class _Paper:
    arxiv_id: str
    day: date
    title: str
    topics: frozenset[str]


@dataclass(frozen=True, slots=True)
class _Period:
    """The papers of a window's two periods, and those of each topic in them."""

    then: tuple[date, date]
    now: tuple[date, date]
    papers: tuple[int, int]
    before: Mapping[str, frozenset[str]]
    after: Mapping[str, frozenset[str]]


def count_trends(entries: Iterable[CatalogEntry], citations: Mapping[str, int | None]) -> Trends:
    """The topics of a category's papers since 2010, rising, cooling and new.

    Args:
        entries: The category's catalog.
        citations: The papers' citation counts, for the topics' impact and key papers; none
            leaves both out.

    Returns:
        The topics, their counts and the lists of each window.

    Raises:
        ValueError: If the catalog holds no paper since 2010.
    """
    titled = [entry for entry in entries if entry.first_seen >= ARCHIVE_SINCE]
    if not titled:
        msg = "The catalog holds no paper since 2010"
        raise ValueError(msg)
    said: Counter[str] = Counter()
    for entry in titled:
        said.update(title_phrases(entry.title).keys())
    minimum = max(VOCABULARY_MIN, round(len(titled) * VOCABULARY_SHARE))
    vocabulary = {key for key, papers in said.items() if papers >= minimum}

    through = max(entry.first_seen for entry in titled)
    months = _month(through) + 1
    totals = [0] * months
    counts: defaultdict[str, list[int]] = defaultdict(lambda: [0] * months)
    names: defaultdict[str, Counter[str]] = defaultdict(Counter)
    papers: list[_Paper] = []
    for entry in titled:
        phrases = {key: name for key, name in title_phrases(entry.title).items() if key in vocabulary}
        month = _month(entry.first_seen)
        totals[month] += 1
        for key, name in phrases.items():
            counts[key][month] += 1
            names[key][name] += 1
        papers.append(_Paper(entry.arxiv_id, entry.first_seen, entry.title, frozenset(phrases)))
    # The name titles write most often; the first in order among those as frequent.
    named = {
        key: min(spelled.items(), key=lambda item: (-item[1], item[0]))[0] for key, spelled in names.items()
    }
    # The lists rank phrases and acronyms; the explorer has every topic.
    ranked = {key for key in vocabulary if " " in key or _is_acronym(named[key])}
    papers = [replace(paper, topics=paper.topics & ranked) for paper in papers]

    windows: dict[str, TrendWindow] = {}
    periods: dict[str, _Period] = {}
    for name, (days, share) in WINDOWS.items():
        period = _period(papers, through, days)
        periods[name] = period
        windows[name] = _ranked(period, counts, days, share, months)
    listed = sorted(
        {key for window in windows.values() for key in (*window.rising, *window.cooling, *window.new)}
    )
    impact = _ImpactCounter(papers, citations, months)
    topics = {
        key: TrendTopic(
            name=named[key],
            counts=tuple(counts[key][-MONTHS:]),
            windows={
                name: (len(period.before.get(key, ())), len(period.after.get(key, ())))
                for name, period in periods.items()
            },
            first=_first_month(counts[key]),
            impact=impact.share(key),
            papers=_key_papers(papers, key, through, citations),
        )
        for key in listed
    }
    series = {key: _series(named[key], counts[key]) for key in sorted(vocabulary)}
    return Trends(
        through=through,
        start=_month_name(0),
        totals=tuple(totals),
        windows=windows,
        topics=topics,
        months=MONTHS,
        series=series,
    )


def _period(papers: Iterable[_Paper], through: date, days: int) -> _Period:
    """The papers of the last ``days`` days, and of the same days a year before them."""
    now = (through - timedelta(days=days - 1), through)
    then = (now[0] - timedelta(days=365), now[1] - timedelta(days=365))
    before: defaultdict[str, set[str]] = defaultdict(set)
    after: defaultdict[str, set[str]] = defaultdict(set)
    counted = [0, 0]
    for paper in papers:
        for index, (start, end), topics in ((0, then, before), (1, now, after)):
            if start <= paper.day <= end:
                counted[index] += 1
                for key in paper.topics:
                    topics[key].add(paper.arxiv_id)
    return _Period(
        then=then,
        now=now,
        papers=(counted[0], counted[1]),
        before={key: frozenset(ids) for key, ids in before.items()},
        after={key: frozenset(ids) for key, ids in after.items()},
    )


def _ranked(
    period: _Period, counts: Mapping[str, list[int]], days: int, share: float, months: int
) -> TrendWindow:
    """A window's rising, cooling and new topics."""
    then_papers, now_papers = period.papers
    minimum = max(RANK_MIN, round(share * now_papers))
    # The share added to both sides of the lift: a few papers of the recent period, for the
    # smallest topics ranked. The same on both sides, so that a share that holds lifts by 1.
    added = max(3, minimum // 3) / max(now_papers, 1)

    def lift(key: str) -> float:
        now = len(period.after.get(key, ())) / max(now_papers, 1)
        then = len(period.before.get(key, ())) / max(then_papers, 1)
        return (now + added) / (then + added)

    # A topic rises only if its share grows, and cools only if it falls: a small category
    # has fewer topics than a list.
    rising = sorted(
        (key for key, ids in period.after.items() if len(ids) >= minimum and lift(key) > 1),
        key=lambda key: (-lift(key), key),
    )
    cooling = sorted(
        (key for key, ids in period.before.items() if len(ids) >= minimum and lift(key) < 1),
        key=lambda key: (lift(key), key),
    )
    recent = max(FIRST_PAPERS, minimum // 2)
    new = sorted(
        (
            key
            for key, ids in period.after.items()
            if len(ids) >= recent
            and (first := _first_index(counts[key])) is not None
            and first >= months - NEW_MONTHS
        ),
        key=lambda key: (-len(period.after[key]), key),
    )
    return TrendWindow(
        days=days,
        earlier=period.then,
        recent=period.now,
        papers=period.papers,
        rising=_distinct(rising, period.after, LIST_SIZE),
        cooling=_distinct(cooling, period.before, LIST_SIZE),
        new=_distinct(new, period.after, NEW_SIZE),
        added=round(added, 8),
    )


def _distinct(ranked: list[str], papers: Mapping[str, frozenset[str]], size: int) -> tuple[str, ...]:
    """The first ``size`` topics of a ranking, one phrase for each.

    A phrase sharing half its papers with one ranked before it (of those either has) is the
    same topic, which the more specific of the two names, in the place of the first: "visual
    token pruning" over "visual token", even ranked past the list's end.
    """
    kept: list[str] = []
    for key in ranked:
        mine = papers[key]
        same = next(
            (
                index
                for index, other in enumerate(kept)
                if len(mine & papers[other]) >= SAME_TOPIC * len(mine | papers[other])
            ),
            None,
        )
        if same is None:
            if len(kept) < size:
                kept.append(key)
        elif len(key.split()) > len(kept[same].split()):
            kept[same] = key
    return tuple(kept)


def _series(name: str, counts: list[int]) -> TopicSeries:
    """A topic's counts from the month of its first paper."""
    start = next(month for month, papers in enumerate(counts) if papers)
    return TopicSeries(name, start, tuple(counts[start:]))


def _first_index(counts: list[int]) -> int | None:
    """The first month with ``FIRST_PAPERS`` papers of a topic, if any."""
    return next((month for month, papers in enumerate(counts) if papers >= FIRST_PAPERS), None)


def _first_month(counts: list[int]) -> str | None:
    first = _first_index(counts)
    return None if first is None else _month_name(first)


class _ImpactCounter:
    """The topics' impact: their papers' share among the most cited tenth of their month."""

    def __init__(self, papers: list[_Paper], citations: Mapping[str, int | None], months: int) -> None:
        self._papers = papers
        self._citations = citations
        self._months = range(months - 1 - IMPACT_MONTHS[1], months - IMPACT_MONTHS[0])
        by_month: defaultdict[int, list[int]] = defaultdict(list)
        for paper in papers:
            by_month[_month(paper.day)].append(citations.get(paper.arxiv_id) or 0)
        # The citations of the last paper of each month's most cited tenth.
        self._cutoffs = {
            month: sorted(cited, reverse=True)[max(math.ceil(len(cited) * TOP_SHARE), 1) - 1]
            for month, cited in by_month.items()
        }

    def share(self, key: str) -> float | None:
        """Of the topic's papers of the impact's months, the share among their month's most cited tenth."""
        if not self._citations:
            return None
        cited = [
            (self._citations.get(paper.arxiv_id) or 0) >= max(self._cutoffs[_month(paper.day)], 1)
            for paper in self._papers
            if key in paper.topics and _month(paper.day) in self._months
        ]
        return round(sum(cited) / len(cited), 3) if len(cited) >= IMPACT_MIN_PAPERS else None


def _key_papers(
    papers: Iterable[_Paper], key: str, through: date, citations: Mapping[str, int | None]
) -> tuple[KeyPaper, ...]:
    """A topic's most cited papers of the last 12 months, cited at least once."""
    since = through - timedelta(days=364)
    cited = sorted(
        (
            (citations.get(paper.arxiv_id) or 0, paper)
            for paper in papers
            if key in paper.topics and paper.day >= since
        ),
        key=lambda item: (-item[0], item[1].arxiv_id),
    )
    return tuple(KeyPaper(paper.arxiv_id, paper.title, count) for count, paper in cited[:KEY_PAPERS] if count)


TITLES_SOURCE = "arXiv"
"""Where the titles come from, as ``trends.json`` and ``topics.json`` say."""
TRENDS_SOURCE = "arXiv, Semantic Scholar"
"""The same, with the citation counts of the topics' impact and key papers."""


def format_trends_report(category: str, trends: Trends) -> str:
    """Render what :func:`count_trends` counted as one line, with the window of 90 days' first rising topics.

    Args:
        category: arXiv category.
        trends: The topics counted.
    """
    window = trends.windows["quarter"]
    leading = ", ".join(trends.topics[key].name for key in window.rising[:3])
    return (
        f"{category}: {len(trends.series):,} topics of {sum(trends.totals):,} papers to "
        f"{trends.through.isoformat()}; last {window.days} days: {len(window.rising)} rising"
        f"{f' ({leading}…)' if leading else ''}, {len(window.cooling)} cooling, {len(window.new)} new"
    )
