from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from preprint_radar.http import HttpClient
from preprint_radar.sources.arxiv_html import (
    FrontMatter,
    PageCache,
    clean_affiliation,
    clean_affiliations,
    fetch_front_matter,
    front_matter_html,
    name_key,
    names_only_authors,
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
        pytest.param(
            "2609.05518",
            ("The Hong Kong Polytechnic University", "Jilin University"),
            id="mailbox-names-after-an-affiliation",
        ),
        pytest.param(
            "2609.12885",
            (
                "Faculty of Library, Information and Media Science, University of Tsukuba",
                "Pixie Dust Technologies, Inc",
            ),
            id="obfuscated-address-alone",
        ),
        pytest.param(
            "2609.37046",
            ("Munich University of Applied Sciences, Intelligent Vehicles Lab (IVL), 80335 Munich, Germany",),
            id="obfuscated-address-after-an-affiliation",
        ),
        pytest.param(
            "2609.06721",
            ("National University of Singapore", "University of Science and Technology of China"),
            id="are-with-sentences-in-the-affiliation",
        ),
    ],
)
def test_parse_affiliations(paper_html: PaperHtml, arxiv_id: str, expected: tuple[str, ...]) -> None:
    assert parse_front_matter(paper_html(arxiv_id)).affiliations == expected


def test_splits_also_with_into_affiliations(paper_html: PaperHtml) -> None:
    affiliations = parse_front_matter(paper_html("2609.00814")).affiliations

    assert [affiliation.split(",")[0] for affiliation in affiliations] == [
        "Aerospace Information Research Institute",
        "School of Electronic",
        "University of Chinese Academy of Sciences",
        "National Key Laboratory of Target Cognition and Application Technology (TCAT)",
    ]


