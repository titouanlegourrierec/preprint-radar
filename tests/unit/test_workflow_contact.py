"""The contact goes to the workflow steps that reach arXiv only (PUB-6).

Actions prints a step's environment in its public log: a job-level contact would be in
every step's header, third-party actions included, while only arXiv's requests carry it.
"""

import re
from pathlib import Path

WORKFLOWS = Path(__file__).parents[2] / ".github" / "workflows"
_STEP_RE = re.compile(r"^      - (?:name: (.+)|run: (.+)|uses: (.+))$")


def _steps_with_contact() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in sorted(WORKFLOWS.glob("*.yml")):
        step = ""
        for line in path.read_text(encoding="utf-8").splitlines():
            if match := _STEP_RE.match(line):
                step = next(group for group in match.groups() if group)
            elif line.lstrip().startswith("PREPRINT_RADAR_CONTACT:"):
                # A job's env sits at 6 spaces, a step's at 10.
                found.add((path.name, step if line.startswith(" " * 10) else "the whole job"))
    return found


def test_the_contact_is_given_to_the_steps_that_reach_arxiv_only() -> None:
    assert _steps_with_contact() == {
        ("update.yml", "Fetch papers"),
        ("update.yml", "Extract stored papers again"),
        ("archive.yml", "Update the archive"),
        # The highly cited papers' HTML pages (OPS-6).
        ("archive.yml", "Read the affiliations of the highly cited papers"),
        ("canary.yml", "uv run pytest -m network"),
    }
