"""Names as the extraction compares them: case, accents, punctuation and order aside."""

import re
import unicodedata

from preprint_radar.letters import PLAIN_LETTERS

# Curly quotes and long dashes fold to their ASCII forms: "Shin\u2019ichi" == "Shin'ichi",
# and "Linxi \u201cJim\u201d Fan" is the listing's 'Linxi "Jim" Fan' (2610.19495). So does a
# dotless "\u0131", which the listing writes for LaTeX's "\'{\i}": "Alvaro Garc\u0131a" is the
# page's "\u00c1lvaro Garc\u00eda" (2505.12089).
_PUNCTUATION_VARIANTS = str.maketrans(
    "\u2018\u2019\u02bc\u201c\u201d\u2013\u2014\u2212\u0131", "'" * 3 + '"' * 2 + "-" * 3 + "i"
)


def _fold(text: str) -> str:
    """Lowercase, strip accents and normalize punctuation, for name comparison.

    Letters without a decomposition are written plainly, as everywhere names are compared:
    "Bartłomiej" is "Bartlomiej" (``PLAIN_LETTERS``, EXT-7).
    """
    decomposed = unicodedata.normalize("NFKD", text.translate(_PUNCTUATION_VARIANTS))
    folded = "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()
    return folded.translate(PLAIN_LETTERS)


# Apostrophes and LaTeX accent leftovers join the letters around them ("Niccol`o" is "Niccolò").
_NAME_JOINERS_RE = re.compile(r"['`^~\"]")


def name_key(name: str) -> tuple[str, ...]:
    """Key under which two spellings of one person's name compare equal.

    Case, accents, punctuation and word order are ignored, so a new version of a paper
    that respells an author ("Ma Ziqi" as "Ziqi Ma", "Niccol`o" as "Niccolò") keeps them.

    Args:
        name: An author name as listed.

    Returns:
        The name's words, folded and sorted.
    """
    return tuple(sorted(re.findall(r"[^\W_]+", _NAME_JOINERS_RE.sub("", _fold(name)))))
