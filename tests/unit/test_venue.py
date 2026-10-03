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


@pytest.mark.parametrize(
    "comments",
    [
        pytest.param("Comparison with CVPR 2025 methods", id="comparison"),
        pytest.param("Rejected from CVPR 2026", id="rejection"),
        pytest.param("WACV 2024 (Rejected)", id="rejection-after"),
        pytest.param("Our method ranks first on the ECCV 2024 benchmark", id="ranking"),
        pytest.param("ranked 1st at the CVPR 2021 Challenge on Sign Language", id="challenge-rank"),
        pytest.param("An extension of our ECCV 2024 paper", id="extension"),
        pytest.param("Manuscript prepared for ICASSP 2027", id="prepared"),
        pytest.param("23 pages, submit to ICLR", id="submit"),
        pytest.param("Project page: https://example.github.io/method-NeurIPS-2026/", id="link"),
    ],
)
def test_never_reads_a_mention_as_an_acceptance(comments: str) -> None:
    assert extract_venue(comments) is None


@pytest.mark.parametrize(
    ("comments", "expected"),
    [
        # A mention elsewhere in the clause leaves the venue's own part alone.
        ("CVPR 2018, Rank 1 in Segmentation Track of the VisDA Challenge 2017", "CVPR 2018"),
        ("Journal extension of CVPR 2021 paper PMP-Net, Accepted by TPAMI", "TPAMI 2021"),
        ("Accepted to NeurIPS 2025 Datasets and Benchmarks Track", "NeurIPS 2025"),
        # Years written short, glued or after a hyphen.
        ("accepted by CVPR16", "CVPR 2016"),
        ("A conference version of this paper is accepted by ECCV-18", "ECCV 2018"),
        # Major venues whatever their case, and a typo of "accepted".
        ("Neurips 2025 camera-ready version", "NeurIPS 2025"),
        ("accepted to cvpr2019, code at https://github.com/x/cvpr2018-baseline", "CVPR 2019"),
        ("Accpeted to EMNLP 2026 Main Conference", "EMNLP 2026"),
        # Full names, the longest one that fits.
        (
            (
                "Accepted to IEEE International Conference on Computer Vision and Pattern Recognition "
                "(CVPR) 2017"
            ),
            "CVPR 2017",
        ),
        ("40th Conference on Neural Information Processing Systems (NeurIPS 2026)", "NeurIPS 2026"),
        # Page numbers are not years.
        ("Published in IEEE TPAMI, pp.2028-2040", "TPAMI"),
    ],
)
def test_reads_acceptances_around_mentions(comments: str, expected: str) -> None:
    assert extract_venue(comments) == expected


@pytest.mark.parametrize(
    "comments",
    [
        pytest.param("Accepted at VISAPP 2026", id="VISAPP"),
        pytest.param("Accepted at CVIP 2025", id="CVIP"),
        pytest.param(
            "Proceedings of the 9th International Conference on Computer Vision Theory and Applications",
            id="VISAPP-in-full",
        ),
        pytest.param(
            "Accepted at 7th International Conference on Computer Vision and Image Processing (CVIP), 2022",
            id="CVIP-in-full",
        ),
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
