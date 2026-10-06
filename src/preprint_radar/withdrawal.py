"""Whether a paper was withdrawn, from its comments (decision 18).

An author withdraws an arXiv paper by submitting a last version without a PDF, whose
comments say so: "This paper has been withdrawn by the author due to a crucial sign
error", "We would like to withdraw this paper", "Withdrawn by arXiv admins". Its earlier
versions stay readable, but nobody stands by them any more: the site leaves withdrawn
papers out of Highly cited and marks them in the day views.

The comments also mention withdrawals that are not this paper's: from a workshop or the
proceedings ("withdrawn from AutoNUE workshop at ECCV 2018", 1808.07703), of an earlier
version ("V1 has been withdrawn due to a template issue", 2504.12080), of another
submission ("The wrong submission has now been withdrawn", 2411.14243), or of a paper
it replaces ("a revised version of the withdrawn paper").
"""

import re

_WITHDRAWAL_RE = re.compile(r"\bwithdr(?:aw(?:n|s|ing|al)?|ew)\b", re.IGNORECASE)
# From somewhere other than arXiv: a venue, the proceedings, a conference.
_FROM_ELSEWHERE_RE = re.compile(
    r"(?:\s+\w+){0,2}?\s+from\s+(?!arxiv\b|public\b|(?:this|the)\s+(?:website|site|server)\b)",
    re.IGNORECASE,
)
# Something other than this paper was withdrawn: an earlier version, another submission.
_ANOTHER_SUBJECT_RE = re.compile(
    r"(?:\bv\d+|\b(?:wrong|other|old|previous|earlier|duplicate)\s+(?:submission|version|manuscript|paper))"
    r"(?:\s+(?:has|have|had|was|were|is|been|now))*\s*$",
    re.IGNORECASE,
)
# "the withdrawn paper", which this one replaces.
_ATTRIBUTIVE_RE = re.compile(r"\s+(?:paper|version|manuscript|submission|work|preprint)\b", re.IGNORECASE)
_ARTICLE_RE = re.compile(r"\b(?:the|a|previously|earlier)\s+$", re.IGNORECASE)


def is_withdrawn(comments: str | None) -> bool:
    """Whether the comments say that the paper itself was withdrawn.

    Args:
        comments: The comments of the paper's latest version.

    Returns:
        ``True`` when one mention of a withdrawal is about this paper.
    """
    text = comments or ""
    for match in _WITHDRAWAL_RE.finditer(text):
        before, after = text[: match.start()], text[match.end() :]
        elsewhere = _FROM_ELSEWHERE_RE.match(after) is not None
        another = _ANOTHER_SUBJECT_RE.search(before) is not None
        attributive = (
            match.group().lower() == "withdrawn"
            and _ARTICLE_RE.search(before) is not None
            and _ATTRIBUTIVE_RE.match(after) is not None
        )
        if not (elsewhere or another or attributive):
            return True
    return False
