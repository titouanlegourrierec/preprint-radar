"""The paper record's two sides in step (TEST-15): `Paper.to_record()` and the `Paper`
interface of `web/src/types.ts`, and their `SCHEMA_VERSION`s.

The interface is read as text: its fields are the lines indented by exactly two spaces
inside `export interface Paper {`, up to the `}` that closes it at the start of a line, so
that the keys of a nested object (`provenance: { affiliations?: ... }`) are not taken for
fields.
"""

import re
from datetime import date
from pathlib import Path

from preprint_radar.models import Paper, Provenance
from preprint_radar.store.paper_store import SCHEMA_VERSION

TYPES = (Path(__file__).parents[2] / "web" / "src" / "types.ts").read_text(encoding="utf-8")
# Fields only the site's records have: the build merges them from scholar.json and code.json.
BUILD_ONLY = {"doi", "author_ids", "code"}
# Fields the store writes only when known: the site cannot count on them.
WRITTEN_WHEN_KNOWN = {"institution_ids", "extractor", "withdrawn", "provenance"}


def _interface_fields() -> dict[str, bool]:
    """The fields of the TypeScript `Paper`, each with whether it is optional (`?`)."""
    body = re.search(r"^export interface Paper \{\n(.*?)^\}", TYPES, re.MULTILINE | re.DOTALL)
    assert body is not None
    return {
        name: optional == "?" for name, optional in re.findall(r"^  (\w+)(\??):", body.group(1), re.MULTILINE)
    }


def _full_record() -> dict[str, object]:
    """A record with every field the store can write."""
    paper = Paper(
        arxiv_id="2609.00001",
        announced=date(2026, 9, 25),
        title="T",
        authors=("Ada Lovelace",),
        affiliations=("MIT",),
        author_affiliations=((0,),),
        institutions=("Massachusetts Institute of Technology",),
        institution_ids=("042nb2s44",),
        extractor=7,
        withdrawn=True,
        affiliations_provenance=Provenance("html", date(2026, 9, 25)),
        institutions_provenance=Provenance("ror", date(2026, 9, 25)),
    )
    return dict(paper.to_record())


def test_the_site_reads_every_field_the_store_writes() -> None:
    fields = _interface_fields()

    assert set(fields) - BUILD_ONLY == set(_full_record())


def test_fields_written_only_when_known_are_optional_on_the_site() -> None:
    fields = _interface_fields()

    assert all(fields[name] for name in WRITTEN_WHEN_KNOWN | BUILD_ONLY)


def test_both_sides_have_the_same_schema_version() -> None:
    version = re.search(r"^export const SCHEMA_VERSION = (\d+);$", TYPES, re.MULTILINE)

    assert version is not None
    assert int(version.group(1)) == SCHEMA_VERSION
