import gzip
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
    first_version_url,
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
                # Its own creator, numbered: "¹R&D Center for Digital Nature, ...".
                "R&D Center for Digital Nature, University of Tsukuba",
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
        pytest.param(
            "2610.15403",
            (
                "Department of Geography, National University of Singapore, Singapore",
                "College of Geodesy and Geomatics, Shandong University of Science and Technology, China",
                "University of the Bundeswehr Munich, Germany",
                (
                    "State Key Laboratory of Information Engineering in Surveying, Mapping and Remote "
                    "Sensing, Wuhan University, China"
                ),
                (
                    "School of Forest, Fisheries and Geomatics Sciences, University of Florida, "
                    "Gainesville, FL, USA"
                ),
                "Fort Lauderdale Research and Education Center, University of Florida, Davie, FL, USA",
                "Institute of Remote Sensing and GIS, Peking University, China",
                "Department of Architecture, National University of Singapore, Singapore",
                "Department of Real Estate, National University of Singapore, Singapore",
            ),
            id="affiliation-note-after-the-abstract",
        ),
        pytest.param(
            "2610.17605",
            (
                "Oregon State University",
                "The Ohio State University",
                "Argonne National Laboratory",
                "The University of Texas Rio Grande Valley",
            ),
            id="lines-led-by-symbols",
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
    "2610.01434": (
        "Xudong Wang",
        "Hao Wu",
        "Haozhe Hu",
        "Peiran Yin",
        "Xinghao Chen",
        "Yunpu Ma",
        "Wei Zhang",
        "Xiaoyu Shen",
    ),
    "2610.02382": (
        "Zhongpai Gao",
        "Benjamin Planche",
        "Meng Zheng",
        "Anwesa Choudhuri",
        "Terrence Chen",
        "Ziyan Wu",
    ),
    "2610.03290": (
        "Christiaan M. Geldenhuys",
        "Joshua M. Jansen van Vüren",
        "Véronique Suttels",
        "Trevor Brokowski",
        "Ablo P. Wachinou",
        "Mary-Anne Hartley",
        "Rensu P. Theart",
        "Grant Theron",
        "Thomas R. Niesler",
    ),
    "2609.36407": ("Zhiyuan Yang", "Jiahao Cheng", "Mahdi S. Hosseini"),
    "2610.12978": (
        "Zihao Pan",
        "Mengting Chen",
        "Cheng Shi",
        "Taihang Hu",
        "Zhengrong Yue",
        "Zikang Wang",
        "Yuan Wang",
        "Wei Li",
        "Sibei Yang",
    ),
    "2610.15403": (
        "Hao Li",
        "Wenping Yin",
        "Fabian Deuser",
        "Jia Jia",
        "Ziqi Liu",
        "Levente Juhász",
        "Fan Zhang",
        "Filip Biljecki",
    ),
    "2610.17412": (
        "Xiaoya Tang",
        "Shilong Liu",
        "Daniel Smolyak",
        "Xiwen Li",
        "Quynh Nguyen",
        "Tolga Tasdizen",
    ),
    "2610.17605": (
        "Mingze Xia",
        "Yuxiao Li",
        "Baixi Sun",
        "Wenbo Li",
        "Pu Jiao",
        "Sheng Di",
        "Franck Cappello",
        "Hanqi Guo",
        "Xin Liang",
    ),
    # The listing glues the first two names: "Pan Yin. Shuai Yang".
    "2610.18323": (
        "Pan Yin. Shuai Yang",
        "Yuanhao Liu",
        "Datao Tang",
        "Jialin Li",
        "Hao Wang",
        "Pei Liu",
        "Kaiyu Li",
        "Cong Zhao",
        "Xiangyong Cao",
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
        # One address shared by both authors, written on the last one: its lines are one
        # affiliation, so it is everyone's.
        pytest.param("2609.36458", ((0,), (0,)), id="shared-address-on-the-last-author"),
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
        # Eight names in one creator, apart by wide spaces only: not a person, so the markers
        # place them (the creator went to the last author, at every affiliation).
        pytest.param(
            "2610.01434",
            ((0,), (0, 1), (0, 1), (0, 1), (0, 2), (3,), (0,), (0,)),
            id="one-creator-for-all-names-without-separators",
        ),
        pytest.param("2609.36407", ((0,), (0,), (0, 1)), id="a-pair-shares-its-block"),
        # Marker 2 reads "Laboratory ... Response / Technologies (LiGHT) / Swiss Federal
        # Institute of Technology (EPFL), ...": two affiliations, the first joined from two lines.
        pytest.param(
            "2610.03290",
            ((0,), (0,), (1, 2), (1, 2), (3,), (1, 2), (0,), (4, 5, 6, 7), (0,)),
            id="anchors-made-of-affiliations",
        ),
        # Two authors' names printed as the fourth one's affiliation, beside the shared one.
        pytest.param("2610.02382", None, id="names-beside-the-only-affiliation"),
        # The numbered lines and addresses set as authors are nobody: the last person alone
        # holds a contact ("¹Sun Yat-sen University"), so the markers place them. Zikang Wang
        # is written inside a contact, not as a creator: placed nowhere.
        pytest.param(
            "2610.12978",
            ((0, 1, 2), (1,), (2,), (1,), (3,), None, (1,), (1,), (0,)),
            id="numbered-lines-set-as-authors",
        ),
        pytest.param(
            "2610.15403", ((0,), (1,), (2,), (0,), (3,), (4, 5), (6,), (7, 8)), id="lettered-affiliation-note"
        ),
        pytest.param("2610.17412", ((0,), (1,), (2,), (0,), (2,), (0,)), id="affiliations-glued-to-names"),
        pytest.param(
            "2610.17605", ((0,), (1,), (2,), (0,), (3,), (2,), (2,), (1,), (0,)), id="lines-led-by-symbols"
        ),
        # The one affiliation of a block without markers is everyone's.
        pytest.param("2610.18323", ((0,),) * 9, id="unmarked-line-under-the-names"),
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
        (
            "National Research Council Canada\nLondon, ON, Canada",
            ("National Research Council Canada, London, ON, Canada",),
        ),
        ("University of Luxembourg\nTrier, Germany", ("University of Luxembourg", "Trier, Germany")),
        (
            "University of New South Wales\nCanberra, Australia",
            ("University of New South Wales, Canberra, Australia",),
        ),
        (
            "Kazakh-British Technical University\nAlmaty, Kazakhstan",
            ("Kazakh-British Technical University, Almaty, Kazakhstan",),
        ),
        (
            "Key Laboratory of Symbolic Computation of Ministry of\nEducation, Jilin University",
            ("Key Laboratory of Symbolic Computation of Ministry of Education, Jilin University",),
        ),
        (
            "TU Graz, Graz, Austria author@example.at\nUniversity of Alicante, Alicante, Spain",
            ("TU Graz, Graz, Austria", "University of Alicante, Alicante, Spain"),
        ),
    ],
    ids=[
        "place-joins-previous-line",
        "complete-affiliations-stay-apart",
        "names-stay-apart",
        "a-name-ending-with-the-same-country",
        "a-name-ending-with-another-country",
        "a-state-is-not-a-country",
        "more-countries",
        "a-line-ending-with-a-preposition",
        "an-address-ending-with-at",
    ],
)
def test_joins_lines_that_only_name_a_place(raw: str, expected: tuple[str, ...]) -> None:
    html = f'<div class="ltx_authors"><span class="ltx_contact ltx_role_affiliation">{raw}</span></div>'
    assert parse_front_matter(html).affiliations == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Division of Molecular Biology, Faculty of Medicine\nand Health Sciences",
            ("Division of Molecular Biology, Faculty of Medicine and Health Sciences",),
        ),
        (
            "Stanford University\nand Mila - Quebec AI Institute",
            ("Stanford University", "Mila - Quebec AI Institute"),
        ),
    ],
    ids=["a-unit-goes-on", "an-institution-does-not"],
)
def test_a_line_starting_with_and_continues_a_unit(raw: str, expected: tuple[str, ...]) -> None:
    html = f'<div class="ltx_authors"><span class="ltx_contact ltx_role_affiliation">{raw}</span></div>'
    assert parse_front_matter(html).affiliations == expected


