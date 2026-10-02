import pytest

from preprint_radar.venue import extract_venue


@pytest.mark.parametrize(
    ("comments", "expected"),
    [
        ("Accepted to ECCV 2026", "ECCV 2026"),
        ("Accepted at BMVC2026", "BMVC 2026"),
        ("ECCV 2026. Corresponding author is Junjun Jiang", "ECCV 2026"),
        (
            "Accepted to the 34th ACM International Conference on Multimedia (ACM MM 2026)",
            "ACM MM 2026",
        ),
        ("Accepted at the 34th ACM International Conference on Multimedia (MM '26)", "ACM MM 2026"),
        ("18 pages, 18 figures. SIGGRAPH Asia '26", "SIGGRAPH Asia 2026"),
        ("SIGGRAPH ASIA 2026", "SIGGRAPH Asia 2026"),
        ("Accepted at the 37th British Machine Vision Conference (BMVC) 2026. 13 pages", "BMVC 2026"),
        ("ECCV Workshop 2026, AI City Challenge 2026 Track 5", "ECCV 2026 Workshop"),
        (
            "Accepted at ShapeMI 2026 (Shape in Medical Imaging), MICCAI 2026 Workshop.",
            "MICCAI 2026 Workshop",
        ),
        ("Accepted at WACV 2027 (first-round acceptance)", "WACV 2027"),
        ("Accepted by IEEE TIP. Code: https://github.com/x/y", "TIP"),
        ("Accepted by EMNLP industry track", "EMNLP"),
        ("5 pages, 6 figures. Accepted for presentation at IGARSS 2026 (IEEE Symposium)", "IGARSS 2026"),
        (
            "Accepted at the 28th International Conference on Digital Image Computing (DICTA 2026).",
            "DICTA 2026",
        ),
        (
            (
                "Accepted at the International Conference on System Analysis & Intelligent Information "
                "Technologies (SAIIT-2026)"
            ),
            "SAIIT 2026",
        ),
        ("19 pages. Published in the Proceedings of the 2026 CHI Conference (CHI '26)", "CHI 2026"),
        ("Published by ACM, New York, NY, USA, 2026", None),
        ("Accepted at the Computer Graphics International (CGI) 2026, 2 figures", "CGI 2026"),
    ],
)
def test_recognizes_venues(comments: str, expected: str) -> None:
    assert extract_venue(comments) == expected


@pytest.mark.parametrize(
    "comments",
    [
        None,
        "10 pages, 5 figures",
        "23 pages. Submitted to the 40th Conference on Neural Information Processing Systems (NeurIPS 2026).",
        "11pages,7 figures, submitted to ICML 2026",
        "Under review at CVPR 2027",
        "Extended version of the paper accepted at the MACLEAN workshop, ECML PKDD 2026.",
        "A shorter version was accepted to the IROS 2026 Space Robotics Workshop (non-archival)",
        "Accepted @ 34th Color & Imaging Conference",
        "Code will be released on the ACLU website.",
    ],
)
def test_ignores_non_acceptances(comments: str | None) -> None:
    assert extract_venue(comments) is None


# Known false positives (TEST-4), fixed with the venue table of META-4: strict, so that the
# fix shows up as a test to turn back into a plain one.
@pytest.mark.xfail(strict=True, reason="META-4: a venue named without an acceptance cue")
@pytest.mark.parametrize(
    "comments",
    [
        pytest.param("Comparison with CVPR 2025 methods", id="comparison"),
        pytest.param("Rejected from CVPR 2026", id="rejection"),
        pytest.param("Our method ranks first on the ECCV 2024 benchmark", id="ranking"),
        pytest.param("An extension of our ECCV 2024 paper", id="extension"),
        pytest.param("Published in IEEE TPAMI, pp.2028-2040", id="page-numbers-as-a-year"),
    ],
)
def test_never_reads_a_mention_as_an_acceptance(comments: str) -> None:
    assert extract_venue(comments) is None


@pytest.mark.parametrize(
    "comments",
    [
        pytest.param("Accepted at VISAPP 2026", id="VISAPP"),
        pytest.param("Accepted at CVIP 2025", id="CVIP"),
    ],
)
def test_never_reads_iccv_inside_another_name(comments: str) -> None:
    assert "ICCV" not in (extract_venue(comments) or "")


def test_uses_journal_reference() -> None:
    journal_ref = (
        "Proceedings of the IEEE/CVF Winter Conference on Applications of Computer Vision (WACV), "
        "2026, pp. 7679-7688"
    )
    assert extract_venue(None, journal_ref) == "WACV 2026"
