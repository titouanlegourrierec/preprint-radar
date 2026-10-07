"""The institution each affiliation names, as the site counts them (AFF-13, decision 12).

ROR names most affiliations (``sources/ror.py``); these rules name the rest, and give a
company one name however its subsidiaries are registered ("Google (United States)" and
"Google, Switzerland" are "Google"). The site used to apply them itself, in TypeScript,
while the pipeline asked ROR in Python: they live here now, and the site only displays
what the store says. ``web/src/institutions.ts`` keeps the acronyms, for its search, and a
test keeps both tables equal.

The rules are heuristic: an affiliation is split at commas, and its most institution-like
part is kept ("School of Computer Science, Peking University" names Peking University),
unless a company or an acronym is written anywhere in it.
"""

import re
import unicodedata
from collections.abc import Sequence

from preprint_radar.sources.arxiv_html import COUNTRIES

# JavaScript's \b, which the rules were written with: ASCII word characters only, so that
# "Laboratório" has no "lab" word.
_WORD = r"[A-Za-z0-9_]"
_B = rf"(?:(?<={_WORD})(?!{_WORD})|(?<!{_WORD})(?={_WORD}))"

# Words that identify the institution itself, as opposed to one of its departments or its
# address. Scores: 3 university-like, 2 organization, 1 anything else, 0.5 a unit of some
# institution, 0.25 an address.
_UNIVERSITY_RE = re.compile(
    r"universit|université|universität|universidad|università|polytechn|politecnico|college|academy"
    rf"|école|ecole|{_B}(?:eth|epfl|kaist|mit|inria|cnrs|riken|max planck){_B}",
    re.IGNORECASE,
)
_ORGANIZATION_RE = re.compile(
    rf"{_B}(?:inc|ltd|llc|gmbh|corp|corporation|company|labs?|laborator(?:y|ies)|research|institute"
    r"|institut|centre|center|hospital|foundation|google|deepmind|meta|microsoft|nvidia|amazon|apple"
    rf"|adobe|tencent|alibaba|bytedance|baidu|huawei|samsung|sony|intel|openai|ibm|qualcomm){_B}",
    re.IGNORECASE,
)
_UNIT_RE = re.compile(
    r"^(?:the\s+)?(?:dept\.?|department|school|faculty|division|chair|group|graduate school|college of"
    rf"|laboratory of|key laboratory|state key laboratory){_B}",
    re.IGNORECASE,
)
# "Zhiyang Innovation Co., Ltd.": the legal suffix belongs to the name before it.
_LEGAL_SUFFIX_RE = re.compile(rf",\s*(ltd|inc|llc|gmbh|co|corp|ag|plc|s\.a|s\.r\.l){_B}", re.IGNORECASE)
# "A and B are with the University of X": only the institution matters.
_ARE_WITH_RE = re.compile(rf"^.*?{_B}(?:is|are)\s+(?:also\s+)?(?:with|at)\s+", re.IGNORECASE)
# Not an institution at all: people who work on their own.
_INDEPENDENT_RE = re.compile(
    r"^(?:an?\s+)?(?:independent|individual)(?:\s+(?:researcher|scholar|scientist|author)s?)?$", re.IGNORECASE
)
# Not an affiliation either, in data extracted before the pipeline rejected them:
# link labels, contribution notes, lone words, a country.
_JUNK_RE = re.compile(
    r"^(?:the|an?|dot|code|github|data(?:set)?|demo|video|website|homepage|graduate|correspondence"
    r"|project\s+(?:page|website)|(?:core\s+|main\s+)?contributors?|(?:co-?)?(?:first|second|last|senior)"
    r"\s+authors?)$",
    re.IGNORECASE,
)
_COUNTRY_RE = re.compile(rf"^(?:{COUNTRIES})\.?$", re.IGNORECASE)
# Two letters in a row: what a part of an affiliation needs to name anything.
_LETTERS_RE = re.compile(r"[^\W\d_]{2}")
_DIGIT_RE = re.compile(r"\d")
_LEADING_THE_RE = re.compile(r"^the\s+", re.IGNORECASE)
_AND_RE = re.compile(r"^and$", re.IGNORECASE)
_SEPARATOR_RE = re.compile(r"[,;]")