def test_names_are_never_joined_to_the_next_line(paper_html: PaperHtml) -> None:
    front = parse_front_matter(paper_html("2610.02382"), authors=AUTHORS["2610.02382"])
    assert front.affiliations == ("United Imaging Intelligence, Boston MA, USA",)


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


def test_parse_abstract_renders_math_as_text(paper_html: PaperHtml) -> None:
    # MathML becomes the inline LaTeX of arXiv's metadata, which reads as text (SRCH-19).
    abstract = parse_front_matter(paper_html("2609.23431")).abstract

    assert abstract is not None
    assert "top-K" in abstract
    assert "$" not in abstract


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


def _thanks(text: str, kind: str = "") -> str:
    """A thanks note; ``kind`` is the type LaTeXML gives some ("funding", "correspondence")."""
    classes = f"ltx_note ltx_thanks_{kind} ltx_role_thanks" if kind else "ltx_note ltx_role_thanks"
    return f'<span class="{classes}"><span class="ltx_note_content">{text}</span></span>'


def test_a_thanks_note_that_only_names_an_affiliation_is_the_papers() -> None:
    # IEEE conference classes, as IROS papers write them (2609.26325, AFF-11).
    authors = ("Ada Lovelace", "Bob Smith")
    html = (
        _author_block(*((name, ()) for name in authors))
        + _thanks("Department of Computer Science, University of Freiburg, Germany.", "note")
        + _thanks("German Research Foundation, Emmy Noether Program.", "funding")
    )

    front = parse_front_matter(html, authors=authors)

    assert front.affiliations == ("Department of Computer Science, University of Freiburg, Germany",)
    assert front.author_affiliations == ((0,), (0,))


