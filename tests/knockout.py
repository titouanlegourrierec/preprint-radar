"""Knock out the extraction's rules one at a time, to find those no test needs (EXT-2).

Line and branch coverage cannot see a rule written as one alternative of a regular
expression. Here each regular expression of ``sources/arxiv_html.py`` is made to never
match, whole, then each of its top-level alternatives in turn (a country of ``COUNTRIES``
and what a negative lookaround holds aside), and the extraction's tests run against it. A
knockout that leaves them green is a rule no test asserts on. With the page cache and
``data/``, each of those is replayed on the cached pages and the stored affiliations: one
that changes what they give is a live rule without a test, which the next
``EXTRACTOR_VERSION`` bump could lose unseen. Give it a fixture or a named test.

    make knockout                    # every rule: about 10 minutes on 10 cores
    make knockout REGEX=_HOST_RE     # those of one expression

Exits 1 when a live rule has no test.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from preprint_radar.console import console
from preprint_radar.sources import arxiv_html
from preprint_radar.store.paper_store import PaperStore

ROOT = Path(__file__).parents[1]
# The tests that read the extraction, directly or through what it stored.
TESTS = [
    f"tests/unit/{name}.py"
    for name in (
        "test_arxiv_html",
        "test_golden_fixtures",
        "test_reclean",
        "test_quality",
        "test_institutions",
        "test_naming",
        "test_arxiv_api",
        "test_validate",
        "test_collect",
    )
]
NEVER = "(?!)"


@dataclass(frozen=True, slots=True)
class Knockout:
    """One rule made to never match.

    Attributes:
        regex: The module-level name of the regular expression.
        label: What no longer matches: an alternative, or the whole expression.
        pattern: The expression without it.
        flags: The expression's flags.
    """

    regex: str
    label: str
    pattern: str
    flags: int

    def apply(self) -> None:
        """Put the knocked-out expression in the module, in place of the rule's."""
        setattr(arxiv_html, self.regex, re.compile(self.pattern, self.flags))


def top_alternatives(pattern: str) -> list[tuple[int, int]]:
    """The start and end of each alternative of a pattern's outermost alternations.

    Those of the least nested groups holding a ``|``, outside negative lookarounds (whose
    alternatives knocked out would match more, not less); a character class or an escape
    holds none.
    """
    found: list[tuple[int, int, int]] = []
    # Each open group: where its content starts, its depth, its splits, whether negative.
    stack: list[tuple[int, int, list[int], bool]] = [(0, 0, [], False)]
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\":
            index += 2
            continue
        if char == "[":
            index = _class_end(pattern, index)
            continue
        if char == "(":
            start = _group_start(pattern, index)
            negative = stack[-1][3] or pattern.startswith(("(?!", "(?<!"), index)
            stack.append((start, len(stack), [], negative))
            index = start
            continue
        if char == ")":
            found.extend(_split(stack.pop(), index))
        elif char == "|":
            stack[-1][2].append(index)
        index += 1
    found.extend(_split(stack.pop(), len(pattern)))
    if not found:
        return []
    least = min(depth for _, _, depth in found)
    return sorted((start, end) for start, end, depth in found if depth == least)


def _class_end(pattern: str, index: int) -> int:
    """Just past the character class opening at ``index``."""
    index += 1
    if pattern.startswith("^", index):
        index += 1
    if pattern.startswith("]", index):
        index += 1
    while index < len(pattern) and pattern[index] != "]":
        index += 2 if pattern[index] == "\\" else 1
    return index + 1


def _group_start(pattern: str, index: int) -> int:
    """Where the content of the group opening at ``index`` starts, past its kind."""
    kind = re.match(r"\((?:\?(?:P<\w+>|P=\w+|<?[=!]|[a-zA-Z-]*:))?", pattern[index:])
    assert kind is not None  # The empty kind matches any "(".
    return index + kind.end()


def _split(group: tuple[int, int, list[int], bool], end: int) -> Iterator[tuple[int, int, int]]:
    start, depth, splits, negative = group
    if splits and not negative:
        bounds = [start, *(split + 1 for split in splits)]
        yield from ((bound, stop, depth) for bound, stop in zip(bounds, [*splits, end], strict=True))


def knockouts(only: str | None = None) -> list[Knockout]:
    """Every rule to knock out, in a fixed order: each expression whole, then its alternatives.

    Args:
        only: The name of one expression, else all of the module.
    """
    countries = {arxiv_html.COUNTRIES[start:end] for start, end in top_alternatives(arxiv_html.COUNTRIES)}
    found: list[Knockout] = []
    for name, value in sorted(vars(arxiv_html).items()):
        if not isinstance(value, re.Pattern) or (only and name != only):
            continue
        pattern = value.pattern
        found.append(Knockout(name, "(whole)", NEVER, value.flags))
        for start, end in top_alternatives(pattern):
            label = pattern[start:end]
            if label not in countries:
                found.append(Knockout(name, label, pattern[:start] + NEVER + pattern[end:], value.flags))
    return found


