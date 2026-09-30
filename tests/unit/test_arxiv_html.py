from collections.abc import Callable

import httpx
import pytest

from preprint_radar.http import HttpClient
from preprint_radar.sources.arxiv_html import (
    FrontMatter,
    clean_affiliation,
    fetch_front_matter,
    parse_front_matter,
)

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
        pytest.param(
            "2609.26512",
            (
                (
                    "Centre for Human-Computer Interaction, Indian Institute of Technology, Mandi, 175075, "
                    "Himachal Pradesh, India"
                ),
                "Freie Universität, Berlin, Germany",
                "Goethe University, Frankfurt, Germany",
            ),
            id="elsarticle-key-values-wrapped-across-lines",
        ),
        pytest.param(
            "2608.29027",
            (
                (
                    "Research and Development Application Department, FPT University, Cantho city, "
                    "90000, Vietnam"
                ),
                "School of Electrical Engineering, Korea University, Seoul city, 02841, South Korea",
                "Department of Information Technology, FPT University, Cantho city, 90000, Vietnam",
            ),
            id="empty-fields-leave-no-double-commas",
        ),
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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(
            "addressline=Department of Data Science, city=Erlangen, "
            "organization=Friedrich-Alexander University, postcode=91054, country=Germany",
            "Friedrich-Alexander University, Department of Data Science, Erlangen, 91054, Germany",
            id="organization-first",
        ),
        pytest.param(
            "postcode=91054, organization=Friedrich-Alexander University, city=Erlangen",
            "Friedrich-Alexander University, 91054, Erlangen",
            id="leading-postcode-kept",
        ),
        pytest.param(
            "organization=Indian Institute of Technology Ropar, city=Rupnagar, citysep=, postcode=140001, "
            "state=Punjab, country=India",
            "Indian Institute of Technology Ropar, Rupnagar, 140001, Punjab, India",
            id="empty-values-dropped",
        ),
        pytest.param(
            "organization=IIT, addressline=Mandi, city=Mandi, country=India",
            "IIT, Mandi, India",
            id="repeated-value-once",
        ),
        pytest.param(
            "orgnization=the Hupan Lab, city=Hangzhou, country=China",
            "the Hupan Lab, Hangzhou, China",
            id="misspelled-key",
        ),
        pytest.param(
            "FPT University, , Cantho city, 90000, , Vietnam", "FPT University, Cantho city, 90000, Vietnam"
        ),
    ],
)
def test_cleans_elsarticle_keys_and_empty_fields(raw: str, expected: str) -> None:
    assert clean_affiliation(raw) == expected


def test_splits_elsarticle_affiliations_at_a_repeated_key() -> None:
    raw = (
        "organization=Centre for Human-Computer\nInteraction, IIT,\ncity=Mandi, country=India\n"
        "organization=Goethe University, city=Frankfurt, country=Germany"
    )
    html = f'<div class="ltx_authors"><span class="ltx_contact ltx_role_affiliation">{raw}</span></div>'
    assert parse_front_matter(html).affiliations == (
        "Centre for Human-Computer Interaction, IIT, Mandi, India",
        "Goethe University, Frankfurt, Germany",
    )


AUTHORS = {
    "2609.30234": (
        "Ding-Jiun Huang",
        "Yuanhao Wang",
        "Cheng Zhang",
        "Hugo Bertiche",
        "Alexandru-Eugen Ichim",
        "Thabo Beeler",
        "Fernando De la Torre",
    ),
    "2609.21811": (
        "Muhammet Sami Yavuz",
        "Sabri Mustafa Kahya",
        "Richard R. Chen",
        "Jana Lipkova",
        "Benedikt Wiestler",
    ),
    "2609.30056": (
        "Yang Zhou",
        "Jiuhong Xiao",
        "Shizhao Ye",
        "Long Quang",
        "Carlos Nieto-Granda",
        "Giuseppe Loianno",
    ),
    "2609.11271": (
        "Hyunsu Go",
        "Youngung Han",
        "Kyeonghun Kim",
        "Jinyong Jun",
        "Junbeom Lee",
        "Dohyun Kweon",
        "Yului Jeong",
        "Suah Park",
        "Sungha Park",
        "Anna Jung",
        "Woo Kyoung Jeong",
        "Ken Ying-Kai Liao",
        "Hyuk-Jae Lee",
        "Nam-Joon Kim",
    ),
    "2609.29350": ("Yuling Jiao", "Wensen Ma", "Houduo Qi", "Defeng Sun"),
    "2609.25108": (
        "Khoa Pham-Dinh",
        "Sanaz Nami",
        "Hamed Rezazadegan Tavakoli",
        "Moncef Gabbouj",
        "Farhad Pakdaman",
    ),
    "2609.29721": ("Toya Oyama", "Rainer Lienhart", "Shin'ichi Satoh"),
    "2609.29650": (
        "David Chushig-Muzo",
        "Luis M. López-Ramos",
        "Ángeles Rodríguez de Cara",
        "Eva Milara",
        "Luis Zhinin-Vera",
        "Diego H. Peluffo-Ordóñez",
    ),
    "2609.29384": ("Changqing Gong", "Huafeng Qin", "Mounîm A. El-Yacoubi"),
    "2609.23431": ("Junwen Chen", "Keiji Yanai"),
    "2609.26161": ("Ignacio Bugueno-Cordova", "Javier Ruiz-del-Solar", "Rodrigo Verschae"),
    "2609.28473": (
        "Chao Feng",
        "Zhiyang Xu",
        "Bowei Chen",
        "Yuanjun Xiong",
        "Xiyao Wang",
        "Jui-Hsien Wang",
        "Richard Zhang",
        "Zhe Lin",
        "Andrew Owens",
        "Yijun Li",
    ),
    "2609.26512": ("Shashank Baghel", "Kshitij Dwivedi", "Dinesh Singh", "Sanjeev Nara"),
    "2608.29027": ("Anh Nguyen Quynh", "Khang Nguyen Quoc", "Luyl-Da Quach"),
}


