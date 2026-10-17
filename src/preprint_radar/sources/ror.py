"""Institutions named by affiliation strings, from the Research Organization Registry (ROR).

ROR's affiliation matching (``/v2/organizations?affiliation=...``) marks the match it is
confident about as ``chosen``. It is right for most universities written in full ("School
of Computer Science, Peking University, Beijing" is Peking University), but it can pick a
wrong organization on a single common word ("ARC Lab, Tencent" matched an association
called ARC). A match is therefore only kept when one of the organization's names, of at
least two significant words, appears word for word in the affiliation. Acronyms and most
companies are not matched; the web app names those with its own rules. ROR can also choose
a shorter name inside the right one ("Texas A&M University" for "Texas A&M
University-Kingsville", whose hyphen ROR writes as a spaced en dash): a candidate whose
whole name holds the chosen one's and is written in the affiliation is kept instead.
"""

import json
import logging
import re
import unicodedata
from collections.abc import Iterable, Mapping

from preprint_radar.console import Advance, no_progress
from preprint_radar.exceptions import FetchError, NotFoundError, ParseError
from preprint_radar.http import HttpClient
from preprint_radar.models import Institution

logger = logging.getLogger(__name__)

ROR_API_URL = "https://api.ror.org/v2/organizations"
# ROR allows about 2,000 requests per 5 minutes; stay well below.
ROR_DELAY_SECONDS = 0.5
# Lookups in a row that may fail before ROR is considered down.
MAX_CONSECUTIVE_FAILURES = 3

_STOP_WORDS = frozenset(
    {"the", "of", "and", "for", "at", "in", "de", "du", "des", "la", "le", "di", "del", "der"}
)
_MIN_NAME_WORDS = 2
_PARENTHESIS_RE = re.compile(r"\([^()]*\)")
_TRAILING_PARENTHESIS_RE = re.compile(r"\s*\([^()]*\)$")
_LEADING_THE_RE = re.compile(r"^the\s+", re.IGNORECASE)
_WORD_RE = re.compile(r"[^\W_]+")
# Hyphens and dashes, which affiliations and ROR's names write as they please (AFF-30).
_DASH_RE = re.compile(r"[-\u2010-\u2015\u2212]")
_ROR_URL_RE = re.compile(r"^https?://ror\.org/([0-9a-z]{9})$")


def match_institution(client: HttpClient, affiliation: str) -> Institution | None:
    """The institution an affiliation string belongs to, according to ROR.

    Args:
        client: HTTP client for the ROR API.
        affiliation: One affiliation string, e.g. ``"Dept. of EECS, MIT, Cambridge, MA"``.

    Returns:
        The organization, or ``None`` when ROR has no confident, supported match.

    Raises:
        FetchError: If the API cannot be reached.
        ParseError: If the response is not the expected JSON.
    """
    try:
        text = client.get_text(ROR_API_URL, params={"affiliation": affiliation})
    except NotFoundError:
        return None
    return parse_ror_response(text, affiliation)


def parse_ror_response(text: str, affiliation: str) -> Institution | None:
    """Extract the institution from a ROR affiliation-matching response.

    Args:
        text: Body of the ``/v2/organizations?affiliation=...`` response.
        affiliation: The affiliation string that was matched.

    Returns:
        The chosen organization, with its name and id, if one of its names appears in the
        affiliation, else ``None``.

    Raises:
        ParseError: If the response is not the expected JSON.
    """
    try:
        items = json.loads(text)["items"]
        chosen = next((item["organization"] for item in items if item.get("chosen")), None)
    except (json.JSONDecodeError, AttributeError, KeyError, TypeError) as exc:
        msg = f"Unexpected ROR response for {affiliation!r}: {exc}"
        raise ParseError(msg) from exc
    if not isinstance(chosen, dict):
        return None
    chosen = _longer_match(items, chosen, affiliation)
    names = chosen.get("names")
    if not isinstance(names, list) or not _is_supported(affiliation, names):
        return None
    name = _display_name(chosen, names)
    return None if name is None else Institution(name, ror_id(chosen.get("id")))


