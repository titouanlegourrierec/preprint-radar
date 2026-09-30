from datetime import date
from pathlib import Path

import httpx
import pytest
from tests.conftest import FIXTURES_DIR

from preprint_radar.catalog import Catalog, CatalogEntry, parse_list_records
from preprint_radar.exceptions import FetchError, ParseError
from preprint_radar.http import HttpClient

PAGE = (FIXTURES_DIR / "oai" / "list_records.xml").read_text(encoding="utf-8")
NEXT_PAGE = "fixture-token"  # the resumption token of the fixture page
NO_RECORDS = (
    '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
    '<error code="noRecordsMatch">No records</error></OAI-PMH>'
)


def test_parse_list_records() -> None:
    page = parse_list_records(PAGE)

    assert page.resumption_token == NEXT_PAGE
    first, second = page.entries  # the deleted record is skipped
    assert first.arxiv_id == "0904.2037"
    assert first.categories == ("cs.LG", "cs.CV")
    assert first.title == "Boosting through Optimization of Margin Distributions"
    assert first.authors == ("Chunhua Shen", "Hanxi Li")
    assert first.abstract is not None
    assert first.abstract.startswith("Boosting has attracted much research attention")
    assert first.comments is not None
    assert "IEEE Transactions on Neural Networks" in first.comments
    assert second.authors == ("Ping Li",)
    assert second.comments is None


def test_first_seen_comes_from_the_identifier_when_created_disagrees() -> None:
    first, second = parse_list_records(PAGE).entries

    # 0904.2037 was first submitted in April 2009, although OAI says created 2010-01-06.
    assert first.first_seen == date(2009, 4, 1)
    assert second.first_seen == date(2010, 1, 7)


def test_no_records_is_an_empty_last_page() -> None:
    page = parse_list_records(NO_RECORDS)

    assert page.entries == ()
    assert page.resumption_token is None


@pytest.mark.parametrize(
    "xml",
    [
        "not xml",
        '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><error code="badArgument">x</error></OAI-PMH>',
        '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"></OAI-PMH>',
    ],
)
def test_invalid_pages_raise(xml: str) -> None:
    with pytest.raises(ParseError):
        parse_list_records(xml)


def test_entry_record_round_trip() -> None:
    entry = parse_list_records(PAGE).entries[0]

    assert CatalogEntry.from_record(entry.to_record()) == entry


class FakeOai:
    """Serve the fixture page, then a last page; optionally fail once on the second."""

    def __init__(self, *, fail_second_page: bool = False) -> None:
        self.params: list[dict[str, str]] = []
        self.fail_second_page = fail_second_page

    def handle(self, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        self.params.append(params)
        if params.get("resumptionToken") == NEXT_PAGE:
            if self.fail_second_page:
                self.fail_second_page = False
                return httpx.Response(500)
            last = PAGE.replace("0904.2037", "1001.9999").replace(
                '<resumptionToken cursor="0" completeListSize="5">fixture-token</resumptionToken>', ""
            )
            return httpx.Response(200, text=last)
        if "from" in params:
            return httpx.Response(200, text=NO_RECORDS)
        return httpx.Response(200, text=PAGE)

    def client(self) -> HttpClient:
        return HttpClient(transport=httpx.MockTransport(self.handle), max_attempts=1)


def test_catalog_harvests_everything_then_what_changed(tmp_path: Path) -> None:
    fake = FakeOai()
    catalog = Catalog(tmp_path, "cs.CV")

    with fake.client() as client:
        first = catalog.refresh(client, date(2026, 9, 30))
        second = catalog.refresh(client, date(2026, 10, 7))

    assert catalog.set_spec == "cs:cs:CV"
    assert first == 4  # two records on each page
    assert second == 0
    assert sorted(catalog.entries()) == ["0904.2037", "1001.1020", "1001.9999"]
    assert fake.params[0] == {"verb": "ListRecords", "metadataPrefix": "arXiv", "set": "cs:cs:CV"}
    # The refresh starts a day before the previous harvest.
    assert fake.params[-1]["from"] == "2026-09-29"


def test_catalog_resumes_an_interrupted_harvest(tmp_path: Path) -> None:
    fake = FakeOai(fail_second_page=True)
    catalog = Catalog(tmp_path, "cs.CV")

    with fake.client() as client:
        with pytest.raises(FetchError):
            catalog.refresh(client, date(2026, 9, 30))
        assert catalog.entries() == {}  # nothing merged yet
        catalog.refresh(client, date(2026, 9, 30))

    assert sorted(catalog.entries()) == ["0904.2037", "1001.1020", "1001.9999"]
    # The second run asked for the second page only.
    assert fake.params[-1] == {"verb": "ListRecords", "resumptionToken": NEXT_PAGE}
