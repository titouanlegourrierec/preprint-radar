"""Whether another service's name for an author is the arXiv author's.

Semantic Scholar and OpenAlex list the authors of the version they know, which can be
another paper's (a wrong link) or have other authors, in another order: what they say of an
author is only kept where their name is the paper's author's.
"""

import re
import unicodedata

from preprint_radar.institutions import PLAIN_LETTERS

_NAME_JOINER_RE = re.compile("[-'\N{RIGHT SINGLE QUOTATION MARK}.]")
_NAME_WORD_RE = re.compile(r"[^\W_]+")


def same_person(listed: str, named: str) -> bool:
    """Whether ``named`` is the author arXiv lists as ``listed``.

    One spelling holds the other's words ("Mahdi Hosseini", "Mahdi S. Hosseini", "Hosseini,
    Mahdi"), or both have the same surname and given names that start alike ("M.
    Hosseini"). Accents and letters such as "ø" fold away; a transliteration does not
    ("Plötz" is not "Ploetz").
    """
    words, other = name_words(listed), name_words(named)
    if not words or not other:
        return False
    if set(words) <= set(other) or set(other) <= set(words):
        return True
    # Initials: the same surname, and given names that start alike ("D. Gopinath").
    return words[-1] == other[-1] and words[0][0] == other[0][0]


def name_words(name: str) -> list[str]:
    """A name's words, folded, a hyphenated given name as one: "Jin-Chao" is "jinchao"."""
    # In the order of ``institutions.search_key``: marks first, so that "ǿ" is "o" too.
    decomposed = unicodedata.normalize("NFD", name)
    folded = "".join(char for char in decomposed if not unicodedata.combining(char))
    folded = folded.lower().translate(PLAIN_LETTERS)
    return _NAME_WORD_RE.findall(_NAME_JOINER_RE.sub("", folded.replace(". ", " ")))