@pytest.mark.parametrize(
    ("arxiv_id", "expected"),
    [
        pytest.param(
            "2609.30234",
            ((0,), (1,), (2,), (3,), (4,), (4,), (0,)),
            id="one-affiliation-block-per-author",
        ),
        pytest.param("2609.21811", ((0, 1), (2,), (3,), (4,), (0, 1)), id="per-author-multi-line"),
        pytest.param(
            "2609.30056",
            ((0,), (0, 1), (1,), (0, 2), (2,), (1,)),
            id="per-author-authors-are-with",
        ),
        pytest.param(
            "2609.11271",
            ((0,), (0, 1), (1,), (0,), (2,), (1, 3), (0,), (0,), (0,), (0,), (4,), (5,), (0,), (0,)),
            id="markers-on-names",
        ),
        pytest.param("2609.29350", ((0,), (1,), (2, 1), (1,)), id="markers-in-footnote"),
        pytest.param(
            "2609.25108",
            ((0,), (0,), (1,), (0,), (1,)),
            id="markers-after-the-affiliation",
        ),
        pytest.param("2609.29721", ((0, 1), (2,), (1, 0)), id="symbol-marker-runs"),
        pytest.param(
            "2609.29650",
            ((0,), (0,), (0,), (0,), (1,), (2,)),
            id="thanks-sentences-with-initials",
        ),
        pytest.param("2609.29384", ((0,), (1,), (0,)), id="thanks-sentences"),
        pytest.param("2609.23431", ((0,), (0,)), id="single-affiliation-is-everyones"),
        pytest.param("2609.26512", ((0,), None, (1, 2), None), id="per-author-elsarticle-keys"),
        pytest.param("2608.29027", ((0,), (1,), (2,)), id="per-author-empty-fields"),
        pytest.param("2609.26161", None, id="no-markers-on-names"),
        pytest.param("2609.28473", None, id="shared-block-without-markers"),
    ],
)
def test_maps_authors_to_their_affiliations(
    paper_html: PaperHtml, arxiv_id: str, expected: tuple[tuple[int, ...] | None, ...] | None
) -> None:
    front = parse_front_matter(paper_html(arxiv_id), authors=AUTHORS[arxiv_id])
    assert front.author_affiliations == expected


def test_maps_every_affiliation_to_a_single_author() -> None:
    html = """<div class="ltx_authors"><span class="ltx_creator ltx_role_author">
      <span class="ltx_personname">Ada Lovelace</span>
      <span class="ltx_contact ltx_role_affiliation">MIT</span>
      <span class="ltx_contact ltx_role_affiliation">NVIDIA</span></span></div>"""
    front = parse_front_matter(html, authors=("Ada Lovelace",))
    assert front.author_affiliations == ((0, 1),)


def test_mapping_needs_the_author_list(paper_html: PaperHtml) -> None:
    assert parse_front_matter(paper_html("2609.30234")).author_affiliations is None


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


def _author_block(*creators: tuple[str, tuple[str, ...]], contacts: tuple[str, ...] = ()) -> str:
    """An author block: each creator's name and own contacts, then contacts shared by all."""
    spans = "".join(
        f'<span class="ltx_creator ltx_role_author"><span class="ltx_personname">{name}</span>'
        + "".join(_contact(text) for text in own)
        + "</span>"
        for name, own in creators
    )
    return f'<div class="ltx_authors">{spans}{"".join(_contact(text) for text in contacts)}</div>'


def _contact(text: str) -> str:
    return f'<span class="ltx_contact ltx_role_affiliation">{text}</span>'


def _thanks(text: str) -> str:
    return f'<span class="ltx_note ltx_role_thanks"><span class="ltx_note_content">{text}</span></span>'


