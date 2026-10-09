"""The stars of the repositories papers link, from GitHub's GraphQL API (PROD-18).

The REST API answers one repository per request, 60 an hour without a token: too few for
the 7,500 repositories of the stored papers. GraphQL takes 100 in one query, as aliases of
one ``repository`` field each, for one point of a token's 5,000 an hour (1,000 for a
workflow's ``GITHUB_TOKEN``, enough too); it needs a token, though one that may read
nothing but public data. A repository that was deleted, renamed away or never published
("code coming soon") comes back as a ``NOT_FOUND`` error for its alias, the others' stars
with it.
"""

import json
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from itertools import batched
from typing import Any

from preprint_radar.exceptions import FetchError, ParseError
from preprint_radar.http import HttpClient

logger = logging.getLogger(__name__)

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
GITHUB_BATCH_SIZE = 100
# GitHub asks for requests one at a time, with a pause, against its secondary limits.
GITHUB_DELAY_SECONDS = 1.0
# A bad or revoked token gets these on every request: trying again only wastes the run.
GITHUB_TOKEN_REJECTED = frozenset({401})
# An alias that cannot be a repository's: `rateLimit` is asked in the same query.
_ALIAS = "repo{}"


@dataclass(frozen=True, slots=True)
class Stars:
    """What GitHub said of the repositories asked for.

    Attributes:
        stars: The stars of each repository it knows, by ``owner/name`` (lowercase).
        missing: Those it does not know (deleted, private, renamed away or never public).
            The others were in a query that failed: asked again next time.
    """

    stars: dict[str, int] = field(default_factory=dict)
    missing: set[str] = field(default_factory=set)


def fetch_stars(client: HttpClient, repositories: Iterable[str], *, token: str) -> Stars:
    """The stars of GitHub repositories, 100 per query.

    Args:
        client: HTTP client for GitHub.
        repositories: ``owner/name`` of each.
        token: A GitHub token; any, even one that reads only public data.

    Returns:
        Their stars, and those GitHub does not know.

    Raises:
        FetchError: If GitHub rejects the token.
    """
    found = Stars()
    headers = {"Authorization": f"bearer {token}"}
    wanted = sorted(set(repositories))
    for batch in batched(wanted, GITHUB_BATCH_SIZE, strict=False):
        try:
            text = client.post_text(GITHUB_GRAPHQL_URL, json={"query": _query(batch)}, headers=headers)
            stars, missing, remaining = parse_stars(text, batch)
        except (FetchError, ParseError) as exc:
            if isinstance(exc, FetchError) and exc.status in GITHUB_TOKEN_REJECTED:
                msg = f"GitHub rejected the token (HTTP {exc.status}): {exc}"
                raise FetchError(msg, status=exc.status) from exc
            logger.warning("GitHub lookup of %d repositories failed: %s", len(batch), exc)
            continue
        found.stars.update(stars)
        found.missing.update(missing)
        logger.debug("GitHub: %s points left this hour", remaining)
    logger.info(
        "GitHub knows %s of %s repositories (%s not found)",
        f"{len(found.stars):,}",
        f"{len(wanted):,}",
        f"{len(found.missing):,}",
    )
    return found


def _query(batch: tuple[str, ...]) -> str:
    """A GraphQL query for the stars of each repository, aliased by its position."""
    fields = " ".join(
        f"{_ALIAS.format(position)}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) "
        "{ stargazerCount }"
        for position, (owner, name) in enumerate(repository.split("/", 1) for repository in batch)
    )
    return f"query {{ rateLimit {{ remaining }} {fields} }}"


def parse_stars(text: str, batch: tuple[str, ...]) -> tuple[dict[str, int], set[str], int | None]:
    """The stars of a batch's repositories, those not found, and the points left.

    Raises:
        ParseError: If the response is not GraphQL's JSON, or reports another error than a
            repository not found (a rate limit, a query it refused): the whole batch then
            waits for the next run.
    """
    try:
        payload: Any = json.loads(text)
        data: Mapping[str, Any] = payload.get("data") or {}
        errors: list[Mapping[str, Any]] = payload.get("errors") or []
        # A repository not found is its alias's error, its data null; any other is the query's.
        refused = [error for error in errors if error.get("type") != "NOT_FOUND"]
        if refused:
            msg = f"GitHub refused the query: {refused[0].get('message') or refused[0]}"
            raise ParseError(msg)
        stars: dict[str, int] = {}
        missing: set[str] = set()
        for position, repository in enumerate(batch):
            alias = _ALIAS.format(position)
            node = data.get(alias)
            if node is None:
                missing.add(repository)
            else:
                stars[repository] = int(node["stargazerCount"])
        remaining = (data.get("rateLimit") or {}).get("remaining")
    except (json.JSONDecodeError, AttributeError, KeyError, TypeError, ValueError) as exc:
        msg = f"Unexpected GitHub response: {exc}"
        raise ParseError(msg) from exc
    return stars, missing, remaining