def test_never_returns_contact_details(paper_html: PaperHtml) -> None:
    for arxiv_id in (
        "2609.30234",
        "2609.28473",
        "2609.30249",
        "2609.30056",
        "2609.26161",
        "2609.29650",
        "2609.05518",
        "2609.12885",
        "2609.37046",
    ):
        for affiliation in parse_front_matter(paper_html(arxiv_id)).affiliations:
            assert "@" not in affiliation
            assert "http" not in affiliation
            assert "(at)" not in affiliation
            assert "[at]" not in affiliation
            assert "{" not in affiliation


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
    "2609.36458": ("Abdullah All Tanvir", "Xin Zhong"),
    "2609.05583": (
        "Márcus Lobo",
        "Vitor Matias",
        "Afonso Paiva",
        "Jeová Farias",
        "Tiago Novello",
        "Moacir Ponti",
    ),
    "2609.38153": ("Trong-Tung Nguyen", "Anand Bhattad"),
    "2609.37030": (
        "Jiahao Zhan",
        "Yongrui Ma",
        "Qunliang Xing",
        "Xuanyu Zhang",
        "Jingqi Tong",
        "Junlin Li",
        "Li zhang",
        "Shijie Zhao",
        "Tianfan Xue",
    ),
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
    "2608.30420": (
        "Tiffanie Godelaine",
        "Maxime Zanella",
        "Karim El Khoury",
        "Benoit Macq",
        "Christophe De Vleeschouwer",
    ),
    "2609.37107": (
        "Rajit Rajpal",
        "Shahbuland Matiana",
        "Liew Wei Pyn",
        "Anmol Agarwal",
        "Ryan Craig",
        "Andrew Lapp",
        "Mithun Hunsur",
        "Sami BuGhanem",
        "Scottie Fox",
        "Aaron Sanders",
        "Carson Poole",
        "Irene Park",
        "Dave Rossi",
        "Spencer Frazier",
        "Louis Castricato",
    ),
    "2609.38180": (
        "Hao-Tang Tsui",
        "Yu-Rou Tuan",
        "Xiaoxuan Ma",
        "Nicolas Ugrinovic",
        "Takaaki Shiratori",
        "Kris Kitani",
    ),
    "2609.04190": (
        "Adheesh Sunil Juvekar",
        "Onkar Kishor Susladkar",
        "Kiet A. Nguyen",
        "Muntasir Wahed",
        "Nabeel Bashir",
        "Xiaona Zhou",
        "Tianjiao Yu",
        "Vedant Shah",
        "Ismini Lourentzou",
    ),
    "2609.06721": ("Hangyu Qin", "Junbin Xiao", "Shenglang Zhang", "Angela Yao"),
    "2609.00814": (
        "Kaiyue Kang",
        "Qixuan He",
        "Peijin Wang",
        "Yingchao Feng",
        "Chao Ren",
        "Kangxin Wang",
        "Wenhui Diao",
        "Yixiao Wang",
        "Liangjin Zhao",
        "Kaiwen Wei",
        "Nayu Liu",
        "Xian Sun",
    ),
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
        # The first author's name is printed as an affiliation: once it is dropped, the one
        # affiliation left is not given to everyone.
        pytest.param("2609.38153", (None, (0,)), id="single-affiliation-next-to-a-dropped-name"),
        pytest.param(
            "2609.37030",
            ((0, 1), (0, 1), (1,), (2,), (3,), (1,), (1,), (1,), (0, 4)),
            id="per-author-without-correspondence-line",
        ),
        pytest.param("2609.36458", None, id="shared-block-on-the-last-author"),
        pytest.param("2609.05583", ((0,), (0,), (0,), (2,), (1,), (0,)), id="one-creator-for-all-names"),
        pytest.param("2609.26512", ((0,), None, (1, 2), None), id="per-author-elsarticle-keys"),
        pytest.param("2608.29027", ((0,), (1,), (2,)), id="per-author-empty-fields"),
        pytest.param("2609.26161", None, id="no-markers-on-names"),
        pytest.param("2609.28473", None, id="shared-block-without-markers"),
        pytest.param("2609.06721", ((0,), (1,), (1,), (0,)), id="are-with-sentences-in-the-affiliation"),
        pytest.param(
            "2609.00814",
            ((0, 1, 2, 3),) * 3 + ((0, 3),) * 2 + ((0, 1, 2, 3),) * 2 + ((0, 3),) * 4 + ((0, 1, 2, 3),),
            id="also-with-gives-every-affiliation",
        ),
        # Another author's name was printed as the affiliation of Xiaoxuan Ma: the one
        # affiliation left is not everyone's (Takaaki Shiratori is not at CMU).
        pytest.param("2609.38180", None, id="names-dropped-next-to-a-single-affiliation"),
        # Co-authors' names in the affiliation macros, and links set as authors after the
        # last one: the block of Louis Castricato, the last author, is everyone's.
        pytest.param("2609.37107", None, id="links-set-as-authors"),
        pytest.param(
            "2609.04190", ((0,), (0,), (0,), *(None,) * 6), id="name-lists-among-per-author-contacts"
        ),
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


@pytest.mark.parametrize(
    ("arxiv_id", "expected"),
    [
        pytest.param("2609.38180", ("Carnegie Mellon University",), id="accented-name"),
        pytest.param("2609.04190", ("University of Illinois Urbana-Champaign",), id="lists-of-names"),
        pytest.param("2608.30420", (), id="ieee-grades"),
    ],
)
def test_drops_author_names_printed_as_affiliations(
    paper_html: PaperHtml, arxiv_id: str, expected: tuple[str, ...]
) -> None:
    assert parse_front_matter(paper_html(arxiv_id), authors=AUTHORS[arxiv_id]).affiliations == expected


def test_a_source_of_names_only_leaves_its_turn_to_the_next() -> None:
    authors = ("Ada Lovelace", "Bob Smith")
    html = _author_block(
        *((name, ()) for name in authors), contacts=("Ada Lovelace and Bob Smith",)
    ) + _thanks("Ada Lovelace and Bob Smith are with MIT.")

    front = parse_front_matter(html, authors=authors)

    assert front.affiliations == ("MIT",)
    assert front.author_affiliations == ((0,), (0,))


