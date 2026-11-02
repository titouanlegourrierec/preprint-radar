"""Score the extraction against papers read by hand (AQ-1).

``tests/fixtures/gold-affiliations.json`` holds what 60 pages should give, the second
audit's sample: their affiliations, who is where (by name, as ``expected.json`` writes it)
and the institution of each. The golden fixtures pin what the extraction gives; these say
what it should, defects included, so the rate is the measure. The pages come from the page
cache; the institutions are the stored ones, which ROR named.

    make gold-affiliations    # seconds; before an EXTRACTOR_VERSION bump, and after

Each layer is scored by exact match: the strings, then who is where, then the institutions
of the papers whose stored strings are right.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from preprint_radar.console import console
from preprint_radar.models import Paper
from preprint_radar.sources.arxiv_html import PageCache, archive_page_url, parse_front_matter
from preprint_radar.store.paper_store import PaperStore

ROOT = Path(__file__).parents[1]
GOLD = ROOT / "tests" / "fixtures" / "gold-affiliations.json"


def placed(
    authors: list[str], affiliations: list[str], mapping: tuple[tuple[int, ...] | None, ...] | None
) -> list[Any] | None:
    """Who is where, by name: each author with the affiliations they are placed at."""
    if mapping is None:
        return None
    return [
        [author, None if entry is None else [affiliations[index] for index in entry]]
        for author, entry in zip(authors, mapping, strict=True)
    ]


def _stored(data_dir: Path) -> dict[str, Paper]:
    """Every stored paper, by id: day files, archive and the most cited recent ones."""
    store = PaperStore(data_dir)
    stored: dict[str, Paper] = {}
    for category in store.categories():
        top = store.load_top_recent(category)
        for paper in [
            *store.iter_papers(category),
            *store.iter_archive(category),
            *(top.papers if top else ()),
        ]:
            stored.setdefault(paper.arxiv_id, paper)
    return stored


def _misses(expected: dict[str, Any], html: str, paper: Paper | None) -> list[str]:
    """The layers a paper's page, and its stored record, do not give as expected."""
    front = parse_front_matter(html, authors=expected["authors"])
    affiliations = list(front.affiliations)
    missed = []
    if affiliations != expected["affiliations"]:
        missed.append("strings")
    if placed(expected["authors"], affiliations, front.author_affiliations) != expected["placed"]:
        missed.append("who is where")
    if paper is not None and expected["institutions"] is not None:
        record = (list(paper.affiliations or ()), list(paper.institutions or ()))
        if record != (expected["affiliations"], expected["institutions"]):
            missed.append("institutions")
    return missed


def main() -> int:
    """Print each layer's exact-match rate and the papers it misses; 1 when a page is missing."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--page-cache-dir", type=Path, default=ROOT / ".cache" / "front-matter")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    gold: dict[str, dict[str, Any]] = json.loads(GOLD.read_text(encoding="utf-8"))["papers"]
    cache = PageCache(args.page_cache_dir)
    stored = _stored(args.data_dir)
    layers = ("strings", "who is where", "institutions")
    scored = dict.fromkeys(layers, 0)
    misses: dict[str, list[str]] = {layer: [] for layer in layers}
    missing: list[str] = []
    for arxiv_id, expected in gold.items():
        paper = stored.get(arxiv_id)
        urls = [paper.html_url if paper else None, archive_page_url(arxiv_id)]
        html = next((page for url in urls if url and (page := cache.get(url)) is not None), None)
        if html is None:
            missing.append(arxiv_id)
            continue
        scored["strings"] += 1
        scored["who is where"] += 1
        scored["institutions"] += paper is not None and expected["institutions"] is not None
        for layer in _misses(expected, html, paper):
            misses[layer].append(f"{arxiv_id}  {expected.get('note', '')}".rstrip())
    for layer, missed in misses.items():
        console.print(f"{layer}: {scored[layer] - len(missed)} of {scored[layer]} exact")
        for note in missed:
            console.print(f"  {note}")
    if missing:
        console.print(f"Not in the page cache: {', '.join(missing)}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
