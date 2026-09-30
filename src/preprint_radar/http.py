"""Polite, rate-limited HTTP access to arXiv and the other services the pipeline uses."""

import logging
import time
from collections.abc import Callable, Mapping
from types import TracebackType
from typing import Self

import httpx

from preprint_radar import __version__
from preprint_radar.exceptions import FetchError, NotFoundError

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = f"preprint-radar/{__version__}"
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_BACKOFF_SECONDS = 10.0
CONNECT_RETRIES = 3
MAX_RETRY_AFTER_SECONDS = 300.0

# 406 is included because export.arxiv.org's firewall also returns it intermittently.
RETRYABLE_STATUS_CODES = frozenset({406, 429, 500, 502, 503, 504})

ARXIV_CRAWL_DELAY_SECONDS = 15.0
"""``Crawl-delay`` requested by https://arxiv.org/robots.txt."""

ARXIV_API_DELAY_SECONDS = 4.0
"""Delay between API calls; the terms of use ask for at least 3 seconds, with some margin."""


def build_user_agent(contact: str | None = None) -> str:
    """Build the ``User-Agent`` header, optionally with a contact address.

    arXiv asks automated clients to identify themselves so they can be reached.

    Args:
        contact: E-mail address or URL of the person running the tool.

    Returns:
        The header value.
    """
    return f"{DEFAULT_USER_AGENT} ({contact})" if contact else DEFAULT_USER_AGENT


class RateLimiter:
    """Enforce a minimum interval between consecutive calls to :meth:`wait`."""

    def __init__(
        self,
        min_interval: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Create a rate limiter.

        Args:
            min_interval: Minimum number of seconds between two calls.
            clock: Monotonic clock, injectable for testing.
            sleep: Sleep function, injectable for testing.
        """
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last_call: float | None = None

    def wait(self) -> None:
        """Block until the next call is allowed, then record it."""
        if self._last_call is not None:
            remaining = self._last_call + self.min_interval - self._clock()
            if remaining > 0:
                logger.debug("Rate limiting: sleeping %.1fs", remaining)
                self._sleep(remaining)
        self._last_call = self._clock()


class HttpClient:
    """Thin wrapper around :class:`httpx.Client` with rate limiting, retries and error mapping.

    Use it as a context manager so that the underlying connection pool is closed::

        with HttpClient(min_interval=ARXIV_CRAWL_DELAY_SECONDS) as client:
            html = client.get_text("https://arxiv.org/list/cs.CV/recent")
    """

    def __init__(
        self,
        *,
        min_interval: float = 0.0,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff: float = DEFAULT_BACKOFF_SECONDS,
        transport: httpx.BaseTransport | None = None,
        rate_limiter: RateLimiter | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Create a client.

        Args:
            min_interval: Minimum number of seconds between two requests.
            user_agent: ``User-Agent`` header sent with every request.
            timeout: Request timeout, in seconds.
            max_attempts: Attempts per request when the server signals a transient failure.
            backoff: Delay before the first retry, doubled after each attempt.
            transport: Custom transport, mainly useful for testing.
            rate_limiter: Custom rate limiter; overrides ``min_interval``.
            sleep: Sleep function used between retries, injectable for testing.
        """
        self._rate_limiter = rate_limiter or RateLimiter(min_interval)
        self._max_attempts = max_attempts
        self._backoff = backoff
        self._sleep = sleep
        self._http = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            transport=transport or httpx.HTTPTransport(retries=CONNECT_RETRIES),
        )
        # Replace (rather than extend) httpx's default headers: export.arxiv.org's firewall
        # rejects long queries with an empty "406 Not Acceptable" for httpx's default header
        # set and order, but accepts this curl-like one.
        self._http.headers = httpx.Headers([("User-Agent", user_agent), ("Accept", "*/*")])

    def __enter__(self) -> Self:
        """Enter the runtime context."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the client when leaving the runtime context."""
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._http.close()

    def get_text(self, url: str, *, params: Mapping[str, str | int] | None = None) -> str:
        """Send a ``GET`` request and return the response body.

        Transient failures (throttling, server errors, timeouts, dropped connections) are
        retried with exponential backoff.

        Args:
            url: Absolute URL.
            params: Query-string parameters.

        Returns:
            The decoded response body.

        Raises:
            NotFoundError: If the server answers ``404 Not Found``.
            FetchError: For any other network or HTTP error, once retries are exhausted.
        """
        return self._request("GET", url, params=params)

    def post_text(
        self,
        url: str,
        *,
        json: object,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        """Send a ``POST`` request with a JSON body and return the response body.

        Rate limiting, retries and errors are the same as for :meth:`get_text`.

        Args:
            url: Absolute URL.
            json: Body, serialized as JSON.
            params: Query-string parameters.
            headers: Extra headers for this request (e.g. an API key).

        Returns:
            The decoded response body.

        Raises:
            NotFoundError: If the server answers ``404 Not Found``.
            FetchError: For any other network or HTTP error, once retries are exhausted.
        """
        return self._request("POST", url, params=params, json=json, headers=headers)

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str | int] | None = None,
        json: object = None,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        delay = self._backoff
        for attempt in range(1, self._max_attempts + 1):
            self._rate_limiter.wait()
            logger.debug("%s %s %s (attempt %d)", method, url, dict(params or {}), attempt)
            try:
                response = self._http.request(method, url, params=params, json=json, headers=headers)
            except httpx.TransportError as exc:
                # Timeouts and dropped connections are as transient as a 503.
                if attempt == self._max_attempts:
                    raise FetchError(f"Request to {url} failed: {exc}") from exc
                logger.warning("%s for %s; retrying in %.0fs", type(exc).__name__, url, delay)
                self._sleep(delay)
                delay *= 2
                continue
            except httpx.HTTPError as exc:
                raise FetchError(f"Request to {url} failed: {exc}") from exc

            status = response.status_code
            if status == httpx.codes.NOT_FOUND:
                raise NotFoundError(f"Not found: {response.url}")
            if status not in RETRYABLE_STATUS_CODES or attempt == self._max_attempts:
                break
            wait = _retry_after(response) or delay
            logger.warning("HTTP %d for %s; retrying in %.0fs", status, response.url, wait)
            self._sleep(wait)
            delay *= 2

        if response.is_error:
            raise FetchError(f"HTTP {response.status_code} for {response.url}")
        return response.text


def _retry_after(response: httpx.Response) -> float | None:
    """Return the delay requested by a numeric ``Retry-After`` header, capped."""
    value = response.headers.get("Retry-After", "")
    return min(float(value), MAX_RETRY_AFTER_SECONDS) if value.isdigit() else None
