"""Removals and corrections made on request stay (PUB-1)."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from preprint_radar.cli import main
from preprint_radar.collect import _carry_over, _needs_institutions
from preprint_radar.exceptions import StoreError
from preprint_radar.models import (
    CodeRecord,
    KeyPaper,
    Paper,
    Provenance,
    ScholarRecord,
    Trends,
    TrendTopic,
)
from preprint_radar.openalex_affiliations import needs_openalex
from preprint_radar.store.corrections import pin_paper, remove_paper
from preprint_radar.store.paper_store import Corrections, PaperStore
from preprint_radar.store.reclean import reclean_paper
from preprint_radar.store.validate import Level, validate_store

DAY = date(2026, 10, 26)
TODAY = date(2026, 11, 2)
NOW = datetime(2026, 11, 2, 6, tzinfo=UTC)
GONE = "2610.00002"
PAPER = Paper(
    arxiv_id="2610.00001",
    announced=DAY,
    title="Kept",
    authors=("Ada Lovelace", "Bob Smith"),
    html_url="https://arxiv.org/html/2610.00001v1",
    affiliations=("MIT", "Stanford University"),
    author_affiliations=((0,), (1,)),
    institutions=("Massachusetts Institute of Technology", "Stanford University"),
    extractor=21,
    affiliations_provenance=Provenance("html", DAY),
    institutions_provenance=Provenance("ror", DAY),
)
OLD = replace(PAPER, arxiv_id="1701.00001", announced=date(2017, 1, 5))


def _trends(*ids: str) -> Trends:
    topic = TrendTopic(
        name="world model",
        counts=(1, 2),
        windows={},
        first=None,
        impact=None,
        papers=tuple(KeyPaper(arxiv_id, "A title", 3) for arxiv_id in ids),
    )
    return Trends(
        through=DAY,
        start="2026-09",
        totals=(1, 2),
        windows={},
        topics={"world model": topic},
        months=2,
        series={},
    )


def _store(tmp_path: Path) -> PaperStore:
    """A store holding ``GONE`` in every file keyed by paper, and ``PAPER`` beside it."""
    store = PaperStore(tmp_path / "data")
    gone = replace(PAPER, arxiv_id=GONE, title="To remove")
    store.save("cs.CV", [PAPER, gone])
    store.write_archive("cs.CV", [OLD, replace(gone, announced=date(2017, 2, 1))])
    store.write_top_recent("cs.CV", [PAPER, gone], since=date(2025, 11, 1))
    for days, count in ((7, 1), (0, 5)):
        store.write_citations(
            "cs.CV", {PAPER.arxiv_id: count, GONE: count}, source="S2", now=NOW - timedelta(days)
        )
    store.write_scholar(
        "cs.CV",
        {GONE: ScholarRecord("10.1/x", None, ()), PAPER.arxiv_id: ScholarRecord("10.1/y", None, ())},
        source="S2",
    )
    store.write_code("cs.CV", {GONE: CodeRecord("https://github.com/a/b", stars=3)}, source="GitHub", now=NOW)
    store.write_trends("cs.CV", _trends(GONE, PAPER.arxiv_id), source="arXiv", now=NOW)
    store.write_index()
    return store


def _held(store: PaperStore) -> list[str]:
    """The files that name ``GONE``."""
    return sorted(
        path.relative_to(store.root).as_posix()
        for path in store.root.rglob("*.json")
        if f'"{GONE}"' in path.read_text(encoding="utf-8") and path.name != "corrections.json"
    )


def _errors(store: PaperStore) -> list[str]:
    return [finding.message for finding in validate_store(store).findings if finding.level is Level.ERROR]


def test_no_corrections_without_the_file(tmp_path: Path) -> None:
    store = PaperStore(tmp_path / "data")

    assert store.load_corrections("cs.CV") == Corrections()
    assert store.removed("cs.CV") == frozenset()


def test_corrections_are_written_and_read_back(tmp_path: Path) -> None:
    store = PaperStore(tmp_path / "data")
    corrections = Corrections(removed={GONE: DAY}, pinned={PAPER.arxiv_id: TODAY})

    store.write_corrections("cs.CV", corrections)

    assert store.load_corrections("cs.CV") == corrections


def test_an_invalid_corrections_file_is_refused(tmp_path: Path) -> None:
    store = PaperStore(tmp_path / "data")
    path = store.root / "cs.CV" / "corrections.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"schema_version": 1, "removed": []}', encoding="utf-8")

    with pytest.raises(StoreError, match="Invalid corrections file"):
        store.load_corrections("cs.CV")
    assert any("Invalid corrections file" in message for message in _errors(store))


def test_the_store_writes_a_removed_paper_nowhere(tmp_path: Path) -> None:
    store = PaperStore(tmp_path / "data")
    store.write_corrections("cs.CV", Corrections(removed={GONE: TODAY}))

    _store(tmp_path)

    assert _held(store) == []
    assert store.stored_ids("cs.CV") == [PAPER.arxiv_id, OLD.arxiv_id, PAPER.arxiv_id]
    gains = store.load_citation_gains("cs.CV")
    assert gains is not None
    assert gains.gains == {PAPER.arxiv_id: 4}


def test_removing_a_paper_takes_it_out_of_every_file(tmp_path: Path) -> None:
    store = _store(tmp_path)
    before = store.load_citation_counts("cs.CV")
    assert len(_held(store)) == 8

    written = remove_paper(store, "cs.CV", GONE, TODAY)

    assert _held(store) == []
    assert len(written) == 8  # its day, the archive, top-recent, counts, gains, scholar, code, trends
    assert store.load_corrections("cs.CV").removed == {GONE: TODAY}
    after = store.load_citation_counts("cs.CV")
    assert after is not None
    assert before is not None
    assert after.generated_at == before.generated_at
    assert after.counts == {PAPER.arxiv_id: 5}
    trends = store.load_trends("cs.CV")
    assert trends is not None
    assert [paper.arxiv_id for paper in trends.topics["world model"].papers] == [PAPER.arxiv_id]
    assert (
        json.loads((store.root / "index.json").read_text(encoding="utf-8"))["categories"]["cs.CV"][0]["count"]
        == 1
    )
    assert _errors(store) == []
    # Asked again: the first day stays, and nothing is left to write.
    assert remove_paper(store, "cs.CV", GONE, TODAY + timedelta(days=1)) == []
    assert store.load_corrections("cs.CV").removed == {GONE: TODAY}


def test_removing_a_pinned_paper_unpins_it(tmp_path: Path) -> None:
    store = PaperStore(tmp_path / "data")
    store.save("cs.CV", [PAPER])
    store.write_corrections("cs.CV", Corrections(pinned={PAPER.arxiv_id: DAY}))

    remove_paper(store, "cs.CV", PAPER.arxiv_id, TODAY)

    assert store.load_corrections("cs.CV") == Corrections(removed={PAPER.arxiv_id: TODAY})


def test_validate_fails_on_a_removed_paper_written_again(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write_corrections("cs.CV", Corrections(removed={GONE: TODAY}))

    errors = [message for message in _errors(store) if "removed on request" in message]

    assert errors == [
        f"{GONE}: removed on request, still in {name}"
        for name in (
            "the papers",
            "citations.json",
            "citation-gains.json",
            "scholar.json",
            "code.json",
            "trends.json",
        )
    ]


def test_a_keyed_file_that_does_not_load_stops_a_removal(tmp_path: Path) -> None:
    store = _store(tmp_path)
    (store.root / "cs.CV" / "scholar.json").write_text('{"schema_version": 1}', encoding="utf-8")

    with pytest.raises(StoreError, match=r"Invalid scholar\.json"):
        remove_paper(store, "cs.CV", GONE, TODAY)


def test_a_keyed_file_that_does_not_load_is_left_to_its_own_check(tmp_path: Path) -> None:
    store = _store(tmp_path)
    remove_paper(store, "cs.CV", GONE, TODAY)
    (store.root / "cs.CV" / "code.json").write_text("{", encoding="utf-8")

    assert not any("removed on request" in message for message in _errors(store))


def test_pinning_keeps_the_corrected_affiliations_from_every_step(tmp_path: Path) -> None:
    store = PaperStore(tmp_path / "data")
    corrected = replace(PAPER, author_affiliations=((0,), (0, 1)))
    store.save("cs.CV", [corrected])
    store.write_archive("cs.CV", [OLD])
    other = replace(PAPER, arxiv_id="2610.00003")
    store.save("cs.CV", [other])
    store.write_top_recent("cs.CV", [corrected, other], since=date(2025, 11, 1))
    store.write_index()

    report = pin_paper(store, "cs.CV", PAPER.arxiv_id, TODAY)

    assert report.records == 2
    pinned = next(paper for paper in store.load_day("cs.CV", DAY) if paper.arxiv_id == PAPER.arxiv_id)
    assert pinned.affiliations_by_hand
    assert pinned.affiliations_provenance == Provenance("manual", TODAY)
    assert (pinned.author_affiliations, pinned.extractor, pinned.institutions) == (((0,), (0, 1)), None, None)
    assert [paper.affiliations_by_hand for paper in store.iter_top_recent("cs.CV")] == [False, True]
    assert store.load_corrections("cs.CV").pinned == {PAPER.arxiv_id: TODAY}
    assert _errors(store) == []
    # `institutions` names them again, and keeps them named.
    assert _needs_institutions(pinned)
    assert not _needs_institutions(replace(pinned, institutions=("MIT", "Stanford University")))
    # No step reads them again: OpenAlex, the cleaning, and a new version's author list.
    assert not needs_openalex(replace(pinned, affiliations=(), author_affiliations=None), TODAY)
    assert reclean_paper(
        replace(pinned, affiliations=("Ada Lovelace, MIT",), author_affiliations=None)
    ).affiliations == ("Ada Lovelace, MIT",)
    listed = Paper(
        arxiv_id=PAPER.arxiv_id,
        announced=DAY,
        title="Kept",
        authors=("Ada Lovelace", "Bob Smith", "Carl Third"),
        html_url="https://arxiv.org/html/2610.00001v2",
    )
    renamed = _carry_over(listed, pinned)
    assert (renamed.affiliations, renamed.author_affiliations) == (PAPER.affiliations, None)
    assert renamed.affiliations_by_hand


def test_pinning_an_archived_paper(tmp_path: Path) -> None:
    store = PaperStore(tmp_path / "data")
    store.write_archive("cs.CV", [OLD])

    assert pin_paper(store, "cs.CV", OLD.arxiv_id, TODAY).records == 1
    assert [paper.affiliations_by_hand for paper in store.iter_archive("cs.CV")] == [True]


@pytest.mark.parametrize(
    ("papers", "message"),
    [
        ([], "not stored"),
        (
            [
                replace(
                    PAPER,
                    affiliations=None,
                    author_affiliations=None,
                    institutions=None,
                    extractor=None,
                    affiliations_provenance=None,
                    institutions_provenance=None,
                )
            ],
            "no affiliations to pin",
        ),
    ],
    ids=["not-stored", "no-affiliations"],
)
def test_pinning_refuses_a_paper_it_cannot_pin(tmp_path: Path, papers: list[Paper], message: str) -> None:
    store = PaperStore(tmp_path / "data")
    store.save("cs.CV", papers)

    with pytest.raises(StoreError, match=message):
        pin_paper(store, "cs.CV", PAPER.arxiv_id, TODAY)
    assert store.load_corrections("cs.CV") == Corrections()


def test_validate_fails_when_a_run_read_a_pinned_paper_again(tmp_path: Path) -> None:
    store = PaperStore(tmp_path / "data")
    store.save("cs.CV", [PAPER])
    pin_paper(store, "cs.CV", PAPER.arxiv_id, TODAY)
    store.write_index()
    store.save("cs.CV", [PAPER])  # what a step that ignored the pin would write

    assert _errors(store) == [
        f"{PAPER.arxiv_id}: pinned on request, but its affiliations are no longer the maintainer's"
    ]


def test_validate_leaves_a_pinned_paper_to_the_files_own_checks(tmp_path: Path) -> None:
    store = PaperStore(tmp_path / "data")
    store.save("cs.CV", [PAPER])
    pin_paper(store, "cs.CV", PAPER.arxiv_id, TODAY)
    store.write_index()
    (store.root / "cs.CV" / "top-recent.json").write_text("{", encoding="utf-8")

    assert not any("pinned on request" in message for message in _errors(store))


def test_the_commands_remove_and_pin(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = _store(tmp_path)
    data = ["--data-dir", str(store.root)]

    assert main(["remove", f"{GONE}v2", *data]) == 0
    assert main(["pin", PAPER.arxiv_id, *data]) == 0

    out = capsys.readouterr().out
    assert f"cs.CV: {GONE} removed, 8 files written" in out
    assert f"cs.CV: {PAPER.arxiv_id} pinned, 2 records" in out
    assert _held(store) == []


@pytest.mark.parametrize("value", ["2610.1", "cs.CV", "2610.00001 "])
def test_the_commands_refuse_what_is_no_arxiv_id(tmp_path: Path, value: str) -> None:
    with pytest.raises(SystemExit):
        main(["remove", value, "--data-dir", str(tmp_path)])


def test_old_style_ids_are_taken(tmp_path: Path) -> None:
    store = PaperStore(tmp_path / "data")
    store.write_archive("cs.CV", [replace(OLD, arxiv_id="cs/0601001", announced=date(2006, 1, 2))])

    assert main(["remove", "cs/0601001v1", "--data-dir", str(store.root)]) == 0
    assert list(store.iter_archive("cs.CV")) == []
