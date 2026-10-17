"""The stars of the repositories papers link, from GitHub's GraphQL API (PROD-18).

The REST API answers one repository per request, 60 an hour without a token: too few for
the 7,500 repositories of the stored papers. GraphQL takes 100 in one query, as aliases of
one ``repository`` field each, for one point of a token's 5,000 an hour (1,000 for a
workflow's ``GITHUB_TOKEN``, enough too); it needs a token, though one that may read
nothing but public data. A repository that was deleted, renamed away or never published
("code coming soon") comes back as a ``NOT_FOUND`` error for its alias, the others' stars
with it.

GitHub's secondary limits also cap the CPU time its GraphQL queries take, 60 s a minute,
and a query of 100 repositories takes about 2 s of it: at one a second, the workflow's run
of 2026-10-11 was refused after 30 queries, and 4,698 papers kept the week before's stars.
Queries go one every 3 s, and one refused for a limit (403, or 429) is asked again after
the wait GitHub asks for.
"""

import json
import logging
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from itertools import batched
from typing import Any

from preprint_radar.console import Advance, no_progress
from preprint_radar.exceptions import FetchError, ParseError
from preprint_radar.http import HttpClient

logger = logging.getLogger(__name__)

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
GITHUB_BATCH_SIZE = 100
# One query every 3 s keeps its CPU time (about 2 s each) under GitHub's 60 s a minute.
GITHUB_DELAY_SECONDS = 3.0
# A bad or revoked token gets these on every request: trying again only wastes the run.
GITHUB_TOKEN_REJECTED = frozenset({401})
# A secondary limit: wait for its Retry-After, else a minute, doubled at each refusal
# (GitHub's own advice), then stop asking: the rest keep last week's stars.
GITHUB_LIMITED = frozenset({403, 429})
GITHUB_LIMIT_WAIT_SECONDS = 60.0
GITHUB_LIMIT_TRIES = 3
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


class _LimitedError(FetchError):
    """GitHub kept refusing a query for its limits."""


def fetch_stars(
    client: HttpClient,
    repositories: Iterable[str],
    *,
    token: str,
    progress: Advance = no_progress,
    sleep: Callable[[float], None] = time.sleep,
) -> Stars:
    """The stars of GitHub repositories, 100 per query.

    Args:
        client: HTTP client for GitHub.
        repositories: ``owner/name`` of each.
        token: A GitHub token; any, even one that reads only public data.
        progress: Told the repositories of each query, answered or not.
        sleep: Sleep function, for the waits GitHub's limits ask; injectable for testing.

    Returns:
        Their stars, and those GitHub does not know.

    Raises:
        FetchError: If GitHub rejects the token.
    """
    found = Stars()
    headers = {"Authorization": f"bearer {token}"}
    wanted = sorted(set(repositories))
    asked = 0
    for batch in batched(wanted, GITHUB_BATCH_SIZE, strict=False):
        try:
            text = _ask(client, batch, headers=headers, sleep=sleep)
            stars, missing, remaining = parse_stars(text, batch)
        except _LimitedError as exc:
            left = len(wanted) - asked
            logger.warning(
                "GitHub kept limiting the queries; %s repositories left unasked: %s", f"{left:,}", exc
            )
            progress(left)
            break
        except (FetchError, ParseError) as exc:
            if isinstance(exc, FetchError) and exc.status in GITHUB_TOKEN_REJECTED:
                msg = f"GitHub rejected the token (HTTP {exc.status}): {exc}"
                raise FetchError(msg, status=exc.status) from exc
            # Neither stars nor missing: asked again next time.
            logger.warning("GitHub lookup of %d repositories failed: %s", len(batch), exc)
            stars, missing, remaining = {}, set(), None
        asked += len(batch)
        progress(len(batch))
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


def _ask(
    client: HttpClient, batch: tuple[str, ...], *, headers: Mapping[str, str], sleep: Callable[[float], None]
) -> str:
    """GitHub's answer to one query, asked again while its limits refuse it.

    Raises:
        _LimitedError: If its limits refused it ``GITHUB_LIMIT_TRIES`` times.
        FetchError: If it failed otherwise.
    """
    wait = GITHUB_LIMIT_WAIT_SECONDS
    attempt = 1
    while True:
        try:
            return client.post_text(GITHUB_GRAPHQL_URL, json={"query": _query(batch)}, headers=headers)
        except FetchError as exc:
            if exc.status not in GITHUB_LIMITED:
                raise
            if attempt == GITHUB_LIMIT_TRIES:
                raise _LimitedError(str(exc), status=exc.status) from exc
            delay = exc.retry_after or wait
            logger.info("GitHub limits the queries (HTTP %d); next try in %.0f s", exc.status, delay)
            sleep(delay)
            wait *= 2
            attempt += 1


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

    Args:
        text: GraphQL's response.
        batch: The repositories asked for, as ``owner/name``, in the query's order.

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