def test_a_numbered_list_in_a_thanks_note_after_its_sentences() -> None:
    # Markers LaTeXML printed as text, with a modifier circumflex (2609.16443).
    html = _thanks(
        "*Equal contribution. Work done while A. Doe was at USC. $\u02c61$University of Southern "
        "California, $\u02c62$Stanford University, $^{3}$UC San Diego."
    )

    assert parse_front_matter(html).affiliations == (
        "University of Southern California",
        "Stanford University",
        "UC San Diego",
    )


@pytest.mark.parametrize(
    "note",
    [
        pytest.param("Now at Google Research.", id="sentence"),
        pytest.param("jzlab.org", id="domain"),
        pytest.param("$^1$Alpha, $^2$Beta, $^3$Gamma University", id="too-few-institutions"),
        pytest.param(" . ", id="empty"),
    ],
)
def test_a_thanks_note_that_lists_no_affiliation_gives_none(note: str) -> None:
    assert parse_front_matter(_thanks(note)).affiliations == ()


def test_a_listed_affiliation_is_the_last_source() -> None:
    html = _author_block(("Ada Lovelace", ("MIT",))) + _thanks("University of Freiburg, Germany.")

    assert parse_front_matter(html, authors=("Ada Lovelace",)).affiliations == ("MIT",)


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


def test_a_sentence_that_names_no_place_states_no_affiliation() -> None:
    # A thanks note's "is at" whatever follows (AFF-9).
    html = _thanks("A. Doe is with MIT. This work is at the intersection of vision and language.")

    assert parse_front_matter(html).affiliations == ("MIT",)


def test_a_stated_affiliation_is_cut_at_its_semicolons() -> None:
    html = _thanks("A. Doe is with the University of Madrid; Robotics Institute, ETH Zurich.")

    assert parse_front_matter(html).affiliations == ("University of Madrid", "Robotics Institute, ETH Zurich")


def test_one_stated_affiliation_places_only_whom_it_names() -> None:
    # Not everyone's, as one affiliation of the first sources is (AFF-9).
    authors = ("Ada Lovelace", "Bob Smith")
    html = _author_block(*((name, ()) for name in authors)) + _thanks("Ada Lovelace is with MIT.")

    front = parse_front_matter(html, authors=authors)

    assert front.affiliations == ("MIT",)
    assert front.author_affiliations == ((0,), None)


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


def test_markers_written_without_separators_are_read_one_by_one() -> None:
    html = _author_block(
        ("Ada Lovelace<sup>12</sup>", ()),
        ("Bob Smith<sup>\u22c6\u2020</sup>", ()),
        contacts=("<sup>1</sup>MIT <sup>2</sup>NVIDIA <sup>\u22c6</sup>ETH Zurich <sup>\u2020</sup>EPFL",),
    )

    front = parse_front_matter(html, authors=("Ada Lovelace", "Bob Smith"))

    assert front.author_affiliations == ((0, 1), (2, 3))


def test_a_marker_without_affiliation_drops_the_markers() -> None:
    html = _author_block(
        ("Ada Lovelace<sup>1</sup>", ()),
        ("Bob Smith<sup>4</sup>", ()),
        contacts=("<sup>1</sup>MIT <sup>3</sup>NVIDIA",),
    )

    assert parse_front_matter(html, authors=("Ada Lovelace", "Bob Smith")).author_affiliations is None


