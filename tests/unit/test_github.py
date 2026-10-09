import json

import httpx
import pytest

from preprint_radar.exceptions import FetchError, ParseError
from preprint_radar.http import HttpClient
from preprint_radar.sources.github import GITHUB_BATCH_SIZE, fetch_stars, parse_stars


def _answer(data: dict[str, object], errors: list[dict[str, object]] | None = None) -> str:
    return json.dumps({"data": data, **({"errors": errors} if errors else {})})


def test_parse_stars_tells_the_repositories_not_found() -> None:
    text = _answer(
        {"rateLimit": {"remaining": 998}, "repo0": {"stargazerCount": 1234}, "repo1": None},
        [{"type": "NOT_FOUND", "path": ["repo1"], "message": "Could not resolve to a Repository"}],
    )

    assert parse_stars(text, ("lab/fast-net", "lab/gone")) == ({"lab/fast-net": 1234}, {"lab/gone"}, 998)


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        '{"data": {"repo0": {"stars": 3}}}',
        _answer({}, [{"type": "RATE_LIMITED", "message": "API rate limit exceeded"}]),
        _answer({}, [{"message": "Parse error on bad query"}]),
    ],
)
def test_parse_stars_refuses_a_failed_query(text: str) -> None:
    with pytest.raises(ParseError):
        parse_stars(text, ("lab/fast-net",))


def test_fetch_stars_asks_100_repositories_a_query() -> None:
    queries: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "bearer test-token"
        query = json.loads(request.content)["query"]
        queries.append(query)
        if len(queries) == 2:
            return httpx.Response(502)  # left for next time
        count = query.count("repository(")
        return httpx.Response(200, text=_answer({f"repo{i}": {"stargazerCount": i} for i in range(count)}))

    repositories = [f"lab/net-{number:03d}" for number in range(GITHUB_BATCH_SIZE + 1)]
    done: list[int] = []
    with HttpClient(transport=httpx.MockTransport(handle), max_attempts=1) as client:
        found = fetch_stars(client, [*repositories, "lab/net-000"], token="test-token", progress=done.append)

    assert done == [100, 1]  # the failed query too

    assert len(queries) == 2
    assert 'repo0: repository(owner: "lab", name: "net-000") { stargazerCount }' in queries[0]
    assert "rateLimit { remaining }" in queries[0]
    # The first batch answered; the second failed: neither stars nor missing.
    assert found.stars == {repository: number for number, repository in enumerate(repositories[:100])}
    assert found.missing == set()


def test_fetch_stars_fails_on_a_rejected_token() -> None:
    def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    with (
        HttpClient(transport=httpx.MockTransport(handle), max_attempts=1) as client,
        pytest.raises(FetchError, match="GitHub rejected the token"),
    ):
        fetch_stars(client, ["lab/fast-net"], token="bad")