@pytest.mark.parametrize(
    "text",
    [
        "Nicolás Ugrinovic",
        "Eduil Nascimento Jr",
        "Yiqun Zhang, and Yiu-Ming Cheung",
        "Shuai Tao & Wulong Liu",
        "Benoît Macq Fellow, IEEE, and Christophe De Vleeschouwer Member, IEEE",
        "Senior Member, IEEE Ada Lovelace",
    ],
)
def test_names_only_authors(text: str) -> None:
    authors = (
        "Nicolas Ugrinovic",
        "Eduil Nascimento Jr.",
        "Yiqun Zhang",
        "Yiu-Ming Cheung",
        "Shuai Tao",
        "Wulong Liu",
        "Benoit Macq",
        "Christophe De Vleeschouwer",
        "Ada Lovelace",
    )
    assert names_only_authors(text, authors)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("Yiqun Zhang, and Grace Hopper", id="someone-else"),
        pytest.param("Alzheimer\u2019s Disease Neuroimaging Initiative", id="collective"),
        pytest.param("Yiqun Zhang Lab", id="institution-word"),
        pytest.param(", IEEE", id="no-name"),
    ],
)
def test_names_of_others_or_institutions_stay(text: str) -> None:
    authors = ("Yiqun Zhang", "Alzheimer's Disease Neuroimaging Initiative")
    assert not names_only_authors(text, authors)


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


@pytest.mark.parametrize(
    "raw",
    [
        "1, 2",
        "AB",
        "* †",
        "the",
        "dot",
        "Code",
        "GitHub",
        "Core Contributors",
        "second authors",
        "School of",
        "Department of",
        "Graduate",
        "USA",
        "United Kingdom",
        "South Korea",
        "Singapore.",
    ],
)
def test_clean_affiliation_drops_what_names_nothing(raw: str) -> None:
    assert clean_affiliation(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("jane.doe (at) example.org", None, id="obfuscated-address"),
        pytest.param("MIT, USA lab [at] example [dot] org", "MIT, USA", id="obfuscated-address-after"),
        pytest.param("Jilin University{jane.doe, john.roe, j.smith}", "Jilin University", id="mailbox-names"),
        pytest.param("{jane.doe, john.roe. j.smith", None, id="unclosed-mailbox-names"),
        pytest.param("{Department of Physics}, MIT", "{Department of Physics}, MIT", id="braces-of-latex"),
        pytest.param(
            "University of Zurich, Switzerland ()", "University of Zurich, Switzerland", id="empty-brackets"
        ),
        pytest.param(
            "K. Prentice and J. Martin are with Guide Dogs NSW, Sydney, Australia",
            "Guide Dogs NSW, Sydney, Australia",
            id="are-with",
        ),
        pytest.param(
            "All authors are with Agile Robots SE, Munich", "Agile Robots SE, Munich", id="all-authors"
        ),
        pytest.param(
            "Frank Kirchner is additionally affiliated with the University of Bremen",
            "University of Bremen",
            id="additionally-affiliated",
        ),
        pytest.param(
            "The lab is at the University of Bremen",
            "The lab is at the University of Bremen",
            id="institution-before-the-verb",
        ),
    ],
)
def test_clean_affiliation_strips_contact_details_and_people(raw: str, expected: str | None) -> None:
    assert clean_affiliation(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(
            "School of AI, Wuhan University, Wuhan, China, and also with ByteDance, Beijing, China",
            ("School of AI, Wuhan University, Wuhan, China", "ByteDance, Beijing, China"),
            id="and-also-with",
        ),
        pytest.param(
            "CAS, Beijing, China, also with UCAS, Beijing, China, also with the TCAT Lab",
            ("CAS, Beijing, China", "UCAS, Beijing, China", "TCAT Lab"),
            id="several-also-with",
        ),
        pytest.param(
            "The authors are also with the Robot Visual Perception Center, Hunan University",
            ("Robot Visual Perception Center, Hunan University",),
            id="people-also-with",
        ),
        pytest.param(
            "A. Doe, B. Roe, and C. Poe are at Imperial College London. A. Doe is with the Robot Learning "
            "Lab. B. Roe is with the SWIRL Lab",
            ("Imperial College London", "Robot Learning Lab", "SWIRL Lab"),
            id="several-sentences",
        ),
        pytest.param("Code", (), id="nothing"),
    ],
)
def test_clean_affiliations_splits_what_holds_several(raw: str, expected: tuple[str, ...]) -> None:
    assert clean_affiliations(raw) == expected


