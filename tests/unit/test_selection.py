from datetime import date

import httpx
import pytest

from preprint_radar.citations import api_key, fetch_citation_counts, parse_batch_response
from preprint_radar.exceptions import ParseError
from preprint_radar.http import HttpClient
from preprint_radar.selection import Candidate, citation_rate, is_recent, select_archive

TODAY = date(2026, 9, 30)


def _old(arxiv_id: str, citations: int | None, years: int = 4) -> Candidate:
    return Candidate(arxiv_id, date(TODAY.year - years, TODAY.month, 1), citations)


def test_citation_rate_counts_at_least_one_year() -> None:
    assert citation_rate(40, date(2022, 9, 30), TODAY) == pytest.approx(10, rel=0.01)
    assert citation_rate(40, date(2026, 3, 1), TODAY) == 40
    assert citation_rate(None, date(2020, 1, 1), TODAY) == 0


def test_recent_papers_are_not_candidates() -> None:
    assert is_recent(date(2026, 1, 1), TODAY)
    assert not is_recent(date(2025, 9, 1), TODAY)
    selection = select_archive(
        [Candidate("2608.00001", date(2026, 8, 1), 500)], set(), budget=10, today=TODAY
    )

    assert selection.keep == frozenset()


def test_the_budget_keeps_the_best_rates_whatever_the_age() -> None:
    candidates = [
        _old("1512.00001", 1000, years=10),  # 100/year
        _old("2209.00001", 240, years=4),  # 60/year
        _old("1805.00001", 300, years=8),  # 37.5/year
        _old("2309.00001", 0),
        _old("2209.00002", None),
    ]

    selection = select_archive(candidates, set(), budget=2, today=TODAY)

    assert selection.keep == {"1512.00001", "2209.00001"}
    assert selection.entered == selection.keep
    assert selection.threshold == pytest.approx(60, rel=0.05)


def test_never_cited_papers_stay_out_even_under_budget() -> None:
    selection = select_archive(
        [_old("2309.00001", 0), _old("2209.00002", None)], set(), budget=10, today=TODAY
    )

    assert selection.keep == frozenset()


def test_archived_papers_stay_within_the_margin() -> None:
    # Ranks: a (100), b (90), c (80), d (70); budget 2, margin 1.5: stay while rank < 3.
    candidates = [_old("a", 400), _old("b", 360), _old("c", 320), _old("d", 280)]

    selection = select_archive(candidates, {"c", "d"}, budget=2, today=TODAY, margin=1.5)

    assert selection.keep == {"a", "b", "c"}
    assert selection.entered == {"a", "b"}
    assert selection.left == {"d"}


def test_ties_are_broken_by_identifier() -> None:
    selection = select_archive([_old("b", 100), _old("a", 100)], set(), budget=1, today=TODAY)

    assert selection.keep == {"a"}


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
    assert len(sleeps) == 1
    assert requests[-1].headers["x-api-key"] == "secret"
    assert requests[-1].url.params["fields"] == "citationCount"
    assert b'"ARXIV:2609.1"' in requests[-1].content


def test_fetch_citation_counts_gives_up_on_a_batch_that_keeps_failing() -> None:
    with HttpClient(transport=httpx.MockTransport(lambda _: httpx.Response(503)), max_attempts=1) as client:
        counts = fetch_citation_counts(client, ["2609.1"], sleep=lambda _: None)

    assert counts == {}


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