# Companies are written many ways ("NVIDIA AI Technology Centre", "Microsoft Research Asia",
# "ARC Lab, Tencent IEG"): any mention names the company, the first that matches. Hospitals
# named after a company ("Samsung Medical Center") are not the company.
BRANDS: tuple[tuple[str, str], ...] = (
    (r"deepmind", "Google DeepMind"),
    (r"google", "Google"),
    (r"nvidia", "NVIDIA"),
    (r"(?:meta|facebook)", "Meta"),
    (r"microsoft", "Microsoft"),
    (r"tencent", "Tencent"),
    (r"adobe", "Adobe"),
    (r"huawei", "Huawei"),
    (r"(?:alibaba|damo academy)", "Alibaba Group"),
    (r"bytedance", "ByteDance"),
    (r"baidu", "Baidu"),
    (r"samsung", "Samsung"),
    (r"sony", "Sony"),
    (r"amazon", "Amazon"),
    (r"apple", "Apple"),
    (r"intel", "Intel"),
    (r"qualcomm", "Qualcomm"),
    (r"ibm", "IBM"),
    (r"openai", "OpenAI"),
    (r"xiaomi", "Xiaomi"),
    (r"kuaishou", "Kuaishou"),
    (r"sensetime", "SenseTime"),
)
_BRANDS = tuple((re.compile(rf"{_B}{pattern}{_B}", re.IGNORECASE), brand) for pattern, brand in BRANDS)
_NOT_A_BRAND_RE = re.compile(r"hospital|medical|clinic", re.IGNORECASE)
# Acronyms written alone, mapped to the names ROR gives, so that they share a node with the
# full names it resolves. Keys are search keys; ambiguous ones (NTU: Nanyang or National
# Taiwan) are left out. The site searches them too: `web/src/institutions.ts` has a copy.
ACRONYMS: dict[str, str] = {
    "mit": "Massachusetts Institute of Technology",
    "cmu": "Carnegie Mellon University",
    "kaist": "Korea Advanced Institute of Science and Technology",
    "kaust": "King Abdullah University of Science and Technology",
    "hust": "Huazhong University of Science and Technology",
    "ustc": "University of Science and Technology of China",
    "sjtu": "Shanghai Jiao Tong University",
    "zju": "Zhejiang University",
    "pku": "Peking University",
    "thu": "Tsinghua University",
    "cuhk": "Chinese University of Hong Kong",
    "cuhksz": "Chinese University of Hong Kong, Shenzhen",
    "cuhk sz": "Chinese University of Hong Kong, Shenzhen",
    "cuhk shenzhen": "Chinese University of Hong Kong, Shenzhen",
    "hkust": "Hong Kong University of Science and Technology",
    "hku": "University of Hong Kong",
    "nus": "National University of Singapore",
    "ucla": "University of California, Los Angeles",
    "ucsd": "University of California, San Diego",
    "ucl": "University College London",
    "uc san diego": "University of California, San Diego",
    "uc berkeley": "University of California, Berkeley",
    "uiuc": "University of Illinois Urbana-Champaign",
    "epfl": "École Polytechnique Fédérale de Lausanne",
    "tum": "Technical University of Munich",
    "eth": "ETH Zurich",
    "ethz": "ETH Zurich",
    "ucas": "University of Chinese Academy of Sciences",
    "bupt": "Beijing University of Posts and Telecommunications",
    "sustech": "Southern University of Science and Technology",
    "uestc": "University of Electronic Science and Technology of China",
    "xjtu": "Xi'an Jiaotong University",
    "nju": "Nanjing University",
    "hit": "Harbin Institute of Technology",
    "bit": "Beijing Institute of Technology",
    "georgia tech": "Georgia Institute of Technology",
    "caltech": "California Institute of Technology",
    "casia": "Chinese Academy of Sciences",
}
# Campuses of the University of California, written as a part of their own.
_UC_CAMPUS_RE = re.compile(
    r"^(?:berkeley|los angeles|san diego|davis|irvine|santa barbara|santa cruz|riverside|merced"
    r"|san francisco)$",
    re.IGNORECASE,
)
_UNIVERSITY_OF_CALIFORNIA_RE = re.compile(r"^university of california$", re.IGNORECASE)
_KEY_SEPARATOR_RE = re.compile(r"[\W_]+")


