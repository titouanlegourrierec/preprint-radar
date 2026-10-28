import json
import re
from pathlib import Path

import pytest
from tests.conftest import FIXTURES_DIR

from preprint_radar.institutions import (
    ACRONYMS,
    canonical,
    ids_where_named,
    institution_name,
    name_institutions,
    search_key,
)


@pytest.mark.parametrize(
    ("affiliation", "institution"),
    [
        ("Carnegie Mellon University, United States of America", "Carnegie Mellon University"),
        ("School of Computer Science, Peking University", "Peking University"),
        ("Google, Switzerland", "Google"),
        ("Pengcheng Laboratory, China", "Pengcheng Laboratory"),
        (
            (
                "School of Human Settlements and Civil Engineering, "
                "Xi\N{RIGHT SINGLE QUOTATION MARK}an Jiaotong University, "
                "Xi\N{RIGHT SINGLE QUOTATION MARK}an, 710049, China"
            ),
            "Xi\N{RIGHT SINGLE QUOTATION MARK}an Jiaotong University",
        ),
        ("The University of Texas at Austin", "University of Texas at Austin"),
        ("KAIST", "Korea Advanced Institute of Science and Technology"),
        ("Meta", "Meta"),
        ("and", None),
        # Units and addresses alone name no institution.
        ("Department of Computer Science", None),
        ("College of Computer Science and Electronic Engineering", None),
        ("Nagoya 461-8680", None),
        ("Independent Researcher", None),
        ("Independent Researcher, University of Regensburg", "University of Regensburg"),
        ("Independent Author", None),
        ("Independent researchers", None),
        # Leftovers that older data still holds: they must not become institutions.
        ("Correspondence", None),
        ("the", None),
        ("Code", None),
        ("Core Contributors", None),
        ("USA", None),
        ("United Kingdom", None),
        ("Tencent, China", "Tencent"),
        # Companies, however written; a hospital is not its sponsor.
        ("NVIDIA AI Technology Centre, Singapore", "NVIDIA"),
        ("ARC Lab, Tencent IEG", "Tencent"),
        ("Microsoft Research Asia, Shanghai, China", "Microsoft"),
        ("Samsung Medical Center", "Samsung Medical Center"),
        ("Zhiyang Innovation Co., Ltd", "Zhiyang Innovation Co. Ltd"),
        # Acronyms and campuses.
        ("MIT, Boston, USA", "Massachusetts Institute of Technology"),
        ("CASIA", "Chinese Academy of Sciences"),
        # An acronym, then one of its units, is the institution (AFF-36).
        ("KAIST AI", "Korea Advanced Institute of Science and Technology"),
        ("KAIST College of AI, Seoul", "Korea Advanced Institute of Science and Technology"),
        (
            "KAIST (Korea Advanced Institute of Science and Technology)",
            "Korea Advanced Institute of Science and Technology",
        ),
        ("CUHK MMLab", "Chinese University of Hong Kong"),
        ("ETH Zürich", "ETH Zurich"),
        ("UC Berkeley EECS", "University of California, Berkeley"),
        ("HKUST (GZ)", "Hong Kong University of Science and Technology (Guangzhou)"),
        # Not a joint entity, a hospital, a list, nor a word written like an acronym.
        ("MIT-IBM Watson AI Lab", "MIT-IBM Watson AI Lab"),
        ("KAIST & AITRICS", "KAIST & AITRICS"),
        ("TUM Klinikum", "TUM Klinikum"),
        ("CUHK The University of Adelaide HKUST", "CUHK The University of Adelaide HKUST"),
        ("Hit Robot Group", "Hit Robot Group"),
        ("Oxford", "University of Oxford"),
        ("Oxford Instruments", "Oxford Instruments"),
        ("Stanford, CA, USA", "Stanford University"),
        ("Ultromics Ltd, Oxford, UK", "Ultromics Ltd"),
        ("NEC Laboratories America, Princeton, NJ", "NEC Laboratories America"),
        ("UCB", "University of California, Berkeley"),
        ("University of California, Berkeley", "University of California, Berkeley"),
        ("EECS, University of California, Los Angeles, CA", "University of California, Los Angeles"),
        ("Luca Gandolfi and Chiara Plizzari are with Bocconi University", "Bocconi University"),
        # JavaScript's word boundaries, which the rules were written with: ASCII only.
        ("Laboratório de Visão, Brasil", "Laboratório de Visão"),
    ],
)
def test_institution_name(affiliation: str, institution: str | None) -> None:
    assert institution_name(affiliation) == institution


@pytest.mark.parametrize(
    ("name", "common"),
    [
        ("Google DeepMind", "Google DeepMind"),
        ("Tencent (China)", "Tencent"),
        ("Peking University", "Peking University"),
    ],
)
def test_canonical_gives_a_company_its_common_name(name: str, common: str) -> None:
    assert canonical(name) == common


def test_the_registry_comes_first_and_the_rules_name_the_rest() -> None:
    affiliations = ("University of Padova, Italy", "CMU", "Microsoft Research Asia, Beijing", "Ada Lovelace")
    registered = ("University of Padua", None, "Microsoft Research Asia", None)

    assert name_institutions(affiliations, registered, authors=("Ada Lovelace",)) == (
        "University of Padua",
        "Carnegie Mellon University",
        "Microsoft",
        None,
    )


# The site's tests (web/tests/text.test.ts) read the same cases.
FOLD_CASES = json.loads((FIXTURES_DIR / "fold-cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(("name", "key"), [(case["text"], case["key"]) for case in FOLD_CASES])
def test_search_key_is_the_sites(name: str, key: str) -> None:
    assert search_key(name) == key


def test_one_author_whether_spelled_with_sharp_s_or_ss() -> None:
    names = name_institutions(("Matthias Niessner", "TUM"), (None, None), authors=("Matthias Nießner",))

    assert names == (None, "Technical University of Munich")


def test_the_site_knows_the_same_acronyms() -> None:
    source = (Path(__file__).parents[2] / "web" / "src" / "institutions.ts").read_text(encoding="utf-8")
    table = re.search(r"const ACRONYMS[^=]*= \{(.*?)\};", source, re.DOTALL)

    assert table is not None
    pairs = re.findall(r'^\s*("?)([^":]+)\1: (".*"),$', table.group(1), re.MULTILINE)
    assert {key: json.loads(name) for _, key, name in pairs} == ACRONYMS


def test_an_id_stays_only_where_an_institution_is_named() -> None:
    assert ids_where_named(("042nb2s44", "00f54p054"), ("MIT", None)) == ("042nb2s44", None)
    assert ids_where_named(None, ("MIT",)) is None
    assert ids_where_named((), ()) is None
