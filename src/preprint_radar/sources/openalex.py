"""Affiliations of archived papers, from OpenAlex.

Most papers older than late 2023 have no HTML rendering on arXiv, so their affiliations
cannot be read the way recent ones are. OpenAlex (CC0 data, no key needed) knows the
institutions of each author of an arXiv paper, looked up by its arXiv DOI
(``10.48550/arXiv.<id>``), 50 papers per request. Its institutions are registry entries
(ROR), so they serve as both the affiliations and their institutions; its raw
affiliation strings are too rough to show ("Google,,,,,", "[Google Brain]").

It knows those of few preprints of the last two years, but those of nearly every published
version: :func:`fetch_published_authors` asks for the published versions of papers, by
their DOI, and :func:`published_affiliations` keeps the institutions of their arXiv
authors (AFF-20).
"""

import json
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import batched

from preprint_radar.exceptions import FetchError, NotFoundError, ParseError
from preprint_radar.http import HttpClient
from preprint_radar.models import Institution
from preprint_radar.names import same_person
from preprint_radar.sources.ror import organization_name, ror_id

logger = logging.getLogger(__name__)

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
OPENALEX_BATCH_SIZE = 50
# OpenAlex allows 10 requests per second; stay well below.
OPENALEX_DELAY_SECONDS = 0.25
_ARXIV_DOI_PREFIX = "10.48550/arxiv."
_DOI_URL_PREFIX = "https://doi.org/"
# What separates the values and the filters of a filter parameter: a DOI holding one cannot
# be asked for in a batch (none of the 15,222 of cs.CV does).
_FILTER_SEPARATORS = frozenset("|,")


@dataclass(frozen=True, slots=True)
class PaperAffiliations:
    """Affiliations of a paper, in the shape of :class:`~preprint_radar.models.Paper`.

    Attributes:
        affiliations: Distinct institutions, in order of first appearance.
        author_affiliations: Per author, indices into ``affiliations``; ``None`` when
            OpenAlex does not list the same number of authors as arXiv.
        institution_ids: The ROR id of each institution, when OpenAlex gives it.
    """

    affiliations: tuple[str, ...]
    author_affiliations: tuple[tuple[int, ...] | None, ...] | None
    institution_ids: tuple[str | None, ...] = ()


