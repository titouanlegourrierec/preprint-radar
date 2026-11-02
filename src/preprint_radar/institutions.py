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
from collections.abc import Iterable, Mapping, Sequence

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
# What a part without any institution word names when it is no institution (AQ-4): a street
# before its city ("Kifer Rd, Sunnyvale", "Kexueyuan Nanlu, Haidian Qu"; "Afari Intelligent
# Drive" alone is a company), a city of one or two words before its state or province
# ("Pittsburgh, PA 15213", "Kingston, ON"; not DE, Germany as often as Delaware), a note or
# a link's label leading the string ("Equal supervision", "Project webpage"), a mailbox name
# ("jane.doe"; not a domain, "valeo.ai" a lab). A city alone ("Seoul, Korea") is left:
# nothing tells it from an institution ("IIT Delhi").
_STREET_RE = re.compile(
    r"\b(?:st|street|ave|avenue|rd|road|blvd|boulevard|dr|drive|hwy|highway|lane|ln|nanlu|beilu|lu)\.?$",
    re.IGNORECASE,
)
_STATES = (
    "AL|AK|AZ|AR|CA|CO|CT|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH"
    "|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC|AB|BC|MB|NB|NL|NS|ON|PE|QC|SK"
)
_STATE_RE = re.compile(rf"^(?:{_STATES})(?:\s+\d{{5}}(?:-\d{{4}})?)?$")
_CITY_WORDS = 2
_NOTE_RE = re.compile(
    r"^(?:project|code|demo|equal|lead\s+author|project\s+advisors?|web\s*page|home\s*page)\b", re.IGNORECASE
)
_MAILBOX_RE = re.compile(
    r"^[a-z0-9]+(?:[._][a-z0-9]+)*[._](?!(?:ai|com|io|net|org|media|gr|cn|edu)$)[a-z0-9]+$"
)
# A person's name: two or three capitalized words.
_PERSON_RE = re.compile(r"^[A-Z][\w'\u2019-]*\.?(?:\s+[A-Z][\w'\u2019-]*\.?){1,2}$")
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
    "hkust gz": "Hong Kong University of Science and Technology (Guangzhou)",
    "hkust guangzhou": "Hong Kong University of Science and Technology (Guangzhou)",
    "hku": "University of Hong Kong",
    "nus": "National University of Singapore",
    "ucla": "University of California, Los Angeles",
    "ucsd": "University of California San Diego",
    "ucl": "University College London",
    "uc san diego": "University of California San Diego",
    "uc berkeley": "University of California, Berkeley",
    "ucb": "University of California, Berkeley",
    # Names written alone, as acronyms are ("¹ NVIDIA ² MIT ³ UCB ⁴ Oxford", 2610.19495); of
    # places too (`_PLACE_NAMES`).
    "oxford": "University of Oxford",
    "stanford": "Stanford University",
    "harvard": "Harvard University",
    "princeton": "Princeton University",
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
# A part led by a known acronym, then one of its units: "KAIST AI", "KAIST College of AI",
# "CUHK MMLab", "TUM School of Computation" are the institution (AFF-36), as "KAIST" alone.
_ACRONYM_LED_RE = re.compile(
    r"^(?P<acronym>"
    + "|".join(r"\s+".join(map(re.escape, key.split())) for key in sorted(ACRONYMS, key=len, reverse=True))
    + r")\s+(?P<rest>\S.*)$",
    re.IGNORECASE,
)
# What follows the acronym in a part that is not its unit: a joint entity ("KAIST & AITRICS";
# "MIT-IBM Watson AI Lab" has no space), another campus ("HKUST (GZ)", an acronym of its
# own), a hospital ("TUM Klinikum"), or a list naming another university ("CUHK The
# University of Adelaide HKUST").
_NOT_ITS_UNIT_RE = re.compile(r"&|^\(|universit|hospital|klinik|clinic|health|medical", re.IGNORECASE)
# Names of places as well as of their universities: their university only when no other part
# names an institution ("Stanford, CA"), not in "Ultromics Ltd, Oxford, UK".
_PLACE_NAMES = frozenset({"oxford", "stanford", "princeton"})
# The acronym written as one, with two capitals at least: "Hit Robot Group" is no Harbin
# Institute of Technology, "Oxford Instruments" no University of Oxford ("Oxford" alone is).
_ACRONYM_CAPITALS = 2
# Campuses of the University of California, written as a part of their own.
_UC_CAMPUS_RE = re.compile(
    r"^(?:berkeley|los angeles|san diego|davis|irvine|santa barbara|santa cruz|riverside|merced"
    r"|san francisco)$",
    re.IGNORECASE,
)
_UNIVERSITY_OF_CALIFORNIA_RE = re.compile(r"^university of california$", re.IGNORECASE)
_KEY_SEPARATOR_RE = re.compile(r"[\W_]+")


