import json

import httpx
import pytest
from tests.conftest import FIXTURES_DIR

from preprint_radar.exceptions import ParseError
from preprint_radar.http import HttpClient
from preprint_radar.sources.ror import match_institution, match_institutions, parse_ror_response

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


@pytest.mark.parametrize(
    "organization",
    [
        pytest.param({"names": "Massachusetts Institute of Technology"}, id="names-not-a-list"),
        pytest.param(
            {"names": [42, {"value": "Massachusetts Institute of Technology", "types": ["label"]}]},
            id="no-display-name",
        ),
        pytest.param([], id="organization-not-an-object"),
    ],
)
def test_parse_ror_response_without_usable_names(organization: object) -> None:
    text = json.dumps({"items": [{"chosen": True, "organization": organization}]})

    assert parse_ror_response(text, "Massachusetts Institute of Technology, Cambridge, MA") is None


def test_match_institution_of_an_unknown_string() -> None:
    with HttpClient(transport=httpx.MockTransport(lambda _: httpx.Response(404)), max_attempts=1) as client:
        assert match_institution(client, "Nowhere") is None


@pytest.mark.parametrize("text", ["not json", "{}", '{"items": [42]}'])
def test_parse_ror_response_rejects_unexpected_json(text: str) -> None:
    with pytest.raises(ParseError):
        parse_ror_response(text, "MIT")


def _client(requested: list[str]) -> HttpClient:
    def handle(request: httpx.Request) -> httpx.Response:
        affiliation = request.url.params["affiliation"]
        requested.append(affiliation)
        if affiliation.startswith("Unreachable"):
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


def test_match_institutions_stops_at_the_limit() -> None:
    requested: list[str] = []
    with _client(requested) as client:
        matches = match_institutions(client, ["Meta AI", "Peking University"], limit=1)

    assert matches == {"Meta AI": None}
    assert requested == ["Meta AI"]


def test_match_institutions_skips_a_failure_and_stops_when_ror_is_down() -> None:
    requested: list[str] = []
    strings = ["Unreachable 1", "Meta AI", "Unreachable 2", "Unreachable 3", "Unreachable 4", "Later"]
    with _client(requested) as client:
        matches = match_institutions(client, strings)

    # One failure is skipped (left for the next run); three in a row stop the lookups.
    assert matches == {"Meta AI": None}
    assert requested == strings[:5]
