"""Affiliations of archived papers, from OpenAlex.

Most papers older than late 2023 have no HTML rendering on arXiv, so their affiliations
cannot be read the way recent ones are. OpenAlex (CC0 data, no key needed) knows the
institutions of each author of an arXiv paper, looked up by its arXiv DOI
(``10.48550/arXiv.<id>``), 50 papers per request. Its institutions are registry entries
(ROR), so they serve as both the affiliations and their institutions; its raw
affiliation strings are too rough to show ("Google,,,,,", "[Google Brain]").
"""

import json
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import batched

from preprint_radar.exceptions import FetchError, ParseError
from preprint_radar.http import HttpClient
from preprint_radar.institutions import organization_name

logger = logging.getLogger(__name__)

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
OPENALEX_BATCH_SIZE = 50
# OpenAlex allows 10 requests per second; stay well below.
OPENALEX_DELAY_SECONDS = 0.5
_ARXIV_DOI_PREFIX = "10.48550/arxiv."


@dataclass(frozen=True, slots=True)
class PaperAffiliations:
    """Affiliations of a paper, in the shape of :class:`~preprint_radar.models.Paper`.

    Attributes:
        affiliations: Distinct institutions, in order of first appearance.
        author_affiliations: Per author, indices into ``affiliations``; ``None`` when
            OpenAlex does not list the same number of authors as arXiv.
    """

    affiliations: tuple[str, ...]
    author_affiliations: tuple[tuple[int, ...] | None, ...] | None


def fetch_affiliations(client: HttpClient, papers: Mapping[str, int]) -> dict[str, PaperAffiliations]:
    """Affiliations of arXiv papers.

    Args:
        client: HTTP client for OpenAlex.
        papers: Number of arXiv authors of each paper, by arXiv identifier.

    Returns:
        The affiliations of the papers OpenAlex returned (empty when it places their
        authors nowhere). Papers it did not return are left out, to be tried again later:
        its batch answers vary, the same 50 papers giving 49 works once and 42 the next.
    """
    found: dict[str, PaperAffiliations] = {}
    for batch in batched(papers, OPENALEX_BATCH_SIZE, strict=False):
        try:
            text = client.get_text(
                OPENALEX_WORKS_URL,
                params={
                    "filter": "doi:" + "|".join(_ARXIV_DOI_PREFIX + arxiv_id for arxiv_id in batch),
                    "select": "doi,authorships",
                    "per-page": OPENALEX_BATCH_SIZE,
                },
            )
            works = parse_works(text)
        except (FetchError, ParseError) as exc:
            logger.warning("OpenAlex lookup of %d papers failed: %s", len(batch), exc)
            continue
        for arxiv_id in batch:
            if arxiv_id in works:
                found[arxiv_id] = affiliations_from_authorships(works[arxiv_id], papers[arxiv_id])
        logger.info("%d papers looked up in OpenAlex", len(found))
    return found


def parse_works(text: str) -> dict[str, list[list[str]]]:
    """Institutions of each author of the works in a ``/works`` response, by arXiv id.

    Raises:
        ParseError: If the response is not the expected JSON.
    """
    try:
        results = json.loads(text)["results"]
        works: dict[str, list[list[str]]] = {}
        for work in results:
            doi = str(work.get("doi") or "").lower()
            if _ARXIV_DOI_PREFIX not in doi:
                continue
            arxiv_id = doi.split(_ARXIV_DOI_PREFIX, maxsplit=1)[1]
            works[arxiv_id] = [_institutions(authorship) for authorship in work.get("authorships") or []]
    except (json.JSONDecodeError, AttributeError, KeyError, TypeError) as exc:
        msg = f"Unexpected OpenAlex response: {exc}"
        raise ParseError(msg) from exc
    return works


def affiliations_from_authorships(authorships: list[list[str]], authors: int) -> PaperAffiliations:
    """Turn per-author institutions into distinct affiliations and a mapping.

    Args:
        authorships: Institutions of each author, in OpenAlex's order.
        authors: Number of authors arXiv lists; the mapping is only kept when it matches.
    """
    affiliations: list[str] = []
    for names in authorships:
        affiliations.extend(name for name in names if name not in affiliations)
    if len(authorships) != authors or not affiliations:
        return PaperAffiliations(tuple(affiliations), None)
    mapping = tuple(tuple(affiliations.index(name) for name in names) or None for names in authorships)
    return PaperAffiliations(tuple(affiliations), mapping)


def _institutions(authorship: Mapping[str, object]) -> list[str]:
    names: list[str] = []
    institutions = authorship.get("institutions")
    for institution in institutions if isinstance(institutions, Iterable) else []:
        if not isinstance(institution, Mapping) or not institution.get("display_name"):
            continue
        name = organization_name(
            str(institution["display_name"]), company=institution.get("type") == "company"
        )
        if name not in names:
            names.append(name)
    return names