def test_thanks_sentences_on_one_line_end_before_the_next_initials() -> None:
    authors = ("Eva Milara", "Luis Zhinin", "Plato")
    html = _author_block(*((name, ()) for name in authors)) + _thanks(
        "E. Milara is with the University of Madrid, Spain. "
        "L. Zhinin is with the University of Quito, Ecuador."
    )

    front = parse_front_matter(html, authors=authors)

    assert front.affiliations == ("University of Madrid, Spain", "University of Quito, Ecuador")
    assert front.author_affiliations == ((0,), (1,), None)


def test_thanks_sentences_keep_abbreviations_in_affiliations() -> None:
    html = _thanks("A. Doe is with the Dept. of CS, MIT, USA. B. Roe is with Stanford University.")

    assert parse_front_matter(html).affiliations == ("Dept. of CS, MIT, USA", "Stanford University")


def test_thanks_sentences_with_two_affiliations() -> None:
    html = _thanks("A. Doe is with the University of Madrid, and is also with the University of Quito.")

    assert parse_front_matter(html).affiliations == ("University of Madrid", "University of Quito")


def test_thanks_initials_shared_by_two_authors_name_neither() -> None:
    authors = ("Eva Milara", "Emilio Milara")
    html = _author_block(*((name, ()) for name in authors)) + _thanks(
        "E. Milara is with the University of Madrid, Spain. The authors are with the University of Quito."
    )

    assert parse_front_matter(html, authors=authors).author_affiliations == ((1,), (1,))


def test_thanks_sentences_place_each_author_once() -> None:
    authors = ("Ada Lovelace", "Bob Smith")
    html = _author_block(
        *((name, ()) for name in authors), contacts=("University of Madrid", "University of Quito")
    ) + _thanks(
        "The authors are with the University of Madrid. Ada Lovelace is with the University of Madrid. "
        "Bob Smith is with the Moon. Bob Smith is also with the University of Quito."
    )

    assert parse_front_matter(html, authors=authors).author_affiliations == ((0,), (0, 1))


def test_no_mapping_without_an_author_block() -> None:
    html = _thanks("Ada Lovelace is with MIT. Bob Smith is with NVIDIA.")

    front = parse_front_matter(html, authors=("Ada Lovelace", "Bob Smith"))

    assert front.affiliations == ("MIT", "NVIDIA")
    assert front.author_affiliations is None


def test_markers_skip_symbols_and_repeated_affiliations() -> None:
    authors = ("Ada Lovelace", "Bob Smith", "Carl Jones")
    html = _author_block(
        ("Ada Lovelace<sup>1,2</sup>", ()),
        ("Bob Smith<sup>*</sup>", ()),
        ("Carl Jones<sup>3</sup>", ()),
        contacts=("<sup>1</sup>MIT <sup>2</sup>MIT <sup>3</sup>NVIDIA",),
    )

    # Ada's two markers name the same affiliation; Bob's only marker is a contribution note.
    assert parse_front_matter(html, authors=authors).author_affiliations == ((0,), None, (1,))


def test_a_marker_without_affiliation_drops_the_markers() -> None:
    html = _author_block(
        ("Ada Lovelace<sup>1</sup>", ()),
        ("Bob Smith<sup>4</sup>", ()),
        contacts=("<sup>1</sup>MIT <sup>3</sup>NVIDIA",),
    )

    assert parse_front_matter(html, authors=("Ada Lovelace", "Bob Smith")).author_affiliations is None


def test_an_ambiguous_creator_name_drops_the_per_author_blocks() -> None:
    html = _author_block(("A. Lovelace", ("MIT",)), ("Bob Smith", ("NVIDIA",)))

    front = parse_front_matter(html, authors=("Ada Lovelace", "Anna Lovelace", "Bob Smith"))

    assert front.author_affiliations is None


@pytest.mark.parametrize(
    ("creators", "authors", "expected"),
    [
        pytest.param(("Jane Roe", "Bob Smith"), ("Jane Doe", "Bob Smith"), ((0,), (1,)), id="same-position"),
        pytest.param(
            ("Xavier Unknown", "Bob Smith"), ("Bob Smith", "Carl Jones"), ((1,), None), id="position-taken"
        ),
    ],
)
def test_unmatched_creators_fall_back_on_their_position(
    creators: tuple[str, str], authors: tuple[str, str], expected: tuple[tuple[int, ...] | None, ...]
) -> None:
    html = _author_block((creators[0], ("MIT",)), (creators[1], ("NVIDIA",)))

    assert parse_front_matter(html, authors=authors).author_affiliations == expected


def test_notes_without_content_give_nothing() -> None:
    html = (
        '<article class="ltx_document">'
        '<span class="ltx_note ltx_role_address">Massachusetts Institute of Technology</span>'
        '<span class="ltx_note ltx_role_footnotetext"><sup>1</sup>Stanford University</span>'
        "</article>"
    )

    assert parse_front_matter(html).affiliations == ()


@pytest.mark.parametrize("raw", ["1, 2", "AB", "* †"])
def test_clean_affiliation_drops_what_names_nothing(raw: str) -> None:
    assert clean_affiliation(raw) is None