def search_key(text: str) -> str:
    """A name as the site compares names: accents and case gone, punctuation one space.

    The site's ``searchKey`` (``web/src/text.ts``), which keys graph nodes: "Universität
    Zürich" and "universitat zurich" are one institution. Unlike ``arxiv_html``'s fold, "ß"
    stays.

    Args:
        text: A name.

    Returns:
        Its key.
    """
    decomposed = unicodedata.normalize("NFD", text)
    folded = "".join(char for char in decomposed if not unicodedata.combining(char)).lower()
    return _KEY_SEPARATOR_RE.sub(" ", folded).strip()


def institution_name(affiliation: str) -> str | None:
    """The institution an affiliation string names, by the rules alone.

    "Google, Switzerland" and "Google" both give "Google", "School of Computer Science,
    Peking University" gives "Peking University", "CMU" gives "Carnegie Mellon
    University". A unit on its own, an address or an independent researcher names none.

    Args:
        affiliation: A stored affiliation string.

    Returns:
        The institution, or ``None``.
    """
    text = _ARE_WITH_RE.sub("", _LEGAL_SUFFIX_RE.sub(r" \1", affiliation), count=1)
    parts = [_LEADING_THE_RE.sub("", part.strip()) for part in _SEPARATOR_RE.split(text)]
    parts = [
        part
        for part in parts
        if _LETTERS_RE.search(part)
        and not _AND_RE.match(part)
        and not _INDEPENDENT_RE.match(part)
        and not _JUNK_RE.match(part)
        and not _COUNTRY_RE.match(part)
    ]
    best, best_index, best_score = "", -1, -1.0
    for index, part in enumerate(parts):
        if alias := ACRONYMS.get(search_key(part)):
            return alias
        if (score := _score(part)) > best_score:
            best, best_index, best_score = part, index, score
    if best_score < 3:  # noqa: PLR2004 - a university-like part outranks a company mentioned
        for pattern, brand in _BRANDS:
            if any(pattern.search(part) and not _NOT_A_BRAND_RE.search(part) for part in parts):
                return brand
    if best_score <= 0.5:  # noqa: PLR2004 - a unit or an address alone names nothing
        return None
    campus = parts[best_index + 1] if best_index + 1 < len(parts) else None
    if _UNIVERSITY_OF_CALIFORNIA_RE.match(best) and campus is not None and _UC_CAMPUS_RE.match(campus):
        return f"{best}, {campus}"
    return best


def _score(part: str) -> float:
    if _UNIT_RE.match(part):
        return 0.5
    if _UNIVERSITY_RE.search(part):
        return 3
    # Postcodes and street numbers: an address, unless nothing better is written.
    if _DIGIT_RE.search(part):
        return 0.25
    if _ORGANIZATION_RE.search(part):
        return 2
    return 1


def canonical(name: str) -> str:
    """The name to give an institution a registry names: a company's common name.

    ROR registers subsidiaries apart ("Tencent (China)", "Microsoft Research Asia"); they
    are the company here, as the rules name it.

    Args:
        name: A name from ROR or OpenAlex.

    Returns:
        The company's name, or ``name``.
    """
    for pattern, brand in _BRANDS:
        if pattern.search(name) and not _NOT_A_BRAND_RE.search(name):
            return brand
    return name


def ids_where_named(
    ids: Sequence[str | None] | None, names: Sequence[str | None]
) -> tuple[str | None, ...] | None:
    """The registry ids of the institutions named, ``None`` where the rules name none.

    Args:
        ids: The ROR id of each affiliation's institution, ``None`` when not known.
        names: The institutions named for them now.

    Returns:
        The ids kept, or ``None`` without ids.
    """
    if not ids:
        return None
    return tuple(ror_id if name else None for ror_id, name in zip(ids, names, strict=True))


def name_institutions(
    affiliations: Sequence[str], registered: Sequence[str | None], authors: Sequence[str] = ()
) -> tuple[str | None, ...]:
    """The institution of each affiliation: the registry's, else the rules'.

    One of the paper's own authors is never an institution (a name printed where an
    affiliation goes).

    Args:
        affiliations: A paper's affiliations.
        registered: The name ROR or OpenAlex gives each, ``None`` where it gives none.
        authors: The paper's authors.

    Returns:
        One name or ``None`` per affiliation.
    """
    people = {search_key(author) for author in authors}
    names = (
        canonical(name) if name else institution_name(affiliation)
        for affiliation, name in zip(affiliations, registered, strict=True)
    )
    return tuple(name if name and search_key(name) not in people | {""} else None for name in names)
