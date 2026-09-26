from collections.abc import Callable

import httpx
import pytest

from preprint_radar.http import HttpClient
from preprint_radar.paper_page import FrontMatter, fetch_front_matter, parse_front_matter

PaperHtml = Callable[[str], str]


@pytest.mark.parametrize(
    ("arxiv_id", "expected"),
    [
        pytest.param(
            "2609.30234",
            (
                "Carnegie Mellon University, United States of America",
                "University of Washington, United States of America",
                "Texas A&M University, United States of America",
                "Google, United States of America",
                "Google, Switzerland",
            ),
            id="one-affiliation-per-author",
        ),
        pytest.param(
            "2609.30249",
            (
                "Massachusetts Institute of Technology",
                "National University of Singapore",
                "University of Pennsylvania",
                "NVIDIA",
            ),
            id="affiliations-separated-by-quad",
        ),
        pytest.param(
            "2609.28473",
            (
                "Cornell University",
                "Adobe",
                "Virginia Tech",
                "University of Washington",
                "University of Maryland",
            ),
            id="affiliations-separated-by-line-breaks",
        ),
        pytest.param(
            "2609.24787",
            (
                "ETH Zurich",
                "University of Oxford",
                "Norwegian Institute of Bioeconomy Research (NIBIO)",
                "University of Zurich",
            ),
            id="numbered-lines",
        ),
        pytest.param(
            "2609.21811",
            (
                (
                    "AI for Image-Guided Diagnosis and Therapy, School of Medicine and Health, "
                    "Technical University of Munich (TUM), Munich, Germany"
                ),
                "Munich Center for Machine Learning (MCML), Munich, Germany",
                "Technical University of Munich (TUM), Munich, Germany",
                "University of California, Irvine, Irvine, CA, USA",
                (
                    "Department of Pathology, School of Medicine, and Department of Biomedical Engineering, "
                    "School of Engineering, University of California, Irvine, Irvine, CA, USA"
                ),
            ),
            id="multi-line-affiliations",
        ),
        pytest.param(
            "2609.11271",
            (
                "Seoul National University, Seoul, Republic of Korea",
                "OUTTA, Seoul, Republic of Korea",
                "Chung-Ang University, Seoul, Republic of Korea",
                "Kyung Hee University, Seoul, Republic of Korea",
                "Samsung Medical Center, Seoul, Republic of Korea",
                "NVIDIA AI Technology Center, Taipei, Taiwan",
            ),
            id="markers-between-affiliations",
        ),
        pytest.param(
            "2609.30056",
            (
                "New York University, New York, USA",
                (
                    "Department of Electrical Engineering and Computer Sciences, University of California, "
                    "Berkeley, CA 94720, USA"
                ),
                (
                    "U.S. Army Combat Capabilities Development Command, Army Research Laboratory, "
                    "Adelphi, MD 20783, USA"
                ),
            ),
            id="e-mail-after-affiliation",
        ),
        pytest.param(
            "2609.29825",
            (
                "Department of Biomedical Engineering, National University of Singapore, Singapore",
                "School of Automation, Southeast University, Nanjing, China",
            ),
            id="address-contacts",
        ),
        pytest.param("2609.25108", ("Tampere University", "Nokia Technologies"), id="address-note"),
        pytest.param(
            "2609.29721",
            ("The University of Tokyo", "National Institute of Informatics", "University of Augsburg"),
            id="address-note-with-symbol-markers",
        ),
        pytest.param(
            "2609.26161",
            (
                "Department of Electrical Engineering, University of Chile, Santiago, Chile",
                "Advanced Mining Technology Center (AMTC), University of Chile, Santiago, Chile",
                "The Iniciativa de Datos e Inteligencia Artificial, University of Chile, Santiago, Chile",
            ),
            id="springer-institute-notes",
        ),
        pytest.param(
            "2609.29350",
            (
                (
                    "School of Artificial Intelligence, National Center for Applied Mathematics in Hubei, "
                    "Hubei Key Laboratory of Computational Science, Wuhan University, Wuhan, China"
                ),
                (
                    "Department of Applied Mathematics, The Hong Kong Polytechnic University, Hung Hom, "
                    "Kowloon, Hong Kong SAR, China"
                ),
                (
                    "Department of Data Science and Artificial Intelligence, The Hong Kong Polytechnic "
                    "University, Hung Hom, Kowloon, Hong Kong SAR, China"
                ),
            ),
            id="numbered-footnote",
        ),
        pytest.param(
            "2609.29650",
            (
                (
                    "Department of Signal Theory and Communications, Telematics and Computing Systems, "
                    "Rey Juan Carlos University (URJC), Madrid, Spain"
                ),
                "LoUISE Research Group, University of Castilla-La Mancha, Albacete, Spain",
                "School of Mathematical and Computational Sciences, Yachay Tech University, Ecuador",
            ),
            id="ieee-thanks-notes",
        ),
        pytest.param(
            "2609.29384",
            (
                "Telecom SudParis, Institut Polytechnique de Paris, 91120 Palaiseau, France",
                (
                    "School of Computer Science and Information Engineering, Chongqing Technology and "
                    "Business University, Chongqing 400067, China"
                ),
            ),
            id="ieee-thanks-notes-with-parenthesized-e-mail",
        ),
        pytest.param("2609.25615", (), id="no-author-block"),
    ],
)
def test_parse_affiliations(paper_html: PaperHtml, arxiv_id: str, expected: tuple[str, ...]) -> None:
    assert parse_front_matter(paper_html(arxiv_id)).affiliations == expected


