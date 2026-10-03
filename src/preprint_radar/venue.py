"""Detect the venue a paper was accepted at, from its free-form comments.

Authors write things like "Accepted to ECCV 2026", "BMVC2026", "published in the
Proceedings of the IEEE/CVF Winter Conference on Applications of Computer Vision (WACV),
2026" or "Submitted to NeurIPS 2026" (not an acceptance). This module recognizes the venues
of a table (:data:`VENUES`) and, failing that, an acronym followed by a year in a sentence
that announces an acceptance.

A venue of the table counts unless its clause says the paper was not accepted there
("Submitted to", "Under review at", "Rejected from") or only mentions it ("Comparison with
CVPR 2025 methods", "ranks first on the ECCV 2024 benchmark", "An extension of our ECCV
2024 paper"). Requiring an acceptance cue instead would lose a venue in twenty: "40th
Conference on Neural Information Processing Systems (NeurIPS 2026)", "Findings of EMNLP
2026".
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class Venue:
    """A venue of the table.

    Attributes:
        name: Canonical name, as shown ("CVPR", "SIGGRAPH Asia").
        kind: Conference or journal.
        acronym: Pattern of its acronyms, case-sensitive unless marked ``(?i:...)``.
        full: Pattern of its full names, matched ignoring case, or ``None``.
    """

    name: str
    kind: Literal["conference", "journal"]
    acronym: str
    full: str | None = None


# A full name must not be the start of a longer one: "International Conference on Computer
# Vision" begins VISAPP's "... Theory and Applications", CVIP's "... and Image Processing" and
# a misnamed "... and Pattern Recognition"; "... on Image Processing" begins IPTA's "... Theory,
# Tools and Applications" and IPAS's "..., Applications and Systems". CVPR's name is also a
# book series ("Advances in Computer Vision and Pattern Recognition").
_NAME_ENDS = r"(?!,?\s+(?:and|Theory|Applications|Systems)\b|,\s*Imaging)"

# Ordered so that longer names win ("SIGGRAPH Asia" before "SIGGRAPH").
VENUES: tuple[Venue, ...] = (
    Venue("NeurIPS", "conference", r"(?i:NeurIPS)|NIPS", r"Neural Information Processing Systems"),
    Venue("ICLR", "conference", r"(?i:ICLR)", r"International Conference on Learning Representations"),
    Venue("ICML", "conference", r"(?i:ICML)", r"International Conference on Machine Learning"),
    Venue(
        "CVPR",
        "conference",
        r"(?i:CVPR)W?",
        r"(?<!\bin )(?:Conference on )?Computer Vision and Pattern Recognition",
    ),
    Venue("ICCV", "conference", r"(?i:ICCV)W?", rf"International Conference on Computer Vision{_NAME_ENDS}"),
    Venue("ECCV", "conference", r"(?i:ECCV)W?", rf"European Conference on Computer Vision{_NAME_ENDS}"),
    Venue("WACV", "conference", r"(?i:WACV)", r"Winter Conference on Applications of Computer Vision"),
    Venue("BMVC", "conference", r"(?i:BMVC)", r"British Machine Vision Conference"),
    Venue("ACCV", "conference", r"ACCV", rf"Asian Conference on Computer Vision{_NAME_ENDS}"),
    Venue("3DV", "conference", r"3DV", r"International Conference on 3D Vision"),
    Venue("SIGGRAPH Asia", "conference", r"(?i:SIGGRAPH\s+Asia)"),
    Venue("SIGGRAPH", "conference", r"(?i:SIGGRAPH)"),
    Venue("CHI", "conference", r"CHI", r"CHI\s+Conference\s+on\s+Human\s+Factors\s+in\s+Computing\s+Systems"),
    Venue(
        "ACM MM",
        "conference",
        r"ACM\s?MM",
        r"ACM\s+Multimedia|ACM\s+International\s+Conference\s+on\s+Multimedia",
    ),
    Venue(
        "AAAI",
        "conference",
        r"(?i:AAAI)",
        r"AAAI Conference on Artificial Intelligence|National Conference on Artificial Intelligence",
    ),
    Venue("IJCAI", "conference", r"IJCAI", r"International Joint Conference on Artificial Intelligence"),
    Venue("ACL", "conference", r"ACL", r"Annual Meeting of the Association for Computational Linguistics"),
    Venue("EMNLP", "conference", r"EMNLP", r"Empirical Methods in Natural Language Processing"),
    Venue(
        "NAACL",
        "conference",
        r"NAACL",
        r"North American Chapter of the Association for Computational Linguistics",
    ),
    Venue("CoRL", "conference", r"CoRL", r"Conference on Robot Learning"),
    Venue("ICRA", "conference", r"ICRA", r"International Conference on Robotics and Automation"),
    Venue("IROS", "conference", r"IROS", r"International Conference on Intelligent Robots and Systems"),
    Venue("RSS", "conference", r"(?!)", r"Robotics:\s+Science\s+and\s+Systems"),
    Venue(
        "MICCAI",
        "conference",
        r"(?i:MICCAI)",
        r"Medical Image Computing and Computer[- ]Assisted Intervention",
    ),
    Venue("IPMI", "conference", r"IPMI", r"Information Processing in Medical Imaging"),
    Venue("ISBI", "conference", r"ISBI", r"International Symposium on Biomedical Imaging"),
    Venue("MIDL", "conference", r"MIDL", r"Medical Imaging with Deep Learning"),
    Venue(
        "ICASSP",
        "conference",
        r"ICASSP",
        r"International Conference on Acoustics,? Speech,? and Signal Processing",
    ),
    Venue("ICIP", "conference", r"ICIP", rf"International Conference on Image Processing{_NAME_ENDS}"),
    Venue("ICME", "conference", r"ICME", r"International Conference on Multimedia and Expo"),
    Venue("ICPR", "conference", r"ICPR", rf"International Conference on Pattern Recognition{_NAME_ENDS}"),
    Venue("IGARSS", "conference", r"IGARSS", r"Geoscience and Remote Sensing Symposium"),
    Venue("KDD", "conference", r"KDD", r"Knowledge Discovery and Data Mining"),
    Venue("ECML PKDD", "conference", r"ECML[\s-]?PKDD"),
    Venue(
        "AISTATS",
        "conference",
        r"AISTATS",
        r"International Conference on Artificial Intelligence and Statistics",
    ),
    Venue("TPAMI", "journal", r"T-?PAMI", r"Pattern\s+Analysis\s+and\s+Machine\s+Intelligence"),
    Venue("IJCV", "journal", r"IJCV", r"International\s+Journal\s+of\s+Computer\s+Vision"),
    Venue("TIP", "journal", r"TIP", r"Transactions\s+on\s+Image\s+Processing"),
    Venue("TMI", "journal", r"TMI", r"Transactions\s+on\s+Medical\s+Imaging"),
    Venue("TVCG", "journal", r"TVCG", r"Transactions\s+on\s+Visualization\s+and\s+Computer\s+Graphics"),
    Venue("TMLR", "journal", r"TMLR", r"Transactions\s+on\s+Machine\s+Learning\s+Research"),
    Venue("JMLR", "journal", r"JMLR", r"Journal\s+of\s+Machine\s+Learning\s+Research"),
    Venue("RA-L", "journal", r"RA-?L", r"Robotics\s+and\s+Automation\s+Letters"),
    Venue("MedIA", "journal", r"MedIA", r"Medical\s+Image\s+Analysis"),
)


def _venue_pattern(venue: Venue) -> str:
    return venue.acronym if venue.full is None else f"{venue.acronym}|(?i:{venue.full})"


_KNOWN_RE = re.compile(
    "|".join(f"(?P<v{index}>{_venue_pattern(venue)})" for index, venue in enumerate(VENUES))
)
# A known venue must stand alone: "ACL" in "ACLU" or "ICME" in "ICMEW2" is not a venue.
_BOUNDARY_BEFORE = re.compile(r"[A-Za-z]$")
_BOUNDARY_AFTER = re.compile(r"^[A-Za-z]")

# Acronym followed by a year, for venues outside the list: "IGARSS 2026", "(DICTA 2026)",
# "SAIIT-2026".
_GENERIC_RE = re.compile(r"(?<![\w-])(?P<name>[A-Z][A-Z0-9&]*(?:-[A-Z0-9&]+)*)\)?,?[\s-]?(?P<year>20\d{2})\b")
# Acronyms that come before a year without being venues: places and publishers.
_MIN_ACRONYM_LENGTH = 3
_NOT_VENUES = frozenset(
    {"USA", "UK", "UAE", "NY", "CA", "ACM", "IEEE", "IET", "LNCS", "CEUR", "PMLR", "MDPI"}
)
_ACCEPTANCE_RE = re.compile(
    # "accepted", and its frequent typos ("accpeted").
    r"\bacc?(?:ep|pe)t|\bto appear\b|\bappear(?:s|ed)? (?:in|at)\b|\bpublished\b"
    r"|\bcamera[- ]ready\b|\bproceedings\b|\bpresent(?:ed|ation)\b",
    re.IGNORECASE,
)
# Clauses that say the paper is not, or not yet, at the venue they name.
_NOT_ACCEPTED_RE = re.compile(
    r"\bsubmit|\bsubmission\b|\bunder review\b|\bin review\b|\bprepared for\b"
    r"|\b(?:extended|shorter)(?: \w+)? version\b",
    re.IGNORECASE,
)
# Words that make a venue a mention, in its comma-separated part of the clause: "CVPR 2018,
# Rank 1 in the ... Challenge" is a CVPR paper, "ranked 1st at the CVPR 2021 Challenge" not.
_MENTION_RE = re.compile(
    r"\brejected\b|\bextension of\b|\bcompar|\bversus\b|\bvs\b|\brank(?:s|ed|ing)?\b"
    r"|\bbenchmark\b(?!s? track)",
    re.IGNORECASE,
)
_WORKSHOP_RE = re.compile(r"workshop|\b(?:CVPR|ICCV|ECCV)W\b", re.IGNORECASE)
# Links name venues without announcing anything ("cvpr.thecvf.com", ".../cvpr2024-code").
_URL_RE = re.compile(r"\b(?:https?://|www\.)\S+|\b[\w.-]+\.(?:com|org|io|net)/\S*", re.IGNORECASE)
# Years: "2026", or "'26" as in "SIGGRAPH Asia '26"; never one of a page range
# ("pp.2028-2040").
_YEAR = r"(?:(?<!\d)(?<!\d[-\u2013])(?<!pp\.)(?P<year>20\d{2})(?![-\u2013]\d)|['\u2019](?P<short>\d{2}))\b"
_YEAR_AFTER_RE = re.compile(
    rf"^(?:-?(?P<glued>\d{{2}})\b|[\s)\],:-]{{0,4}}(?:(?:Workshops?|Asia)\s*)?[\s(),-]{{0,4}}{_YEAR})"
)
_YEAR_BEFORE_RE = re.compile(r"\b(?P<year>20\d{2})\s+(?:(?:IEEE|ACM|IEEE/CVF)\s+)?$")
# Glued to an acronym too: "(ICME2020)", "(MICCAI'22)".
_ANY_YEAR_RE = re.compile(rf"(?<![a-z\d]){_YEAR}")
_CLAUSE_SPLIT_RE = re.compile(r"(?<=[.;!?])\s+|\n")


def extract_venue(comments: str | None, journal_ref: str | None = None) -> str | None:
    """Return the venue a paper was accepted at, e.g. ``"ECCV 2026"``.

    Args:
        comments: Author comments from the listing.
        journal_ref: Journal reference, if any.

    Returns:
        The venue, suffixed with ``"Workshop"`` for workshop papers, or ``None`` when no
        acceptance could be recognized.
    """
    clauses = [
        _URL_RE.sub(" ", clause)
        for text in (comments, journal_ref)
        if text
        for clause in _CLAUSE_SPLIT_RE.split(text)
        if clause.strip()
    ]
    accepted = [clause for clause in clauses if not _NOT_ACCEPTED_RE.search(clause)]
    for clause in accepted:
        if venue := _known_venue(clause):
            return venue
    for clause in accepted:
        if not _ACCEPTANCE_RE.search(clause):
            continue
        for match in _GENERIC_RE.finditer(clause):
            if len(match.group("name")) >= _MIN_ACRONYM_LENGTH and match.group("name") not in _NOT_VENUES:
                suffix = " Workshop" if _WORKSHOP_RE.search(clause) else ""
                return f"{match.group('name')} {match.group('year')}{suffix}"
    return None


def _known_venue(clause: str) -> str | None:
    """First venue of the table named in the clause, with its year when one is given."""
    for match in _KNOWN_RE.finditer(clause):
        before, after = clause[: match.start()], clause[match.end() :]
        if _BOUNDARY_BEFORE.search(before) or _BOUNDARY_AFTER.search(after.removeprefix("W")):
            continue
        start, end = clause.rfind(",", 0, match.start()) + 1, clause.find(",", match.end())
        if _MENTION_RE.search(clause[start : end if end != -1 else None]):
            continue
        name = next(VENUES[int(group[1:])].name for group, value in match.groupdict().items() if value)
        # Next to the name ("ECCV 2026", "2026 ECCV"), else anywhere in the clause
        # ("Proceedings of the ... (WACV), 2026").
        year = _year(before, after, clause)
        suffix = " Workshop" if _WORKSHOP_RE.search(clause) else ""
        return f"{name}{year}{suffix}"
    return None


def _year(before: str, after: str, clause: str) -> str:
    """Year next to the venue name ("ECCV 2026", "2026 ECCV", "CVPR15", "ECCV-18"), else in the clause."""
    match = _YEAR_AFTER_RE.search(after) or _YEAR_BEFORE_RE.search(before) or _ANY_YEAR_RE.search(clause)
    if match is None:
        return ""
    groups = {key: value for key, value in match.groupdict().items() if value}
    if "year" in groups:
        return f" {groups['year']}"
    return f" 20{groups.get('short') or groups['glued']}"


# Semantic Scholar names preprint servers as venues: they are not publications.
_PREPRINT_SERVER_RE = re.compile(r"arxiv|biorxiv|medrxiv|\bssrn\b|research square|techrxiv", re.IGNORECASE)
_FULL_NAME_RES = tuple(re.compile(f"(?i:{venue.full})") if venue.full else None for venue in VENUES)
# "ECCV Workshops", "... Workshops (CVPRW)"; not WACV's "IEEE Workshop/Winter Conference".
_PUBLISHED_WORKSHOP_RE = re.compile(r"\bWorkshops?\b(?!/)|\([A-Z]+W\)")
_PUBLISHED_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_PRINT_EDITION_RE = re.compile(r"\s*\((?:Print|Online)\)\s*$", re.IGNORECASE)


def published_venue(
    name: str | None,
    alternate_names: Sequence[str] = (),
    venue: str | None = None,
    year: int | None = None,
) -> str | None:
    """Where Semantic Scholar says a paper was published, named as :data:`VENUES` names it.

    A venue of the table is recognized by one of its full names in ``name`` or ``venue``
    ("Computer Vision and Pattern Recognition", "2018 IEEE/CVF Conference on Computer
    Vision and Pattern Recognition"), by its acronym in them ("ECCV Workshops"), or, for a
    venue the table knows by acronym only, by an alternate name that is that acronym
    ("SIGGRAPH Asia"): the alternate names of another venue can share an acronym ("ICIP"
    is also the International Conference on Information Photonics). Other venues keep Semantic
    Scholar's name of the venue, never its bare ``venue`` string, which can be an
    abbreviation ("Medical Image Anal.").

    Args:
        name: The name of its ``publicationVenue``.
        alternate_names: That venue's other names ("CVPR", "Comput Vis Pattern Recognit").
        venue: Its ``venue`` string.
        year: The year of publication, used when no name holds one.

    Returns:
        "CVPR 2018", "ECCV 2020 Workshop", "Information Fusion 2024", or ``None`` for a
        preprint server or no venue.
    """
    names = [text.strip() for text in (name, venue) if text and text.strip()]
    if not names or _PREPRINT_SERVER_RE.search(names[0]):
        return None
    known = _table_venue(names, alternate_names)
    if known is not None:
        label = known.name
    elif name and name.strip():
        label = _PRINT_EDITION_RE.sub("", name.strip())
    else:
        return None
    found = next((match.group() for text in names if (match := _PUBLISHED_YEAR_RE.search(text))), None)
    when = found or (str(year) if year else None)
    workshop = "Workshop" if any(_PUBLISHED_WORKSHOP_RE.search(text) for text in names) else None
    return " ".join(part for part in (label, when, workshop) if part)


def _table_venue(names: Sequence[str], alternate_names: Sequence[str]) -> Venue | None:
    """The venue of the table named in full in ``names``, else by an acronym.

    An acronym counts in the names ("ECCV Workshops", "NeurIPS Datasets and Benchmarks"),
    but among the venue's alternate names only for a venue the table knows by acronym only.
    """
    for venue, full in zip(VENUES, _FULL_NAME_RES, strict=True):
        if full is not None and any(full.search(text) for text in names):
            return venue
    for venue in VENUES:
        acronym = re.compile(rf"(?<![A-Za-z])(?:{venue.acronym})(?![A-Za-z])")
        if any(acronym.search(text) for text in names) or (
            venue.full is None and any(re.fullmatch(venue.acronym, text.strip()) for text in alternate_names)
        ):
            return venue
    return None
