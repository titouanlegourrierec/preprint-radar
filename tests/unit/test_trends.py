from datetime import date, timedelta

import pytest

from preprint_radar.models import KeyPaper
from preprint_radar.sources.arxiv_oai import CatalogEntry
from preprint_radar.trends import MONTHS, _distinct, count_trends, format_trends_report, title_phrases

THROUGH = date(2026, 10, 20)


@pytest.mark.parametrize(
    ("title", "said", "unsaid"),
    [
        pytest.param(
            "Semi-Supervised Medical Image Segmentation with SAM",
            ["semi-supervised medical image segmentation", "medical image segmentation", "SAM"],
            ["supervised medical image", "segmentation with"],
            id="whole-words-and-no-function-word-at-an-end",
        ),
        pytest.param(
            "VLMs Are Blind: Rethinking NeRF in 2025",
            ["VLM", "NeRF", "rethinking NeRF", "VLMs are blind"],
            ["blind rethinking", "NeRF in 2025"],
            id="punctuation-ends-a-phrase-a-year-names-none",
        ),
        pytest.param(
            "World-Action Models for Long-Horizon Robot Policies",
            ["world-action model", "long-horizon robot policy", "robot policy"],
            ["world", "action", "robot policies"],
            id="a-word-alone-is-an-acronym-or-no-topic",
        ),
        pytest.param(
            "Feed-Forward 3D Gaussian Splatting - A BENCHMARK",
            ["feed-forward 3D gaussian splatting", "3D gaussian splatting"],
            ["3D", "feed-forward 3D", "BENCHMARK", "splatting a"],
            id="field-acronyms-neither-alone-nor-last",
        ),
        pytest.param(
            "Efficient Learning of Geometry-Aware Time Series Patches",
            ["time series patch", "time series"],
            ["efficient learning", "geometry-aware", "time sery"],
            id="generic-words-and-modifiers",
        ),
    ],
)
def test_title_phrases(title: str, said: list[str], unsaid: list[str]) -> None:
    named = set(title_phrases(title).values())

    assert set(said) <= named
    assert not set(unsaid) & named


def test_a_phrase_is_keyed_by_its_words_the_last_singular() -> None:
    assert title_phrases("Video World Models") == {
        "video": "video",
        "video world": "video world",
        "video world model": "video world model",
        "world": "world",
        "world model": "world model",
    }
    assert title_phrases("LLMs, CNNs and GANs") == {
        "llm": "LLM",
        "cnn": "CNN",
        "cnns and gan": "CNNs and GAN",
        "gan": "GAN",
    }
    assert set(title_phrases("Lens Bias in Robotics")) == {
        "lens",
        "bias",
        "robotics",
        "lens bias",
        "lens bias in robotics",
        "bias in robotics",
    }
    # Generic words and modifiers alone, plurals included, say nothing.
    assert title_phrases("Deep Neural Networks for Large-Scale Datasets") == {}


def test_a_phrase_has_four_words_and_six_parts_at_most() -> None:
    assert max(len(key.split()) for key in title_phrases("Alpha Beta Gamma Delta Epsilon")) == 4
    assert set(title_phrases("Vision-Language-Action Text-to-Image-To-Video Model")) == {
        "vision language action",
        "text to image to video",
        "text to image to video model",
    }


def _papers(series: int, titles: str | tuple[str, ...], days: list[date]) -> list[CatalogEntry]:
    """Papers announced on ``days``, numbered in their month by ``series`` (1 to 9), the titles in turn."""
    cycle = (titles,) if isinstance(titles, str) else titles
    return [
        CatalogEntry(
            arxiv_id=f"{day:%y%m}.{series}{index:04d}",
            created=day,
            categories=("cs.CV",),
            title=cycle[index % len(cycle)],
            authors=("A. Author",),
        )
        for index, day in enumerate(days)
    ]


def _every(start: date, count: int, step: int = 1) -> list[date]:
    return [start + timedelta(days=index * step) for index in range(count)]


THINGS = ("Driving", "Robots", "Games", "Cities", "Surgery")
WORLD_MODELS = tuple(f"World Models for {thing}" for thing in THINGS)
SEMI_SUPERVISED = tuple(f"Semi-Supervised Segmentation of {thing}" for thing in THINGS)
# The window of 90 days: 2026-07-23 to 2026-10-20, against 2025-07-23 to 2025-10-20.
CATALOG = [
    # Rising: 3 papers in March 2024, 2 a year ago, 32 in the last 90 days.
    *_papers(1, "World Models for Driving", _every(date(2024, 3, 4), 3)),
    *_papers(2, "World Models for Driving", _every(date(2025, 7, 25), 2)),
    *_papers(3, WORLD_MODELS, _every(date(2026, 7, 25), 20, 4)),
    # New: 12 papers since August 2026, which make 12 of the 32 above.
    *_papers(4, "Video World Models", _every(date(2026, 8, 24), 12, 4)),
    # Cooling: 20 papers a year ago, 2 in the last 90 days.
    *_papers(5, SEMI_SUPERVISED, _every(date(2025, 7, 25), 20, 4)),
    *_papers(6, "Semi-Supervised Segmentation of Roads", _every(date(2026, 7, 25), 2)),
    # Neither, and the same before 2010, which is not counted.
    *_papers(7, "Gaussian Splatting Revisited", _every(date(2023, 6, 1), 12, 30)),
    *_papers(8, "Gaussian Splatting Before", _every(date(2009, 1, 1), 5)),
    # A paper a day saying no topic, to the last day.
    *_papers(9, "Rethinking Deep Learning", _every(date(2025, 1, 1), 658)),
]


