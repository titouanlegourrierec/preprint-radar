"""Citation counts of arXiv papers, from Semantic Scholar.

Semantic Scholar counts citations to every version of a paper (the arXiv preprint and
its published version together), unlike OpenAlex, which undercounts published papers
(about 1.7 times fewer in median). Its batch endpoint takes 500 arXiv identifiers per
request. With an API key (``SEMANTIC_SCHOLAR_API_KEY``, free on request) it allows one
request per second, yet still refuses (429) about half of the batches at that pace: they
are tried again after a short wait. Anonymous requests share a small, busy pool and are
tried again after a long one. A batch whose answer is not one entry per paper asked for is
no refusal: the archive of 2026-10-11 tried one 30 times over 25 minutes, then left the
1,415 papers after it without a count. It is tried twice, then asked for in halves, down
to the paper Semantic Scholar cannot answer for, which alone is left out.

The same endpoint gives the published version of a paper (:func:`fetch_scholar_records`):
its DOI, its venue and its authors' ids. The year of the venue is read from the names of
the proceedings or the journal ("2022 IEEE/CVF Conference on ..."), its volume or an IEEE
DOI, never from ``publicationDate`` or ``year``, which are often the arXiv version's (a
paper of CVPR 2022 posted in 2021 has 2021).
"""

import json
import logging
import os
import re
import time
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from itertools import batched
from typing import Any

from preprint_radar.config import S2_API_KEY_ENV
from preprint_radar.console import Advance, no_progress
from preprint_radar.exceptions import FetchError, ParseError
from preprint_radar.http import HttpClient
from preprint_radar.models import ScholarRecord
from preprint_radar.venue import published_venue

logger = logging.getLogger(__name__)

S2_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
S2_SOURCE = "Semantic Scholar"
"""Name of the source, as written in ``citations.json``."""
S2_BATCH_SIZE = 500
S2_DELAY_SECONDS = 1.1
"""With a key: just under the one request per second a key allows (across all endpoints)."""
S2_ANONYMOUS_DELAY_SECONDS = 2.0
# A refused batch (429, or a 5xx: both mean "slow down") is tried again after a wait that
# doubles each time, up to a cap: 30 tries span about 25 minutes of refusals.
S2_BATCH_TRIES = 30
S2_RETRY_WAIT_SECONDS = 2.0
S2_ANONYMOUS_RETRY_WAIT_SECONDS = 20.0
S2_MAX_RETRY_WAIT_SECONDS = 60.0
# An invalid or revoked key gets these on every request: trying again only wastes the run.
S2_KEY_REJECTED = frozenset({401, 403})
# An answer that does not match its batch is tried that many times before the batch is
# halved; past that many such batches in a run (one bad paper in 500 takes about 10), the
# run stops, as for refusals.
S2_MISMATCH_TRIES = 2
S2_MAX_MISMATCHED_BATCHES = 50
# A few refusals in a row are routine, even with a key: only longer streaks are reported.
_REPORTED_STREAK = 5
# Progress is reported every that many batches (5,000 papers).
_PROGRESS_EVERY = 10
S2_COUNT_FIELDS = "citationCount"
# About 1 KB a paper, 500 KB a batch: answered in a few seconds, like a batch of counts.
S2_RECORD_FIELDS = "externalIds,venue,publicationVenue,journal,authors"
# arXiv's own DOIs (10.48550/arXiv.<id>) say nothing of a published version.
_ARXIV_DOI_PREFIX = "10.48550/"
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_BARE_YEAR_RE = re.compile(r"^\s*(?:19|20)\d{2}\s*$")
_PREPRINT_RE = re.compile(r"arxiv", re.IGNORECASE)
# IEEE DOIs hold the year of their proceedings: 10.1109/CVPR52688.2022.01234.
_IEEE_DOI_YEAR_RE = re.compile(r"^10\.1109/[^/.]+\.((?:19|20)\d{2})\.")