def test_a_pair_is_not_placed_at_a_place_alone() -> None:
    html = _author_block(
        ("Ada Lovelace", ("Institute of Artificial Intelligence",)),
        ("Bob Smith", ("University of Central Florida",)),
        ("Carl Jones & Dan Brown", ("Orlando, FL 32816, USA",)),
    )

    front = parse_front_matter(html, authors=("Ada Lovelace", "Bob Smith", "Carl Jones", "Dan Brown"))

    assert front.author_affiliations == ((0,), (1,), None, None)


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
        "IEEE Publication Technology Department",
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
        pytest.param("MIT{jane_doe, john.roe}", "MIT", id="mailbox-names-with-underscores"),
        pytest.param(
            "{jane.doe,j_roe,jsmith, Apple", "Apple", id="unclosed-mailbox-names-before-an-affiliation"
        ),
        # Capitalized mailbox names, which dots or underscores join (2610.25235).
        pytest.param("KAUST {Jane.Doe, A_Roe}", "KAUST", id="capitalized-mailbox-names"),
        pytest.param(
            "{Jane.Doe, John.Roe, A.Smith, Mary.Major,", None, id="unclosed-capitalized-mailbox-names"
        ),
        pytest.param(
            "{Jane.Doe, John.Roe, Apple",
            "Apple",
            id="unclosed-capitalized-mailbox-names-before-an-affiliation",
        ),
        pytest.param("{Department of Physics}, MIT", "{Department of Physics}, MIT", id="braces-of-latex"),
        # A contact detail the rules leave is the whole string's end: `validate` would
        # refuse the store, and the run push nothing (AFF-32).
        pytest.param("Visual Lab, Tokyo {Jane, John}", None, id="mailbox-names-the-rules-leave"),
        pytest.param("Lab of X, jane (at) uni", None, id="obfuscated-address-the-rules-leave"),
        pytest.param(
            "University of Zurich, Switzerland ()", "University of Zurich, Switzerland", id="empty-brackets"
        ),
        pytest.param(
            "The University of Hong Kong, and", "The University of Hong Kong", id="list-cut-after-and"
        ),
        pytest.param(
            "Nanjing University of Posts and", "Nanjing University of Posts and", id="name-cut-after-and"
        ),
        pytest.param(
            "HafenCity University, Hamburg, Germany -", "HafenCity University, Hamburg, Germany", id="dash"
        ),
        pytest.param("\\addrDepartment of Physics, MIT", "Department of Physics, MIT", id="latex-command"),
        pytest.param("Tel.: +49 (0) 662 1541 4841", None, id="phone"),
        pytest.param(
            "A. Doe and B. Roe are with TUM, Munich, Germany. {jane.doe, john.roe}@example.org",
            "TUM, Munich, Germany",
            id="mailboxes-at-the-end",
        ),
        pytest.param(
            "Jane Doe is a Robotics Engineer at FloMobility Pvt. Ltd., Bangalore, India",
            "FloMobility Pvt. Ltd., Bangalore, India",
            id="a-role-at",
        ),
        pytest.param(
            "Technikum Wien, Vienna, Austria author@example.org",
            "Technikum Wien, Vienna, Austria",
            id="address-at-the-end",
        ),
        pytest.param("TODO: Jane Roe's affiliation and", None, id="placeholder"),
        # An unwrapped thanks note glues the address to the sentence (2609.10082).
        pytest.param(
            "HKUST, Hong Kong SAR, China (author@example.org)",
            "HKUST, Hong Kong SAR, China",
            id="address-in-brackets",
        ),
        # The sentence of a thanks note ends after the address (2609.28184).
        pytest.param(
            "the University of Trento, Trento, Italy. {name.surname}@example.org.",
            "the University of Trento, Trento, Italy",
            id="address-before-the-full-stop",
        ),
        # A lost line break glues the label to the country (2608.29996).
        pytest.param(
            "Wayne State University, MI, USAEmail: {jane, john}@example.org",
            "Wayne State University, MI, USA",
            id="label-glued-to-the-country",
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
        pytest.param(
            "Cornell University 2University of California, Berkeley",
            ("Cornell University", "University of California, Berkeley"),
            id="numbered-markers-as-text",
        ),
        pytest.param(
            "USTC 2CASIA 3HKUST(GZ) 4eBay", ("USTC", "CASIA", "HKUST(GZ)", "eBay"), id="markers-in-a-row"
        ),
        pytest.param(
            "Geely, 2Hunan University; 3ECNU",
            ("Geely", "Hunan University", "ECNU"),
            id="markers-after-commas",
        ),
        pytest.param("Code", (), id="nothing"),
        # Two spaces before a marker written as text (2402.13251).
        pytest.param(
            "Roblox  2Carnegie Mellon University  3Stanford University",
            ("Roblox", "Carnegie Mellon University", "Stanford University"),
            id="markers-after-wide-spaces",
        ),
    ],
)
def test_clean_affiliations_splits_what_holds_several(raw: str, expected: tuple[str, ...]) -> None:
    assert clean_affiliations(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("UCL, Gower Street, London WC1E 6AE, United Kingdom", id="uk-postcode"),
        pytest.param("Université Laval, Québec, QC G1V 0A6, Canada", id="canadian-postcode"),
        pytest.param("University of Windsor, ON, N9B 3P4, Canada", id="postcode-after-a-code"),
        pytest.param("Lab 3D Vision, 4K Media Group", id="one-letter-after-the-number"),
        pytest.param("54th Research Institute of CETC", id="ordinal"),
    ],
)
def test_numbers_inside_an_affiliation_are_not_markers(raw: str) -> None:
    assert clean_affiliations(raw) == (raw,)