@pytest.mark.parametrize(
    ("arxiv_id", "expected"),
    [
        pytest.param(
            "2609.36458",
            ("Department of Computer Science", "University of Nebraska Omaha, Omaha, NE, USA"),
            id="line-break-spacing",
        ),
        pytest.param("2609.38153", ("Johns Hopkins University",), id="spacing-and-project-website"),
        pytest.param(
            "2609.37030",
            ("MMLab, CUHK", "ByteDance Inc", "Peking University", "Fudan University", "CPII under InnoHK"),
            id="correspondence-line",
        ),
    ],
)
def test_drops_layout_and_link_leftovers(
    paper_html: PaperHtml, arxiv_id: str, expected: tuple[str, ...]
) -> None:
    assert parse_front_matter(paper_html(arxiv_id), authors=AUTHORS[arxiv_id]).affiliations == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("[5pt]", None, id="line-break-spacing-alone"),
        pytest.param(
            "[0.2em] Department of Physics", "Department of Physics", id="line-break-spacing-inline"
        ),
        pytest.param("MITProject page", "MIT", id="glued-link-label"),
        pytest.param(
            "Sony Depthsensing Solutions, Brussels, BelgiumProject page",
            "Sony Depthsensing Solutions, Brussels, Belgium",
            id="glued-link-label-after-a-country",
        ),
        pytest.param("Project Website:", None, id="link-label-alone"),
        pytest.param("Correspondence to: Shujun Wang", None, id="correspondence"),
        pytest.param(
            "Author to whom any correspondence should be addressed", None, id="correspondence-sentence"
        ),
    ],
)
def test_clean_affiliation_drops_layout_and_link_leftovers(raw: str, expected: str | None) -> None:
    assert clean_affiliation(raw) == expected


@pytest.mark.parametrize(
    ("listed", "respelled"),
    [
        # Respellings seen when a new version of a paper was listed.
        ("Ma Ziqi", "Ziqi Ma"),
        ("Shi Fan", "Fan Shi"),
        ("Niccol`o Cavagnero", "Niccolò Cavagnero"),
        ("Eduil Nascimento Jr.", "Eduil Nascimento Jr"),
        ("Yu-Ming Cheung", "Yu Ming Cheung"),
    ],
)
def test_name_key_ignores_spelling(listed: str, respelled: str) -> None:
    assert name_key(listed) == name_key(respelled)


def test_name_key_tells_people_apart() -> None:
    assert name_key("Noa Garcia") != name_key("Yuta Nakashima")


FULL_PAGE = """<html><head><title>A paper</title></head><body><article class="ltx_document">
<h1 class="ltx_title ltx_title_document">A paper</h1>
<div class="ltx_authors"><span class="ltx_creator ltx_role_author">
<span class="ltx_personname">Ada Lovelace <img src="orcid.png"/></span>
<span class="ltx_contact ltx_role_affiliation">MIT</span></span></div>
<figure class="ltx_figure"><img src="x1.png"/><figcaption>A teaser, big.</figcaption></figure>
<div class="ltx_abstract"><h6 class="ltx_title">Abstract</h6><p>We do things.</p></div>
<section class="ltx_section"><h2>Introduction</h2><p>Body text, Stanford University.</p></section>
<section class="ltx_bibliography"><p>References.</p></section>
</article></body></html>"""


def test_the_front_matter_of_a_page_extracts_like_the_page() -> None:
    small = front_matter_html(FULL_PAGE)

    assert parse_front_matter(small, authors=("Ada Lovelace",)) == parse_front_matter(
        FULL_PAGE, authors=("Ada Lovelace",)
    )
    assert "Introduction" not in small
    assert "References" not in small
    assert "teaser" not in small
    assert "orcid.png" not in small
    assert "We do things." in small


def test_a_page_without_a_document_is_kept_whole() -> None:
    assert front_matter_html("<p>Maintenance</p>") == "<p>Maintenance</p>"


def test_the_page_cache_keeps_front_matters_by_paper_version(tmp_path: Path) -> None:
    cache = PageCache(tmp_path / "pages")
    url = "https://arxiv.org/html/2609.30249v2"

    assert cache.get(url) is None
    assert url not in cache
    cache.put(url, FULL_PAGE)

    assert url in cache
    assert cache.get(url) == front_matter_html(FULL_PAGE)
    assert [path.relative_to(tmp_path) for path in (tmp_path / "pages").rglob("*")] == [
        Path("pages/2609"),
        Path("pages/2609/2609.30249v2.html.gz"),
    ]
    assert "https://arxiv.org/html/2609.30249v1" not in cache


