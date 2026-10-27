"""``docs/data-format.md`` documents every file the store writes and every field of its records."""

import json
import re
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from preprint_radar.models import (
    CodeRecord,
    Cohort,
    KeyPaper,
    Paper,
    Provenance,
    ScholarRecord,
    TopicSeries,
    Trends,
    TrendTopic,
    TrendWindow,
)
from preprint_radar.store.paper_store import SCHEMA_VERSION, PaperStore

ROOT = Path(__file__).parents[2]
DOC = ROOT / "docs" / "data-format.md"
# The objects keyed by data (ids, years, categories, topics), whose keys are not fields; under
# these names, a list or a text is a field's value.
_KEYED_BY_DATA = frozenset(
    {"categories", "archives", "top_recent", "counts", "gains", "years", "topics", "papers", "institutions"}
)
_DATED_RE = re.compile(r"\d{4}(?:-\d\d-\d\d)?\.json$")

NOW = datetime(2026, 10, 25, 6, tzinfo=UTC)
# Every field of a record set, the optional ones included.
PAPER = Paper(
    arxiv_id="2610.00001",
    announced=date(2026, 10, 26),
    title="Synthetic Worlds",
    authors=("A. Author", "B. Author"),
    primary_subject="Computer Vision and Pattern Recognition (cs.CV)",
    subjects=("Computer Vision and Pattern Recognition (cs.CV)", "Machine Learning (cs.LG)"),
    comments="Accepted at CVPR 2026; withdrawn",
    journal_ref="Journal of Examples 1 (2026)",
    venue="CVPR 2026",
    cross_list_from="cs.LG",
    html_url="https://arxiv.org/html/2610.00001v1",
    abstract="A synthetic abstract.",
    affiliations=("Example Lab, Example University",),
    author_affiliations=((0,), None),
    institutions=("Example University",),
    institution_ids=("00example",),
    extractor=12,
    withdrawn=True,
    affiliations_provenance=Provenance("html", date(2026, 10, 26)),
    institutions_provenance=Provenance("ror", date(2026, 10, 26)),
)
TRENDS = Trends(
    through=date(2026, 10, 20),
    start="2010-01",
    totals=(4, 5),
    windows={
        "quarter": TrendWindow(
            days=90,
            earlier=(date(2025, 7, 23), date(2025, 10, 20)),
            recent=(date(2026, 7, 23), date(2026, 10, 20)),
            papers=(4, 5),
            rising=("world model",),
            cooling=(),
            new=(),
            added=0.5,
        )
    },
    topics={
        "world model": TrendTopic(
            name="world model",
            counts=(1, 2),
            windows={"quarter": (1, 2)},
            first=None,
            impact=0.5,
            papers=(KeyPaper("2610.00001", "Synthetic Worlds", 3),),
            also=("world modeling",),
        )
    },
    months=2,
    series={"world model": TopicSeries("world model", 0, (1, 2), ("world modeling",))},
)


def _write_every_file(store: PaperStore) -> None:
    """Every file of the store, each with every field it can hold."""
    store.save("cs.CV", [PAPER])
    store.write_archive("cs.CV", [replace(PAPER, arxiv_id="1701.00001", announced=date(2017, 1, 5))])
    store.write_top_recent("cs.CV", [PAPER], since=date(2025, 10, 26))
    for days, citations in ((7, 1), (0, 3)):
        store.write_citations(
            "cs.CV", {PAPER.arxiv_id: citations}, source="Semantic Scholar", now=NOW - timedelta(days)
        )
    store.write_scholar(
        "cs.CV",
        {PAPER.arxiv_id: ScholarRecord("10.1000/example", "CVPR 2026", ("1", None))},
        source="Semantic Scholar",
    )
    for days, stars in ((7, 10), (0, 15)):
        store.write_code(
            "cs.CV",
            {
                PAPER.arxiv_id: CodeRecord("https://github.com/example/worlds", stars=stars, shared=True),
                "1701.00001": CodeRecord("https://huggingface.co/datasets/example/worlds", likes=4),
            },
            source="GitHub, Hugging Face",
            now=NOW - timedelta(days),
        )
    store.write_countries("cs.CV", {"00example": "US", "01example": None}, source="OpenAlex", now=NOW)
    store.write_cohorts(
        "cs.CV", {2017: Cohort(papers=10, top_1=50, top_5=20, top_10=9)}, source="Semantic Scholar"
    )
    store.write_trends("cs.CV", TRENDS, source="arXiv, Semantic Scholar", now=NOW)
    store.write_index()


def _fields(value: object, found: set[str]) -> set[str]:
    """The field names of a file's objects, leaving out the keys that are data."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _KEYED_BY_DATA and isinstance(item, dict):
                for keyed in item.values():
                    _fields(keyed, found)
            else:
                found.add(key)
                _fields(item, found)
    elif isinstance(value, list):
        for item in value:
            _fields(item, found)
    return found


def test_every_file_and_field_the_store_writes_is_documented(tmp_path: Path) -> None:
    store = PaperStore(tmp_path / "data")
    _write_every_file(store)
    doc = DOC.read_text(encoding="utf-8")

    files = sorted(path for path in store.root.rglob("*.json"))
    names = {_DATED_RE.sub("", path.relative_to(store.root).as_posix()) for path in files}
    assert names == {
        "index.json",
        "cs.CV/",
        "cs.CV/archive/",
        *(f"cs.CV/{name}.json" for name in ("top-recent", "citations", "citation-gains", "cohorts")),
        *(f"cs.CV/{name}.json" for name in ("scholar", "code", "countries", "trends", "topics")),
    }
    # The day and archive files by their name's pattern, the others by their own.
    assert "`<category>/<YYYY-MM-DD>.json`" in doc
    assert "`<category>/archive/<YYYY>.json`" in doc
    named = [name.replace("cs.CV/", "<category>/") for name in names if name.endswith(".json")]
    assert [name for name in named if f"`{name}`" not in doc] == []

    fields: set[str] = set()
    for path in files:
        _fields(json.loads(path.read_text(encoding="utf-8")), fields)
    assert {"arxiv_id", "institution_ids", "provenance", "withdrawn", "also", "gained", "likes"} <= fields
    assert sorted(field for field in fields if f"`{field}`" not in doc and f'"{field}"' not in doc) == []


def test_the_version_documented_is_the_store_s() -> None:
    assert f"`schema_version`, {SCHEMA_VERSION} today" in DOC.read_text(encoding="utf-8")
