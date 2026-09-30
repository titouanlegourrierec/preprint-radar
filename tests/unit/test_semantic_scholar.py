import logging

import httpx
import pytest

from preprint_radar.exceptions import ParseError
from preprint_radar.http import HttpClient
from preprint_radar.sources.semantic_scholar import (
    S2_BATCH_TRIES,
    S2_RETRY_WAIT_SECONDS,
    api_key,
    fetch_citation_counts,
    parse_batch_response,
)


def test_parse_batch_response() -> None:
    text = '[{"paperId": "x", "citationCount": 12}, null, {"paperId": "y"}]'

    assert parse_batch_response(text, ("1", "2", "3")) == {"1": 12, "2": None, "3": None}
    with pytest.raises(ParseError):
        parse_batch_response("[]", ("1",))
    with pytest.raises(ParseError):
        parse_batch_response("oops", ("1",))


def test_fetch_citation_counts_sends_the_key_and_retries_refusals() -> None:
    requests: list[httpx.Request] = []
    responses = iter([httpx.Response(429), httpx.Response(200, text='[{"citationCount": 7}, null]')])

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return next(responses)

    sleeps: list[float] = []
    batches: list[dict[str, int | None]] = []
    with HttpClient(transport=httpx.MockTransport(handle), max_attempts=1) as client:
        counts = fetch_citation_counts(
            client,
            ["2609.1", "2609.2", "2609.1"],
            key="secret",
            on_batch=lambda b: batches.append(dict(b)),
            sleep=sleeps.append,
        )

    assert counts == {"2609.1": 7, "2609.2": None}
    assert batches == [counts]
    assert sleeps == [S2_RETRY_WAIT_SECONDS]  # a short wait with a key
    assert requests[-1].headers["x-api-key"] == "secret"
    assert requests[-1].url.params["fields"] == "citationCount"
    assert b'"ARXIV:2609.1"' in requests[-1].content


@pytest.mark.parametrize(
    ("key", "first_waits"),
    [(None, [20.0, 40.0, 60.0, 60.0]), ("secret", [2.0, 4.0, 8.0, 16.0, 32.0, 60.0])],
    ids=["anonymous", "with-a-key"],
)
def test_fetch_citation_counts_waits_longer_and_longer_then_gives_up(
    key: str | None, first_waits: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    sleeps: list[float] = []
    with HttpClient(transport=httpx.MockTransport(lambda _: httpx.Response(503)), max_attempts=1) as client:
        counts = fetch_citation_counts(client, ["2609.1"], key=key, sleep=sleeps.append)

    assert counts == {}
    assert sleeps[: len(first_waits)] == first_waits
    assert len(sleeps) == S2_BATCH_TRIES - 1
    assert "0 batches fetched from Semantic Scholar, 30 refused tries" in caplog.text


def test_fetch_citation_counts_without_progress_callback() -> None:
    answer = httpx.Response(200, text='[{"citationCount": 3}]')
    with HttpClient(transport=httpx.MockTransport(lambda _: answer), max_attempts=1) as client:
        assert fetch_citation_counts(client, ["2609.1"]) == {"2609.1": 3}


def test_api_key_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    assert api_key() is None
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "")
    assert api_key() is None
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "test-key")
    assert api_key() == "test-key"
