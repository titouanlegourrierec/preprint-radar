"""Institutions named by affiliation strings, from the Research Organization Registry (ROR).

ROR's affiliation matching (``/v2/organizations?affiliation=...``) marks the match it is
confident about as ``chosen``. It is right for most universities written in full ("School
of Computer Science, Peking University, Beijing" is Peking University), but it can pick a
wrong organization on a single common word ("ARC Lab, Tencent" matched an association
called ARC). A match is therefore only kept when one of the organization's names, of at
least two significant words, appears word for word in the affiliation. Acronyms and most
companies are not matched; the web app names those with its own rules.
"""

import json
import logging
import re
import unicodedata
from collections.abc import Iterable, Mapping

from preprint_radar.exceptions import FetchError, NotFoundError, ParseError
from preprint_radar.http import HttpClient

logger = logging.getLogger(__name__)

ROR_API_URL = "https://api.ror.org/v2/organizations"
# ROR allows about 2,000 requests per 5 minutes; stay well below.
ROR_DELAY_SECONDS = 0.5

_STOP_WORDS = frozenset(
    {"the", "of", "and", "for", "at", "in", "de", "du", "des", "la", "le", "di", "del", "der"}
)
_MIN_NAME_WORDS = 2
_PARENTHESIS_RE = re.compile(r"\([^()]*\)")
_TRAILING_PARENTHESIS_RE = re.compile(r"\s*\([^()]*\)$")
_LEADING_THE_RE = re.compile(r"^the\s+", re.IGNORECASE)
_WORD_RE = re.compile(r"[^\W_]+")


def match_institution(client: HttpClient, affiliation: str) -> str | None:
    """Name of the institution an affiliation string belongs to, according to ROR.

    Args:
        client: HTTP client for the ROR API.
        affiliation: One affiliation string, e.g. ``"Dept. of EECS, MIT, Cambridge, MA"``.

    Returns:
        The organization's name, or ``None`` when ROR has no confident, supported match.

    Raises:
        FetchError: If the API cannot be reached.
        ParseError: If the response is not the expected JSON.
    """
    try:
        text = client.get_text(ROR_API_URL, params={"affiliation": affiliation})
    except NotFoundError:
        return None
    return parse_ror_response(text, affiliation)


def parse_ror_response(text: str, affiliation: str) -> str | None:
    """Extract the institution name from a ROR affiliation-matching response.

    Args:
        text: Body of the ``/v2/organizations?affiliation=...`` response.
        affiliation: The affiliation string that was matched.

    Returns:
        The chosen organization's name if one of its names appears in the affiliation,
        else ``None``.

    Raises:
        ParseError: If the response is not the expected JSON.
    """
    try:
        items = json.loads(text)["items"]
        chosen = next((item["organization"] for item in items if item.get("chosen")), None)
    except (json.JSONDecodeError, AttributeError, KeyError, TypeError) as exc:
        msg = f"Unexpected ROR response for {affiliation!r}: {exc}"
        raise ParseError(msg) from exc
    if chosen is None or not _is_supported(affiliation, chosen):
        return None
    return _display_name(chosen)


def match_institutions(
    client: HttpClient, affiliations: Iterable[str], *, limit: int | None = None
) -> dict[str, str | None]:
    """Match distinct affiliation strings, stopping at the first unreachable request.

    Args:
        client: HTTP client for the ROR API.
        affiliations: Affiliation strings; duplicates are looked up once.
        limit: Maximum number of requests (``None``: no limit).

    Returns:
        The strings that could be looked up, with their institution (``None``: no match).
        Strings left out (limit reached, API unreachable) are to be tried again later.
    """
    matches: dict[str, str | None] = {}
    for affiliation in dict.fromkeys(affiliations):
        if limit is not None and len(matches) >= limit:
            break
        try:
            matches[affiliation] = match_institution(client, affiliation)
        except (FetchError, ParseError) as exc:
            logger.warning("ROR lookup stopped after %d strings: %s", len(matches), exc)
            break
    return matches


def _is_supported(affiliation: str, organization: Mapping[str, object]) -> bool:
    """Whether one of the organization's names (not an acronym) is written in the affiliation."""
    words = _words(affiliation)
    names = organization.get("names")
    if not isinstance(names, list):
        return False
    for name in names:
        if not isinstance(name, dict) or set(name.get("types", [])) <= {"acronym"}:
            continue
        wanted = _words(str(name.get("value", "")))
        if len(wanted) >= _MIN_NAME_WORDS and wanted <= words:
            return True
    return False


def _display_name(organization: Mapping[str, object]) -> str | None:
    """The organization's display name, without "The" nor a company's country suffix."""
    names = organization.get("names")
    if not isinstance(names, list):
        return None
    display = next(
        (
            str(name["value"])
            for name in names
            if isinstance(name, dict) and "ror_display" in name.get("types", [])
        ),
        None,
    )
    if display is None:
        return None
    display = _LEADING_THE_RE.sub("", display)
    types = organization.get("types")
    # "Google DeepMind (United Kingdom)": companies carry their country, universities their
    # campus ("... (Guangzhou)"), which is kept.
    if isinstance(types, list) and "company" in types:
        display = _TRAILING_PARENTHESIS_RE.sub("", display)
    return display


def _words(text: str) -> set[str]:
    """Significant words of a name, folded, without parenthesized parts."""
    decomposed = unicodedata.normalize("NFKD", _PARENTHESIS_RE.sub(" ", text))
    folded = "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()
    return {word for word in _WORD_RE.findall(folded) if word not in _STOP_WORDS}