# Letters that do not decompose into a base letter and an accent, written as plain letters
# wherever names are compared (AFF-24); the site's ``fold`` (``web/src/text.ts``) has the same.
PLAIN_LETTERS = str.maketrans({
    "\N{LATIN SMALL LETTER DOTLESS I}": "i",
    "\N{LATIN SMALL LETTER L WITH STROKE}": "l",
    "\N{LATIN SMALL LETTER O WITH STROKE}": "o",
    "\N{LATIN SMALL LETTER D WITH STROKE}": "d",
    "\N{LATIN SMALL LETTER SHARP S}": "ss",
    "\N{LATIN SMALL LETTER AE}": "ae",
})  # fmt: skip


def search_key(text: str) -> str:
    """A name as the site compares names: accents and case gone, punctuation one space.

    The site's ``searchKey`` (``web/src/text.ts``), which keys graph nodes: "Universität
    Zürich" and "universitat zurich" are one institution. The letters of ``PLAIN_LETTERS``
    are written plainly, so that "Nießner" and "Niessner", or "Bartłomiej" and "Bartlomiej",
    are one author (AFF-24); the cases in ``tests/fixtures/fold-cases.json`` give the same
    key in both languages.

    Args:
        text: A name.

    Returns:
        Its key.
    """
    decomposed = unicodedata.normalize("NFD", text)
    lowered = "".join(char for char in decomposed if not unicodedata.combining(char)).lower()
    # Not ``casefold``, which also rewrites what JavaScript's ``toLowerCase`` leaves (ligatures,
    # final sigma); the plain letters last, since capitals lowercase to them (ẞ to ß).
    folded = lowered.translate(PLAIN_LETTERS)
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
    independent = any(_INDEPENDENT_RE.match(part) for part in parts)
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
        key = search_key(part)
        if key not in _PLACE_NAMES and (alias := ACRONYMS.get(key) or _led_by_acronym(part)):
            return alias
        if (score := _score(part)) > best_score:
            best, best_index, best_score = part, index, score
    if search_key(best) in _PLACE_NAMES:
        return ACRONYMS[search_key(best)]
    if best_score < 3:  # noqa: PLR2004 - a university-like part outranks a company mentioned
        for pattern, brand in _BRANDS:
            if any(pattern.search(part) and not _NOT_A_BRAND_RE.search(part) for part in parts):
                return brand
    campus = parts[best_index + 1] if best_index + 1 < len(parts) else None
    if _names_nothing(affiliation, best, best_score, campus, independent=independent):
        return None
    if _UNIVERSITY_OF_CALIFORNIA_RE.match(best) and campus is not None and _UC_CAMPUS_RE.match(campus):
        return f"{best}, {campus}"
    return best


def _names_nothing(
    affiliation: str, best: str, score: float, after: str | None, *, independent: bool
) -> bool:
    """Whether the best part of a string names no institution.

    A unit or an address alone; an independent researcher's town ("Independent,
    Jerusalem"); and, when it has no institution word, a street, a city before its state, a
    note or a list of mailbox names (AQ-4).
    """
    if score <= 0.5 or (independent and score < 2 and not best.isupper()):  # noqa: PLR2004 - a unit, an address, a town
        return True
    return score == 1 and (
        (_STREET_RE.search(best) is not None and after is not None)
        or (len(best.split()) <= _CITY_WORDS and after is not None and _STATE_RE.match(after) is not None)
        or _NOTE_RE.match(affiliation.strip()) is not None
        or _MAILBOX_RE.match(best) is not None
    )


def _led_by_acronym(part: str) -> str | None:
    """The institution a part led by its acronym names, then one of its units ("KAIST AI")."""
    match = _ACRONYM_LED_RE.match(part)
    if match is None:
        return None
    institution = ACRONYMS[search_key(match["acronym"])]
    if sum(char.isupper() for char in match["acronym"]) < _ACRONYM_CAPITALS:
        return None
    # The acronym spelled out after it: "KAIST (Korea Advanced Institute of Science and Technology)".
    if search_key(match["rest"]) == search_key(institution):
        return institution
    return None if _NOT_ITS_UNIT_RE.search(match["rest"]) else institution


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


# Institutions the registry names as a better-known one, by their ROR id: the name they get
# instead, and the words by which an affiliation without an id says it is theirs (AQ-7).
# The site counts institutions by name: "Northeastern University" in Shenyang and in Boston
# were one node and one row. The better-known keeps the plain name, as Wikipedia does.
HOMONYMS: Mapping[str, tuple[str, str]] = {
    "03awzbc87": ("Northeastern University (China)", r"China|Shenyang"),
    "00cf0ab87": ("Southeast University (Bangladesh)", r"Bangladesh|Dhaka"),
    "056qj1t15": ("Institute of Automation (Dresden)", r"Germany|Dresden"),
    "00m6w7z96": ("Northwestern University (Philippines)", r"Philippines|Laoag"),
    "04dwckp88": ("Concordia University (Portland)", r"Portland|Oregon"),
    "00y7snj24": ("Northwest University (Kirkland)", r"Kirkland|Washington|USA|United States"),
    "03xg85719": ("Institute for Advanced Study (Berlin)", r"Berlin|Germany"),
    "040r3xq19": ("Universidad de León (Mexico)", r"M[eé]xico|Guanajuato"),
}
_HOMONYM_SUFFIX_RE = re.compile(r"\s+\([^()]+\)$")
# Each plain name's homonyms, and the words that tell an affiliation is theirs.
_HOMONYM_WORDS: dict[str, list[tuple[str, re.Pattern[str]]]] = {}
for _told, _words in HOMONYMS.values():
    _HOMONYM_WORDS.setdefault(_HOMONYM_SUFFIX_RE.sub("", _told), []).append(
        (_told, re.compile(rf"{_B}(?:{_words}){_B}"))
    )