def test_the_page_cache_forgets_a_page(tmp_path: Path) -> None:
    cache = PageCache(tmp_path)
    url = "https://arxiv.org/html/2609.30249v1"
    cache.put(url, "<p>An error page</p>")

    cache.discard(url)
    cache.discard(url)
    cache.discard("https://arxiv.org/html/")

    assert url not in cache


def test_the_page_cache_ignores_urls_that_name_no_paper_version(tmp_path: Path) -> None:
    cache = PageCache(tmp_path / "pages")
    cache.put("https://arxiv.org/html/../../etc/passwd", FULL_PAGE)

    assert not (tmp_path / "pages").exists()
    assert cache.get("https://arxiv.org/html/../../etc/passwd") is None
    assert 42 not in cache


def test_fetch_front_matter_reads_the_cache_first(tmp_path: Path, paper_html: PaperHtml) -> None:
    requests: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path.endswith("v9"):
            return httpx.Response(404)
        return httpx.Response(200, text=paper_html("2609.30249"))

    cache = PageCache(tmp_path / "pages")
    url = "https://arxiv.org/html/2609.30249v1"
    with HttpClient(transport=httpx.MockTransport(handle)) as client:
        first = fetch_front_matter(client, url, cache=cache)
        again = fetch_front_matter(client, url, cache=cache)
        missing = fetch_front_matter(client, "https://arxiv.org/html/2609.30249v9", cache=cache)

    assert requests == ["/html/2609.30249v1", "/html/2609.30249v9"]
    assert again == first
    assert "NVIDIA" in first.affiliations
    assert missing == FrontMatter()
    assert "https://arxiv.org/html/2609.30249v9" not in cache


# What the heuristics must not produce (TEST-4): each case names the wrong string a past
# version gave, or would give, and the affiliations the page gives instead.


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(
            "54th Research Institute of CETC, China", "54th Research Institute of CETC, China", id="54th"
        ),
        pytest.param("1 2nd Department of Radiology", "2nd Department of Radiology", id="2nd-after-a-marker"),
        pytest.param("3M Company, St. Paul, MN, USA", "3M Company, St. Paul, MN, USA", id="3M"),
        pytest.param("2 3D Vision Lab, Zhejiang University", "3D Vision Lab, Zhejiang University", id="3D"),
        pytest.param("4K Imaging Lab", "4K Imaging Lab", id="4K"),
        pytest.param("1Cornell University", "Cornell University", id="marker-glued"),
        pytest.param("12, 3 ETH Zurich", "ETH Zurich", id="markers"),
    ],
)
def test_numbers_that_start_a_name_are_not_markers(raw: str, expected: str) -> None:
    assert clean_affiliation(raw) == expected


_NUMBERED_BLOCK = """<div class="ltx_authors"><span class="ltx_creator ltx_role_author">
<span class="ltx_personname">Ada Lovelace<sup>1</sup>, Bob Smith<sup>2</sup>
<sup>1</sup>Stanford University
<sup>2</sup>3M Company, USA</span></span></div>"""


