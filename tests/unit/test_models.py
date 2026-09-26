from dataclasses import replace

import pytest

from preprint_radar.exceptions import StoreError
from preprint_radar.models import Listing, Paper


def test_record_round_trip(listing: Listing) -> None:
    for paper in listing.papers:
        assert Paper.from_record(paper.to_record()) == paper


def test_record_round_trip_keeps_enrichment(listing: Listing) -> None:
    paper = replace(
        listing.papers[0],
        abstract="An abstract.",
        affiliations=("MIT", "NVIDIA"),
        author_affiliations=((0, 1), None, (1,)),
    )
    restored = Paper.from_record(paper.to_record())

    assert restored.abstract == "An abstract."
    assert restored.affiliations == ("MIT", "NVIDIA")
    assert restored.author_affiliations == ((0, 1), None, (1,))
    assert restored.is_enriched


def test_urls(listing: Listing) -> None:
    paper = listing.papers[0]
    assert paper.abs_url == "https://arxiv.org/abs/2609.30245"
    assert paper.pdf_url == "https://arxiv.org/pdf/2609.30245"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", None),
        ("authors", "not a list"),
        ("announced", "yesterday"),
        ("abstract", 42),
        ("author_affiliations", "not a list"),
        ("author_affiliations", [["one"]]),
    ],
)
def test_from_record_rejects_invalid_fields(listing: Listing, field: str, value: object) -> None:
    record: dict[str, object] = dict(listing.papers[0].to_record())
    record[field] = value
    with pytest.raises(StoreError, match=r"2609\.30245"):
        Paper.from_record(record)