def told_apart(name: str, ror_id: str | None, affiliation: str) -> str:
    """The name of an institution that shares it with another, made its own (:data:`HOMONYMS`).

    By its id; without one, by the words of its affiliation ("Northeastern University,
    Shenyang, China"); else the name, the better-known one's.

    Args:
        name: The institution's name, as the registry or the rules give it.
        ror_id: Its ROR id, ``None`` when not known.
        affiliation: The affiliation string it was named for.

    Returns:
        The name, made unique where it is a homonym's.
    """
    if ror_id is not None:
        return HOMONYMS[ror_id][0] if ror_id in HOMONYMS else name
    for told, words in _HOMONYM_WORDS.get(name, ()):
        if words.search(affiliation):
            return told
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


def unique_ids(named: Iterable[tuple[str | None, str | None]]) -> dict[str, str]:
    """The ROR id of each institution name written with exactly one (AQ-6).

    A name written with two ids is two institutions ("Northeastern University", in China and
    the United States), which no id may stand for.

    Args:
        named: Institution names, each with its ROR id where one was given.

    Returns:
        Each name's id, for the names of a single id.
    """
    ids: dict[str, set[str]] = {}
    for name, ror_id in named:
        if name and ror_id:
            ids.setdefault(name, set()).add(ror_id)
    return {name: next(iter(found)) for name, found in ids.items() if len(found) == 1}


def with_known_ids(
    names: Sequence[str | None], ids: Sequence[str | None] | None, known: Mapping[str, str]
) -> tuple[str | None, ...] | None:
    """The ids of the institutions named, those the rules named given the id their name has elsewhere.

    The map and the country filter count institutions by their ROR id: "University of Hong
    Kong", named by the rules 176 times without one, was missing from them (AQ-6).

    Args:
        names: The institutions named.
        ids: Their ids, ``None`` when not known.
        known: The id of each name written with a single one (:func:`unique_ids`).

    Returns:
        The ids, or ``None`` when none is known.
    """
    filled = tuple(
        ror_id or (known.get(name) if name else None)
        for name, ror_id in zip(names, ids or (None,) * len(names), strict=True)
    )
    return filled if any(filled) else None


def name_institutions(
    affiliations: Sequence[str],
    registered: Sequence[str | None],
    authors: Sequence[str] = (),
    ids: Sequence[str | None] | None = None,
) -> tuple[str | None, ...]:
    """The institution of each affiliation: the registry's, else the rules'.

    One of the paper's own authors is never an institution (a name printed where an
    affiliation goes), and an institution named as a better-known one is told apart
    (:func:`told_apart`, AQ-7).

    Args:
        affiliations: A paper's affiliations.
        registered: The name ROR or OpenAlex gives each, ``None`` where it gives none.
        authors: The paper's authors.
        ids: The ROR id the registry gives each, ``None`` where it gives none.

    Returns:
        One name or ``None`` per affiliation.
    """
    people = {search_key(author) for author in authors}
    surnames = {key.split()[-1] for key in people if key}
    names = (
        None
        if _lists_authors(affiliation, surnames)
        else canonical(name)
        if name
        else institution_name(affiliation)
        for affiliation, name in zip(affiliations, registered, strict=True)
    )
    return tuple(
        told_apart(name, ror_id, affiliation) if name and search_key(name) not in people | {""} else None
        for name, ror_id, affiliation in zip(
            names, ids or (None,) * len(affiliations), affiliations, strict=True
        )
    )


def _lists_authors(affiliation: str, surnames: set[str]) -> bool:
    """Whether a string is a list of the paper's authors, spelled their own way (AQ-4).

    "Kate Tolstaya, Sarah Tang, ..." for "Ekaterina Tolstaya": two parts at least, each a
    person's name, two of them ending with an author's surname.
    """
    parts = [part.strip() for part in _SEPARATOR_RE.split(affiliation) if part.strip()]
    if len(parts) < 2 or not all(_PERSON_RE.match(part) or part.split()[-1:] == [part] for part in parts):  # noqa: PLR2004
        return False
    return sum(search_key(part).split()[-1:][0] in surnames for part in parts if search_key(part)) >= 2  # noqa: PLR2004