def test_superscript_markers_glued_to_affiliations_start_numbered_lines() -> None:
    # Free-form block: names with markers, then numbered affiliations on one line.
    html = (
        '<div class="ltx_authors"><span class="ltx_creator ltx_role_author"><span class="ltx_personname">'
        "Ada Lovelace<sup>1*</sup> Bob Smith<sup>2,3*\u2021</sup> Carl Jones<sup>\u2217</sup><br/>"
        "<sup>1</sup>MIT <sup>2</sup>Duke University <sup>3</sup>NVIDIA"
        "</span></span></div>"
    )

    front = parse_front_matter(html, authors=("Ada Lovelace", "Bob Smith", "Carl Jones"))

    assert front.affiliations == ("MIT", "Duke University", "NVIDIA")
    # Symbols mark notes: "2,3*‡" is 2 and 3, and the asterisk operator alone is nothing.
    assert front.author_affiliations == ((0,), (1, 2), None)


@pytest.mark.parametrize(
    ("note", "expected", "placed"),
    [
        pytest.param(
            "Ada Lovelace and Bob Smith are with the School of\nComputing, University of Leeds, U.K.",
            ("School of Computing, University of Leeds, U.K",),
            ((0,), (0,)),
            id="sentence-wrapped",
        ),
        pytest.param(
            "Ada Lovelace,\nand Bob Smith are with the University of Leeds.",
            ("University of Leeds",),
            ((0,), (0,)),
            id="people-wrapped",
        ),
        pytest.param(
            "Ada Lovelace is with the University of Leeds, U.K\nBob Smith is with ETH Zurich.",
            ("University of Leeds, U.K", "ETH Zurich"),
            ((0,), (1,)),
            id="next-statement-without-full-stop",
        ),
        pytest.param(
            "The authors are with the University of Leeds\n* Equal contribution\nManuscript received May 1",
            ("University of Leeds",),
            ((0,), (0,)),
            id="notes-after-the-affiliation",
        ),
    ],
)
def test_thanks_notes_are_read_across_the_wraps_of_their_source(
    note: str, expected: tuple[str, ...], placed: tuple[tuple[int, ...], ...]
) -> None:
    authors = ("Ada Lovelace", "Bob Smith")
    html = _author_block(*((name, ()) for name in authors)) + _thanks(note)

    front = parse_front_matter(html, authors=authors)

    assert front.affiliations == expected
    assert front.author_affiliations == placed


@pytest.mark.parametrize(
    ("contacts", "expected"),
    [
        pytest.param(
            ("Department of Computer Science", "Dartmouth College", "Hanover, NH, USA"),
            ("Department of Computer Science, Dartmouth College, Hanover, NH, USA",),
            id="one-node-per-line",
        ),
        pytest.param(
            ('School of Physics<br class="ltx_break"/>University of Oslo',),
            ("School of Physics, University of Oslo",),
            id="line-break",
        ),
        pytest.param(
            ('<sup>1</sup>School of Physics<br class="ltx_break"/><sup>2</sup>University of Oslo',),
            ("School of Physics", "University of Oslo"),
            id="not-across-a-marker",
        ),
        pytest.param(
            ("Department of Physics", "Department of Chemistry", "University of Oslo"),
            ("Department of Physics", "Department of Chemistry, University of Oslo"),
            id="not-another-unit",
        ),
        pytest.param(
            ("Department of Physics", "Corresponding author"),
            ("Department of Physics",),
            id="not-a-note",
        ),
    ],
)
def test_a_unit_takes_the_institution_on_the_next_line(
    contacts: tuple[str, ...], expected: tuple[str, ...]
) -> None:
    html = _author_block(("Ada Lovelace", contacts), ("Bob Smith", ("ETH Zurich",)))

    front = parse_front_matter(html, authors=("Ada Lovelace", "Bob Smith"))

    assert front.affiliations == (*expected, "ETH Zurich")
    assert front.author_affiliations == (tuple(range(len(expected))), (len(expected),))


