import gzip
from datetime import date
from pathlib import Path

import httpx
import pytest
from tests.conftest import FIXTURES_DIR

from preprint_radar.catalog import Catalog, CatalogEntry, parse_list_records
from preprint_radar.exceptions import FetchError, ParseError, StoreError
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
        self.expired = False

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


def test_catalog_restarts_a_harvest_whose_token_expired(tmp_path: Path) -> None:
    fake = FakeOai(fail_second_page=True)
    catalog = Catalog(tmp_path, "cs.CV")
    with fake.client() as client, pytest.raises(FetchError):
        catalog.refresh(client, date(2026, 9, 30))

    expired = (
        '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><error code="badResumptionToken"/></OAI-PMH>'
    )
    handle = fake.handle

    def with_expired_token(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("resumptionToken") == NEXT_PAGE and fake.expired:
            fake.expired = False
            return httpx.Response(200, text=expired)
        return handle(request)

    fake.expired = True
    with HttpClient(transport=httpx.MockTransport(with_expired_token), max_attempts=1) as client:
        catalog.refresh(client, date(2026, 10, 7))

    assert sorted(catalog.entries()) == ["0904.2037", "1001.1020", "1001.9999"]


def test_first_seen_of_an_old_style_identifier_is_created() -> None:
    entry = CatalogEntry(
        arxiv_id="cs/0601001", created=date(2006, 1, 2), categories=("cs.CV",), title="T", authors=()
    )

    assert entry.first_seen == date(2006, 1, 2)


def test_records_without_metadata_id_or_title_are_skipped() -> None:
    record = PAGE.split("<record>")[1].split("</record>")[0]
    without_metadata = record.split("<metadata>")[0] + "</record>"
    without_title = record.replace(
        "<title>Boosting through Optimization of Margin Distributions</title>", "<title> </title>"
    )
    nameless_author = record.replace("<keyname>Shen</keyname>", "").replace(
        "<forenames>Chunhua</forenames>", ""
    )
    xml = PAGE.replace(record, f"{without_metadata}<record>{without_title}</record><record>{nameless_author}")

    entries = parse_list_records(xml).entries

    assert [entry.arxiv_id for entry in entries] == ["0904.2037", "1001.1020"]
    assert entries[0].authors == ("Hanxi Li",)


def test_invalid_records_raise() -> None:
    with pytest.raises(TypeError, match="Expected a list"):
        CatalogEntry.from_record(
            {"id": "1", "created": "2020-01-01", "categories": "cs.CV", "title": "T", "authors": []}
        )


def test_an_invalid_state_raises(tmp_path: Path) -> None:
    catalog = Catalog(tmp_path, "cs.CV")
    (tmp_path / "cs.CV.state.json").write_text("{not json", encoding="utf-8")

    with FakeOai().client() as client, pytest.raises(StoreError, match="Invalid catalog state"):
        catalog.refresh(client, date(2026, 9, 30))


@pytest.mark.parametrize(
    "content",
    [
        b"not gzip at all",
        gzip.compress(b"not json\n"),
        gzip.compress(b'{"id": "1"}\n'),
        gzip.compress(b'{"id": "1", "created": "2020-01-01"}\n')[:-12],
    ],
)
def test_an_invalid_catalog_raises(tmp_path: Path, content: bytes) -> None:
    catalog = Catalog(tmp_path, "cs.CV")
    catalog.path.write_bytes(content)

    with pytest.raises(StoreError, match="Invalid catalog"):
        catalog.entries()


def test_a_harvest_killed_while_writing_a_page_resumes(tmp_path: Path) -> None:
    fake = FakeOai(fail_second_page=True)
    catalog = Catalog(tmp_path, "cs.CV")
    with fake.client() as client, pytest.raises(FetchError):
        catalog.refresh(client, date(2026, 9, 30))
    # The run was killed while appending the next page: half a gzip member.
    record = '{"id": "1001.5555", "created": "2010-01-05", "categories": [], "title": "Cut", "authors": []}\n'
    member = gzip.compress(record.encode())
    partial = tmp_path / "cs.CV.partial.jsonl.gz"
    partial.write_bytes(partial.read_bytes() + member[: len(member) // 2])

    with fake.client() as client:
        catalog.refresh(client, date(2026, 9, 30))

    assert sorted(catalog.entries()) == ["0904.2037", "1001.1020", "1001.9999"]