def test_never_returns_contact_details(paper_html: PaperHtml) -> None:
    for arxiv_id in ("2609.30234", "2609.28473", "2609.30249", "2609.30056", "2609.26161", "2609.29650"):
        for affiliation in parse_front_matter(paper_html(arxiv_id)).affiliations:
            assert "@" not in affiliation
            assert "http" not in affiliation


def test_ignores_footnotes(paper_html: PaperHtml) -> None:
    affiliations = parse_front_matter(paper_html("2609.29347")).affiliations
    assert not any("contribution" in affiliation for affiliation in affiliations)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Authors are with Delft University of Technology, The Netherlands",
            "Delft University of Technology, The Netherlands",
        ),
        ("The authors are with the School of Computing, KAIST", "School of Computing, KAIST"),
        ("The author is affiliated with MIT", "MIT"),
    ],
)
def test_strips_authors_are_with_prefix(raw: str, expected: str) -> None:
    html = f'<div class="ltx_authors"><span class="ltx_contact ltx_role_affiliation">{raw}</span></div>'
    assert parse_front_matter(html).affiliations == (expected,)


def test_ignores_authorship_footnotes(paper_html: PaperHtml) -> None:
    affiliations = parse_front_matter(paper_html("2609.21811")).affiliations
    assert not any("authorship" in affiliation for affiliation in affiliations)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Technical University of Munich\nMunich, Germany",
            ("Technical University of Munich, Munich, Germany",),
        ),
        (
            "Seoul National University, Seoul, Korea\nSamsung Electronics, Korea",
            (
                "Seoul National University, Seoul, Korea",
                "Samsung Electronics, Korea",
            ),
        ),
        ("Stanford University\nNVIDIA", ("Stanford University", "NVIDIA")),
    ],
    ids=["place-joins-previous-line", "complete-affiliations-stay-apart", "names-stay-apart"],
)
def test_joins_lines_that_only_name_a_place(raw: str, expected: tuple[str, ...]) -> None:
    html = f'<div class="ltx_authors"><span class="ltx_contact ltx_role_affiliation">{raw}</span></div>'
    assert parse_front_matter(html).affiliations == expected


def test_drops_conjunctions_split_from_affiliations() -> None:
    raw = "Bioengineering Department, UCLA\n and \nMila - Quebec AI Institute\n& Canada-CIFAR AI Chair"
    html = f'<div class="ltx_authors"><span class="ltx_contact ltx_role_affiliation">{raw}</span></div>'
    assert parse_front_matter(html).affiliations == (
        "Bioengineering Department, UCLA",
        "Mila - Quebec AI Institute",
        "Canada-CIFAR AI Chair",
    )


def test_author_names_are_not_affiliations(paper_html: PaperHtml) -> None:
    front = parse_front_matter(paper_html("2609.30249"), authors=("Nvidia", "Jiayuan Mao"))
    assert "NVIDIA" not in front.affiliations
    assert "University of Pennsylvania" in front.affiliations


def test_parse_abstract(paper_html: PaperHtml) -> None:
    abstract = parse_front_matter(paper_html("2609.30249")).abstract

    assert abstract is not None
    assert abstract.startswith("Coding agents have demonstrated enormous success")
    assert "Abstract" not in abstract[:20]
    assert "(RAPID), which" in abstract
    assert "\n" not in abstract


def test_parse_abstract_renders_math_as_latex(paper_html: PaperHtml) -> None:
    abstract = parse_front_matter(paper_html("2609.23431")).abstract

    assert abstract is not None
    assert "$K$" in abstract


def test_missing_front_matter(paper_html: PaperHtml) -> None:
    assert parse_front_matter(paper_html("2609.25615")) == FrontMatter()


def test_fetch_front_matter_returns_empty_on_404() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(404))
    with HttpClient(transport=transport) as client:
        assert fetch_front_matter(client, "https://arxiv.org/html/2609.00000v1") == FrontMatter()


def test_fetch_front_matter_parses_page(paper_html: PaperHtml) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text=paper_html("2609.30249")))
    with HttpClient(transport=transport) as client:
        front = fetch_front_matter(client, "https://arxiv.org/html/2609.30249v1")
    assert "NVIDIA" in front.affiliations
    assert front.abstract