def test_markers_find_a_unit_joined_to_its_institution() -> None:
    # The second marker's line is one affiliation once joined, written with a comma (2610.02000).
    html = _author_block(
        ("Ada Lovelace<sup>1</sup>, Bob Smith<sup>1,2</sup>", ()),
        contacts=(
            (
                "<sup>1</sup>Department of Physics<br/>"
                "<sup>2</sup>Department of Chemistry<br/>University of Oslo"
            ),
        ),
    )

    front = parse_front_matter(html, authors=("Ada Lovelace", "Bob Smith"))

    assert front.affiliations == ("Department of Physics", "Department of Chemistry, University of Oslo")
    assert front.author_affiliations == ((0,), (0, 1))


@pytest.mark.parametrize(
    ("arxiv_id", "expected"),
    [
        pytest.param(
            "2609.36458",
            ("Department of Computer Science, University of Nebraska Omaha, Omaha, NE, USA",),
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


TABLE_PAGE = """<html><body><article class="ltx_document">
<div class="ltx_authors"><span class="ltx_creator ltx_role_author">
<span class="ltx_personname">Ada Lovelace</span>
<span class="ltx_contact ltx_role_affiliation"><table class="ltx_tabular"><tr>
<td>Trier University of Applied Sciences</td></tr></table></span></span></div>
<div class="ltx_abstract"><p>We do things.</p>
<table class="ltx_tabular"><tr><td>A results table, big.</td></tr></table></div>
</article></body></html>"""


GLOSSARY_PAGE = """<html><body><article class="ltx_document">
<section class="ltx_glossary ltx_acronym ltx_list_acronym"><h6>Acronyms</h6>
<dl><dt>CNN</dt><dd>Convolutional Neural Network</dd></dl></section>
<h1 class="ltx_title ltx_title_document">A paper</h1>
<div class="ltx_authors"><span class="ltx_creator ltx_role_author">
<span class="ltx_personname">Ada Lovelace</span>
<span class="ltx_contact ltx_role_affiliation">University of Augsburg</span></span></div>
<div class="ltx_abstract"><p>We do things.</p></div>
<section class="ltx_section"><h2>Introduction</h2><p>Body text, Stanford University.</p></section>
</article></body></html>"""


def test_the_front_matter_goes_past_a_list_of_acronyms_before_the_title() -> None:
    small = front_matter_html(GLOSSARY_PAGE)

    # 2610.09677: the acronyms ended a front matter that had not begun.
    assert parse_front_matter(small, authors=("Ada Lovelace",)) == parse_front_matter(
        GLOSSARY_PAGE, authors=("Ada Lovelace",)
    )
    assert parse_front_matter(small).affiliations == ("University of Augsburg",)
    assert "Convolutional" not in small
    assert "Introduction" not in small


def test_the_front_matter_keeps_the_tables_of_the_author_block() -> None:
    small = front_matter_html(TABLE_PAGE)

    assert parse_front_matter(small, authors=("Ada Lovelace",)).affiliations == (
        "Trier University of Applied Sciences",
    )
    assert "results table" not in small


def test_a_page_kept_before_the_tables_or_empty_is_stale(tmp_path: Path) -> None:
    cache = PageCache(tmp_path / "pages")
    url = "https://arxiv.org/html/2609.30249v2"

    assert not cache.stale(url)
    cache.put(url, FULL_PAGE)
    assert not cache.stale(url)
    (tmp_path / "pages" / "2609" / "2609.30249v2.html.gz").write_bytes(
        gzip.compress(b'<html><body><article class="ltx_document"></article></body></html>')
    )
    assert cache.stale(url)
    # Kept empty, a list of acronyms ending it before the title (2610.09677).
    (tmp_path / "pages" / "2609" / "2609.30249v2.html.gz").write_bytes(
        gzip.compress(
            b'<html><body><article class="ltx_document" data-front-matter="2">\n</article></body></html>'
        )
    )
    assert cache.stale(url)
    cache.put(url, GLOSSARY_PAGE)
    assert not cache.stale(url)
    # A page without a document is kept whole: it lost nothing.
    cache.put(url, "<p>Maintenance</p>")
    assert not cache.stale(url)


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
    # A page that does not exist is remembered as such.
    assert cache.missing("https://arxiv.org/html/2609.30249v9")
    assert not cache.missing(url)


def test_the_page_cache_remembers_only_pages_that_name_a_version(tmp_path: Path) -> None:
    cache = PageCache(tmp_path / "pages")
    cache.put_missing("https://arxiv.org/html/2609.30249")

    assert not cache.missing("https://arxiv.org/html/2609.30249")
    assert not (tmp_path / "pages").exists()


@pytest.mark.parametrize(
    ("arxiv_id", "url"),
    [
        ("2312.00001", "https://arxiv.org/html/2312.00001v1"),
        ("2509.12345", "https://arxiv.org/html/2509.12345v1"),
        ("2311.99999", None),  # before arXiv rendered any
        ("1512.03385", None),
        ("cs/0112017", None),
    ],
)
def test_first_version_url(arxiv_id: str, url: str | None) -> None:
    assert first_version_url(arxiv_id) == url


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
            ("Dept. of Computer Science, University of Alabama, USA",),
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


def test_lines_led_by_symbols_skip_notes() -> None:
    html = _author_block(
        ("Ada Lovelace<sup>*</sup>", ()),
        ("Bob Smith<sup>\u2020</sup>", ()),
        (
            "<br><sup>*</sup>Equal contribution <sup>*</sup>Stanford University <sup>\u2020</sup>MIT Lab",
            (),
        ),
    )

    front = parse_front_matter(html, authors=("Ada Lovelace", "Bob Smith"))

    assert front.affiliations == ("Stanford University", "MIT Lab")
    assert front.author_affiliations == ((0,), (1,))


def test_lines_led_by_symbols_count_only_when_each_names_an_institution() -> None:
    html = _author_block(
        ("Ada Lovelace<sup>*</sup>", ()),
        ("Bob Smith<sup>\u2020</sup>", ()),
        ("<br><sup>*</sup>Stanford University <sup>\u2020</sup>Now at Google", ()),
    )

    assert parse_front_matter(html, authors=("Ada Lovelace", "Bob Smith")).affiliations == ()


def test_one_line_led_by_a_symbol_is_only_its_authors() -> None:
    html = _author_block(
        ("Ada Lovelace<sup>*</sup>\n", ()), ("Bob Smith\n", ()), ("<sup>*</sup>Stanford University", ())
    )

    front = parse_front_matter(html, authors=("Ada Lovelace", "Bob Smith"))

    assert front.affiliations == ("Stanford University",)
    assert front.author_affiliations == ((0,), None)


def test_symbols_that_follow_their_affiliations_lead_none() -> None:
    # "Independent§University of Waterloo¶" (2505.11293): "§" is Independent's.
    html = _author_block(
        ("Ada Lovelace<sup>\u00a7</sup>\n", ()),
        ("Bob Smith<sup>\u00b6</sup>\n", ()),
        ("Independent<sup>\u00a7</sup>University of Waterloo<sup>\u00b6</sup>", ()),
    )

    assert parse_front_matter(html, authors=("Ada Lovelace", "Bob Smith")).affiliations == ()


def test_unmarked_lines_never_hold_an_author() -> None:
    html = _author_block(
        ("Ada Lovelace  Bob Smith<br>Ada Lovelace, Stanford University<br>MIT Media Lab", ())
    )

    front = parse_front_matter(html, authors=("Ada Lovelace", "Bob Smith"))

    assert front.affiliations == ("MIT Media Lab",)
    # A line left out may hold another affiliation: the one kept is not everyone's.
    assert front.author_affiliations is None


def test_an_unmarked_line_under_the_names_is_an_affiliation(paper_html: PaperHtml) -> None:
    front = parse_front_matter(paper_html("2610.18323"), authors=AUTHORS["2610.18323"])

    assert front.affiliations == ("Xi\u2019an Jiaotong University",)


@pytest.mark.parametrize(
    "pieces",
    [
        pytest.param(
            ("University of Science", "Technology of China", "Beijing", "China"), id="and-and-commas"
        ),
        pytest.param(("Peking University", "Computer Engineering"), id="unit-cut-off"),
    ],
)
def test_an_author_field_cut_at_its_commas_gives_no_pieces(pieces: tuple[str, ...]) -> None:
    # LaTeXML makes a creator of each piece (2411.15633, 2510.11387).
    names = ("Ada Lovelace", "Bob Smith", *pieces)
    html = _author_block(*((f"{name}\n", ()) for name in names))

    assert parse_front_matter(html, authors=("Ada Lovelace", "Bob Smith")).affiliations == ()


def test_creators_that_are_whole_affiliations_are_read() -> None:
    names = ("Ada Lovelace", "Bob Smith", "Stanford University\n(Palo Alto)", "Corresponding author.")
    html = _author_block(*((f"{name}\n", ()) for name in names))

    front = parse_front_matter(html, authors=("Ada Lovelace", "Bob Smith"))

    assert front.affiliations == ("Stanford University",)
    # "(Palo Alto)" was left out, as "(Guangzhou)" under its university (2609.33258): the
    # one affiliation kept is not surely everyone's.
    assert front.author_affiliations is None


def test_the_one_unmarked_line_is_everyones() -> None:
    # "Labussière" holds "lab", which no line of names is an institution for (2610.06596).
    html = _author_block(
        ("Ada Lovelace  Mathieu Labussière<br>Stanford University<br>author@example.org", ())
    )

    front = parse_front_matter(html, authors=("Ada Lovelace", "Mathieu Labussière"))

    assert front.affiliations == ("Stanford University",)
    assert front.author_affiliations == ((0,), (0,))


def test_unmarked_lines_are_no_source_beside_contacts() -> None:
    html = _author_block(("Ada Lovelace<br>Stanford University", ("Equal contribution",)))

    assert parse_front_matter(html, authors=("Ada Lovelace",)).affiliations == ()


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        pytest.param("Ada LovelaceMIT Media Lab", ("MIT Media Lab",), id="glued"),
        pytest.param(
            "Ada Lovelace<sup>1</sup>Stanford University", ("Stanford University",), id="marker-between"
        ),
        pytest.param("Ada Lovelace MIT Media Lab", (), id="a-space-is-no-glue"),
        pytest.param("Ada Lovelacex Media Lab", (), id="lowercase-goes-on-with-the-name"),
        # Names glued to each other are no affiliation (2508.10104).
        pytest.param("Ada LovelaceBob Smith", (), id="names-glued-to-each-other"),
    ],
)
def test_an_affiliation_glued_to_its_author(name: str, expected: tuple[str, ...]) -> None:
    html = _author_block((name, ()), ("Bob Smith", ("Equal contribution",)))

    assert parse_front_matter(html, authors=("Ada Lovelace", "Bob Smith")).affiliations == expected


def test_numbered_lines_set_as_authors_are_affiliations(paper_html: PaperHtml) -> None:
    front = parse_front_matter(paper_html("2610.12978"), authors=AUTHORS["2610.12978"])

    # "¹Sun Yat-sen University" is a contact of the last author; the other numbered lines
    # are creators of their own, beside e-mail addresses set as authors.
    assert front.affiliations == (
        "Sun Yat-sen University",
        "Alibaba Group",
        "The University of Hong Kong",
        "Shanghai Jiao Tong University",
    )


def test_a_marker_before_a_name_keeps_the_person() -> None:
    html = _author_block(
        ("<sup>*</sup>Ada Lovelace", ("Stanford University",)),
        ("Bob Smith", ("MIT Media Lab",)),
        ("<sup>1</sup>Equal contribution", ()),
    )

    front = parse_front_matter(html, authors=("Ada Lovelace", "Bob Smith"))

    assert front.author_affiliations == ((0,), (1,))


def test_markers_written_in_math_are_read_without_their_source() -> None:
    dagger = (
        '<math alttext="\\dagger"><semantics><mo>\u2020</mo>'
        '<annotation encoding="application/x-tex">\\dagger</annotation></semantics></math>'
    )
    html = _author_block(
        (f"Ada Lovelace<sup>1</sup><sup>{dagger}</sup>", ()),
        ("Bob Smith<sup>2</sup>", ()),
        contacts=("<sup>1</sup>Stanford University <sup>2</sup>MIT Media Lab",),
    )

    front = parse_front_matter(html, authors=("Ada Lovelace", "Bob Smith"))

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