def _tests_pass(index: int, only: str | None) -> bool:
    """Whether the extraction's tests pass with that knockout, run in a process of its own."""
    command = [sys.executable, __file__, "--run", str(index), *(["--regex", only] if only else [])]
    # The interpreter running this file, on this file.
    return subprocess.run(command, cwd=ROOT, capture_output=True, check=False).returncode == 0  # noqa: S603


def _run_one(index: int, only: str | None) -> int:
    knockout = knockouts(only)[index]

    class Plugin:
        @staticmethod
        def pytest_configure() -> None:
            knockout.apply()

    return int(pytest.main(["-q", "-x", "-p", "no:cacheprovider", *TESTS], plugins=[Plugin()]))


def _outputs(pages: list[tuple[str, str, tuple[str, ...]]], strings: list[str]) -> dict[str, Any]:
    """What the extraction gives each cached page and each stored string."""
    given: dict[str, Any] = {}
    for arxiv_id, html, authors in pages:
        front = arxiv_html.parse_front_matter(html, authors=authors)
        given[arxiv_id] = (front.affiliations, front.author_affiliations)
    for string in strings:
        given[string] = arxiv_html.clean_affiliations(string)
    return given


# What each replaying process compares: the corpus, and what today's rules give it.
_REPLAY: dict[str, Any] = {}


def _start_replay(
    pages: list[tuple[str, str, tuple[str, ...]]], strings: list[str], base: dict[str, Any]
) -> None:
    _REPLAY.update(pages=pages, strings=strings, base=base)


def _replay(knockout: Knockout) -> list[str]:
    """The cached pages and stored strings whose extraction the knockout changes."""
    kept = getattr(arxiv_html, knockout.regex)
    knockout.apply()
    try:
        given = _outputs(_REPLAY["pages"], _REPLAY["strings"])
    finally:
        setattr(arxiv_html, knockout.regex, kept)
    return [key for key, value in given.items() if value != _REPLAY["base"][key]]


def _corpus(cache_dir: Path, data_dir: Path) -> tuple[list[tuple[str, str, tuple[str, ...]]], list[str]]:
    """The cached pages of the stored papers, with their authors, and every stored affiliation."""
    cache = arxiv_html.PageCache(cache_dir)
    store = PaperStore(data_dir)
    pages: list[tuple[str, str, tuple[str, ...]]] = []
    seen: set[str] = set()
    strings: set[str] = set()
    for category in store.categories():
        top_recent = store.load_top_recent(category)
        recent = top_recent.papers if top_recent else []
        for paper in [*store.iter_papers(category), *store.iter_archive(category), *recent]:
            strings.update(paper.affiliations or ())
            for url in filter(None, (paper.html_url, arxiv_html.archive_page_url(paper.arxiv_id))):
                html = None if url in seen else cache.get(url)
                if html is not None:
                    seen.add(url)
                    pages.append((paper.arxiv_id, html, paper.authors))
    return pages, sorted(strings)


def main() -> int:
    """Knock out every rule, and report those no test needs; 1 when one changes a cached page."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--regex", help="the expressions of one name only, as `_HOST_RE`")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1, help="tests run at once")
    parser.add_argument("--page-cache-dir", type=Path, default=ROOT / ".cache" / "front-matter")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--run", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.run is not None:
        return _run_one(args.run, args.regex)

    found = knockouts(args.regex)
    console.print(f"{len(found)} knockouts, the tests of each in its own process")
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        passed = list(pool.map(lambda index: _tests_pass(index, args.regex), range(len(found))))
    survivors = [knockout for knockout, green in zip(found, passed, strict=True) if green]
    console.print(f"{len(survivors)} leave the tests green")
    if not survivors or not args.page_cache_dir.is_dir():
        for knockout in survivors:
            console.print(f"untested  {knockout.regex}  {knockout.label}")
        return 0

    pages, strings = _corpus(args.page_cache_dir, args.data_dir)
    base = _outputs(pages, strings)
    live = 0
    with ProcessPoolExecutor(args.jobs, initializer=_start_replay, initargs=(pages, strings, base)) as pool:
        for knockout, changed in zip(survivors, pool.map(_replay, survivors), strict=True):
            live += bool(changed)
            # Every one: the pages to make fixtures of, the strings of a named test.
            what = (
                f"changes {len(changed)}: {json.dumps(changed, ensure_ascii=False)}"
                if changed
                else "changes nothing"
            )
            console.print(f"{'LIVE' if changed else 'untested'}  {knockout.regex}  {knockout.label}  {what}")
    console.print(
        f"{live} live rules without a test, over {len(pages)} cached pages and {len(strings):,} strings"
    )
    return 1 if live else 0


if __name__ == "__main__":
    sys.exit(main())
