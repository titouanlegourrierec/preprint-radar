from dataclasses import replace
from datetime import date

import pytest

from preprint_radar.exceptions import StoreError
from preprint_radar.models import Listing, Paper, Provenance


def test_record_round_trip(listing: Listing) -> None:
    for paper in listing.papers:
        assert Paper.from_record(paper.to_record()) == paper


def test_record_round_trip_keeps_enrichment(listing: Listing) -> None:
    paper = replace(
        listing.papers[0],
        authors=("Ada Lovelace", "Alan Turing", "Grace Hopper"),
        abstract="An abstract.",
        affiliations=("MIT", "NVIDIA"),
        author_affiliations=((0, 1), None, (1,)),
        institutions=("Massachusetts Institute of Technology", None),
        institution_ids=("042nb2s44", None),
        extractor=1,
        affiliations_provenance=Provenance("html", date(2026, 10, 6)),
        institutions_provenance=Provenance("ror"),
    )
    record = paper.to_record()
    restored = Paper.from_record(record)

    assert restored.abstract == "An abstract."
    assert restored.affiliations == ("MIT", "NVIDIA")
    assert restored.author_affiliations == ((0, 1), None, (1,))
    assert restored.institutions == ("Massachusetts Institute of Technology", None)
    assert restored.institution_ids == ("042nb2s44", None)
    assert restored.extractor == 1
    assert record["provenance"] == {
        "affiliations": {"source": "html", "at": "2026-10-06"},
        "institutions": {"source": "ror"},
    }
    assert restored.affiliations_provenance == Provenance("html", date(2026, 10, 6))
    assert restored.institutions_provenance == Provenance("ror")
    assert restored.is_enriched


def test_an_unknown_extractor_and_unknown_ids_are_not_written(listing: Listing) -> None:
    assert "extractor" not in listing.papers[0].to_record()
    assert "institution_ids" not in listing.papers[0].to_record()
    assert "provenance" not in listing.papers[0].to_record()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"affiliations_provenance": Provenance("html")}, "'affiliations' has a provenance but no value"),
        (
            {"affiliations": ("MIT",), "institutions_provenance": Provenance("ror")},
            "'institutions' has a provenance but no value",
        ),
        ({"affiliations": ("MIT",), "affiliations_provenance": Provenance("ror")}, "unknown source"),
        (
            {
                "affiliations": ("MIT",),
                "institutions": (None,),
                "institutions_provenance": Provenance("html"),
            },
            "unknown source",
        ),
    ],
    ids=["affiliations-reset", "institutions-reset", "affiliations-by-ror", "institutions-from-html"],
)
def test_a_provenance_needs_its_field_and_a_source_of_its_kind(
    listing: Listing, changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(listing.papers[0], **changes)


@pytest.mark.parametrize(
    "institutions",
    [None, ("Massachusetts Institute of Technology",)],
    ids=["without-institutions", "not-one-per-affiliation"],
)
def test_institution_ids_follow_the_institutions(
    listing: Listing, institutions: tuple[str, ...] | None
) -> None:
    with pytest.raises(ValueError, match="institution_ids"):
        replace(
            listing.papers[0],
            affiliations=("MIT", "NVIDIA"),
            institutions=institutions and (*institutions, None),
            institution_ids=("042nb2s44",),
        )


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
        ("institutions", [1]),
        # One institution per affiliation, and none without affiliations.
        ("institutions", ["MIT", None]),
        ("extractor", "1"),
        ("extractor", True),
        ("provenance", "html"),
        ("provenance", {"abstract": {"source": "rss"}}),
        ("provenance", {"affiliations": "html"}),
        ("provenance", {"affiliations": {"at": "2026-10-06"}}),
    ],
)
def test_from_record_rejects_invalid_fields(listing: Listing, field: str, value: object) -> None:
    record: dict[str, object] = dict(listing.papers[0].to_record())
    record[field] = value
    with pytest.raises(StoreError, match=r"2609\.30245"):
        Paper.from_record(record)


@pytest.mark.parametrize(
    ("affiliations", "author_affiliations"),
    [
        (["MIT", "NVIDIA"], [[0]]),  # one entry for three authors
        (["MIT", "NVIDIA"], [[0], None, [2]]),  # there is no third affiliation
        (["MIT", "NVIDIA"], [[0], None, [-1]]),
        (["MIT", "NVIDIA"], [[True], None, None]),  # a JSON boolean is not an index
        (None, [[0], None, None]),  # indices into affiliations not retrieved yet
    ],
)
def test_from_record_rejects_a_mapping_out_of_step(
    listing: Listing, affiliations: list[str] | None, author_affiliations: list[list[object] | None]
) -> None:
    record: dict[str, object] = dict(
        replace(listing.papers[0], authors=("Ada Lovelace", "Alan Turing", "Grace Hopper")).to_record()
    )
    record["affiliations"] = affiliations
    record["author_affiliations"] = author_affiliations
    with pytest.raises(StoreError, match="author_affiliations"):
        Paper.from_record(record)