def api_key() -> str | None:
    """The Semantic Scholar API key from the environment, if any."""
    return os.environ.get(S2_API_KEY_ENV) or None


def fetch_citation_counts(
    client: HttpClient,
    arxiv_ids: Iterable[str],
    *,
    key: str | None = None,
    on_batch: Callable[[Mapping[str, int | None]], None] | None = None,
    max_seconds: float | None = None,
    progress: Advance = no_progress,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, int | None]:
    """Citation counts of arXiv papers.

    Args:
        client: HTTP client for Semantic Scholar, rate-limited by the caller and making a
            single attempt per request: refused batches are tried again here.
        arxiv_ids: arXiv identifiers, without version.
        key: API key, sent as ``x-api-key``; ``None`` for anonymous requests.
        on_batch: Called with the counts of each batch as soon as it is fetched, so that
            the caller can save progress.
        max_seconds: Time budget: past it, refused batches are not tried again, and the
            papers from the first of them on are left out. ``None``: no budget.
        progress: Told the papers of each batch fetched.
        sleep: Sleep function between tries of a refused batch, injectable for testing.
        clock: Monotonic clock for the time budget, injectable for testing.

    Returns:
        The counts of the papers fetched (``None``: unknown to Semantic Scholar). If a
        batch keeps failing, the papers from it on are left out: callers check coverage.

    Raises:
        FetchError: If Semantic Scholar rejects the API key (or, without one, the
            requests): no try would get through.
    """

    def fetched(batch: Mapping[str, int | None]) -> None:
        if on_batch is not None:
            on_batch(batch)
        progress(len(batch))

    return _fetch_all(
        client,
        arxiv_ids,
        _BatchKind("citation counts", S2_COUNT_FIELDS, parse_batch_response),
        key=key,
        on_batch=fetched,
        max_seconds=max_seconds,
        sleep=sleep,
        clock=clock,
    )


def fetch_scholar_records(
    client: HttpClient,
    arxiv_ids: Iterable[str],
    *,
    key: str | None = None,
    max_seconds: float | None = None,
    progress: Advance = no_progress,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, ScholarRecord | None]:
    """The DOI, published venue and author ids of arXiv papers, as Semantic Scholar knows them.

    Args and failures as :func:`fetch_citation_counts`.

    Returns:
        A record per paper fetched (``None``: unknown to Semantic Scholar); papers from a
        batch that keeps failing on are left out. The author ids are those of Semantic
        Scholar's author list, which the caller compares with the paper's.
    """
    return _fetch_all(
        client,
        arxiv_ids,
        _BatchKind("paper records", S2_RECORD_FIELDS, parse_records_response),
        key=key,
        on_batch=lambda batch: progress(len(batch)),
        max_seconds=max_seconds,
        sleep=sleep,
        clock=clock,
    )


@dataclass(frozen=True, slots=True)
class _BatchKind[T]:
    """What a batch asks for: its name in the log, the fields, and how to read the answer."""

    what: str
    fields: str
    parse: Callable[[str, tuple[str, ...]], dict[str, T | None]]


