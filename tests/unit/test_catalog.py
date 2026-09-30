import gzip
from datetime import date
from pathlib import Path

import httpx
import pytest
from tests.conftest import FIXTURES_DIR

from preprint_radar.archive.catalog import Catalog
from preprint_radar.exceptions import FetchError, StoreError
from preprint_radar.http import HttpClient

PAGE = (FIXTURES_DIR / "oai" / "list_records.xml").read_text(encoding="utf-8")
NEXT_PAGE = "fixture-token"  # the resumption token of the fixture page
NO_RECORDS = (
    '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
    '<error code="noRecordsMatch">No records</error></OAI-PMH>'
)


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