def test_topics_rise_cool_and_appear() -> None:
    trends = count_trends(CATALOG, {})

    quarter = trends.windows["quarter"]
    assert trends.through == THROUGH
    assert quarter.earlier == (date(2025, 7, 23), date(2025, 10, 20))
    assert quarter.recent == (date(2026, 7, 23), THROUGH)
    assert quarter.papers == (112, 124)
    # The share of 3 papers of the 90 days, a third of the 10 a topic needs to be ranked.
    assert quarter.added == round(3 / 124, 8)
    # "video world" is "video world model", which names it; the specific titles are too rare.
    assert quarter.rising == ("world model", "video world model")
    assert quarter.cooling == ("semi supervised segmentation",)
    assert quarter.new == ("video world model",)
    assert set(trends.topics) == {"world model", "video world model", "semi supervised segmentation"}
    world = trends.topics["world model"]
    assert world.name == "world model"
    assert world.windows == {"quarter": (2, 32), "year": (2, 32)}
    assert len(world.counts) == MONTHS
    assert sum(world.counts) == 37
    assert world.first == "2024-03"
    assert trends.topics["semi supervised segmentation"].name == "semi-supervised segmentation"
    # A word alone, but an acronym, rises in the explorer only: July to October 2026.
    assert trends.series["world"].counts[-4:] == (2, 10, 15, 5)
    assert "world" not in trends.topics
    # Without citation counts, neither impact nor key papers.
    assert world.impact is None
    assert world.papers == ()
    # The explorer's series start at the topic's first paper since 2010.
    assert trends.start == "2010-01"
    assert trends.series["gaussian splatting"].start == (2023 - 2010) * 12 + 5
    assert sum(trends.series["gaussian splatting"].counts) == 12
    assert len(trends.totals) == (2026 - 2010) * 12 + 10
    assert sum(trends.totals) == len(CATALOG) - 5
    assert format_trends_report("cs.CV", trends) == (
        "cs.CV: 21 topics of 729 papers to 2026-10-20; last 90 days: 2 rising "
        "(world model, video world model…), 1 cooling, 1 new"
    )


def test_a_topic_among_its_months_most_cited_has_impact_and_key_papers() -> None:
    cities = _papers(1, "World Models of Cities", _every(date(2026, 1, 5), 20))
    citations: dict[str, int | None] = {paper.arxiv_id: 500 for paper in cities}
    citations[cities[0].arxiv_id] = 900
    citations[cities[1].arxiv_id] = None

    trends = count_trends([*CATALOG, *cities], citations)

    world = trends.topics["world model"]
    # Its papers 3 to 15 months before October 2026: those of July 2025, January and July
    # 2026; 19 of the 24 are among their month's most cited tenth, the cities but one.
    assert world.impact == round(19 / 24, 3)
    assert world.papers == (
        KeyPaper("2601.10000", "World Models of Cities", 900),
        KeyPaper("2601.10002", "World Models of Cities", 500),
        KeyPaper("2601.10003", "World Models of Cities", 500),
    )
    # Never cited: no impact, no key paper.
    assert trends.topics["semi supervised segmentation"].impact == 0
    assert trends.topics["semi supervised segmentation"].papers == ()
    # Too few papers in those months.
    assert trends.topics["video world model"].impact is None


def test_a_topic_whose_share_holds_neither_rises_nor_cools() -> None:
    # A small category, every paper of which says it: a year ago, 30 papers; now, 10.
    catalog = [
        *_papers(1, "Graph Matching Networks", _every(date(2025, 7, 25), 30)),
        *_papers(2, "Graph Matching Networks", _every(date(2026, 10, 11), 10)),
    ]

    trends = count_trends(catalog, {})

    assert trends.windows["quarter"].papers == (30, 10)
    assert format_trends_report("cs.OS", trends) == (
        "cs.OS: 5 topics of 40 papers to 2026-10-20; last 90 days: 0 rising, 0 cooling, 0 new"
    )


def test_the_lists_rank_an_acronym_alone_the_explorer_a_word_too() -> None:
    catalog = [
        *_papers(1, tuple(f"VLA for {thing}" for thing in THINGS), _every(date(2026, 8, 3), 12, 4)),
        *_papers(2, tuple(f"Mamba for {thing}" for thing in THINGS), _every(date(2026, 8, 3), 12, 4)),
        *_papers(9, "Rethinking Deep Learning", _every(date(2025, 1, 1), 658)),
    ]

    trends = count_trends(catalog, {})

    assert trends.windows["quarter"].rising == ("vla",)
    assert trends.windows["quarter"].new == ("vla",)
    assert trends.topics["vla"].name == "VLA"
    assert trends.series["mamba"].counts[-3:] == (8, 4, 0)
    assert "mamba" not in trends.topics


def test_nothing_to_count_without_a_paper_since_2010() -> None:
    with pytest.raises(ValueError, match="no paper since 2010"):
        count_trends(_papers(1, "Gaussian Splatting Before", _every(date(2009, 1, 1), 3)), {})


def test_the_most_specific_phrase_names_a_topic() -> None:
    papers = {
        "visual token": frozenset("123456"),
        "visual token pruning": frozenset("1234"),
        "token pruning": frozenset("12347"),
        "world model": frozenset("89a"),
        "video world model": frozenset("8"),
    }

    # "video world model" shares a third of the papers of "world model": a topic of its own.
    assert _distinct(list(papers), papers, 10) == ("visual token pruning", "world model", "video world model")
    # A more specific phrase names a topic even ranked past the list's end.
    assert _distinct(list(papers), papers, 1) == ("visual token pruning",)