@pytest.mark.parametrize(
    ("html", "authors", "wrong", "expected"),
    [
        pytest.param(
            _author_block(("Ada Lovelace", ("Hyper<sup>2</sup>labs, Berlin, Germany",))),
            ("Ada Lovelace",),
            "labs, Berlin, Germany",
            ("Hyper2labs, Berlin, Germany",),
            id="superscript-inside-a-word",
        ),
        pytest.param(
            _author_block(("Ada Lovelace", ("Tampere University<sup>1</sup>Nokia Technologies",))),
            ("Ada Lovelace",),
            "Tampere University1Nokia Technologies",
            ("Tampere University", "Nokia Technologies"),
            id="superscript-between-words",
        ),
        pytest.param(
            _author_block(
                (
                    "Ada Lovelace",
                    ('Dept. of Computer Science<br class="ltx_break"/>University of Alabama, USA',),
                )
            ),
            ("Ada Lovelace",),
            "Dept. of Computer ScienceUniversity of Alabama, USA",
            ("Dept. of Computer Science", "University of Alabama, USA"),
            id="line-break-without-newline",
        ),
        pytest.param(
            _author_block(("Ada Lovelace", ("Dept. of Computer ScienceUniversity of Alabama, USA",))),
            ("Ada Lovelace",),
            "Dept. of Computer ScienceUniversity of Alabama, USA",
            ("Dept. of Computer Science, University of Alabama, USA",),
            id="line-break-lost-by-latexml",
        ),
        pytest.param(
            _author_block(("Ada Lovelace", ("54th Research Institute of CETC, Shijiazhuang, China",))),
            ("Ada Lovelace",),
            "th Research Institute of CETC, Shijiazhuang, China",
            ("54th Research Institute of CETC, Shijiazhuang, China",),
            id="ordinal",
        ),
        pytest.param(
            _NUMBERED_BLOCK,
            ("Ada Lovelace", "Bob Smith"),
            "M Company, USA",
            ("Stanford University", "3M Company, USA"),
            id="numbered-3M",
        ),
        pytest.param(
            _author_block(("Nicolas Ugrinovic", ("Nicolás Ugrinovic",)), contacts=("MIT",)),
            ("Nicolas Ugrinovic",),
            "Nicolás Ugrinovic",
            ("MIT",),
            id="accented-author-name",
        ),
        pytest.param(
            _author_block(
                ("Yiqun Zhang", ()), ("Yiu-Ming Cheung", ()), contacts=("Yiqun Zhang, and Yiu-Ming Cheung",)
            )
            + _thanks("Yiqun Zhang and Yiu-Ming Cheung are with Hong Kong Baptist University."),
            ("Yiqun Zhang", "Yiu-Ming Cheung"),
            "Yiqun Zhang, and Yiu-Ming Cheung",
            ("Hong Kong Baptist University",),
            id="list-of-author-names",
        ),
        pytest.param(
            _author_block(("Ada Lovelace", ("TUM, Munich, Germany ivl [at] example.org",))),
            ("Ada Lovelace",),
            "TUM, Munich, Germany ivl [at] example.org",
            ("TUM, Munich, Germany",),
            id="obfuscated-address",
        ),
        pytest.param(
            _author_block(("Ada Lovelace", ("MIT{ada.lovelace, bob.smith}",))),
            ("Ada Lovelace",),
            "MIT{ada.lovelace, bob.smith}",
            ("MIT",),
            id="mailbox-list",
        ),
    ],
)
def test_pages_never_give(html: str, authors: tuple[str, ...], wrong: str, expected: tuple[str, ...]) -> None:
    affiliations = parse_front_matter(html, authors=authors).affiliations
    assert wrong not in affiliations
    assert affiliations == expected


def test_numbered_lines_place_names_that_start_with_a_number() -> None:
    front = parse_front_matter(_NUMBERED_BLOCK, authors=("Ada Lovelace", "Bob Smith"))
    assert front.author_affiliations == ((0,), (1,))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(
            "Department of Mathematics and StatisticsAuburn University, AL, 36849, USA",
            "Department of Mathematics and Statistics, Auburn University, AL, 36849, USA",
            id="unit-then-university",
        ),
        pytest.param(
            "Tsinghua Laboratory of Brain and Intelligence (THBI)IDG/McGovern Institute",
            "Tsinghua Laboratory of Brain and Intelligence (THBI), IDG/McGovern Institute",
            id="closing-bracket",
        ),
        pytest.param("AnimSchool, Utah, USA", "AnimSchool, Utah, USA", id="name-without-unit"),
        pytest.param("Google DeepMind, London", "Google DeepMind, London", id="brand"),
        pytest.param("School of AI, McGill University", "School of AI, McGill University", id="mc"),
        pytest.param(
            "Harbin Institute of Technology (ShenZhen)",
            "Harbin Institute of Technology (ShenZhen)",
            id="brackets",
        ),
        pytest.param(
            "Research Center of Knowledge-DrivenHuman-Machine Intelligence",
            "Research Center of Knowledge-DrivenHuman-Machine Intelligence",
            id="hyphenated-word",
        ),
    ],
)
def test_parts_glued_by_latexml_are_separated(raw: str, expected: str) -> None:
    assert clean_affiliation(raw) == expected
