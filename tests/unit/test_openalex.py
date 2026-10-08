import json

import httpx
import pytest
from tests.conftest import FIXTURES_DIR

from preprint_radar.exceptions import ParseError
from preprint_radar.http import HttpClient
from preprint_radar.models import Institution
from preprint_radar.sources.openalex import (
    OPENALEX_BATCH_SIZE,
    PublishedAuthor,
    affiliations_from_authorships,
    fetch_affiliations,
    fetch_published_authors,
    parse_published_works,
    parse_works,
    published_affiliations,
)

WORKS = (FIXTURES_DIR / "openalex" / "works.json").read_text(encoding="utf-8")


def test_parse_works_names_institutions_per_author() -> None:
    works = parse_works(WORKS)

    assert [[i.name for i in names] for names in works["1512.03385"]] == [
        ["Microsoft"]
    ] * 4  # "Microsoft (United States)"
    assert [i.name for i in works["2010.11929"][3]] == ["German Research Centre for Artificial Intelligence"]
    # With their ROR ids.
    assert all(institution.ror_id for names in works["1512.03385"] for institution in names)


def test_affiliations_from_authorships() -> None:
    google, eth = Institution("Google", "00njsd438"), Institution("ETH Zurich", None)
    both = affiliations_from_authorships([[google], [google, eth], []], 3)

    assert both.affiliations == ("Google", "ETH Zurich")
    assert both.author_affiliations == ((0,), (0, 1), None)
    assert both.institution_ids == ("00njsd438", None)
    # A different author count: affiliations without the mapping.
    assert affiliations_from_authorships([[google]], 2).author_affiliations is None
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
    institutions = [
        {"display_name": "Google", "ror": "https://ror.org/00njsd438"},
        {"display_name": None},
        "Google",
        {"display_name": "Google"},
    ]
    work = {
        "doi": "https://doi.org/10.48550/arXiv.2609.00001",
        "authorships": [{"institutions": institutions}],
    }

    assert parse_works(json.dumps({"results": [work]})) == {
        "2609.00001": [[Institution("Google", "00njsd438")]]
    }


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


GOOGLE = {"display_name": "Google (United States)", "ror": "https://ror.org/00njsd438", "type": "company"}
ETH = {"display_name": "ETH Zurich", "ror": "https://ror.org/05a28rw58", "type": "education"}


def _authorship(name: str | None, *institutions: dict[str, str], raw: str = "") -> dict[str, object]:
    return {
        "author": {"display_name": name} if name is not None else None,
        "raw_author_name": raw,
        "institutions": list(institutions),
    }


def test_parse_published_works_names_the_authors_and_their_institutions() -> None:
    work = {
        "doi": "https://doi.org/10.1109/CVPR.2016.90",
        "authorships": [
            _authorship("Ada Lovelace", GOOGLE),
            _authorship(None, ETH, raw="Turing, Alan"),  # no OpenAlex author: the work's name
        ],
    }
    no_doi = {"doi": None, "authorships": [_authorship("Grace Hopper")]}

    assert parse_published_works(json.dumps({"results": [work, no_doi]})) == {
        "10.1109/cvpr.2016.90": [
            PublishedAuthor("Ada Lovelace", (Institution("Google", "00njsd438"),)),
            PublishedAuthor("Turing, Alan", (Institution("ETH Zurich", "05a28rw58"),)),
        ]
    }


@pytest.mark.parametrize("text", ["not json", "{}", '{"results": [42]}'])
def test_parse_published_works_rejects_unexpected_json(text: str) -> None:
    with pytest.raises(ParseError, match="Unexpected OpenAlex response"):
        parse_published_works(text)


GOOGLE_INSTITUTION = Institution("Google", "00njsd438")
ETH_INSTITUTION = Institution("ETH Zurich", "05a28rw58")


def test_published_affiliations_match_the_authors_by_name() -> None:
    published = [
        PublishedAuthor("Alan M. Turing", (ETH_INSTITUTION,)),  # another order
        PublishedAuthor("Charles Babbage", (Institution("Cambridge", None),)),  # not on arXiv
        PublishedAuthor("Ada Lovelace", (GOOGLE_INSTITUTION, ETH_INSTITUTION)),
    ]

    found = published_affiliations(["Ada Lovelace", "Alan Turing", "Grace Hopper"], published)

    assert found is not None
    # Only the arXiv authors' institutions, in their order.
    assert found.affiliations == ("Google", "ETH Zurich")
    assert found.institution_ids == ("00njsd438", "05a28rw58")
    # Grace Hopper is not among the published authors: placed nowhere.
    assert found.author_affiliations == ((0, 1), (1,), None)


def test_published_affiliations_of_another_paper() -> None:
    published = [PublishedAuthor("Ada Lovelace", (GOOGLE_INSTITUTION,)), PublishedAuthor("Someone Else", ())]

    # One author of three: the DOI is another paper's.
    assert published_affiliations(["Ada Lovelace", "Alan Turing", "Grace Hopper"], published) is None
    # Half of them is enough.
    assert published_affiliations(["Ada Lovelace", "Alan Turing"], published) is not None


def test_published_affiliations_without_institutions() -> None:
    found = published_affiliations(["Ada Lovelace"], [PublishedAuthor("Ada Lovelace", ())])

    assert found is not None
    assert found.affiliations == ()
    assert found.author_affiliations is None


def test_fetch_published_authors_asks_50_dois_per_request() -> None:
    filters: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        filters.append(request.url.params["filter"])
        if len(filters) == 2:
            return httpx.Response(503)  # left for next time
        work = {"doi": "https://doi.org/10.1/a", "authorships": [_authorship("Ada Lovelace", GOOGLE)]}
        return httpx.Response(200, json={"results": [work]})

    dois = ["10.1/A", *(f"10.2/{number}" for number in range(OPENALEX_BATCH_SIZE)), "10.3/a|b"]
    with HttpClient(transport=httpx.MockTransport(handle), max_attempts=1) as client:
        found = fetch_published_authors(client, dois)

    assert found == {"10.1/a": [PublishedAuthor("Ada Lovelace", (GOOGLE_INSTITUTION,))]}
    # Lowercase, and without the DOI that would split the filter.
    assert len(filters) == 2
    assert filters[0].startswith("doi:10.1/a|10.2/0|")
    assert "10.3/a" not in "".join(filters)
