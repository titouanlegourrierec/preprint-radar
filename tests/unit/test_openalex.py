import json

import httpx
import pytest
from tests.conftest import FIXTURES_DIR

from preprint_radar.exceptions import ParseError
from preprint_radar.http import HttpClient
from preprint_radar.sources.openalex import affiliations_from_authorships, fetch_affiliations, parse_works

WORKS = (FIXTURES_DIR / "openalex" / "works.json").read_text(encoding="utf-8")


def test_parse_works_names_institutions_per_author() -> None:
    works = parse_works(WORKS)

    assert works["1512.03385"] == [["Microsoft"]] * 4  # "Microsoft (United States)"
    assert works["2010.11929"][3] == ["German Research Centre for Artificial Intelligence"]


def test_affiliations_from_authorships() -> None:
    both = affiliations_from_authorships([["Google"], ["Google", "ETH Zurich"], []], 3)

    assert both.affiliations == ("Google", "ETH Zurich")
    assert both.author_affiliations == ((0,), (0, 1), None)
    # A different author count: affiliations without the mapping.
    assert affiliations_from_authorships([["Google"]], 2).author_affiliations is None
    assert affiliations_from_authorships([], 2).affiliations == ()


def test_fetch_affiliations_asks_one_by_one_for_what_a_batch_misses() -> None:
    vit, resnet = json.loads(WORKS)["results"]
    batch_answer = json.dumps({"results": [resnet]})  # the batch misses ViT

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/works"):
            return httpx.Response(200, text=batch_answer)
        if path.endswith("2010.11929"):
            return httpx.Response(200, text=json.dumps(vit))
        if path.endswith("2609.99999"):
            return httpx.Response(404)
        return httpx.Response(503)

    with HttpClient(transport=httpx.MockTransport(handle), max_attempts=1) as client:
        found = fetch_affiliations(
            client, {"1512.03385": 4, "2010.11929": 4, "2609.99999": 2, "2609.88888": 2}
        )

    assert found["1512.03385"].affiliations == ("Microsoft",)  # in the batch answer
    assert found["2010.11929"].affiliations[0] == "Google"  # missed by the batch, found alone
    assert found["2609.99999"].affiliations == ()  # unknown to OpenAlex
    assert "2609.88888" not in found  # the lookup failed: tried again next time


def test_parse_works_skips_unnamed_and_repeated_institutions() -> None:
    institutions = [{"display_name": "Google"}, {"display_name": None}, "Google", {"display_name": "Google"}]
    work = {
        "doi": "https://doi.org/10.48550/arXiv.2609.00001",
        "authorships": [{"institutions": institutions}],
    }

    assert parse_works(json.dumps({"results": [work]})) == {"2609.00001": [["Google"]]}


@pytest.mark.parametrize("text", ["not json", "{}", '{"results": [42]}'])
def test_parse_works_rejects_unexpected_json(text: str) -> None:
    with pytest.raises(ParseError, match="Unexpected OpenAlex response"):
        parse_works(text)


def test_fetch_affiliations_leaves_a_failed_batch_for_later() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503)

    with HttpClient(transport=httpx.MockTransport(handle), max_attempts=1) as client:
        assert fetch_affiliations(client, {"1512.03385": 4, "2010.11929": 4}) == {}
    assert len(requests) == 1  # no one-by-one lookups after a failed batch
