import httpx
import pytest

from preprint_radar.exceptions import FetchError, NotFoundError
from preprint_radar.http import DEFAULT_USER_AGENT, HttpClient, RateLimiter, build_user_agent


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_get_text_sends_params_and_user_agent() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="hello")

    with HttpClient(transport=httpx.MockTransport(handler)) as client:
        assert client.get_text("https://arxiv.org/list/cs.CV/recent", params={"show": 10}) == "hello"

    [request] = requests
    assert request.url.params["show"] == "10"
    assert request.headers["User-Agent"] == DEFAULT_USER_AGENT
    # export.arxiv.org rejects httpx's default header order (User-Agent last).
    names = [name.lower() for name, _ in request.headers.raw]
    assert names.index(b"user-agent") < names.index(b"accept")


def test_404_raises_not_found() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(404))
    with HttpClient(transport=transport) as client, pytest.raises(NotFoundError):
        client.get_text("https://arxiv.org/html/0000.00000")


def test_client_errors_are_not_retried() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(400)

    with HttpClient(transport=httpx.MockTransport(handler)) as client, pytest.raises(FetchError, match="400"):
        client.get_text("https://arxiv.org/")
    assert len(calls) == 1


def test_transient_errors_are_retried_with_backoff() -> None:
    responses = iter([httpx.Response(429), httpx.Response(503), httpx.Response(200, text="finally")])
    sleeps: list[float] = []
    transport = httpx.MockTransport(lambda _: next(responses))

    with HttpClient(transport=transport, backoff=10.0, sleep=sleeps.append) as client:
        assert client.get_text("https://export.arxiv.org/api/query") == "finally"
    assert sleeps == [10.0, 20.0]


def test_retry_after_header_is_honored() -> None:
    responses = iter([httpx.Response(429, headers={"Retry-After": "42"}), httpx.Response(200)])
    sleeps: list[float] = []
    transport = httpx.MockTransport(lambda _: next(responses))

    with HttpClient(transport=transport, sleep=sleeps.append) as client:
        client.get_text("https://arxiv.org/")
    assert sleeps == [42.0]


def test_gives_up_after_max_attempts() -> None:
    sleeps: list[float] = []
    transport = httpx.MockTransport(lambda _: httpx.Response(503))

    with (
        HttpClient(transport=transport, max_attempts=3, sleep=sleeps.append) as client,
        pytest.raises(FetchError, match="503"),
    ):
        client.get_text("https://arxiv.org/")
    assert len(sleeps) == 2


def test_network_errors_raise_fetch_error_once_retries_are_exhausted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    sleeps: list[float] = []
    with (
        HttpClient(transport=httpx.MockTransport(handler), max_attempts=3, sleep=sleeps.append) as client,
        pytest.raises(FetchError, match="boom"),
    ):
        client.get_text("https://arxiv.org/")
    assert len(sleeps) == 2


def test_other_request_errors_are_not_retried() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TooManyRedirects("loop", request=request)

    sleeps: list[float] = []
    with (
        HttpClient(transport=httpx.MockTransport(handler), max_attempts=3, sleep=sleeps.append) as client,
        pytest.raises(FetchError, match="loop"),
    ):
        client.get_text("https://arxiv.org/")
    assert sleeps == []


def test_errors_quote_the_start_of_a_json_body() -> None:
    message = {"message": "Too Many Requests. Please wait and try again or apply for a key."}
    responses = {"/json": httpx.Response(429, json=message), "/html": httpx.Response(429, text="<p>busy</p>")}
    transport = httpx.MockTransport(lambda request: responses[request.url.path])

    with HttpClient(transport=transport, max_attempts=1) as client:
        with pytest.raises(FetchError, match=r"HTTP 429 for .*/json: .*apply for a key"):
            client.get_text("https://api.semanticscholar.org/json")
        with pytest.raises(FetchError, match=r"HTTP 429 for https://api\.semanticscholar\.org/html$"):
            client.get_text("https://api.semanticscholar.org/html")


def test_at_least_one_attempt() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        HttpClient(max_attempts=0)


def test_timeouts_are_retried() -> None:
    calls = iter([httpx.ReadTimeout("slow"), httpx.Response(200, text="late")])

    def handler(request: httpx.Request) -> httpx.Response:
        outcome = next(calls)
        if isinstance(outcome, Exception):
            raise httpx.ReadTimeout(str(outcome), request=request)
        return outcome

    sleeps: list[float] = []
    with HttpClient(transport=httpx.MockTransport(handler), backoff=5.0, sleep=sleeps.append) as client:
        assert client.get_text("https://oaipmh.arxiv.org/oai") == "late"
    assert sleeps == [5.0]


def test_post_text_sends_json_and_retries() -> None:
    bodies: list[bytes] = []
    responses = iter([httpx.Response(429), httpx.Response(200, text="[]")])

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        bodies.append(request.content)
        return next(responses)

    sleeps: list[float] = []
    with HttpClient(transport=httpx.MockTransport(handler), sleep=sleeps.append) as client:
        text = client.post_text("https://api.example.org/batch", json={"ids": ["a"]}, params={"f": "x"})

    assert text == "[]"
    assert bodies == [b'{"ids":["a"]}', b'{"ids":["a"]}']
    assert len(sleeps) == 1


def test_rate_limiter_spaces_calls() -> None:
    clock = FakeClock()
    limiter = RateLimiter(15.0, clock=clock.time, sleep=clock.sleep)

    limiter.wait()  # first call is immediate
    clock.now += 5.0
    limiter.wait()  # 10 s left to wait
    limiter.wait()  # full interval

    assert clock.sleeps == [10.0, 15.0]


def test_client_uses_rate_limiter() -> None:
    clock = FakeClock()
    limiter = RateLimiter(3.0, clock=clock.time, sleep=clock.sleep)
    transport = httpx.MockTransport(lambda _: httpx.Response(200))

    with HttpClient(transport=transport, rate_limiter=limiter) as client:
        client.get_text("https://arxiv.org/")
        client.get_text("https://arxiv.org/")

    assert clock.sleeps == [3.0]


def test_build_user_agent() -> None:
    assert build_user_agent() == DEFAULT_USER_AGENT
    assert build_user_agent("me@example.org") == f"{DEFAULT_USER_AGENT} (me@example.org)"
