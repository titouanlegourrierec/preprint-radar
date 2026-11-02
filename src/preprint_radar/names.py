"""Whether another service's name for an author is the arXiv author's.

Semantic Scholar and OpenAlex list the authors of the version they know, which can be
another paper's (a wrong link) or have other authors, in another order: what they say of an
author is only kept where their name is the paper's author's.
"""

import re
import unicodedata
from collections import Counter

from preprint_radar.letters import PLAIN_LETTERS

_NAME_JOINER_RE = re.compile("[-'\N{RIGHT SINGLE QUOTATION MARK}.]")
_NAME_WORD_RE = re.compile(r"[^\W_]+")


def same_person(listed: str, named: str, *, initials: bool = True) -> bool:
    """Whether ``named`` is the author arXiv lists as ``listed``.

    One spelling holds the other's words, each as many times ("Mahdi Hosseini", "Mahdi S.
    Hosseini", "Hosseini, Mahdi"; "Yan Yan" is not "Yichao Yan"), or, with ``initials``,
    both have the same surname and one's given name is the initial of the other's ("M.
    Hosseini"): two given names written out are two people ("Wen Li", "Wei Li", AQ-8).
    Accents and letters such as "ø" fold away; a transliteration does not ("Plötz" is not
    "Ploetz").

    Args:
        listed: The name arXiv lists.
        named: Another service's name for an author.
        initials: Whether an initial may stand for a given name.
    """
    words, other = name_words(listed), name_words(named)
    if not words or not other:
        return False
    mine, theirs = Counter(words), Counter(other)
    if mine <= theirs or theirs <= mine:
        return True
    # Initials: the same surname, and a given name that is the other's initial ("D. Gopinath").
    first, second = words[0], other[0]
    return (
        initials
        and words[-1] == other[-1]
        and (len(first) == 1 or len(second) == 1)
        and first[0] == second[0]
    )


def name_words(name: str) -> list[str]:
    """A name's words, folded, a hyphenated given name as one: "Jin-Chao" is "jinchao"."""
    # In the order of ``institutions.search_key``: marks first, so that "ǿ" is "o" too.
    decomposed = unicodedata.normalize("NFD", name)
    folded = "".join(char for char in decomposed if not unicodedata.combining(char))
    folded = folded.lower().translate(PLAIN_LETTERS)
    return _NAME_WORD_RE.findall(_NAME_JOINER_RE.sub("", folded.replace(". ", " ")))