def _fetch_all[T](
    client: HttpClient,
    arxiv_ids: Iterable[str],
    kind: _BatchKind[T],
    *,
    key: str | None,
    on_batch: Callable[[Mapping[str, T | None]], object],
    max_seconds: float | None,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> dict[str, T | None]:
    headers = {"x-api-key": key} if key else None
    first_wait = S2_RETRY_WAIT_SECONDS if key else S2_ANONYMOUS_RETRY_WAIT_SECONDS
    deadline = None if max_seconds is None else clock() + max_seconds
    wanted = list(dict.fromkeys(arxiv_ids))
    found: dict[str, T | None] = {}
    batches = refusals = mismatched = 0
    pending = deque(batched(wanted, S2_BATCH_SIZE, strict=False))
    while pending:
        batch = pending.popleft()
        try:
            batch_found, refused = _fetch_batch(
                client,
                batch,
                kind,
                headers=headers,
                sleep=sleep,
                first_wait=first_wait,
                stop_waiting=(lambda wait: clock() + wait > deadline) if deadline is not None else None,
            )
        except ParseError as exc:
            mismatched += 1
            if mismatched > S2_MAX_MISMATCHED_BATCHES:
                logger.warning(
                    "Semantic Scholar keeps answering batches that do not match; stopping after %s papers",
                    f"{len(found):,}",
                )
                break
            if len(batch) == 1:
                logger.warning("Semantic Scholar cannot answer for %s, left out: %s", batch[0], exc)
                continue
            half = (len(batch) + 1) // 2
            logger.info(
                "A batch of %d papers got an answer that does not match it; asking in halves", len(batch)
            )
            pending.extendleft((batch[half:], batch[:half]))
            continue
        refusals += refused
        if batch_found is None:
            logger.warning("Semantic Scholar keeps refusing; stopping after %s papers", f"{len(found):,}")
            break
        batches += 1
        found.update(batch_found)
        on_batch(batch_found)
        if batches % _PROGRESS_EVERY == 0 or len(found) == len(wanted):
            logger.info(
                "%s of %s %s fetched (%.0f%%)",
                f"{len(found):,}",
                f"{len(wanted):,}",
                kind.what,
                100 * len(found) / len(wanted),
            )
    logger.info("%d batches fetched from Semantic Scholar, %d refused tries", batches, refusals)
    return found


def parse_batch_response(text: str, arxiv_ids: tuple[str, ...]) -> dict[str, int | None]:
    """Match a batch response (one entry per requested id, ``null`` if unknown) to its ids.

    Raises:
        ParseError: If the response is not a list of that length.
    """
    counts: dict[str, int | None] = {}
    for arxiv_id, item in zip(arxiv_ids, _batch_items(text, arxiv_ids), strict=True):
        count = item.get("citationCount") if item is not None else None
        counts[arxiv_id] = count if isinstance(count, int) else None
    return counts


def _batch_items(text: str, arxiv_ids: tuple[str, ...]) -> list[dict[str, Any] | None]:
    """The entries of a batch response, one per requested id (``None``: unknown).

    Raises:
        ParseError: If the response is not a list of that length.
    """
    try:
        items = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"Invalid Semantic Scholar response: {exc}"
        raise ParseError(msg) from exc
    if not isinstance(items, list) or len(items) != len(arxiv_ids):
        answer = f"{len(items)} entries" if isinstance(items, list) else " ".join(text.split())[:200]
        msg = f"Semantic Scholar response does not match the requested papers ({len(arxiv_ids)}): {answer}"
        raise ParseError(msg)
    return [item if isinstance(item, dict) else None for item in items]


def parse_records_response(text: str, arxiv_ids: tuple[str, ...]) -> dict[str, ScholarRecord | None]:
    """Match a batch response with record fields to its ids.

    Raises:
        ParseError: If the response is not a list of that length, or an entry not an object.
    """
    items = _batch_items(text, arxiv_ids)
    try:
        return {
            arxiv_id: _scholar_record(item) if item is not None else None
            for arxiv_id, item in zip(arxiv_ids, items, strict=True)
        }
    except (AttributeError, TypeError) as exc:
        msg = f"Unexpected Semantic Scholar record: {exc}"
        raise ParseError(msg) from exc


def _scholar_record(item: Mapping[str, Any]) -> ScholarRecord:
    external = item.get("externalIds") or {}
    doi = external.get("DOI") if isinstance(external.get("DOI"), str) else None
    if doi is not None and doi.lower().startswith(_ARXIV_DOI_PREFIX):
        doi = None
    journal = item.get("journal") or {}
    publication = item.get("publicationVenue") or {}
    venue_string = item.get("venue") if isinstance(item.get("venue"), str) else None
    name = publication.get("name") if isinstance(publication.get("name"), str) else None
    alternate = [text for text in publication.get("alternate_names") or [] if isinstance(text, str)]
    year = _venue_year(journal, venue_string, doi)
    authors = item.get("authors")
    listed = isinstance(authors, list) and bool(authors)
    return ScholarRecord(
        doi=doi,
        venue=published_venue(name, alternate, venue_string, year),
        author_ids=_author_field(authors, "authorId") if listed else None,
        author_names=_author_field(authors, "name") if listed else None,
    )


def _author_field(authors: list[Mapping[str, Any]], key: str) -> tuple[str | None, ...]:
    return tuple(author.get(key) if isinstance(author.get(key), str) else None for author in authors)


def _venue_year(journal: Mapping[str, Any], venue: str | None, doi: str | None) -> int | None:
    """The year of the published version, from its names, its volume or an IEEE DOI.

    In order: the journal's or proceedings' name ("2022 IEEE/CVF Conference on ..."), the
    venue string, the volume when it is a year ("2022"), then an IEEE DOI
    (10.1109/CVPR52688.2022.01234). A paper only known as a preprint has the journal
    "ArXiv" and the volume "abs/2006.05929", whose identifier is no year.
    """
    name = journal.get("name")
    names = [name if isinstance(name, str) and not _PREPRINT_RE.search(name) else None, venue]
    for text in names:
        if text is not None and (match := _YEAR_RE.search(text)):
            return int(match.group())
    volume = journal.get("volume")
    if isinstance(volume, str) and _BARE_YEAR_RE.match(volume):
        return int(volume.strip())
    if doi is not None and (match := _IEEE_DOI_YEAR_RE.match(doi)):
        return int(match.group(1))
    return None


def _fetch_batch[T](
    client: HttpClient,
    batch: tuple[str, ...],
    kind: _BatchKind[T],
    *,
    headers: Mapping[str, str] | None,
    sleep: Callable[[float], None],
    first_wait: float,
    stop_waiting: Callable[[float], bool] | None = None,
) -> tuple[dict[str, T | None] | None, int]:
    """What one batch gives (``None`` if every try was refused), and the number of refusals.

    ``stop_waiting`` tells, given the wait before the next try, whether to give up instead.

    Raises:
        FetchError: If the key (or, without one, the request) is rejected.
        ParseError: If ``S2_MISMATCH_TRIES`` answers did not match the batch.
    """
    error: FetchError | ParseError | None = None
    mismatches = 0
    for attempt in range(1, S2_BATCH_TRIES + 1):
        try:
            text = client.post_text(
                S2_BATCH_URL,
                params={"fields": kind.fields},
                json={"ids": [f"ARXIV:{arxiv_id}" for arxiv_id in batch]},
                headers=headers,
            )
            return kind.parse(text, batch), attempt - 1
        except (FetchError, ParseError) as exc:
            if isinstance(exc, FetchError) and exc.status in S2_KEY_REJECTED:
                rejected = "the API key" if headers else "the request"
                msg = f"Semantic Scholar rejected {rejected} (HTTP {exc.status}): {exc}"
                raise FetchError(msg, status=exc.status) from exc
            if isinstance(exc, ParseError):
                mismatches += 1
                if mismatches == S2_MISMATCH_TRIES:
                    raise
            error = exc
            logger.debug("Semantic Scholar batch refused (try %d): %s", attempt, exc)
            if attempt < S2_BATCH_TRIES:
                wait = min(first_wait * 2 ** (attempt - 1), S2_MAX_RETRY_WAIT_SECONDS)
                if stop_waiting is not None and stop_waiting(wait):
                    logger.warning(
                        "Semantic Scholar refused a batch %d times; out of time, stopping", attempt
                    )
                    return None, attempt
                if attempt % _REPORTED_STREAK == 0:
                    logger.info(
                        "Semantic Scholar refused a batch %d times in a row; next try in %.0f s",
                        attempt,
                        wait,
                    )
                sleep(wait)
    logger.warning("Semantic Scholar refused a batch %d times, the last: %s", S2_BATCH_TRIES, error)
    return None, S2_BATCH_TRIES