def match_institutions(
    client: HttpClient,
    affiliations: Iterable[str],
    *,
    limit: int | None = None,
    progress: Advance = no_progress,
) -> dict[str, Institution | None]:
    """Match distinct affiliation strings, giving up when ROR keeps failing.

    A failed lookup (timeout, server error) leaves its string for later; a few failures
    in a row mean that ROR is down, and stop the lookups.

    Args:
        client: HTTP client for the ROR API.
        affiliations: Affiliation strings; duplicates are looked up once.
        limit: Maximum number of requests (``None``: no limit).
        progress: Told of each string looked up.

    Returns:
        The strings that could be looked up, with their institution (``None``: no match).
        Strings left out (limit reached, lookup failed) are to be tried again later.
    """
    matches: dict[str, Institution | None] = {}
    failures = 0
    for requests, affiliation in enumerate(dict.fromkeys(affiliations), start=1):
        if limit is not None and requests > limit:
            break
        try:
            matches[affiliation] = match_institution(client, affiliation)
        except (FetchError, ParseError) as exc:
            failures += 1
            logger.warning("ROR lookup of %r failed: %s", affiliation, exc)
            if failures >= MAX_CONSECUTIVE_FAILURES:
                logger.warning("ROR keeps failing; stopping after %d lookups", requests)
                break
        else:
            failures = 0
        finally:
            progress(1)
    return matches


def _longer_match(
    items: list[dict[str, object]], chosen: dict[str, object], affiliation: str
) -> dict[str, object]:
    """The candidate whose name holds the chosen one's and is written whole in the affiliation (AFF-30).

    "Texas A&M University-Kingsville (TAMUK)" chose Texas A&M University (score 1.0) over
    Texas A&M University - Kingsville (0.95, an en dash), which it is (2609.22631). Names are compared
    as runs of words, dashes and case aside; the first such candidate, in ROR's order,
    wins. Else the chosen organization.
    """
    written = f" {' '.join(_word_run(affiliation))} "
    chosen_names = [run for run in _name_runs(chosen) if f" {run} " in written]
    for item in items:
        organization = item.get("organization") if isinstance(item, dict) else None
        if not isinstance(organization, dict) or organization is chosen:
            continue
        for run in _name_runs(organization):
            if f" {run} " in written and any(
                f" {name} " in f" {run} " and name != run for name in chosen_names
            ):
                return organization
    return chosen


def _name_runs(organization: Mapping[str, object]) -> list[str]:
    """The organization's names but acronyms, each as its run of folded words."""
    names = organization.get("names")
    return [
        " ".join(_word_run(str(name.get("value", ""))))
        for name in (names if isinstance(names, list) else [])
        if isinstance(name, dict) and not set(name.get("types", [])) <= {"acronym"}
    ]


def _word_run(text: str) -> list[str]:
    """The words of a text in order, folded, dashes splitting them, without parenthesized parts."""
    decomposed = unicodedata.normalize("NFKD", _PARENTHESIS_RE.sub(" ", _DASH_RE.sub(" ", text)))
    folded = "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()
    return _WORD_RE.findall(folded)


def _is_supported(affiliation: str, names: list[object]) -> bool:
    """Whether one of the organization's names (not an acronym) is written in the affiliation."""
    words = _words(affiliation)
    for name in names:
        if not isinstance(name, dict) or set(name.get("types", [])) <= {"acronym"}:
            continue
        wanted = _words(str(name.get("value", "")))
        if len(wanted) >= _MIN_NAME_WORDS and wanted <= words:
            return True
    return False


def ror_id(url: object) -> str | None:
    """The id of a ROR URL ("https://ror.org/03vek6s52" is "03vek6s52"), else ``None``."""
    match = _ROR_URL_RE.match(url) if isinstance(url, str) else None
    return match.group(1) if match else None


def organization_name(name: str, *, company: bool) -> str:
    """An organization's name as registries write it, tidied for display.

    Drops a leading "The", and a company's country ("Google DeepMind (United Kingdom)",
    "Microsoft (United States)"); a university's campus ("... (Guangzhou)") is kept.
    """
    name = _LEADING_THE_RE.sub("", name.strip())
    return _TRAILING_PARENTHESIS_RE.sub("", name) if company else name


def _display_name(organization: Mapping[str, object], names: list[object]) -> str | None:
    """The organization's display name, tidied by :func:`organization_name`."""
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
    types = organization.get("types")
    return organization_name(display, company=isinstance(types, list) and "company" in types)


def _words(text: str) -> set[str]:
    """Significant words of a name, folded, without parenthesized parts."""
    decomposed = unicodedata.normalize("NFKD", _PARENTHESIS_RE.sub(" ", text))
    folded = "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()
    return {word for word in _WORD_RE.findall(folded) if word not in _STOP_WORDS}
