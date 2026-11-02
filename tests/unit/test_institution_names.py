"""What the naming rules give 3,704 stored affiliation strings, pinned (EXT-5).

The named tests of ``test_institutions.py`` say what a rule is for; this one shows what a
change does to real strings at once: every rule but a few could go with them all green. The
strings are those of the store of 2026-11-02 read from pages, half of those the rules name
otherwise than their first part, a twentieth of the others, and those they name nothing.
After a deliberate change, write it again and review the diff of the file::

    UPDATE_GOLDEN=1 uv run pytest tests/unit/test_institution_names.py
"""

import json
import os

from tests.conftest import FIXTURES_DIR

from preprint_radar.institutions import institution_name

NAMES = FIXTURES_DIR / "institution-names.json"


def test_the_rules_name_stored_strings_as_they_did() -> None:
    expected: dict[str, str | None] = json.loads(NAMES.read_text(encoding="utf-8"))
    actual = {affiliation: institution_name(affiliation) for affiliation in expected}
    if os.environ.get("UPDATE_GOLDEN"):
        lines = [
            f"  {json.dumps(key, ensure_ascii=False)}: {json.dumps(name, ensure_ascii=False)}"
            for key, name in actual.items()
        ]
        NAMES.write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")
    changed = {key: (expected[key], name) for key, name in actual.items() if name != expected[key]}
    assert changed == {}
