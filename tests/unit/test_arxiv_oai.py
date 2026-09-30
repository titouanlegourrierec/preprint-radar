from datetime import date

import pytest
from tests.conftest import FIXTURES_DIR

from preprint_radar.exceptions import ParseError
from preprint_radar.sources.arxiv_oai import CatalogEntry, parse_list_records

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
