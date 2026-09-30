import httpx
import pytest
from tests.conftest import FIXTURES_DIR

from preprint_radar.exceptions import ParseError
from preprint_radar.http import HttpClient
from preprint_radar.institutions import match_institutions, parse_ror_response

ROR_DIR = FIXTURES_DIR / "ror"


def _response(name: str) -> str:
    return (ROR_DIR / f"{name}.json").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("fixture", "affiliation", "expected"),
    [
        pytest.param(
            "peking",
            "School of Computer Science, Peking University, Beijing, China",
            "Peking University",
            id="department-of-a-university",
        ),
        pytest.param(
            "hkust_gz",
            "The Hong Kong University of Science and Technology (Guangzhou)",
            "Hong Kong University of Science and Technology (Guangzhou)",
            id="leading-the-dropped-campus-kept",
        ),
        pytest.param("deepmind", "Google DeepMind", "Google DeepMind", id="company-country-dropped"),
        pytest.param("tencent_arc", "ARC Lab, Tencent IEG", None, id="chosen-on-one-word"),
        pytest.param(
            "imperial_gate",
            "Imperial College London, 180 Queen\u2019s Gate, London, SW7 2AZ, United Kingdom",
            None,
            id="chosen-on-the-street-name",
        ),
        pytest.param("meta", "Meta AI", None, id="nothing-chosen"),
    ],
)
def test_parse_ror_response(fixture: str, affiliation: str, expected: str | None) -> None:
    assert parse_ror_response(_response(fixture), affiliation) == expected


@pytest.mark.parametrize("text", ["not json", "{}", '{"items": [42]}'])
def test_parse_ror_response_rejects_unexpected_json(text: str) -> None:
    with pytest.raises(ParseError):
        parse_ror_response(text, "MIT")


def _client(requested: list[str]) -> HttpClient:
    def handle(request: httpx.Request) -> httpx.Response:
        affiliation = request.url.params["affiliation"]
        requested.append(affiliation)
        if affiliation == "Unreachable":
            return httpx.Response(503)
        return httpx.Response(200, text=_response("peking" if "Peking" in affiliation else "meta"))

    return HttpClient(transport=httpx.MockTransport(handle), max_attempts=1)


def test_match_institutions_looks_each_string_up_once() -> None:
    requested: list[str] = []
    with _client(requested) as client:
        matches = match_institutions(
            client, ["Peking University, China", "Meta AI", "Peking University, China"]
        )

    assert requested == ["Peking University, China", "Meta AI"]
    assert matches == {"Peking University, China": "Peking University", "Meta AI": None}


def test_match_institutions_stops_at_the_limit_or_when_ror_is_down() -> None:
    requested: list[str] = []
    with _client(requested) as client:
        limited = match_institutions(client, ["Meta AI", "Peking University"], limit=1)
        down = match_institutions(client, ["Unreachable", "Meta AI"])

    assert limited == {"Meta AI": None}
    assert down == {}
    assert requested == ["Meta AI", "Unreachable"]
