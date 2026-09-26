"""Detect the venue a paper was accepted at, from its free-form comments.

Authors write things like "Accepted to ECCV 2026", "BMVC2026", "published in the
Proceedings of the IEEE/CVF Winter Conference on Applications of Computer Vision (WACV),
2026" or "Submitted to NeurIPS 2026" (not an acceptance). This module recognizes a list of
well-known venues and, failing that, an acronym followed by a year in a sentence that
announces an acceptance.
"""

import re

# Canonical name -> pattern (matched case-sensitively unless marked otherwise), ordered so
# that longer names win ("SIGGRAPH Asia" before "SIGGRAPH").
_KNOWN_VENUES: tuple[tuple[str, str], ...] = (
    ("NeurIPS", r"NeurIPS|NIPS|(?i:Neural Information Processing Systems)"),
    ("ICLR", r"ICLR|(?i:International Conference on Learning Representations)"),
    ("ICML", r"ICML|(?i:International Conference on Machine Learning)"),
    ("CVPR", r"CVPRW?|(?i:Conference on Computer Vision and Pattern Recognition)"),
    ("ICCV", r"ICCVW?|(?i:International Conference on Computer Vision)"),
    ("ECCV", r"ECCVW?|(?i:European Conference on Computer Vision)"),
    ("WACV", r"WACV|(?i:Winter Conference on Applications of Computer Vision)"),
    ("BMVC", r"BMVC|(?i:British Machine Vision Conference)"),
    ("ACCV", r"ACCV|(?i:Asian Conference on Computer Vision)"),
    ("3DV", r"3DV|(?i:International Conference on 3D Vision)"),
    ("SIGGRAPH Asia", r"(?i:SIGGRAPH\s+Asia)"),
    ("SIGGRAPH", r"SIGGRAPH"),
    ("CHI", r"CHI|(?i:CHI\s+Conference\s+on\s+Human\s+Factors\s+in\s+Computing\s+Systems)"),
    ("ACM MM", r"ACM\s?MM|(?i:ACM\s+Multimedia|ACM\s+International\s+Conference\s+on\s+Multimedia)"),
    ("AAAI", r"AAAI"),
    ("IJCAI", r"IJCAI"),
    ("ACL", r"ACL"),
    ("EMNLP", r"EMNLP"),
    ("NAACL", r"NAACL"),
    ("CoRL", r"CoRL|(?i:Conference on Robot Learning)"),
    ("ICRA", r"ICRA"),
    ("IROS", r"IROS"),
    ("RSS", r"(?i:Robotics:\s+Science\s+and\s+Systems)"),
    ("MICCAI", r"MICCAI"),
    ("IPMI", r"IPMI"),
    ("ISBI", r"ISBI"),
    ("MIDL", r"MIDL"),
    ("ICASSP", r"ICASSP"),
    ("ICIP", r"ICIP"),
    ("ICME", r"ICME"),
    ("ICPR", r"ICPR"),
    ("IGARSS", r"IGARSS"),
    ("KDD", r"KDD"),
    ("ECML PKDD", r"ECML[\s-]?PKDD"),
    ("AISTATS", r"AISTATS"),
    ("TPAMI", r"T-?PAMI|(?i:Pattern\s+Analysis\s+and\s+Machine\s+Intelligence)"),
    ("IJCV", r"IJCV|(?i:International\s+Journal\s+of\s+Computer\s+Vision)"),
    ("TIP", r"TIP|(?i:Transactions\s+on\s+Image\s+Processing)"),
    ("TMI", r"TMI|(?i:Transactions\s+on\s+Medical\s+Imaging)"),
    ("TVCG", r"TVCG|(?i:Transactions\s+on\s+Visualization\s+and\s+Computer\s+Graphics)"),
    ("TMLR", r"TMLR|(?i:Transactions\s+on\s+Machine\s+Learning\s+Research)"),
    ("JMLR", r"JMLR"),
    ("RA-L", r"RA-?L|(?i:Robotics\s+and\s+Automation\s+Letters)"),
    ("MedIA", r"MedIA|(?i:Medical\s+Image\s+Analysis)"),
)
_KNOWN_RE = re.compile(
    "|".join(f"(?P<v{index}>{pattern})" for index, (_, pattern) in enumerate(_KNOWN_VENUES))
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
    r"\baccept|\bto appear\b|\bpublished\b|\bcamera[- ]ready\b|\bproceedings\b", re.IGNORECASE
)
_NOT_ACCEPTED_RE = re.compile(
    r"\bsubmitt?ed\b|\bsubmission\b|\bunder review\b|\bin review\b|\b(?:extended|shorter) version\b",
    re.IGNORECASE,
)
_WORKSHOP_RE = re.compile(r"workshop|\b(?:CVPR|ICCV|ECCV)W\b", re.IGNORECASE)
# Years: "2026", or "'26" as in "SIGGRAPH Asia '26".
_YEAR = r"(?:(?P<year>20\d{2})|['\u2019](?P<short>\d{2}))\b"
_YEAR_AFTER_RE = re.compile(rf"^[\s)\],:-]{{0,4}}(?:(?:Workshops?|Asia)\s*)?[\s(),-]{{0,4}}{_YEAR}")
_YEAR_BEFORE_RE = re.compile(r"\b(?P<year>20\d{2})\s+(?:(?:IEEE|ACM|IEEE/CVF)\s+)?$")
_ANY_YEAR_RE = re.compile(rf"(?<!\w){_YEAR}")
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
        clause
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
    """First well-known venue named in the clause, with its year when one is given."""
    for match in _KNOWN_RE.finditer(clause):
        before, after = clause[: match.start()], clause[match.end() :]
        if _BOUNDARY_BEFORE.search(before) or _BOUNDARY_AFTER.search(after.removeprefix("W")):
            continue
        name = next(_KNOWN_VENUES[int(group[1:])][0] for group, value in match.groupdict().items() if value)
        # Next to the name ("ECCV 2026", "2026 ECCV"), else anywhere in the clause
        # ("Proceedings of the ... (WACV), 2026").
        year = _year(before, after, clause)
        suffix = " Workshop" if _WORKSHOP_RE.search(clause) else ""
        return f"{name}{year}{suffix}"
    return None


def _year(before: str, after: str, clause: str) -> str:
    """Year next to the venue name ("ECCV 2026", "2026 ECCV"), else anywhere in the clause."""
    match = _YEAR_AFTER_RE.search(after) or _YEAR_BEFORE_RE.search(before) or _ANY_YEAR_RE.search(clause)
    if match is None:
        return ""
    groups = {key: value for key, value in match.groupdict().items() if value}
    return f" {groups['year']}" if "year" in groups else f" 20{groups['short']}"
