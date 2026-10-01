import json
import logging

import httpx
import pytest

from preprint_radar.exceptions import FetchError, ParseError
from preprint_radar.http import HttpClient
from preprint_radar.sources.semantic_scholar import (
    S2_BATCH_SIZE,
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
    # Only streaks are reported, without the routine refusals.
    streak = f"refused a batch 5 times in a row; next try in {min(first_waits[0] * 16, 60):.0f} s"
    assert streak in caplog.text
    assert "4 times in a row" not in caplog.text
    assert "refused a batch 30 times, the last: HTTP 503" in caplog.text


def test_fetch_citation_counts_without_progress_callback(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    answer = httpx.Response(200, text='[{"citationCount": 3}]')
    with HttpClient(transport=httpx.MockTransport(lambda _: answer), max_attempts=1) as client:
        assert fetch_citation_counts(client, ["2609.1"]) == {"2609.1": 3}

    assert "1 of 1 citation counts fetched (100%)" in caplog.text


def test_fetch_citation_counts_reports_progress_every_ten_batches(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"citationCount": 1}] * len(json.loads(request.content)["ids"]))

    ids = [f"2609.{number:05d}" for number in range(11 * S2_BATCH_SIZE)]
    with HttpClient(transport=httpx.MockTransport(handle), max_attempts=1) as client:
        assert len(fetch_citation_counts(client, ids)) == len(ids)

    progress = [line for line in caplog.text.splitlines() if "citation counts fetched" in line]
    assert len(progress) == 2
    assert progress[0].endswith("5,000 of 5,500 citation counts fetched (91%)")


def test_api_key_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    assert api_key() is None
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "")
    assert api_key() is None
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "test-key")
    assert api_key() == "test-key"


@pytest.mark.parametrize(
    ("key", "status", "rejected"),
    [("secret", 403, "the API key"), (None, 401, "the request")],
    ids=["invalid-key", "anonymous"],
)
def test_a_rejected_key_stops_at_once(key: str | None, status: int, rejected: str) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status)

    sleeps: list[float] = []
    with (
        HttpClient(transport=httpx.MockTransport(handle), max_attempts=1) as client,
        pytest.raises(
            FetchError, match=f"Semantic Scholar rejected {rejected} \\(HTTP {status}\\)"
        ) as raised,
    ):
        fetch_citation_counts(client, ["2609.1"], key=key, sleep=sleeps.append)

    assert raised.value.status == status
    assert len(requests) == 1
    assert sleeps == []


def test_refusals_are_given_up_at_the_end_of_the_time_budget(caplog: pytest.LogCaptureFixture) -> None:
    responses = iter(
        [httpx.Response(200, text=json.dumps([{"citationCount": 1}] * S2_BATCH_SIZE))]
        + [httpx.Response(429)] * S2_BATCH_TRIES
    )
    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    with HttpClient(transport=httpx.MockTransport(lambda _: next(responses)), max_attempts=1) as client:
        counts = fetch_citation_counts(
            client,
            [f"2609.{i}" for i in range(2 * S2_BATCH_SIZE)],
            key="secret",
            max_seconds=10,
            sleep=sleep,
            clock=lambda: now[0],
        )

    # The first batch, then tries after 2, 4 s: the next wait (8 s) would end past 10 s.
    assert len(counts) == S2_BATCH_SIZE
    assert now[0] == 6
    assert "refused a batch 3 times; out of time, stopping" in caplog.text