def fetch_affiliations(client: HttpClient, papers: Mapping[str, int]) -> dict[str, PaperAffiliations]:
    """Affiliations of arXiv papers.

    Args:
        client: HTTP client for OpenAlex.
        papers: Number of arXiv authors of each paper, by arXiv identifier.

    Returns:
        The affiliations of the papers looked up (empty when OpenAlex does not know the
        paper or places its authors nowhere). Papers whose lookup failed are left out, to
        be tried again later.
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
            # The DOI filter misses some works that the DOI lookup finds (a batch of 25 such
            # papers gave none): ask for the missing ones one by one.
            authorships = works[arxiv_id] if arxiv_id in works else _lookup(client, arxiv_id)
            if authorships is not None:
                found[arxiv_id] = affiliations_from_authorships(authorships, papers[arxiv_id])
        logger.info("%s papers looked up in OpenAlex", f"{len(found):,}")
    return found


def _lookup(client: HttpClient, arxiv_id: str) -> list[list[Institution]] | None:
    """Institutions of each author of one paper; ``[]`` if unknown, ``None`` on failure."""
    try:
        text = client.get_text(
            f"{OPENALEX_WORKS_URL}/doi:{_ARXIV_DOI_PREFIX}{arxiv_id}", params={"select": "doi,authorships"}
        )
        return parse_works(f'{{"results": [{text}]}}').get(arxiv_id, [])
    except NotFoundError:
        return []
    except (FetchError, ParseError) as exc:
        logger.warning("OpenAlex lookup of %s failed: %s", arxiv_id, exc)
        return None


def parse_works(text: str) -> dict[str, list[list[Institution]]]:
    """Institutions of each author of the works in a ``/works`` response, by arXiv id.

    Raises:
        ParseError: If the response is not the expected JSON.
    """
    try:
        results = json.loads(text)["results"]
        works: dict[str, list[list[Institution]]] = {}
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


def affiliations_from_authorships(authorships: list[list[Institution]], authors: int) -> PaperAffiliations:
    """Turn per-author institutions into distinct affiliations and a mapping.

    Args:
        authorships: Institutions of each author, in OpenAlex's order.
        authors: Number of authors arXiv lists; the mapping is only kept when it matches.
    """
    distinct: dict[str, Institution] = {}
    for institutions in authorships:
        for institution in institutions:
            distinct.setdefault(institution.name, institution)
    affiliations = list(distinct)
    ids = tuple(institution.ror_id for institution in distinct.values())
    if len(authorships) != authors or not affiliations:
        return PaperAffiliations(tuple(affiliations), None, ids)
    mapping = tuple(
        tuple(affiliations.index(institution.name) for institution in institutions) or None
        for institutions in authorships
    )
    return PaperAffiliations(tuple(affiliations), mapping, ids)


@dataclass(frozen=True, slots=True)
class PublishedAuthor:
    """An author of a published version, as OpenAlex names them, with their institutions."""

    name: str
    institutions: tuple[Institution, ...]


def fetch_published_authors(client: HttpClient, dois: Iterable[str]) -> dict[str, list[PublishedAuthor]]:
    """The authors of published versions, with their institutions, 50 DOIs per request.

    Args:
        client: HTTP client for OpenAlex.
        dois: DOIs of the published versions.

    Returns:
        The authors of each version OpenAlex knows, by lowercase DOI. Versions whose lookup
        failed are left out, to be asked for again next time.
    """
    wanted = sorted({doi.lower() for doi in dois if not _FILTER_SEPARATORS & set(doi)})
    found: dict[str, list[PublishedAuthor]] = {}
    for batch in batched(wanted, OPENALEX_BATCH_SIZE, strict=False):
        try:
            text = client.get_text(
                OPENALEX_WORKS_URL,
                params={
                    "filter": "doi:" + "|".join(batch),
                    "select": "doi,authorships",
                    "per-page": OPENALEX_BATCH_SIZE,
                },
            )
            found.update(parse_published_works(text))
        except (FetchError, ParseError) as exc:
            logger.warning("OpenAlex lookup of %d published versions failed: %s", len(batch), exc)
    return found


def parse_published_works(text: str) -> dict[str, list[PublishedAuthor]]:
    """The authors of the works in a ``/works`` response, with their institutions, by lowercase DOI.

    Raises:
        ParseError: If the response is not the expected JSON.
    """
    try:
        works: dict[str, list[PublishedAuthor]] = {}
        for work in json.loads(text)["results"]:
            doi = str(work.get("doi") or "").lower().removeprefix(_DOI_URL_PREFIX)
            if doi:
                works[doi] = [
                    PublishedAuthor(_author_name(authorship), tuple(_institutions(authorship)))
                    for authorship in work.get("authorships") or []
                ]
    except (json.JSONDecodeError, AttributeError, KeyError, TypeError) as exc:
        msg = f"Unexpected OpenAlex response: {exc}"
        raise ParseError(msg) from exc
    return works


def published_affiliations(
    authors: Sequence[str], published: Sequence[PublishedAuthor]
) -> PaperAffiliations | None:
    """The affiliations of a paper from the authors of its published version.

    The published version can add or drop authors, or order them otherwise: each arXiv
    author takes the institutions of the published author of the same name
    (:func:`names.same_person`), and the institutions of authors arXiv does not list are
    left out.

    Args:
        authors: The paper's authors, as arXiv lists them.
        published: The authors of its published version.

    Returns:
        Its affiliations, with the mapping of each author placed; ``None`` when fewer than
        half of its authors are among the published ones, whose version is then another
        paper's (a wrong DOI).
    """
    unmatched = list(published)
    per_author: list[tuple[Institution, ...] | None] = []
    for author in authors:
        match = next((candidate for candidate in unmatched if same_person(author, candidate.name)), None)
        if match is not None:
            unmatched.remove(match)
        per_author.append(None if match is None else match.institutions)
    if 2 * sum(institutions is not None for institutions in per_author) < len(authors):
        return None
    distinct: dict[str, Institution] = {}
    for institutions in per_author:
        for institution in institutions or ():
            distinct.setdefault(institution.name, institution)
    if not distinct:
        return PaperAffiliations((), None)
    names = list(distinct)
    mapping = tuple(
        tuple(names.index(institution.name) for institution in institutions or ()) or None
        for institutions in per_author
    )
    return PaperAffiliations(
        tuple(names), mapping, tuple(institution.ror_id for institution in distinct.values())
    )


def _author_name(authorship: Mapping[str, object]) -> str:
    """OpenAlex's name for an author, else the name the work gives ("Dosovitskiy, Alexey")."""
    author = authorship.get("author")
    name = author.get("display_name") if isinstance(author, Mapping) else None
    return str(name or authorship.get("raw_author_name") or "")


def _institutions(authorship: Mapping[str, object]) -> list[Institution]:
    found: list[Institution] = []
    institutions = authorship.get("institutions")
    for institution in institutions if isinstance(institutions, Iterable) else []:
        if not isinstance(institution, Mapping) or not institution.get("display_name"):
            continue
        name = organization_name(
            str(institution["display_name"]), company=institution.get("type") == "company"
        )
        if all(known.name != name for known in found):
            found.append(Institution(name, ror_id(institution.get("ror"))))
    return found
