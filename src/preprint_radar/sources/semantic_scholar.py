"""Citation counts of arXiv papers, from Semantic Scholar.

Semantic Scholar counts citations to every version of a paper (the arXiv preprint and
its published version together), unlike OpenAlex, which undercounts published papers
(about 1.7 times fewer in median). Its batch endpoint takes 500 arXiv identifiers per
request. With an API key (``SEMANTIC_SCHOLAR_API_KEY``, free on request) it allows one
request per second, yet still refuses (429) about half of the batches at that pace: they
are tried again after a short wait. Anonymous requests share a small, busy pool and are
tried again after a long one.
"""

import json
import logging
import os
import time
from collections.abc import Callable, Iterable, Mapping
from itertools import batched

from preprint_radar.exceptions import FetchError, ParseError
from preprint_radar.http import HttpClient

logger = logging.getLogger(__name__)

S2_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
S2_BATCH_SIZE = 500
S2_API_KEY_ENV = "SEMANTIC_SCHOLAR_API_KEY"
S2_DELAY_SECONDS = 1.1
"""With a key: just under the one request per second a key allows (across all endpoints)."""
S2_ANONYMOUS_DELAY_SECONDS = 2.0
# A refused batch (429, or a 5xx: both mean "slow down") is tried again after a wait that
# doubles each time, up to a cap: 30 tries span about 25 minutes of refusals.
S2_BATCH_TRIES = 30
S2_RETRY_WAIT_SECONDS = 2.0
S2_ANONYMOUS_RETRY_WAIT_SECONDS = 20.0
S2_MAX_RETRY_WAIT_SECONDS = 60.0
# Refusals in a row from which each one is logged: a streak rather than the usual noise.
_REPORTED_TRY = 3


def api_key() -> str | None:
    """The Semantic Scholar API key from the environment, if any."""
    return os.environ.get(S2_API_KEY_ENV) or None


def fetch_citation_counts(
    client: HttpClient,
    arxiv_ids: Iterable[str],
    *,
    key: str | None = None,
    on_batch: Callable[[Mapping[str, int | None]], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, int | None]:
    """Citation counts of arXiv papers.

    Args:
        client: HTTP client for Semantic Scholar, rate-limited by the caller and making a
            single attempt per request: refused batches are tried again here.
        arxiv_ids: arXiv identifiers, without version.
        key: API key, sent as ``x-api-key``; ``None`` for anonymous requests.
        on_batch: Called with the counts of each batch as soon as it is fetched, so that
            the caller can save progress.
        sleep: Sleep function between tries of a refused batch, injectable for testing.

    Returns:
        The counts of the papers fetched (``None``: unknown to Semantic Scholar). If a
        batch keeps failing, the papers from it on are left out: callers check coverage.
    """
    headers = {"x-api-key": key} if key else None
    first_wait = S2_RETRY_WAIT_SECONDS if key else S2_ANONYMOUS_RETRY_WAIT_SECONDS
    counts: dict[str, int | None] = {}
    batches = refusals = 0
    for batch in batched(dict.fromkeys(arxiv_ids), S2_BATCH_SIZE, strict=False):
        batch_counts, refused = _fetch_batch(
            client, batch, headers=headers, sleep=sleep, first_wait=first_wait
        )
        refusals += refused
        if batch_counts is None:
            logger.warning("Semantic Scholar keeps refusing; stopping after %d papers", len(counts))
            break
        batches += 1
        counts.update(batch_counts)
        if on_batch is not None:
            on_batch(batch_counts)
        logger.info("%d citation counts fetched", len(counts))
    logger.info("%d batches fetched from Semantic Scholar, %d refused tries", batches, refusals)
    return counts


def parse_batch_response(text: str, arxiv_ids: tuple[str, ...]) -> dict[str, int | None]:
    """Match a batch response (one entry per requested id, ``null`` if unknown) to its ids.

    Raises:
        ParseError: If the response is not a list of that length.
    """
    try:
        items = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"Invalid Semantic Scholar response: {exc}"
        raise ParseError(msg) from exc
    if not isinstance(items, list) or len(items) != len(arxiv_ids):
        msg = "Semantic Scholar response does not match the requested papers"
        raise ParseError(msg)
    counts: dict[str, int | None] = {}
    for arxiv_id, item in zip(arxiv_ids, items, strict=True):
        count = item.get("citationCount") if isinstance(item, dict) else None
        counts[arxiv_id] = count if isinstance(count, int) else None
    return counts


def _fetch_batch(
    client: HttpClient,
    batch: tuple[str, ...],
    *,
    headers: Mapping[str, str] | None,
    sleep: Callable[[float], None],
    first_wait: float,
) -> tuple[dict[str, int | None] | None, int]:
    """Counts of one batch (``None`` if every try was refused), and the number of refusals."""
    for attempt in range(1, S2_BATCH_TRIES + 1):
        try:
            text = client.post_text(
                S2_BATCH_URL,
                params={"fields": "citationCount"},
                json={"ids": [f"ARXIV:{arxiv_id}" for arxiv_id in batch]},
                headers=headers,
            )
            return parse_batch_response(text, batch), attempt - 1
        except (FetchError, ParseError) as exc:
            level = logging.INFO if attempt >= _REPORTED_TRY else logging.DEBUG
            logger.log(level, "Semantic Scholar batch refused (try %d): %s", attempt, exc)
            if attempt < S2_BATCH_TRIES:
                sleep(min(first_wait * 2 ** (attempt - 1), S2_MAX_RETRY_WAIT_SECONDS))
    return None, S2_BATCH_TRIES
