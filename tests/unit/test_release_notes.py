"""The script that turns a CHANGELOG.md section into the notes of a GitHub release."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / ".github" / "scripts" / "release-notes.sh"
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="needs bash")

CHANGELOG = """# Changelog

Intro.

## 0.2.0 (2026-10-01): a phase

Phase 0 of the roadmap.

### Data

- A list item wrapped
  over two lines.
- Another one.

A paragraph wrapped
over two lines.

## 0.1.0 (2026-09-30): baseline

The baseline.
"""


def _notes(version: str, changelog: Path) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    # A fixed script on a temporary file.
    return subprocess.run(  # noqa: S603
        [BASH, str(SCRIPT), version, str(changelog)], capture_output=True, text=True, check=False
    )


@pytest.fixture
def changelog(tmp_path: Path) -> Path:
    path = tmp_path / "CHANGELOG.md"
    path.write_text(CHANGELOG, encoding="utf-8")
    return path


def test_notes_are_the_section_of_the_version_unwrapped(changelog: Path) -> None:
    result = _notes("v0.2.0", changelog)

    assert result.returncode == 0
    assert result.stdout == (
        "Phase 0 of the roadmap.\n\n### Data\n\n- A list item wrapped over two lines.\n- Another one.\n\n"
        "A paragraph wrapped over two lines.\n"
    )
    assert _notes("0.1.0", changelog).stdout == "The baseline.\n"


def test_a_version_without_a_section_fails(changelog: Path) -> None:
    result = _notes("0.3.0", changelog)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "has no section for 0.3.0" in result.stderr


def test_the_changelog_has_a_section_for_the_current_version() -> None:
    version = re.search(r'^version = "(.+)"$', (ROOT / "pyproject.toml").read_text(), re.MULTILINE)
    assert version is not None

    assert _notes(version.group(1), ROOT / "CHANGELOG.md").returncode == 0
